"""
智能检索服务 - 多模态版
实现基于GraphRAG的智能问答系统，支持文字、图片、表格、图表的多模态内容展示
"""
import logging
import json
import requests
import os
import base64
from typing import Dict, List, Any, Optional, Generator
from datetime import datetime

from utils.config_loader import config_loader
from utils.database import mysql_manager, milvus_manager, neo4j_manager
from utils.model_manager import model_manager

logger = logging.getLogger(__name__)

class SearchService:
    """智能检索服务类 - 多模态版"""
    
    def __init__(self):
        self.config = config_loader.get_app_config()
        self.model_config = config_loader.get_model_config()
        self.prompt_config = config_loader.get_prompt_config()
        self.multimedia_config = self.config.get("multimedia", {})
        self.conversation_history = {}  # 存储对话历史
        
        logger.info("智能检索服务初始化完成 - 多模态版")
    
    def search(self, query: str, session_id: str = None, stream: bool = False) -> Dict[str, Any]:
        """
        智能检索主函数
        
        Args:
            query: 用户查询
            session_id: 会话ID，用于多轮对话
            stream: 是否流式返回
            
        Returns:
            检索结果
        """
        try:
            # 获取或创建会话
            if not session_id:
                session_id = self._create_session()
            
            # 记录用户查询
            self._add_to_conversation(session_id, "user", query)
            
            if stream:
                return self._stream_search(query, session_id)
            else:
                return self._direct_search(query, session_id)
                
        except Exception as e:
            logger.error(f"智能检索失败: {e}")
            return {
                "success": False,
                "message": f"检索失败: {str(e)}",
                "session_id": session_id
            }
    
    def _direct_search(self, query: str, session_id: str) -> Dict[str, Any]:
        """非流式检索"""
        # 向量检索
        vector_results = self._vector_search(query)
        
        # 图检索
        graph_results = self._graph_search(query)
        
        # 融合检索结果
        combined_results = self._combine_search_results(vector_results, graph_results)
        
        # 生成回答
        answer = self._generate_answer(query, combined_results, session_id)
        
        # 记录AI回答
        self._add_to_conversation(session_id, "assistant", answer)
        
        return {
            "success": True,
            "answer": answer,
            "sources": combined_results,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }
    
    def _stream_search(self, query: str, session_id: str) -> Generator[str, None, None]:
        """流式检索"""
        # 先执行检索
        vector_results = self._vector_search(query)
        graph_results = self._graph_search(query)
        combined_results = self._combine_search_results(vector_results, graph_results)
        
        # 流式生成回答
        full_answer = ""
        for chunk in self._generate_streaming_answer(query, combined_results, session_id):
            full_answer += chunk
            yield chunk
        
        # 记录完整回答
        self._add_to_conversation(session_id, "assistant", full_answer)
    
    def _vector_search(self, query: str) -> List[Dict[str, Any]]:
        """向量检索"""
        try:
            # 检查是否有可用的文档数据
            if not self._has_vector_data():
                logger.info("暂无向量数据，跳过向量检索")
                return []
            
            # 获取查询的嵌入向量
            query_embedding = model_manager.get_embedding([query])[0]
            
            # 在Milvus中搜索相似向量
            search_config = self.config["vector_search"]
            results = milvus_manager.search_vectors(
                query_embedding,
                top_k=search_config["top_k"]
            )
            
            # 过滤低相似度结果
            threshold = search_config["similarity_threshold"]
            filtered_results = [
                result for result in results 
                if result["score"] >= threshold
            ]
            
            logger.info(f"向量检索找到 {len(filtered_results)} 个相关结果")
            return filtered_results
            
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []
    
    def _has_vector_data(self) -> bool:
        """检查是否有向量数据"""
        try:
            # 检查Milvus集合是否有数据
            return milvus_manager.has_data()
        except Exception:
            return False
    
    def _graph_search(self, query: str) -> List[Dict[str, Any]]:
        """图检索"""
        try:
            # 提取查询中的实体
            entities = self._extract_query_entities(query)
            
            if not entities:
                return []
            
            # 在Neo4j中搜索相关的图结构
            graph_config = self.config["graph_search"]
            results = []
            
            for entity in entities:
                # 搜索实体相关的路径
                # Neo4j语法：路径长度需要是具体数字，不能使用参数
                max_hops = graph_config["max_hops"]
                cypher_query = f"""
                MATCH path = (n {{name: $entity_name}})-[*1..{max_hops}]-(m)
                RETURN path, n, m
                LIMIT $max_paths
                """
                
                graph_results = neo4j_manager.execute_query(
                    cypher_query,
                    {
                        "entity_name": entity,
                        "max_paths": graph_config["max_paths"]
                    }
                )
                
                results.extend(graph_results)
            
            logger.info(f"图检索找到 {len(results)} 个相关路径")
            return results
            
        except Exception as e:
            logger.error(f"图检索失败: {e}")
            return []
    
    def _extract_query_entities(self, query: str) -> List[str]:
        """从查询中提取实体"""
        # 这里需要实现实体识别
        # 可以使用NER模型或调用LLM
        
        # 暂时使用简单的关键词提取
        # 实际实现应该调用LLM进行实体识别
        entities = []
        
        # 简单的实体识别逻辑（示例）
        # 实际应该使用更复杂的NER方法
        words = query.split()
        for word in words:
            if len(word) > 2:  # 简单过滤
                entities.append(word)
        
        return entities[:3]  # 限制实体数量
    
    def _combine_search_results(self, vector_results: List[Dict], graph_results: List[Dict]) -> List[Dict[str, Any]]:
        """融合检索结果 - 多模态版"""
        combined = []
        
        # 处理向量检索结果
        for result in vector_results:
            metadata = json.loads(result["metadata"]) if result["metadata"] else {}
            content_type = metadata.get("type", "text")
            
            # 基础结果结构
            combined_item = {
                "type": "vector",
                "content_type": content_type,
                "content": result["content"],
                "file_id": result["file_id"],
                "chunk_id": result["chunk_id"],
                "score": result["score"],
                "metadata": metadata
            }
            
            # 根据内容类型添加多模态信息
            if content_type == "image":
                combined_item.update(self._process_image_result(result, metadata))
            elif content_type == "table":
                combined_item.update(self._process_table_result(result, metadata))
            elif content_type == "chart":
                combined_item.update(self._process_chart_result(result, metadata))
            
            combined.append(combined_item)
        
        # 处理图检索结果
        for result in graph_results:
            combined.append({
                "type": "graph",
                "content_type": "graph",
                "path": result,
                "score": 0.8  # 图结果默认分数
            })
        
        # 按分数排序，但优先展示多模态内容
        combined.sort(key=lambda x: (x.get("content_type") != "text", x["score"]), reverse=True)
        
        return combined[:15]  # 增加结果数量以容纳多模态内容
    
    def _generate_answer(self, query: str, search_results: List[Dict], session_id: str) -> str:
        """生成回答"""
        try:
            # 准备上下文信息
            context_info = self._prepare_context(search_results)
            
            # 获取对话历史
            history = self._get_conversation_history(session_id)
            
            # 选择合适的提示词模板
            if history:
                prompt_template = self.prompt_config["intelligent_search"]["conversation_context"]
                prompt = prompt_template.format(
                    conversation_history=self._format_conversation_history(history),
                    current_question=query,
                    document_info=context_info
                )
            else:
                prompt_template = self.prompt_config["intelligent_search"]["result_integration"]
                prompt = prompt_template.format(
                    question=query,
                    retrieved_info=context_info
                )
            
            # 调用LLM生成回答
            answer = self._call_llm(prompt)
            
            return answer
            
        except Exception as e:
            logger.error(f"生成回答失败: {e}")
            return "抱歉，我暂时无法回答这个问题，请稍后再试。"
    
    def _generate_streaming_answer(self, query: str, search_results: List[Dict], session_id: str) -> Generator[str, None, None]:
        """流式生成回答"""
        try:
            # 准备上下文信息
            context_info = self._prepare_context(search_results)
            
            # 获取对话历史
            history = self._get_conversation_history(session_id)
            
            # 准备提示词
            if history:
                prompt_template = self.prompt_config["intelligent_search"]["conversation_context"]
                prompt = prompt_template.format(
                    conversation_history=self._format_conversation_history(history),
                    current_question=query,
                    document_info=context_info
                )
            else:
                prompt_template = self.prompt_config["intelligent_search"]["result_integration"]
                prompt = prompt_template.format(
                    question=query,
                    retrieved_info=context_info
                )
            
            # 流式调用LLM
            for chunk in self._call_llm_stream(prompt):
                yield chunk
                
        except Exception as e:
            logger.error(f"流式生成回答失败: {e}")
            yield "抱歉，我暂时无法回答这个问题，请稍后再试。"
    
    def _prepare_context(self, search_results: List[Dict]) -> str:
        """准备上下文信息"""
        context_parts = []
        
        for i, result in enumerate(search_results, 1):
            if result["type"] == "vector":
                context_parts.append(f"文档片段 {i}：\n{result['content']}\n")
            elif result["type"] == "graph":
                # 处理图结构信息
                context_parts.append(f"关系信息 {i}：\n{self._format_graph_result(result)}\n")
        
        return "\n".join(context_parts)
    
    def _format_graph_result(self, graph_result: Dict) -> str:
        """格式化图结果"""
        # 简化的图结果格式化
        return "相关实体关系信息"
    
    def _call_llm(self, prompt: str) -> str:
        """调用LLM生成文本"""
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
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                logger.error(f"LLM API调用失败: {response.status_code} - {response.text}")
                return "抱歉，服务暂时不可用。"
                
        except Exception as e:
            logger.error(f"调用LLM失败: {e}")
            return "抱歉，服务暂时不可用。"
    
    def _call_llm_stream(self, prompt: str) -> Generator[str, None, None]:
        """流式调用LLM"""
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
                "temperature": llm_config["temperature"],
                "stream": True
            }
            
            response = requests.post(
                f"{llm_config['api_url']}/chat/completions",
                headers=headers,
                json=data,
                stream=True,
                timeout=30
            )
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data_str = line[6:]
                            if data_str.strip() == '[DONE]':
                                break
                            try:
                                data = json.loads(data_str)
                                if 'choices' in data and len(data['choices']) > 0:
                                    delta = data['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        yield delta['content']
                            except json.JSONDecodeError:
                                continue
            else:
                yield "抱歉，服务暂时不可用。"
                
        except Exception as e:
            logger.error(f"流式调用LLM失败: {e}")
            yield "抱歉，服务暂时不可用。"
    
    def _create_session(self) -> str:
        """创建新会话"""
        import uuid
        session_id = str(uuid.uuid4())
        self.conversation_history[session_id] = []
        return session_id
    
    def _add_to_conversation(self, session_id: str, role: str, content: str) -> None:
        """添加对话记录"""
        if session_id not in self.conversation_history:
            self.conversation_history[session_id] = []
        
        self.conversation_history[session_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # 限制对话历史长度
        max_history = 10
        if len(self.conversation_history[session_id]) > max_history:
            self.conversation_history[session_id] = self.conversation_history[session_id][-max_history:]
    
    def _get_conversation_history(self, session_id: str) -> List[Dict]:
        """获取对话历史"""
        return self.conversation_history.get(session_id, [])
    
    def _format_conversation_history(self, history: List[Dict]) -> str:
        """格式化对话历史"""
        formatted = []
        for item in history:
            role = "用户" if item["role"] == "user" else "助手"
            formatted.append(f"{role}: {item['content']}")
        
        return "\n".join(formatted)
    
    def get_conversation_history(self, session_id: str) -> List[Dict]:
        """获取会话的对话历史"""
        return self._get_conversation_history(session_id)
    
    def clear_conversation(self, session_id: str) -> bool:
        """清空会话历史"""
        if session_id in self.conversation_history:
            del self.conversation_history[session_id]
            return True
        return False
    
    def get_search_suggestions(self, query: str) -> List[str]:
        """获取搜索建议"""
        # 基于查询内容和现有文档提供搜索建议
        suggestions = []
        
        try:
            # 可以基于文档内容或常见查询模式生成建议
            # 这里提供一些基础建议
            if "表格" in query or "数据" in query:
                suggestions.extend([
                    "显示相关的数据表格",
                    "分析表格中的趋势",
                    "比较不同数据项"
                ])
            
            if "图" in query or "图片" in query:
                suggestions.extend([
                    "解释图表内容",
                    "描述图像信息",
                    "分析视觉元素"
                ])
            
            # 通用建议
            suggestions.extend([
                "总结文档主要内容",
                "提取关键信息",
                "查找相关章节"
            ])
            
        except Exception as e:
            logger.error(f"生成搜索建议失败: {e}")
        
        return suggestions[:5]  # 限制建议数量
    
    # ===== 多模态内容处理方法 =====
    
    def _process_image_result(self, result: Dict, metadata: Dict) -> Dict[str, Any]:
        """处理图像搜索结果"""
        try:
            # 查找图像文件路径
            image_path = self._find_image_path(result["file_id"], result["chunk_id"])
            
            # 图像展示信息
            image_info = {
                "image_path": image_path,
                "image_base64": self._encode_image_to_base64(image_path) if image_path else None,
                "image_description": result["content"],
                "image_metadata": {
                    "width": metadata.get("width"),
                    "height": metadata.get("height"),
                    "format": metadata.get("format"),
                    "objects_detected": metadata.get("objects_detected", []),
                    "text_content": metadata.get("text_content", "")
                },
                "display_type": "image"
            }
            
            return image_info
            
        except Exception as e:
            logger.error(f"处理图像结果失败: {e}")
            return {"display_type": "image", "error": str(e)}
    
    def _process_table_result(self, result: Dict, metadata: Dict) -> Dict[str, Any]:
        """处理表格搜索结果"""
        try:
            # 查找表格数据
            table_data = self._find_table_data(result["file_id"], result["chunk_id"])
            
            # 表格展示信息
            table_info = {
                "table_data": table_data,
                "table_summary": result["content"],
                "table_metadata": {
                    "rows": metadata.get("rows"),
                    "columns": metadata.get("columns"),
                    "data_types": metadata.get("data_types", []),
                    "key_insights": metadata.get("key_insights", [])
                },
                "table_export_formats": self.multimedia_config.get("tables", {}).get("export_formats", ["csv"]),
                "display_type": "table"
            }
            
            return table_info
            
        except Exception as e:
            logger.error(f"处理表格结果失败: {e}")
            return {"display_type": "table", "error": str(e)}
    
    def _process_chart_result(self, result: Dict, metadata: Dict) -> Dict[str, Any]:
        """处理图表搜索结果"""
        try:
            # 查找图表文件路径
            chart_path = self._find_chart_path(result["file_id"], result["chunk_id"])
            
            # 图表展示信息
            chart_info = {
                "chart_path": chart_path,
                "chart_base64": self._encode_image_to_base64(chart_path) if chart_path else None,
                "chart_description": result["content"],
                "chart_metadata": {
                    "chart_type": metadata.get("chart_type"),
                    "data_points": metadata.get("data_points", []),
                    "trend_analysis": metadata.get("trend_analysis", ""),
                    "statistical_summary": metadata.get("statistical_summary", {}),
                    "axis_labels": metadata.get("axis_labels", {}),
                    "legend_info": metadata.get("legend_info", [])
                },
                "display_type": "chart"
            }
            
            return chart_info
            
        except Exception as e:
            logger.error(f"处理图表结果失败: {e}")
            return {"display_type": "chart", "error": str(e)}
    
    def _find_image_path(self, file_id: str, chunk_id: str) -> Optional[str]:
        """查找图像文件路径"""
        try:
            # 从chunk_id解析图像信息
            # chunk_id格式: file_id_page_pagenum_image_imgindex
            parts = chunk_id.split("_")
            if len(parts) >= 6 and parts[2] == "page" and parts[4] == "image":
                page_num = parts[3]
                img_index = parts[5]
                
                image_dir = self.multimedia_config.get("images", {}).get("save_dir", "uploads/images")
                image_filename = f"{file_id}_page_{page_num}_image_{img_index}.png"
                image_path = os.path.join(image_dir, image_filename)
                
                if os.path.exists(image_path):
                    return image_path
            
            return None
            
        except Exception as e:
            logger.error(f"查找图像路径失败: {e}")
            return None
    
    def _find_table_data(self, file_id: str, chunk_id: str) -> Optional[List[List[str]]]:
        """查找表格数据"""
        try:
            # 从数据库查询表格数据或从文件读取
            # 这里简化处理，实际应该从GraphRAGService存储的数据中获取
            table_dir = self.multimedia_config.get("tables", {}).get("export_dir", "uploads/tables")
            
            # 从chunk_id解析表格信息
            parts = chunk_id.split("_")
            if len(parts) >= 6 and parts[2] == "page" and parts[4] == "table":
                page_num = parts[3]
                table_index = parts[5]
                
                table_filename = f"{file_id}_page_{page_num}_table_{table_index}.csv"
                table_path = os.path.join(table_dir, table_filename)
                
                if os.path.exists(table_path):
                    import csv
                    with open(table_path, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        return list(reader)
            
            return None
            
        except Exception as e:
            logger.error(f"查找表格数据失败: {e}")
            return None
    
    def _find_chart_path(self, file_id: str, chunk_id: str) -> Optional[str]:
        """查找图表文件路径"""
        try:
            # 从chunk_id解析图表信息
            parts = chunk_id.split("_")
            if len(parts) >= 6 and parts[2] == "page" and parts[4] == "chart":
                page_num = parts[3]
                chart_index = parts[5]
                
                chart_dir = self.multimedia_config.get("charts", {}).get("save_dir", "uploads/charts")
                chart_filename = f"{file_id}_page_{page_num}_chart_{chart_index}.png"
                chart_path = os.path.join(chart_dir, chart_filename)
                
                if os.path.exists(chart_path):
                    return chart_path
            
            return None
            
        except Exception as e:
            logger.error(f"查找图表路径失败: {e}")
            return None
    
    def _encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """将图像编码为base64字符串"""
        try:
            if not image_path or not os.path.exists(image_path):
                return None
            
            with open(image_path, 'rb') as f:
                image_data = f.read()
                base64_str = base64.b64encode(image_data).decode('utf-8')
                
                # 根据文件扩展名确定MIME类型
                ext = os.path.splitext(image_path)[1].lower()
                mime_type = {
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg', 
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.bmp': 'image/bmp',
                    '.svg': 'image/svg+xml'
                }.get(ext, 'image/png')
                
                return f"data:{mime_type};base64,{base64_str}"
            
        except Exception as e:
            logger.error(f"图像base64编码失败: {e}")
            return None
    
    def get_multimodal_content(self, file_id: str, content_type: str = None) -> List[Dict[str, Any]]:
        """获取文件的多模态内容"""
        try:
            # 从向量数据库查询指定文件的多模态内容
            if not milvus_manager.collection:
                return []
            
            # 构建查询表达式
            if content_type:
                expr = f"file_id == '{file_id}'"
            else:
                expr = f"file_id == '{file_id}'"
            
            results = milvus_manager.collection.query(
                expr=expr,
                output_fields=["chunk_id", "content", "metadata"]
            )
            
            multimodal_content = []
            for result in results:
                metadata = json.loads(result["metadata"]) if result["metadata"] else {}
                result_type = metadata.get("type", "text")
                
                if not content_type or result_type == content_type:
                    content_item = {
                        "chunk_id": result["chunk_id"],
                        "content": result["content"],
                        "content_type": result_type,
                        "metadata": metadata
                    }
                    
                    # 添加多模态展示信息
                    if result_type == "image":
                        content_item.update(self._process_image_result(result, metadata))
                    elif result_type == "table":
                        content_item.update(self._process_table_result(result, metadata))
                    elif result_type == "chart":
                        content_item.update(self._process_chart_result(result, metadata))
                    
                    multimodal_content.append(content_item)
            
            return multimodal_content
            
        except Exception as e:
            logger.error(f"获取多模态内容失败: {e}")
            return []

# 全局智能检索服务实例
search_service = SearchService() 