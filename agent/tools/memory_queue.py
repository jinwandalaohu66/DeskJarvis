"""
线程安全记忆存储队列

功能：
- 使用队列缓冲记忆保存任务
- 后台线程处理队列，避免阻塞主流程
- 文件锁防止并发写入冲突
"""

import logging
import threading
import queue
import platform
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# 文件锁支持（Unix 使用 fcntl，Windows 使用 msvcrt）
try:
    if platform.system() != "Windows":
        import fcntl
        HAS_FLOCK = True
    else:
        import msvcrt
        HAS_FLOCK = True
except ImportError:
    HAS_FLOCK = False
    logger.warning("[SECURITY_SHIELD] 文件锁不可用，将使用队列同步")


class ThreadSafeMemoryQueue:
    """
    线程安全记忆存储队列
    
    使用队列 + 文件锁确保记忆存储的线程安全性。
    """
    
    def __init__(self, memory_manager, lock_file_path: Optional[Path] = None):
        """
        初始化队列
        
        Args:
            memory_manager: MemoryManager 实例
            lock_file_path: 文件锁路径（默认 ~/.deskjarvis/.memory_lock）
        """
        self.memory_manager = memory_manager
        self.queue: queue.Queue = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        if lock_file_path is None:
            lock_file_path = Path.home() / ".deskjarvis" / ".memory_lock"
        self.lock_file_path = lock_file_path
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 启动后台工作线程
        self._start_worker()
    
    def _start_worker(self):
        """启动后台工作线程"""
        if self.worker_thread and self.worker_thread.is_alive():
            return
        
        self._stop_event.clear()
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name="MemoryQueueWorker",
            daemon=True
        )
        self.worker_thread.start()
        logger.info("[SECURITY_SHIELD] 记忆存储队列工作线程已启动")
    
    def _worker_loop(self):
        """工作线程循环：处理队列中的任务"""
        while not self._stop_event.is_set():
            try:
                # 从队列获取任务（超时1秒，允许检查停止事件）
                try:
                    task = self.queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # 处理任务
                try:
                    self._process_task(task)
                except Exception as e:
                    logger.error(f"[SECURITY_SHIELD] 处理记忆存储任务失败: {e}", exc_info=True)
                finally:
                    self.queue.task_done()
            except Exception as e:
                logger.error(f"[SECURITY_SHIELD] 记忆存储队列工作线程异常: {e}", exc_info=True)
    
    def _process_task(self, task: Dict[str, Any]):
        """
        处理单个记忆存储任务（带文件锁）
        
        Args:
            task: 任务字典，包含 save_task_result 的参数
        """
        # 使用文件锁防止并发写入冲突
        lock_file = None
        try:
            if HAS_FLOCK:
                lock_file = open(self.lock_file_path, 'w')
                # 获取排他锁（阻塞直到获取）
                if platform.system() != "Windows":
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                else:
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                
                logger.debug("[SECURITY_SHIELD] 已获取记忆存储文件锁")
            
            # 执行保存操作
            self.memory_manager.save_task_result(
                instruction=task.get("instruction"),
                steps=task.get("steps", []),
                result=task.get("result"),
                success=task.get("success", True),
                duration=task.get("duration", 0.0),
                files_involved=task.get("files_involved", [])
            )
            
            logger.debug("[SECURITY_SHIELD] 记忆存储完成")
        except Exception as e:
            logger.error(f"[SECURITY_SHIELD] 记忆存储失败: {e}", exc_info=True)
        finally:
            # 释放文件锁
            if lock_file and HAS_FLOCK:
                try:
                    if platform.system() != "Windows":
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    else:
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    lock_file.close()
                except Exception:
                    pass
    
    def enqueue_save(self, instruction: str, steps: List[Dict], result: Dict, 
                     success: bool, duration: float, files_involved: List[str] = None):
        """
        将记忆保存任务加入队列（非阻塞）
        
        Args:
            instruction: 用户指令
            steps: 步骤列表
            result: 执行结果
            success: 是否成功
            duration: 执行时长
            files_involved: 涉及的文件列表
        """
        task = {
            "instruction": instruction,
            "steps": steps,
            "result": result,
            "success": success,
            "duration": duration,
            "files_involved": files_involved or []
        }
        
        try:
            self.queue.put(task, block=False)
            logger.debug("[SECURITY_SHIELD] 记忆保存任务已加入队列")
        except queue.Full:
            logger.warning("[SECURITY_SHIELD] 记忆存储队列已满，任务被丢弃")
    
    def shutdown(self, wait: bool = True):
        """
        关闭队列（等待所有任务完成）
        
        Args:
            wait: 是否等待队列清空
        """
        if wait:
            logger.info("[SECURITY_SHIELD] 等待记忆存储队列清空...")
            self.queue.join()
        
        self._stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=5.0)
        
        logger.info("[SECURITY_SHIELD] 记忆存储队列已关闭")
