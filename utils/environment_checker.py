"""
环境检查工具类
在项目启动时检查各项基础设施是否准备就绪
"""
import os
import logging
import sys
from typing import Dict, List, Tuple
from utils.config_loader import config_loader
from utils.database import mysql_manager, milvus_manager, neo4j_manager
from utils.model_manager import model_manager

logger = logging.getLogger(__name__)

class EnvironmentChecker:
    """环境检查器"""
    
    def __init__(self):
        self.check_results = {}
    
    def check_all(self) -> Tuple[bool, Dict[str, bool]]:
        """
        执行所有环境检查
        
        Returns:
            (是否全部通过, 各项检查结果)
        """
        logger.info("开始环境检查...")
        
        checks = [
            ("directories", self._check_directories),
            ("databases", self._check_databases),
            ("models", self._check_models),
            ("dependencies", self._check_dependencies)
        ]
        
        all_passed = True
        
        for check_name, check_func in checks:
            try:
                result = check_func()
                self.check_results[check_name] = result
                if not result:
                    all_passed = False
                logger.info(f"{check_name} 检查: {'通过' if result else '失败'}")
            except Exception as e:
                logger.error(f"{check_name} 检查异常: {e}")
                self.check_results[check_name] = False
                all_passed = False
        
        if all_passed:
            logger.info("所有环境检查通过，系统准备就绪！")
        else:
            logger.error("部分环境检查失败，请检查配置")
        
        return all_passed, self.check_results
    
    def _check_directories(self) -> bool:
        """检查必要的目录结构"""
        logger.info("检查目录结构...")
        
        required_dirs = [
            "uploads",
            "logs", 
            "models",
            "models/embedding",
            "models/ocr",
            "models/table_detection",
            "models/image_analysis",
            "models/chart_recognition"
        ]
        
        all_exists = True
        for dir_path in required_dirs:
            if not os.path.exists(dir_path):
                logger.info(f"创建目录: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)
            else:
                logger.debug(f"目录已存在: {dir_path}")
        
        return True
    
    def _check_databases(self) -> bool:
        """检查数据库连接和初始化"""
        logger.info("检查数据库连接...")
        
        # 检查MySQL
        try:
            mysql_manager.connect()
            logger.info("MySQL数据库连接正常")
            mysql_result = True
        except Exception as e:
            logger.error(f"MySQL数据库连接失败: {e}")
            mysql_result = False
        
        # 检查Milvus
        try:
            milvus_manager.connect()
            logger.info("Milvus向量数据库连接正常")
            milvus_result = True
        except Exception as e:
            logger.error(f"Milvus向量数据库连接失败: {e}")
            milvus_result = False
        
        # 检查Neo4j
        try:
            neo4j_manager.connect()
            logger.info("Neo4j图数据库连接正常")
            neo4j_result = True
        except Exception as e:
            logger.error(f"Neo4j图数据库连接失败: {e}")
            neo4j_result = False
        
        return mysql_result and milvus_result and neo4j_result
    
    def _check_models(self) -> bool:
        """检查模型是否准备就绪"""
        logger.info("检查模型状态...")
        
        model_types = ["embedding", "ocr", "table_detection", "image_analysis", "chart_recognition"]
        all_ready = True
        
        for model_type in model_types:
            if model_manager.check_model_availability(model_type):
                logger.info(f"{model_type} 模型已准备就绪")
            else:
                logger.info(f"{model_type} 模型不存在，开始下载...")
                if model_manager.download_model(model_type):
                    logger.info(f"{model_type} 模型下载完成")
                else:
                    logger.error(f"{model_type} 模型下载失败")
                    all_ready = False
        
        # 测试加载关键模型
        try:
            model_manager.load_embedding_model()
            logger.info("嵌入模型测试加载成功")
        except Exception as e:
            logger.error(f"嵌入模型测试加载失败: {e}")
            all_ready = False
        
        try:
            model_manager.load_ocr_model()
            logger.info("OCR模型测试加载成功")
        except Exception as e:
            logger.error(f"OCR模型测试加载失败: {e}")
            all_ready = False
        
        return all_ready
    
    def _check_dependencies(self) -> bool:
        """检查Python依赖"""
        logger.info("检查Python依赖...")
        
        # 包名到导入名的映射
        package_import_map = {
            "flask": "flask",
            "pymysql": "pymysql",
            "pymilvus": "pymilvus", 
            "neo4j": "neo4j",
            "paddleocr": "paddleocr",
            "sentence-transformers": "sentence_transformers",
            "transformers": "transformers",
            "torch": "torch",
            "PyYAML": "yaml",
            "requests": "requests",
            "Pillow": "PIL",
            "numpy": "numpy",
            "pandas": "pandas"
        }
        
        missing_packages = []
        
        for package, import_name in package_import_map.items():
            try:
                __import__(import_name)
                logger.debug(f"依赖包 {package} 已安装")
            except ImportError:
                logger.warning(f"缺少依赖包: {package}")
                missing_packages.append(package)
        
        if missing_packages:
            logger.error(f"缺少以下依赖包: {missing_packages}")
            logger.error("请运行: pip install -r requirements.txt")
            return False
        
        logger.info("所有依赖包检查通过")
        return True
    
    def generate_report(self) -> str:
        """生成环境检查报告"""
        report = "\n" + "="*50 + "\n"
        report += "环境检查报告\n"
        report += "="*50 + "\n"
        
        for check_name, result in self.check_results.items():
            status = "✅ 通过" if result else "❌ 失败"
            report += f"{check_name.upper()}: {status}\n"
        
        report += "="*50 + "\n"
        return report

# 全局环境检查器实例
environment_checker = EnvironmentChecker() 