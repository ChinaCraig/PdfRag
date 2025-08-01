"""
Neo4j图数据库管理器
负责图数据的存储、查询和关系管理功能
"""
import logging
from typing import Dict, List, Any
from neo4j import GraphDatabase
from utils.config_loader import config_loader

logger = logging.getLogger(__name__)

class Neo4jManager:
    """Neo4j图数据库管理器"""
    
    def __init__(self):
        self.driver = None
        self.config = config_loader.get_db_config()["neo4j"]
    
    def connect(self) -> None:
        """连接到Neo4j数据库"""
        try:
            self.driver = GraphDatabase.driver(
                self.config["uri"],
                auth=(self.config["username"], self.config["password"])
            )
            logger.info("Neo4j图数据库连接成功")
        except Exception as e:
            logger.error(f"Neo4j图数据库连接失败: {e}")
            raise
    
    def disconnect(self) -> None:
        """断开数据库连接"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j数据库连接已断开")
    
    def execute_query(self, query: str, parameters: Dict = None) -> List[Dict]:
        """执行Cypher查询"""
        try:
            if not self.driver:
                logger.info("数据库连接不存在，正在重新连接...")
                self.connect()
            
            # 验证查询参数
            if not query or not isinstance(query, str):
                raise ValueError("查询语句不能为空且必须是字符串")
            
            parameters = parameters or {}
            if not isinstance(parameters, dict):
                raise ValueError("参数必须是字典类型")
            
            logger.debug(f"执行查询: {query[:100]}{'...' if len(query) > 100 else ''}")
            logger.debug(f"参数: {parameters}")
            
            with self.driver.session() as session:
                result = session.run(query, parameters)
                records = [record.data() for record in result]
                logger.debug(f"查询返回 {len(records)} 条记录")
                return records
                
        except Exception as e:
            logger.error(f"执行Neo4j查询失败: {e}")
            logger.error(f"查询: {query}")
            logger.error(f"参数: {parameters}")
            
            # 针对常见错误提供更好的错误信息
            if "ParameterMissing" in str(e):
                logger.error("参数缺失错误 - 检查查询中的$参数是否都有对应的值")
            elif "SyntaxError" in str(e):
                logger.error("Cypher语法错误 - 检查查询语句语法")
            elif "ConstraintValidationFailed" in str(e):
                logger.error("约束验证失败 - 可能违反了唯一性约束")
            elif "ConnectionError" in str(e):
                logger.error("数据库连接错误 - 检查Neo4j服务状态")
            
            raise
    
    def _sanitize_entity_type(self, entity_type: str) -> str:
        """清理实体类型名称，确保符合Neo4j命名规范"""
        import re
        # 移除特殊字符，只保留字母、数字和下划线
        sanitized = re.sub(r'[^A-Za-z0-9_]', '_', entity_type)
        # 确保以字母开头和非空
        if not sanitized or not sanitized[0].isalpha():
            sanitized = 'ENTITY_' + (sanitized if sanitized else 'UNKNOWN')
        return sanitized.upper()  # 标签通常用大写
    
    def create_entity(self, entity_type: str, properties: Dict[str, Any]) -> None:
        """创建实体节点"""
        if not properties or not isinstance(properties, dict):
            logger.error("create_entity: properties参数无效")
            return
        
        # 验证必需的name字段
        entity_name = properties.get("name")
        if not entity_name or not str(entity_name).strip():
            logger.error(f"create_entity: 缺少有效的name字段，properties: {properties}")
            return
        
        # 清理和验证实体类型，防止注入攻击
        sanitized_entity_type = self._sanitize_entity_type(entity_type)
        entity_name = str(entity_name).strip()
        
        try:
            # 使用MERGE避免重复创建，根据name属性去重
            # 分离name和其他属性，避免参数冲突
            other_properties = {k: v for k, v in properties.items() if k != "name"}
            
            # 如果有其他属性，使用SET更新；如果没有，只创建节点
            if other_properties:
                query = f"""
                MERGE (n:{sanitized_entity_type} {{name: $name}})
                SET n += $properties
                """
                params = {
                    "name": entity_name,
                    "properties": other_properties
                }
            else:
                query = f"""
                MERGE (n:{sanitized_entity_type} {{name: $name}})
                """
                params = {"name": entity_name}
            
            self.execute_query(query, params)
            logger.debug(f"✅ 实体创建成功: {sanitized_entity_type}(name={entity_name})")
            
        except Exception as e:
            logger.error(f"❌ 创建实体失败: {sanitized_entity_type}(name={entity_name}), 错误: {e}")
            raise
    
    def _sanitize_relation_type(self, relation_type: str) -> str:
        """清理关系类型名称，确保符合Neo4j命名规范"""
        import re
        # 移除特殊字符，只保留字母、数字和下划线
        sanitized = re.sub(r'[^A-Za-z0-9_]', '_', relation_type)
        # 确保以字母开头和非空
        if not sanitized or not sanitized[0].isalpha():
            sanitized = 'REL_' + (sanitized if sanitized else 'UNKNOWN')
        return sanitized.upper()  # 关系类型通常用大写
    
    def create_relationship(self, from_entity: Dict, to_entity: Dict, 
                          relation_type: str, properties: Dict = None) -> None:
        """创建关系"""
        # 验证输入参数
        if not from_entity or not isinstance(from_entity, dict):
            logger.error("create_relationship: from_entity参数无效")
            return
        
        if not to_entity or not isinstance(to_entity, dict):
            logger.error("create_relationship: to_entity参数无效")
            return
        
        # 验证实体名称
        from_name = from_entity.get("name")
        to_name = to_entity.get("name")
        
        if not from_name or not str(from_name).strip():
            logger.error(f"create_relationship: from_entity缺少有效的name字段，from_entity: {from_entity}")
            return
        
        if not to_name or not str(to_name).strip():
            logger.error(f"create_relationship: to_entity缺少有效的name字段，to_entity: {to_entity}")
            return
        
        # 清理和验证关系类型，防止注入攻击
        sanitized_relation_type = self._sanitize_relation_type(relation_type)
        from_name = str(from_name).strip()
        to_name = str(to_name).strip()
        properties = properties or {}
        
        try:
            # 关系类型不能参数化，需要用字符串格式化
            # 同时使用MERGE避免重复创建关系
            if properties:
                # 有属性时，创建关系并设置属性
                query = f"""
                MATCH (a {{name: $from_name}}), (b {{name: $to_name}})
                MERGE (a)-[r:{sanitized_relation_type}]->(b)
                SET r += $properties
                """
                params = {
                    "from_name": from_name,
                    "to_name": to_name,
                    "properties": properties
                }
            else:
                # 无属性时，只创建关系
                query = f"""
                MATCH (a {{name: $from_name}}), (b {{name: $to_name}})
                MERGE (a)-[r:{sanitized_relation_type}]->(b)
                """
                params = {
                    "from_name": from_name,
                    "to_name": to_name
                }
            
            self.execute_query(query, params)
            logger.debug(f"✅ 关系创建成功: {from_name} -[{sanitized_relation_type}]-> {to_name}")
            
        except Exception as e:
            logger.error(f"❌ 创建关系失败: {from_name} -[{sanitized_relation_type}]-> {to_name}, 错误: {e}")
            raise
    
    def check_nodes_exist(self, entity_names: List[str]) -> Dict[str, bool]:
        """检查节点是否存在"""
        try:
            if not entity_names:
                return {}
            
            # 使用参数化查询检查多个节点
            query = "UNWIND $names AS name MATCH (n {name: name}) RETURN name"
            params = {"names": entity_names}
            
            result = self.execute_query(query, params)
            existing_names = {record["name"] for record in result}
            
            return {name: name in existing_names for name in entity_names}
            
        except Exception as e:
            logger.error(f"检查节点存在性失败: {e}")
            return {name: False for name in entity_names}
    
    def health_check(self) -> bool:
        """数据库健康检查"""
        try:
            result = self.execute_query("RETURN 1 AS test")
            return len(result) > 0 and result[0].get("test") == 1
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")
            return False
    
    def create_relationship_safe(self, from_entity: Dict, to_entity: Dict, 
                               relation_type: str, properties: Dict = None) -> bool:
        """安全的关系创建 - 确保节点存在"""
        try:
            from_name = from_entity.get("name", "").strip()
            to_name = to_entity.get("name", "").strip()
            
            if not from_name or not to_name:
                logger.error("节点名称不能为空")
                return False
            
            # 检查节点是否存在
            node_status = self.check_nodes_exist([from_name, to_name])
            
            missing_nodes = [name for name, exists in node_status.items() if not exists]
            if missing_nodes:
                logger.warning(f"关系创建失败: 以下节点不存在: {missing_nodes}")
                return False
            
            # 节点都存在，创建关系
            self.create_relationship(from_entity, to_entity, relation_type, properties)
            return True
            
        except Exception as e:
            logger.error(f"安全关系创建失败: {e}")
            return False
    
    def batch_create_entities(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量创建实体"""
        created_count = 0
        failed_count = 0
        errors = []
        
        for i, entity_data in enumerate(entities):
            try:
                entity_type = entity_data.get("type", "UNKNOWN")
                properties = {k: v for k, v in entity_data.items() if k != "type"}
                
                self.create_entity(entity_type, properties)
                created_count += 1
                
                # 每100个实体记录一次进度
                if (i + 1) % 100 == 0:
                    logger.info(f"批量创建进度: {i + 1}/{len(entities)}")
                    
            except Exception as e:
                failed_count += 1
                error_msg = f"创建实体失败 [{i}]: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            "total": len(entities),
            "created": created_count,
            "failed": failed_count,
            "errors": errors
        }
    
    def batch_create_relationships(self, relationships: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量创建关系"""
        created_count = 0
        failed_count = 0
        errors = []
        
        for i, rel_data in enumerate(relationships):
            try:
                from_entity = {"name": rel_data.get("subject", "")}
                to_entity = {"name": rel_data.get("object", "")}
                relation_type = rel_data.get("predicate", "RELATED_TO")
                properties = {k: v for k, v in rel_data.items() 
                            if k not in ["subject", "object", "predicate"]}
                
                if self.create_relationship_safe(from_entity, to_entity, relation_type, properties):
                    created_count += 1
                else:
                    failed_count += 1
                
                # 每100个关系记录一次进度
                if (i + 1) % 100 == 0:
                    logger.info(f"批量关系创建进度: {i + 1}/{len(relationships)}")
                    
            except Exception as e:
                failed_count += 1
                error_msg = f"创建关系失败 [{i}]: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            "total": len(relationships),
            "created": created_count,
            "failed": failed_count,
            "errors": errors
        }

# 创建全局Neo4j管理器实例
neo4j_manager = Neo4jManager()