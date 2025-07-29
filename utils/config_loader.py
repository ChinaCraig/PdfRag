"""
配置加载工具类
用于加载YAML配置文件
"""
import yaml
import os
from typing import Dict, Any

class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self._configs = {}
    
    def load_config(self, config_name: str) -> Dict[str, Any]:
        """
        加载指定的配置文件
        
        Args:
            config_name: 配置文件名（不包含.yaml扩展名）
            
        Returns:
            配置字典
        """
        if config_name in self._configs:
            return self._configs[config_name]
        
        config_path = os.path.join(self.config_dir, f"{config_name}.yaml")
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        self._configs[config_name] = config
        return config
    
    def get_db_config(self) -> Dict[str, Any]:
        """获取数据库配置"""
        return self.load_config("db")
    
    def get_model_config(self) -> Dict[str, Any]:
        """获取模型配置"""
        return self.load_config("model")
    
    def get_app_config(self) -> Dict[str, Any]:
        """获取应用配置"""
        return self.load_config("config")
    
    def get_prompt_config(self) -> Dict[str, Any]:
        """获取提示词配置"""
        return self.load_config("prompt")
    
    def reload_config(self, config_name: str = None) -> None:
        """
        重新加载配置
        
        Args:
            config_name: 要重新加载的配置名，None表示重新加载所有
        """
        if config_name:
            if config_name in self._configs:
                del self._configs[config_name]
        else:
            self._configs.clear()
    
    def get_nested_value(self, path: str, default: Any = None) -> Any:
        """
        获取嵌套配置值
        
        Args:
            path: 配置路径，用点分隔，格式如 "model.embedding"
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        try:
            parts = path.split('.')
            config_name = parts[0]
            
            # 加载配置
            config = self.load_config(config_name)
            
            # 逐层获取嵌套值
            current = config
            for part in parts[1:]:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return default
            
            return current
            
        except Exception:
            return default

# 全局配置加载器实例
config_loader = ConfigLoader() 