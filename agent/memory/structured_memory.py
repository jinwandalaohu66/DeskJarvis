"""
层1：结构化记忆（SQLite）

功能：
- 用户偏好存储（key-value）
- 最近文件历史
- 会话摘要
- 知识图谱三元组
- 习惯模式
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class StructuredMemory:
    """结构化记忆 - SQLite 存储"""
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化结构化记忆
        
        Args:
            db_path: 数据库路径，默认 ~/.deskjarvis/memory.db
        """
        if db_path is None:
            db_path = Path.home() / ".deskjarvis" / "memory.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_database()
        logger.info(f"结构化记忆已初始化: {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_database(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 用户偏好表（key-value）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    confidence REAL DEFAULT 1.0,
                    confirmed BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. 最近文件历史
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recent_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    file_type TEXT,
                    operation TEXT,
                    tags TEXT,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recent_files_path ON recent_files(path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_recent_files_time ON recent_files(created_at)")
            
            # 3. 会话摘要
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    summary TEXT,
                    key_actions TEXT,
                    files_involved TEXT,
                    emotion TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 4. 知识图谱三元组
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_graph (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    target TEXT,
                    context TEXT,
                    confidence REAL DEFAULT 1.0,
                    importance REAL DEFAULT 0.5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kg_subject ON knowledge_graph(subject)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kg_object ON knowledge_graph(object)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_kg_predicate ON knowledge_graph(predicate)")
            
            # 5. 习惯模式
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_type TEXT NOT NULL,
                    pattern_value TEXT NOT NULL,
                    frequency INTEGER DEFAULT 1,
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_habits_type ON habits(pattern_type)")
            
            # 6. 指令历史（用于工作流发现）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS instruction_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    instruction TEXT NOT NULL,
                    normalized TEXT,
                    steps TEXT,
                    success BOOLEAN,
                    duration_seconds REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info("数据库表已初始化")
    
    # ========== 偏好管理 ==========
    
    def set_preference(
        self, 
        key: str, 
        value: Any, 
        category: str = "general",
        confidence: float = 1.0,
        confirmed: bool = False
    ):
        """设置用户偏好"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            cursor.execute("""
                INSERT INTO preferences (key, value, category, confidence, confirmed, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET 
                    value = excluded.value,
                    category = excluded.category,
                    confidence = excluded.confidence,
                    confirmed = excluded.confirmed,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, value_str, category, confidence, confirmed))
        logger.debug(f"设置偏好: {key} = {value}")
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except json.JSONDecodeError:
                    return row["value"]
            return default
    
    def get_all_preferences(self, category: Optional[str] = None) -> Dict[str, Any]:
        """获取所有偏好"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT key, value FROM preferences WHERE category = ?", (category,))
            else:
                cursor.execute("SELECT key, value FROM preferences")
            
            result = {}
            for row in cursor.fetchall():
                try:
                    result[row["key"]] = json.loads(row["value"])
                except json.JSONDecodeError:
                    result[row["key"]] = row["value"]
            return result
    
    # ========== 文件历史 ==========
    
    def add_file_record(
        self,
        path: str,
        file_type: Optional[str] = None,
        operation: str = "access",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ):
        """添加文件记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO recent_files (path, file_type, operation, tags, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                path,
                file_type or self._guess_file_type(path),
                operation,
                json.dumps(tags or [], ensure_ascii=False),
                json.dumps(metadata or {}, ensure_ascii=False)
            ))
        logger.debug(f"添加文件记录: {path} ({operation})")
    
    def get_recent_files(self, limit: int = 10, file_type: Optional[str] = None) -> List[Dict]:
        """获取最近文件"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if file_type:
                cursor.execute("""
                    SELECT * FROM recent_files 
                    WHERE file_type = ?
                    ORDER BY created_at DESC LIMIT ?
                """, (file_type, limit))
            else:
                cursor.execute("""
                    SELECT * FROM recent_files 
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def search_files(self, keyword: str, limit: int = 10) -> List[Dict]:
        """搜索文件"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM recent_files 
                WHERE path LIKE ? OR tags LIKE ?
                ORDER BY created_at DESC LIMIT ?
            """, (f"%{keyword}%", f"%{keyword}%", limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def _guess_file_type(self, path: str) -> str:
        """猜测文件类型"""
        ext = Path(path).suffix.lower()
        type_map = {
            ".pdf": "document",
            ".doc": "document", ".docx": "document",
            ".xls": "spreadsheet", ".xlsx": "spreadsheet",
            ".ppt": "presentation", ".pptx": "presentation",
            ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image",
            ".mp4": "video", ".avi": "video", ".mov": "video",
            ".mp3": "audio", ".wav": "audio",
            ".py": "code", ".js": "code", ".ts": "code", ".java": "code",
            ".zip": "archive", ".rar": "archive", ".7z": "archive",
        }
        return type_map.get(ext, "other")
    
    # ========== 会话摘要 ==========
    
    def save_session(
        self,
        session_id: str,
        summary: str,
        key_actions: Optional[List[str]] = None,
        files_involved: Optional[List[str]] = None,
        emotion: Optional[str] = None
    ):
        """保存会话摘要"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (session_id, summary, key_actions, files_involved, emotion)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary = excluded.summary,
                    key_actions = excluded.key_actions,
                    files_involved = excluded.files_involved,
                    emotion = excluded.emotion,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                session_id,
                summary,
                json.dumps(key_actions or [], ensure_ascii=False),
                json.dumps(files_involved or [], ensure_ascii=False),
                emotion
            ))
        logger.debug(f"保存会话摘要: {session_id}")
    
    def get_recent_sessions(self, limit: int = 5) -> List[Dict]:
        """获取最近会话"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sessions 
                ORDER BY updated_at DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== 知识图谱 ==========
    
    def add_knowledge(
        self,
        subject: str,
        predicate: str,
        obj: str,
        target: Optional[str] = None,
        context: Optional[str] = None,
        confidence: float = 1.0,
        importance: float = 0.5
    ):
        """添加知识三元组"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO knowledge_graph 
                (subject, predicate, object, target, context, confidence, importance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (subject, predicate, obj, target, context, confidence, importance))
        logger.debug(f"添加知识: {subject} → {predicate} → {obj}")
    
    def query_knowledge(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """查询知识图谱"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []
            
            if subject:
                conditions.append("subject LIKE ?")
                params.append(f"%{subject}%")
            if predicate:
                conditions.append("predicate LIKE ?")
                params.append(f"%{predicate}%")
            if obj:
                conditions.append("object LIKE ?")
                params.append(f"%{obj}%")
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            
            cursor.execute(f"""
                SELECT * FROM knowledge_graph 
                WHERE {where_clause}
                ORDER BY importance DESC, created_at DESC 
                LIMIT ?
            """, params)
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== 习惯模式 ==========
    
    def record_habit(self, pattern_type: str, pattern_value: str, metadata: Optional[Dict] = None):
        """记录习惯模式"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 检查是否已存在
            cursor.execute("""
                SELECT id, frequency FROM habits 
                WHERE pattern_type = ? AND pattern_value = ?
            """, (pattern_type, pattern_value))
            row = cursor.fetchone()
            
            if row:
                # 更新频率
                cursor.execute("""
                    UPDATE habits SET 
                        frequency = frequency + 1,
                        last_seen = CURRENT_TIMESTAMP,
                        metadata = ?
                    WHERE id = ?
                """, (json.dumps(metadata or {}, ensure_ascii=False), row["id"]))
            else:
                # 新增
                cursor.execute("""
                    INSERT INTO habits (pattern_type, pattern_value, metadata)
                    VALUES (?, ?, ?)
                """, (pattern_type, pattern_value, json.dumps(metadata or {}, ensure_ascii=False)))
        
        logger.debug(f"记录习惯: {pattern_type} = {pattern_value}")
    
    def get_habits(self, pattern_type: Optional[str] = None, min_frequency: int = 1) -> List[Dict]:
        """获取习惯模式"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if pattern_type:
                cursor.execute("""
                    SELECT * FROM habits 
                    WHERE pattern_type = ? AND frequency >= ?
                    ORDER BY frequency DESC
                """, (pattern_type, min_frequency))
            else:
                cursor.execute("""
                    SELECT * FROM habits 
                    WHERE frequency >= ?
                    ORDER BY frequency DESC
                """, (min_frequency,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== 指令历史 ==========
    
    def add_instruction(
        self,
        instruction: str,
        normalized: Optional[str] = None,
        steps: Optional[List[Dict]] = None,
        success: bool = True,
        duration: float = 0
    ):
        """添加指令历史"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO instruction_history 
                (instruction, normalized, steps, success, duration_seconds)
                VALUES (?, ?, ?, ?, ?)
            """, (
                instruction,
                normalized or self._normalize_instruction(instruction),
                json.dumps(steps or [], ensure_ascii=False),
                success,
                duration
            ))
        logger.debug(f"添加指令历史: {instruction[:50]}...")
    
    def get_similar_instructions(self, instruction: str, limit: int = 5) -> List[Dict]:
        """获取相似指令（简单关键词匹配）"""
        normalized = self._normalize_instruction(instruction)
        keywords = normalized.split()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 简单的关键词匹配
            conditions = " OR ".join(["normalized LIKE ?" for _ in keywords])
            params = [f"%{kw}%" for kw in keywords]
            params.append(limit)
            
            cursor.execute(f"""
                SELECT * FROM instruction_history 
                WHERE {conditions}
                ORDER BY created_at DESC LIMIT ?
            """, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def _normalize_instruction(self, instruction: str) -> str:
        """标准化指令（用于匹配）"""
        import re
        # 移除数字、特殊字符，转小写
        normalized = re.sub(r'[0-9\.\-\_\/\\]', ' ', instruction.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    # ========== 清理 ==========
    
    def cleanup_old_data(self, days: int = 90):
        """清理旧数据（保留重要的）"""
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 清理文件历史（保留最近的）
            cursor.execute("""
                DELETE FROM recent_files 
                WHERE created_at < ? 
                AND id NOT IN (SELECT id FROM recent_files ORDER BY created_at DESC LIMIT 100)
            """, (cutoff_str,))
            
            # 清理知识图谱（保留重要的）
            cursor.execute("""
                DELETE FROM knowledge_graph 
                WHERE created_at < ? AND importance < 0.8
            """, (cutoff_str,))
            
            # 清理指令历史
            cursor.execute("""
                DELETE FROM instruction_history 
                WHERE created_at < ?
                AND id NOT IN (SELECT id FROM instruction_history ORDER BY created_at DESC LIMIT 500)
            """, (cutoff_str,))
            
            logger.info(f"清理了 {days} 天前的旧数据")
    
    # ========== 导出记忆上下文 ==========
    
    def get_memory_context(self, limit_per_category: int = 5) -> str:
        """
        获取记忆上下文（用于注入 prompt）
        
        Returns:
            格式化的记忆上下文字符串
        """
        context_parts = []
        
        # 1. 用户偏好
        prefs = self.get_all_preferences()
        if prefs:
            pref_items = [f"- {k}: {v}" for k, v in list(prefs.items())[:limit_per_category]]
            context_parts.append("**用户偏好**：\n" + "\n".join(pref_items))
        
        # 2. 最近文件
        files = self.get_recent_files(limit=limit_per_category)
        if files:
            file_items = [f"- {f['path']} ({f['operation']}, {f['created_at'][:10]})" for f in files]
            context_parts.append("**最近文件**：\n" + "\n".join(file_items))
        
        # 3. 常用习惯
        habits = self.get_habits(min_frequency=2)[:limit_per_category]
        if habits:
            habit_items = [f"- {h['pattern_type']}: {h['pattern_value']} (使用{h['frequency']}次)" for h in habits]
            context_parts.append("**用户习惯**：\n" + "\n".join(habit_items))
        
        # 4. 最近会话
        sessions = self.get_recent_sessions(limit=3)
        if sessions:
            session_items = [f"- {s['summary'][:100]}" for s in sessions if s.get('summary')]
            if session_items:
                context_parts.append("**最近会话**：\n" + "\n".join(session_items))
        
        return "\n\n".join(context_parts) if context_parts else ""
