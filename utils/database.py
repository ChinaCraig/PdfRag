"""
数据库连接工具类
包括MySQL、Milvus和Neo4j数据库的连接管理
"""
import os
import pymysql
import pymysql.cursors
from pymilvus import connections, db, Collection, FieldSchema, CollectionSchema, DataType
from neo4j import GraphDatabase
import logging
from typing import Optional, List, Dict, Any
from utils.config_loader import config_loader

logger = logging.getLogger(__name__)

class MySQLManager:
    """MySQL数据库管理器"""
    
    def __init__(self):
        self.connection = None
        self.config = config_loader.get_db_config()["mysql"]
    
    def connect(self) -> None:
        """连接到MySQL数据库"""
        try:
            # 先尝试连接到指定数据库
            try:
                self.connection = pymysql.connect(
                    host=self.config["host"],
                    port=self.config["port"],
                    user=self.config["username"],
                    password=self.config["password"],
                    database=self.config["database"],
                    charset=self.config["charset"],
                    autocommit=True,
                    cursorclass=pymysql.cursors.DictCursor,
                    connect_timeout=60,
                    read_timeout=30,
                    write_timeout=30,
                    sql_mode="STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO"
                )
                logger.info("MySQL数据库连接成功")
            except pymysql.MySQLError as db_error:
                if "Unknown database" in str(db_error):
                    # 数据库不存在，先连接到MySQL服务器创建数据库
                    logger.info(f"数据库 {self.config['database']} 不存在，正在创建...")
                    temp_connection = pymysql.connect(
                        host=self.config["host"],
                        port=self.config["port"],
                        user=self.config["username"],
                        password=self.config["password"],
                        charset=self.config["charset"],
                        autocommit=True,
                        cursorclass=pymysql.cursors.DictCursor,
                        connect_timeout=60
                    )
                    
                    with temp_connection.cursor() as cursor:
                        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    temp_connection.close()
                    
                    # 重新连接到新创建的数据库
                    self.connection = pymysql.connect(
                        host=self.config["host"],
                        port=self.config["port"],
                        user=self.config["username"],
                        password=self.config["password"],
                        database=self.config["database"],
                        charset=self.config["charset"],
                        autocommit=True,
                        cursorclass=pymysql.cursors.DictCursor,
                        connect_timeout=60,
                        read_timeout=30,
                        write_timeout=30,
                        sql_mode="STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO"
                    )
                    logger.info(f"数据库 {self.config['database']} 创建成功并连接")
                    # 创建数据库后需要初始化表结构
                    self._init_database_tables()
                else:
                    raise db_error
            
            # 检查表是否存在，如果不存在则创建
            self._check_and_create_tables()
                    
        except Exception as e:
            logger.error(f"MySQL数据库连接失败: {e}")
            raise
    
    def _check_and_create_tables(self) -> None:
        """检查并创建必要的表"""
        try:
            with self.connection.cursor() as cursor:
                # 检查files表是否存在
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.tables 
                    WHERE table_schema = %s AND table_name = 'files'
                """, (self.config["database"],))
                
                result = cursor.fetchone()
                if result['count'] == 0:
                    logger.info("数据库表不存在，正在初始化...")
                    self._init_database_tables()
                    
        except Exception as e:
            logger.warning(f"检查数据库表失败: {e}")
    
    def _init_database_tables(self) -> None:
        """初始化数据库表结构"""
        try:
            # 读取并执行SQL脚本
            sql_file_path = "db.sql"
            if not os.path.exists(sql_file_path):
                logger.warning("数据库初始化脚本 db.sql 不存在")
                return
                
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            # 分割SQL语句并执行
            sql_statements = sql_content.split(';')
            
            with self.connection.cursor() as cursor:
                for statement in sql_statements:
                    statement = statement.strip()
                    if statement and not statement.startswith('--') and not statement.startswith('/*'):
                        try:
                            cursor.execute(statement)
                        except Exception as e:
                            # 忽略一些可预期的错误（如表已存在等）
                            if "already exists" not in str(e).lower():
                                logger.warning(f"执行SQL语句失败: {statement[:50]}... Error: {e}")
            
            logger.info("数据库表结构初始化完成")
            
        except Exception as e:
            logger.error(f"初始化数据库表失败: {e}")
    
    def disconnect(self) -> None:
        """断开数据库连接"""
        if self.connection:
            self.connection.close()
            logger.info("MySQL数据库连接已断开")
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """
        执行查询
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            查询结果列表
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not self.connection:
                    self.connect()
                
                # 检查连接是否还活着
                if not self._is_connection_alive():
                    logger.warning("MySQL连接已断开，正在重连...")
                    self.connect()
                
                with self.connection.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(query, params)
                    return cursor.fetchall()
                    
            except (pymysql.Error, pymysql.OperationalError, pymysql.InterfaceError) as e:
                logger.warning(f"MySQL查询失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # 重新连接
                    try:
                        self.connect()
                    except Exception as reconnect_error:
                        logger.error(f"重连失败: {reconnect_error}")
                        continue
                else:
                    logger.error(f"MySQL查询最终失败: {e}")
                    raise
        
        return []
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """
        执行更新操作
        
        Args:
            query: SQL更新语句
            params: 更新参数
            
        Returns:
            受影响的行数
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not self.connection:
                    self.connect()
                
                # 检查连接是否还活着
                if not self._is_connection_alive():
                    logger.warning("MySQL连接已断开，正在重连...")
                    self.connect()
                
                with self.connection.cursor() as cursor:
                    return cursor.execute(query, params)
                    
            except (pymysql.Error, pymysql.OperationalError, pymysql.InterfaceError) as e:
                logger.warning(f"MySQL更新失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # 重新连接
                    try:
                        self.connect()
                    except Exception as reconnect_error:
                        logger.error(f"重连失败: {reconnect_error}")
                        continue
                else:
                    logger.error(f"MySQL更新最终失败: {e}")
                    raise
        
        return 0
    
    def _is_connection_alive(self) -> bool:
        """检查连接是否还活着"""
        try:
            if not self.connection:
                return False
            
            # 使用ping方法检查连接，更加高效
            self.connection.ping(reconnect=False)
            return True
        except Exception as e:
            logger.debug(f"MySQL连接检查失败: {e}")
            return False

class MilvusManager:
    """Milvus向量数据库管理器"""
    
    def __init__(self):
        self.collection = None
        self.config = config_loader.get_db_config()["milvus"]
        self.model_config = config_loader.get_model_config()["embedding"]
    
    def connect(self) -> None:
        """连接到Milvus数据库"""
        try:
            connections.connect(
                alias="default",
                host=self.config["host"],
                port=self.config["port"]
            )
            logger.info("Milvus向量数据库连接成功")
            self._init_collection()
        except Exception as e:
            logger.error(f"Milvus向量数据库连接失败: {e}")
            raise
    
    def _init_collection(self) -> None:
        """初始化集合"""
        try:
            # 检查数据库是否存在，不存在则创建
            database_name = self.config["database"]
            existing_databases = db.list_database()
            
            if database_name not in existing_databases:
                db.create_database(database_name)
                logger.info(f"创建Milvus数据库: {database_name}")
            else:
                logger.info(f"Milvus数据库已存在: {database_name}")
            
            # 使用指定数据库
            db.using_database(database_name)
            
            # 定义集合schema，从配置文件读取向量维度
            embedding_dim = self.model_config["dimensions"]
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
                FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=65535)
            ]
            
            schema = CollectionSchema(fields, "PDF文档向量存储集合")
            
            # 创建或获取集合
            collection_name = self.config["collection"]
            from pymilvus import utility
            
            # 检查集合是否存在，如果存在则检查维度是否匹配
            if utility.has_collection(collection_name):
                existing_collection = Collection(collection_name)
                # 获取现有集合的schema
                existing_schema = existing_collection.schema
                existing_embedding_field = None
                for field in existing_schema.fields:
                    if field.name == "embedding":
                        existing_embedding_field = field
                        break
                
                # 如果维度不匹配，删除旧集合
                if existing_embedding_field and existing_embedding_field.params.get('dim') != embedding_dim:
                    logger.info(f"Milvus集合维度不匹配({existing_embedding_field.params.get('dim')} != {embedding_dim})，删除旧集合: {collection_name}")
                    utility.drop_collection(collection_name)
                    self.collection = Collection(collection_name, schema)
                    logger.info(f"重新创建Milvus集合: {collection_name} (维度: {embedding_dim})")
                else:
                    self.collection = existing_collection
                    logger.info(f"Milvus集合已存在且维度正确: {collection_name} (维度: {embedding_dim})")
            else:
                self.collection = Collection(collection_name, schema)
                logger.info(f"创建Milvus集合: {collection_name} (维度: {embedding_dim})")
            
            # 创建索引
            index_params = {
                "metric_type": "IP",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            
            if not self.collection.has_index():
                self.collection.create_index("embedding", index_params)
                logger.info("创建Milvus索引")
            
            # 加载集合
            self.collection.load()
            
        except Exception as e:
            logger.error(f"Milvus集合初始化失败: {e}")
            raise
    
    def insert_vectors(self, data: List[Dict[str, Any]]) -> None:
        """插入向量数据"""
        if not self.collection:
            raise RuntimeError("Milvus集合未初始化")
        
        self.collection.insert(data)
        self.collection.flush()
    
    def has_data(self) -> bool:
        """检查集合是否有数据"""
        try:
            if not self.collection:
                return False
            return self.collection.num_entities > 0
        except Exception as e:
            logger.error(f"检查Milvus数据失败: {e}")
            return False
    
    def has_collection(self) -> bool:
        """检查集合是否存在"""
        try:
            from pymilvus import utility
            collection_name = self.config["collection"]
            return utility.has_collection(collection_name)
        except Exception as e:
            logger.error(f"检查Milvus集合失败: {e}")
            return False
    
    def create_collection(self) -> None:
        """创建集合（如果不存在）"""
        try:
            if not self.has_collection():
                self._init_collection()
                logger.info("Milvus集合创建成功")
            else:
                # 即使集合存在，也需要初始化连接
                self._init_collection()
                logger.info("Milvus集合已存在，完成初始化")
        except Exception as e:
            logger.error(f"创建Milvus集合失败: {e}")
            raise
    
    def search_vectors(self, query_vector: List[float], top_k: int = 5) -> List[Dict]:
        """搜索相似向量"""
        if not self.collection:
            raise RuntimeError("Milvus集合未初始化")
        
        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        results = self.collection.search(
            [query_vector],
            "embedding",
            search_params,
            limit=top_k,
            output_fields=["file_id", "chunk_id", "content", "metadata"]
        )
        
        return [
            {
                "id": hit.id,
                "score": hit.score,
                "file_id": hit.entity.get("file_id"),
                "chunk_id": hit.entity.get("chunk_id"),
                "content": hit.entity.get("content"),
                "metadata": hit.entity.get("metadata")
            }
            for hit in results[0]
        ]

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

# 全局数据库管理器实例
mysql_manager = MySQLManager()
milvus_manager = MilvusManager()
neo4j_manager = Neo4jManager() 