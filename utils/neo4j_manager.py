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
        if not self.driver:
            self.connect()
        
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def create_entity(self, entity_type: str, properties: Dict[str, Any]) -> None:
        """创建实体节点"""
        query = f"CREATE (n:{entity_type} $properties)"
        self.execute_query(query, {"properties": properties})
    
    def create_relationship(self, from_entity: Dict, to_entity: Dict, 
                          relation_type: str, properties: Dict = None) -> None:
        """创建关系"""
        query = """
        MATCH (a {name: $from_name}), (b {name: $to_name})
        CREATE (a)-[r:$relation_type $properties]->(b)
        """
        params = {
            "from_name": from_entity["name"],
            "to_name": to_entity["name"],
            "relation_type": relation_type,
            "properties": properties or {}
        }
        self.execute_query(query, params)

# 创建全局Neo4j管理器实例
neo4j_manager = Neo4jManager()