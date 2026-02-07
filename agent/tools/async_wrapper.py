"""
异步包装器 - 将同步 LLM 调用包装为异步

功能：
- 使用线程池执行同步 API 调用，避免阻塞主线程
- 支持超时和取消
- 确保在请求大模型期间仍能响应其他请求
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class AsyncLLMWrapper:
    """
    异步 LLM 调用包装器
    
    使用线程池将同步的 LLM API 调用包装为异步调用，
    避免阻塞主线程，确保能响应其他请求。
    """
    
    def __init__(self, max_workers: int = 3):
        """
        初始化异步包装器
        
        Args:
            max_workers: 线程池最大工作线程数
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="LLM-Async")
        self._active_tasks = {}  # 跟踪活动任务
        self._lock = threading.Lock()
    
    def call_async(self, func: Callable, *args, timeout: Optional[float] = None, **kwargs) -> Any:
        """
        异步调用函数（使用线程池）
        
        Args:
            func: 要调用的函数
            *args: 位置参数
            timeout: 超时时间（秒），None 表示不超时
            **kwargs: 关键字参数
            
        Returns:
            函数返回值
            
        Raises:
            TimeoutError: 如果超时
            Exception: 函数执行时的异常
        """
        task_id = id(func)
        
        # 提交任务到线程池
        future = self.executor.submit(func, *args, **kwargs)
        
        with self._lock:
            self._active_tasks[task_id] = future
        
        try:
            # 等待结果（带超时）
            if timeout:
                result = future.result(timeout=timeout)
            else:
                result = future.result()
            
            return result
        except FutureTimeoutError:
            logger.error(f"[SECURITY_SHIELD] LLM 调用超时（{timeout}秒）")
            future.cancel()  # 尝试取消任务
            raise TimeoutError(f"LLM 调用超时（{timeout}秒）")
        except Exception as e:
            logger.error(f"[SECURITY_SHIELD] LLM 调用异常: {e}", exc_info=True)
            raise
        finally:
            with self._lock:
                self._active_tasks.pop(task_id, None)
    
    def shutdown(self, wait: bool = True):
        """关闭线程池"""
        self.executor.shutdown(wait=wait)
        logger.info("[SECURITY_SHIELD] 异步 LLM 包装器已关闭")


# 全局单例
_global_wrapper: Optional[AsyncLLMWrapper] = None
_wrapper_lock = threading.Lock()


def get_async_wrapper() -> AsyncLLMWrapper:
    """获取全局异步包装器实例"""
    global _global_wrapper
    with _wrapper_lock:
        if _global_wrapper is None:
            _global_wrapper = AsyncLLMWrapper()
        return _global_wrapper
