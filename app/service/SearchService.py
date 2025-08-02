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
        """流式检索 - 自然思考过程"""
        import json
        
        # 开始思考过程（流式文本输出）
        yield json.dumps({
            "type": "thinking_text",
            "content": "正在分析您的问题"
        }) + "\n"
        
        yield json.dumps({
            "type": "thinking_text", 
            "content": "，提取关键信息"
        }) + "\n"
        
        # 向量检索
        yield json.dumps({
            "type": "thinking_text",
            "content": "，查找相关文档"
        }) + "\n"
        vector_results = self._vector_search(query)
        
        if vector_results:
            yield json.dumps({
                "type": "thinking_text",
                "content": f"，找到 {len(vector_results)} 个相关片段"
            }) + "\n"
        
        # 图检索
        yield json.dumps({
            "type": "thinking_text",
            "content": "，搜索知识关联"
        }) + "\n"
        graph_results = self._graph_search(query)
        
        if graph_results:
            yield json.dumps({
                "type": "thinking_text",
                "content": f"，发现 {len(graph_results)} 个知识关系"
            }) + "\n"
        
        # 结果融合
        yield json.dumps({
            "type": "thinking_text",
            "content": "，整理信息"
        }) + "\n"
        combined_results = self._combine_search_results(vector_results, graph_results)
        
        # 分析多模态内容
        multimedia_count = sum(1 for r in combined_results if r.get("content_type") != "text")
        if multimedia_count > 0:
            content_types = list(set(r.get("content_type", "text") for r in combined_results if r.get("content_type") != "text"))
            type_names = {"image": "图片", "table": "表格", "chart": "图表"}
            content_desc = "、".join([type_names.get(t, t) for t in content_types])
            yield json.dumps({
                "type": "thinking_text",
                "content": f"，发现 {multimedia_count} 个多媒体元素（{content_desc}）"
            }) + "\n"
        
        # 思考完成
        yield json.dumps({
            "type": "thinking_text",
            "content": "，正在组织答案...\n\n"
        }) + "\n"
        
        # 流式生成答案
        full_answer_text = ""
        multimedia_map = {}
        
        # 首先准备多媒体映射
        for result in combined_results:
            if result.get("content_type") != "text":
                chunk_id = result.get("chunk_id")
                multimedia_map[chunk_id] = {
                    "type": result.get("content_type"),
                    "content_description": result.get("content", ""),
                    "display_data": self._prepare_display_data(result),
                    "file_id": result.get("file_id"),
                    "metadata": result.get("metadata", {})
                }
        
        # 流式生成文本内容
        for text_chunk in self._stream_generate_answer_with_placeholders(query, combined_results, session_id, multimedia_map):
            full_answer_text += text_chunk
            yield json.dumps({
                "type": "answer_chunk",
                "content": text_chunk
            }) + "\n"
        
        # 发送多媒体信息
        yield json.dumps({
            "type": "answer_multimedia",
            "multimedia_map": multimedia_map
        }) + "\n"
        
        # 答案完成信号
        yield json.dumps({
            "type": "answer_complete"
        }) + "\n"
        
        # 记录完整回答
        self._add_to_conversation(session_id, "assistant", full_answer_text)
    
    def _vector_search(self, query: str) -> List[Dict[str, Any]]:
        """向量检索 - 分层召回版"""
        try:
            # 检查是否有可用的文档数据
            if not self._has_vector_data():
                logger.info("暂无向量数据，跳过向量检索")
                return []
            
            # 1. BM25粗召回（如果支持）
            bm25_results = self._bm25_search(query, top_k=200)
            
            # 2. 向量召回 Top-200
            vector_results = self._dense_vector_search(query, top_k=200)
            
            # 3. 合并去重
            combined_results = self._merge_and_deduplicate(bm25_results, vector_results)
            
            # 4. 重排序 (使用BGE-reranker或Mini-LM)
            reranked_results = self._rerank_results(query, combined_results)
            
            # 5. 阈值过滤
            search_config = self.config.get("vector_search", {})
            threshold = search_config.get("similarity_threshold", 0.7)
            final_results = [
                result for result in reranked_results 
                if result.get("final_score", 0) >= threshold
            ]
            
            logger.info(f"分层检索: BM25({len(bm25_results)}) + 向量({len(vector_results)}) → 合并({len(combined_results)}) → 重排({len(reranked_results)}) → 过滤({len(final_results)})")
            return final_results[:search_config.get("top_k", 10)]
            
        except Exception as e:
            logger.error(f"分层向量检索失败: {e}")
            return []
    
    def _bm25_search(self, query: str, top_k: int = 200) -> List[Dict[str, Any]]:
        """BM25粗召回"""
        try:
            # 简化版本：使用MySQL全文搜索模拟BM25
            results = mysql_manager.execute_query("""
                SELECT file_id, chunk_id, content, 
                       MATCH(content) AGAINST(%s IN NATURAL LANGUAGE MODE) as bm25_score
                FROM file_chunks 
                WHERE MATCH(content) AGAINST(%s IN NATURAL LANGUAGE MODE)
                ORDER BY bm25_score DESC
                LIMIT %s
            """, (query, query, top_k))
            
            return [{"source": "bm25", "score": r["bm25_score"], **r} for r in results or []]
            
        except Exception as e:
            logger.warning(f"BM25检索失败，跳过: {e}")
            return []
    
    def _dense_vector_search(self, query: str, top_k: int = 200) -> List[Dict[str, Any]]:
        """密集向量检索"""
        try:
            # 获取查询的嵌入向量
            query_embedding = model_manager.get_embedding([query])[0]
            
            # 在Milvus中搜索相似向量
            results = milvus_manager.search_vectors(query_embedding, top_k=top_k)
            
            return [{"source": "vector", **result} for result in results]
            
        except Exception as e:
            logger.error(f"密集向量检索失败: {e}")
            return []
    
    def _merge_and_deduplicate(self, bm25_results: List[Dict], vector_results: List[Dict]) -> List[Dict[str, Any]]:
        """合并去重"""
        try:
            seen_chunks = set()
            merged = []
            
            # 合并两种检索结果
            all_results = bm25_results + vector_results
            
            for result in all_results:
                chunk_id = result.get("chunk_id")
                if chunk_id and chunk_id not in seen_chunks:
                    seen_chunks.add(chunk_id)
                    merged.append(result)
            
            return merged
            
        except Exception as e:
            logger.error(f"结果合并失败: {e}")
            return bm25_results + vector_results
    
    def _rerank_results(self, query: str, results: List[Dict]) -> List[Dict[str, Any]]:
        """重排序"""
        try:
            if not results:
                return []
            
            # 使用RRF (Reciprocal Rank Fusion) 算法
            rrf_scores = {}
            k = 60  # RRF参数
            
            # 按来源分组排序
            bm25_results = sorted([r for r in results if r.get("source") == "bm25"], 
                                key=lambda x: x.get("score", 0), reverse=True)
            vector_results = sorted([r for r in results if r.get("source") == "vector"], 
                                  key=lambda x: x.get("score", 0), reverse=True)
            
            # 计算RRF分数
            for rank, result in enumerate(bm25_results, 1):
                chunk_id = result.get("chunk_id")
                if chunk_id:
                    rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1.0 / (k + rank)
            
            for rank, result in enumerate(vector_results, 1):
                chunk_id = result.get("chunk_id")
                if chunk_id:
                    rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1.0 / (k + rank)
            
            # 为结果添加最终分数
            for result in results:
                chunk_id = result.get("chunk_id")
                result["final_score"] = rrf_scores.get(chunk_id, 0)
            
            # 按最终分数排序
            return sorted(results, key=lambda x: x.get("final_score", 0), reverse=True)
            
        except Exception as e:
            logger.error(f"重排序失败: {e}")
            return results
    
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
        """从查询中提取实体 - NER/LLM 升级版"""
        try:
            entities = []
            
            # 方法1: 使用spaCy NER（如果可用）
            try:
                entities.extend(self._extract_entities_with_spacy(query))
            except ImportError:
                logger.debug("spaCy不可用，跳过NER提取")
            except Exception as e:
                logger.warning(f"spaCy NER提取失败: {e}")
            
            # 方法2: 使用LLM进行实体提取
            llm_entities = self._extract_entities_with_llm(query)
            entities.extend(llm_entities)
            
            # 方法3: 基于模式的实体识别
            pattern_entities = self._extract_entities_with_patterns(query)
            entities.extend(pattern_entities)
            
            # 去重并按置信度排序
            unique_entities = list(set(entities))
            
            # 实体对齐：查找图谱中实际存在的实体
            aligned_entities = self._align_entities_with_graph(unique_entities)
            
            logger.info(f"实体提取: 原始({len(unique_entities)}) → 对齐({len(aligned_entities)})")
            return aligned_entities[:5]  # 限制实体数量
            
        except Exception as e:
            logger.error(f"实体提取失败: {e}")
            # 回退到简单方法
            return self._simple_entity_extraction(query)
    
    def _extract_entities_with_spacy(self, query: str) -> List[str]:
        """使用spaCy进行NER"""
        try:
            import spacy
            
            # 尝试加载中文模型
            try:
                nlp = spacy.load("zh_core_web_sm")
            except OSError:
                # 回退到英文模型
                nlp = spacy.load("en_core_web_sm")
            
            doc = nlp(query)
            entities = []
            
            for ent in doc.ents:
                # 过滤有用的实体类型
                if ent.label_ in ["PERSON", "ORG", "GPE", "PRODUCT", "EVENT", "WORK_OF_ART"]:
                    entities.append(ent.text.strip())
            
            return entities
            
        except Exception as e:
            logger.debug(f"spaCy NER失败: {e}")
            return []
    
    def _extract_entities_with_llm(self, query: str) -> List[str]:
        """使用LLM进行实体提取（带缓存）"""
        try:
            # 检查缓存
            cache_key = f"entity_extract_{hash(query)}"
            if hasattr(self, '_entity_cache') and cache_key in self._entity_cache:
                return self._entity_cache[cache_key]
            
            # 构建实体提取prompt
            entity_prompt = f"""
请从以下查询中提取关键实体，包括人名、机构名、产品名、概念等：

查询: {query}

请只返回实体列表，每行一个，不要其他解释：
"""
            
            response = self._call_llm(entity_prompt)
            
            # 解析LLM响应
            entities = []
            for line in response.split('\n'):
                line = line.strip()
                if line and not line.startswith(('请', '查询', '实体', '-', '*')):
                    # 清理常见的LLM输出噪音
                    cleaned = line.replace('- ', '').replace('* ', '').strip()
                    if len(cleaned) > 1 and len(cleaned) < 50:
                        entities.append(cleaned)
            
            # 缓存结果
            if not hasattr(self, '_entity_cache'):
                self._entity_cache = {}
            self._entity_cache[cache_key] = entities
            
            return entities[:10]  # LLM提取限制数量
            
        except Exception as e:
            logger.warning(f"LLM实体提取失败: {e}")
            return []
    
    def _extract_entities_with_patterns(self, query: str) -> List[str]:
        """基于模式的实体识别"""
        try:
            import re
            entities = []
            
            # 中文人名模式
            chinese_name_pattern = r'[王李张刘陈杨黄赵周吴徐孙胡朱高林何郭马罗梁宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏锺汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段漕钱汤尹黎易常武乔贺赖龚文][一-龥]{1,3}'
            names = re.findall(chinese_name_pattern, query)
            entities.extend(names)
            
            # 组织机构模式
            org_patterns = [
                r'[一-龥]+(?:公司|集团|企业|机构|组织|部门|学院|大学|医院|银行)',
                r'[A-Z][a-zA-Z\s]+(?:Inc|Corp|Ltd|LLC|Company|Group|Organization)',
            ]
            for pattern in org_patterns:
                matches = re.findall(pattern, query)
                entities.extend(matches)
            
            # 产品/概念模式
            concept_patterns = [
                r'[一-龥]{2,8}(?:系统|平台|产品|技术|方案|模型|算法|协议)',
                r'[A-Z]{2,}(?:\s+[A-Z]{2,})*',  # 缩写词
            ]
            for pattern in concept_patterns:
                matches = re.findall(pattern, query)
                entities.extend(matches)
            
            return entities
            
        except Exception as e:
            logger.warning(f"模式实体提取失败: {e}")
            return []
    
    def _align_entities_with_graph(self, entities: List[str]) -> List[str]:
        """实体与知识图谱对齐"""
        try:
            if not entities:
                return []
            
            aligned_entities = []
            
            # 在Neo4j中查找实际存在的实体
            for entity in entities:
                # 精确匹配
                exact_match = neo4j_manager.execute_query(
                    "MATCH (n:Entity {name: $name}) RETURN n.name as name LIMIT 1",
                    {"name": entity}
                )
                
                if exact_match:
                    aligned_entities.append(entity)
                    continue
                
                # 模糊匹配
                fuzzy_matches = neo4j_manager.execute_query(
                    "MATCH (n:Entity) WHERE n.name CONTAINS $partial_name RETURN n.name as name LIMIT 3",
                    {"partial_name": entity}
                )
                
                if fuzzy_matches:
                    # 选择最相似的
                    best_match = self._find_most_similar(entity, [m["name"] for m in fuzzy_matches])
                    if best_match:
                        aligned_entities.append(best_match)
            
            return aligned_entities
            
        except Exception as e:
            logger.warning(f"实体对齐失败: {e}")
            return entities  # 返回原始实体
    
    def _find_most_similar(self, target: str, candidates: List[str]) -> Optional[str]:
        """找到最相似的实体"""
        try:
            from difflib import SequenceMatcher
            
            best_match = None
            best_score = 0.0
            
            for candidate in candidates:
                score = SequenceMatcher(None, target.lower(), candidate.lower()).ratio()
                if score > best_score and score > 0.6:  # 相似度阈值
                    best_score = score
                    best_match = candidate
            
            return best_match
            
        except Exception:
            return candidates[0] if candidates else None
    
    def _simple_entity_extraction(self, query: str) -> List[str]:
        """简单实体提取（回退方案）"""
        try:
            import jieba
            
            # 使用jieba分词
            words = list(jieba.cut(query))
            
            # 过滤有意义的词
            entities = []
            for word in words:
                word = word.strip()
                if (len(word) >= 2 and 
                    not word.isdigit() and 
                    word not in ['的', '是', '在', '有', '和', '与', '或', '但', '而', '了', '吗', '呢']):
                    entities.append(word)
            
            return entities[:5]
            
        except ImportError:
            # jieba也不可用，使用最基础的方法
            words = query.split()
            return [w for w in words if len(w) > 2][:3]
        except Exception as e:
            logger.error(f"简单实体提取失败: {e}")
            return []
    
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
            file_id = result.get("file_id", "")
            chunk_id = result.get("chunk_id", "")
            
            logger.debug(f"正在处理图片: file_id={file_id}, chunk_id={chunk_id}")
            
            image_path = self._find_image_path(file_id, chunk_id)
            logger.debug(f"图片路径查找结果: {image_path}")
            
            # 编码图片为base64
            image_base64 = None
            if image_path and os.path.exists(image_path):
                image_base64 = self._encode_image_to_base64(image_path)
                logger.debug(f"图片base64编码{'成功' if image_base64 else '失败'}")
            else:
                logger.warning(f"图片文件不存在: {image_path}")
                # 生成占位图片
                image_base64 = self._generate_placeholder_image()
            
            # 图像展示信息
            image_info = {
                "image_path": image_path,
                "image_base64": image_base64,
                "image_description": result.get("content", "图片内容"),
                "image_metadata": {
                    "width": metadata.get("width"),
                    "height": metadata.get("height"),
                    "format": metadata.get("format"),
                    "objects_detected": metadata.get("objects_detected", []),
                    "text_content": metadata.get("text_content", "")
                },
                "display_type": "image",
                "status": "loaded" if image_base64 else "failed"
            }
            
            return image_info
            
        except Exception as e:
            logger.error(f"处理图像结果失败: {e}")
            return {
                "display_type": "image", 
                "error": str(e),
                "image_base64": self._generate_placeholder_image(),
                "status": "error"
            }
    
    def _process_table_result(self, result: Dict, metadata: Dict) -> Dict[str, Any]:
        """处理表格搜索结果"""
        try:
            # 查找表格数据
            file_id = result.get("file_id", "")
            chunk_id = result.get("chunk_id", "")
            
            logger.debug(f"正在处理表格: file_id={file_id}, chunk_id={chunk_id}")
            
            table_data = self._find_table_data(file_id, chunk_id)
            
            # 如果找不到实际表格数据，生成示例数据
            if not table_data:
                logger.warning(f"表格数据不存在，生成示例数据")
                table_data = self._generate_sample_table_data(result.get("content", ""))
            
            logger.debug(f"表格数据加载{'成功' if table_data else '失败'}: {len(table_data) if table_data else 0}行")
            
            # 表格展示信息
            table_info = {
                "table_data": table_data,
                "table_summary": result.get("content", "表格内容"),
                "table_metadata": {
                    "rows": len(table_data) - 1 if table_data and len(table_data) > 1 else 0,
                    "columns": len(table_data[0]) if table_data and len(table_data) > 0 else 0,
                    "data_types": metadata.get("data_types", []),
                    "key_insights": metadata.get("key_insights", [])
                },
                "table_export_formats": self.multimedia_config.get("tables", {}).get("export_formats", ["csv"]),
                "display_type": "table",
                "status": "loaded" if table_data else "failed"
            }
            
            return table_info
            
        except Exception as e:
            logger.error(f"处理表格结果失败: {e}")
            return {
                "display_type": "table", 
                "error": str(e),
                "table_data": self._generate_sample_table_data("错误示例"),
                "status": "error"
            }
    
    def _process_chart_result(self, result: Dict, metadata: Dict) -> Dict[str, Any]:
        """处理图表搜索结果"""
        try:
            # 查找图表文件路径
            file_id = result.get("file_id", "")
            chunk_id = result.get("chunk_id", "")
            
            logger.debug(f"正在处理图表: file_id={file_id}, chunk_id={chunk_id}")
            
            chart_path = self._find_chart_path(file_id, chunk_id)
            logger.debug(f"图表路径查找结果: {chart_path}")
            
            # 编码图表为base64
            chart_base64 = None
            if chart_path and os.path.exists(chart_path):
                chart_base64 = self._encode_image_to_base64(chart_path)
                logger.debug(f"图表base64编码{'成功' if chart_base64 else '失败'}")
            else:
                logger.warning(f"图表文件不存在: {chart_path}")
                # 生成占位图表
                chart_base64 = self._generate_placeholder_chart()
            
            # 图表展示信息
            chart_info = {
                "chart_path": chart_path,
                "chart_base64": chart_base64,
                "chart_description": result.get("content", "图表内容"),
                "chart_metadata": {
                    "chart_type": metadata.get("chart_type", "未知"),
                    "data_points": metadata.get("data_points", []),
                    "trend_analysis": metadata.get("trend_analysis", ""),
                    "statistical_summary": metadata.get("statistical_summary", {}),
                    "axis_labels": metadata.get("axis_labels", {}),
                    "legend_info": metadata.get("legend_info", [])
                },
                "display_type": "chart",
                "status": "loaded" if chart_base64 else "failed"
            }
            
            return chart_info
            
        except Exception as e:
            logger.error(f"处理图表结果失败: {e}")
            return {
                "display_type": "chart", 
                "error": str(e),
                "chart_base64": self._generate_placeholder_chart(),
                "status": "error"
            }
    
    def _find_image_path(self, file_id: str, chunk_id: str) -> Optional[str]:
        """查找图像文件路径"""
        try:
            # 改进的chunk_id解析逻辑
            # chunk_id格式: file_id_page_pagenum_image_imgindex
            
            # 使用file_id作为分割基准，更加稳定
            if chunk_id.startswith(file_id + "_page_"):
                remaining = chunk_id[len(file_id + "_page_"):]
                parts = remaining.split("_")
                
                # 期望格式: pagenum_image_imgindex
                if len(parts) >= 3 and parts[1] == "image":
                    page_num = parts[0]
                    img_index = parts[2]
                    
                    image_dir = self.multimedia_config.get("images", {}).get("save_dir", "uploads/images")
                    image_filename = f"{file_id}_page_{page_num}_image_{img_index}.png"
                    image_path = os.path.join(image_dir, image_filename)
                    
                    logger.debug(f"查找图片路径: {image_path}")
                    
                    if os.path.exists(image_path):
                        logger.debug(f"✅ 图片文件存在: {image_path}")
                        return image_path
                    else:
                        logger.warning(f"❌ 图片文件不存在: {image_path}")
            else:
                logger.warning(f"chunk_id格式不匹配: {chunk_id}, 期望以 {file_id}_page_ 开头")
            
            return None
            
        except Exception as e:
            logger.error(f"查找图像路径失败: {e}")
            return None
    
    def _find_table_data(self, file_id: str, chunk_id: str) -> Optional[List[List[str]]]:
        """查找表格数据"""
        try:
            # 改进的chunk_id解析逻辑（与图片保持一致）
            table_dir = self.multimedia_config.get("tables", {}).get("export_dir", "uploads/tables")
            
            # 使用file_id作为分割基准
            if chunk_id.startswith(file_id + "_page_"):
                remaining = chunk_id[len(file_id + "_page_"):]
                parts = remaining.split("_")
                
                # 期望格式: pagenum_table_tableindex
                if len(parts) >= 3 and parts[1] == "table":
                    page_num = parts[0]
                    table_index = parts[2]
                    
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
            # 改进的chunk_id解析逻辑（与图片保持一致）
            if chunk_id.startswith(file_id + "_page_"):
                remaining = chunk_id[len(file_id + "_page_"):]
                parts = remaining.split("_")
                
                # 期望格式: pagenum_chart_chartindex
                if len(parts) >= 3 and parts[1] == "chart":
                    page_num = parts[0]
                    chart_index = parts[2]
                    
                    chart_dir = self.multimedia_config.get("charts", {}).get("save_dir", "uploads/charts")
                    chart_filename = f"{file_id}_page_{page_num}_chart_{chart_index}.png"
                    chart_path = os.path.join(chart_dir, chart_filename)
                    
                    logger.debug(f"查找图表路径: {chart_path}")
                    
                    if os.path.exists(chart_path):
                        logger.debug(f"✅ 图表文件存在: {chart_path}")
                        return chart_path
                    else:
                        logger.warning(f"❌ 图表文件不存在: {chart_path}")
            else:
                logger.warning(f"chunk_id格式不匹配: {chunk_id}, 期望以 {file_id}_page_ 开头")
            
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
    
    def _prepare_display_data(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """准备用于前端显示的数据"""
        content_type = result.get("content_type", "text")
        display_data = {}
        
        if content_type == "image":
            display_data = self._process_image_result(result, result.get("metadata", {}))
        elif content_type == "table":
            display_data = self._process_table_result(result, result.get("metadata", {}))
        elif content_type == "chart":
            display_data = self._process_chart_result(result, result.get("metadata", {}))
        
        return display_data
    
    def _generate_unified_answer_with_multimedia(self, query: str, search_results: List[Dict], session_id: str) -> Dict[str, Any]:
        """
        生成包含多媒体内容的统一回答
        """
        try:
            # 准备多媒体内容映射
            multimedia_map = {}
            for result in search_results:
                if result.get("content_type") != "text":
                    chunk_id = result.get("chunk_id")
                    multimedia_map[chunk_id] = {
                        "type": result.get("content_type"),
                        "content_description": result.get("content", ""),
                        "display_data": self._prepare_display_data(result),
                        "file_id": result.get("file_id"),
                        "metadata": result.get("metadata", {})
                    }
            
            # 生成包含占位符的文本内容
            text_with_placeholders = self._generate_answer_with_placeholders(query, search_results, session_id, multimedia_map)
            
            # 构建统一的回答结构
            unified_answer = {
                "text_content": text_with_placeholders,
                "multimedia_map": multimedia_map,
                "structure": {
                    "has_images": any(v["type"] == "image" for v in multimedia_map.values()),
                    "has_tables": any(v["type"] == "table" for v in multimedia_map.values()),
                    "has_charts": any(v["type"] == "chart" for v in multimedia_map.values()),
                    "multimedia_count": len(multimedia_map)
                }
            }
            
            return unified_answer
            
        except Exception as e:
            logger.error(f"生成统一回答失败: {e}")
            return {
                "text_content": "抱歉，生成回答时遇到问题。",
                "multimedia_map": {},
                "structure": {"has_images": False, "has_tables": False, "has_charts": False, "multimedia_count": 0}
            }
    
    def _generate_answer_with_placeholders(self, query: str, search_results: List[Dict], session_id: str, multimedia_map: Dict) -> str:
        """
        生成包含多媒体占位符的回答文本
        """
        try:
            # 准备上下文信息，包含多媒体引用说明
            context_parts = []
            
            for i, result in enumerate(search_results, 1):
                if result["type"] == "vector":
                    content_type = result.get("content_type", "text")
                    chunk_id = result.get("chunk_id", "")
                    
                    if content_type == "text":
                        context_parts.append(f"文档片段 {i}：\n{result['content']}\n")
                    else:
                        # 为多媒体内容添加占位符说明
                        placeholder = f"[{content_type.upper()}:{chunk_id}]"
                        context_parts.append(f"多媒体内容 {i}（{content_type}）：{placeholder}\n描述：{result['content']}\n")
                
                elif result["type"] == "graph":
                    context_parts.append(f"关系信息 {i}：\n{self._format_graph_result(result)}\n")
            
            context_info = "\n".join(context_parts)
            
            # 获取对话历史
            history = self._get_conversation_history(session_id)
            
            # 构建特殊的prompt，指导LLM在适当位置插入多媒体占位符
            multimedia_instructions = ""
            if multimedia_map:
                multimedia_instructions = f"""

在回答中，你可以在适当的位置引用以下多媒体内容：
{chr(10).join([f'- {content_type.upper()}内容: [{content_type.upper()}:{chunk_id}] - {data["content_description"][:100]}...' 
              for chunk_id, data in multimedia_map.items() 
              for content_type in [data["type"]]])}

请在回答中的合适位置使用这些占位符，例如：
- 当需要展示图片时，写: [IMAGE:chunk_id]
- 当需要展示表格时，写: [TABLE:chunk_id]  
- 当需要展示图表时，写: [CHART:chunk_id]

占位符应该放在相关文字描述之后，作为支撑材料。
"""
            
            # 选择合适的提示词模板
            if history:
                prompt_template = self.prompt_config["intelligent_search"]["conversation_context"]
                prompt = prompt_template.format(
                    conversation_history=self._format_conversation_history(history),
                    current_question=query,
                    document_info=context_info
                ) + multimedia_instructions
            else:
                prompt_template = self.prompt_config["intelligent_search"]["result_integration"]
                prompt = prompt_template.format(
                    question=query,
                    retrieved_info=context_info
                ) + multimedia_instructions
            
            # 调用LLM生成包含占位符的回答
            answer = self._call_llm(prompt)
            
            return answer
            
        except Exception as e:
            logger.error(f"生成带占位符回答失败: {e}")
            return "抱歉，我暂时无法回答这个问题，请稍后再试。"
    
    def _stream_generate_answer_with_placeholders(self, query: str, search_results: List[Dict], session_id: str, multimedia_map: Dict) -> Generator[str, None, None]:
        """
        流式生成包含多媒体占位符的回答文本
        """
        try:
            # 准备上下文信息，包含多媒体引用说明
            context_parts = []
            
            for i, result in enumerate(search_results, 1):
                if result["type"] == "vector":
                    content_type = result.get("content_type", "text")
                    chunk_id = result.get("chunk_id", "")
                    
                    if content_type == "text":
                        context_parts.append(f"文档片段 {i}：\n{result['content']}\n")
                    else:
                        # 为多媒体内容添加占位符说明
                        placeholder = f"[{content_type.upper()}:{chunk_id}]"
                        context_parts.append(f"多媒体内容 {i}（{content_type}）：{placeholder}\n描述：{result['content']}\n")
                
                elif result["type"] == "graph":
                    context_parts.append(f"关系信息 {i}：\n{self._format_graph_result(result)}\n")
            
            context_info = "\n".join(context_parts)
            
            # 获取对话历史
            history = self._get_conversation_history(session_id)
            
            # 多媒体使用说明
            multimedia_instructions = ""
            if multimedia_map:
                multimedia_instructions = f"""

在回答中，你可以在适当的位置引用以下多媒体内容：
{chr(10).join([f'- {content_type.upper()}内容: [{content_type.upper()}:{chunk_id}] - {data["content_description"][:100]}...' 
              for chunk_id, data in multimedia_map.items() 
              for content_type in [data["type"]]])}

请在回答中的合适位置使用这些占位符，例如：
- 当需要展示图片时，写: [IMAGE:chunk_id]
- 当需要展示表格时，写: [TABLE:chunk_id]  
- 当需要展示图表时，写: [CHART:chunk_id]

占位符应该放在相关文字描述之后，作为支撑材料。
"""
            
            # 选择合适的提示词模板
            if history:
                prompt_template = self.prompt_config["intelligent_search"]["conversation_context"]
                prompt = prompt_template.format(
                    conversation_history=self._format_conversation_history(history),
                    current_question=query,
                    document_info=context_info
                ) + multimedia_instructions
            else:
                prompt_template = self.prompt_config["intelligent_search"]["result_integration"]
                prompt = prompt_template.format(
                    question=query,
                    retrieved_info=context_info
                ) + multimedia_instructions
            
            # 流式调用LLM生成包含占位符的回答
            for chunk in self._call_llm_stream(prompt):
                yield chunk
                
        except Exception as e:
            logger.error(f"流式生成带占位符回答失败: {e}")
            yield "抱歉，生成回答时遇到问题。"
    
    def get_enhanced_answer_with_layout(self, query: str, session_id: str = None) -> Dict[str, Any]:
        """
        获取带有智能布局的增强回答
        """
        try:
            # 获取基础搜索结果
            basic_result = self.search(query, session_id, stream=False)
            
            if not basic_result.get("success"):
                return basic_result
            
            # 分析内容并生成智能布局
            sources = basic_result.get("sources", [])
            layout = self._generate_intelligent_layout(sources, query)
            
            # 生成结构化回答
            structured_answer = self._generate_structured_answer(query, sources, layout, session_id)
            
            return {
                "success": True,
                "answer": structured_answer,
                "layout": layout,
                "sources": sources,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"生成增强回答失败: {e}")
            return {
                "success": False,
                "message": f"生成回答失败: {str(e)}",
                "session_id": session_id
            }
    
    def _generate_intelligent_layout(self, sources: List[Dict], query: str) -> Dict[str, Any]:
        """
        生成智能内容布局
        """
        layout = {
            "sections": [],
            "content_flow": "mixed",  # mixed, media_first, text_first
            "interaction_level": "basic"  # basic, intermediate, advanced
        }
        
        # 分析内容类型分布
        content_types = {}
        for source in sources:
            content_type = source.get("content_type", "text")
            content_types[content_type] = content_types.get(content_type, 0) + 1
        
        # 根据查询类型调整布局策略
        if "图" in query or "图片" in query or "图像" in query:
            layout["content_flow"] = "media_first"
        elif "表格" in query or "数据" in query or "统计" in query:
            layout["content_flow"] = "mixed"
        else:
            layout["content_flow"] = "text_first"
        
        # 生成布局段落
        if content_types.get("image", 0) > 0:
            layout["sections"].append({
                "type": "images",
                "title": "相关图片",
                "count": content_types["image"],
                "interactive": True
            })
        
        if content_types.get("table", 0) > 0:
            layout["sections"].append({
                "type": "tables", 
                "title": "数据表格",
                "count": content_types["table"],
                "interactive": True
            })
        
        if content_types.get("chart", 0) > 0:
            layout["sections"].append({
                "type": "charts",
                "title": "图表分析", 
                "count": content_types["chart"],
                "interactive": True
            })
        
        # 总是包含文本总结
        layout["sections"].append({
            "type": "text_summary",
            "title": "详细解答",
            "count": 1,
            "interactive": False
        })
        
        return layout
    
    def _generate_structured_answer(self, query: str, sources: List[Dict], layout: Dict, session_id: str) -> Dict[str, Any]:
        """
        生成结构化回答
        """
        structured = {
            "sections": {},
            "summary": "",
            "key_points": [],
            "recommendations": []
        }
        
        # 按布局生成各个部分
        for section in layout["sections"]:
            section_type = section["type"]
            
            if section_type in ["images", "tables", "charts"]:
                content_type = section_type[:-1]  # 去掉复数s
                section_sources = [s for s in sources if s.get("content_type") == content_type]
                structured["sections"][section_type] = {
                    "title": section["title"],
                    "contents": section_sources,
                    "analysis": self._generate_content_analysis(section_sources, content_type)
                }
            elif section_type == "text_summary":
                structured["sections"]["text_summary"] = {
                    "title": section["title"],
                    "content": self._generate_comprehensive_summary(query, sources, session_id)
                }
        
        # 生成关键要点
        structured["key_points"] = self._extract_key_points(sources)
        
        # 生成建议
        structured["recommendations"] = self._generate_recommendations(query, sources)
        
        return structured
    
    def _generate_content_analysis(self, sources: List[Dict], content_type: str) -> str:
        """
        为特定类型内容生成分析
        """
        if not sources:
            return ""
        
        analysis_prompts = {
            "image": "请分析这些图片的内容和它们之间的关联：",
            "table": "请分析这些表格数据的关键信息和趋势：", 
            "chart": "请分析这些图表显示的数据模式和洞察："
        }
        
        prompt = analysis_prompts.get(content_type, "请分析这些内容：")
        context = "\n".join([s.get("content", "") for s in sources[:3]])  # 限制上下文长度
        
        try:
            analysis = self._call_llm(f"{prompt}\n\n{context}\n\n请提供简洁的分析。")
            return analysis
        except Exception as e:
            logger.error(f"生成内容分析失败: {e}")
            return "分析暂时不可用。"
    
    def _generate_comprehensive_summary(self, query: str, sources: List[Dict], session_id: str) -> str:
        """
        生成综合性总结
        """
        # 重用现有的答案生成逻辑
        return self._generate_answer(query, sources, session_id)
    
    def _extract_key_points(self, sources: List[Dict]) -> List[str]:
        """
        提取关键要点
        """
        key_points = []
        
        # 从不同类型的内容中提取要点
        for source in sources[:5]:  # 限制处理数量
            content = source.get("content", "")
            content_type = source.get("content_type", "text")
            
            if content and len(content) > 50:
                # 简化的要点提取（实际可用LLM优化）
                if content_type == "text":
                    # 提取文本要点
                    sentences = content.split('。')[:2]  # 取前两句
                    for sentence in sentences:
                        if len(sentence.strip()) > 20:
                            key_points.append(sentence.strip() + "。")
                elif content_type in ["image", "table", "chart"]:
                    # 多媒体内容的要点
                    key_points.append(f"{content_type}内容：{content[:100]}...")
        
        return key_points[:5]  # 最多5个要点
    
    def _generate_recommendations(self, query: str, sources: List[Dict]) -> List[str]:
        """
        生成相关建议
        """
        recommendations = []
        
        # 根据内容类型生成建议
        content_types = set(s.get("content_type", "text") for s in sources)
        
        if "image" in content_types:
            recommendations.append("建议仔细查看相关图片以获得更直观的理解")
        
        if "table" in content_types:
            recommendations.append("建议分析表格数据以发现更多数据模式")
        
        if "chart" in content_types:
            recommendations.append("建议研究图表趋势以了解数据变化")
        
        # 添加通用建议
        recommendations.extend([
            "可以基于这些内容提出更具体的问题",
            "建议关注关键数据点和趋势分析"
        ])
        
        return recommendations[:4]  # 最多4个建议
    
    def _generate_placeholder_image(self) -> str:
        """生成占位图片的base64编码"""
        try:
            # 生成简单的SVG占位图片
            svg_content = '''<svg width="400" height="300" xmlns="http://www.w3.org/2000/svg">
                <rect width="400" height="300" fill="#f0f0f0" stroke="#ccc" stroke-width="2"/>
                <text x="200" y="140" text-anchor="middle" font-family="Arial" font-size="16" fill="#666">📷 图片内容</text>
                <text x="200" y="170" text-anchor="middle" font-family="Arial" font-size="12" fill="#999">来自PDF文档</text>
            </svg>'''
            import base64
            svg_bytes = svg_content.strip().encode('utf-8')
            base64_str = base64.b64encode(svg_bytes).decode('utf-8')
            return f"data:image/svg+xml;base64,{base64_str}"
        except Exception as e:
            logger.error(f"生成占位图片失败: {e}")
            return None
    
    def _generate_placeholder_chart(self) -> str:
        """生成占位图表的base64编码"""
        try:
            # 生成简单的SVG占位图表
            svg_content = '''<svg width="400" height="300" xmlns="http://www.w3.org/2000/svg">
                <rect width="400" height="300" fill="#f8f9fa" stroke="#dee2e6" stroke-width="2"/>
                <rect x="50" y="50" width="300" height="200" fill="none" stroke="#6c757d" stroke-width="1"/>
                <line x1="50" y1="250" x2="350" y2="250" stroke="#6c757d" stroke-width="2"/>
                <line x1="50" y1="50" x2="50" y2="250" stroke="#6c757d" stroke-width="2"/>
                <rect x="80" y="200" width="40" height="50" fill="#007bff" opacity="0.7"/>
                <rect x="140" y="150" width="40" height="100" fill="#28a745" opacity="0.7"/>
                <rect x="200" y="100" width="40" height="150" fill="#ffc107" opacity="0.7"/>
                <rect x="260" y="180" width="40" height="70" fill="#dc3545" opacity="0.7"/>
                <text x="200" y="280" text-anchor="middle" font-family="Arial" font-size="14" fill="#495057">📊 图表数据可视化</text>
            </svg>'''
            import base64
            svg_bytes = svg_content.strip().encode('utf-8')
            base64_str = base64.b64encode(svg_bytes).decode('utf-8')
            return f"data:image/svg+xml;base64,{base64_str}"
        except Exception as e:
            logger.error(f"生成占位图表失败: {e}")
            return None
    
    def _generate_sample_table_data(self, description: str) -> List[List[str]]:
        """生成示例表格数据"""
        try:
            # 根据描述生成合适的示例数据
            if "财务" in description or "收入" in description or "利润" in description:
                return [
                    ["项目", "Q1", "Q2", "Q3", "Q4"],
                    ["营业收入(万元)", "2,580", "2,890", "3,120", "3,650"],
                    ["净利润(万元)", "386", "445", "512", "678"],
                    ["增长率", "12.5%", "15.2%", "18.8%", "25.1%"]
                ]
            elif "销售" in description or "产品" in description:
                return [
                    ["产品", "销量", "单价", "收入"],
                    ["产品A", "1,200", "¥85", "¥102,000"],
                    ["产品B", "890", "¥120", "¥106,800"],
                    ["产品C", "650", "¥200", "¥130,000"]
                ]
            else:
                return [
                    ["类别", "数值", "百分比", "备注"],
                    ["项目1", "125", "25.0%", "正常"],
                    ["项目2", "189", "37.8%", "优秀"],
                    ["项目3", "94", "18.8%", "一般"],
                    ["项目4", "92", "18.4%", "需改进"]
                ]
        except Exception as e:
            logger.error(f"生成示例表格数据失败: {e}")
            return [
                ["列1", "列2", "列3"],
                ["数据1", "数据2", "数据3"],
                ["示例", "内容", "展示"]
            ]
    
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