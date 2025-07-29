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
from utils.hardware_detector import hardware_detector

logger = logging.getLogger(__name__)

class EnvironmentChecker:
    """环境检查器"""
    
    def __init__(self):
        self.check_results = {}
        self.hardware_info = {}
        self.recommended_config = {}
    
    def check_all(self) -> Tuple[bool, Dict[str, bool]]:
        """
        执行所有环境检查
        
        Returns:
            (是否全部通过, 各项检查结果)
        """
        logger.info("开始环境检查...")
        
        checks = [
            ("hardware", self._check_hardware),
            ("directories", self._check_directories),
            ("databases", self._check_databases),
            ("models", self._check_models),
            ("dependencies", self._check_dependencies),
            ("requirements", self._check_hardware_requirements)
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
    
    def _check_hardware(self) -> bool:
        """检查硬件环境"""
        logger.info("检查硬件环境...")
        
        try:
            # 执行硬件检测
            self.hardware_info = hardware_detector.detect_all()
            
            # 获取推荐配置
            self.recommended_config = hardware_detector.get_recommended_config()
            
            # 输出硬件信息摘要
            cpu_info = self.hardware_info.get("cpu", {})
            memory_info = self.hardware_info.get("memory", {})
            gpu_info = self.hardware_info.get("gpu", {})
            
            logger.info(f"CPU: {cpu_info.get('logical_cores', 'Unknown')}核心")
            logger.info(f"内存: {memory_info.get('total_gb', 'Unknown')}GB")
            logger.info(f"GPU: {'是' if gpu_info.get('cuda_available', False) else '否'}")
            logger.info(f"性能评分: {self.hardware_info.get('performance_score', 0)}/100")
            
            # 应用推荐配置到模型配置
            self._apply_hardware_recommendations()
            
            return True
            
        except Exception as e:
            logger.error(f"硬件检测失败: {e}")
            return False
    
    def _apply_hardware_recommendations(self) -> None:
        """应用硬件推荐配置到系统配置"""
        try:
            if not self.recommended_config:
                return
            
            # 获取当前模型配置
            model_config = config_loader.get_model_config()
            
            # 更新GPU配置
            gpu_acceleration = self.recommended_config.get("gpu_acceleration", False)
            if model_config.get("gpu_acceleration") != gpu_acceleration:
                logger.info(f"根据硬件配置调整GPU加速: {gpu_acceleration}")
                # 这里可以动态更新配置，或者生成建议
            
            # 记录处理模式建议
            processing_mode = self.recommended_config.get("processing_mode", "conservative")
            batch_size = self.recommended_config.get("batch_size", 1)
            max_workers = self.recommended_config.get("max_workers", 1)
            
            logger.info(f"推荐处理模式: {processing_mode}")
            logger.info(f"推荐批处理大小: {batch_size}")
            logger.info(f"推荐最大工作线程: {max_workers}")
            
        except Exception as e:
            logger.warning(f"应用硬件建议失败: {e}")
    
    def _check_hardware_requirements(self) -> bool:
        """检查是否满足最低硬件要求"""
        logger.info("检查硬件要求...")
        
        # 定义最低硬件要求
        min_requirements = {
            "min_cpu_cores": 2,
            "min_memory_gb": 4,
            "min_available_memory_gb": 2
        }
        
        try:
            # 检查硬件要求
            meets_requirements, issues = hardware_detector.check_requirements(min_requirements)
            
            if meets_requirements:
                logger.info("硬件要求检查通过")
                return True
            else:
                logger.error("硬件要求检查失败:")
                for issue in issues:
                    logger.error(f"  - {issue}")
                
                # 给出建议
                logger.info("建议:")
                if self.hardware_info.get("performance_score", 0) < 30:
                    logger.info("  - 系统性能较低，建议升级硬件或使用轻量化模式")
                    logger.info("  - 考虑关闭GPU加速，使用CPU模式")
                    logger.info("  - 减少并发处理数量")
                
                return False
                
        except Exception as e:
            logger.error(f"硬件要求检查异常: {e}")
            return False
    
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
        
        model_types = ["embedding", "ocr"]
        all_ready = True
        
        # 根据硬件性能决定是否预加载模型
        performance_score = self.hardware_info.get("performance_score", 50)
        should_preload = performance_score > 60  # 性能好的时候才预加载
        
        for model_type in model_types:
            try:
                logger.info(f"检查 {model_type} 模型配置...")
                # 这里只检查模型配置，不实际加载
                if model_type == "embedding":
                    model_config = config_loader.get_nested_value("model.embedding", {})
                    model_path = model_config.get("model_path", "./models/embedding")
                    if os.path.exists(model_path):
                        logger.info(f"{model_type} 模型本地路径存在")
                    else:
                        logger.info(f"{model_type} 模型将在首次使用时下载")
                elif model_type == "ocr":
                    # OCR模型由PaddleOCR自动管理
                    logger.info(f"{model_type} 模型配置正常")
                    
                logger.info(f"{model_type} 模型检查通过")
            except Exception as e:
                logger.error(f"{model_type} 模型检查失败: {e}")
                all_ready = False
        
        # 根据硬件性能决定是否测试加载关键模型
        if should_preload:
            logger.info("系统性能良好，进行模型预加载测试...")
        
            # 测试加载关键模型
            try:
                logger.info("测试加载嵌入模型...")
                model_manager.load_embedding_model()
                logger.info("嵌入模型测试加载成功")
            except Exception as e:
                logger.error(f"嵌入模型测试加载失败: {e}")
                # 如果是网络连接问题，不标记为失败
                if "huggingface.co" in str(e) or "SSL" in str(e) or "ConnectionPool" in str(e):
                    logger.warning("网络连接问题，跳过模型预加载测试（将在使用时重试）")
                elif performance_score < 40:
                    logger.warning("系统性能较低，建议使用轻量化模型")
                else:
                    all_ready = False
            
            try:
                logger.info("测试加载OCR模型...")
                model_manager.load_ocr_model()
                logger.info("OCR模型测试加载成功")
            except Exception as e:
                logger.error(f"OCR模型测试加载失败: {e}")
                # OCR模型通常是本地加载，失败则标记为失败
                all_ready = False
        else:
            logger.info("系统性能一般，跳过模型预加载测试（将在使用时加载）")
        
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
            "pandas": "pandas",
            "psutil": "psutil"  # 新增硬件检测依赖
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
        report_lines = [
            "\n" + "="*60,
            "系统环境检查报告",
            "="*60,
            ""
        ]
        
        # 基本检查结果
        report_lines.append("📋 基础环境检查:")
        for check_name, result in self.check_results.items():
            if check_name != "hardware":  # 硬件信息单独处理
                status = "✅ 通过" if result else "❌ 失败"
                check_name_zh = {
                    "directories": "目录结构",
                    "databases": "数据库连接", 
                    "models": "模型状态",
                    "dependencies": "依赖包",
                    "requirements": "硬件要求"
                }.get(check_name, check_name)
                report_lines.append(f"  {check_name_zh}: {status}")
        report_lines.append("")
        
        # 硬件检测报告
        if self.hardware_info:
            hardware_report = hardware_detector.generate_report()
            report_lines.append(hardware_report)
        
        # 推荐配置
        if self.recommended_config:
            report_lines.extend([
                "⚙️ 推荐系统配置:",
                f"  GPU加速: {'启用' if self.recommended_config.get('gpu_acceleration', False) else '禁用'}",
                f"  处理模式: {self.recommended_config.get('processing_mode', 'conservative')}",
                f"  批处理大小: {self.recommended_config.get('batch_size', 1)}",
                f"  最大工作线程: {self.recommended_config.get('max_workers', 1)}",
                f"  模型缓存: {'启用' if self.recommended_config.get('model_cache_enabled', True) else '禁用'}",
                ""
            ])
        
        # 总体状态
        all_passed = all(self.check_results.values())
        performance_score = self.hardware_info.get("performance_score", 0)
        
        report_lines.extend([
            "🎯 系统状态总结:",
            f"  环境检查: {'✅ 全部通过' if all_passed else '❌ 存在问题'}",
            f"  硬件性能: {performance_score}/100",
        ])
        
        if performance_score < 30:
            report_lines.append("  建议: 系统性能较低，建议使用轻量化模式")
        elif performance_score > 80:
            report_lines.append("  建议: 系统性能优秀，可以启用高级功能")
        else:
            report_lines.append("  建议: 系统性能适中，使用平衡模式")
        
        report_lines.extend([
            "",
            "="*60
        ])
        
        return "\n".join(report_lines)
    
    def get_startup_recommendations(self) -> List[str]:
        """获取启动建议"""
        recommendations = []
        
        if not self.hardware_info:
            return ["请先运行硬件检测"]
        
        performance_score = self.hardware_info.get("performance_score", 0)
        cpu_info = self.hardware_info.get("cpu", {})
        memory_info = self.hardware_info.get("memory", {})
        gpu_info = self.hardware_info.get("gpu", {})
        
        # 基于硬件性能的建议
        if performance_score < 30:
            recommendations.extend([
                "系统性能较低，建议:",
                "  - 启用轻量化处理模式",
                "  - 关闭GPU加速，使用CPU模式", 
                "  - 减少并发文件处理数量",
                "  - 考虑使用更小的模型"
            ])
        elif performance_score > 80:
            recommendations.extend([
                "系统性能优秀，建议:",
                "  - 启用GPU加速（如可用）",
                "  - 启用并行处理优化",
                "  - 启用模型预加载",
                "  - 可以处理大批量文件"
            ])
        
        # CPU建议
        logical_cores = cpu_info.get("logical_cores", 1)
        if logical_cores < 4:
            recommendations.append("CPU核心数较少，建议限制并发处理数量")
        
        # 内存建议  
        total_memory = memory_info.get("total_gb", 0)
        if total_memory < 8:
            recommendations.append("内存较少，建议减少模型缓存和批处理大小")
        
        # GPU建议
        if not gpu_info.get("cuda_available", False):
            recommendations.append("未检测到CUDA GPU，将使用CPU模式")
        
        return recommendations

# 全局环境检查器实例
environment_checker = EnvironmentChecker() 