"""
模型管理工具类
负责模型的下载、加载和管理
"""
import os
import logging
import requests
import torch
from sentence_transformers import SentenceTransformer
from paddleocr import PaddleOCR
from transformers import BlipProcessor, BlipForConditionalGeneration
from typing import Dict, Any, Optional, List
import json
from utils.config_loader import config_loader

logger = logging.getLogger(__name__)

class ModelManager:
    """模型管理器"""
    
    def __init__(self):
        self.config = config_loader.get_model_config()
        self.models = {}
        self.gpu_enabled = self.config.get("gpu_acceleration", False)
        self.device = "cuda" if self.gpu_enabled and torch.cuda.is_available() else "cpu"
        logger.info(f"使用设备: {self.device}")
    
    def download_model(self, model_type: str) -> bool:
        """
        下载指定类型的模型
        
        Args:
            model_type: 模型类型 (embedding, ocr, table_detection, etc.)
            
        Returns:
            下载是否成功
        """
        try:
            model_config = self.config.get(model_type, {})
            model_path = model_config.get("model_path")
            
            if not model_path:
                logger.error(f"模型 {model_type} 配置中缺少model_path")
                return False
            
            # 创建模型目录
            os.makedirs(model_path, exist_ok=True)
            
            download_config = self.config.get("model_downloads", {}).get(model_type, {})
            
            if model_type == "embedding":
                return self._download_embedding_model(model_config, download_config)
            elif model_type == "ocr":
                return self._download_ocr_model(model_config, download_config)
            elif model_type == "table_detection":
                return self._download_table_detection_model(model_config, download_config)
            elif model_type == "image_analysis":
                return self._download_image_analysis_model(model_config, download_config)
            elif model_type == "chart_recognition":
                return self._download_chart_recognition_model(model_config, download_config)
            else:
                logger.warning(f"未知的模型类型: {model_type}")
                return False
                
        except Exception as e:
            logger.error(f"下载模型 {model_type} 失败: {e}")
            return False
    
    def _download_embedding_model(self, model_config: Dict, download_config: Dict) -> bool:
        """下载嵌入模型"""
        try:
            model_name = model_config["model_name"]
            model_path = model_config["model_path"]
            
            # 检查模型是否已存在
            if os.path.exists(os.path.join(model_path, "pytorch_model.bin")):
                logger.info(f"嵌入模型已存在: {model_path}")
                return True
            
            logger.info(f"开始下载嵌入模型: {model_name}")
            # 使用sentence-transformers下载模型
            model = SentenceTransformer(model_name)
            model.save(model_path)
            logger.info(f"嵌入模型下载完成: {model_path}")
            return True
            
        except Exception as e:
            logger.error(f"下载嵌入模型失败: {e}")
            return False
    
    def _download_ocr_model(self, model_config: Dict, download_config: Dict) -> bool:
        """下载OCR模型"""
        try:
            # PaddleOCR会自动下载模型
            if download_config.get("auto_download", True):
                logger.info("OCR模型将在首次使用时自动下载")
                return True
            return True
        except Exception as e:
            logger.error(f"OCR模型下载失败: {e}")
            return False
    
    def _download_table_detection_model(self, model_config: Dict, download_config: Dict) -> bool:
        """下载表格检测模型"""
        # 暂时返回True，实际实现需要根据具体模型
        logger.info("表格检测模型下载功能待实现")
        return True
    
    def _download_image_analysis_model(self, model_config: Dict, download_config: Dict) -> bool:
        """下载图像分析模型"""
        # 暂时返回True，实际实现需要根据具体模型
        logger.info("图像分析模型下载功能待实现")
        return True
    
    def _download_chart_recognition_model(self, model_config: Dict, download_config: Dict) -> bool:
        """下载图表识别模型"""
        # 暂时返回True，实际实现需要根据具体模型
        logger.info("图表识别模型下载功能待实现")
        return True
    
    def load_embedding_model(self) -> SentenceTransformer:
        """加载嵌入模型"""
        if "embedding" in self.models:
            return self.models["embedding"]
        
        try:
            embedding_config = self.config["embedding"]
            model_path = embedding_config["model_path"]
            
            if os.path.exists(os.path.join(model_path, "pytorch_model.bin")):
                # 从本地路径加载
                model = SentenceTransformer(model_path, device=self.device)
            else:
                # 从HuggingFace加载
                model_name = embedding_config["model_name"]
                model = SentenceTransformer(model_name, device=self.device)
            
            self.models["embedding"] = model
            logger.info("嵌入模型加载成功")
            return model
            
        except Exception as e:
            logger.error(f"嵌入模型加载失败: {e}")
            raise
    
    def load_ocr_model(self) -> PaddleOCR:
        """加载OCR模型"""
        if "ocr" in self.models:
            return self.models["ocr"]
        
        try:
            ocr_config = self.config["ocr"]
            
            # 根据GPU配置设置
            use_gpu = self.gpu_enabled and torch.cuda.is_available()
            
            # PaddleOCR的lang参数应该是单个字符串，不是列表
            languages = ocr_config.get("language", ["ch", "en"])
            # 只取第一个语言，如果需要多语言支持需要分别初始化
            primary_lang = languages[0] if languages else "ch"
            
            ocr = PaddleOCR(
                use_angle_cls=ocr_config.get("use_angle_cls", True),
                lang=primary_lang,
                use_gpu=use_gpu,
                show_log=False
            )
            
            self.models["ocr"] = ocr
            logger.info("OCR模型加载成功")
            return ocr
            
        except Exception as e:
            logger.error(f"OCR模型加载失败: {e}")
            raise
    
    def get_embedding(self, texts: List[str]) -> List[List[float]]:
        """
        获取文本嵌入向量
        
        Args:
            texts: 文本列表
            
        Returns:
            嵌入向量列表
        """
        model = self.load_embedding_model()
        embeddings = model.encode(texts, convert_to_tensor=True)
        return embeddings.cpu().numpy().tolist()
    
    def extract_text_from_image(self, image_path: str) -> List[Dict[str, Any]]:
        """
        从图像中提取文本
        
        Args:
            image_path: 图像路径
            
        Returns:
            提取的文本信息列表
        """
        ocr = self.load_ocr_model()
        result = ocr.ocr(image_path, cls=True)
        
        texts = []
        for line in result[0] if result[0] else []:
            texts.append({
                "text": line[1][0],
                "confidence": line[1][1],
                "bbox": line[0]
            })
        
        return texts
    
    def check_model_availability(self, model_type: str) -> bool:
        """
        检查模型是否可用
        
        Args:
            model_type: 模型类型
            
        Returns:
            模型是否可用
        """
        try:
            if model_type == "embedding":
                model_config = self.config["embedding"]
                model_path = model_config["model_path"]
                return os.path.exists(os.path.join(model_path, "pytorch_model.bin"))
            elif model_type == "ocr":
                # OCR模型会自动下载，认为总是可用
                return True
            else:
                # 其他模型暂时返回True
                return True
        except Exception as e:
            logger.error(f"检查模型 {model_type} 可用性失败: {e}")
            return False

# 全局模型管理器实例
model_manager = ModelManager() 