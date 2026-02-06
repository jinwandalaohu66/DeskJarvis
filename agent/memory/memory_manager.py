"""
记忆管理器 - 统一管理三层记忆

核心功能：
1. 统一的记忆存储和检索接口
2. 自动记忆更新（任务结束后）
3. 智能记忆注入（规划前）
4. 定期维护（压缩、清理）
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import uuid
import threading

from agent.memory.structured_memory import StructuredMemory
from agent.memory.vector_memory import VectorMemory
from agent.memory.advanced_memory import AdvancedMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    记忆管理器 - 整合三层记忆系统
    
    使用示例：
        memory = MemoryManager()
        
        # 规划前：获取相关记忆
        context = memory.get_context_for_instruction("整理桌面文件")
        
        # 任务后：保存记忆
        memory.save_task_result(instruction, steps, result, success)
        
        # 偏好管理
        memory.set_preference("download_path", "/Users/xxx/Downloads")
        memory.get_preference("download_path")
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化记忆管理器
        
        Args:
            db_path: 数据库目录，默认 ~/.deskjarvis/
        """
        if db_path is None:
            db_path = Path.home() / ".deskjarvis"
        
        self.db_path = db_path
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化三层记忆
        self.structured = StructuredMemory(db_path / "memory.db")
        self.vector = VectorMemory(db_path / "vector_memory")
        self.advanced = AdvancedMemory()
        
        # 当前会话 ID
        self.session_id = str(uuid.uuid4())[:8]
        
        # 加载高级记忆状态
        self._load_advanced_state()
        
        # 启动后台维护任务
        self._start_maintenance_thread()
        
        logger.info(f"记忆管理器已初始化，会话 ID: {self.session_id}")
    
    # ========== 核心 API ==========
    
    def get_context_for_instruction(
        self, 
        instruction: str,
        include_vector: bool = True,
        max_tokens: int = 500
    ) -> str:
        """
        获取指令相关的记忆上下文（用于注入 prompt）
        
        Args:
            instruction: 用户指令
            include_vector: 是否包含向量搜索结果
            max_tokens: 最大 token 数（约等于字符数 / 2）
        
        Returns:
            格式化的记忆上下文字符串
        """
        context_parts = []
        
        # 1. 分析用户情绪
        emotion_result = self.advanced.analyze_emotion(instruction)
        if emotion_result["emotion"] != "neutral":
            context_parts.append(f"[用户情绪: {emotion_result['emotion']}] {emotion_result['suggestion']}")
        
        # 2. 结构化记忆上下文
        structured_context = self.structured.get_memory_context(limit_per_category=3)
        if structured_context:
            context_parts.append(structured_context)
        
        # 3. 向量记忆上下文（语义搜索）
        if include_vector and self.vector.enabled:
            try:
                vector_context = self.vector.get_memory_context(instruction, limit=3)
                if vector_context:
                    context_parts.append(vector_context)
            except Exception as e:
                # 记忆系统是“增强能力”，不应该阻塞主流程
                logger.warning(f"获取向量记忆上下文失败，将跳过向量记忆: {e}")
        
        # 4. 高级记忆上下文
        advanced_context = self.advanced.get_memory_context()
        if advanced_context:
            context_parts.append(advanced_context)
        
        # 5. 工作流建议
        workflow_suggestion = self.advanced.get_workflow_suggestion(instruction)
        if workflow_suggestion:
            context_parts.append(f"**工作流提示**：{workflow_suggestion['message']}")
        
        # 合并并截断
        full_context = "\n\n".join(context_parts)
        
        # 简单截断（按字符数）
        max_chars = max_tokens * 2
        if len(full_context) > max_chars:
            full_context = full_context[:max_chars] + "\n...(记忆已截断)"
        
        return full_context
    
    def save_task_result(
        self,
        instruction: str,
        steps: List[Dict],
        result: Dict,
        success: bool,
        duration: float = 0,
        files_involved: Optional[List[str]] = None
    ):
        """
        保存任务结果到记忆
        
        Args:
            instruction: 用户指令
            steps: 执行步骤
            result: 执行结果
            success: 是否成功
            duration: 执行时长（秒）
            files_involved: 涉及的文件
        """
        try:
            # 1. 保存到结构化记忆
            self.structured.add_instruction(
                instruction=instruction,
                steps=steps,
                success=success,
                duration=duration
            )
            
            # 2. 保存到向量记忆
            response_text = result.get("message", "") or str(result)
            self.vector.add_conversation(
                user_message=instruction,
                assistant_response=response_text,
                session_id=self.session_id,
                success=success
            )
            
            self.vector.add_instruction_pattern(
                instruction=instruction,
                steps=steps,
                success=success,
                duration=duration,
                files_involved=files_involved
            )
            
            # 3. 记录动作到高级记忆
            for step in steps:
                self.advanced.record_action(step)
            
            # 4. 提取并保存文件记录
            if files_involved:
                for file_path in files_involved:
                    operation = "create" if success else "failed"
                    self.structured.add_file_record(file_path, operation=operation)
            
            # 5. 提取知识三元组
            self._extract_and_save_knowledge(instruction, steps, result)
            
            # 6. 记录习惯
            self._record_habits(instruction, steps)
            
            logger.debug(f"任务结果已保存到记忆: {instruction[:50]}...")
            
        except Exception as e:
            logger.error(f"保存任务结果失败: {e}")
    
    def save_session_summary(self, summary: str, key_actions: Optional[List[str]] = None):
        """保存会话摘要"""
        files = [f["path"] for f in self.structured.get_recent_files(limit=10)]
        emotion_pattern = self.advanced.get_emotion_pattern()
        
        self.structured.save_session(
            session_id=self.session_id,
            summary=summary,
            key_actions=key_actions,
            files_involved=files,
            emotion=emotion_pattern.get("dominant_emotion")
        )
    
    # ========== 偏好管理 ==========
    
    def set_preference(
        self, 
        key: str, 
        value: Any, 
        category: str = "general",
        confirmed: bool = False
    ):
        """设置用户偏好"""
        self.structured.set_preference(key, value, category, confirmed=confirmed)
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        return self.structured.get_preference(key, default)
    
    def confirm_preference(self, key: str):
        """确认偏好（用户明确表示喜欢这个设置）"""
        current = self.get_preference(key)
        if current is not None:
            self.set_preference(key, current, confirmed=True)
    
    def get_all_preferences(self) -> Dict[str, Any]:
        """获取所有偏好"""
        return self.structured.get_all_preferences()
    
    # ========== 文件历史 ==========
    
    def add_file_record(self, path: str, operation: str = "access", tags: Optional[List[str]] = None):
        """添加文件记录"""
        self.structured.add_file_record(path, operation=operation, tags=tags)
    
    def get_recent_files(self, limit: int = 10, file_type: Optional[str] = None) -> List[Dict]:
        """获取最近文件"""
        return self.structured.get_recent_files(limit, file_type)
    
    def search_files(self, keyword: str) -> List[Dict]:
        """搜索文件"""
        return self.structured.search_files(keyword)
    
    # ========== 知识图谱 ==========
    
    def add_knowledge(self, subject: str, predicate: str, obj: str, **kwargs):
        """添加知识"""
        self.structured.add_knowledge(subject, predicate, obj, **kwargs)
    
    def query_knowledge(self, **kwargs) -> List[Dict]:
        """查询知识"""
        return self.structured.query_knowledge(**kwargs)
    
    # ========== 语义搜索 ==========
    
    def semantic_search(self, query: str, limit: int = 5) -> Dict[str, List]:
        """语义搜索所有记忆"""
        if not self.vector.enabled:
            return {"conversations": [], "instructions": [], "summaries": []}
        return self.vector.search_all(query, limit)
    
    def find_similar_instructions(self, instruction: str, limit: int = 3) -> List[Dict]:
        """查找相似指令"""
        if not self.vector.enabled:
            # 降级到结构化搜索
            return self.structured.get_similar_instructions(instruction, limit)
        return self.vector.find_similar_instructions(instruction, limit)
    
    # ========== 工作流发现 ==========
    
    def discover_workflows(self) -> List[Dict]:
        """发现工作流模式"""
        # 从结构化记忆获取指令历史
        with self.structured._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT instruction, steps, success, created_at 
                FROM instruction_history 
                ORDER BY created_at DESC LIMIT 500
            """)
            history = []
            for row in cursor.fetchall():
                history.append({
                    "instruction": row["instruction"],
                    "steps": row["steps"],
                    "success": bool(row["success"]),
                    "timestamp": row["created_at"]
                })
        
        return self.advanced.discover_workflows(history)
    
    def get_workflow_suggestion(self, instruction: str) -> Optional[Dict]:
        """获取工作流建议"""
        return self.advanced.get_workflow_suggestion(instruction)
    
    # ========== 情绪分析 ==========
    
    def analyze_emotion(self, text: str) -> Dict:
        """分析情绪"""
        return self.advanced.analyze_emotion(text)
    
    def get_emotion_pattern(self) -> Dict:
        """获取情绪模式"""
        return self.advanced.get_emotion_pattern()
    
    # ========== 主动学习 ==========
    
    def get_pending_confirmations(self) -> List[Dict]:
        """获取待确认的偏好"""
        return self.advanced.get_pending_confirmations()
    
    def handle_confirmation_response(self, confirmation_id: str, response: str):
        """处理确认响应"""
        # 解析确认 ID
        parts = confirmation_id.split("_")
        if len(parts) >= 3:
            pref_type = parts[1]
            
            if response == "是":
                # 保存为确认的偏好
                # 需要从 pending 中找到对应的偏好
                pending = self.get_pending_confirmations()
                for p in pending:
                    if p["id"] == confirmation_id:
                        pref = p["preference"]
                        self.set_preference(
                            f"auto_{pref['type']}", 
                            pref["value"],
                            category="auto_discovered",
                            confirmed=True
                        )
                        break
            elif response == "以后不再询问":
                # 标记为不再询问
                self.set_preference(
                    f"no_ask_{pref_type}",
                    True,
                    category="system"
                )
    
    # ========== 内部方法 ==========
    
    def _extract_and_save_knowledge(self, instruction: str, steps: List[Dict], result: Dict):
        """提取并保存知识三元组"""
        # 简单的知识提取
        for step in steps:
            step_type = step.get("type", "")
            params = step.get("params", {})
            
            if step_type == "file_save" or step_type == "file_create":
                path = params.get("path", "")
                if path:
                    self.add_knowledge("用户", "创建", path)
            
            elif step_type == "file_rename":
                old = params.get("old_name", "")
                new = params.get("new_name", "")
                if old and new:
                    self.add_knowledge(old, "重命名为", new)
            
            elif step_type == "browser_navigate":
                url = params.get("url", "")
                if url:
                    self.add_knowledge("用户", "访问", url)
            
            elif step_type == "download_file":
                url = params.get("url", "")
                path = params.get("save_path", "")
                if url and path:
                    self.add_knowledge(url, "下载到", path)
    
    def _record_habits(self, instruction: str, steps: List[Dict]):
        """记录习惯模式"""
        # 记录指令模式
        # 检测常用动词
        action_words = ["下载", "整理", "删除", "重命名", "移动", "复制", "总结", "搜索"]
        for word in action_words:
            if word in instruction:
                self.structured.record_habit("action", word)
        
        # 检测时间相关词
        time_words = ["每天", "每周", "定时", "提醒"]
        for word in time_words:
            if word in instruction:
                self.structured.record_habit("time_preference", word)
        
        # 检测文件类型偏好
        for step in steps:
            params = step.get("params", {})
            path = params.get("path", "") or params.get("file_path", "")
            if path:
                ext = Path(path).suffix.lower()
                if ext:
                    self.structured.record_habit("file_type", ext)
    
    def _load_advanced_state(self):
        """加载高级记忆状态"""
        state_file = self.db_path / "advanced_state.json"
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.advanced.import_state(state)
                logger.info("已加载高级记忆状态")
            except Exception as e:
                logger.warning(f"加载高级记忆状态失败: {e}")
    
    def _save_advanced_state(self):
        """保存高级记忆状态"""
        state_file = self.db_path / "advanced_state.json"
        try:
            state = self.advanced.export_state()
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.debug("已保存高级记忆状态")
        except Exception as e:
            logger.warning(f"保存高级记忆状态失败: {e}")
    
    def _start_maintenance_thread(self):
        """启动后台维护线程"""
        def maintenance_loop():
            while True:
                try:
                    time.sleep(3600)  # 每小时执行一次
                    self._run_maintenance()
                except Exception as e:
                    logger.error(f"维护任务失败: {e}")
        
        thread = threading.Thread(target=maintenance_loop, daemon=True)
        thread.start()
        logger.debug("后台维护线程已启动")
    
    def _run_maintenance(self):
        """执行维护任务"""
        logger.info("开始执行记忆维护...")
        
        # 1. 压缩旧的向量记忆
        if self.vector.enabled:
            self.vector.compress_memories(time_window="week")
        
        # 2. 清理旧的结构化数据
        self.structured.cleanup_old_data(days=90)
        
        # 3. 保存高级记忆状态
        self._save_advanced_state()
        
        # 4. 发现新的工作流
        self.discover_workflows()
        
        # 5. 持久化向量记忆
        if self.vector.enabled:
            self.vector.persist()
        
        logger.info("记忆维护完成")
    
    # ========== 统计 & 诊断 ==========
    
    def get_stats(self) -> Dict:
        """获取记忆系统统计"""
        with self.structured._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM preferences")
            prefs_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM recent_files")
            files_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM knowledge_graph")
            knowledge_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM instruction_history")
            instructions_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM habits")
            habits_count = cursor.fetchone()[0]
        
        vector_stats = self.vector.get_stats() if self.vector.enabled else {}
        
        return {
            "session_id": self.session_id,
            "structured_memory": {
                "preferences": prefs_count,
                "recent_files": files_count,
                "knowledge_graph": knowledge_count,
                "instruction_history": instructions_count,
                "habits": habits_count
            },
            "vector_memory": vector_stats,
            "advanced_memory": {
                "emotions_recorded": len(self.advanced.emotions_history),
                "actions_recorded": len(self.advanced.actions_history),
                "workflows_discovered": len(self.advanced.discovered_patterns)
            }
        }
    
    def export_all_memories(self) -> Dict:
        """导出所有记忆（用于备份）"""
        return {
            "preferences": self.get_all_preferences(),
            "recent_files": self.get_recent_files(limit=100),
            "knowledge": self.query_knowledge(limit=1000),
            "habits": self.structured.get_habits(),
            "advanced_state": self.advanced.export_state(),
            "exported_at": datetime.now().isoformat()
        }
    
    def shutdown(self):
        """关闭记忆管理器（保存状态）"""
        logger.info("正在关闭记忆管理器...")
        self._save_advanced_state()
        if self.vector.enabled:
            self.vector.persist()
        logger.info("记忆管理器已关闭")
