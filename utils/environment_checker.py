"""
环境检查器 - 重构版
检查项目启动必需的环境条件
"""
import os
import sys
import logging
import requests
from typing import List, Dict, Any

from utils.config_loader import config_loader

logger = logging.getLogger(__name__)

class EnvironmentChecker:
    """环境检查器 - 重构版"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.success_messages = []
    
    def check_all(self) -> bool:
        """执行所有环境检查"""
        self.errors.clear()
        self.warnings.clear()
        self.success_messages.clear()
        
        logger.info("🔍 开始环境检查...")
        
        checks = [
            ("目录结构", self._check_directories),
            ("Python依赖", self._check_python_dependencies),
            ("MySQL连接", self._check_mysql_connection),
            ("Milvus连接", self._check_milvus_connection),
            ("Neo4j连接", self._check_neo4j_connection),
            ("模型目录", self._check_model_directories),
            ("DeepSeek API", self._check_deepseek_api),
            ("OCR模型预加载", self._check_and_preload_ocr)  # 新增OCR预加载检查
        ]
        
        all_passed = True
        for check_name, check_func in checks:
            try:
                result = check_func()
                if result:
                    self.success_messages.append(f"✅ {check_name}: 正常")
                    logger.info(f"✅ {check_name}: 检查通过")
                else:
                    all_passed = False
                    logger.error(f"❌ {check_name}: 检查失败")
            except Exception as e:
                all_passed = False
                error_msg = f"{check_name}检查异常: {e}"
                self.errors.append(error_msg)
                logger.error(f"❌ {error_msg}")
        
        if all_passed:
            logger.info("🎉 所有环境检查通过！")
        else:
            logger.error("⚠️ 部分环境检查失败，请检查配置")
        
        return all_passed
    
    def _check_directories(self) -> bool:
        """检查必需的目录结构"""
        try:
            required_dirs = [
                "uploads",
                "logs", 
                "models",
                "config",
                "templates"
            ]
            
            for dir_name in required_dirs:
                if not os.path.exists(dir_name):
                    os.makedirs(dir_name, exist_ok=True)
                    self.warnings.append(f"目录不存在，已创建: {dir_name}")
            
            return True
            
        except Exception as e:
            self.errors.append(f"目录检查失败: {e}")
            return False
    
    def _check_python_dependencies(self) -> bool:
        """检查Python依赖包"""
        try:
            required_packages = [
                ("flask", "flask"),
                ("pymysql", "pymysql"),
                ("pymilvus", "pymilvus"),
                ("neo4j", "neo4j"),
                ("sentence_transformers", "sentence_transformers"),
                ("paddleocr", "paddleocr"),
                ("PyMuPDF", "fitz"),
                ("requests", "requests"),
                ("pyyaml", "yaml"),
                ("pillow", "PIL")
            ]
            
            missing_packages = []
            for package, import_name in required_packages:
                try:
                    __import__(import_name)
                except ImportError:
                    missing_packages.append(package)
            
            if missing_packages:
                self.errors.append(f"缺少必需的Python包: {', '.join(missing_packages)}")
                self.errors.append("请运行: pip install -r requirements.txt")
                return False
            
            return True
            
        except Exception as e:
            self.errors.append(f"Python依赖检查失败: {e}")
            return False
    
    def _check_mysql_connection(self) -> bool:
        """检查MySQL数据库连接"""
        try:
            # 延迟导入数据库模块
            from utils.database import mysql_manager
            
            mysql_manager.connect()
            # 测试基本查询
            mysql_manager.execute_query("SELECT 1")
            mysql_manager.disconnect()
            return True
            
        except Exception as e:
            self.errors.append(f"MySQL连接失败: {e}")
            self.errors.append("请检查数据库配置和网络连接")
            return False
    
    def _check_milvus_connection(self) -> bool:
        """检查Milvus向量数据库连接"""
        try:
            # 延迟导入数据库模块
            from utils.database import milvus_manager
            
            milvus_manager.connect()
            # 检查集合是否存在，不存在则创建
            if not milvus_manager.has_collection():
                milvus_manager.create_collection()
                self.warnings.append("Milvus集合不存在，已自动创建")
            
            return True
            
        except Exception as e:
            self.errors.append(f"Milvus连接失败: {e}")
            self.errors.append("请检查Milvus服务状态和网络连接")
            return False
    
    def _check_neo4j_connection(self) -> bool:
        """检查Neo4j图数据库连接"""
        try:
            # 延迟导入数据库模块
            from utils.database import neo4j_manager
            
            neo4j_manager.connect()
            # 测试基本查询
            neo4j_manager.execute_query("RETURN 1 as test")
            neo4j_manager.disconnect()
            return True
            
        except Exception as e:
            self.errors.append(f"Neo4j连接失败: {e}")
            self.errors.append("请检查Neo4j服务状态和认证信息")
            return False
    
    def _check_model_directories(self) -> bool:
        """检查模型目录"""
        try:
            model_config = config_loader.get_model_config()
            
            # 检查嵌入模型目录
            embedding_path = model_config["embedding"]["model_path"]
            if not os.path.exists(embedding_path):
                os.makedirs(embedding_path, exist_ok=True)
                self.warnings.append(f"嵌入模型目录不存在，已创建: {embedding_path}")
                self.warnings.append("768维嵌入模型将在首次使用时自动下载")
            
            # 检查OCR模型目录
            ocr_path = model_config["ocr"]["model_path"]
            if not os.path.exists(ocr_path):
                os.makedirs(ocr_path, exist_ok=True)
                self.warnings.append(f"OCR模型目录不存在，已创建: {ocr_path}")
            
            return True
            
        except Exception as e:
            self.errors.append(f"模型目录检查失败: {e}")
            return False
    
    def _check_deepseek_api(self) -> bool:
        """检查DeepSeek API连接"""
        try:
            model_config = config_loader.get_model_config()
            llm_config = model_config["llm"]
            
            api_key = llm_config["api_key"]
            api_url = llm_config["api_url"]
            
            if not api_key or api_key == "your-api-key-here":
                self.errors.append("DeepSeek API密钥未配置")
                self.errors.append("请在config/model.yaml中设置正确的API密钥")
                return False
            
            # 简单测试API连接
            import requests
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 发送简单的测试请求
            test_data = {
                "model": llm_config["model_name"],
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10
            }
            
            response = requests.post(
                f"{api_url}/chat/completions",
                headers=headers,
                json=test_data,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("DeepSeek API连接正常")
                return True
            else:
                self.errors.append(f"DeepSeek API测试失败: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.errors.append(f"DeepSeek API检查失败: {e}")
            return False
    
    def _check_and_preload_ocr(self) -> bool:
        """检查并预加载OCR模型"""
        try:
            logger.info("🔍 开始检查OCR模型...")
            
            # 检查PaddleOCR默认模型目录
            paddleocr_dir = os.path.expanduser("~/.paddleocr/")
            models_dir = os.path.join(paddleocr_dir, "whl")
            
            # 检查是否有模型文件
            has_models = False
            if os.path.exists(models_dir):
                for root, dirs, files in os.walk(models_dir):
                    # 查找.pdmodel文件（PaddlePaddle模型文件）
                    if any(f.endswith('.pdmodel') for f in files):
                        has_models = True
                        break
            
            if not has_models:
                logger.warning("⚠️ PaddleOCR模型文件不存在，首次使用时将自动下载")
                logger.info("🔄 开始预加载OCR模型（首次下载可能需要几分钟）...")
                
                # 创建临时图像进行OCR测试，触发模型下载
                import tempfile
                from PIL import Image
                import io
                
                # 创建一个简单的测试图像
                img = Image.new('RGB', (100, 50), color='white')
                # 添加一些简单文字（用于OCR测试）
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(img)
                try:
                    # 尝试使用默认字体
                    draw.text((10, 10), "Test", fill='black')
                except:
                    # 如果字体加载失败，直接绘制简单形状
                    draw.rectangle([10, 10, 90, 40], outline='black', width=2)
                
                # 保存临时图像
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                    img.save(tmp_file.name)
                    temp_image_path = tmp_file.name
                
                try:
                    # 导入并初始化PaddleOCR（这会触发模型下载）
                    from paddleocr import PaddleOCR
                    
                    logger.info("📥 PaddleOCR模型下载中，请稍候...")
                    
                    # 创建OCR实例（会自动下载模型）
                    ocr = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=False, show_log=False)
                    
                    # 测试OCR功能
                    logger.info("🧪 测试OCR功能...")
                    results = ocr.ocr(temp_image_path, cls=True)
                    
                    logger.info("✅ OCR模型预加载成功")
                    self.success_messages.append("OCR模型已预加载并测试通过")
                    
                    # 清理临时文件
                    if os.path.exists(temp_image_path):
                        os.unlink(temp_image_path)
                    
                    return True
                    
                except Exception as e:
                    # 清理临时文件
                    if os.path.exists(temp_image_path):
                        os.unlink(temp_image_path)
                    
                    logger.error(f"❌ OCR模型预加载失败: {e}")
                    self.errors.append(f"OCR模型预加载失败: {e}")
                    self.errors.append("请检查网络连接，PaddleOCR需要下载模型文件")
                    return False
            else:
                logger.info("✅ OCR模型已存在，跳过下载")
                # 即使模型存在，也做一个快速测试
                try:
                    from paddleocr import PaddleOCR
                    # 创建OCR实例进行快速验证
                    ocr = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=False, show_log=False)
                    logger.info("✅ OCR模型验证通过")
                    return True
                except Exception as e:
                    logger.warning(f"⚠️ OCR模型验证失败: {e}")
                    self.warnings.append(f"OCR模型验证失败，但将在使用时重试: {e}")
                    return True
                
        except Exception as e:
            logger.error(f"❌ OCR检查失败: {e}")
            self.errors.append(f"OCR检查失败: {e}")
            return False
    
    def generate_report(self) -> str:
        """生成环境检查报告"""
        report = ["=" * 60]
        report.append("环境检查报告")
        report.append("=" * 60)
        
        if self.success_messages:
            report.append("\n✅ 成功项目:")
            for msg in self.success_messages:
                report.append(f"  {msg}")
        
        if self.warnings:
            report.append("\n⚠️ 警告信息:")
            for warning in self.warnings:
                report.append(f"  {warning}")
        
        if self.errors:
            report.append("\n❌ 错误信息:")
            for error in self.errors:
                report.append(f"  {error}")
        
        report.append("\n" + "=" * 60)
        return "\n".join(report)
    
    def get_startup_recommendations(self) -> List[str]:
        """获取启动建议"""
        recommendations = []
        
        if self.errors:
            recommendations.append("⚠️ 发现严重错误，建议修复后再启动系统")
            recommendations.extend([f"• {error}" for error in self.errors[:3]])  # 只显示前3个
        
        if self.warnings:
            recommendations.append("ℹ️ 注意事项:")
            recommendations.extend([f"• {warning}" for warning in self.warnings[:3]])  # 只显示前3个
        
        if not self.errors and not self.warnings:
            recommendations.append("🎉 环境检查全部通过，系统已准备就绪！")
        
        return recommendations

# 全局实例
environment_checker = EnvironmentChecker() 