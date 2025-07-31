"""
GraphRAG服务 - 完全重构版
负责PDF文件的多模态内容识别和知识图谱构建
支持文字、表格、图片、图表的完整识别和理解
"""
import os
import uuid
import logging
import json
import threading
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from PIL import Image
import fitz  # PyMuPDF
import io
import tempfile
import requests
import cv2
import numpy as np

from utils.config_loader import config_loader
from utils.database import mysql_manager, milvus_manager, neo4j_manager
from utils.model_manager import model_manager

logger = logging.getLogger(__name__)

class GraphRAGService:
    """GraphRAG服务类 - 多模态内容识别和知识图谱构建"""
    
    def __init__(self):
        self.config = config_loader.get_app_config()
        self.model_config = config_loader.get_model_config()
        self.prompt_config = config_loader.get_prompt_config()
        self.graphrag_config = self.config.get("graph_rag", {})
        self.multimedia_config = self.config.get("multimedia", {})
        
        # 多模态配置
        self.multimodal_config = self.graphrag_config.get("multimodal", {})
        self.image_config = self.multimodal_config.get("image_processing", {})
        self.table_config = self.multimodal_config.get("table_processing", {})
        self.chart_config = self.multimodal_config.get("chart_processing", {})
        
        # 处理状态跟踪
        self.processing_status = {}
        
        # 确保多媒体目录存在
        self._ensure_multimedia_directories()
        
        logger.info("GraphRAG服务初始化完成 - 多模态版本")
    
    def _ensure_multimedia_directories(self):
        """确保多媒体目录存在"""
        directories = [
            self.multimedia_config.get("images", {}).get("save_dir", "uploads/images"),
            self.multimedia_config.get("tables", {}).get("export_dir", "uploads/tables"),
            self.multimedia_config.get("charts", {}).get("save_dir", "uploads/charts")
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def process_pdf_file(self, file_id: str, file_path: str) -> Dict[str, Any]:
        """
        处理PDF文件的完整流程
        
        Args:
            file_id: 文件ID
            file_path: 文件路径
            
        Returns:
            处理结果
        """
        try:
            logger.info(f"🚀 开始GraphRAG处理: {file_id}")
            
            # 初始化处理状态
            self._update_processing_status(file_id, "processing", 0, "开始处理...")
            
            # 第一步：PDF多模态内容提取
            logger.info(f"📖 步骤1: PDF多模态内容提取")
            extraction_result = self._extract_multimodal_content(file_id, file_path)
            self._update_processing_status(file_id, "processing", 30, f"内容提取完成")
            
            if not extraction_result["success"]:
                raise ValueError(f"PDF内容提取失败: {extraction_result['message']}")
            
            content_chunks = extraction_result["content_chunks"]
            
            # 第二步：生成嵌入向量
            logger.info(f"🔤 步骤2: 生成嵌入向量")
            self._generate_embeddings_for_chunks(content_chunks, file_id)
            self._update_processing_status(file_id, "processing", 50, "嵌入向量生成完成")
            
            # 第三步：保存到向量数据库
            logger.info(f"💾 步骤3: 保存到向量数据库")
            self._save_chunks_to_vector_db(content_chunks, file_id)
            self._update_processing_status(file_id, "processing", 65, "向量数据保存完成")
            
            # 第四步：知识图谱构建
            logger.info(f"🧠 步骤4: 知识图谱构建")
            self._update_processing_status(file_id, "processing", 67, "🧠 开始构建知识图谱...")
            kg_result = self._build_knowledge_graph(content_chunks, file_id)
            self._update_processing_status(file_id, "processing", 86, 
                                         f"🧠 知识图谱构建完成：整理出{kg_result['entities_count']}个实体，{kg_result['relations_count']}个关系")
            
            # 第五步：保存到图数据库
            logger.info(f"🕸️ 步骤5: 保存到图数据库")
            self._update_processing_status(file_id, "processing", 88, 
                                         f"🕸️ 开始保存{kg_result['entities_count']}个实体和{kg_result['relations_count']}个关系到Neo4j...")
            self._save_knowledge_graph_to_db(kg_result["entities"], kg_result["relations"], file_id)
            self._update_processing_status(file_id, "processing", 98, 
                                         f"🕸️ 知识图谱保存完成，共存储{kg_result['entities_count']}个实体和{kg_result['relations_count']}个关系")
            
            # 更新最终状态
            total_statistics = f"处理完成！共提取{len(content_chunks)}个内容块，生成{kg_result['entities_count']}个实体，{kg_result['relations_count']}个关系"
            self._update_processing_status(file_id, "completed", 100, f"🎉 GraphRAG {total_statistics}")
            
            result = {
                "success": True,
                "message": "GraphRAG处理完成",
                "statistics": {
                    "total_chunks": len(content_chunks),
                    "text_chunks": len([c for c in content_chunks if c["content_type"] == "text"]),
                    "image_chunks": len([c for c in content_chunks if c["content_type"] == "image"]),
                    "table_chunks": len([c for c in content_chunks if c["content_type"] == "table"]),
                    "chart_chunks": len([c for c in content_chunks if c["content_type"] == "chart"]),
                    "entities_count": kg_result["entities_count"],
                    "relations_count": kg_result["relations_count"]
                }
            }
            
            logger.info(f"✅ GraphRAG处理完成: {file_id}")
            return result
            
        except Exception as e:
            logger.error(f"❌ GraphRAG处理失败: {file_id}, 错误: {e}", exc_info=True)
            self._update_processing_status(file_id, "failed", 0, f"处理失败: {str(e)}")
            return {
                "success": False,
                "message": f"GraphRAG处理失败: {str(e)}"
            }
    
    def _extract_multimodal_content(self, file_id: str, file_path: str) -> Dict[str, Any]:
        """
        提取PDF的多模态内容
        
        Args:
            file_id: 文件ID
            file_path: PDF文件路径
            
        Returns:
            提取结果
        """
        try:
            content_chunks = []
            
            # 打开PDF文档
            doc = fitz.open(file_path)
            total_pages = len(doc)
            logger.info(f"📄 PDF共{total_pages}页")
            
            # 初始状态
            self._update_processing_status(file_id, "processing", 5, 
                                         f"📄 开始提取PDF内容，共{total_pages}页")
            
            for page_num in range(total_pages):
                logger.info(f"📖 处理第{page_num + 1}/{total_pages}页")
                page = doc[page_num]
                
                # 提取文本内容
                self._update_processing_status(file_id, "processing", 
                                             5 + int((page_num + 0.2) / total_pages * 25), 
                                             f"📖 正在提取第{page_num + 1}页文本内容...")
                text_chunks = self._extract_text_content(page, file_id, page_num)
                content_chunks.extend(text_chunks)
                
                # 提取图像内容
                self._update_processing_status(file_id, "processing", 
                                             5 + int((page_num + 0.4) / total_pages * 25), 
                                             f"🖼️ 正在提取第{page_num + 1}页图像内容...")
                image_chunks = self._extract_image_content(page, file_id, page_num)
                content_chunks.extend(image_chunks)
                
                # 提取表格内容
                self._update_processing_status(file_id, "processing", 
                                             5 + int((page_num + 0.6) / total_pages * 25), 
                                             f"📊 正在提取第{page_num + 1}页表格内容...")
                table_chunks = self._extract_table_content(page, file_id, page_num)
                content_chunks.extend(table_chunks)
                
                # 提取图表内容
                self._update_processing_status(file_id, "processing", 
                                             5 + int((page_num + 0.8) / total_pages * 25), 
                                             f"📈 正在提取第{page_num + 1}页图表内容...")
                chart_chunks = self._extract_chart_content(page, file_id, page_num)
                content_chunks.extend(chart_chunks)
                
                # 页面处理完成 - 显示当前页发现的内容统计
                page_text_count = len([c for c in text_chunks])
                page_image_count = len([c for c in image_chunks])
                page_table_count = len([c for c in table_chunks])
                page_chart_count = len([c for c in chart_chunks])
                
                page_summary = []
                if page_text_count > 0:
                    page_summary.append(f"{page_text_count}个文本块")
                if page_image_count > 0:
                    page_summary.append(f"{page_image_count}个图像")
                if page_table_count > 0:
                    page_summary.append(f"{page_table_count}个表格")
                if page_chart_count > 0:
                    page_summary.append(f"{page_chart_count}个图表")
                
                progress = 5 + int((page_num + 1) / total_pages * 25)
                if page_summary:
                    status_message = f"✅ 第{page_num + 1}/{total_pages}页完成，发现{', '.join(page_summary)}"
                else:
                    status_message = f"✅ 第{page_num + 1}/{total_pages}页完成"
                
                self._update_processing_status(file_id, "processing", progress, status_message)
            
            doc.close()
            
            logger.info(f"✅ PDF多模态内容提取完成，共{len(content_chunks)}个内容块")
            return {
                "success": True,
                "content_chunks": content_chunks,
                "statistics": {
                    "total_chunks": len(content_chunks),
                    "text_chunks": len([c for c in content_chunks if c["content_type"] == "text"]),
                    "image_chunks": len([c for c in content_chunks if c["content_type"] == "image"]),
                    "table_chunks": len([c for c in content_chunks if c["content_type"] == "table"]),
                    "chart_chunks": len([c for c in content_chunks if c["content_type"] == "chart"])
                }
            }
            
        except Exception as e:
            logger.error(f"❌ PDF多模态内容提取失败: {e}")
            return {
                "success": False,
                "message": f"PDF内容提取失败: {str(e)}",
                "content_chunks": []
            }
    
    def _extract_text_content(self, page, file_id: str, page_num: int) -> List[Dict[str, Any]]:
        """提取文本内容"""
        chunks = []
        
        try:
            # 获取页面文本
            text = page.get_text()
            if not text.strip():
                return chunks
            
            # 分块设置
            chunk_size = self.graphrag_config.get("chunk_size", 1000)
            chunk_overlap = self.graphrag_config.get("chunk_overlap", 200)
            
            # 智能分割文本（按段落和句子）
            text_chunks = self._smart_text_chunking(text, chunk_size, chunk_overlap)
            
            for chunk_index, chunk_text in enumerate(text_chunks):
                if chunk_text.strip():
                    chunk_id = f"{file_id}_page_{page_num}_text_{chunk_index}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "file_id": file_id,
                        "content": chunk_text.strip(),
                        "content_type": "text",
                        "page_number": page_num,
                        "chunk_index": chunk_index,
                        "metadata": {
                            "page": page_num,
                            "type": "text",
                            "length": len(chunk_text.strip()),
                            "language": self._detect_language(chunk_text.strip())
                        }
                    })
            
            logger.debug(f"📝 第{page_num + 1}页提取{len(chunks)}个文本块")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ 文本提取失败: {e}")
            return []
    
    def _extract_image_content(self, page, file_id: str, page_num: int) -> List[Dict[str, Any]]:
        """提取并分析图像内容"""
        chunks = []
        
        try:
            if not self.image_config.get("enabled", True):
                return chunks
                
            image_list = page.get_images()
            logger.debug(f"📷 第{page_num + 1}页发现{len(image_list)}个图像")
            
            for img_index, img in enumerate(image_list):
                try:
                    # 提取图像数据
                    xref = img[0]
                    pix = fitz.Pixmap(page.parent, xref)
                    
                    if pix.n - pix.alpha < 4:  # 确保不是CMYK
                        # 检查图像大小
                        if pix.width < 50 or pix.height < 50:
                            logger.debug(f"跳过过小的图像: {pix.width}x{pix.height}")
                            continue
                        
                        # 保存图像到文件系统
                        image_path = None
                        if self.image_config.get("save_to_filesystem", True):
                            image_path = self._save_image_to_filesystem(pix, file_id, page_num, img_index)
                        
                        # 进行图像理解分析
                        image_analysis = self._analyze_image_content(pix, file_id, page_num, img_index)
                        
                        chunk_id = f"{file_id}_page_{page_num}_image_{img_index}"
                        chunks.append({
                            "chunk_id": chunk_id,
                            "file_id": file_id,
                            "content": image_analysis["description"],
                            "content_type": "image",
                            "page_number": page_num,
                            "chunk_index": img_index,
                            "image_path": image_path,
                            "metadata": {
                                "page": page_num,
                                "type": "image",
                                "width": pix.width,
                                "height": pix.height,
                                "format": img[8] if len(img) > 8 else "unknown",
                                "objects_detected": image_analysis.get("objects", []),
                                "scene_description": image_analysis.get("scene", ""),
                                "text_content": image_analysis.get("text_content", ""),
                                "visual_elements": image_analysis.get("visual_elements", [])
                            }
                        })
                        
                        logger.debug(f"✅ 第{page_num + 1}页第{img_index + 1}个图像分析完成")
                    
                    pix = None  # 释放内存
                    
                except Exception as e:
                    logger.warning(f"⚠️ 第{page_num + 1}页第{img_index + 1}个图像处理失败: {e}")
                    continue
            
            logger.debug(f"📷 第{page_num + 1}页提取{len(chunks)}个图像块")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ 图像提取失败: {e}")
            return []
    
    def _extract_table_content(self, page, file_id: str, page_num: int) -> List[Dict[str, Any]]:
        """提取并分析表格内容"""
        chunks = []
        
        try:
            if not self.table_config.get("enabled", True):
                return chunks
                
            # 使用PyMuPDF的表格检测
            table_finder = page.find_tables()
            tables = list(table_finder)
            
            for table_index, table in enumerate(tables):
                try:
                    # 提取表格数据
                    table_data = table.extract()
                    if table_data and len(table_data) > 1:  # 至少有标题行和数据行
                        
                        # 格式化表格内容
                        table_analysis = self._analyze_table_content(table_data, page_num, table_index)
                        
                        # 保存表格到文件系统（如果配置了）
                        table_path = None
                        if self.table_config.get("keep_full_table", True):
                            table_path = self._save_table_to_filesystem(table_data, file_id, page_num, table_index)
                        
                        chunk_id = f"{file_id}_page_{page_num}_table_{table_index}"
                        chunks.append({
                            "chunk_id": chunk_id,
                            "file_id": file_id,
                            "content": table_analysis["formatted_content"],
                            "content_type": "table",
                            "page_number": page_num,
                            "chunk_index": table_index,
                            "table_path": table_path,
                            "table_data": table_data,  # 保留原始表格数据用于检索
                            "metadata": {
                                "page": page_num,
                                "type": "table",
                                "table_index": table_index,
                                "rows": len(table_data),
                                "columns": len(table_data[0]) if table_data else 0,
                                "summary": table_analysis.get("summary", ""),
                                "data_types": table_analysis.get("data_types", []),
                                "key_insights": table_analysis.get("key_insights", [])
                            }
                        })
                        
                        logger.debug(f"✅ 第{page_num + 1}页表格{table_index + 1}分析完成")
                
                except Exception as e:
                    logger.warning(f"⚠️ 处理表格失败: {e}")
                    continue
            
            logger.debug(f"📊 第{page_num + 1}页提取{len(chunks)}个表格")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ 表格提取失败: {e}")
            return []
    
    def _extract_chart_content(self, page, file_id: str, page_num: int) -> List[Dict[str, Any]]:
        """提取并分析图表内容"""
        chunks = []
        
        try:
            if not self.chart_config.get("enabled", True):
                return chunks
                
            # 获取页面图像用于图表检测
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            
            # 使用图表识别模型分析
            chart_analysis = self._analyze_chart_content(img_data, file_id, page_num)
            
            if chart_analysis and chart_analysis.get("charts_detected"):
                for chart_index, chart_info in enumerate(chart_analysis["charts_detected"]):
                    # 保存图表图像
                    chart_path = self._save_chart_to_filesystem(chart_info["image_data"], 
                                                              file_id, page_num, chart_index)
                    
                    chunk_id = f"{file_id}_page_{page_num}_chart_{chart_index}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "file_id": file_id,
                        "content": chart_info["description"],
                        "content_type": "chart",
                        "page_number": page_num,
                        "chunk_index": chart_index,
                        "chart_path": chart_path,
                        "metadata": {
                            "page": page_num,
                            "type": "chart",
                            "chart_type": chart_info.get("chart_type", "unknown"),
                            "data_points": chart_info.get("data_points", []),
                            "trend_analysis": chart_info.get("trend_analysis", ""),
                            "statistical_summary": chart_info.get("statistical_summary", {}),
                            "axis_labels": chart_info.get("axis_labels", {}),
                            "legend_info": chart_info.get("legend_info", [])
                        }
                    })
                    
                    logger.debug(f"✅ 第{page_num + 1}页图表{chart_index + 1}分析完成")
            
            logger.debug(f"📈 第{page_num + 1}页提取{len(chunks)}个图表")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ 图表提取失败: {e}")
            return []
    
    def _smart_text_chunking(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """智能文本分块"""
        try:
            chunks = []
            
            # 按段落分割
            paragraphs = text.split('\n\n')
            current_chunk = ""
            
            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                
                # 如果当前段落加入后超过块大小
                if len(current_chunk) + len(paragraph) > chunk_size:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        
                        # 处理重叠
                        if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                            current_chunk = current_chunk[-chunk_overlap:] + "\n" + paragraph
                        else:
                            current_chunk = paragraph
                    else:
                        # 单个段落过长，按句子分割
                        sentences = self._split_long_paragraph(paragraph, chunk_size)
                        chunks.extend(sentences[:-1])
                        current_chunk = sentences[-1] if sentences else ""
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + paragraph
                    else:
                        current_chunk = paragraph
            
            # 添加最后一个块
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            return chunks
            
        except Exception as e:
            logger.error(f"智能文本分块失败: {e}")
            # 回退到简单分块
            return self._simple_text_chunking(text, chunk_size, chunk_overlap)
    
    def _split_long_paragraph(self, paragraph: str, max_size: int) -> List[str]:
        """分割过长的段落"""
        try:
            # 按句子分割
            import re
            sentences = re.split(r'[.!?。！？]', paragraph)
            
            chunks = []
            current_chunk = ""
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                    
                if len(current_chunk) + len(sentence) > max_size:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence
                    else:
                        # 单个句子过长，强制分割
                        chunks.append(sentence[:max_size])
                        current_chunk = sentence[max_size:]
                else:
                    if current_chunk:
                        current_chunk += "。" + sentence
                    else:
                        current_chunk = sentence
            
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            return chunks
            
        except Exception as e:
            logger.error(f"段落分割失败: {e}")
            return [paragraph]
    
    def _simple_text_chunking(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """简单文本分块（回退方案）"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end].strip()
            
            if chunk:
                chunks.append(chunk)
            
            start = end - chunk_overlap
            if start >= len(text):
                break
        
        return chunks
    
    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        try:
            # 简单的语言检测
            chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
            total_chars = len([c for c in text if c.isalpha()])
            
            if total_chars > 0 and chinese_chars / total_chars > 0.3:
                return "zh"
            else:
                return "en"
        except:
            return "unknown"
    
    def _save_image_to_filesystem(self, pix, file_id: str, page_num: int, img_index: int) -> str:
        """保存图像到文件系统"""
        try:
            image_dir = self.multimedia_config.get("images", {}).get("save_dir", "uploads/images")
            os.makedirs(image_dir, exist_ok=True)
            
            image_filename = f"{file_id}_page_{page_num}_image_{img_index}.png"
            image_path = os.path.join(image_dir, image_filename)
            
            pix.save(image_path)
            
            return image_path
            
        except Exception as e:
            logger.error(f"保存图像失败: {e}")
            return None
    
    # 待续...（由于响应长度限制，这里先提供部分代码）

    def _analyze_image_content(self, pix, file_id: str, page_num: int, img_index: int) -> Dict[str, Any]:
        """深度分析图像内容"""
        try:
            # 基础信息
            width, height = pix.width, pix.height
            
            result = {
                "description": f"图像(第{page_num + 1}页)：尺寸{width}x{height}",
                "objects": [],
                "scene": "",
                "text_content": "",
                "visual_elements": []
            }
            
            # 保存临时图像用于分析
            temp_path = f"temp_img_{file_id}_{page_num}_{img_index}.png"
            
            try:
                pix.save(temp_path)
                
                # 使用OCR提取图像中的文字
                if self.image_config.get("text_detection", True):
                    ocr_text = self._extract_text_from_image(temp_path)
                    if ocr_text:
                        result["text_content"] = ocr_text
                        result["description"] += f"，包含文字：{ocr_text[:100]}"
                
                # 使用图像理解模型分析
                if self.image_config.get("understanding_model"):
                    understanding_result = self._image_understanding_analysis(temp_path)
                    if understanding_result:
                        result.update(understanding_result)
                
                # 清理临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                return result
                
            except Exception as e:
                # 确保清理临时文件
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                logger.warning(f"图像内容分析失败: {e}")
                return result
            
        except Exception as e:
            logger.error(f"图像分析失败: {e}")
            return {
                "description": f"图像(第{page_num + 1}页)：分析失败",
                "objects": [],
                "scene": "",
                "text_content": "",
                "visual_elements": []
            }
    
    def _extract_text_from_image(self, image_path: str) -> str:
        """从图像中提取文字"""
        try:
            # 使用模型管理器的OCR功能
            ocr_results = model_manager.extract_text_from_image(image_path)
            
            if ocr_results:
                return " ".join([result.get("text", "") for result in ocr_results if result.get("text")])
            return ""
            
        except Exception as e:
            logger.warning(f"图像OCR失败: {e}")
            return ""
    
    def _image_understanding_analysis(self, image_path: str) -> Dict[str, Any]:
        """图像理解分析"""
        try:
            # 这里可以集成图像理解模型（如BLIP2）
            # 暂时返回基础分析结果
            logger.debug("图像理解分析功能待实现")
            return {
                "scene": "场景分析待实现",
                "objects": ["对象检测待实现"],
                "visual_elements": ["视觉元素分析待实现"]
            }
            
        except Exception as e:
            logger.error(f"图像理解分析失败: {e}")
            return {}
    
    def _analyze_table_content(self, table_data: List[List[str]], page_num: int, table_index: int) -> Dict[str, Any]:
        """分析表格内容"""
        try:
            if not table_data:
                return {"formatted_content": f"表格(第{page_num + 1}页)：空表格"}
            
            # 格式化表格内容
            content_lines = [f"表格(第{page_num + 1}页，表{table_index + 1})："]
            
            # 表头
            if table_data:
                headers = table_data[0]
                content_lines.append("表头：" + " | ".join(str(cell) for cell in headers))
                
                # 数据行
                max_rows = self.table_config.get("max_embed_rows", 50)
                data_rows = table_data[1:min(max_rows + 1, len(table_data))]
                
                for i, row in enumerate(data_rows, 1):
                    row_text = " | ".join(str(cell) for cell in row)
                    content_lines.append(f"第{i}行：{row_text}")
                
                if len(table_data) > max_rows + 1:
                    content_lines.append(f"... (共{len(table_data) - 1}行数据)")
            
            # 生成表格摘要
            summary = ""
            if self.table_config.get("generate_summary", True):
                summary = self._generate_table_summary(table_data)
            
            # 分析数据类型
            data_types = self._analyze_table_data_types(table_data)
            
            return {
                "formatted_content": "\n".join(content_lines),
                "summary": summary,
                "data_types": data_types,
                "key_insights": self._extract_table_insights(table_data)
            }
            
        except Exception as e:
            logger.error(f"表格内容分析失败: {e}")
            return {"formatted_content": f"表格(第{page_num + 1}页)：分析失败"}
    
    def _generate_table_summary(self, table_data: List[List[str]]) -> str:
        """生成表格摘要"""
        try:
            if not table_data or len(table_data) < 2:
                return "表格数据不足"
            
            rows = len(table_data) - 1  # 排除表头
            cols = len(table_data[0])
            
            summary = f"包含{rows}行{cols}列数据"
            
            # 简单的数据特征分析
            if len(table_data) > 1:
                headers = table_data[0]
                summary += f"，主要字段：{', '.join(headers[:3])}"
                if len(headers) > 3:
                    summary += "等"
            
            return summary
            
        except Exception as e:
            logger.error(f"表格摘要生成失败: {e}")
            return "摘要生成失败"
    
    def _analyze_table_data_types(self, table_data: List[List[str]]) -> List[str]:
        """分析表格数据类型"""
        try:
            if not table_data or len(table_data) < 2:
                return []
            
            data_types = []
            cols = len(table_data[0])
            
            for col_idx in range(cols):
                # 收集该列的数据样本
                col_data = []
                for row_idx in range(1, min(6, len(table_data))):  # 取前5行数据分析
                    if col_idx < len(table_data[row_idx]):
                        col_data.append(str(table_data[row_idx][col_idx]).strip())
                
                # 简单的类型推断
                if not col_data:
                    data_types.append("empty")
                elif all(self._is_number(val) for val in col_data if val):
                    data_types.append("number")
                elif all(self._is_date(val) for val in col_data if val):
                    data_types.append("date")
                else:
                    data_types.append("text")
            
            return data_types
            
        except Exception as e:
            logger.error(f"数据类型分析失败: {e}")
            return []
    
    def _is_number(self, value: str) -> bool:
        """检查是否为数字"""
        try:
            float(value.replace(",", "").replace("%", ""))
            return True
        except:
            return False
    
    def _is_date(self, value: str) -> bool:
        """检查是否为日期"""
        try:
            import re
            # 简单的日期格式检查
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',
                r'\d{2}/\d{2}/\d{4}',
                r'\d{4}年\d{1,2}月\d{1,2}日'
            ]
            return any(re.match(pattern, value) for pattern in date_patterns)
        except:
            return False
    
    def _extract_table_insights(self, table_data: List[List[str]]) -> List[str]:
        """提取表格关键见解"""
        try:
            insights = []
            
            if not table_data or len(table_data) < 2:
                return insights
            
            # 基础统计
            rows = len(table_data) - 1
            cols = len(table_data[0])
            insights.append(f"数据维度：{rows}行×{cols}列")
            
            # 检查数值列的统计信息
            for col_idx in range(cols):
                col_name = table_data[0][col_idx] if table_data[0] else f"列{col_idx + 1}"
                numbers = []
                
                for row_idx in range(1, len(table_data)):
                    if col_idx < len(table_data[row_idx]):
                        val = str(table_data[row_idx][col_idx]).strip()
                        if self._is_number(val):
                            try:
                                numbers.append(float(val.replace(",", "").replace("%", "")))
                            except:
                                pass
                
                if len(numbers) > 0:
                    avg = sum(numbers) / len(numbers)
                    insights.append(f"{col_name}平均值：{avg:.2f}")
            
            return insights[:5]  # 限制见解数量
            
        except Exception as e:
            logger.error(f"表格见解提取失败: {e}")
            return []
    
    def _save_table_to_filesystem(self, table_data: List[List[str]], file_id: str, page_num: int, table_index: int) -> str:
        """保存表格到文件系统"""
        try:
            table_dir = self.multimedia_config.get("tables", {}).get("export_dir", "uploads/tables")
            os.makedirs(table_dir, exist_ok=True)
            
            # 保存为CSV格式
            import csv
            table_filename = f"{file_id}_page_{page_num}_table_{table_index}.csv"
            table_path = os.path.join(table_dir, table_filename)
            
            with open(table_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerows(table_data)
            
            return table_path
            
        except Exception as e:
            logger.error(f"保存表格失败: {e}")
            return None
    
    def _analyze_chart_content(self, img_data: bytes, file_id: str, page_num: int) -> Dict[str, Any]:
        """分析图表内容"""
        try:
            # 图表检测和分析逻辑（待完整实现）
            logger.debug("图表分析功能待完整实现")
            
            # 暂时返回基础结果
            return {
                "charts_detected": [],
                "analysis_complete": False
            }
            
        except Exception as e:
            logger.error(f"图表分析失败: {e}")
            return {"charts_detected": []}
    
    def _save_chart_to_filesystem(self, chart_image_data: bytes, file_id: str, page_num: int, chart_index: int) -> str:
        """保存图表到文件系统"""
        try:
            chart_dir = self.multimedia_config.get("charts", {}).get("save_dir", "uploads/charts")
            os.makedirs(chart_dir, exist_ok=True)
            
            chart_filename = f"{file_id}_page_{page_num}_chart_{chart_index}.png"
            chart_path = os.path.join(chart_dir, chart_filename)
            
            with open(chart_path, 'wb') as f:
                f.write(chart_image_data)
            
            return chart_path
            
        except Exception as e:
            logger.error(f"保存图表失败: {e}")
            return None
    
    def _generate_embeddings_for_chunks(self, chunks: List[Dict[str, Any]], file_id: str) -> None:
        """为内容块生成嵌入向量"""
        try:
            # 提取文本内容
            texts = [chunk["content"] for chunk in chunks]
            total_chunks = len(texts)
            logger.info(f"🔤 开始生成{total_chunks}个内容块的嵌入向量...")
            
            # 初始状态更新
            self._update_processing_status(file_id, "processing", 32, 
                                         f"🔤 准备为{total_chunks}个内容块生成嵌入向量...")
            
            # 分批处理嵌入向量生成，避免内存过载
            batch_size = 50  # 每批处理50个文本
            all_embeddings = []
            total_batches = (total_chunks + batch_size - 1) // batch_size
            
            for i in range(0, total_chunks, batch_size):
                batch_texts = texts[i:i + batch_size]
                current_batch = i // batch_size + 1
                batch_progress = 32 + int((i / total_chunks) * 18)  # 32% 到 50%
                
                self._update_processing_status(file_id, "processing", batch_progress, 
                                             f"🔤 正在生成第{current_batch}/{total_batches}批嵌入向量 ({i+1}-{min(i+batch_size, total_chunks)}/{total_chunks})")
                
                # 生成当前批次的嵌入向量
                batch_embeddings = model_manager.get_embedding(batch_texts)
                all_embeddings.extend(batch_embeddings)
                
                logger.info(f"🔤 完成批次 {current_batch}/{total_batches}")
            
            # 分配给各个块
            for chunk, embedding in zip(chunks, all_embeddings):
                chunk["embedding"] = embedding
            
            logger.info(f"✅ 嵌入向量生成完成，共{len(all_embeddings)}个768维向量")
            
        except Exception as e:
            logger.error(f"❌ 嵌入向量生成失败: {e}")
            raise
    
    def _save_chunks_to_vector_db(self, chunks: List[Dict[str, Any]], file_id: str) -> None:
        """保存内容块到向量数据库"""
        try:
            total_chunks = len(chunks)
            logger.info(f"💾 开始保存{total_chunks}个向量到Milvus数据库...")
            
            # 初始状态更新
            self._update_processing_status(file_id, "processing", 52, 
                                         "💾 正在连接向量数据库...")
            
            # 确保Milvus连接
            if not milvus_manager.collection:
                logger.info("初始化Milvus连接...")
                milvus_manager.connect()
            
            self._update_processing_status(file_id, "processing", 55, 
                                         f"💾 准备保存{total_chunks}个向量到Milvus数据库...")
            
            # 准备向量数据
            vector_data = []
            for i, chunk in enumerate(chunks):
                if i % 100 == 0:  # 每100个chunk更新一次进度
                    prep_progress = 55 + int((i / total_chunks) * 5)  # 55% 到 60%
                    self._update_processing_status(file_id, "processing", prep_progress, 
                                                 f"💾 正在准备向量数据 ({i+1}/{total_chunks})")
                
                vector_data.append({
                    "file_id": chunk["file_id"],
                    "chunk_id": chunk["chunk_id"],
                    "content": chunk["content"],
                    "embedding": chunk["embedding"],
                    "metadata": json.dumps(chunk.get("metadata", {}))
                })
            
            self._update_processing_status(file_id, "processing", 60, 
                                         f"💾 开始批量插入{total_chunks}个向量到数据库...")
            
            # 分批插入数据，避免一次性插入过多数据
            batch_size = 100
            total_insert_batches = (len(vector_data) + batch_size - 1) // batch_size
            for i in range(0, len(vector_data), batch_size):
                batch_data = vector_data[i:i + batch_size]
                current_insert_batch = i // batch_size + 1
                insert_progress = 60 + int((i / len(vector_data)) * 5)  # 60% 到 65%
                
                self._update_processing_status(file_id, "processing", insert_progress, 
                                             f"💾 正在插入第{current_insert_batch}/{total_insert_batches}批向量数据 ({i+1}-{min(i+batch_size, len(vector_data))}/{len(vector_data)})")
                
                milvus_manager.insert_vectors(batch_data)
                logger.info(f"💾 插入批次 {current_insert_batch}/{total_insert_batches}")
            
            logger.info(f"✅ 成功保存{len(vector_data)}个向量到Milvus")
            
        except Exception as e:
            logger.error(f"❌ 保存向量数据失败: {e}")
            raise
    
    def _build_knowledge_graph(self, chunks: List[Dict[str, Any]], file_id: str) -> Dict[str, Any]:
        """构建知识图谱"""
        try:
            # 分离不同类型的内容块
            text_chunks = [c for c in chunks if c["content_type"] == "text"]
            image_chunks = [c for c in chunks if c["content_type"] == "image"]
            table_chunks = [c for c in chunks if c["content_type"] == "table"]
            chart_chunks = [c for c in chunks if c["content_type"] == "chart"]
            
            self._update_processing_status(file_id, "processing", 68, 
                                         f"🧠 开始分析内容：文本{len(text_chunks)}块，表格{len(table_chunks)}个，图像{len(image_chunks)}个，图表{len(chart_chunks)}个")
            
            all_entities = []
            all_relations = []
            
            # 从文本中提取实体和关系
            if text_chunks:
                self._update_processing_status(file_id, "processing", 70, 
                                             f"🧠 正在从{len(text_chunks)}个文本块提取实体和关系...")
                text_entities, text_relations = self._extract_entities_relations_from_text(text_chunks)
                all_entities.extend(text_entities)
                all_relations.extend(text_relations)
                self._update_processing_status(file_id, "processing", 75, 
                                             f"📝 文本分析完成：发现{len(text_entities)}个实体，{len(text_relations)}个关系")
            
            # 从表格中提取实体和关系
            if table_chunks:
                self._update_processing_status(file_id, "processing", 77, 
                                             f"📊 正在从{len(table_chunks)}个表格提取实体和关系...")
                table_entities, table_relations = self._extract_entities_relations_from_tables(table_chunks)
                all_entities.extend(table_entities)
                all_relations.extend(table_relations)
                self._update_processing_status(file_id, "processing", 79, 
                                             f"📊 表格分析完成：发现{len(table_entities)}个实体，{len(table_relations)}个关系")
            
            # 从图像中提取实体
            if image_chunks:
                self._update_processing_status(file_id, "processing", 80, 
                                             f"🖼️ 正在从{len(image_chunks)}个图像识别实体...")
                image_entities = self._extract_entities_from_images(image_chunks)
                all_entities.extend(image_entities)
                self._update_processing_status(file_id, "processing", 81, 
                                             f"🖼️ 图像分析完成：识别出{len(image_entities)}个实体")
            
            # 从图表中提取实体和关系
            if chart_chunks:
                self._update_processing_status(file_id, "processing", 82, 
                                             f"📈 正在从{len(chart_chunks)}个图表提取实体和关系...")
                chart_entities, chart_relations = self._extract_entities_relations_from_charts(chart_chunks)
                all_entities.extend(chart_entities)
                all_relations.extend(chart_relations)
                self._update_processing_status(file_id, "processing", 83, 
                                             f"📈 图表分析完成：发现{len(chart_entities)}个实体，{len(chart_relations)}个关系")
            
            # 实体去重和合并
            self._update_processing_status(file_id, "processing", 84, 
                                         f"🔗 正在整理实体去重，原始发现{len(all_entities)}个实体...")
            deduplicated_entities = self._deduplicate_entities(all_entities)
            
            # 关系优化
            self._update_processing_status(file_id, "processing", 85, 
                                         f"🔗 正在优化关系连接，原始发现{len(all_relations)}个关系...")
            optimized_relations = self._optimize_relations(all_relations, deduplicated_entities)
            
            logger.info(f"✅ 知识图谱构建完成：{len(deduplicated_entities)}个实体，{len(optimized_relations)}个关系")
            
            return {
                "entities": deduplicated_entities,
                "relations": optimized_relations,
                "entities_count": len(deduplicated_entities),
                "relations_count": len(optimized_relations)
            }
            
        except Exception as e:
            logger.error(f"❌ 知识图谱构建失败: {e}")
            return {
                "entities": [],
                "relations": [],
                "entities_count": 0,
                "relations_count": 0
            }
    
    def _extract_entities_relations_from_text(self, text_chunks: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        """从文本中提取实体和关系"""
        entities = []
        relations = []
        
        try:
            # 批量处理文本块
            batch_size = self.graphrag_config.get("batch_processing", {}).get("default_batch_size", 2)
            
            for i in range(0, len(text_chunks), batch_size):
                batch = text_chunks[i:i + batch_size]
                combined_text = "\n\n".join([chunk["content"] for chunk in batch])
                
                # 提取实体
                batch_entities = self._extract_entities_from_text(combined_text)
                
                # 提取关系
                batch_relations = self._extract_relations_from_text(combined_text, batch_entities)
                
                # 为实体和关系添加来源信息
                for entity in batch_entities:
                    entity["source_chunks"] = [chunk["chunk_id"] for chunk in batch]
                    entity["source_type"] = "text"
                
                for relation in batch_relations:
                    relation["source_chunks"] = [chunk["chunk_id"] for chunk in batch]
                    relation["source_type"] = "text"
                
                entities.extend(batch_entities)
                relations.extend(batch_relations)
            
            return entities, relations
            
        except Exception as e:
            logger.error(f"从文本提取实体关系失败: {e}")
            return [], []
    
    def _extract_entities_from_text(self, text: str) -> List[Dict[str, Any]]:
        """从文本中提取实体"""
        try:
            if "entity_extraction" not in self.prompt_config.get("document_parsing", {}):
                logger.warning("实体提取提示词未配置")
                return []
            
            prompt_template = self.prompt_config["document_parsing"]["entity_extraction"]
            prompt = prompt_template.format(text=text[:2000])  # 限制文本长度
            
            response = self._call_llm(prompt)
            
            # 解析响应
            entities = self._parse_entities_response(response)
            
            return entities
            
        except Exception as e:
            logger.error(f"实体提取失败: {e}")
            return []
    
    def _extract_relations_from_text(self, text: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从文本中提取关系"""
        try:
            if not entities or "relation_extraction" not in self.prompt_config.get("document_parsing", {}):
                return []
            
            entities_str = "\n".join([f"- {entity['name']} ({entity['type']})" for entity in entities[:10]])
            prompt_template = self.prompt_config["document_parsing"]["relation_extraction"]
            prompt = prompt_template.format(text=text[:2000], entities=entities_str)
            
            response = self._call_llm(prompt)
            
            # 解析响应
            relations = self._parse_relations_response(response)
            
            return relations
            
        except Exception as e:
            logger.error(f"关系提取失败: {e}")
            return []
    
    def _extract_entities_relations_from_tables(self, table_chunks: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        """从表格中提取实体和关系"""
        entities = []
        relations = []
        
        try:
            for table_chunk in table_chunks:
                table_data = table_chunk.get("table_data", [])
                if not table_data or len(table_data) < 2:
                    continue
                
                # 从表格头部提取实体（字段名）
                headers = table_data[0]
                for header in headers:
                    if header and str(header).strip():
                        entities.append({
                            "entity_id": str(uuid.uuid4()),
                            "name": str(header).strip(),
                            "type": "TABLE_FIELD",
                            "confidence": 0.9,
                            "source_chunks": [table_chunk["chunk_id"]],
                            "source_type": "table"
                        })
                
                # 从表格数据中提取实体（数据值）
                for row_idx, row in enumerate(table_data[1:6]):  # 限制处理行数
                    for col_idx, cell in enumerate(row):
                        if cell and str(cell).strip() and not self._is_number(str(cell)):
                            entities.append({
                                "entity_id": str(uuid.uuid4()),
                                "name": str(cell).strip(),
                                "type": "TABLE_VALUE",
                                "confidence": 0.7,
                                "source_chunks": [table_chunk["chunk_id"]],
                                "source_type": "table",
                                "table_position": {"row": row_idx + 1, "col": col_idx}
                            })
                
                # 创建字段之间的关系
                for i in range(len(headers) - 1):
                    relations.append({
                        "relationship_id": str(uuid.uuid4()),
                        "subject": headers[i],
                        "predicate": "RELATED_FIELD",
                        "object": headers[i + 1],
                        "confidence": 0.6,
                        "source_chunks": [table_chunk["chunk_id"]],
                        "source_type": "table"
                    })
            
            return entities, relations
            
        except Exception as e:
            logger.error(f"从表格提取实体关系失败: {e}")
            return [], []
    
    def _extract_entities_from_images(self, image_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从图像中提取实体"""
        entities = []
        
        try:
            for image_chunk in image_chunks:
                # 从图像的OCR文本中提取实体
                text_content = image_chunk.get("metadata", {}).get("text_content", "")
                if text_content:
                    text_entities = self._extract_entities_from_text(text_content)
                    for entity in text_entities:
                        entity["source_chunks"] = [image_chunk["chunk_id"]]
                        entity["source_type"] = "image"
                    entities.extend(text_entities)
                
                # 从检测到的对象中创建实体
                objects_detected = image_chunk.get("metadata", {}).get("objects_detected", [])
                for obj in objects_detected:
                    if isinstance(obj, str) and obj.strip():
                        entities.append({
                            "entity_id": str(uuid.uuid4()),
                            "name": obj.strip(),
                            "type": "IMAGE_OBJECT",
                            "confidence": 0.8,
                            "source_chunks": [image_chunk["chunk_id"]],
                            "source_type": "image"
                        })
            
            return entities
            
        except Exception as e:
            logger.error(f"从图像提取实体失败: {e}")
            return []
    
    def _extract_entities_relations_from_charts(self, chart_chunks: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        """从图表中提取实体和关系"""
        entities = []
        relations = []
        
        try:
            for chart_chunk in chart_chunks:
                metadata = chart_chunk.get("metadata", {})
                
                # 从轴标签提取实体
                axis_labels = metadata.get("axis_labels", {})
                for axis, label in axis_labels.items():
                    if label and str(label).strip():
                        entities.append({
                            "entity_id": str(uuid.uuid4()),
                            "name": str(label).strip(),
                            "type": "CHART_AXIS",
                            "confidence": 0.9,
                            "source_chunks": [chart_chunk["chunk_id"]],
                            "source_type": "chart"
                        })
                
                # 从图例信息提取实体
                legend_info = metadata.get("legend_info", [])
                for legend_item in legend_info:
                    if isinstance(legend_item, str) and legend_item.strip():
                        entities.append({
                            "entity_id": str(uuid.uuid4()),
                            "name": legend_item.strip(),
                            "type": "CHART_SERIES",
                            "confidence": 0.8,
                            "source_chunks": [chart_chunk["chunk_id"]],
                            "source_type": "chart"
                        })
                
                # 创建图表类型与数据的关系
                chart_type = metadata.get("chart_type", "")
                if chart_type:
                    for entity in entities[-len(legend_info):]:  # 对最近添加的图例实体
                        relations.append({
                            "relationship_id": str(uuid.uuid4()),
                            "subject": entity["name"],
                            "predicate": "DISPLAYED_IN",
                            "object": chart_type,
                            "confidence": 0.8,
                            "source_chunks": [chart_chunk["chunk_id"]],
                            "source_type": "chart"
                        })
            
            return entities, relations
            
        except Exception as e:
            logger.error(f"从图表提取实体关系失败: {e}")
            return [], []
    
    def _deduplicate_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """实体去重和合并"""
        try:
            if not entities:
                return []
            
            # 按名称分组
            entity_groups = {}
            for entity in entities:
                name = entity["name"].lower().strip()
                if name not in entity_groups:
                    entity_groups[name] = []
                entity_groups[name].append(entity)
            
            deduplicated = []
            similarity_threshold = self.graphrag_config.get("knowledge_graph", {}).get("similarity_threshold", 0.85)
            
            for name, group in entity_groups.items():
                if len(group) == 1:
                    deduplicated.append(group[0])
                else:
                    # 合并相似实体
                    merged_entity = self._merge_entities(group)
                    deduplicated.append(merged_entity)
            
            return deduplicated
            
        except Exception as e:
            logger.error(f"实体去重失败: {e}")
            return entities
    
    def _merge_entities(self, entity_group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并相似实体"""
        try:
            # 选择置信度最高的实体作为基础
            base_entity = max(entity_group, key=lambda x: x.get("confidence", 0))
            
            # 合并来源信息
            all_source_chunks = []
            for entity in entity_group:
                all_source_chunks.extend(entity.get("source_chunks", []))
            
            base_entity["source_chunks"] = list(set(all_source_chunks))
            base_entity["merged_count"] = len(entity_group)
            
            return base_entity
            
        except Exception as e:
            logger.error(f"实体合并失败: {e}")
            return entity_group[0] if entity_group else {}
    
    def _optimize_relations(self, relations: List[Dict[str, Any]], entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """优化关系"""
        try:
            # 创建实体名称到ID的映射
            entity_name_to_id = {entity["name"]: entity["entity_id"] for entity in entities}
            
            # 过滤和优化关系
            optimized = []
            seen_relations = set()
            
            for relation in relations:
                subject = relation.get("subject", "")
                object_name = relation.get("object", "")
                predicate = relation.get("predicate", "")
                
                # 检查实体是否存在
                if subject in entity_name_to_id and object_name in entity_name_to_id:
                    relation_key = f"{subject}_{predicate}_{object_name}"
                    if relation_key not in seen_relations:
                        seen_relations.add(relation_key)
                        optimized.append(relation)
            
            return optimized
            
        except Exception as e:
            logger.error(f"关系优化失败: {e}")
            return relations
    
    def _save_knowledge_graph_to_db(self, entities: List[Dict[str, Any]], relations: List[Dict[str, Any]], file_id: str) -> None:
        """保存知识图谱到数据库"""
        try:
            # 保存实体到Neo4j
            for entity in entities:
                entity_data = {
                    "entity_id": entity["entity_id"],
                    "name": entity["name"],
                    "type": entity["type"],
                    "file_id": file_id,
                    "confidence": entity["confidence"],
                    "source_type": entity.get("source_type", "unknown")
                }
                neo4j_manager.create_entity(entity["type"], entity_data)
            
            # 保存关系到Neo4j
            for relation in relations:
                subject_entity = {"name": relation["subject"]}
                object_entity = {"name": relation["object"]}
                relation_props = {
                    "confidence": relation["confidence"],
                    "file_id": file_id,
                    "source_type": relation.get("source_type", "unknown")
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
    
    def _call_llm(self, prompt: str) -> str:
        """调用大语言模型"""
        try:
            llm_config = self.model_config.get("llm", {})
            
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
            
            response = requests.post(
                f"{llm_config['api_url']}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content
            else:
                logger.error(f"LLM API调用失败: HTTP {response.status_code}")
                return '{"entities": [], "relations": []}'
                
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return '{"entities": [], "relations": []}'
    
    def _parse_entities_response(self, response: str) -> List[Dict[str, Any]]:
        """解析实体提取响应"""
        try:
            # 清理响应
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            elif cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            # 提取JSON
            start_idx = cleaned_response.find('{')
            end_idx = cleaned_response.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                json_str = cleaned_response[start_idx:end_idx+1]
                result = json.loads(json_str)
                
                entities = result.get("entities", [])
                standardized = []
                
                for entity in entities:
                    if isinstance(entity, dict) and entity.get("name"):
                        standardized.append({
                            "entity_id": str(uuid.uuid4()),
                            "name": entity.get("name", "").strip(),
                            "type": entity.get("type", "UNKNOWN").strip(),
                            "confidence": 0.8
                        })
                
                return standardized
            
            return []
            
        except Exception as e:
            logger.error(f"实体响应解析失败: {e}")
            return []
    
    def _parse_relations_response(self, response: str) -> List[Dict[str, Any]]:
        """解析关系提取响应"""
        try:
            # 清理响应
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            elif cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            # 提取JSON
            start_idx = cleaned_response.find('{')
            end_idx = cleaned_response.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                json_str = cleaned_response[start_idx:end_idx+1]
                result = json.loads(json_str)
                
                relations = result.get("relations", [])
                standardized = []
                
                for relation in relations:
                    if isinstance(relation, dict) and relation.get("subject") and relation.get("object"):
                        standardized.append({
                            "relationship_id": str(uuid.uuid4()),
                            "subject": relation.get("subject", "").strip(),
                            "predicate": relation.get("predicate", "RELATED_TO").strip(),
                            "object": relation.get("object", "").strip(),
                            "confidence": relation.get("confidence", 0.8)
                        })
                
                return standardized
            
            return []
            
        except Exception as e:
            logger.error(f"关系响应解析失败: {e}")
            return []
    
    def _update_processing_status(self, file_id: str, status: str, progress: int, message: str) -> None:
        """更新处理状态"""
        try:
            self.processing_status[file_id] = {
                "status": status,
                "progress": progress,
                "message": message,
                "updated_at": datetime.now()
            }
            
            # 更新数据库状态
            mysql_manager.execute_update(
                "UPDATE files SET status = %s, processing_progress = %s WHERE file_id = %s",
                (status, progress, file_id)
            )
            
            logger.info(f"📊 {file_id}: {status} - {progress}% - {message}")
            
        except Exception as e:
            logger.warning(f"更新处理状态失败: {e}")
    
    def get_processing_status(self, file_id: str) -> Dict[str, Any]:
        """获取处理状态"""
        return self.processing_status.get(file_id, {
            "status": "unknown",
            "progress": 0,
            "message": "状态未知"
        })

# 全局GraphRAG服务实例
graphrag_service = GraphRAGService()