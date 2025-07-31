"""
MySQL数据库管理器 - SQLAlchemy高性能版本
负责MySQL数据库的连接、查询和管理功能
解决了连接池、线程安全、事务管理等所有问题
"""
import os
import logging
import threading
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Union
from sqlalchemy import (
    create_engine, text, MetaData, inspect,
    Engine, Connection, Result
)
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError
from utils.config_loader import config_loader

logger = logging.getLogger(__name__)

class MySQLManager:
    """MySQL数据库管理器 - SQLAlchemy高性能实现"""
    
    def __init__(self):
        self.config = config_loader.get_db_config()["mysql"]
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self.Session: Optional[scoped_session] = None
        self._lock = threading.Lock()
        self._initialized = False
        
        # 初始化连接
        self._initialize()
    
    def _build_connection_url(self) -> str:
        """构建数据库连接URL"""
        return (
            f"mysql+pymysql://{self.config['username']}:{self.config['password']}"
            f"@{self.config['host']}:{self.config['port']}/{self.config['database']}"
            f"?charset={self.config['charset']}"
        )
    
    def _initialize(self) -> None:
        """初始化数据库引擎和会话"""
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:
                return
                
            try:
                # 构建连接URL
                database_url = self._build_connection_url()
                
                # 创建引擎，配置连接池
                self.engine = create_engine(
                    database_url,
                    # 连接池配置
                    poolclass=QueuePool,
                    pool_size=10,                    # ✅ 连接池基础大小
                    max_overflow=20,                 # ✅ 额外连接数
                    pool_timeout=30,                 # ✅ 获取连接超时
                    pool_recycle=3600,               # ✅ 连接回收时间(1小时)
                    pool_pre_ping=True,              # ✅ 连接前检测
                    
                    # 连接参数
                    connect_args={
                        "charset": self.config["charset"],
                        "autocommit": False,         # ✅ 禁用自动提交
                        "connect_timeout": 60,
                        "read_timeout": 30,
                        "write_timeout": 30,
                        "sql_mode": "STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO"
                    },
                    
                    # 其他配置
                    echo=False,                      # 生产环境关闭SQL日志
                    future=True                      # 使用SQLAlchemy 2.0样式
                )
                
                # 创建会话工厂
                self.SessionLocal = sessionmaker(
                    autocommit=False,               # ✅ 禁用自动提交
                    autoflush=False,                # ✅ 禁用自动刷新
                    bind=self.engine
                )
                
                # 创建线程安全的会话
                self.Session = scoped_session(self.SessionLocal)
                
                # 测试连接并创建数据库（如果需要）
                self._ensure_database_exists()
                
                # 初始化表结构
                self._init_database_tables()
                
                self._initialized = True
                logger.info("SQLAlchemy MySQL数据库管理器初始化成功")
                
            except Exception as e:
                logger.error(f"SQLAlchemy MySQL数据库管理器初始化失败: {e}")
                raise
    
    def _ensure_database_exists(self) -> None:
        """确保数据库存在，如果不存在则创建"""
        try:
            # 首先尝试连接到指定数据库
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("数据库连接成功")
                
        except SQLAlchemyError as e:
            if "Unknown database" in str(e):
                logger.info(f"数据库 {self.config['database']} 不存在，正在创建...")
                
                # 连接到MySQL服务器（不指定数据库）
                server_url = (
                    f"mysql+pymysql://{self.config['username']}:{self.config['password']}"
                    f"@{self.config['host']}:{self.config['port']}"
                    f"?charset={self.config['charset']}"
                )
                
                temp_engine = create_engine(server_url)
                with temp_engine.connect() as conn:
                    conn.execute(text(
                        f"CREATE DATABASE IF NOT EXISTS {self.config['database']} "
                        f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    ))
                    conn.commit()
                
                temp_engine.dispose()
                logger.info(f"数据库 {self.config['database']} 创建成功")
            else:
                raise
    
    def _init_database_tables(self) -> None:
        """初始化数据库表结构"""
        try:
            sql_file_path = "db.sql"
            if not os.path.exists(sql_file_path):
                logger.warning("数据库初始化脚本 db.sql 不存在")
                return
            
            # 检查表是否已存在
            inspector = inspect(self.engine)
            existing_tables = inspector.get_table_names()
            
            if 'files' in existing_tables:
                logger.info("数据库表已存在，跳过初始化")
                return
            
            # 读取并执行SQL脚本
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            # 分割SQL语句并执行
            sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
            
            with self.engine.begin() as conn:  # ✅ 使用事务
                for statement in sql_statements:
                    if statement and not statement.startswith('--') and not statement.startswith('/*'):
                        try:
                            conn.execute(text(statement))
                        except Exception as e:
                            if "already exists" not in str(e).lower():
                                logger.warning(f"执行SQL语句失败: {statement[:50]}... Error: {e}")
            
            logger.info("数据库表结构初始化完成")
            
        except Exception as e:
            logger.error(f"初始化数据库表失败: {e}")
    
    @contextmanager
    def get_session(self):
        """获取数据库会话的上下文管理器"""
        session = self.Session()
        try:
            yield session
        except Exception as e:
            session.rollback()  # ✅ 异常时回滚
            logger.error(f"数据库会话错误: {e}")
            raise
        finally:
            session.close()    # ✅ 确保会话关闭
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = self.engine.connect()
        try:
            yield conn
        except Exception as e:
            logger.error(f"数据库连接错误: {e}")
            raise
        finally:
            conn.close()
    
    def execute_query(self, query: str, params: Union[Dict, tuple, None] = None) -> List[Dict[str, Any]]:
        """
        执行查询操作（兼容原有API）
        
        Args:
            query: SQL查询语句
            params: 查询参数（支持字典或元组格式）
            
        Returns:
            查询结果列表
        """
        try:
            with self.get_connection() as conn:
                # 处理参数格式
                if isinstance(params, tuple):
                    # 将位置参数转换为命名参数
                    param_dict = {f"param_{i}": val for i, val in enumerate(params)}
                    # 替换查询中的 %s 为 :param_0, :param_1 等
                    formatted_query = query
                    for i in range(len(params)):
                        formatted_query = formatted_query.replace('%s', f':param_{i}', 1)
                    result = conn.execute(text(formatted_query), param_dict)
                else:
                    result = conn.execute(text(query), params or {})
                
                # 将结果转换为字典列表
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
                
        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            raise
    
    def execute_update(self, query: str, params: Union[Dict, tuple, None] = None) -> int:
        """
        执行更新操作（兼容原有API）
        
        Args:
            query: SQL更新语句
            params: 更新参数（支持字典或元组格式）
            
        Returns:
            受影响的行数
        """
        try:
            with self.engine.begin() as conn:  # ✅ 自动事务管理
                # 处理参数格式
                if isinstance(params, tuple):
                    param_dict = {f"param_{i}": val for i, val in enumerate(params)}
                    formatted_query = query
                    for i in range(len(params)):
                        formatted_query = formatted_query.replace('%s', f':param_{i}', 1)
                    result = conn.execute(text(formatted_query), param_dict)
                else:
                    result = conn.execute(text(query), params or {})
                
                return result.rowcount
                
        except Exception as e:
            logger.error(f"更新执行失败: {e}")
            raise
    
    def execute_many(self, query: str, params_list: List[Union[Dict, tuple]]) -> int:
        """批量执行操作"""
        try:
            with self.engine.begin() as conn:
                total_affected = 0
                for params in params_list:
                    if isinstance(params, tuple):
                        param_dict = {f"param_{i}": val for i, val in enumerate(params)}
                        formatted_query = query
                        for i in range(len(params)):
                            formatted_query = formatted_query.replace('%s', f':param_{i}', 1)
                        result = conn.execute(text(formatted_query), param_dict)
                    else:
                        result = conn.execute(text(query), params or {})
                    total_affected += result.rowcount
                
                return total_affected
                
        except Exception as e:
            logger.error(f"批量操作执行失败: {e}")
            raise
    
    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        with self.get_session() as session:
            try:
                yield session
                session.commit()  # ✅ 成功时提交
            except Exception as e:
                session.rollback()  # ✅ 失败时回滚
                logger.error(f"事务执行失败: {e}")
                raise
    
    def execute_in_transaction(self, operations: List[Dict[str, Any]]) -> bool:
        """在事务中执行多个操作"""
        try:
            with self.transaction() as session:
                for operation in operations:
                    query = operation.get('query')
                    params = operation.get('params', {})
                    session.execute(text(query), params)
                return True
        except Exception as e:
            logger.error(f"事务操作失败: {e}")
            return False
    
    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        if not self.engine:
            return {}
        
        pool = self.engine.pool
        info = {
            "pool_class": pool.__class__.__name__,
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow()
        }
        
        # 添加可选的属性（如果存在）
        if hasattr(pool, 'invalid'):
            info["invalid"] = pool.invalid()
        
        return info
    
    def check_connection(self) -> bool:
        """检查数据库连接状态"""
        try:
            with self.get_connection() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"数据库连接检查失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """断开数据库连接（兼容原有API）"""
        if self.Session:
            self.Session.remove()
        if self.engine:
            self.engine.dispose()
        logger.info("SQLAlchemy数据库连接已断开")
    
    def connect(self) -> None:
        """连接数据库（兼容原有API）"""
        if not self._initialized:
            self._initialize()
        logger.info("SQLAlchemy数据库连接已建立")
    
    @property
    def implementation(self) -> str:
        """获取当前使用的实现方式"""
        return "sqlalchemy"
    
    @property
    def is_sqlalchemy(self) -> bool:
        """检查是否使用SQLAlchemy实现"""
        return True

# 创建MySQL管理器实例
mysql_manager = MySQLManager()