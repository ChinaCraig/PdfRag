"""
文件管理服务
负责PDF文件的上传、删除、重命名以及内容解析和GraphRAG数据提取
"""
import os
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import json
import fitz  # PyMuPDF
from PIL import Image
import io
import threading
from concurrent.futures import ThreadPoolExecutor
import requests
import re

from utils.config_loader import config_loader
from utils.database import mysql_manager, milvus_manager, neo4j_manager
from utils.model_manager import model_manager

logger = logging.getLogger(__name__)

class FileService:
    """文件管理服务类"""
    
    def __init__(self):
        self.config = config_loader.get_app_config()
        self.model_config = config_loader.get_model_config()
        self.prompt_config = config_loader.get_prompt_config()
        self.upload_dir = self.config["upload"]["upload_dir"]
        self.allowed_extensions = set(self.config["upload"]["allowed_extensions"])
        self.max_file_size = self.config["upload"]["max_file_size"] * 1024 * 1024  # MB to bytes
        self.processing_status = {}  # 文件处理状态
        
        # 确保上传目录存在
        os.makedirs(self.upload_dir, exist_ok=True)
    
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
            
            logger.info(f"文件上传检查 - 检查文件名: {check_filename}, 显示文件名: {display_filename}")
            
            # 检查文件类型
            if not self._allowed_file(check_filename):
                logger.warning(f"文件类型检查失败 - 文件名: {check_filename}")
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
            safe_filename = f"{file_id}_{timestamp}.pdf"  # 统一使用.pdf扩展名
            file_path = os.path.join(self.upload_dir, safe_filename)
            
            logger.info(f"保存文件 - 文件ID: {file_id}, 存储路径: {file_path}, 原始文件名: {display_filename}")
            
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
            
            logger.info(f"📋📋📋 准备保存文件信息 - 文件ID: {file_id}")
            logger.info(f"📋 文件信息内容: {file_info}")
            try:
                logger.info(f"📋 调用_save_file_info方法...")
                self._save_file_info(file_info)
                logger.info(f"✅✅✅ 文件信息保存成功 - 文件ID: {file_id}")
            except Exception as db_error:
                logger.error(f"❌❌❌ 文件信息保存失败，但继续进行文件处理 - 文件ID: {file_id}, 错误: {db_error}")
                # 注意：即使数据库保存失败，我们也继续进行文件处理
            
            # 异步开始文件内容识别
            logger.info(f"🚀🚀🚀 准备启动文件处理线程 - 文件ID: {file_id}, 文件路径: {file_path}")
            logger.info(f"🔍 当前upload_file方法正在执行到文件处理部分")
            logger.info(f"🔍 文件处理方法地址: {self._start_file_processing}")
            try:
                logger.info(f"🔍 即将调用self._start_file_processing...")
                self._start_file_processing(file_id, file_path)
                logger.info(f"✅✅✅ 文件处理线程启动命令已发送 - 文件ID: {file_id}")
            except Exception as thread_error:
                logger.error(f"❌❌❌ 文件处理线程启动失败 - 文件ID: {file_id}, 错误: {thread_error}", exc_info=True)
            
            return {
                "success": True,
                "message": "文件上传成功",
                "file_id": file_id,
                "filename": display_filename
            }
            
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            return {
                "success": False,
                "message": f"文件上传失败: {str(e)}"
            }
    
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
            
            # 删除向量数据
            self._delete_vector_data(file_id)
            
            # 删除图数据
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
            
            # 处理文件状态和进度
            for file in files:
                file_id = file["file_id"]
                if file_id in self.processing_status:
                    file["processing_progress"] = self.processing_status[file_id]["progress"]
                    file["status"] = self.processing_status[file_id]["status"]
            
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
        if file_id in self.processing_status:
            return self.processing_status[file_id]
        
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
            logger.info(f"💾 开始保存文件信息到数据库 - 文件ID: {file_info['file_id']}")
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
            logger.info(f"✅ 文件信息已成功保存到数据库 - 文件ID: {file_info['file_id']}")
        except Exception as e:
            logger.error(f"❌ 保存文件信息到数据库失败 - 文件ID: {file_info.get('file_id', 'unknown')}, 错误: {e}", exc_info=True)
            # 不重新抛出异常，让后续处理继续进行
    
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
    
    def _start_file_processing(self, file_id: str, file_path: str) -> None:
        """开始文件内容识别处理"""
        logger.info(f"🔧🔧🔧 _start_file_processing方法被调用 - 文件ID: {file_id}")
        logger.info(f"🔧🔧🔧 方法参数: file_id={file_id}, file_path={file_path}")
        try:
            logger.info(f"🔧 进入try块，开始创建文件处理线程 - 文件ID: {file_id}")
            logger.info(f"🔧 线程目标: _process_file_content_safe, 参数: {file_id}, {file_path}")
            
            # 首先测试是否能创建简单线程
            def test_thread():
                logger.info(f"🧪 测试线程运行成功 - 文件ID: {file_id}")
            
            test = threading.Thread(target=test_thread, name=f"Test-{file_id[:8]}")
            test.daemon = True
            test.start()
            test.join(timeout=1)  # 等待1秒
            logger.info(f"✅ 测试线程完成")
            
            # 在后台线程中处理文件
            thread = threading.Thread(
                target=self._process_file_content_safe,
                args=(file_id, file_path),
                name=f"FileProcessor-{file_id[:8]}"
            )
            thread.daemon = True
            
            logger.info(f"🔧 文件处理线程已创建，准备启动 - 线程名: {thread.name}")
            thread.start()
            logger.info(f"✅ 文件处理线程已启动 - 线程名: {thread.name}, 线程ID: {thread.ident}")
            
            # 立即返回，不等待线程
            return
            
        except Exception as e:
            logger.error(f"❌ 启动文件处理线程失败 - 文件ID: {file_id}, 错误: {e}", exc_info=True)
    
    def _process_file_content_safe(self, file_id: str, file_path: str) -> None:
        """安全的文件处理包装器 - 第一步：PDF文本提取"""
        logger.info(f"🚀🚀🚀 _process_file_content_safe方法被调用 - 文件ID: {file_id}")
        logger.info(f"🚀🚀🚀 线程开始执行，当前线程: {threading.current_thread().name}")
        
        import time
        timeout_timer = None
        
        # 超时处理函数
        def timeout_handler():
            logger.error(f"⏰ PDF处理超时 - 文件ID: {file_id}")
            self._handle_processing_failure(file_id, "处理超时")
        
        try:
            logger.info(f"🚀 进入try块，PDF智能处理启动 - 文件ID: {file_id}")
            logger.info(f"🚀 线程信息: {threading.current_thread().name}")
            
            # 检查文件是否存在
            import os
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            logger.info(f"✅ 文件存在检查通过: {file_path}")
            logger.info(f"📊 文件大小: {os.path.getsize(file_path)} bytes")
            
            # 设置处理状态
            self.processing_status[file_id] = {
                "status": "processing",
                "progress": 10,
                "message": "开始PDF处理..."
            }
            
            # 设置超时控制（60秒） - 使用Timer替代signal
            timeout_timer = threading.Timer(60.0, timeout_handler)
            timeout_timer.start()
            logger.info(f"⏰ 超时控制已启动 (60秒)")
            
            # 第一步：安全的PDF文本提取
            logger.info(f"📖 开始PDF文本提取 - 文件ID: {file_id}")
            text_content = self._safe_pdf_text_extraction(file_id, file_path)
            
            # 更新进度
            self.processing_status[file_id] = {
                "status": "processing",
                "progress": 50,
                "message": "PDF文本提取完成，准备保存..."
            }
            
            # 简单保存文本内容到数据库（作为处理结果的记录）
            logger.info(f"💾 开始保存处理结果 - 文件ID: {file_id}")
            self._save_processing_result(file_id, text_content)
            
            # 取消超时
            if timeout_timer:
                timeout_timer.cancel()
                logger.info(f"⏰ 超时控制已取消")
            
            # 更新状态为完成
            self.processing_status[file_id] = {
                "status": "completed", 
                "progress": 100,
                "message": "PDF处理完成"
            }
            
            # 更新数据库状态
            mysql_manager.execute_update(
                "UPDATE files SET status = 'completed', processing_progress = 100 WHERE file_id = %s",
                (file_id,)
            )
            
            logger.info(f"✅ PDF智能处理完成 - 文件ID: {file_id}")
            
        except Exception as e:
            logger.error(f"❌ PDF处理失败 - 文件ID: {file_id}, 错误: {e}", exc_info=True)
            self._handle_processing_failure(file_id, str(e))
        
        finally:
            # 确保清理超时设置
            if timeout_timer:
                timeout_timer.cancel()
            logger.info(f"🏁 PDF处理线程结束 - 文件ID: {file_id}")
    
    def _safe_pdf_text_extraction(self, file_id: str, file_path: str) -> str:
        """安全的PDF文本提取"""
        try:
            logger.info(f"📖 正在打开PDF文件: {file_path}")
            import fitz
            
            # 打开PDF文档
            doc = fitz.open(file_path)
            total_pages = len(doc)
            logger.info(f"📄 PDF文件打开成功，共 {total_pages} 页")
            
            # 限制处理页数，避免处理过大文件
            max_pages = min(total_pages, 50)  # 最多处理50页
            logger.info(f"📊 将处理前 {max_pages} 页")
            
            all_text = []
            
            # 逐页提取文本
            for page_num in range(max_pages):
                logger.info(f"📖 处理第 {page_num + 1}/{max_pages} 页")
                
                # 更新处理进度
                progress = 10 + int((page_num / max_pages) * 40)  # 10-50%的进度
                self.processing_status[file_id]["progress"] = progress
                self.processing_status[file_id]["message"] = f"提取第 {page_num + 1}/{max_pages} 页文本..."
                
                try:
                    page = doc[page_num]
                    text = page.get_text()
                    
                    if text.strip():
                        all_text.append(f"--- 第 {page_num + 1} 页 ---\n{text.strip()}")
                        logger.debug(f"✅ 第 {page_num + 1} 页文本提取完成，长度: {len(text)}")
                    else:
                        logger.debug(f"⚠️ 第 {page_num + 1} 页无文本内容")
                
                except Exception as page_error:
                    logger.warning(f"⚠️ 第 {page_num + 1} 页处理失败: {page_error}")
                    continue
            
            # 关闭文档
            doc.close()
            logger.info(f"📖 PDF文档已关闭")
            
            # 合并所有文本
            full_text = "\n\n".join(all_text)
            logger.info(f"✅ PDF文本提取完成，总长度: {len(full_text)} 字符")
            
            return full_text
            
        except Exception as e:
            logger.error(f"❌ PDF文本提取失败: {e}", exc_info=True)
            raise
    
    def _save_processing_result(self, file_id: str, content: str) -> None:
        """保存处理结果"""
        try:
            # 简单统计信息
            char_count = len(content)
            line_count = content.count('\n') + 1 if content else 0
            
            logger.info(f"💾 保存处理结果 - 文件ID: {file_id}, 字符数: {char_count}, 行数: {line_count}")
            
            # 这里可以保存到数据库或文件系统
            # 暂时只记录日志
            logger.info(f"✅ 处理结果统计完成 - 文件ID: {file_id}")
            
        except Exception as e:
            logger.error(f"❌ 保存处理结果失败: {e}", exc_info=True)
    
    def _handle_processing_failure(self, file_id: str, error_msg: str) -> None:
        """处理失败的统一处理"""
        try:
            # 更新状态为失败
            self.processing_status[file_id] = {
                "status": "failed",
                "progress": 0,
                "message": f"处理失败: {error_msg}"
            }
            
            # 更新数据库状态
            mysql_manager.execute_update(
                "UPDATE files SET status = 'failed' WHERE file_id = %s",
                (file_id,)
            )
            
            logger.info(f"✅ 失败状态已更新 - 文件ID: {file_id}")
            
        except Exception as db_error:
            logger.error(f"❌ 更新失败状态失败: {db_error}")
    
    def _process_file_content(self, file_id: str, file_path: str) -> None:
        """
        处理文件内容，提取文字、表格、图片、图表等
        
        Args:
            file_id: 文件ID
            file_path: 文件路径
        """
        import threading
        current_thread = threading.current_thread()
        logger.info(f"✅ 文件处理线程已启动 - 线程名: {current_thread.name}, 线程ID: {current_thread.ident}")
        logger.info(f"📄 开始处理文件 {file_id}，路径: {file_path}")
        
        try:
            # 检查文件是否存在
            import os
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            logger.info(f"✅ 文件存在检查通过: {file_path}")
            logger.info(f"📊 文件大小: {os.path.getsize(file_path)} bytes")
            
            # 初始化处理状态
            logger.info(f"🔄 初始化处理状态...")
            self.processing_status[file_id] = {
                "status": "processing",
                "progress": 0,
                "message": "开始处理文件..."
            }
            logger.info(f"✅ 处理状态初始化完成")
            
            # 更新数据库状态
            logger.info(f"💾 更新数据库状态...")
            mysql_manager.execute_update(
                "UPDATE files SET status = 'processing', processing_progress = 0 WHERE file_id = %s",
                (file_id,)
            )
            logger.info(f"✅ 文件 {file_id} 状态已更新为processing")
            
            # 打开PDF文件
            logger.info(f"📖 正在打开PDF文件: {file_path}")
            import fitz
            logger.info(f"✅ fitz模块导入成功")
            doc = fitz.open(file_path)
            total_pages = len(doc)
            logger.info(f"🎉 PDF文件打开成功，共 {total_pages} 页")
            
            all_chunks = []
            entities = []
            relations = []
            
            # 逐页处理
            for page_num in range(total_pages):
                logger.info(f"开始处理第 {page_num + 1}/{total_pages} 页")
                page = doc[page_num]
                
                # 更新进度
                progress = int((page_num / total_pages) * 80)  # 80%用于页面处理
                self.processing_status[file_id]["progress"] = progress
                self.processing_status[file_id]["message"] = f"处理第 {page_num + 1}/{total_pages} 页..."
                
                # 提取文本
                logger.debug(f"提取第 {page_num + 1} 页文本")
                text_content = self._extract_text_from_page(page)
                logger.debug(f"第 {page_num + 1} 页文本提取完成，长度: {len(text_content) if text_content else 0}")
                
                # 提取图像
                logger.debug(f"提取第 {page_num + 1} 页图像")
                images = self._extract_images_from_page(page, page_num)
                logger.debug(f"第 {page_num + 1} 页图像提取完成，数量: {len(images)}")
                
                # 提取表格
                logger.debug(f"提取第 {page_num + 1} 页表格")
                tables = self._extract_tables_from_page(page, page_num)
                logger.debug(f"第 {page_num + 1} 页表格提取完成，数量: {len(tables)}")
                
                # 处理提取的内容
                if text_content:
                    chunks = self._create_text_chunks(text_content, file_id, page_num)
                    all_chunks.extend(chunks)
                
                if images:
                    image_chunks = self._process_images(images, file_id, page_num)
                    all_chunks.extend(image_chunks)
                
                if tables:
                    table_chunks = self._process_tables(tables, file_id, page_num)
                    all_chunks.extend(table_chunks)
            
            doc.close()
            logger.info(f"PDF文件已关闭，总共提取了 {len(all_chunks)} 个内容块")
            
            # 生成嵌入向量
            self.processing_status[file_id]["message"] = "生成嵌入向量..."
            self.processing_status[file_id]["progress"] = 85
            logger.info(f"开始生成 {len(all_chunks)} 个内容块的嵌入向量")
            self._generate_embeddings(all_chunks)
            logger.info("嵌入向量生成完成")
            
            # 提取实体和关系
            self.processing_status[file_id]["message"] = "提取实体和关系..."
            self.processing_status[file_id]["progress"] = 90
            logger.info("开始提取实体和关系")
            entities, relations = self._extract_entities_and_relations(all_chunks)
            logger.info(f"实体和关系提取完成，实体数量: {len(entities)}，关系数量: {len(relations)}")
            
            # 保存到向量数据库
            self.processing_status[file_id]["message"] = "保存到向量数据库..."
            self.processing_status[file_id]["progress"] = 95
            logger.info("开始保存到向量数据库")
            self._save_to_vector_db(all_chunks)
            logger.info("向量数据库保存完成")
            
            # 保存到图数据库
            self.processing_status[file_id]["message"] = "保存到图数据库..."
            logger.info("开始保存到图数据库")
            self._save_to_graph_db(entities, relations, file_id)
            logger.info("图数据库保存完成")
            
            # 完成处理
            self.processing_status[file_id] = {
                "status": "completed",
                "progress": 100,
                "message": "处理完成"
            }
            
            mysql_manager.execute_update(
                "UPDATE files SET status = 'completed', processing_progress = 100 WHERE file_id = %s",
                (file_id,)
            )
            
            logger.info(f"文件 {file_id} 处理完成")
            
        except Exception as e:
            logger.error(f"❌ 处理文件 {file_id} 失败: {e}", exc_info=True)
            logger.error(f"❌ 异常类型: {type(e).__name__}")
            logger.error(f"❌ 异常消息: {str(e)}")
            
            # 更新处理状态
            try:
                self.processing_status[file_id] = {
                    "status": "failed",
                    "progress": 0,
                    "message": f"处理失败: {str(e)}"
                }
                logger.info(f"✅ 内存中处理状态已更新为失败")
            except Exception as status_error:
                logger.error(f"❌ 更新内存处理状态失败: {status_error}")
            
            # 更新数据库状态
            try:
                mysql_manager.execute_update(
                    "UPDATE files SET status = 'failed' WHERE file_id = %s",
                    (file_id,)
                )
                logger.info(f"✅ 文件 {file_id} 数据库状态已更新为failed")
            except Exception as db_error:
                logger.error(f"❌ 更新数据库文件状态失败: {db_error}")
        
        finally:
            logger.info(f"🏁 文件处理线程结束 - 文件ID: {file_id}")
    
    def _extract_text_from_page(self, page) -> str:
        """从页面提取文本"""
        return page.get_text()
    
    def _extract_images_from_page(self, page, page_num: int) -> List[Dict]:
        """从页面提取图像"""
        images = []
        image_list = page.get_images()
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            pix = fitz.Pixmap(page.parent, xref)
            
            if pix.n - pix.alpha < 4:  # 确保不是CMYK
                img_data = pix.tobytes("png")
                images.append({
                    "page": page_num,
                    "index": img_index,
                    "data": img_data,
                    "width": pix.width,
                    "height": pix.height
                })
            
            pix = None
        
        return images
    
    def _extract_tables_from_page(self, page, page_num: int) -> List[Dict]:
        """从页面提取表格"""
        tables = []
        
        try:
            # 方法1: 尝试使用PyMuPDF的表格检测
            tabs = page.find_tables()
            
            if tabs:
                for i, tab in enumerate(tabs):
                    try:
                        # 提取表格数据
                        table_data = tab.extract()
                        if table_data and len(table_data) > 1:  # 至少有标题行和一行数据
                            tables.append({
                                "page": page_num,
                                "table_index": i,
                                "data": table_data,
                                "bbox": tab.bbox,  # 表格边界框
                                "method": "pymupdf"
                            })
                    except Exception as e:
                        logger.warning(f"PyMuPDF表格提取失败: {e}")
            
            # 方法2: 基于文本位置的表格检测（备用方法）
            if not tables:
                text_tables = self._detect_tables_by_text_position(page, page_num)
                tables.extend(text_tables)
            
            logger.info(f"页面 {page_num + 1} 检测到 {len(tables)} 个表格")
            return tables
            
        except Exception as e:
            logger.error(f"表格提取失败: {e}")
            return []
    
    def _detect_tables_by_text_position(self, page, page_num: int) -> List[Dict]:
        """基于文本位置检测表格"""
        tables = []
        
        try:
            # 获取详细的文本信息，包括位置
            text_dict = page.get_text("dict")
            
            # 分析文本块，寻找表格模式
            potential_table_blocks = []
            
            for block in text_dict["blocks"]:
                if "lines" in block:
                    lines = block["lines"]
                    
                    # 检查是否有多列对齐的文本（表格特征）
                    line_positions = []
                    for line in lines:
                        if "spans" in line:
                            x_positions = []
                            for span in line["spans"]:
                                x_positions.append(span["bbox"][0])  # x坐标
                            
                            if len(x_positions) > 1:  # 多列
                                line_positions.append(x_positions)
                    
                    # 如果有多行都有相似的列位置，可能是表格
                    if len(line_positions) >= 3:  # 至少3行
                        is_table = self._is_aligned_table(line_positions)
                        if is_table:
                            table_data = self._extract_table_from_block(block)
                            if table_data:
                                potential_table_blocks.append({
                                    "page": page_num,
                                    "table_index": len(tables),
                                    "data": table_data,
                                    "bbox": block["bbox"],
                                    "method": "text_position"
                                })
            
            tables.extend(potential_table_blocks)
            return tables
            
        except Exception as e:
            logger.error(f"基于位置的表格检测失败: {e}")
            return []
    
    def _is_aligned_table(self, line_positions: List[List[float]], tolerance: float = 10.0) -> bool:
        """检查文本行是否呈表格对齐"""
        if len(line_positions) < 3:
            return False
        
        # 检查列位置的一致性
        first_line_cols = len(line_positions[0])
        
        # 检查每行的列数是否相似
        consistent_cols = 0
        for positions in line_positions:
            if abs(len(positions) - first_line_cols) <= 1:  # 允许1列的差异
                consistent_cols += 1
        
        # 如果大部分行的列数一致，认为是表格
        return consistent_cols / len(line_positions) >= 0.7
    
    def _extract_table_from_block(self, block: Dict) -> List[List[str]]:
        """从文本块中提取表格数据"""
        table_data = []
        
        try:
            lines = block.get("lines", [])
            
            for line in lines:
                row_data = []
                spans = line.get("spans", [])
                
                # 按x坐标排序span
                spans_sorted = sorted(spans, key=lambda s: s["bbox"][0])
                
                for span in spans_sorted:
                    text = span.get("text", "").strip()
                    if text:
                        row_data.append(text)
                
                if row_data:
                    table_data.append(row_data)
            
            return table_data if len(table_data) >= 2 else []
            
        except Exception as e:
            logger.error(f"表格数据提取失败: {e}")
            return []
    
    def _create_text_chunks(self, text: str, file_id: str, page_num: int) -> List[Dict]:
        """创建文本块"""
        chunk_size = config_loader.get_app_config()["graph_rag"]["chunk_size"]
        chunk_overlap = config_loader.get_app_config()["graph_rag"]["chunk_overlap"]
        
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            
            if chunk_text.strip():
                chunk_id = f"{file_id}_page_{page_num}_chunk_{chunk_index}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "file_id": file_id,
                    "content": chunk_text.strip(),
                    "content_type": "text",
                    "page": page_num,
                    "metadata": {
                        "page": page_num,
                        "chunk_index": chunk_index,
                        "start_pos": start,
                        "end_pos": end
                    }
                })
                chunk_index += 1
            
            start = end - chunk_overlap
        
        return chunks
    
    def _process_images(self, images: List[Dict], file_id: str, page_num: int) -> List[Dict]:
        """处理图像，提取描述信息"""
        chunks = []
        
        for i, image in enumerate(images):
            try:
                # 保存临时图像文件
                temp_image_path = f"temp_image_{file_id}_{page_num}_{i}.png"
                with open(temp_image_path, "wb") as f:
                    f.write(image["data"])
                
                # 使用OCR提取文本
                ocr_results = model_manager.extract_text_from_image(temp_image_path)
                
                # 生成图像描述（这里需要使用图像分析模型）
                image_description = self._generate_image_description(temp_image_path)
                
                # 创建图像块
                chunk_id = f"{file_id}_page_{page_num}_image_{i}"
                content = f"图像描述: {image_description}\n"
                
                if ocr_results:
                    ocr_text = " ".join([result["text"] for result in ocr_results])
                    content += f"图像中的文字: {ocr_text}"
                
                chunks.append({
                    "chunk_id": chunk_id,
                    "file_id": file_id,
                    "content": content,
                    "content_type": "image",
                    "page": page_num,
                    "metadata": {
                        "page": page_num,
                        "image_index": i,
                        "width": image["width"],
                        "height": image["height"],
                        "ocr_results": ocr_results
                    }
                })
                
                # 删除临时文件
                os.remove(temp_image_path)
                
            except Exception as e:
                logger.error(f"处理图像失败: {e}")
        
        return chunks
    
    def _process_tables(self, tables: List[Dict], file_id: str, page_num: int) -> List[Dict]:
        """处理表格数据"""
        chunks = []
        
        for i, table in enumerate(tables):
            try:
                # 处理表格内容（这里需要根据具体的表格数据结构实现）
                table_content = self._format_table_content(table)
                
                chunk_id = f"{file_id}_page_{page_num}_table_{i}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "file_id": file_id,
                    "content": table_content,
                    "content_type": "table",
                    "page": page_num,
                    "metadata": {
                        "page": page_num,
                        "table_index": i,
                        "table_data": table
                    }
                })
                
            except Exception as e:
                logger.error(f"处理表格失败: {e}")
        
        return chunks
    
    def _generate_image_description(self, image_path: str) -> str:
        """生成图像描述"""
        try:
            # 使用DeepSeek多模态能力或OCR结果分析图像内容
            # 首先尝试获取图像的基本信息
            with Image.open(image_path) as img:
                width, height = img.size
                mode = img.mode
                format_name = img.format
            
            # 构建图像分析提示
            basic_info = f"图像尺寸: {width}x{height}, 颜色模式: {mode}, 格式: {format_name}"
            
            # 尝试使用OCR提取文本（如果图像包含文字）
            ocr_text = ""
            try:
                ocr_results = model_manager.extract_text_from_image(image_path)
                if ocr_results:
                    ocr_texts = [result.get("text", "") for result in ocr_results]
                    ocr_text = " ".join(ocr_texts).strip()
            except Exception as e:
                logger.warning(f"OCR处理失败: {e}")
            
            # 基于OCR结果和图像信息生成描述
            description_parts = []
            description_parts.append(basic_info)
            
            if ocr_text:
                description_parts.append(f"图像中包含文字内容: {ocr_text[:200]}")  # 限制长度
                
                # 基于文字内容判断图像类型
                if any(keyword in ocr_text.lower() for keyword in ['chart', '图表', '数据', '百分比', '%']):
                    description_parts.append("图像类型: 可能是数据图表或统计图")
                elif any(keyword in ocr_text.lower() for keyword in ['title', '标题', '章节']):
                    description_parts.append("图像类型: 可能是文档标题或章节页面")
                elif len(ocr_text.split()) > 20:
                    description_parts.append("图像类型: 包含大量文字的文档图像")
                else:
                    description_parts.append("图像类型: 包含少量文字的图像")
            else:
                # 基于图像尺寸和比例进行简单判断
                aspect_ratio = width / height if height > 0 else 1
                if 0.8 <= aspect_ratio <= 1.2:
                    description_parts.append("图像类型: 接近正方形，可能是图标、logo或示意图")
                elif aspect_ratio > 2:
                    description_parts.append("图像类型: 宽幅图像，可能是横向图表、时间线或流程图")
                elif aspect_ratio < 0.5:
                    description_parts.append("图像类型: 竖幅图像，可能是竖向列表或纵向图表")
                else:
                    description_parts.append("图像类型: 常规比例图像，可能是照片、插图或混合内容")
            
            # 尝试使用LLM进行更详细的分析（如果配置了相应提示词）
            try:
                enhanced_description = self._analyze_image_with_llm(description_parts, ocr_text)
                if enhanced_description:
                    description_parts.append(f"智能分析: {enhanced_description}")
            except Exception as e:
                logger.warning(f"LLM图像分析失败: {e}")
            
            return "\n".join(description_parts)
            
        except Exception as e:
            logger.error(f"图像描述生成失败: {e}")
            return f"图像描述生成失败: 无法分析图像 {image_path}"
    
    def _analyze_image_with_llm(self, image_info: List[str], ocr_text: str) -> str:
        """使用LLM分析图像内容"""
        try:
            # 构建分析提示
            image_context = "\n".join(image_info)
            
            if "image_analysis" in self.prompt_config and "image_description" in self.prompt_config["image_analysis"]:
                prompt_template = self.prompt_config["image_analysis"]["image_description"]
                
                # 自定义提示内容
                analysis_prompt = f"""
基于以下图像信息，请提供一个详细的图像描述和分析：

图像基本信息：
{image_context}

OCR提取的文字内容：
{ocr_text if ocr_text else "无文字内容"}

请分析：
1. 图像的主要内容和用途
2. 如果是图表，描述数据类型和趋势
3. 如果是文档，描述布局和结构
4. 图像在文档中可能的作用和意义

请用中文回答，保持简洁但包含关键信息。
"""
                
                response = self._call_llm(analysis_prompt)
                return response.strip() if response else ""
            
        except Exception as e:
            logger.error(f"LLM图像分析失败: {e}")
            
        return ""
    
    def _format_table_content(self, table: Dict) -> str:
        """格式化表格内容"""
        try:
            table_data = table.get("data", [])
            if not table_data:
                return "空表格"
            
            # 构建表格文本表示
            formatted_content = []
            
            # 添加表格元信息
            formatted_content.append(f"表格位置: 第{table.get('page', 0) + 1}页")
            formatted_content.append(f"检测方法: {table.get('method', 'unknown')}")
            formatted_content.append(f"表格大小: {len(table_data)}行 x {len(table_data[0]) if table_data else 0}列")
            formatted_content.append("")
            
            # 格式化表格数据
            if len(table_data) > 0:
                # 表头
                headers = table_data[0]
                formatted_content.append("表头: " + " | ".join(str(cell) for cell in headers))
                formatted_content.append("-" * 50)
                
                # 数据行
                for i, row in enumerate(table_data[1:], 1):
                    if i <= 10:  # 只显示前10行数据，避免内容过长
                        row_text = " | ".join(str(cell) for cell in row)
                        formatted_content.append(f"第{i}行: {row_text}")
                    elif i == 11:
                        formatted_content.append(f"... (还有{len(table_data) - 11}行数据)")
                        break
            
            # 使用LLM生成表格摘要
            table_text = "\n".join(formatted_content)
            summary = self._generate_table_summary(table_text)
            
            final_content = []
            final_content.append("=== 表格摘要 ===")
            final_content.append(summary)
            final_content.append("")
            final_content.append("=== 表格详细内容 ===")
            final_content.extend(formatted_content)
            
            return "\n".join(final_content)
            
        except Exception as e:
            logger.error(f"表格内容格式化失败: {e}")
            return f"表格格式化失败: {str(e)}"
    
    def _generate_table_summary(self, table_content: str) -> str:
        """使用LLM生成表格摘要"""
        try:
            prompt_template = self.prompt_config["table_analysis"]["table_summary"]
            prompt = prompt_template.format(table_content=table_content)
            
            response = self._call_llm(prompt)
            return response.strip() if response else "无法生成表格摘要"
            
        except Exception as e:
            logger.error(f"表格摘要生成失败: {e}")
            return "表格摘要生成失败"
    
    def _generate_embeddings(self, chunks: List[Dict]) -> None:
        """为文本块生成嵌入向量"""
        texts = [chunk["content"] for chunk in chunks]
        embeddings = model_manager.get_embedding(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
    
    def _extract_entities_and_relations(self, chunks: List[Dict]) -> tuple:
        """提取实体和关系"""
        entities = []
        relations = []
        
        try:
            # 合并文本内容进行批量处理
            text_chunks = [chunk for chunk in chunks if chunk["content_type"] == "text"]
            
            # 批量处理文本块以提高效率
            batch_size = 5
            for i in range(0, len(text_chunks), batch_size):
                batch = text_chunks[i:i+batch_size]
                combined_text = "\n\n".join([chunk["content"] for chunk in batch])
                
                # 提取实体
                batch_entities = self._extract_entities(combined_text)
                
                # 提取关系
                if batch_entities:
                    batch_relations = self._extract_relations(combined_text, batch_entities)
                    relations.extend(batch_relations)
                
                # 为实体添加chunk信息
                for entity in batch_entities:
                    entity["chunks"] = [chunk["chunk_id"] for chunk in batch]
                    entity["file_id"] = batch[0]["file_id"] if batch else None
                
                entities.extend(batch_entities)
                
            logger.info(f"提取到 {len(entities)} 个实体，{len(relations)} 个关系")
            return entities, relations
            
        except Exception as e:
            logger.error(f"实体关系提取失败: {e}")
            return [], []
    
    def _save_to_vector_db(self, chunks: List[Dict]) -> None:
        """保存到向量数据库"""
        try:
            # 确保Milvus连接和集合初始化
            if not milvus_manager.collection:
                logger.info("Milvus集合未初始化，重新连接...")
                milvus_manager.connect()
            
            vector_data = []
            
            for chunk in chunks:
                vector_data.append({
                    "file_id": chunk["file_id"],
                    "chunk_id": chunk["chunk_id"],
                    "content": chunk["content"],
                    "embedding": chunk["embedding"],
                    "metadata": json.dumps(chunk["metadata"])
                })
            
            if vector_data:
                milvus_manager.insert_vectors(vector_data)
                logger.info(f"成功保存 {len(vector_data)} 个向量到Milvus")
                
        except Exception as e:
            logger.error(f"保存到向量数据库失败: {e}")
            raise
    
    def _save_to_graph_db(self, entities: List[Dict], relations: List[Dict], file_id: str) -> None:
        """保存到图数据库"""
        # 创建实体节点
        for entity in entities:
            entity["file_id"] = file_id
            neo4j_manager.create_entity(entity["type"], entity)
        
        # 创建关系
        for relation in relations:
            neo4j_manager.create_relationship(
                relation["subject"],
                relation["object"],
                relation["predicate"],
                {"confidence": relation.get("confidence", 1.0), "file_id": file_id}
            )
    
    def _extract_entities(self, text: str) -> List[Dict]:
        """使用LLM提取实体"""
        try:
            prompt_template = self.prompt_config["document_parsing"]["entity_extraction"]
            prompt = prompt_template.format(text=text)
            
            response = self._call_llm(prompt)
            
            # 解析JSON响应
            try:
                # 清理响应字符串，移除可能的前缀和后缀
                cleaned_response = response.strip()
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()
                
                result = json.loads(cleaned_response)
                entities = result.get("entities", [])
                
                # 标准化实体格式
                standardized_entities = []
                for entity in entities:
                    standardized_entities.append({
                        "name": entity.get("name", ""),
                        "type": entity.get("type", "UNKNOWN"),
                        "position": entity.get("position", ""),
                        "confidence": 0.8  # 默认置信度
                    })
                
                return standardized_entities
                
            except json.JSONDecodeError as e:
                logger.warning(f"LLM返回的不是有效JSON格式: {str(e)[:100]}，尝试解析文本")
                logger.debug(f"原始响应: {response[:200]}...")
                return self._parse_entities_from_text(response)
                
        except Exception as e:
            logger.error(f"实体提取失败: {e}")
            return []
    
    def _extract_relations(self, text: str, entities: List[Dict]) -> List[Dict]:
        """使用LLM提取关系"""
        try:
            entities_str = "\n".join([f"- {entity['name']} ({entity['type']})" for entity in entities])
            prompt_template = self.prompt_config["document_parsing"]["relation_extraction"]
            prompt = prompt_template.format(text=text, entities=entities_str)
            
            response = self._call_llm(prompt)
            
            # 解析JSON响应
            try:
                # 清理响应字符串
                cleaned_response = response.strip()
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()
                
                result = json.loads(cleaned_response)
                relations = result.get("relations", [])
                
                # 标准化关系格式
                standardized_relations = []
                for relation in relations:
                    standardized_relations.append({
                        "subject": relation.get("subject", ""),
                        "predicate": relation.get("predicate", "RELATED_TO"),
                        "object": relation.get("object", ""),
                        "confidence": relation.get("confidence", 0.8)
                    })
                
                return standardized_relations
                
            except json.JSONDecodeError as e:
                logger.warning(f"LLM返回的不是有效JSON格式: {str(e)[:100]}，尝试解析文本")
                logger.debug(f"原始响应: {response[:200]}...")
                return self._parse_relations_from_text(response)
                
        except Exception as e:
            logger.error(f"关系提取失败: {e}")
            return []
    
    def _parse_entities_from_text(self, text: str) -> List[Dict]:
        """从文本中解析实体（备用方法）"""
        entities = []
        lines = text.strip().split('\n')
        
        for line in lines:
            if '(' in line and ')' in line:
                match = re.match(r'.*?([^(]+)\s*\(([^)]+)\)', line)
                if match:
                    name = match.group(1).strip()
                    entity_type = match.group(2).strip()
                    if name and entity_type:
                        entities.append({
                            "name": name,
                            "type": entity_type,
                            "position": "",
                            "confidence": 0.7
                        })
        
        return entities
    
    def _parse_relations_from_text(self, text: str) -> List[Dict]:
        """从文本中解析关系（备用方法）"""
        relations = []
        lines = text.strip().split('\n')
        
        for line in lines:
            # 查找形如 "A 关系 B" 的模式
            if '->' in line or '→' in line or ' 与 ' in line:
                parts = re.split(r'[-→]|与', line)
                if len(parts) >= 2:
                    subject = parts[0].strip()
                    obj = parts[-1].strip()
                    predicate = "RELATED_TO"
                    
                    if subject and obj:
                        relations.append({
                            "subject": subject,
                            "predicate": predicate,
                            "object": obj,
                            "confidence": 0.6
                        })
        
        return relations
    
    def _call_llm(self, prompt: str) -> str:
        """调用DeepSeek LLM"""
        try:
            llm_config = self.model_config["llm"]
            
            headers = {
                "Authorization": f"Bearer {llm_config['api_key']}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": llm_config["model_name"],
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": llm_config["max_tokens"],
                "temperature": llm_config["temperature"]
            }
            
            response = requests.post(
                f"{llm_config['api_url']}/chat/completions",
                headers=headers,
                json=data,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                logger.error(f"LLM API调用失败: {response.status_code} - {response.text}")
                return "{}"
                
        except Exception as e:
            logger.error(f"调用LLM失败: {e}")
            return "{}"

# 全局文件服务实例
file_service = FileService() 