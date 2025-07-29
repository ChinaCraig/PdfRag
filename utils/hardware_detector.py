"""
硬件检测工具类
检测系统硬件资源，为模型加载和处理策略提供依据
"""
import os
import platform
import psutil
import torch
import logging
from typing import Dict, Any, Tuple, Optional, List
import multiprocessing
import subprocess

logger = logging.getLogger(__name__)

class HardwareDetector:
    """硬件检测器"""
    
    def __init__(self):
        self.hardware_info = {}
        self.performance_score = 0
        self.recommendations = []
    
    def detect_all(self) -> Dict[str, Any]:
        """
        检测所有硬件信息
        
        Returns:
            硬件信息字典
        """
        logger.info("开始硬件检测...")
        
        self.hardware_info = {
            "system": self._detect_system_info(),
            "cpu": self._detect_cpu_info(),
            "memory": self._detect_memory_info(),
            "gpu": self._detect_gpu_info(),
            "storage": self._detect_storage_info(),
            "python": self._detect_python_env()
        }
        
        # 计算性能评分
        self.performance_score = self._calculate_performance_score()
        self.hardware_info["performance_score"] = self.performance_score
        
        # 生成建议
        self.recommendations = self._generate_recommendations()
        self.hardware_info["recommendations"] = self.recommendations
        
        logger.info(f"硬件检测完成，性能评分: {self.performance_score}/100")
        return self.hardware_info
    
    def _detect_system_info(self) -> Dict[str, str]:
        """检测系统信息"""
        try:
            return {
                "platform": platform.platform(),
                "system": platform.system(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "architecture": platform.architecture()[0],
                "python_version": platform.python_version()
            }
        except Exception as e:
            logger.warning(f"系统信息检测失败: {e}")
            return {}
    
    def _detect_cpu_info(self) -> Dict[str, Any]:
        """检测CPU信息"""
        try:
            # 基础CPU信息
            physical_cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
            logical_cores = psutil.cpu_count(logical=True) or 1
            
            cpu_info = {
                "physical_cores": physical_cores,
                "logical_cores": logical_cores,
                "usage_percent": psutil.cpu_percent(interval=1),
                "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None
            }
            
            # 尝试获取CPU频率信息
            try:
                cpu_freq = psutil.cpu_freq()
                if cpu_freq:
                    cpu_info["max_frequency"] = cpu_freq.max
                    cpu_info["current_frequency"] = cpu_freq.current
            except Exception as e:
                logger.debug(f"获取CPU频率失败: {e}")
                cpu_info["max_frequency"] = None
                cpu_info["current_frequency"] = None
            
            # 尝试获取更详细的CPU信息
            try:
                if platform.system() == "Linux":
                    with open('/proc/cpuinfo', 'r') as f:
                        cpuinfo = f.read()
                        if 'model name' in cpuinfo:
                            for line in cpuinfo.split('\n'):
                                if 'model name' in line:
                                    cpu_info["model_name"] = line.split(':')[1].strip()
                                    break
                elif platform.system() == "Darwin":  # macOS
                    result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        cpu_info["model_name"] = result.stdout.strip()
            except Exception as e:
                logger.debug(f"获取详细CPU信息失败: {e}")
            
            return cpu_info
        except Exception as e:
            logger.warning(f"CPU信息检测失败: {e}")
            # 返回默认值，确保系统能继续运行
            return {
                "physical_cores": 1,
                "logical_cores": 1,
                "max_frequency": None,
                "current_frequency": None,
                "usage_percent": 0,
                "load_average": None
            }
    
    def _detect_memory_info(self) -> Dict[str, Any]:
        """检测内存信息"""
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "usage_percent": memory.percent,
                "swap_total_gb": round(swap.total / (1024**3), 2),
                "swap_used_gb": round(swap.used / (1024**3), 2),
                "swap_percent": swap.percent
            }
        except Exception as e:
            logger.warning(f"内存信息检测失败: {e}")
            return {}
    
    def _detect_gpu_info(self) -> Dict[str, Any]:
        """检测GPU信息"""
        gpu_info = {
            "cuda_available": torch.cuda.is_available(),
            "gpu_count": 0,
            "gpus": []
        }
        
        try:
            if torch.cuda.is_available():
                gpu_info["gpu_count"] = torch.cuda.device_count()
                gpu_info["cuda_version"] = torch.version.cuda
                gpu_info["pytorch_version"] = torch.__version__
                
                for i in range(torch.cuda.device_count()):
                    gpu_properties = torch.cuda.get_device_properties(i)
                    memory_info = torch.cuda.mem_get_info(i)
                    
                    gpu_data = {
                        "id": i,
                        "name": gpu_properties.name,
                        "memory_total_gb": round(gpu_properties.total_memory / (1024**3), 2),
                        "memory_free_gb": round(memory_info[0] / (1024**3), 2),
                        "memory_used_gb": round((gpu_properties.total_memory - memory_info[0]) / (1024**3), 2),
                        "compute_capability": f"{gpu_properties.major}.{gpu_properties.minor}",
                        "multiprocessor_count": gpu_properties.multi_processor_count
                    }
                    gpu_info["gpus"].append(gpu_data)
            else:
                # 检查是否有GPU但没有CUDA支持
                try:
                    if platform.system() == "Linux":
                        result = subprocess.run(['lspci', '|', 'grep', '-i', 'vga'], 
                                              shell=True, capture_output=True, text=True)
                        if result.returncode == 0 and result.stdout:
                            gpu_info["note"] = "检测到GPU设备但CUDA不可用"
                except Exception:
                    pass
                    
        except Exception as e:
            logger.warning(f"GPU信息检测失败: {e}")
        
        return gpu_info
    
    def _detect_storage_info(self) -> Dict[str, Any]:
        """检测存储信息"""
        try:
            disk_usage = psutil.disk_usage('/')
            return {
                "total_gb": round(disk_usage.total / (1024**3), 2),
                "used_gb": round(disk_usage.used / (1024**3), 2),
                "free_gb": round(disk_usage.free / (1024**3), 2),
                "usage_percent": round((disk_usage.used / disk_usage.total) * 100, 1)
            }
        except Exception as e:
            logger.warning(f"存储信息检测失败: {e}")
            return {}
    
    def _detect_python_env(self) -> Dict[str, Any]:
        """检测Python环境信息"""
        try:
            return {
                "version": platform.python_version(),
                "implementation": platform.python_implementation(),
                "compiler": platform.python_compiler(),
                "multiprocessing_method": multiprocessing.get_start_method(),
                "max_workers": multiprocessing.cpu_count()
            }
        except Exception as e:
            logger.warning(f"Python环境检测失败: {e}")
            return {}
    
    def _calculate_performance_score(self) -> int:
        """
        计算系统性能评分 (0-100)
        考虑CPU、内存、GPU等因素
        """
        score = 0
        
        try:
            cpu_info = self.hardware_info.get("cpu", {})
            memory_info = self.hardware_info.get("memory", {})
            gpu_info = self.hardware_info.get("gpu", {})
            
            # CPU评分 (40%)
            cpu_score = 0
            logical_cores = cpu_info.get("logical_cores", 1)
            if logical_cores >= 16:
                cpu_score = 40
            elif logical_cores >= 8:
                cpu_score = 35
            elif logical_cores >= 4:
                cpu_score = 25
            else:
                cpu_score = 15
            
            # 内存评分 (30%)
            memory_score = 0
            total_memory = memory_info.get("total_gb", 0)
            if total_memory >= 32:
                memory_score = 30
            elif total_memory >= 16:
                memory_score = 25
            elif total_memory >= 8:
                memory_score = 20
            else:
                memory_score = 10
            
            # GPU评分 (30%)
            gpu_score = 0
            if gpu_info.get("cuda_available", False):
                gpu_count = gpu_info.get("gpu_count", 0)
                if gpu_count > 0:
                    gpus = gpu_info.get("gpus", [])
                    if gpus:
                        max_gpu_memory = max([gpu.get("memory_total_gb", 0) for gpu in gpus])
                        if max_gpu_memory >= 24:
                            gpu_score = 30
                        elif max_gpu_memory >= 12:
                            gpu_score = 25
                        elif max_gpu_memory >= 8:
                            gpu_score = 20
                        elif max_gpu_memory >= 4:
                            gpu_score = 15
                        else:
                            gpu_score = 10
            
            score = cpu_score + memory_score + gpu_score
            
            # 调整评分，确保在0-100范围内
            score = max(0, min(100, score))
            
        except Exception as e:
            logger.warning(f"性能评分计算失败: {e}")
            score = 50  # 默认中等评分
        
        return score
    
    def _generate_recommendations(self) -> List[str]:
        """根据硬件信息生成优化建议"""
        recommendations = []
        
        try:
            cpu_info = self.hardware_info.get("cpu", {})
            memory_info = self.hardware_info.get("memory", {})
            gpu_info = self.hardware_info.get("gpu", {})
            
            # CPU建议
            logical_cores = cpu_info.get("logical_cores", 1)
            if logical_cores < 4:
                recommendations.append("CPU核心数较少，建议启用轻量化处理模式")
            elif logical_cores >= 16:
                recommendations.append("CPU性能优秀，可以启用并行处理优化")
            
            # 内存建议
            total_memory = memory_info.get("total_gb", 0)
            if total_memory < 8:
                recommendations.append("内存容量不足，建议减少批处理大小和模型缓存")
            elif total_memory >= 32:
                recommendations.append("内存充足，可以启用大批量处理和模型预加载")
            
            # GPU建议
            if not gpu_info.get("cuda_available", False):
                recommendations.append("未检测到CUDA GPU，建议使用CPU优化模式")
            else:
                gpu_count = gpu_info.get("gpu_count", 0)
                if gpu_count > 0:
                    gpus = gpu_info.get("gpus", [])
                    if gpus:
                        max_gpu_memory = max([gpu.get("memory_total_gb", 0) for gpu in gpus])
                        if max_gpu_memory >= 12:
                            recommendations.append("GPU显存充足，可以启用GPU加速和大模型")
                        elif max_gpu_memory >= 4:
                            recommendations.append("GPU显存适中，建议使用中等大小的模型")
                        else:
                            recommendations.append("GPU显存较小，建议使用轻量化模型")
            
            # 性能评分建议
            if self.performance_score < 30:
                recommendations.append("系统性能较低，强烈建议启用轻量化模式")
            elif self.performance_score > 80:
                recommendations.append("系统性能优秀，可以启用所有高级功能")
            
        except Exception as e:
            logger.warning(f"生成建议失败: {e}")
            recommendations.append("硬件检测异常，建议使用默认配置")
        
        return recommendations
    
    def get_recommended_config(self) -> Dict[str, Any]:
        """
        根据硬件信息生成推荐配置
        
        Returns:
            推荐的系统配置
        """
        config = {
            "gpu_acceleration": False,
            "batch_size": 1,
            "max_workers": 1,
            "model_cache_enabled": True,
            "processing_mode": "conservative",  # conservative, balanced, aggressive
            "preload_models": False  # 添加预加载模型配置
        }
        
        try:
            cpu_info = self.hardware_info.get("cpu", {})
            memory_info = self.hardware_info.get("memory", {})
            gpu_info = self.hardware_info.get("gpu", {})
            
            logical_cores = cpu_info.get("logical_cores", 1)
            total_memory = memory_info.get("total_gb", 0)
            cuda_available = gpu_info.get("cuda_available", False)
            
            # 根据性能评分设置处理模式
            if self.performance_score >= 80:
                config["processing_mode"] = "aggressive"
                config["batch_size"] = min(8, logical_cores)
                config["max_workers"] = min(4, logical_cores // 2)
            elif self.performance_score >= 50:
                config["processing_mode"] = "balanced"
                config["batch_size"] = min(4, logical_cores)
                config["max_workers"] = min(2, logical_cores // 4)
            else:
                config["processing_mode"] = "conservative"
                config["batch_size"] = 1
                config["max_workers"] = 1
            
            # GPU配置
            if cuda_available and gpu_info.get("gpu_count", 0) > 0:
                gpus = gpu_info.get("gpus", [])
                if gpus:
                    max_gpu_memory = max([gpu.get("memory_total_gb", 0) for gpu in gpus])
                    if max_gpu_memory >= 4:  # 至少4GB显存才建议启用GPU
                        config["gpu_acceleration"] = True
            
            # 根据性能和内存情况决定是否建议预加载模型
            if self.performance_score >= 60 and total_memory >= 8:
                config["preload_models"] = True
            
            logger.debug(f"硬件推荐配置: {config}")
            
            # 内存配置
            if total_memory < 8:
                config["model_cache_enabled"] = False
                config["batch_size"] = 1
            elif total_memory >= 16:
                config["model_cache_enabled"] = True
            
        except Exception as e:
            logger.warning(f"生成推荐配置失败: {e}")
        
        return config
    
    def check_requirements(self, min_requirements: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        检查是否满足最低硬件要求
        
        Args:
            min_requirements: 最低硬件要求
            
        Returns:
            (是否满足要求, 不满足的项目列表)
        """
        issues = []
        
        try:
            cpu_info = self.hardware_info.get("cpu", {})
            memory_info = self.hardware_info.get("memory", {})
            
            # 检查CPU
            min_cores = min_requirements.get("min_cpu_cores", 2)
            logical_cores = cpu_info.get("logical_cores", 0)
            if logical_cores < min_cores:
                issues.append(f"CPU核心数不足: 需要至少{min_cores}核心，当前{logical_cores}核心")
            
            # 检查内存
            min_memory = min_requirements.get("min_memory_gb", 4)
            total_memory = memory_info.get("total_gb", 0)
            if total_memory < min_memory:
                issues.append(f"内存不足: 需要至少{min_memory}GB，当前{total_memory}GB")
            
            # 检查可用内存
            available_memory = memory_info.get("available_gb", 0)
            min_available = min_requirements.get("min_available_memory_gb", 2)
            if available_memory < min_available:
                issues.append(f"可用内存不足: 需要至少{min_available}GB，当前{available_memory}GB")
            
        except Exception as e:
            logger.warning(f"硬件要求检查失败: {e}")
            issues.append("硬件检测异常，无法验证要求")
        
        return len(issues) == 0, issues
    
    def generate_report(self) -> str:
        """生成硬件检测报告"""
        if not self.hardware_info:
            return "硬件信息未检测"
        
        report_lines = [
            "=" * 60,
            "硬件检测报告",
            "=" * 60,
            ""
        ]
        
        # 系统信息
        system_info = self.hardware_info.get("system", {})
        if system_info:
            report_lines.extend([
                "📟 系统信息:",
                f"  操作系统: {system_info.get('platform', 'Unknown')}",
                f"  架构: {system_info.get('architecture', 'Unknown')}",
                f"  Python版本: {system_info.get('python_version', 'Unknown')}",
                ""
            ])
        
        # CPU信息
        cpu_info = self.hardware_info.get("cpu", {})
        if cpu_info:
            report_lines.extend([
                "🔧 CPU信息:",
                f"  型号: {cpu_info.get('model_name', 'Unknown')}",
                f"  物理核心: {cpu_info.get('physical_cores', 'Unknown')}",
                f"  逻辑核心: {cpu_info.get('logical_cores', 'Unknown')}",
                f"  当前使用率: {cpu_info.get('usage_percent', 0)}%",
                ""
            ])
        
        # 内存信息
        memory_info = self.hardware_info.get("memory", {})
        if memory_info:
            report_lines.extend([
                "💾 内存信息:",
                f"  总内存: {memory_info.get('total_gb', 0)}GB",
                f"  可用内存: {memory_info.get('available_gb', 0)}GB",
                f"  使用率: {memory_info.get('usage_percent', 0)}%",
                ""
            ])
        
        # GPU信息
        gpu_info = self.hardware_info.get("gpu", {})
        if gpu_info:
            report_lines.extend([
                "🎮 GPU信息:",
                f"  CUDA可用: {'是' if gpu_info.get('cuda_available', False) else '否'}",
                f"  GPU数量: {gpu_info.get('gpu_count', 0)}",
            ])
            
            for gpu in gpu_info.get("gpus", []):
                report_lines.extend([
                    f"  GPU {gpu['id']}: {gpu['name']}",
                    f"    显存: {gpu['memory_total_gb']}GB (可用: {gpu['memory_free_gb']}GB)",
                ])
            report_lines.append("")
        
        # 性能评分
        report_lines.extend([
            f"📊 性能评分: {self.performance_score}/100",
            ""
        ])
        
        # 建议
        if self.recommendations:
            report_lines.extend([
                "💡 优化建议:",
            ])
            for rec in self.recommendations:
                report_lines.append(f"  • {rec}")
            report_lines.append("")
        
        report_lines.append("=" * 60)
        
        return "\n".join(report_lines)

# 全局硬件检测器实例
hardware_detector = HardwareDetector() 