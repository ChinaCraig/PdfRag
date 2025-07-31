"""
Milvus向量数据库管理器
负责向量数据的存储、搜索和管理功能
"""
import logging
from typing import List, Dict, Any
from pymilvus import connections, db, Collection, FieldSchema, CollectionSchema, DataType
from utils.config_loader import config_loader

logger = logging.getLogger(__name__)

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

# 创建全局Milvus管理器实例
milvus_manager = MilvusManager()