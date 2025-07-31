"""
简化配置加载器
只保留基本的配置加载功能，移除复杂的硬件检测和性能优化
"""
import os
import yaml
import logging

logger = logging.getLogger(__name__)

class ConfigLoader:
    """简化的配置加载器"""
    
    def __init__(self):
        self.config_cache = {}
        self._load_all_configs()
    
    def _load_all_configs(self):
        """加载所有配置文件"""
        config_files = {
            'app': 'config/config.yaml',
            'db': 'config/db.yaml', 
            'model': 'config/model.yaml',
            'prompt': 'config/prompt.yaml'
        }
        
        for config_name, config_path in config_files.items():
            try:
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        self.config_cache[config_name] = yaml.safe_load(f) or {}
                else:
                    self.config_cache[config_name] = {}
                    logger.warning(f"配置文件不存在: {config_path}")
            except Exception as e:
                logger.error(f"加载配置文件失败 {config_path}: {e}")
                self.config_cache[config_name] = {}
    
    def get_app_config(self):
        """获取应用配置"""
        return self.config_cache.get('app', {})
    
    def get_db_config(self):
        """获取数据库配置"""
        return self.config_cache.get('db', {})
    
    def get_model_config(self):
        """获取模型配置"""
        return self.config_cache.get('model', {})
    
    def get_prompt_config(self):
        """获取提示词配置"""
        return self.config_cache.get('prompt', {})
    
    def get_nested_value(self, path: str, default=None):
        """
        通过路径获取嵌套配置值
        
        Args:
            path: 配置路径，如 'model.embedding.dimensions'
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        try:
            parts = path.split('.')
            config_type = parts[0]
            
            if config_type not in self.config_cache:
                return default
            
            value = self.config_cache[config_type]
            for part in parts[1:]:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            
            return value
        except Exception as e:
            logger.debug(f"获取配置值失败 {path}: {e}")
            return default
    
    def reload_config(self):
        """重新加载配置"""
        self._load_all_configs()
        logger.info("配置已重新加载")

# 全局配置加载器实例
config_loader = ConfigLoader()