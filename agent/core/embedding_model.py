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
import os
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
        
        # 🔴 CRITICAL: 检查是否强制离线模式（通过环境变量）
        self._force_offline = os.environ.get("HF_HUB_OFFLINE", "").lower() in ("1", "true", "yes")
        if self._force_offline:
            logger.info("[SharedModel] 检测到 HF_HUB_OFFLINE=1，将强制使用离线模式")
        
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
        logger.info("[SECURITY_SHIELD] 嵌入模型后台预热已启动（非阻塞）")
    
    def _load_worker(self):
        """后台加载工作线程"""
        try:
            # 自动安装依赖
            self._ensure_dependencies()
            
            # 🔴 CRITICAL: 配置 Hugging Face Hub 环境变量，增强网络稳定性
            self._configure_hf_environment()
            
            logger.info(f"[SharedModel] 开始加载嵌入模型: {self.model_name}")
            start = time.time()
            
            # 延迟导入，避免启动时耗时
            from sentence_transformers import SentenceTransformer
            
            # 🔴 CRITICAL: 使用重试机制加载模型，处理网络错误
            self._model = self._load_model_with_retry(SentenceTransformer)
            
            elapsed = time.time() - start
            logger.info(f"[SharedModel] 模型加载完成，耗时 {elapsed:.1f}s")
        except Exception as e:
            logger.error(f"[SharedModel] 模型加载失败: {e}", exc_info=True)
            self._load_error = e
            # 🔴 CRITICAL: 即使加载失败，也标记为就绪，避免阻塞其他功能
            logger.warning("[SharedModel] 模型加载失败，将使用降级方案（意图路由可能受影响）")
        finally:
            self._ready_event.set()
            self._is_loading = False
    
    def _configure_hf_environment(self):
        """配置 Hugging Face Hub 环境变量，增强网络稳定性"""
        # 设置本地缓存目录（避免重复下载）
        cache_dir = os.path.expanduser("~/.cache/huggingface")
        os.makedirs(cache_dir, exist_ok=True)
        
        # 设置环境变量
        os.environ.setdefault("HF_HOME", cache_dir)
        os.environ.setdefault("TRANSFORMERS_CACHE", cache_dir)
        os.environ.setdefault("HF_HUB_CACHE", cache_dir)
        
        # 🔴 CRITICAL: 增加超时和重试配置
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")  # 5分钟超时
        os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "10")  # ETag 超时
        
        # 禁用进度条（避免输出干扰）
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        
        # 🔴 CRITICAL: 优先使用本地缓存，如果本地有模型则强制离线模式
        # 检查本地是否有模型缓存
        model_cache_path = os.path.join(cache_dir, "hub", "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2")
        if os.path.exists(model_cache_path):
            logger.info("[SharedModel] 检测到本地模型缓存，将优先使用离线模式")
            # 不设置 HF_HUB_OFFLINE=1，因为我们需要检查是否有完整模型
            # 但如果网络失败，会在重试时尝试离线模式
        
        logger.debug(f"[SharedModel] Hugging Face 缓存目录: {cache_dir}")
    
    def _load_model_with_retry(self, SentenceTransformer: Any, max_retries: int = 3) -> Any:
        """
        使用重试机制加载模型，处理网络错误
        
        Args:
            SentenceTransformer: SentenceTransformer 类
            max_retries: 最大重试次数
            
        Returns:
            SentenceTransformer 实例
            
        Raises:
            Exception: 如果所有重试都失败
        """
        last_error = None
        cache_folder = os.path.expanduser("~/.cache/huggingface")
        
        # 🔴 CRITICAL: 如果强制离线模式，直接使用离线模式
        if self._force_offline:
            logger.info("[SharedModel] 强制离线模式，直接使用本地缓存...")
            try:
                model = SentenceTransformer(
                    self.model_name,
                    cache_folder=cache_folder,
                    device="cpu"
                )
                logger.info("[SharedModel] ✅ 离线模式加载成功")
                return model
            except Exception as offline_error:
                logger.error(f"[SharedModel] ❌ 离线模式失败（本地可能没有完整缓存）: {offline_error}")
                raise RuntimeError(
                    f"离线模式加载失败: {offline_error}\n"
                    f"💡 请先在线下载模型，或手动下载到 ~/.cache/huggingface/"
                ) from offline_error
        
        # 🔴 CRITICAL: 首先尝试离线模式（如果本地有缓存）
        try:
            logger.info("[SharedModel] 首先尝试离线模式加载（如果本地有缓存）...")
            os.environ["HF_HUB_OFFLINE"] = "1"  # 临时强制离线模式
            model = SentenceTransformer(
                self.model_name,
                cache_folder=cache_folder,
                device="cpu"
            )
            logger.info("[SharedModel] ✅ 离线模式加载成功（使用本地缓存）")
            os.environ.pop("HF_HUB_OFFLINE", None)  # 恢复在线模式
            return model
        except Exception as offline_error:
            # 离线模式失败，继续尝试在线模式
            os.environ.pop("HF_HUB_OFFLINE", None)
            logger.debug(f"[SharedModel] 离线模式失败（可能没有本地缓存）: {offline_error}")
        
        # 在线模式重试
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[SharedModel] 尝试在线加载模型 (尝试 {attempt}/{max_retries})...")
                
                # 🔴 CRITICAL: 每次重试都创建新的 HTTP 客户端（避免客户端关闭问题）
                # 通过设置环境变量强制创建新客户端
                os.environ.pop("HF_HUB_OFFLINE", None)  # 确保在线模式
                
                model = SentenceTransformer(
                    self.model_name,
                    cache_folder=cache_folder,
                    device="cpu"  # 先使用 CPU，避免 MPS 设备问题
                )
                
                logger.info(f"[SharedModel] ✅ 模型加载成功 (尝试 {attempt})")
                return model
                
            except Exception as e:
                last_error = e
                error_msg = str(e)
                
                # 检查是否是网络相关错误
                is_network_error = any(keyword in error_msg.lower() for keyword in [
                    "ssl", "eof", "connection", "timeout", "closed", "http", "network", "client"
                ])
                
                if is_network_error:
                    logger.warning(f"[SharedModel] 网络错误 (尝试 {attempt}/{max_retries}): {error_msg[:100]}")
                    if attempt < max_retries:
                        # 指数退避：2秒、4秒、8秒（增加等待时间）
                        wait_time = 2 ** attempt
                        logger.info(f"[SharedModel] 等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        continue
                else:
                    # 非网络错误，直接抛出
                    logger.error(f"[SharedModel] 非网络错误，停止重试: {error_msg}")
                    raise
        
        # 🔴 CRITICAL: 所有在线重试都失败，最后尝试一次离线模式
        logger.warning("[SharedModel] 所有在线重试失败，最后尝试离线模式...")
        try:
            os.environ["HF_HUB_OFFLINE"] = "1"
            model = SentenceTransformer(
                self.model_name,
                cache_folder=cache_folder,
                device="cpu"
            )
            logger.info("[SharedModel] ✅ 最后尝试离线模式成功（使用不完整的本地缓存）")
            os.environ.pop("HF_HUB_OFFLINE", None)
            return model
        except Exception as final_error:
            os.environ.pop("HF_HUB_OFFLINE", None)
            logger.error(f"[SharedModel] ❌ 离线模式也失败: {final_error}")
        
        # 所有尝试都失败
        logger.error(f"[SharedModel] ❌ 模型加载完全失败，已重试 {max_retries} 次在线 + 2 次离线")
        raise RuntimeError(
            f"模型加载失败（已重试 {max_retries} 次在线 + 2 次离线）: {last_error}\n"
            f"💡 建议：\n"
            f"1. 检查网络连接\n"
            f"2. 手动下载模型到 ~/.cache/huggingface/\n"
            f"3. 或使用离线模式：设置环境变量 HF_HUB_OFFLINE=1"
        ) from last_error

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
        """
        等待模型就绪
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            True 如果模型已就绪，False 如果超时或加载失败
        """
        if self._model is not None:
            return True
        
        # 等待加载完成（或超时）
        is_ready = self._ready_event.wait(timeout=timeout)
        
        # 🔴 CRITICAL: 即使加载失败，也返回 True（避免阻塞），但会在 encode 时返回空列表
        # 这样可以让系统继续运行，只是意图路由功能会降级
        return is_ready

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
