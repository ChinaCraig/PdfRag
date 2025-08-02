"""
异步处理器 - GPU批量优化
支持异步任务队列和GPU批处理
"""
import asyncio
import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import List, Dict, Any, Optional, Callable, Union
from dataclasses import dataclass
from datetime import datetime
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

logger = logging.getLogger(__name__)

@dataclass
class ProcessingTask:
    """处理任务"""
    task_id: str
    task_type: str  # 'embedding', 'ocr', 'image_analysis', etc.
    data: Any
    priority: int = 0
    created_at: datetime = None
    callback: Optional[Callable] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

class AsyncProcessor:
    """异步处理器 - 支持GPU批处理"""
    
    def __init__(self):
        self.task_queue = asyncio.Queue()
        self.result_cache = {}
        self.workers = {}
        self.batch_processors = {}
        self.gpu_available = TORCH_AVAILABLE and torch.cuda.is_available()
        if TORCH_AVAILABLE:
            self.device = torch.device("cuda" if self.gpu_available else "cpu")
        else:
            self.device = "cpu"
        
        # 批处理配置
        self.batch_configs = {
            'embedding': {
                'batch_size': 32 if self.gpu_available else 8,
                'max_wait_time': 2.0,  # 最大等待时间（秒）
                'max_tokens': 512
            },
            'image_analysis': {
                'batch_size': 8 if self.gpu_available else 2,
                'max_wait_time': 5.0
            },
            'ocr': {
                'batch_size': 4,
                'max_wait_time': 3.0
            }
        }
        
        # 初始化批处理器
        self._init_batch_processors()
        
        logger.info(f"AsyncProcessor初始化完成 - GPU: {self.gpu_available}, Device: {self.device}")
    
    def _init_batch_processors(self):
        """初始化批处理器"""
        for task_type, config in self.batch_configs.items():
            self.batch_processors[task_type] = BatchProcessor(
                task_type=task_type,
                batch_size=config['batch_size'],
                max_wait_time=config['max_wait_time'],
                device=self.device
            )
    
    async def submit_task(self, task: ProcessingTask) -> str:
        """提交任务"""
        await self.task_queue.put(task)
        logger.debug(f"任务已提交: {task.task_id} ({task.task_type})")
        return task.task_id
    
    async def batch_submit_tasks(self, tasks: List[ProcessingTask]) -> List[str]:
        """批量提交任务"""
        task_ids = []
        for task in tasks:
            task_id = await self.submit_task(task)
            task_ids.append(task_id)
        return task_ids
    
    async def get_result(self, task_id: str, timeout: float = 30.0) -> Any:
        """获取任务结果"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if task_id in self.result_cache:
                result = self.result_cache.pop(task_id)
                return result
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"任务 {task_id} 超时")
    
    async def start_workers(self, num_workers: int = 3):
        """启动工作线程"""
        workers = []
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            workers.append(worker)
            self.workers[f"worker-{i}"] = worker
        
        logger.info(f"启动了 {num_workers} 个工作线程")
        return workers
    
    async def _worker(self, worker_name: str):
        """工作线程"""
        logger.info(f"工作线程 {worker_name} 启动")
        
        while True:
            try:
                task = await self.task_queue.get()
                
                if task is None:  # 停止信号
                    break
                
                logger.debug(f"{worker_name} 处理任务: {task.task_id}")
                
                # 根据任务类型选择处理器
                if task.task_type in self.batch_processors:
                    result = await self._process_with_batch(task)
                else:
                    result = await self._process_single_task(task)
                
                # 存储结果
                self.result_cache[task.task_id] = result
                
                # 调用回调
                if task.callback:
                    try:
                        task.callback(task.task_id, result)
                    except Exception as e:
                        logger.error(f"回调执行失败: {e}")
                
                self.task_queue.task_done()
                
            except Exception as e:
                logger.error(f"工作线程 {worker_name} 错误: {e}")
                await asyncio.sleep(1)
    
    async def _process_with_batch(self, task: ProcessingTask) -> Any:
        """使用批处理器处理任务"""
        batch_processor = self.batch_processors[task.task_type]
        return await batch_processor.process_task(task)
    
    async def _process_single_task(self, task: ProcessingTask) -> Any:
        """处理单个任务"""
        try:
            if task.task_type == 'general':
                # 通用处理逻辑
                return await self._process_general_task(task)
            else:
                logger.warning(f"未知任务类型: {task.task_type}")
                return {"error": f"未知任务类型: {task.task_type}"}
        except Exception as e:
            logger.error(f"任务处理失败 {task.task_id}: {e}")
            return {"error": str(e)}
    
    async def _process_general_task(self, task: ProcessingTask) -> Any:
        """处理通用任务"""
        # 这里可以添加通用任务处理逻辑
        await asyncio.sleep(0.1)  # 模拟处理时间
        return {"status": "completed", "data": task.data}
    
    async def stop(self):
        """停止处理器"""
        # 发送停止信号
        for _ in self.workers:
            await self.task_queue.put(None)
        
        # 等待工作线程结束
        for worker in self.workers.values():
            await worker
        
        logger.info("AsyncProcessor 已停止")

class BatchProcessor:
    """批处理器"""
    
    def __init__(self, task_type: str, batch_size: int, max_wait_time: float, device):
        self.task_type = task_type
        self.batch_size = batch_size
        self.max_wait_time = max_wait_time
        self.device = device
        
        self.pending_tasks = []
        self.processing_lock = asyncio.Lock()
        
        logger.debug(f"BatchProcessor初始化: {task_type}, batch_size={batch_size}, device={device}")
    
    async def process_task(self, task: ProcessingTask) -> Any:
        """处理任务（可能批处理）"""
        async with self.processing_lock:
            self.pending_tasks.append(task)
            
            # 检查是否需要立即处理批次
            if (len(self.pending_tasks) >= self.batch_size or 
                self._should_process_batch()):
                
                return await self._process_batch()
            else:
                # 等待更多任务或超时
                return await self._wait_for_batch(task)
    
    def _should_process_batch(self) -> bool:
        """判断是否应该处理批次"""
        if not self.pending_tasks:
            return False
        
        oldest_task = min(self.pending_tasks, key=lambda t: t.created_at)
        wait_time = (datetime.now() - oldest_task.created_at).total_seconds()
        
        return wait_time >= self.max_wait_time
    
    async def _wait_for_batch(self, task: ProcessingTask) -> Any:
        """等待批处理"""
        start_time = time.time()
        
        while time.time() - start_time < self.max_wait_time:
            if len(self.pending_tasks) >= self.batch_size:
                break
            await asyncio.sleep(0.1)
        
        return await self._process_batch()
    
    async def _process_batch(self) -> Any:
        """处理批次"""
        if not self.pending_tasks:
            return None
        
        # 取出批次任务
        batch_tasks = self.pending_tasks[:self.batch_size]
        self.pending_tasks = self.pending_tasks[self.batch_size:]
        
        logger.debug(f"批处理 {self.task_type}: {len(batch_tasks)} 个任务")
        
        try:
            if self.task_type == 'embedding':
                return await self._process_embedding_batch(batch_tasks)
            elif self.task_type == 'image_analysis':
                return await self._process_image_batch(batch_tasks)
            elif self.task_type == 'ocr':
                return await self._process_ocr_batch(batch_tasks)
            else:
                return await self._process_generic_batch(batch_tasks)
        
        except Exception as e:
            logger.error(f"批处理失败 {self.task_type}: {e}")
            return {"error": str(e)}
    
    async def _process_embedding_batch(self, tasks: List[ProcessingTask]) -> List[Any]:
        """批处理嵌入向量"""
        try:
            # 提取文本
            texts = [task.data['text'] for task in tasks]
            
            # GPU批处理逻辑
            if str(self.device).startswith('cuda'):
                results = await self._gpu_batch_embedding(texts)
            else:
                results = await self._cpu_batch_embedding(texts)
            
            # 为每个任务返回对应结果
            task_results = []
            for i, task in enumerate(tasks):
                task_result = {
                    'task_id': task.task_id,
                    'embedding': results[i] if i < len(results) else None,
                    'status': 'completed' if i < len(results) else 'failed'
                }
                task_results.append(task_result)
            
            return task_results
        
        except Exception as e:
            logger.error(f"嵌入向量批处理失败: {e}")
            return [{'task_id': task.task_id, 'error': str(e)} for task in tasks]
    
    async def _gpu_batch_embedding(self, texts: List[str]) -> List[List[float]]:
        """GPU批处理嵌入向量"""
        # 这里需要集成实际的嵌入模型
        # 示例：使用sentence-transformers的GPU加速
        try:
            from utils.model_manager import model_manager
            
            # 自动切片长文本
            processed_texts = []
            for text in texts:
                if len(text) > 512:  # 假设模型最大长度为512
                    # 切片处理
                    chunks = [text[i:i+512] for i in range(0, len(text), 512)]
                    processed_texts.extend(chunks)
                else:
                    processed_texts.append(text)
            
            # 批量生成嵌入
            embeddings = model_manager.get_embedding(processed_texts)
            
            # 如果有切片，需要合并或选择代表性嵌入
            if len(processed_texts) > len(texts):
                # 简化：取第一个切片的嵌入
                embeddings = embeddings[:len(texts)]
            
            return embeddings
        
        except Exception as e:
            logger.error(f"GPU嵌入处理失败: {e}")
            raise
    
    async def _cpu_batch_embedding(self, texts: List[str]) -> List[List[float]]:
        """CPU批处理嵌入向量"""
        try:
            from utils.model_manager import model_manager
            return model_manager.get_embedding(texts)
        except Exception as e:
            logger.error(f"CPU嵌入处理失败: {e}")
            raise
    
    async def _process_image_batch(self, tasks: List[ProcessingTask]) -> List[Any]:
        """批处理图像分析"""
        # 图像分析批处理逻辑
        results = []
        for task in tasks:
            try:
                # 这里集成图像分析模型
                result = {
                    'task_id': task.task_id,
                    'analysis': 'Image analysis result placeholder',
                    'status': 'completed'
                }
                results.append(result)
            except Exception as e:
                results.append({'task_id': task.task_id, 'error': str(e)})
        
        return results
    
    async def _process_ocr_batch(self, tasks: List[ProcessingTask]) -> List[Any]:
        """批处理OCR"""
        results = []
        for task in tasks:
            try:
                # 这里集成OCR模型
                result = {
                    'task_id': task.task_id,
                    'ocr_text': 'OCR result placeholder',
                    'status': 'completed'
                }
                results.append(result)
            except Exception as e:
                results.append({'task_id': task.task_id, 'error': str(e)})
        
        return results
    
    async def _process_generic_batch(self, tasks: List[ProcessingTask]) -> List[Any]:
        """通用批处理"""
        results = []
        for task in tasks:
            result = {
                'task_id': task.task_id,
                'data': task.data,
                'status': 'completed'
            }
            results.append(result)
        
        return results

# 全局异步处理器实例
async_processor = AsyncProcessor()

# 便捷函数
async def process_embeddings_async(texts: List[str]) -> List[List[float]]:
    """异步处理嵌入向量"""
    import uuid
    
    tasks = []
    for text in texts:
        task = ProcessingTask(
            task_id=str(uuid.uuid4()),
            task_type='embedding',
            data={'text': text}
        )
        tasks.append(task)
    
    # 提交任务
    task_ids = await async_processor.batch_submit_tasks(tasks)
    
    # 获取结果
    results = []
    for task_id in task_ids:
        result = await async_processor.get_result(task_id)
        if isinstance(result, list) and len(result) > 0:
            # 批处理结果
            embedding = result[0].get('embedding')
            if embedding:
                results.append(embedding)
        else:
            # 单个结果
            embedding = result.get('embedding')
            if embedding:
                results.append(embedding)
    
    return results

async def init_async_processing():
    """初始化异步处理"""
    await async_processor.start_workers(num_workers=3)
    logger.info("异步处理系统已启动")

async def shutdown_async_processing():
    """关闭异步处理"""
    await async_processor.stop()
    logger.info("异步处理系统已关闭")