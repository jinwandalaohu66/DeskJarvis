"""
Semantic Intent Router

功能：
- 基于语义相似度（Embedding）的意图识别
- 替代脆弱的正则匹配
- 支持意图注册和阈值控制
"""

import logging
import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from agent.core.embedding_model import SharedEmbeddingModel

logger = logging.getLogger(__name__)

@dataclass
class IntentMatch:
    intent_type: str
    confidence: float
    metadata: Dict[str, Any]
    is_fast_path: bool

class IntentRouter:
    """
    语义意图路由器
    """
    
    def __init__(self, embedding_model: SharedEmbeddingModel):
        self.embedding_model = embedding_model
        
        # 预定义意图库 (Canonical Examples)
        # 意图类型 -> [示例列表]
        self.intent_registry = {
            # 文本处理类
            "translate": [
                "Translate this to English", "翻译这段话", "How do you say X in Chinese?",
                "Translate the following text", "把这个翻译成英文", "英文翻译"
            ],
            "summarize": [
                "Summarize this text", "总结一下这段话", "Give me a summary",
                "概括核心内容", "提炼要点"
            ],
            "polish": [
                "Polish this text", "润色一下这段文字", "Make this sound more professional",
                "优化这段话的表达", "修改语法错误"
            ],
            
            # 系统操作类
            "screenshot": [
                "Take a screenshot", "Capture the screen", "截个图", "截屏",
                "Screenshot the desktop", "保存屏幕截图"
            ],
            "volume_control": [
                "Turn up the volume", "Mute the sound", "Volume down",
                "调大音量", "静音", "声音小一点"
            ],
            "brightness_control": [
                "Increase brightness", "Dim the screen", "Set brightness to 50%",
                "调亮屏幕", "屏幕太暗了", "亮度调高点"
            ],
            "system_info": [
                "Check disk usage", "Show battery status", "System information",
                "查看系统信息", "内存还剩多少", "电池状态"
            ],
            
            # 常见应用操作 (简单打开/关闭)
            "app_open": [
                "Open Safari", "Launch Calculator", "Open Discord",
                "打开浏览器", "启动计算器", "打开微信"
            ],
             "app_close": [
                "Close Safari", "Quit Music", "Kill the process",
                "关闭浏览器", "退出音乐", "关闭应用"
            ],
        }
        
        # 意图对应的元数据（处理函数映射等）
        # 新增：每个意图的 min_confidence 阈值（动态阈值）
        self.intent_metadata = {
            "translate": {"type": "text_process", "action": "translate", "min_confidence": 0.65},
            "summarize": {"type": "text_process", "action": "summarize", "min_confidence": 0.65},
            "polish": {"type": "text_process", "action": "polish", "min_confidence": 0.65},
            "screenshot": {"type": "screenshot_desktop", "action": "screenshot", "min_confidence": 0.6},
            "volume_control": {"type": "system_control", "action": "volume", "min_confidence": 0.6},
            "brightness_control": {"type": "system_control", "action": "brightness", "min_confidence": 0.6},
            "system_info": {"type": "system_control", "action": "sys_info", "min_confidence": 0.6},
            "app_open": {"type": "open_app", "action": "open", "min_confidence": 0.7},
            "app_close": {"type": "close_app", "action": "close", "min_confidence": 0.8},  # 应用关闭需要更高置信度
        }
        
        # 缓存意图的 Embeddings（延迟加载，避免启动时阻塞）
        self.intent_embeddings: Dict[str, np.ndarray] = {}
        self._embeddings_cached = False  # 标记是否已缓存
        
        # === 名词惩罚列表：自动生成文件后缀名关键词 ===
        self.file_keywords = self._generate_file_keywords()

    def _cache_embeddings(self):
        """预计算意图示例的 Embeddings（延迟加载）"""
        if self._embeddings_cached:
            return
            
        # 快速检查模型是否就绪，不等待
        if not self.embedding_model.wait_until_ready(timeout=0.1):
            # 模型未就绪，延迟到首次使用时再加载
            return

        # 批量编码所有示例，触发 SentenceTransformer 的批量处理
        all_examples = []
        intent_to_examples = {}
        for intent, examples in self.intent_registry.items():
            intent_to_examples[intent] = examples
            all_examples.extend(examples)
        
        # 批量编码（更高效）
        if all_examples:
            try:
                # 使用模型的批量编码功能
                all_embeddings = self.embedding_model.encode_batch(all_examples)
                if all_embeddings:
                    # 按意图分组
                    idx = 0
                    for intent, examples in intent_to_examples.items():
                        intent_embeddings = []
                        for _ in examples:
                            if idx < len(all_embeddings):
                                intent_embeddings.append(all_embeddings[idx])
                                idx += 1
                        if intent_embeddings:
                            self.intent_embeddings[intent] = np.array(intent_embeddings)
                    self._embeddings_cached = True
            except Exception as e:
                logger.warning(f"[IntentRouter] 批量编码失败，降级到逐个编码: {e}")
                # 降级到逐个编码
                for intent, examples in self.intent_registry.items():
                    embeddings = []
                    for ex in examples:
                        vec = self.embedding_model.encode(ex)
                        if vec:
                            embeddings.append(vec)
                    if embeddings:
                        self.intent_embeddings[intent] = np.array(embeddings)
                self._embeddings_cached = True
                
    def _generate_file_keywords(self) -> List[str]:
        """
        自动生成文件关键词列表（从常见文件后缀名）
        
        Returns:
            文件关键词列表
        """
        # 常见文件后缀名
        common_extensions = [
            # 文档类
            '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.pdf', '.txt', '.rtf', '.odt', '.ods',
            # 图片类
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff', '.heic',
            # 视频类
            '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v',
            # 音频类
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma',
            # 压缩类
            '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
            # 代码类
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.html', '.css', '.json', '.xml', '.yaml', '.yml',
            # 其他
            '.exe', '.dmg', '.pkg', '.deb', '.rpm', '.apk', '.ipa',
        ]
        
        # 文件相关中文关键词
        chinese_keywords = [
            '文件', '文档', '图片', '照片', '视频', '音频', '压缩包', '下载', '桌面',
            '删除', '路径', '文件夹', '目录', '保存', '打开文件'
        ]
        
        # 英文关键词
        english_keywords = [
            'file', 'document', 'image', 'photo', 'video', 'audio', 'archive', 'download', 'desktop',
            'delete', 'path', 'folder', 'directory', 'save', 'open file'
        ]
        
        # 合并所有关键词
        all_keywords = common_extensions + chinese_keywords + english_keywords
        
        logger.debug(f"[SECURITY_SHIELD] 自动生成文件关键词列表，共 {len(all_keywords)} 个")
        return all_keywords
    
    def _check_absolute_path(self, text: str) -> bool:
        """
        检测文本中是否包含绝对路径
        
        Args:
            text: 待检测文本
            
        Returns:
            是否包含绝对路径
        """
        import re
        # Unix 绝对路径：/Users/, /home/, /var/, /etc/, /tmp/, /opt/
        unix_pattern = r'/(Users|home|var|etc|tmp|opt|usr|bin|sbin|lib|mnt|media|root|srv|sys|dev|proc)/'
        # Windows 绝对路径：C:\, D:\, E:\ 等
        windows_pattern = r'[A-Z]:\\'
        
        if re.search(unix_pattern, text, re.IGNORECASE) or re.search(windows_pattern, text):
            return True
        return False
    
    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """计算余弦相似度"""
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return np.dot(v1, v2) / (norm1 * norm2)

    def detect(self, text: str, threshold: float = 0.65) -> Optional[IntentMatch]:
        """
        检测意图
        
        Args:
            text: 用户输入的指令
            threshold: 默认相似度阈值（如果意图没有 min_confidence，则使用此值）
            
        Returns:
            IntentMatch (如果匹配成功) 或 None
        """
        # 1. 简单预处理
        text = text.strip()
        if not text:
            return None
        
        # 1.5. 快速关键词匹配（避免触发语义计算）
        # 对于明显的邮件相关操作，直接返回，不触发 SentenceTransformer
        text_lower = text.lower()
        email_keywords = ["邮件", "email", "收件", "发件", "搜索邮件", "search_emails", "search emails"]
        if any(kw in text_lower for kw in email_keywords):
            # 邮件相关操作不需要语义路由，直接返回 None，走通用规划
            return None
            
        # 2. 延迟加载 Embeddings（首次使用时才计算）
        if not self.intent_embeddings:
             # 尝试补初始化
             self._cache_embeddings()
             
        # 如果模型还没好，降级到 None（走通用规划）
        if not self.intent_embeddings:
            logger.debug("[IntentRouter] 意图库 Embeddings 未就绪，跳过语义路由")
            return None
            
        query_vec = self.embedding_model.encode(text)
        if not query_vec:
            return None # 模型出错
            
        query_vec = np.array(query_vec)
        
        best_intent = None
        best_score = -1.0
        
        # 3. 计算与所有意图簇的相似度（取最大值）
        for intent, example_vecs in self.intent_embeddings.items():
            # 计算 query 与该意图所有示例的相似度，取最大值
            # 向量化计算: dot product
            # example_vecs shape: (N, D)
            # query_vec shape: (D,)
            
            # 归一化
            query_norm = np.linalg.norm(query_vec)
            example_norms = np.linalg.norm(example_vecs, axis=1)
            
            dots = np.dot(example_vecs, query_vec)
            if query_norm == 0:
                scores = np.zeros(len(dots))
            else:
                scores = dots / (example_norms * query_norm)
                
            max_score = np.max(scores)
            
            if max_score > best_score:
                best_score = max_score
                best_intent = intent
        
        # === 增强：名词冲突惩罚机制（使用自动生成的关键词列表）===
        # 如果意图是应用类（app_open/app_close），但用户输入包含文件类关键词，重罚
        if best_intent in ['app_open', 'app_close']:
            user_text = text_lower
            
            # 使用自动生成的文件关键词列表
            has_file_keyword = any(kw in user_text for kw in self.file_keywords)
            
            # 检测绝对路径
            has_absolute_path = self._check_absolute_path(text)
            
            if has_file_keyword or has_absolute_path:
                penalty = 0.4  # 扣掉 0.4 分
                best_score -= penalty
                reason = []
                if has_file_keyword:
                    reason.append("文件关键词")
                if has_absolute_path:
                    reason.append("绝对路径")
                logger.warning(f"[SECURITY_SHIELD] 应用类意图 '{best_intent}' 检测到冲突（{', '.join(reason)}），应用惩罚: -{penalty:.2f} (原分数: {best_score + penalty:.2f} -> {best_score:.2f})")
        
        # 确保分数不为负
        best_score = max(0.0, best_score)
                
        logger.info(f"[IntentRouter] 最佳匹配: {best_intent} (Score: {best_score:.2f})")
        
        # 4. 动态阈值判断（使用意图的 min_confidence，如果没有则使用默认 threshold）
        intent_meta = self.intent_metadata.get(best_intent, {})
        dynamic_threshold = intent_meta.get("min_confidence", threshold)
        
        logger.debug(f"[SECURITY_SHIELD] 意图 '{best_intent}' 动态阈值: {dynamic_threshold:.2f}, 实际分数: {best_score:.2f}")
        
        if best_score >= dynamic_threshold:
            meta = self.intent_metadata.get(best_intent, {})
            return IntentMatch(
                intent_type=best_intent,
                confidence=float(best_score),
                metadata=meta,
                is_fast_path=True # 目前注册的都是 Fast Path 意图
            )
        else:
            logger.debug(f"[SECURITY_SHIELD] 意图 '{best_intent}' 分数 {best_score:.2f} 低于阈值 {dynamic_threshold:.2f}，不匹配")
            
        return None
    
    def add_intent_example(self, intent: str, text: str) -> bool:
        """
        动态添加意图示例（热更新意图库）
        
        功能：
        - 允许系统在运行过程中通过用户的纠正行为，动态丰富 intent_registry
        - 自动重新计算该意图的 Embeddings
        
        Args:
            intent: 意图类型（必须是已存在的意图）
            text: 新的示例文本
            
        Returns:
            是否成功添加
        """
        if intent not in self.intent_registry:
            logger.warning(f"[SECURITY_SHIELD] 意图 '{intent}' 不存在，无法添加示例")
            return False
        
        if not text or not text.strip():
            logger.warning("[SECURITY_SHIELD] 示例文本为空，无法添加")
            return False
        
        # 添加到意图库
        if text not in self.intent_registry[intent]:
            self.intent_registry[intent].append(text.strip())
            logger.info(f"[SECURITY_SHIELD] 已添加意图 '{intent}' 的新示例: {text[:50]}...")
        else:
            logger.debug(f"[SECURITY_SHIELD] 示例已存在，跳过: {text[:50]}...")
            return True
        
        # 重新计算该意图的 Embeddings（延迟计算，不阻塞）
        try:
            # 如果 Embeddings 已缓存，需要更新
            if intent in self.intent_embeddings:
                # 计算新示例的 Embedding
                new_vec = self.embedding_model.encode(text.strip())
                if new_vec:
                    # 追加到现有 Embeddings
                    existing_vecs = self.intent_embeddings[intent]
                    new_vec_array = np.array([new_vec])
                    self.intent_embeddings[intent] = np.vstack([existing_vecs, new_vec_array])
                    logger.debug(f"[SECURITY_SHIELD] 已更新意图 '{intent}' 的 Embeddings")
        except Exception as e:
            logger.warning(f"[SECURITY_SHIELD] 更新意图 '{intent}' 的 Embeddings 失败: {e}")
            # 如果更新失败，清除缓存，下次使用时重新计算
            if intent in self.intent_embeddings:
                del self.intent_embeddings[intent]
                self._embeddings_cached = False
        
        return True
