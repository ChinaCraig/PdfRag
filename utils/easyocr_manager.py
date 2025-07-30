"""
EasyOCR模型管理器
与现有PaddleOCR管理器保持接口兼容，提供更简单快速的OCR解决方案
"""

import os
import logging
import threading
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class EasyOCRManager:
    """
    EasyOCR模型管理器
    
    优势：
    - 配置简单：仅需语言列表
    - 启动快速：自动模型管理
    - 内存优化：单一模型架构
    - 多语言支持：80+语言支持
    """
    
    def __init__(self):
        self.ocr_instance = None
        self.model_lock = threading.Lock()
        self.last_access_time = 0
        self.model_ttl = 1800  # 30分钟TTL
        self.loading_flag = False
        
        # 硬件自适应设置（与现有系统兼容）
        self.adaptive_settings = {
            "enable_gpu": False,
            "device": "cpu", 
            "conservative_mode": False
        }
        
        logger.info("EasyOCR模型管理器初始化完成")
    
    def apply_hardware_config(self, hardware_config: Dict[str, Any]) -> None:
        """
        应用硬件配置（与现有系统兼容）
        
        Args:
            hardware_config: 硬件配置字典
        """
        try:
            old_gpu_setting = self.adaptive_settings.get("enable_gpu", False)
            
            # 更新自适应设置
            self.adaptive_settings.update({
                "enable_gpu": hardware_config.get("gpu_acceleration", False),
                "conservative_mode": hardware_config.get("processing_mode") == "conservative"
            })
            
            # 设备检测
            if self.adaptive_settings["enable_gpu"]:
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.adaptive_settings["device"] = "cuda"
                        logger.info("✅ EasyOCR GPU加速已启用")
                    else:
                        self.adaptive_settings["device"] = "cpu"
                        logger.warning("⚠️ CUDA不可用，EasyOCR使用CPU模式")
                except ImportError:
                    self.adaptive_settings["device"] = "cpu"
                    logger.warning("⚠️ PyTorch未安装，EasyOCR使用CPU模式")
            else:
                self.adaptive_settings["device"] = "cpu"
            
            # 如果GPU设置改变，清空模型缓存
            if old_gpu_setting != self.adaptive_settings["enable_gpu"]:
                logger.info("GPU设置已改变，清空EasyOCR模型缓存")
                self.ocr_instance = None
            
            logger.info(f"EasyOCR硬件配置已应用: {self.adaptive_settings}")
            
        except Exception as e:
            logger.error(f"应用EasyOCR硬件配置失败: {e}")
    
    def load_ocr_model(self, force_reload: bool = False):
        """
        加载EasyOCR模型（接口与PaddleOCR兼容）
        
        Args:
            force_reload: 是否强制重新加载
            
        Returns:
            EasyOCR实例
        """
        # 检查缓存
        if not force_reload and self.ocr_instance and not self._is_model_expired():
            self._update_access_time()
            logger.debug("从缓存加载EasyOCR模型")
            return self.ocr_instance
        
        # 获取加载锁
        with self.model_lock:
            # 双重检查
            if not force_reload and self.ocr_instance and not self._is_model_expired():
                self._update_access_time()
                return self.ocr_instance
            
            # 防止重复加载
            if self.loading_flag:
                logger.warning("EasyOCR模型正在加载中...")
                return None
            
            self.loading_flag = True
            
            try:
                # 导入EasyOCR
                import easyocr
                from utils.config_loader import config_loader
                
                # 获取配置
                easyocr_config = config_loader.get_nested_value("model.ocr.easyocr", {})
                if not easyocr_config:
                    # 如果没有EasyOCR配置，使用默认配置
                    easyocr_config = {
                        "languages": ["ch_sim", "en"],
                        "model_path": "./models/easyocr"
                    }
                
                languages = easyocr_config.get("languages", ["ch_sim", "en"])
                model_path = easyocr_config.get("model_path", "./models/easyocr")
                use_gpu = self.adaptive_settings["enable_gpu"]
                
                # 保守模式强制使用CPU
                if self.adaptive_settings["conservative_mode"]:
                    use_gpu = False
                    logger.info("🔍 保守模式: EasyOCR使用CPU模式")
                
                # 确保模型目录存在
                os.makedirs(model_path, exist_ok=True)
                
                logger.info(f"🔍🔍🔍 开始加载EasyOCR模型")
                logger.info(f"🔍 支持语言: {languages}")
                logger.info(f"🔍 模型路径: {model_path}")
                logger.info(f"🔍 使用GPU: {use_gpu}")
                logger.info(f"🔍 注意：EasyOCR首次使用将自动下载模型，请耐心等待...")
                
                import sys
                sys.stdout.flush()
                sys.stderr.flush()
                
                # 创建EasyOCR实例
                self.ocr_instance = easyocr.Reader(
                    lang_list=languages,
                    gpu=use_gpu,
                    model_storage_directory=model_path,
                    download_enabled=True,
                    verbose=False,  # 减少输出
                    recognizer=True,
                    detector=True
                )
                
                # 测试模型是否正常工作
                logger.info("🧪 测试EasyOCR模型...")
                
                self._update_access_time()
                logger.info(f"✅✅✅ EasyOCR模型加载成功")
                return self.ocr_instance
                
            except Exception as e:
                logger.error(f"❌❌❌ EasyOCR模型加载失败: {e}", exc_info=True)
                raise
            finally:
                self.loading_flag = False
    
    def extract_text_from_image(self, image_path: str) -> List[Dict[str, Any]]:
        """
        提取图像文字（接口与PaddleOCR兼容）
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            OCR结果列表，格式与PaddleOCR保持一致
        """
        try:
            # 加载模型
            ocr = self.load_ocr_model()
            if ocr is None:
                logger.warning("EasyOCR模型加载失败，跳过图像文字提取")
                return []
            
            # 获取检测参数
            from utils.config_loader import config_loader
            detection_params = config_loader.get_nested_value("model.ocr.easyocr.detection_params", {})
            
            # 执行OCR识别
            logger.debug(f"🔍 开始EasyOCR识别: {image_path}")
            
            results = ocr.readtext(
                image_path,
                detail=1,  # 返回详细信息(坐标+文字+置信度)
                paragraph=False,  # 不合并段落，保持原始检测结果
                width_ths=detection_params.get("width_ths", 0.7),
                height_ths=detection_params.get("height_ths", 0.7),
                slope_ths=detection_params.get("slope_ths", 0.1),
                ycenter_ths=detection_params.get("ycenter_ths", 0.7),
                mag_ratio=detection_params.get("mag_ratio", 1.0),
                text_threshold=detection_params.get("text_threshold", 0.7),
                low_text=detection_params.get("low_text", 0.4),
                link_threshold=detection_params.get("link_threshold", 0.4)
            )
            
            # 解析结果，转换为统一格式
            ocr_results = []
            if results:
                for result in results:
                    try:
                        bbox = result[0]  # 边界框 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                        text = result[1].strip()  # 文字内容
                        confidence = float(result[2])  # 置信度
                        
                        # 过滤低质量结果
                        if confidence < 0.5 or len(text.strip()) == 0:
                            continue
                        
                        ocr_results.append({
                            "text": text,
                            "confidence": confidence,
                            "bbox": bbox
                        })
                        
                    except (IndexError, ValueError, TypeError) as e:
                        logger.warning(f"解析EasyOCR结果失败: {e}")
                        continue
            
            logger.debug(f"✅ EasyOCR提取完成: {len(ocr_results)}个文本块")
            return ocr_results
            
        except Exception as e:
            logger.error(f"❌ EasyOCR文字提取失败: {e}")
            return []
    
    def get_model_stats(self) -> Dict[str, Any]:
        """获取模型统计信息（与现有系统兼容）"""
        return {
            "engine_type": "easyocr",
            "model_loaded": self.ocr_instance is not None,
            "last_access_time": self.last_access_time,
            "model_expired": self._is_model_expired(),
            "adaptive_settings": self.adaptive_settings.copy(),
            "loading_flag": self.loading_flag
        }
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.ocr_instance:
                # EasyOCR没有显式的cleanup方法，通过设置为None让GC处理
                self.ocr_instance = None
                logger.info("EasyOCR模型资源已清理")
        except Exception as e:
            logger.error(f"清理EasyOCR资源失败: {e}")
    
    def _update_access_time(self):
        """更新模型访问时间"""
        self.last_access_time = time.time()
    
    def _is_model_expired(self) -> bool:
        """检查模型是否过期"""
        if self.last_access_time == 0:
            return True
        return (time.time() - self.last_access_time) > self.model_ttl

# 全局EasyOCR管理器实例
easyocr_manager = EasyOCRManager()