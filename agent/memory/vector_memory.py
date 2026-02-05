"""
层2：向量记忆（Chroma）

功能：
- 语义搜索历史对话
- 相似任务匹配
- 记忆压缩与摘要
"""

import json
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import time

logger = logging.getLogger(__name__)

# 尝试导入向量库依赖
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("chromadb 未安装，向量记忆功能不可用。请运行: pip install chromadb")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning("sentence-transformers 未安装，请运行: pip install sentence-transformers")


class VectorMemory:
    """向量记忆 - Chroma 存储"""
    
    def __init__(self, db_path: Optional[Path] = None, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        初始化向量记忆
        
        Args:
            db_path: 数据库路径，默认 ~/.deskjarvis/vector_memory
            model_name: 嵌入模型名称
        """
        if not CHROMA_AVAILABLE:
            logger.error("chromadb 不可用，向量记忆功能禁用")
            self.enabled = False
            return
        
        if not EMBEDDINGS_AVAILABLE:
            logger.error("sentence-transformers 不可用，向量记忆功能禁用")
            self.enabled = False
            return
        
        self.enabled = True
        
        if db_path is None:
            db_path = Path.home() / ".deskjarvis" / "vector_memory"
        
        self.db_path = db_path
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化嵌入模型
        logger.info(f"加载嵌入模型: {model_name}")
        self.model = SentenceTransformer(model_name)
        
        # 初始化 Chroma（使用新的持久化 API）
        try:
            self.client = chromadb.PersistentClient(path=str(self.db_path))
        except Exception as e:
            logger.warning(f"Chroma PersistentClient 初始化失败: {e}，尝试使用 EphemeralClient")
            self.client = chromadb.EphemeralClient()
        
        # 创建集合
        self._init_collections()
        logger.info(f"向量记忆已初始化: {self.db_path}")
    
    def _init_collections(self):
        """初始化向量集合"""
        # 对话记忆集合
        self.conversations = self.client.get_or_create_collection(
            name="conversations",
            metadata={"description": "对话历史记忆"}
        )
        
        # 指令模式集合
        self.instructions = self.client.get_or_create_collection(
            name="instructions",
            metadata={"description": "指令模式记忆"}
        )
        
        # 压缩摘要集合
        self.summaries = self.client.get_or_create_collection(
            name="summaries",
            metadata={"description": "压缩后的记忆摘要"}
        )
    
    def _generate_id(self, text: str) -> str:
        """生成唯一ID"""
        return hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()[:16]
    
    def _embed(self, text: str) -> List[float]:
        """生成文本嵌入"""
        if not self.enabled:
            return []
        return self.model.encode(text).tolist()
    
    # ========== 对话记忆 ==========
    
    def add_conversation(
        self,
        user_message: str,
        assistant_response: str,
        session_id: Optional[str] = None,
        emotion: Optional[str] = None,
        success: bool = True,
        metadata: Optional[Dict] = None
    ):
        """
        添加对话记录
        
        Args:
            user_message: 用户消息
            assistant_response: AI 回复
            session_id: 会话 ID
            emotion: 情绪标签
            success: 任务是否成功
            metadata: 额外元数据
        """
        if not self.enabled:
            return
        
        # 组合文本用于嵌入
        combined_text = f"用户: {user_message}\n回复: {assistant_response[:500]}"
        embedding = self._embed(combined_text)
        
        doc_id = self._generate_id(user_message)
        
        meta = {
            "user_message": user_message[:1000],  # 限制长度
            "response_preview": assistant_response[:500],
            "session_id": session_id or "",
            "emotion": emotion or "",
            "success": str(success),
            "timestamp": datetime.now().isoformat(),
            **(metadata or {})
        }
        
        self.conversations.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[combined_text],
            metadatas=[meta]
        )
        
        logger.debug(f"添加对话记忆: {user_message[:50]}...")
    
    def search_conversations(
        self,
        query: str,
        limit: int = 5,
        filter_success: Optional[bool] = None
    ) -> List[Dict]:
        """
        搜索相似对话
        
        Args:
            query: 搜索查询
            limit: 返回数量
            filter_success: 只返回成功/失败的任务
        
        Returns:
            相似对话列表
        """
        if not self.enabled:
            return []
        
        query_embedding = self._embed(query)
        
        where_filter = None
        if filter_success is not None:
            where_filter = {"success": str(filter_success)}
        
        results = self.conversations.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where_filter
        )
        
        if not results["ids"][0]:
            return []
        
        conversations = []
        for i, doc_id in enumerate(results["ids"][0]):
            conversations.append({
                "id": doc_id,
                "document": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0
            })
        
        return conversations
    
    # ========== 指令模式 ==========
    
    def add_instruction_pattern(
        self,
        instruction: str,
        steps: List[Dict],
        success: bool = True,
        duration: float = 0,
        files_involved: Optional[List[str]] = None
    ):
        """
        添加指令模式
        
        Args:
            instruction: 原始指令
            steps: 执行步骤
            success: 是否成功
            duration: 执行时长
            files_involved: 涉及的文件
        """
        if not self.enabled:
            return
        
        embedding = self._embed(instruction)
        doc_id = self._generate_id(instruction)
        
        meta = {
            "instruction": instruction[:500],
            "steps_json": json.dumps(steps, ensure_ascii=False)[:2000],
            "success": str(success),
            "duration": str(duration),
            "files": json.dumps(files_involved or [], ensure_ascii=False),
            "timestamp": datetime.now().isoformat()
        }
        
        self.instructions.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[instruction],
            metadatas=[meta]
        )
        
        logger.debug(f"添加指令模式: {instruction[:50]}...")
    
    def find_similar_instructions(
        self,
        instruction: str,
        limit: int = 3,
        min_similarity: float = 0.7
    ) -> List[Dict]:
        """
        查找相似指令
        
        Args:
            instruction: 当前指令
            limit: 返回数量
            min_similarity: 最小相似度阈值
        
        Returns:
            相似指令列表
        """
        if not self.enabled:
            return []
        
        query_embedding = self._embed(instruction)
        
        results = self.instructions.query(
            query_embeddings=[query_embedding],
            n_results=limit
        )
        
        if not results["ids"][0]:
            return []
        
        instructions = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results["distances"] else 1.0
            # Chroma 返回的是距离，转换为相似度
            similarity = 1 / (1 + distance)
            
            if similarity >= min_similarity:
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                instructions.append({
                    "id": doc_id,
                    "instruction": meta.get("instruction", ""),
                    "steps": json.loads(meta.get("steps_json", "[]")),
                    "success": meta.get("success") == "True",
                    "similarity": similarity,
                    "timestamp": meta.get("timestamp", "")
                })
        
        return instructions
    
    # ========== 记忆压缩 ==========
    
    def compress_memories(
        self,
        time_window: str = "day",
        llm_summarizer: Optional[callable] = None
    ):
        """
        压缩记忆（将详细记忆压缩为摘要）
        
        Args:
            time_window: 压缩窗口 (day/week/month)
            llm_summarizer: LLM 摘要函数 (可选)
        """
        if not self.enabled:
            return
        
        # 获取时间范围
        now = datetime.now()
        if time_window == "day":
            cutoff = now - timedelta(days=1)
        elif time_window == "week":
            cutoff = now - timedelta(weeks=1)
        else:
            cutoff = now - timedelta(days=30)
        
        cutoff_str = cutoff.isoformat()
        
        # 获取需要压缩的对话
        all_results = self.conversations.get(
            where={"timestamp": {"$lt": cutoff_str}},
            include=["documents", "metadatas"]
        )
        
        if not all_results["ids"]:
            logger.info("没有需要压缩的记忆")
            return
        
        # 按时间窗口分组
        groups = {}
        for i, doc_id in enumerate(all_results["ids"]):
            meta = all_results["metadatas"][i] if all_results["metadatas"] else {}
            timestamp = meta.get("timestamp", "")
            if timestamp:
                # 按日期分组
                date_key = timestamp[:10]
                if date_key not in groups:
                    groups[date_key] = []
                groups[date_key].append({
                    "id": doc_id,
                    "document": all_results["documents"][i] if all_results["documents"] else "",
                    "metadata": meta
                })
        
        # 为每个组创建摘要
        for date_key, items in groups.items():
            # 简单摘要（不使用 LLM）
            summary_parts = []
            for item in items[:10]:  # 最多取 10 条
                user_msg = item["metadata"].get("user_message", "")[:100]
                success = item["metadata"].get("success", "True") == "True"
                status = "成功" if success else "失败"
                summary_parts.append(f"- {user_msg} ({status})")
            
            summary = f"【{date_key}】\n" + "\n".join(summary_parts)
            
            # 如果有 LLM 摘要器，使用它
            if llm_summarizer:
                try:
                    detailed_text = "\n".join([item["document"] for item in items])
                    summary = llm_summarizer(detailed_text)
                except Exception as e:
                    logger.warning(f"LLM 摘要失败: {e}")
            
            # 存储摘要
            embedding = self._embed(summary)
            summary_id = self._generate_id(date_key)
            
            self.summaries.add(
                ids=[summary_id],
                embeddings=[embedding],
                documents=[summary],
                metadatas=[{
                    "date": date_key,
                    "item_count": str(len(items)),
                    "timestamp": datetime.now().isoformat()
                }]
            )
            
            # 删除原始记录
            self.conversations.delete(ids=[item["id"] for item in items])
            
            logger.info(f"压缩了 {date_key} 的 {len(items)} 条记忆")
    
    def search_summaries(self, query: str, limit: int = 3) -> List[Dict]:
        """搜索压缩摘要"""
        if not self.enabled:
            return []
        
        query_embedding = self._embed(query)
        
        results = self.summaries.query(
            query_embeddings=[query_embedding],
            n_results=limit
        )
        
        if not results["ids"][0]:
            return []
        
        summaries = []
        for i, doc_id in enumerate(results["ids"][0]):
            summaries.append({
                "id": doc_id,
                "summary": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0
            })
        
        return summaries
    
    # ========== 统一搜索 ==========
    
    def search_all(self, query: str, limit: int = 5) -> Dict[str, List]:
        """
        统一搜索所有记忆
        
        Returns:
            {
                "conversations": [...],
                "instructions": [...],
                "summaries": [...]
            }
        """
        if not self.enabled:
            return {"conversations": [], "instructions": [], "summaries": []}
        
        return {
            "conversations": self.search_conversations(query, limit),
            "instructions": self.find_similar_instructions(query, limit),
            "summaries": self.search_summaries(query, limit)
        }
    
    # ========== 导出记忆上下文 ==========
    
    def get_memory_context(self, query: str, limit: int = 3) -> str:
        """
        获取与查询相关的记忆上下文
        
        Args:
            query: 当前查询/指令
            limit: 每类最多返回数量
        
        Returns:
            格式化的记忆上下文
        """
        if not self.enabled:
            return ""
        
        context_parts = []
        
        # 搜索相关对话
        convs = self.search_conversations(query, limit)
        if convs:
            conv_items = []
            for c in convs:
                meta = c.get("metadata", {})
                user_msg = meta.get("user_message", "")[:100]
                response = meta.get("response_preview", "")[:100]
                conv_items.append(f"- 用户: {user_msg}\n  回复: {response}")
            context_parts.append("**相关历史对话**：\n" + "\n".join(conv_items))
        
        # 搜索相似指令
        insts = self.find_similar_instructions(query, limit)
        if insts:
            inst_items = []
            for inst in insts:
                instruction = inst.get("instruction", "")[:100]
                success = "成功" if inst.get("success") else "失败"
                inst_items.append(f"- {instruction} ({success})")
            context_parts.append("**相似任务记录**：\n" + "\n".join(inst_items))
        
        # 搜索摘要
        sums = self.search_summaries(query, limit=2)
        if sums:
            sum_items = [s.get("summary", "")[:200] for s in sums]
            context_parts.append("**历史摘要**：\n" + "\n".join(sum_items))
        
        return "\n\n".join(context_parts) if context_parts else ""
    
    # ========== 持久化 ==========
    
    def persist(self):
        """持久化到磁盘（新版 Chroma 自动持久化，此方法保留兼容性）"""
        if self.enabled:
            # 新版 PersistentClient 自动持久化，无需手动调用
            logger.debug("向量记忆自动持久化中")
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        if not self.enabled:
            return {"enabled": False}
        
        return {
            "enabled": True,
            "conversations_count": self.conversations.count(),
            "instructions_count": self.instructions.count(),
            "summaries_count": self.summaries.count()
        }
