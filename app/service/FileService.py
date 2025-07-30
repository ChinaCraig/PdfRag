"""
文件管理服务 - 重构版
负责PDF文件的上传、删除、重命名以及GraphRAG内容解析
简化处理流程，提高可靠性
"""
import os
import uuid
import logging
import json
import threading
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import fitz  # PyMuPDF
from PIL import Image
import io
import requests
import re

from utils.config_loader import config_loader
from utils.database import mysql_manager, milvus_manager, neo4j_manager
from utils.model_manager import model_manager

logger = logging.getLogger(__name__)

class FileService:
    """文件管理服务类 - 重构版"""
    
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
        
        logger.info("文件服务初始化完成 - GraphRAG重构版")
    
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
            
            # 异步开始GraphRAG处理
            logger.info(f"🚀 启动GraphRAG处理线程...")
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
                target=self._process_graphrag,
                args=(file_id, file_path),
                name=f"GraphRAG-{file_id[:8]}",
                daemon=True
            )
            thread.start()
            logger.info(f"✅ GraphRAG处理线程已启动: {file_id}")
        except Exception as e:
            logger.error(f"❌ 启动GraphRAG处理线程失败: {e}")
            self._update_file_status(file_id, "failed", 0, f"启动处理失败: {str(e)}")
    
    def _process_graphrag(self, file_id: str, file_path: str) -> None:
        """
        GraphRAG处理主流程
        
        流程：
        1. PDF解析和内容提取
        2. 生成嵌入向量
        3. 实体关系提取
        4. 保存到向量数据库和图数据库
        """
        try:
            logger.info(f"🚀 开始GraphRAG处理: {file_id}")
            
            # 更新状态
            self._update_file_status(file_id, "processing", 5, "开始处理...")
            
            # 第一步：PDF内容提取
            logger.info(f"📖 步骤1: PDF内容提取")
            chunks = self._extract_pdf_content(file_id, file_path)
            self._update_file_status(file_id, "processing", 40, f"内容提取完成，共{len(chunks)}个块")
            
            if not chunks:
                raise ValueError("PDF内容提取失败，没有找到有效内容")
            
            # 第二步：生成嵌入向量
            logger.info(f"🔤 步骤2: 生成嵌入向量")
            self._generate_embeddings_for_chunks(chunks)
            self._update_file_status(file_id, "processing", 60, "嵌入向量生成完成")
            
            # 第三步：保存到向量数据库
            logger.info(f"💾 步骤3: 保存到向量数据库")
            self._save_chunks_to_vector_db(chunks)
            self._update_file_status(file_id, "processing", 75, "向量数据保存完成")
            
            # 第四步：实体关系提取
            logger.info(f"🧠 步骤4: 实体关系提取")
            entities, relations = self._extract_knowledge_graph(chunks)
            self._update_file_status(file_id, "processing", 90, f"知识图谱提取完成：{len(entities)}个实体，{len(relations)}个关系")
            
            # 第五步：保存到图数据库
            logger.info(f"🕸️ 步骤5: 保存到图数据库")
            self._save_knowledge_graph(entities, relations, file_id)
            
            # 更新最终状态
            self._update_file_status(file_id, "completed", 100, "GraphRAG处理完成")
            logger.info(f"✅ GraphRAG处理完成: {file_id}")
            
        except Exception as e:
            logger.error(f"❌ GraphRAG处理失败: {file_id}, 错误: {e}", exc_info=True)
            self._update_file_status(file_id, "failed", 0, f"处理失败: {str(e)}")
    
    def _extract_pdf_content(self, file_id: str, file_path: str) -> List[Dict[str, Any]]:
        """
        提取PDF内容：文字、表格、图片、图表
        
        Returns:
            内容块列表
        """
        all_chunks = []
        
        try:
            # 打开PDF文档
            doc = fitz.open(file_path)
            total_pages = len(doc)
            logger.info(f"📄 PDF共{total_pages}页")
            
            # 逐页处理
            for page_num in range(total_pages):
                logger.info(f"📖 处理第{page_num + 1}/{total_pages}页")
                page = doc[page_num]
                
                # 提取文本
                text_chunks = self._extract_text_from_page(page, file_id, page_num)
                all_chunks.extend(text_chunks)
                
                # 提取图像
                image_chunks = self._extract_images_from_page(page, file_id, page_num)
                all_chunks.extend(image_chunks)
                
                # 提取表格
                table_chunks = self._extract_tables_from_page(page, file_id, page_num)
                all_chunks.extend(table_chunks)
                
                # 更新进度
                progress = 5 + int((page_num + 1) / total_pages * 35)
                self._update_file_status(file_id, "processing", progress, f"已处理{page_num + 1}/{total_pages}页")
            
            doc.close()
            logger.info(f"✅ PDF内容提取完成，共{len(all_chunks)}个内容块")
            return all_chunks
            
        except Exception as e:
            logger.error(f"❌ PDF内容提取失败: {e}")
            raise
    
    def _extract_text_from_page(self, page, file_id: str, page_num: int) -> List[Dict[str, Any]]:
        """从页面提取文本块"""
        chunks = []
        
        try:
            # 获取页面文本
            text = page.get_text()
            if not text.strip():
                return chunks
            
            # 分块设置
            chunk_size = self.config.get("graph_rag", {}).get("chunk_size", 1000)
            chunk_overlap = self.config.get("graph_rag", {}).get("chunk_overlap", 200)
            
            # 分割文本
            start = 0
            chunk_index = 0
            
            while start < len(text):
                end = start + chunk_size
                chunk_text = text[start:end].strip()
                
                if chunk_text:
                    chunk_id = f"{file_id}_page_{page_num}_text_{chunk_index}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "file_id": file_id,
                        "content": chunk_text,
                        "content_type": "text",
                        "page_number": page_num,
                        "chunk_index": chunk_index,
                        "start_position": start,
                        "end_position": min(end, len(text)),
                        "metadata": {
                            "page": page_num,
                            "type": "text",
                            "length": len(chunk_text)
                        }
                    })
                    chunk_index += 1
                
                start = end - chunk_overlap
                if start >= len(text):
                    break
            
            logger.debug(f"📝 第{page_num + 1}页提取{len(chunks)}个文本块")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ 文本提取失败: {e}")
            return []
    
    def _extract_images_from_page(self, page, file_id: str, page_num: int) -> List[Dict[str, Any]]:
        """从页面提取图像"""
        chunks = []
        
        try:
            image_list = page.get_images()
            logger.debug(f"📷 第{page_num + 1}页发现{len(image_list)}个图像")
            
            # 如果图像太多，限制处理数量以避免卡住
            max_images_per_page = 5
            if len(image_list) > max_images_per_page:
                logger.warning(f"⚠️ 第{page_num + 1}页图像过多({len(image_list)}个)，仅处理前{max_images_per_page}个")
                image_list = image_list[:max_images_per_page]
            
            for img_index, img in enumerate(image_list):
                try:
                    logger.debug(f"📷 处理第{page_num + 1}页第{img_index + 1}个图像")
                    
                    # 提取图像数据
                    xref = img[0]
                    pix = fitz.Pixmap(page.parent, xref)
                    
                    if pix.n - pix.alpha < 4:  # 确保不是CMYK
                        # 图像描述（使用OCR，带超时保护）
                        description = self._analyze_image_simple(pix, file_id, page_num, img_index)
                        
                        chunk_id = f"{file_id}_page_{page_num}_image_{img_index}"
                        chunks.append({
                            "chunk_id": chunk_id,
                            "file_id": file_id,
                            "content": description,
                            "content_type": "image",
                            "page_number": page_num,
                            "chunk_index": img_index,
                            "metadata": {
                                "page": page_num,
                                "type": "image",
                                "width": pix.width,
                                "height": pix.height,
                                "format": img[8] if len(img) > 8 else "unknown"
                            }
                        })
                        logger.debug(f"✅ 第{page_num + 1}页第{img_index + 1}个图像处理完成")
                    
                    pix = None  # 释放内存
                    
                except Exception as e:
                    logger.warning(f"⚠️ 第{page_num + 1}页第{img_index + 1}个图像处理失败: {e}")
                    continue
            
            logger.debug(f"📷 第{page_num + 1}页提取{len(chunks)}个图像块")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ 图像提取失败: {e}")
            return []
    
    def _extract_tables_from_page(self, page, file_id: str, page_num: int) -> List[Dict[str, Any]]:
        """从页面提取表格"""
        chunks = []
        
        try:
            # 使用PyMuPDF的表格检测
            table_finder = page.find_tables()
            
            # 将TableFinder转换为列表
            tables = list(table_finder)
            
            for table_index, table in enumerate(tables):
                try:
                    # 提取表格数据
                    table_data = table.extract()
                    if table_data and len(table_data) > 1:  # 至少有标题行和数据行
                        
                        # 格式化表格内容
                        table_content = self._format_table_simple(table_data, page_num, table_index)
                        
                        chunk_id = f"{file_id}_page_{page_num}_table_{table_index}"
                        chunks.append({
                            "chunk_id": chunk_id,
                            "file_id": file_id,
                            "content": table_content,
                            "content_type": "table",
                            "page_number": page_num,
                            "chunk_index": table_index,
                            "metadata": {
                                "page": page_num,
                                "type": "table",
                                "table_index": table_index,
                                "rows": len(table_data),
                                "columns": len(table_data[0]) if table_data else 0
                            }
                        })
                
                except Exception as e:
                    logger.warning(f"⚠️ 处理表格失败: {e}")
                    continue
            
            logger.debug(f"📊 第{page_num + 1}页提取{len(chunks)}个表格")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ 表格提取失败: {e}")
            return []
    
    def _analyze_image_simple(self, pix, file_id: str, page_num: int, img_index: int) -> str:
        """简单的图像分析（带超时保护）"""
        try:
            # 基本信息
            width, height = pix.width, pix.height
            
            # 跳过太小的图像
            if width < 50 or height < 50:
                return f"图像(第{page_num + 1}页)：尺寸{width}x{height}，图像过小跳过OCR"
            
            # 跳过太大的图像以避免OCR卡住 - 针对装修合同等文档优化
            dev_config = config_loader.get_app_config().get("development", {})
            max_image_size = dev_config.get("max_image_size", 2000000)
            if width * height > max_image_size:
                return f"图像(第{page_num + 1}页)：尺寸{width}x{height}，图像过大跳过OCR（限制：{max_image_size}像素）"
            
            # 构建基础描述
            description = f"图像(第{page_num + 1}页)：尺寸{width}x{height}"
            
            # 开发模式下暂时跳过OCR以避免卡住
            dev_config = config_loader.get_app_config().get("development", {})
            skip_ocr = dev_config.get("skip_image_ocr", False)
            
            if skip_ocr:
                logger.debug(f"🔧 开发模式：跳过图像OCR处理")
                return description + "，开发模式跳过OCR"
            
            # 保存临时图像进行OCR（带超时保护）
            temp_path = f"temp_img_{file_id}_{page_num}_{img_index}.png"
            
            try:
                logger.debug(f"💾 保存临时图像: {temp_path}")
                pix.save(temp_path)
                
                # 直接调用OCR，避免多线程问题
                ocr_text = ""
                try:
                    logger.debug(f"🔍 开始OCR处理: {temp_path}")
                    ocr_results = model_manager.extract_text_from_image(temp_path)
                    
                    if ocr_results:
                        ocr_text = " ".join([result.get("text", "") for result in ocr_results if result.get("text")])
                        logger.debug(f"✅ OCR完成，提取文字: {len(ocr_text)}字符")
                    
                except Exception as e:
                    logger.warning(f"⚠️ OCR处理失败: {e}")
                    ocr_text = ""
                
                # 删除临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    logger.debug(f"🗑️ 删除临时文件: {temp_path}")
                
                # 构建最终描述
                if ocr_text:
                    description += f"，包含文字：{ocr_text[:200]}"
                else:
                    description += "，无文字内容"
                
                return description
                
            except Exception as e:
                # 确保删除临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                logger.warning(f"⚠️ 图像处理失败: {e}")
                return description + "，处理失败"
            
        except Exception as e:
            logger.error(f"❌ 图像分析失败: {e}")
            return f"图像(第{page_num + 1}页)：分析失败"
    
    def _format_table_simple(self, table_data: List[List[str]], page_num: int, table_index: int) -> str:
        """简单的表格格式化"""
        try:
            content_lines = [f"表格(第{page_num + 1}页，表{table_index + 1})："]
            
            # 添加表头
            if table_data:
                headers = table_data[0]
                content_lines.append("表头：" + " | ".join(str(cell) for cell in headers))
                
                # 添加数据行（最多10行）
                data_rows = table_data[1:min(11, len(table_data))]
                for i, row in enumerate(data_rows, 1):
                    row_text = " | ".join(str(cell) for cell in row)
                    content_lines.append(f"第{i}行：{row_text}")
                
                if len(table_data) > 11:
                    content_lines.append(f"... (共{len(table_data) - 1}行数据)")
            
            return "\n".join(content_lines)
            
        except Exception as e:
            logger.error(f"表格格式化失败: {e}")
            return f"表格(第{page_num + 1}页)：格式化失败"
    
    def _generate_embeddings_for_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """为内容块生成嵌入向量"""
        try:
            # 提取文本内容
            texts = [chunk["content"] for chunk in chunks]
            logger.info(f"🔤 开始生成{len(texts)}个内容块的嵌入向量...")
            
            # 批量生成嵌入向量
            embeddings = model_manager.get_embedding(texts)
            
            # 分配给各个块
            for chunk, embedding in zip(chunks, embeddings):
                chunk["embedding"] = embedding
            
            logger.info(f"✅ 嵌入向量生成完成，共{len(embeddings)}个768维向量")
            
        except Exception as e:
            logger.error(f"❌ 嵌入向量生成失败: {e}")
            raise
    
    def _save_chunks_to_vector_db(self, chunks: List[Dict[str, Any]]) -> None:
        """保存内容块到向量数据库"""
        try:
            # 确保Milvus连接
            if not milvus_manager.collection:
                logger.info("初始化Milvus连接...")
                milvus_manager.connect()
            
            # 准备向量数据
            vector_data = []
            for chunk in chunks:
                vector_data.append({
                    "file_id": chunk["file_id"],
                    "chunk_id": chunk["chunk_id"],
                    "content": chunk["content"],
                    "embedding": chunk["embedding"],
                    "metadata": json.dumps(chunk["metadata"])
                })
            
            # 插入数据
            milvus_manager.insert_vectors(vector_data)
            logger.info(f"✅ 成功保存{len(vector_data)}个向量到Milvus")
            
        except Exception as e:
            logger.error(f"❌ 保存向量数据失败: {e}")
            raise
    
    def _extract_knowledge_graph(self, chunks: List[Dict[str, Any]]) -> tuple:
        """提取知识图谱：实体和关系"""
        entities = []
        relations = []
        
        try:
            # 只处理文本块
            text_chunks = [chunk for chunk in chunks if chunk["content_type"] == "text"]
            
            # 合并文本内容进行批量处理
            batch_size = 3  # 每次处理3个文本块
            
            for i in range(0, len(text_chunks), batch_size):
                batch = text_chunks[i:i + batch_size]
                combined_text = "\n\n".join([chunk["content"] for chunk in batch])
                
                # 提取实体
                batch_entities = self._extract_entities_simple(combined_text)
                
                # 提取关系
                batch_relations = self._extract_relations_simple(combined_text, batch_entities)
                
                # 为实体添加来源信息
                for entity in batch_entities:
                    entity["source_chunks"] = [chunk["chunk_id"] for chunk in batch]
                    entity["file_id"] = batch[0]["file_id"] if batch else None
                
                # 为关系添加来源信息
                for relation in batch_relations:
                    relation["source_chunks"] = [chunk["chunk_id"] for chunk in batch]
                    relation["file_id"] = batch[0]["file_id"] if batch else None
                
                entities.extend(batch_entities)
                relations.extend(batch_relations)
            
            logger.info(f"✅ 知识图谱提取完成：{len(entities)}个实体，{len(relations)}个关系")
            return entities, relations
            
        except Exception as e:
            logger.error(f"❌ 知识图谱提取失败: {e}")
            return [], []
    
    def _extract_entities_simple(self, text: str) -> List[Dict[str, Any]]:
        """简化的实体提取"""
        response = ""  # 初始化response变量避免UnboundLocalError
        
        try:
            if "entity_extraction" not in self.prompt_config.get("document_parsing", {}):
                logger.warning("实体提取提示词未配置，跳过实体提取")
                return []
            
            prompt_template = self.prompt_config["document_parsing"]["entity_extraction"]
            prompt = prompt_template.format(text=text[:2000])  # 限制文本长度
            
            logger.debug(f"📝 实体提取提示词: {prompt[:200]}...")
            response = self._call_llm_simple(prompt)
            logger.debug(f"🤖 LLM原始响应: {repr(response[:300])}")
            
            # 解析JSON响应（增强容错性）
            try:
                # 清理响应文本 - 更强的清理逻辑
                cleaned_response = response.strip()
                
                # 移除markdown代码块标记
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]
                elif cleaned_response.startswith('```'):
                    cleaned_response = cleaned_response[3:]
                    
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]
                
                # 移除额外的换行符和空格，但保持JSON结构
                cleaned_response = cleaned_response.strip()
                
                # 尝试找到JSON对象的开始和结束
                start_idx = cleaned_response.find('{')
                end_idx = cleaned_response.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    json_str = cleaned_response[start_idx:end_idx+1]
                    logger.debug(f"🔍 提取的JSON: {json_str[:100]}...")
                    result = json.loads(json_str)
                else:
                    # 如果找不到完整的JSON对象，尝试直接解析
                    logger.warning(f"未找到完整JSON对象，尝试直接解析: {cleaned_response[:200]}")
                    result = json.loads(cleaned_response)
                
                # 确保result是字典类型
                if not isinstance(result, dict):
                    logger.warning(f"LLM返回的不是字典格式，而是: {type(result).__name__}")
                    return []
                
                # 增强的键名检测和清理
                entities = []
                for key in result.keys():
                    # 清理键名中的换行符和空格
                    clean_key = key.strip().replace('\n', '').replace('\r', '')
                    if clean_key == "entities" or "entities" in clean_key:
                        entities = result[key]
                        break
                
                if not entities:
                    logger.warning(f"未找到entities字段，可用字段: {list(result.keys())}")
                    return []
                
                # 标准化实体格式
                standardized_entities = []
                for entity in entities:
                    if isinstance(entity, dict) and entity.get("name"):
                        standardized_entities.append({
                            "entity_id": str(uuid.uuid4()),
                            "name": entity.get("name", "").strip(),
                            "type": entity.get("type", "UNKNOWN").strip(),
                            "confidence": 0.8
                        })
                
                logger.info(f"✅ 实体提取成功: {len(standardized_entities)}个实体")
                return standardized_entities
                
            except json.JSONDecodeError as e:
                logger.warning(f"LLM返回的JSON解析失败: {e}")
                logger.debug(f"原始响应: {repr(response[:500])}")
                logger.info("尝试使用文本解析作为备用方案")
                return self._parse_entities_from_text(response)
                
        except Exception as e:
            logger.error(f"实体提取失败: {e}")
            logger.debug(f"实体提取异常详情: {type(e).__name__}: {str(e)}")
            logger.debug(f"原始LLM响应: {repr(response[:500])}")
            return []
    
    def _extract_relations_simple(self, text: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """简化的关系提取"""
        response = ""  # 初始化response变量避免UnboundLocalError
        
        try:
            if not entities or "relation_extraction" not in self.prompt_config.get("document_parsing", {}):
                logger.info("跳过关系提取：没有实体或提示词未配置")
                return []
            
            entities_str = "\n".join([f"- {entity['name']} ({entity['type']})" for entity in entities[:10]])  # 限制实体数量
            prompt_template = self.prompt_config["document_parsing"]["relation_extraction"]
            prompt = prompt_template.format(text=text[:2000], entities=entities_str)
            
            logger.debug(f"📝 关系提取提示词: {prompt[:200]}...")
            response = self._call_llm_simple(prompt)
            logger.debug(f"🤖 关系提取LLM原始响应: {repr(response[:300])}")
            
            # 解析JSON响应（增强容错性）
            try:
                # 清理响应文本
                cleaned_response = response.strip()
                
                # 移除markdown代码块标记
                if cleaned_response.startswith('```json'):
                    cleaned_response = cleaned_response[7:]
                elif cleaned_response.startswith('```'):
                    cleaned_response = cleaned_response[3:]
                    
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]
                
                # 移除额外的换行符和空格，但保持JSON结构
                cleaned_response = cleaned_response.strip()
                
                # 尝试找到JSON对象的开始和结束
                start_idx = cleaned_response.find('{')
                end_idx = cleaned_response.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                    json_str = cleaned_response[start_idx:end_idx+1]
                    logger.debug(f"🔍 关系提取JSON: {json_str[:100]}...")
                    result = json.loads(json_str)
                else:
                    # 如果找不到完整的JSON对象，尝试直接解析
                    logger.warning(f"关系提取未找到完整JSON对象，尝试直接解析: {cleaned_response[:200]}")
                    result = json.loads(cleaned_response)
                
                # 确保result是字典类型
                if not isinstance(result, dict):
                    logger.warning(f"关系提取LLM返回的不是字典格式，而是: {type(result).__name__}")
                    return []
                
                # 增强的键名检测和清理
                relations = []
                for key in result.keys():
                    # 清理键名中的换行符和空格
                    clean_key = key.strip().replace('\n', '').replace('\r', '')
                    if clean_key == "relations" or "relations" in clean_key:
                        relations = result[key]
                        break
                
                if not relations:
                    logger.warning(f"未找到relations字段，可用字段: {list(result.keys())}")
                    return []
                
                # 标准化关系格式
                standardized_relations = []
                for relation in relations:
                    if isinstance(relation, dict) and relation.get("subject") and relation.get("object"):
                        standardized_relations.append({
                            "relationship_id": str(uuid.uuid4()),
                            "subject": relation.get("subject", "").strip(),
                            "predicate": relation.get("predicate", "RELATED_TO").strip(),
                            "object": relation.get("object", "").strip(),
                            "confidence": relation.get("confidence", 0.8)
                        })
                
                logger.info(f"✅ 关系提取成功: {len(standardized_relations)}个关系")
                return standardized_relations
                
            except json.JSONDecodeError as e:
                logger.warning(f"关系提取JSON解析失败: {e}")
                logger.debug(f"原始响应: {repr(response[:500])}")
                return []
                
        except Exception as e:
            logger.error(f"关系提取失败: {e}")
            logger.debug(f"关系提取异常详情: {type(e).__name__}: {str(e)}")
            logger.debug(f"原始LLM响应: {repr(response[:500])}")
            return []
    
    def _save_knowledge_graph(self, entities: List[Dict[str, Any]], relations: List[Dict[str, Any]], file_id: str) -> None:
        """保存知识图谱到Neo4j"""
        try:
            # 创建实体节点
            for entity in entities:
                entity_data = {
                    "entity_id": entity["entity_id"],
                    "name": entity["name"],
                    "type": entity["type"],
                    "file_id": file_id,
                    "confidence": entity["confidence"]
                }
                neo4j_manager.create_entity(entity["type"], entity_data)
            
            # 创建关系
            for relation in relations:
                # 简化的关系创建，直接根据名称匹配
                subject_entity = {"name": relation["subject"]}
                object_entity = {"name": relation["object"]}
                relation_props = {
                    "confidence": relation["confidence"],
                    "file_id": file_id
                }
                
                neo4j_manager.create_relationship(
                    subject_entity,
                    object_entity,
                    relation["predicate"],
                    relation_props
                )
            
            logger.info(f"✅ 知识图谱保存完成：{len(entities)}个实体，{len(relations)}个关系")
            
        except Exception as e:
            logger.error(f"❌ 知识图谱保存失败: {e}")
            # 不抛出异常，允许其他处理继续
    
    def _call_llm_simple(self, prompt: str) -> str:
        """简化的LLM调用"""
        try:
            if not hasattr(self, 'model_config') or not self.model_config:
                logger.error("模型配置未加载")
                return '{"entities": [], "relations": []}'
            
            llm_config = self.model_config.get("llm", {})
            if not llm_config:
                logger.error("LLM配置未找到")
                return '{"entities": [], "relations": []}'
            
            # 检查必要的配置项
            required_keys = ["api_key", "api_url", "model_name"]
            for key in required_keys:
                if not llm_config.get(key):
                    logger.error(f"LLM配置缺少必要项: {key}")
                    return '{"entities": [], "relations": []}'
            
            headers = {
                "Authorization": f"Bearer {llm_config['api_key']}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": llm_config["model_name"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(llm_config.get("max_tokens", 2048), 2048),
                "temperature": llm_config.get("temperature", 0.7)
            }
            
            logger.debug(f"🌐 调用LLM API: {llm_config['api_url']}")
            response = requests.post(
                f"{llm_config['api_url']}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    logger.warning("LLM返回空内容")
                    return '{"entities": [], "relations": []}'
                return content
            else:
                logger.error(f"LLM API调用失败: HTTP {response.status_code}, 响应: {response.text[:200]}")
                return '{"entities": [], "relations": []}'
                
        except requests.exceptions.Timeout:
            logger.error("LLM API调用超时")
            return '{"entities": [], "relations": []}'
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API请求异常: {e}")
            return '{"entities": [], "relations": []}'
        except Exception as e:
            logger.error(f"LLM调用异常: {e}")
            return '{"entities": [], "relations": []}'
    
    def _parse_entities_from_text(self, text: str) -> List[Dict[str, Any]]:
        """从文本中解析实体（备用方法）"""
        entities = []
        try:
            lines = text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 尝试多种解析模式
                patterns = [
                    r'.*?([^(]+)\s*\(([^)]+)\)',  # 实体名(类型)
                    r'.*?name["\'\s]*:["\'\s]*([^,"\'}]+).*?type["\'\s]*:["\'\s]*([^,"\'}]+)',  # JSON格式的name和type
                    r'.*?([A-Za-z\u4e00-\u9fff]+).*?([A-Z_]{2,})',  # 中英文实体名和大写类型
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        name = match.group(1).strip().strip('"\'')
                        entity_type = match.group(2).strip().strip('"\'')
                        
                        if name and entity_type and len(name) > 1:
                            entities.append({
                                "entity_id": str(uuid.uuid4()),
                                "name": name,
                                "type": entity_type,
                                "confidence": 0.6  # 文本解析的置信度较低
                            })
                            break
            
            # 去重
            seen_names = set()
            unique_entities = []
            for entity in entities:
                if entity["name"] not in seen_names:
                    seen_names.add(entity["name"])
                    unique_entities.append(entity)
            
            logger.info(f"📝 文本解析实体备用方案提取到 {len(unique_entities)} 个实体")
            return unique_entities[:20]  # 限制数量
            
        except Exception as e:
            logger.error(f"文本解析实体失败: {e}")
            return []
    
    def _update_file_status(self, file_id: str, status: str, progress: int, message: str) -> None:
        """更新文件处理状态"""
        try:
            # 更新内存状态
            self.processing_status[file_id] = {
                "status": status,
                "progress": progress,
                "message": message
            }
            
            # 更新数据库状态
            mysql_manager.execute_update(
                "UPDATE files SET status = %s, processing_progress = %s WHERE file_id = %s",
                (status, progress, file_id)
            )
            
            logger.info(f"📊 {file_id}: {status} - {progress}% - {message}")
            
        except Exception as e:
            logger.warning(f"更新文件状态失败: {e}")
    
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
    
    def _allowed_file(self, filename: str) -> bool:
        """检查文件类型是否允许"""
        return '.' in filename and \
               '.' + filename.rsplit('.', 1)[1].lower() in self.allowed_extensions
    
    def add_ocr_support(self) -> None:
        """为图像分析添加OCR支持"""
        # 这个方法将在后续版本中实现图像OCR功能
        pass

# 全局文件服务实例
file_service = FileService() 
