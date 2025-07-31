"""
简化模型管理器
提供基本的embedding和OCR功能，移除复杂的硬件检测和性能优化
"""
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SimpleModelManager:
    """简化的模型管理器"""
    
    def __init__(self):
        self.embedding_model = None
        self.ocr_model = None
        
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
            if self.embedding_model is None:
                self._load_embedding_model()
            
            if self.embedding_model is None:
                logger.error("嵌入模型未加载")
                return []
            
            embeddings = self.embedding_model.encode(texts, convert_to_tensor=False, show_progress_bar=False)
            return embeddings.tolist() if hasattr(embeddings, 'tolist') else embeddings
            
        except Exception as e:
            logger.error(f"生成嵌入向量失败: {e}")
            return []
    
    def _load_embedding_model(self):
        """加载嵌入模型"""
        try:
            from sentence_transformers import SentenceTransformer
            from utils.config_loader import config_loader
            
            model_config = config_loader.get_nested_value("model.embedding", {})
            model_name = model_config.get("model_name", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            model_path = model_config.get("model_path", "./models/embedding")
            
            logger.info(f"加载嵌入模型: {model_name}")
            
            if os.path.exists(os.path.join(model_path, "pytorch_model.bin")):
                # 从本地路径加载
                self.embedding_model = SentenceTransformer(model_path)
                logger.info(f"从本地加载嵌入模型: {model_path}")
            else:
                # 从Hugging Face下载
                self.embedding_model = SentenceTransformer(model_name)
                
                # 保存到本地
                os.makedirs(model_path, exist_ok=True)
                self.embedding_model.save(model_path)
                logger.info(f"嵌入模型已保存到本地: {model_path}")
            
            logger.info("✅ 嵌入模型加载成功")
            
        except Exception as e:
            logger.error(f"❌ 嵌入模型加载失败: {e}")
            self.embedding_model = None
    
    def extract_text_from_image(self, image_path: str) -> List[Dict[str, Any]]:
        """
        从图像中提取文本（OCR）
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            OCR结果列表
        """
        try:
            if self.ocr_model is None:
                self._load_ocr_model()
            
            if self.ocr_model is None:
                logger.error("OCR模型未加载")
                return []
            
            # 执行OCR
            results = self.ocr_model.ocr(image_path, cls=True)
            
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
            
            logger.debug(f"OCR提取完成: {len(ocr_results)}个文本块")
            return ocr_results
            
        except Exception as e:
            logger.error(f"OCR文字提取失败: {e}")
            return []
    
    def _load_ocr_model(self):
        """加载PaddleOCR模型"""
        try:
            from paddleocr import PaddleOCR
            from utils.config_loader import config_loader
            
            # 获取全局配置
            model_config = config_loader.get_model_config()
            ocr_config = model_config.get("ocr", {})
            gpu_acceleration = model_config.get("gpu_acceleration", False)
            
            # PaddleOCR参数配置
            model_path = ocr_config.get("model_path", "./models/ocr")
            languages = ocr_config.get("language", ["ch", "en"])
            use_angle_cls = ocr_config.get("use_angle_cls", True)
            use_gpu = ocr_config.get("use_gpu", True) and gpu_acceleration
            
            # 检测参数
            detection_params = ocr_config.get("detection_params", {})
            
            # 识别参数
            recognition_params = ocr_config.get("recognition_params", {})
            
            logger.info(f"加载PaddleOCR模型，GPU加速: {use_gpu}")
            
            # 构建PaddleOCR参数
            paddle_params = {
                "use_angle_cls": use_angle_cls,
                "lang": "ch" if "ch" in languages else "en",
                "use_gpu": use_gpu,
                "show_log": False
            }
            
            # 添加检测参数
            if detection_params:
                paddle_params.update({
                    "det_limit_side_len": detection_params.get("det_limit_side_len", 960),
                    "det_limit_type": detection_params.get("det_limit_type", "max"),
                    "det_thresh": detection_params.get("det_thresh", 0.3),
                    "det_box_thresh": detection_params.get("det_box_thresh", 0.6),
                    "det_unclip_ratio": detection_params.get("det_unclip_ratio", 1.5),
                    "max_candidates": detection_params.get("max_candidates", 1000),
                    "unclip_ratio": detection_params.get("unclip_ratio", 1.5),
                    "use_polygon": detection_params.get("use_polygon", False)
                })
            
            # 添加识别参数
            if recognition_params:
                paddle_params.update({
                    "rec_batch_num": recognition_params.get("rec_batch_num", 6),
                    "max_text_length": recognition_params.get("max_text_length", 25),
                    "use_space_char": recognition_params.get("use_space_char", True)
                })
                
                # 字典路径
                rec_char_dict_path = recognition_params.get("rec_char_dict_path", "")
                if rec_char_dict_path:
                    paddle_params["rec_char_dict_path"] = rec_char_dict_path
            
            # 如果存在本地模型目录，使用本地模型
            if os.path.exists(model_path):
                det_model_dir = os.path.join(model_path, "det")
                rec_model_dir = os.path.join(model_path, "rec")
                cls_model_dir = os.path.join(model_path, "cls")
                
                if os.path.exists(det_model_dir):
                    paddle_params["det_model_dir"] = det_model_dir
                if os.path.exists(rec_model_dir):
                    paddle_params["rec_model_dir"] = rec_model_dir
                if os.path.exists(cls_model_dir) and use_angle_cls:
                    paddle_params["cls_model_dir"] = cls_model_dir
            
            # 创建PaddleOCR实例
            self.ocr_model = PaddleOCR(**paddle_params)
            
            logger.info("✅ PaddleOCR模型加载成功")
            
        except Exception as e:
            logger.error(f"❌ PaddleOCR模型加载失败: {e}")
            self.ocr_model = None
    
    def cleanup(self):
        """清理资源"""
        try:
            self.embedding_model = None
            self.ocr_model = None
            logger.info("简化模型管理器资源已清理")
        except Exception as e:
            logger.error(f"清理简化模型管理器资源失败: {e}")

# 全局模型管理器实例
model_manager = SimpleModelManager()