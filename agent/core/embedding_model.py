"""
Shared Embedding Model Manager

功能：
- 单例模式管理 SentenceTransformer 模型
- 避免 Memory 和 IntentRouter 重复加载模型导致内存浪费
- 线程安全的懒加载
"""

import logging
import threading
import time
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

# 全局单例实例
_shared_model_instance = None
_model_lock = threading.Lock()

class SharedEmbeddingModel:
    """
    共享嵌入模型管理器 (Singleton-ish)
    
    使用方式：
    model = SharedEmbeddingModel.get_instance()
    embedding = model.encode("text")
    """
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None
        self._ready_event = threading.Event()
        self._load_error: Optional[Exception] = None
        self._is_loading = False
        
    @classmethod
    def get_instance(cls, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> 'SharedEmbeddingModel':
        """获取或创建全局实例"""
        global _shared_model_instance
        with _model_lock:
            if _shared_model_instance is None:
                _shared_model_instance = cls(model_name)
            return _shared_model_instance

    def start_loading(self):
        """触发后台加载（如果是首次调用）"""
        with _model_lock:
            if self._model is not None or self._is_loading:
                return
            self._is_loading = True
            
        thread = threading.Thread(
            target=self._load_worker,
            name="SharedModelLoader",
            daemon=True
        )
        thread.start()
    
    def _load_worker(self):
        """后台加载工作线程"""
        try:
            # 自动安装依赖
            self._ensure_dependencies()
            
            logger.info(f"[SharedModel] 开始加载嵌入模型: {self.model_name}")
            start = time.time()
            
            # 延迟导入，避免启动时耗时
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            
            elapsed = time.time() - start
            logger.info(f"[SharedModel] 模型加载完成，耗时 {elapsed:.1f}s")
        except Exception as e:
            logger.error(f"[SharedModel] 模型加载失败: {e}", exc_info=True)
            self._load_error = e
        finally:
            self._ready_event.set()
            self._is_loading = False

    def _ensure_dependencies(self):
        """确保 sentence-transformers 已安装"""
        import importlib
        import subprocess
        import sys
        
        try:
            importlib.import_module("sentence_transformers")
            return
        except ImportError:
            logger.info("[SharedModel] 未检测到 sentence-transformers，尝试自动安装...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "sentence-transformers"])
                logger.info("[SharedModel] sentence-transformers 安装成功")
            except Exception as e:
                logger.error(f"[SharedModel] 自动安装依赖失败: {e}")
                raise

    def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """等待模型就绪"""
        if self._model is not None:
            return True
        return self._ready_event.wait(timeout=timeout)

    def encode(self, text: str) -> List[float]:
        """
        生成嵌入向量（单个文本）
        
        Returns:
            List[float]: 向量列表。如果出错或未就绪，返回空列表。
        """
        if not self.wait_until_ready(timeout=5): # 快速超时，避免阻塞太久
            return []
            
        if self._load_error:
            return []
            
        try:
            # SentenceTransformer encode 返回 numpy array 或 tensor
            # 这里的 .tolist() 确保返回标准 list
            if self._model:
                # 使用 convert_to_numpy=False 避免触发批量处理进度条
                return self._model.encode(text, convert_to_numpy=True, show_progress_bar=False).tolist()
        except Exception as e:
            logger.error(f"[SharedModel] 推理失败: {e}")
            return []
        
        return []
    
    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成嵌入向量（用于批量处理，更高效）
        
        Args:
            texts: 文本列表
            
        Returns:
            List[List[float]]: 向量列表的列表。如果出错或未就绪，返回空列表。
        """
        if not self.wait_until_ready(timeout=5):
            return []
            
        if self._load_error:
            return []
            
        try:
            if self._model:
                # 批量编码，但禁用进度条以避免 "Batches: 100%" 输出
                embeddings = self._model.encode(
                    texts, 
                    convert_to_numpy=True, 
                    show_progress_bar=False,  # 关键：禁用进度条
                    batch_size=32  # 合理的批次大小
                )
                return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"[SharedModel] 批量推理失败: {e}")
            return []
        
        return []
