"""
模型管理器 - 硬件自适应版本
负责各种AI模型的延迟加载、缓存管理和资源优化
支持根据硬件配置动态调整模型加载策略
"""

import os
import logging
import threading
import time
import gc
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor

# 第三方库
from sentence_transformers import SentenceTransformer
from paddleocr import PaddleOCR

# 项目内部模块
from utils.config_loader import config_loader
from utils.easyocr_manager import EasyOCRManager

logger = logging.getLogger(__name__)

class ModelManager:
    """
    智能模型管理器
    
    特性:
    - 延迟加载：模型仅在需要时加载
    - LRU缓存：自动管理模型内存使用
    - 硬件自适应：根据系统性能调整加载策略
    - 并发安全：支持多线程环境
    - 批量处理：优化向量生成效率
    """
    
    def __init__(self):
        """初始化模型管理器"""
        self.models = {}  # 模型缓存
        self.model_locks = {}  # 模型加载锁
        self.model_usage = {}  # 模型使用次数
        self.last_access_time = {}  # 最后访问时间
        self.loading_flags = {}  # 加载状态标记
        
        # 缓存配置
        self.max_models_in_memory = 2
        self.model_ttl = 1800  # 30分钟TTL
        self.cleanup_thread = None
        
        # 硬件自适应设置
        self.adaptive_settings = {
            "enable_gpu": False,
            "enable_model_cache": True,
            "batch_size": 4,
            "conservative_mode": False,
            "preload_models": False,
            "device": "cpu"
        }
        
        # OCR引擎管理
        self.ocr_engines = {}
        self.current_ocr_engine = None
        self.default_ocr_engine = "easyocr"  # 默认使用EasyOCR
        
        # 启动清理线程
        self._start_cleanup_thread()
        
        # 初始化OCR引擎
        self._init_ocr_engines()
        
        logger.info("模型管理器初始化完成 - EasyOCR集成版本")
    
    def apply_hardware_config(self, hardware_config: Dict[str, Any]) -> None:
        """
        应用硬件配置到模型管理器
        
        Args:
            hardware_config: 硬件推荐配置
        """
        try:
            old_gpu_setting = self.adaptive_settings.get("enable_gpu", False)
            
            # 更新自适应设置
            self.adaptive_settings.update({
                "enable_gpu": hardware_config.get("gpu_acceleration", False),
                "batch_size": hardware_config.get("batch_size", 4),
                "enable_model_cache": hardware_config.get("model_cache_enabled", True),
                "conservative_mode": hardware_config.get("processing_mode") == "conservative",
                "preload_models": hardware_config.get("processing_mode") == "aggressive"
            })
            
            # 设置设备
            if self.adaptive_settings["enable_gpu"]:
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.adaptive_settings["device"] = "cuda"
                        logger.info("✅ GPU加速已启用")
                    else:
                        self.adaptive_settings["device"] = "cpu"
                        logger.warning("⚠️ CUDA不可用，使用CPU模式")
                except ImportError:
                    self.adaptive_settings["device"] = "cpu"
                    logger.warning("⚠️ PyTorch未安装，使用CPU模式")
            else:
                self.adaptive_settings["device"] = "cpu"
            
            # 调整缓存设置
            processing_mode = hardware_config.get("processing_mode", "balanced")
            if processing_mode == "conservative":
                self.max_models_in_memory = 1
                self.model_ttl = 600  # 10分钟
            elif processing_mode == "aggressive":
                self.max_models_in_memory = 3
                self.model_ttl = 3600  # 1小时
            else:  # balanced
                self.max_models_in_memory = 2
                self.model_ttl = 1800  # 30分钟
            
            # 如果GPU设置改变，清空模型缓存
            if old_gpu_setting != self.adaptive_settings["enable_gpu"]:
                logger.info("GPU设置已改变，清空模型缓存")
                self._clear_model_cache()
            
            # 将硬件配置应用到OCR引擎
            for engine in self.ocr_engines.values():
                if hasattr(engine, 'apply_hardware_config'):
                    engine.apply_hardware_config(hardware_config)
            
            logger.info(f"硬件自适应配置已应用: {self.adaptive_settings}")
            
        except Exception as e:
            logger.error(f"应用硬件配置失败: {e}")
    
    def _start_cleanup_thread(self) -> None:
        """启动模型清理线程"""
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            return
        
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_unused_models,
            name="ModelCleanup",
            daemon=True
        )
        self.cleanup_thread.start()
        logger.debug("模型清理线程已启动")
    
    def _cleanup_unused_models(self) -> None:
        """定期清理未使用的模型"""
        while True:
            try:
                time.sleep(300)  # 每5分钟检查一次
                current_time = time.time()
                models_to_remove = []
                
                for model_type, last_access in self.last_access_time.items():
                    if current_time - last_access > self.model_ttl:
                        models_to_remove.append(model_type)
                
                for model_type in models_to_remove:
                    self._unload_model(model_type)
                    logger.info(f"自动清理未使用模型: {model_type}")
                
                # 强制垃圾回收
                if models_to_remove:
                    gc.collect()
                    
            except Exception as e:
                logger.error(f"模型清理异常: {e}")
                time.sleep(60)  # 异常时等待1分钟再继续
    
    def _unload_model(self, model_type: str) -> None:
        """卸载指定模型"""
        try:
            if model_type in self.models:
                del self.models[model_type]
            if model_type in self.model_usage:
                del self.model_usage[model_type]
            if model_type in self.last_access_time:
                del self.last_access_time[model_type]
            logger.debug(f"模型已卸载: {model_type}")
        except Exception as e:
            logger.error(f"卸载模型失败: {model_type}, {e}")
    
    def _clear_model_cache(self) -> None:
        """清空所有模型缓存"""
        try:
            model_types = list(self.models.keys())
            for model_type in model_types:
                self._unload_model(model_type)
            gc.collect()
            logger.info("所有模型缓存已清空")
        except Exception as e:
            logger.error(f"清空模型缓存失败: {e}")
    
    def _get_model_lock(self, model_type: str) -> threading.Lock:
        """获取模型加载锁"""
        if model_type not in self.model_locks:
            self.model_locks[model_type] = threading.Lock()
        return self.model_locks[model_type]
    
    def load_embedding_model(self, force_reload: bool = False) -> SentenceTransformer:
        """
        延迟加载嵌入模型
        
        Args:
            force_reload: 是否强制重新加载
            
        Returns:
            嵌入模型实例
        """
        model_type = "embedding"
        
        # 检查缓存
        if not force_reload and model_type in self.models:
            self._update_model_access(model_type)
            logger.debug(f"从缓存加载嵌入模型")
            return self.models[model_type]
        
        # 获取加载锁
        with self._get_model_lock(model_type):
            # 双重检查
            if not force_reload and model_type in self.models:
                self._update_model_access(model_type)
                return self.models[model_type]
            
            # 防止重复加载
            if model_type in self.loading_flags:
                logger.warning(f"模型正在加载中: {model_type}")
                return None
            
            self.loading_flags[model_type] = True
            
            try:
                # 获取模型配置
                model_config = config_loader.get_nested_value("model.embedding", {})
                model_name = model_config.get("model_name", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
                model_path = model_config.get("model_path", "./models/embedding")
                dimensions = model_config.get("dimensions", 384)
                
                # 设备配置
                device = self.adaptive_settings["device"]
                
                logger.info(f"🔤🔤🔤 开始加载嵌入模型")
                logger.info(f"🔤 模型名称: {model_name}")
                logger.info(f"🔤 模型路径: {model_path}")
                logger.info(f"🔤 向量维度: {dimensions}")
                logger.info(f"🔤 使用设备: {device}")
                
                # 保守模式下的加载策略
                if self.adaptive_settings["conservative_mode"]:
                    logger.info(f"🔤 保守模式: 使用轻量化加载策略")
                else:
                    logger.info(f"🔤 注意：768维模型首次加载可能需要5-10分钟，请耐心等待...")
                
                import sys
                sys.stdout.flush()
                sys.stderr.flush()
                
                if os.path.exists(os.path.join(model_path, "pytorch_model.bin")):
                    # 从本地路径加载
                    logger.info(f"🔤 从本地路径加载模型: {model_path}")
                    model = SentenceTransformer(model_path, device=device)
                else:
                    # 从Hugging Face下载
                    logger.info(f"🔤 从Hugging Face下载模型: {model_name}")
                    model = SentenceTransformer(model_name, device=device)
                    
                    # 保存到本地
                    os.makedirs(model_path, exist_ok=True)
                    model.save(model_path)
                    logger.info(f"🔤 模型已保存到本地: {model_path}")
                
                # 验证模型维度
                test_text = ["测试文本"]
                test_embedding = model.encode(test_text, convert_to_tensor=False)
                actual_dim = len(test_embedding[0]) if len(test_embedding) > 0 else 0
                
                logger.info(f"🔤 模型加载完成，实际维度: {actual_dim}")
                
                if actual_dim != dimensions:
                    logger.warning(f"⚠️ 模型维度不匹配！配置维度: {dimensions}, 实际维度: {actual_dim}")
                
                # 缓存模型
                if self.adaptive_settings["enable_model_cache"]:
                    self._ensure_cache_space()
                    self.models[model_type] = model
                    self._update_model_access(model_type)
                    logger.info(f"✅ 嵌入模型已缓存")
                
                logger.info(f"✅✅✅ 嵌入模型加载成功 - {model_name} ({actual_dim}维)")
                return model
                
            except Exception as e:
                logger.error(f"❌❌❌ 嵌入模型加载失败: {e}", exc_info=True)
                raise
            finally:
                # 清除加载标志
                if model_type in self.loading_flags:
                    del self.loading_flags[model_type]
    
    def load_ocr_model(self, force_reload: bool = False) -> PaddleOCR:
        """
        延迟加载OCR模型
        
        Args:
            force_reload: 是否强制重新加载
            
        Returns:
            OCR模型实例
        """
        model_type = "ocr"
        
        # 检查缓存
        if not force_reload and model_type in self.models:
            self._update_model_access(model_type)
            logger.debug(f"从缓存加载OCR模型")
            return self.models[model_type]
        
        # 获取加载锁
        with self._get_model_lock(model_type):
            # 双重检查
            if not force_reload and model_type in self.models:
                self._update_model_access(model_type)
                return self.models[model_type]
            
            # 防止重复加载
            if model_type in self.loading_flags:
                logger.warning(f"模型正在加载中: {model_type}")
                return None
            
            self.loading_flags[model_type] = True
            
            try:
                # 获取OCR配置
                ocr_config = config_loader.get_nested_value("model.ocr", {})
                det_model_dir = ocr_config.get("det_model_dir", "./models/ocr")
                rec_model_dir = ocr_config.get("rec_model_dir", "./models/ocr")
                cls_model_dir = ocr_config.get("cls_model_dir", "./models/ocr")
                
                # GPU设置
                use_gpu = self.adaptive_settings["enable_gpu"]
                
                logger.info(f"🔍🔍🔍 开始加载OCR模型")
                logger.info(f"🔍 检测模型: {det_model_dir}")
                logger.info(f"🔍 识别模型: {rec_model_dir}")
                logger.info(f"🔍 分类模型: {cls_model_dir}")
                logger.info(f"🔍 使用GPU: {use_gpu}")
                
                # 保守模式设置
                if self.adaptive_settings["conservative_mode"]:
                    logger.info(f"🔍 保守模式: 使用轻量化OCR配置")
                    use_gpu = False  # 保守模式强制使用CPU
                
                # 创建OCR实例
                ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang='ch',
                    use_gpu=use_gpu,
                    det_model_dir=det_model_dir if os.path.exists(det_model_dir) else None,
                    rec_model_dir=rec_model_dir if os.path.exists(rec_model_dir) else None,
                    cls_model_dir=cls_model_dir if os.path.exists(cls_model_dir) else None
                )
                
                # 缓存模型
                if self.adaptive_settings["enable_model_cache"]:
                    self._ensure_cache_space()
                    self.models[model_type] = ocr
                    self._update_model_access(model_type)
                    logger.info(f"✅ OCR模型已缓存")
                
                logger.info(f"✅✅✅ OCR模型加载成功")
                return ocr
                
            except Exception as e:
                logger.error(f"❌❌❌ OCR模型加载失败: {e}", exc_info=True)
                raise
            finally:
                # 清除加载标志
                if model_type in self.loading_flags:
                    del self.loading_flags[model_type]
    
    def _ensure_cache_space(self) -> None:
        """确保缓存空间充足"""
        if len(self.models) >= self.max_models_in_memory:
            # 找到最久未使用的模型
            oldest_model = min(
                self.last_access_time.items(),
                key=lambda x: x[1]
            )[0]
            self._unload_model(oldest_model)
            logger.debug(f"缓存空间不足，卸载最久未使用的模型: {oldest_model}")
    
    def _update_model_access(self, model_type: str) -> None:
        """更新模型访问记录"""
        self.last_access_time[model_type] = time.time()
        self.model_usage[model_type] = self.model_usage.get(model_type, 0) + 1
    
    def get_embedding(self, texts: List[str]) -> List[List[float]]:
        """
        获取文本嵌入向量
        
        Args:
            texts: 文本列表
            
        Returns:
            嵌入向量列表
        """
        if not texts:
            return []
        
        try:
            batch_size = self.adaptive_settings["batch_size"]
            
            # 批量处理
            if len(texts) > batch_size:
                return self._get_embedding_batched(texts, batch_size)
            
            # 直接处理
            model = self.load_embedding_model()
            if model is None:
                raise ValueError("嵌入模型加载失败")
            
            embeddings = model.encode(texts, convert_to_tensor=False, show_progress_bar=False)
            return embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings
            
        except Exception as e:
            logger.error(f"生成嵌入向量失败: {e}")
            raise
    
    def _get_embedding_batched(self, texts: List[str], batch_size: int) -> List[List[float]]:
        """批量生成嵌入向量"""
        try:
            model = self.load_embedding_model()
            if model is None:
                raise ValueError("嵌入模型加载失败")
            
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                batch_embeddings = model.encode(
                    batch_texts,
                    convert_to_tensor=False,
                    show_progress_bar=False
                )
                
                if hasattr(batch_embeddings, 'tolist'):
                    all_embeddings.extend(batch_embeddings.tolist())
                else:
                    all_embeddings.extend(batch_embeddings)
                
                logger.debug(f"批处理进度: {min(i + batch_size, len(texts))}/{len(texts)}")
            
            return all_embeddings
            
        except Exception as e:
            logger.error(f"批量生成嵌入向量失败: {e}")
            raise
    
    def extract_text_from_image(self, image_path: str) -> List[Dict[str, Any]]:
        """
        从图像中提取文本（OCR） - 支持多引擎
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            OCR结果列表
        """
        try:
            # 使用当前OCR引擎
            if self.current_ocr_engine:
                return self.current_ocr_engine.extract_text_from_image(image_path)
            else:
                logger.warning("OCR引擎未初始化，尝试初始化默认引擎")
                self._init_ocr_engines()
                if self.current_ocr_engine:
                    return self.current_ocr_engine.extract_text_from_image(image_path)
                else:
                    logger.error("OCR引擎初始化失败")
                    return []
                
        except Exception as e:
            logger.error(f"当前OCR引擎处理失败: {e}")
            
            # 自动回退到PaddleOCR
            if self.current_ocr_engine and not isinstance(self.current_ocr_engine, type(self)):
                logger.info("自动回退到PaddleOCR引擎")
                try:
                    return self._extract_with_paddleocr(image_path)
                except Exception as fallback_error:
                    logger.error(f"PaddleOCR回退也失败: {fallback_error}")
            
            return []
    
    def get_model_stats(self) -> Dict[str, Any]:
        """获取模型使用统计"""
        return {
            "cached_models": list(self.models.keys()),
            "model_usage": self.model_usage.copy(),
            "cache_size": len(self.models),
            "max_cache_size": self.max_models_in_memory,
            "adaptive_settings": self.adaptive_settings.copy()
        }
    
    def preload_models(self, model_types: List[str] = None) -> None:
        """
        预加载指定模型
        
        Args:
            model_types: 要预加载的模型类型列表，None表示预加载所有
        """
        # 检查配置文件中的预加载设置
        from utils.config_loader import config_loader
        app_config = config_loader.get_app_config()
        dev_config = app_config.get("development", {})
        config_preload_enabled = dev_config.get("preload_models", False)
        
        # 检查自适应设置中的预加载
        adaptive_preload_enabled = self.adaptive_settings.get("preload_models", False)
        
        # 只要任一配置启用预加载就执行（优先配置文件）
        preload_enabled = config_preload_enabled or adaptive_preload_enabled
        
        if not preload_enabled:
            logger.debug("预加载已禁用，跳过模型预加载")
            return
        
        if model_types is None:
            model_types = ["embedding", "ocr"]
        
        logger.info(f"🚀 开始预加载模型: {model_types}")
        logger.info(f"预加载原因: 配置文件={config_preload_enabled}, 自适应设置={adaptive_preload_enabled}")
        
        for model_type in model_types:
            try:
                logger.info(f"📥 正在预加载 {model_type} 模型...")
                if model_type == "embedding":
                    self.load_embedding_model()
                    logger.info(f"✅ {model_type} 模型预加载完成")
                elif model_type == "ocr":
                    self.load_ocr_model()
                    logger.info(f"✅ {model_type} 模型预加载完成")
                else:
                    logger.warning(f"未知的模型类型: {model_type}")
            except Exception as e:
                logger.error(f"❌ 预加载模型失败 {model_type}: {e}")
        
        logger.info("🎉 所有模型预加载完成！")
    
    def _init_ocr_engines(self):
        """初始化OCR引擎"""
        try:
            # 获取默认引擎配置
            default_engine = config_loader.get_nested_value("model.ocr.default_engine", self.default_ocr_engine)
            
            logger.info(f"初始化OCR引擎，默认引擎: {default_engine}")
            self._switch_ocr_engine(default_engine)
            
        except Exception as e:
            logger.error(f"初始化OCR引擎失败: {e}")
            # 回退到EasyOCR
            try:
                self._switch_ocr_engine("easyocr")
            except Exception as fallback_error:
                logger.error(f"回退到EasyOCR也失败: {fallback_error}")
    
    def _switch_ocr_engine(self, engine_type: str):
        """切换OCR引擎"""
        try:
            if engine_type not in self.ocr_engines:
                if engine_type == "easyocr":
                    self.ocr_engines[engine_type] = EasyOCRManager()
                    # 应用硬件配置
                    self.ocr_engines[engine_type].apply_hardware_config(self.adaptive_settings)
                elif engine_type == "paddleocr":
                    # 使用现有的self作为PaddleOCR管理器
                    self.ocr_engines[engine_type] = self
                else:
                    raise ValueError(f"不支持的OCR引擎: {engine_type}")
            
            self.current_ocr_engine = self.ocr_engines[engine_type]
            logger.info(f"OCR引擎已切换到: {engine_type}")
            
        except Exception as e:
            logger.error(f"切换OCR引擎失败: {e}")
            raise
    
    def _extract_with_paddleocr(self, image_path: str) -> List[Dict[str, Any]]:
        """使用PaddleOCR提取文字（原有逻辑）"""
        try:
            # 加载PaddleOCR模型
            ocr = self.load_ocr_model()
            if ocr is None:
                logger.warning("PaddleOCR模型加载失败，跳过图像文字提取")
                return []
            
            # 执行OCR
            results = ocr.ocr(image_path, cls=True)
            
            # 解析结果
            ocr_results = []
            if results and results[0]:
                for line in results[0]:
                    if len(line) >= 2:
                        bbox = line[0]  # 边界框
                        text_info = line[1]  # 文字信息
                        if text_info and len(text_info) >= 2:
                            text = text_info[0]  # 文字内容
                            confidence = text_info[1]  # 置信度
                            
                            ocr_results.append({
                                "text": text,
                                "confidence": confidence,
                                "bbox": bbox
                            })
            
            logger.debug(f"PaddleOCR提取完成: {len(ocr_results)}个文本块")
            return ocr_results
            
        except Exception as e:
            logger.error(f"PaddleOCR文字提取失败: {e}")
            return []
    
    def get_ocr_engine_info(self) -> Dict[str, Any]:
        """获取OCR引擎信息"""
        current_engine_name = "unknown"
        if self.current_ocr_engine == self:
            current_engine_name = "paddleocr"
        elif self.current_ocr_engine:
            if hasattr(self.current_ocr_engine, 'get_model_stats'):
                stats = self.current_ocr_engine.get_model_stats()
                current_engine_name = stats.get('engine_type', 'unknown')
            else:
                current_engine_name = type(self.current_ocr_engine).__name__.lower()
        
        return {
            "current_engine": current_engine_name,
            "default_engine": self.default_ocr_engine,
            "available_engines": list(self.ocr_engines.keys()),
            "engine_stats": self.current_ocr_engine.get_model_stats() if hasattr(self.current_ocr_engine, 'get_model_stats') else {}
        }
    
    def switch_ocr_engine_runtime(self, engine_type: str) -> bool:
        """运行时切换OCR引擎"""
        try:
            logger.info(f"运行时切换OCR引擎到: {engine_type}")
            self._switch_ocr_engine(engine_type)
            return True
        except Exception as e:
            logger.error(f"运行时切换OCR引擎失败: {e}")
            return False
    
    def cleanup(self) -> None:
        """清理资源"""
        try:
            logger.info("正在清理模型管理器...")
            self._clear_model_cache()
            
            # 清理OCR引擎
            for engine in self.ocr_engines.values():
                if hasattr(engine, 'cleanup') and engine != self:
                    engine.cleanup()
            
            # 停止清理线程（线程是daemon，会自动结束）
            
            logger.info("模型管理器清理完成")
        except Exception as e:
            logger.error(f"清理模型管理器失败: {e}")

# 全局模型管理器实例
model_manager = ModelManager() 