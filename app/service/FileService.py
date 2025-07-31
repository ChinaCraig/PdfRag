"""
文件管理服务 - 简化版
负责PDF文件的上传、删除、重命名等基础文件管理功能
GraphRAG功能已迁移到GraphRAGService
"""
import os
import uuid
import logging
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional

from utils.config_loader import config_loader
from utils.database import mysql_manager

logger = logging.getLogger(__name__)

class FileService:
    """文件管理服务类 - 简化版，专注基础文件管理功能"""
    
    def __init__(self):
        self.config = config_loader.get_app_config()
        self.upload_dir = self.config["upload"]["upload_dir"]
        self.allowed_extensions = set(self.config["upload"]["allowed_extensions"])
        self.max_file_size = self.config["upload"]["max_file_size"] * 1024 * 1024  # MB to bytes
        
        # 确保上传目录存在
        os.makedirs(self.upload_dir, exist_ok=True)
        
        logger.info("文件服务初始化完成 - 基础文件管理版")
    
    def upload_file(self, file, filename: str, original_filename: str = None) -> Dict[str, Any]:
        """
        上传PDF文件
        
        Args:
            file: 上传的文件对象
            filename: 处理后的文件名（用于类型检查）
            original_filename: 原始文件名（用于显示）
            
        Returns:
            上传结果
        """
        try:
            # 使用原始文件名或处理后的文件名进行类型检查
            check_filename = original_filename or filename
            display_filename = original_filename or filename
            
            logger.info(f"📁 开始上传文件: {display_filename}")
            
            # 检查文件类型
            if not self._allowed_file(check_filename):
                logger.warning(f"❌ 不支持的文件类型: {check_filename}")
                return {
                    "success": False,
                    "message": f"不支持的文件类型，仅支持: {', '.join(self.allowed_extensions)}"
                }
            
            # 检查文件大小
            file.seek(0, 2)  # 移动到文件末尾
            file_size = file.tell()
            file.seek(0)  # 重置文件指针
            
            if file_size > self.max_file_size:
                return {
                    "success": False,
                    "message": f"文件大小超过限制 ({self.max_file_size // 1024 // 1024}MB)"
                }
            
            # 生成唯一文件ID和保存路径
            file_id = str(uuid.uuid4())
            
            # 生成安全的存储文件名
            import time
            timestamp = str(int(time.time()))
            safe_filename = f"{file_id}_{timestamp}.pdf"
            file_path = os.path.join(self.upload_dir, safe_filename)
            
            logger.info(f"💾 保存文件: {file_path}")
            
            # 保存文件
            file.save(file_path)
            
            # 保存文件信息到数据库
            file_info = {
                "file_id": file_id,
                "original_filename": display_filename,
                "filename": safe_filename,
                "file_path": file_path,
                "file_size": file_size,
                "upload_time": datetime.now(),
                "status": "uploaded",
                "processing_progress": 0
            }
            
            logger.info(f"💾 保存文件信息到数据库...")
            self._save_file_info(file_info)
            logger.info(f"✅ 文件上传成功: {display_filename}")
            
            # 异步启动GraphRAG处理（使用独立的GraphRAG服务）
            logger.info(f"🚀 启动GraphRAG处理...")
            self._start_graphrag_processing(file_id, file_path)
            
            return {
                "success": True,
                "message": "文件上传成功，GraphRAG处理已开始",
                "file_id": file_id,
                "filename": display_filename
            }
            
        except Exception as e:
            logger.error(f"❌ 文件上传失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"文件上传失败: {str(e)}"
            }
    
    def _start_graphrag_processing(self, file_id: str, file_path: str) -> None:
        """启动GraphRAG处理线程"""
        try:
            thread = threading.Thread(
                target=self._process_file_with_graphrag_service,
                args=(file_id, file_path),
                name=f"GraphRAG-{file_id[:8]}",
                daemon=True
            )
            thread.start()
            logger.info(f"✅ GraphRAG处理线程已启动: {file_id}")
        except Exception as e:
            logger.error(f"❌ 启动GraphRAG处理线程失败: {e}")
            self._update_file_status(file_id, "failed", 0, f"启动处理失败: {str(e)}")
    
    def _process_file_with_graphrag_service(self, file_id: str, file_path: str) -> None:
        """使用GraphRAG服务处理文件"""
        try:
            # 导入GraphRAG服务
            from app.service.GraphRAGService import graphrag_service
            
            # 调用GraphRAG服务处理文件
            result = graphrag_service.process_pdf_file(file_id, file_path)
            
            if result["success"]:
                logger.info(f"✅ GraphRAG处理成功: {file_id}")
            else:
                logger.error(f"❌ GraphRAG处理失败: {file_id}, 原因: {result['message']}")
                self._update_file_status(file_id, "failed", 0, result["message"])
                
        except Exception as e:
            logger.error(f"❌ GraphRAG服务处理异常: {file_id}, 错误: {e}", exc_info=True)
            self._update_file_status(file_id, "failed", 0, f"处理异常: {str(e)}")
    
    def delete_file(self, file_id: str) -> Dict[str, Any]:
        """
        删除文件
        
        Args:
            file_id: 文件ID
            
        Returns:
            删除结果
        """
        try:
            # 获取文件信息
            file_info = self._get_file_info(file_id)
            if not file_info:
                return {
                    "success": False,
                    "message": "文件不存在"
                }
            
            # 删除物理文件
            if os.path.exists(file_info["file_path"]):
                os.remove(file_info["file_path"])
            
            # 从数据库删除文件信息
            self._delete_file_info(file_id)
            
            # 删除向量数据（调用相应的数据库清理）
            self._delete_vector_data(file_id)
            
            # 删除图数据（调用相应的数据库清理）
            self._delete_graph_data(file_id)
            
            return {
                "success": True,
                "message": "文件删除成功"
            }
            
        except Exception as e:
            logger.error(f"文件删除失败: {e}")
            return {
                "success": False,
                "message": f"文件删除失败: {str(e)}"
            }
    
    def rename_file(self, file_id: str, new_filename: str) -> Dict[str, Any]:
        """
        重命名文件
        
        Args:
            file_id: 文件ID
            new_filename: 新文件名
            
        Returns:
            重命名结果
        """
        try:
            # 检查文件是否存在
            file_info = self._get_file_info(file_id)
            if not file_info:
                return {
                    "success": False,
                    "message": "文件不存在"
                }
            
            # 更新文件名
            mysql_manager.execute_update(
                "UPDATE files SET original_filename = %s WHERE file_id = %s",
                (new_filename, file_id)
            )
            
            return {
                "success": True,
                "message": "文件重命名成功"
            }
            
        except Exception as e:
            logger.error(f"文件重命名失败: {e}")
            return {
                "success": False,
                "message": f"文件重命名失败: {str(e)}"
            }
    
    def get_file_list(self) -> List[Dict[str, Any]]:
        """
        获取文件列表
        
        Returns:
            文件列表
        """
        try:
            files = mysql_manager.execute_query(
                "SELECT file_id, original_filename, file_size, upload_time, status, processing_progress FROM files ORDER BY upload_time DESC"
            )
            
            return files
            
        except Exception as e:
            logger.error(f"获取文件列表失败: {e}")
            return []
    
    def get_processing_status(self, file_id: str) -> Dict[str, Any]:
        """
        获取文件处理状态
        
        Args:
            file_id: 文件ID
            
        Returns:
            处理状态信息
        """
        # 从数据库获取状态
        file_info = self._get_file_info(file_id)
        if file_info:
            return {
                "status": file_info["status"],
                "progress": file_info["processing_progress"],
                "message": "处理中..." if file_info["status"] == "processing" else "处理完成"
            }
        
        return {
            "status": "not_found",
            "progress": 0,
            "message": "文件不存在"
        }
    
    def get_file_detailed_info(self, file_id: str) -> Dict[str, Any]:
        """
        获取文件详细信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件详细信息
        """
        try:
            # 获取基本文件信息
            file_info = self._get_file_info(file_id)
            if not file_info:
                return {
                    "success": False,
                    "message": "文件不存在"
                }
            
            # 获取处理状态
            status_info = self.get_processing_status(file_id)
            
            # 获取统计信息
            stats = self._get_file_statistics(file_id)
            
            return {
                "success": True,
                "file_info": {
                    "file_id": file_info["file_id"],
                    "original_filename": file_info["original_filename"],
                    "file_size": file_info["file_size"],
                    "upload_time": file_info["upload_time"],
                    "status": file_info["status"],
                    "processing_progress": file_info["processing_progress"],
                    "file_path": file_info["file_path"]
                },
                "processing_info": status_info,
                "statistics": stats
            }
            
        except Exception as e:
            logger.error(f"获取文件详细信息失败: {e}")
            return {
                "success": False,
                "message": f"获取文件详细信息失败: {str(e)}"
            }
    
    def _get_file_statistics(self, file_id: str) -> Dict[str, Any]:
        """
        获取文件统计信息
        
        Args:
            file_id: 文件ID
            
        Returns:
            统计信息
        """
        try:
            # 获取向量数据统计
            vector_count = 0
            try:
                # 延迟导入避免循环依赖
                from utils.database import milvus_manager
                
                if milvus_manager.collection and milvus_manager.has_data():
                    # 查询向量数据数量
                    vector_result = milvus_manager.collection.query(
                        expr=f"file_id == '{file_id}'",
                        output_fields=["chunk_id"]
                    )
                    vector_count = len(vector_result) if vector_result else 0
            except Exception as e:
                logger.warning(f"获取向量数据统计失败: {e}")
            
            # 获取图数据统计
            entity_count = 0
            relation_count = 0
            try:
                # 延迟导入避免循环依赖
                from utils.database import neo4j_manager
                
                entity_result = neo4j_manager.execute_query(
                    "MATCH (n) WHERE n.file_id = $file_id RETURN count(n) as count",
                    {"file_id": file_id}
                )
                entity_count = entity_result[0]["count"] if entity_result else 0
                
                relation_result = neo4j_manager.execute_query(
                    "MATCH ()-[r]->() WHERE r.file_id = $file_id RETURN count(r) as count",
                    {"file_id": file_id}
                )
                relation_count = relation_result[0]["count"] if relation_result else 0
            except Exception as e:
                logger.warning(f"获取图数据统计失败: {e}")
            
            return {
                "chunks_count": vector_count,
                "entities_count": entity_count,
                "relations_count": relation_count
            }
            
        except Exception as e:
            logger.error(f"获取文件统计信息失败: {e}")
            return {
                "chunks_count": 0,
                "entities_count": 0,
                "relations_count": 0
            }
    
    def _allowed_file(self, filename: str) -> bool:
        """检查文件类型是否允许"""
        return '.' in filename and \
               '.' + filename.rsplit('.', 1)[1].lower() in self.allowed_extensions
    
    def _save_file_info(self, file_info: Dict[str, Any]) -> None:
        """保存文件信息到数据库"""
        try:
            mysql_manager.execute_update(
                """
                INSERT INTO files (file_id, original_filename, filename, file_path, file_size, upload_time, status, processing_progress)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    file_info["file_id"],
                    file_info["original_filename"],
                    file_info["filename"],
                    file_info["file_path"],
                    file_info["file_size"],
                    file_info["upload_time"],
                    file_info["status"],
                    file_info["processing_progress"]
                )
            )
            logger.info(f"✅ 文件信息保存成功: {file_info['file_id']}")
        except Exception as e:
            logger.error(f"❌ 保存文件信息失败: {e}")
            raise
    
    def _get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """获取文件信息"""
        results = mysql_manager.execute_query(
            "SELECT * FROM files WHERE file_id = %s",
            (file_id,)
        )
        return results[0] if results else None
    
    def _delete_file_info(self, file_id: str) -> None:
        """从数据库删除文件信息"""
        mysql_manager.execute_update(
            "DELETE FROM files WHERE file_id = %s",
            (file_id,)
        )
    
    def _delete_vector_data(self, file_id: str) -> None:
        """删除向量数据"""
        try:
            # 延迟导入避免循环依赖
            from utils.database import milvus_manager
            
            if milvus_manager.collection and milvus_manager.has_data():
                # 使用Milvus的delete接口删除指定file_id的向量
                expr = f"file_id == '{file_id}'"
                milvus_manager.collection.delete(expr)
                milvus_manager.collection.flush()
                logger.info(f"成功删除文件 {file_id} 的向量数据")
            else:
                logger.info(f"Milvus集合为空或未初始化，跳过删除文件 {file_id} 的向量数据")
        except Exception as e:
            logger.warning(f"删除文件 {file_id} 的向量数据失败: {e}")
    
    def _delete_graph_data(self, file_id: str) -> None:
        """删除图数据"""
        try:
            # 延迟导入避免循环依赖
            from utils.database import neo4j_manager
            
            # 删除实体节点和关系
            neo4j_manager.execute_query(
                "MATCH (n {file_id: $file_id}) DETACH DELETE n",
                {"file_id": file_id}
            )
            # 删除只有file_id属性的关系
            neo4j_manager.execute_query(
                "MATCH ()-[r {file_id: $file_id}]-() DELETE r",
                {"file_id": file_id}
            )
            logger.info(f"成功删除文件 {file_id} 的图数据")
        except Exception as e:
            logger.warning(f"删除文件 {file_id} 的图数据失败: {e}")
    
    def _update_file_status(self, file_id: str, status: str, progress: int, message: str) -> None:
        """更新文件处理状态"""
        try:
            # 更新数据库状态
            mysql_manager.execute_update(
                "UPDATE files SET status = %s, processing_progress = %s WHERE file_id = %s",
                (status, progress, file_id)
            )
            
            logger.info(f"📊 {file_id}: {status} - {progress}% - {message}")
            
        except Exception as e:
            logger.warning(f"更新文件状态失败: {e}")

# 全局文件服务实例
file_service = FileService()