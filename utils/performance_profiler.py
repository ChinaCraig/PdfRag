"""
性能分析器 - 实现性能监控和分析功能
"""

import time
import logging
import psutil
import threading
from typing import Dict, Any, Optional, Callable
from functools import wraps
from utils.config_loader import config_loader

logger = logging.getLogger(__name__)

class PerformanceProfiler:
    """性能分析器"""
    
    def __init__(self):
        self.enabled = False
        self.profiling_data = {}
        self.start_times = {}
        self.monitoring_thread = None
        self.is_monitoring = False
        self._lock = threading.Lock()
        
        # 从配置中读取设置
        self._load_config()
    
    def _load_config(self):
        """从配置文件加载性能分析设置"""
        try:
            app_config = config_loader.get_app_config()
            dev_config = app_config.get("development", {})
            perf_config = app_config.get("performance", {})
            
            self.enabled = dev_config.get("profiling_enabled", False)
            self.monitoring_enabled = perf_config.get("monitoring_enabled", False)
            self.log_interval = perf_config.get("performance_logging", {}).get("log_interval", 30)
            
            if self.enabled:
                logger.info("🔍 性能分析器已启用")
                print("🔍 性能分析器已启用")
                self.start_monitoring()
            
        except Exception as e:
            logger.error(f"加载性能分析配置失败: {e}")
    
    def start_monitoring(self):
        """启动性能监控"""
        if not self.enabled or self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(
            target=self._monitor_system_performance,
            name="PerformanceMonitor",
            daemon=True
        )
        self.monitoring_thread.start()
        logger.info("性能监控线程已启动")
    
    def _monitor_system_performance(self):
        """监控系统性能"""
        while self.is_monitoring:
            try:
                # 收集系统指标
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                performance_data = {
                    "timestamp": time.time(),
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_used_gb": memory.used / (1024**3),
                    "memory_total_gb": memory.total / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_used_gb": disk.used / (1024**3),
                    "disk_total_gb": disk.total / (1024**3)
                }
                
                # 记录性能数据
                with self._lock:
                    current_time = int(time.time())
                    self.profiling_data[current_time] = performance_data
                    
                    # 清理过期数据（保留最近1小时）
                    cutoff_time = current_time - 3600
                    expired_keys = [k for k in self.profiling_data.keys() if k < cutoff_time]
                    for key in expired_keys:
                        del self.profiling_data[key]
                
                # 检查是否需要输出性能日志
                if self.monitoring_enabled and cpu_percent > 80:
                    logger.warning(f"⚠️ 系统负载较高 - CPU: {cpu_percent:.1f}%, 内存: {memory.percent:.1f}%")
                
                time.sleep(self.log_interval)
                
            except Exception as e:
                logger.error(f"性能监控错误: {e}")
                time.sleep(10)
    
    def profile_function(self, func_name: str = None):
        """
        函数性能分析装饰器
        
        Args:
            func_name: 自定义函数名，默认使用实际函数名
        """
        def decorator(func: Callable) -> Callable:
            if not self.enabled:
                return func
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                name = func_name or f"{func.__module__}.{func.__name__}"
                
                start_time = time.time()
                start_cpu = psutil.cpu_percent()
                start_memory = psutil.virtual_memory().percent
                
                try:
                    result = func(*args, **kwargs)
                    success = True
                    error = None
                except Exception as e:
                    result = None
                    success = False
                    error = str(e)
                    raise
                finally:
                    end_time = time.time()
                    end_cpu = psutil.cpu_percent()
                    end_memory = psutil.virtual_memory().percent
                    
                    duration = end_time - start_time
                    cpu_delta = end_cpu - start_cpu
                    memory_delta = end_memory - start_memory
                    
                    # 记录性能数据
                    self.record_function_performance(name, {
                        "duration": duration,
                        "cpu_delta": cpu_delta,
                        "memory_delta": memory_delta,
                        "success": success,
                        "error": error,
                        "timestamp": start_time
                    })
                    
                    # 输出详细日志
                    if duration > 1.0:  # 只记录耗时超过1秒的函数
                        logger.info(f"🕐 {name} 执行时间: {duration:.2f}秒")
                        if cpu_delta > 10:
                            logger.info(f"📊 CPU增量: {cpu_delta:.1f}%")
                        if memory_delta > 5:
                            logger.info(f"💾 内存增量: {memory_delta:.1f}%")
                
                return result
            return wrapper
        return decorator
    
    def record_function_performance(self, func_name: str, data: Dict[str, Any]):
        """记录函数性能数据"""
        if not self.enabled:
            return
        
        with self._lock:
            if "functions" not in self.profiling_data:
                self.profiling_data["functions"] = {}
            
            if func_name not in self.profiling_data["functions"]:
                self.profiling_data["functions"][func_name] = []
            
            self.profiling_data["functions"][func_name].append(data)
            
            # 限制每个函数保留的记录数量
            if len(self.profiling_data["functions"][func_name]) > 100:
                self.profiling_data["functions"][func_name] = \
                    self.profiling_data["functions"][func_name][-50:]
    
    def start_timing(self, name: str):
        """开始计时"""
        if not self.enabled:
            return
        
        self.start_times[name] = {
            "time": time.time(),
            "cpu": psutil.cpu_percent(),
            "memory": psutil.virtual_memory().percent
        }
        logger.debug(f"⏱️ 开始计时: {name}")
    
    def end_timing(self, name: str):
        """结束计时"""
        if not self.enabled or name not in self.start_times:
            return
        
        start_data = self.start_times[name]
        duration = time.time() - start_data["time"]
        cpu_delta = psutil.cpu_percent() - start_data["cpu"]
        memory_delta = psutil.virtual_memory().percent - start_data["memory"]
        
        logger.info(f"⏱️ {name} 完成 - 耗时: {duration:.2f}秒")
        if cpu_delta > 5:
            logger.info(f"📊 CPU变化: {cpu_delta:+.1f}%")
        if memory_delta > 2:
            logger.info(f"💾 内存变化: {memory_delta:+.1f}%")
        
        del self.start_times[name]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        if not self.enabled:
            return {"enabled": False}
        
        with self._lock:
            summary = {
                "enabled": True,
                "monitoring_active": self.is_monitoring,
                "data_points": len(self.profiling_data),
                "active_timers": len(self.start_times)
            }
            
            # 系统性能统计
            if self.profiling_data:
                recent_data = list(self.profiling_data.values())[-10:]  # 最近10个数据点
                if recent_data and isinstance(recent_data[0], dict):
                    avg_cpu = sum(d.get("cpu_percent", 0) for d in recent_data) / len(recent_data)
                    avg_memory = sum(d.get("memory_percent", 0) for d in recent_data) / len(recent_data)
                    
                    summary.update({
                        "avg_cpu_percent": avg_cpu,
                        "avg_memory_percent": avg_memory
                    })
            
            # 函数性能统计
            functions_data = self.profiling_data.get("functions", {})
            if functions_data:
                summary["tracked_functions"] = len(functions_data)
                
                # 找出最耗时的函数
                slowest_functions = []
                for func_name, records in functions_data.items():
                    if records:
                        avg_duration = sum(r.get("duration", 0) for r in records[-10:]) / min(10, len(records))
                        slowest_functions.append((func_name, avg_duration))
                
                slowest_functions.sort(key=lambda x: x[1], reverse=True)
                summary["slowest_functions"] = slowest_functions[:5]
            
            return summary
    
    def stop_monitoring(self):
        """停止性能监控"""
        self.is_monitoring = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
        logger.info("性能监控已停止")
    
    def cleanup(self):
        """清理资源"""
        self.stop_monitoring()
        with self._lock:
            self.profiling_data.clear()
            self.start_times.clear()
        logger.info("性能分析器已清理")

# 全局性能分析器实例
performance_profiler = PerformanceProfiler() 