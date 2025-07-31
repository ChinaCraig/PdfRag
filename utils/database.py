"""
数据库连接工具统一入口
提供MySQL、Milvus和Neo4j数据库管理器的统一导入接口
保持向后兼容性，同时支持模块化的数据库管理
"""

# 导入各个数据库管理器
from utils.mysql_manager import mysql_manager, MySQLManager
from utils.milvus_manager import milvus_manager, MilvusManager  
from utils.neo4j_manager import neo4j_manager, Neo4jManager

# 导出所有管理器类和实例，保持向后兼容
__all__ = [
    'mysql_manager', 'MySQLManager',
    'milvus_manager', 'MilvusManager', 
    'neo4j_manager', 'Neo4jManager'
] 