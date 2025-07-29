"""
资源管理器
根据硬件能力动态调整系统资源使用和处理策略
"""
import threading
import time
import logging
import psutil
from typing import Dict, Any, Optional, Callable, List
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
from utils.hardware_detector import hardware_detector
from utils.config_loader import config_loader

logger = logging.getLogger(__name__)

class ResourceManager:
    """系统资源管理器"""
    
    def __init__(self):
        self.hardware_info = {}
        self.current_config = {}
        self.processing_queue = Queue()
        self.active_tasks = {}
        self.thread_pool = None
        self.monitoring_thread = None
        self.is_monitoring = False
        self._lock = threading.Lock()
        
        # 性能阈值
        self.cpu_threshold = 80.0  # CPU使用率阈值
        self.memory_threshold = 85.0  # 内存使用率阈值
        self.gpu_memory_threshold = 90.0  # GPU显存使用率阈值
        
        # 自适应配置
        self.adaptive_config = {
            "max_concurrent_files": 1,
            "chunk_batch_size": 1, 
            "model_cache_limit": 1,
            "enable_gpu": False,
            "processing_timeout": 300  # 5分钟超时
        }
        
    def initialize(self, hardware_info: Dict[str, Any] = None) -> None:
        """
        初始化资源管理器
        
        Args:
            hardware_info: 硬件信息，如果为None则重新检测
        """
        logger.info("初始化资源管理器...")
        
        if hardware_info:
            self.hardware_info = hardware_info
        else:
            self.hardware_info = hardware_detector.detect_all()
        
        # 根据硬件信息设置初始配置
        self._setup_initial_config()
        
        # 启动监控线程
        self._start_monitoring()
        
        logger.info("资源管理器初始化完成")
    
    def _setup_initial_config(self) -> None:
        """根据硬件信息设置初始配置"""
        try:
            cpu_info = self.hardware_info.get("cpu", {})
            memory_info = self.hardware_info.get("memory", {})
            gpu_info = self.hardware_info.get("gpu", {})
            performance_score = self.hardware_info.get("performance_score", 50)
            
            logical_cores = cpu_info.get("logical_cores", 1)
            total_memory = memory_info.get("total_gb", 4)
            cuda_available = gpu_info.get("cuda_available", False)
            
            # 根据性能评分调整配置
            if performance_score >= 80:
                # 高性能配置
                self.adaptive_config.update({
                    "max_concurrent_files": min(4, logical_cores // 2),
                    "chunk_batch_size": min(8, logical_cores),
                    "model_cache_limit": 3,
                    "enable_gpu": cuda_available,
                    "processing_timeout": 600
                })
            elif performance_score >= 50:
                # 平衡配置
                self.adaptive_config.update({
                    "max_concurrent_files": min(2, logical_cores // 2),
                    "chunk_batch_size": min(4, logical_cores),
                    "model_cache_limit": 2,
                    "enable_gpu": cuda_available and total_memory >= 8,
                    "processing_timeout": 450
                })
            else:
                # 保守配置
                self.adaptive_config.update({
                    "max_concurrent_files": 1,
                    "chunk_batch_size": 1,
                    "model_cache_limit": 1,
                    "enable_gpu": False,
                    "processing_timeout": 300
                })
            
            # 创建线程池
            max_workers = self.adaptive_config["max_concurrent_files"]
            self.thread_pool = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="ResourceManager"
            )
            
            logger.info(f"资源配置: 最大并发={max_workers}, 批处理大小={self.adaptive_config['chunk_batch_size']}, GPU={'启用' if self.adaptive_config['enable_gpu'] else '禁用'}")
            
        except Exception as e:
            logger.error(f"设置初始配置失败: {e}")
            # 使用默认保守配置
            self.thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ResourceManager")
    
    def _start_monitoring(self) -> None:
        """启动系统监控线程"""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(
            target=self._monitor_system_resources,
            name="ResourceMonitor",
            daemon=True
        )
        self.monitoring_thread.start()
        logger.info("系统资源监控已启动")
    
    def _monitor_system_resources(self) -> None:
        """监控系统资源使用情况"""
        while self.is_monitoring:
            try:
                # 获取当前系统状态
                cpu_percent = psutil.cpu_percent(interval=1)
                memory_percent = psutil.virtual_memory().percent
                
                # 检查GPU状态（如果可用）
                gpu_memory_percent = 0
                if self.adaptive_config["enable_gpu"]:
                    gpu_memory_percent = self._get_gpu_memory_usage()
                
                # 检查是否需要调整配置
                needs_adjustment = (
                    cpu_percent > self.cpu_threshold or
                    memory_percent > self.memory_threshold or
                    gpu_memory_percent > self.gpu_memory_threshold
                )
                
                if needs_adjustment:
                    self._adjust_performance_config(cpu_percent, memory_percent, gpu_memory_percent)
                
                # 记录资源使用情况
                logger.debug(f"资源监控: CPU={cpu_percent}%, 内存={memory_percent}%, GPU显存={gpu_memory_percent}%")
                
                # 监控间隔
                time.sleep(10)
                
            except Exception as e:
                logger.warning(f"资源监控异常: {e}")
                time.sleep(30)  # 异常时延长监控间隔
    
    def _get_gpu_memory_usage(self) -> float:
        """获取GPU显存使用率"""
        try:
            import torch
            if torch.cuda.is_available():
                device_count = torch.cuda.device_count()
                if device_count > 0:
                    memory_info = torch.cuda.mem_get_info(0)  # 获取第一块GPU的信息
                    free_memory = memory_info[0]
                    total_memory = memory_info[1]
                    used_memory = total_memory - free_memory
                    return (used_memory / total_memory) * 100
        except Exception as e:
            logger.debug(f"获取GPU显存使用率失败: {e}")
        return 0
    
    def _adjust_performance_config(self, cpu_percent: float, memory_percent: float, gpu_memory_percent: float) -> None:
        """根据资源使用情况调整性能配置"""
        with self._lock:
            adjusted = False
            
            # CPU使用率过高
            if cpu_percent > self.cpu_threshold:
                if self.adaptive_config["max_concurrent_files"] > 1:
                    self.adaptive_config["max_concurrent_files"] -= 1
                    adjusted = True
                    logger.info(f"CPU使用率过高({cpu_percent}%)，减少并发文件数至{self.adaptive_config['max_concurrent_files']}")
                
                if self.adaptive_config["chunk_batch_size"] > 1:
                    self.adaptive_config["chunk_batch_size"] = max(1, self.adaptive_config["chunk_batch_size"] // 2)
                    adjusted = True
                    logger.info(f"减少批处理大小至{self.adaptive_config['chunk_batch_size']}")
            
            # 内存使用率过高
            if memory_percent > self.memory_threshold:
                if self.adaptive_config["model_cache_limit"] > 1:
                    self.adaptive_config["model_cache_limit"] -= 1
                    adjusted = True
                    logger.info(f"内存使用率过高({memory_percent}%)，减少模型缓存至{self.adaptive_config['model_cache_limit']}")
                
                if self.adaptive_config["chunk_batch_size"] > 1:
                    self.adaptive_config["chunk_batch_size"] = max(1, self.adaptive_config["chunk_batch_size"] // 2)
                    adjusted = True
            
            # GPU显存使用率过高
            if gpu_memory_percent > self.gpu_memory_threshold and self.adaptive_config["enable_gpu"]:
                self.adaptive_config["enable_gpu"] = False
                adjusted = True
                logger.info(f"GPU显存使用率过高({gpu_memory_percent}%)，切换到CPU模式")
            
            # 重建线程池（如果并发数改变）
            if adjusted and "max_concurrent_files" in locals():
                self._rebuild_thread_pool()
    
    def _rebuild_thread_pool(self) -> None:
        """重建线程池"""
        try:
            if self.thread_pool:
                self.thread_pool.shutdown(wait=True)
            
            max_workers = self.adaptive_config["max_concurrent_files"]
            self.thread_pool = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="ResourceManager"
            )
            logger.info(f"线程池已重建，最大工作线程: {max_workers}")
            
        except Exception as e:
            logger.error(f"重建线程池失败: {e}")
    
    def submit_task(self, task_id: str, task_func: Callable, *args, **kwargs) -> bool:
        """
        提交任务到资源管理器
        
        Args:
            task_id: 任务ID
            task_func: 任务函数
            *args: 任务参数
            **kwargs: 任务关键字参数
            
        Returns:
            是否成功提交
        """
        try:
            with self._lock:
                # 检查当前任务数量
                active_count = len(self.active_tasks)
                max_concurrent = self.adaptive_config["max_concurrent_files"]
                
                if active_count >= max_concurrent:
                    logger.warning(f"达到最大并发限制({max_concurrent})，任务{task_id}等待中...")
                    return False
                
                # 包装任务函数
                wrapped_task = self._wrap_task(task_id, task_func, *args, **kwargs)
                
                # 提交任务
                future = self.thread_pool.submit(wrapped_task)
                self.active_tasks[task_id] = {
                    "future": future,
                    "start_time": time.time(),
                    "status": "running"
                }
                
                logger.info(f"任务{task_id}已提交，当前活跃任务数: {len(self.active_tasks)}")
                return True
                
        except Exception as e:
            logger.error(f"提交任务{task_id}失败: {e}")
            return False
    
    def _wrap_task(self, task_id: str, task_func: Callable, *args, **kwargs) -> Callable:
        """包装任务函数，添加监控和清理逻辑"""
        def wrapped():
            try:
                logger.info(f"开始执行任务: {task_id}")
                
                # 设置任务配置
                task_config = self.get_current_config()
                
                # 执行任务
                result = task_func(*args, config=task_config, **kwargs)
                
                # 更新任务状态
                with self._lock:
                    if task_id in self.active_tasks:
                        self.active_tasks[task_id]["status"] = "completed"
                
                logger.info(f"任务{task_id}执行完成")
                return result
                
            except Exception as e:
                logger.error(f"任务{task_id}执行失败: {e}")
                
                # 更新任务状态
                with self._lock:
                    if task_id in self.active_tasks:
                        self.active_tasks[task_id]["status"] = "failed"
                        self.active_tasks[task_id]["error"] = str(e)
                
                raise
            finally:
                # 清理任务记录
                with self._lock:
                    if task_id in self.active_tasks:
                        del self.active_tasks[task_id]
                
                logger.debug(f"任务{task_id}已清理，当前活跃任务数: {len(self.active_tasks)}")
        
        return wrapped
    
    def get_current_config(self) -> Dict[str, Any]:
        """获取当前自适应配置"""
        with self._lock:
            return self.adaptive_config.copy()
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        with self._lock:
            if task_id in self.active_tasks:
                task_info = self.active_tasks[task_id].copy()
                task_info["runtime"] = time.time() - task_info["start_time"]
                return task_info
            return None
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0)
            memory = psutil.virtual_memory()
            
            gpu_info = {}
            if self.adaptive_config["enable_gpu"]:
                gpu_info["memory_percent"] = self._get_gpu_memory_usage()
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "active_tasks": len(self.active_tasks),
                "max_concurrent": self.adaptive_config["max_concurrent_files"],
                "gpu_info": gpu_info,
                "config": self.adaptive_config.copy()
            }
            
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return {}
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            with self._lock:
                if task_id in self.active_tasks:
                    task_info = self.active_tasks[task_id]
                    future = task_info["future"]
                    
                    if future.cancel():
                        del self.active_tasks[task_id]
                        logger.info(f"任务{task_id}已取消")
                        return True
                    else:
                        logger.warning(f"任务{task_id}无法取消（可能已在执行中）")
                        return False
                else:
                    logger.warning(f"任务{task_id}不存在")
                    return False
                    
        except Exception as e:
            logger.error(f"取消任务{task_id}失败: {e}")
            return False
    
    def cleanup_expired_tasks(self) -> None:
        """清理超时任务"""
        try:
            with self._lock:
                current_time = time.time()
                timeout = self.adaptive_config["processing_timeout"]
                expired_tasks = []
                
                for task_id, task_info in self.active_tasks.items():
                    runtime = current_time - task_info["start_time"]
                    if runtime > timeout:
                        expired_tasks.append(task_id)
                
                for task_id in expired_tasks:
                    logger.warning(f"任务{task_id}执行超时，强制取消")
                    self.cancel_task(task_id)
                    
        except Exception as e:
            logger.error(f"清理超时任务失败: {e}")
    
    def shutdown(self) -> None:
        """关闭资源管理器"""
        logger.info("正在关闭资源管理器...")
        
        # 停止监控
        self.is_monitoring = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
        
        # 关闭线程池
        if self.thread_pool:
            self.thread_pool.shutdown(wait=True)
        
        # 清理任务
        with self._lock:
            self.active_tasks.clear()
        
        logger.info("资源管理器已关闭")
    
    def force_conservative_mode(self) -> None:
        """强制进入保守模式"""
        logger.info("强制进入保守模式")
        with self._lock:
            self.adaptive_config.update({
                "max_concurrent_files": 1,
                "chunk_batch_size": 1,
                "model_cache_limit": 1,
                "enable_gpu": False,
                "processing_timeout": 180
            })
            self._rebuild_thread_pool()
    
    def suggest_system_optimization(self) -> List[str]:
        """基于当前状态提供系统优化建议"""
        suggestions = []
        
        try:
            system_status = self.get_system_status()
            cpu_percent = system_status.get("cpu_percent", 0)
            memory_percent = system_status.get("memory_percent", 0)
            
            if cpu_percent > 80:
                suggestions.append("CPU使用率过高，建议减少并发处理或升级CPU")
            
            if memory_percent > 85:
                suggestions.append("内存使用率过高，建议增加内存或减少模型缓存")
            
            if len(self.active_tasks) >= self.adaptive_config["max_concurrent_files"]:
                suggestions.append("已达到最大并发限制，考虑优化处理效率")
            
            performance_score = self.hardware_info.get("performance_score", 50)
            if performance_score < 40:
                suggestions.append("系统性能较低，建议升级硬件或优化配置")
            
        except Exception as e:
            logger.error(f"生成优化建议失败: {e}")
            suggestions.append("系统状态检查异常，建议重启服务")
        
        return suggestions

# 全局资源管理器实例
resource_manager = ResourceManager() 