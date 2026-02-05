"""
任务历史和收藏管理
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskHistory:
    """任务历史管理器"""
    
    def __init__(self, data_dir: Path = None, max_history: int = 100):
        self.data_dir = data_dir or Path.home() / ".deskjarvis"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "history.json"
        self.favorites_file = self.data_dir / "favorites.json"
        
        self.max_history = max_history
        self.history: List[Dict[str, Any]] = []
        self.favorites: List[Dict[str, Any]] = []
        
        self._load_history()
        self._load_favorites()
    
    def _load_history(self):
        """加载历史记录"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                logger.info(f"已加载 {len(self.history)} 条历史记录")
            except Exception as e:
                logger.error(f"加载历史记录失败: {e}")
    
    def _save_history(self):
        """保存历史记录"""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history[-self.max_history:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存历史记录失败: {e}")
    
    def _load_favorites(self):
        """加载收藏"""
        if self.favorites_file.exists():
            try:
                with open(self.favorites_file, "r", encoding="utf-8") as f:
                    self.favorites = json.load(f)
                logger.info(f"已加载 {len(self.favorites)} 个收藏")
            except Exception as e:
                logger.error(f"加载收藏失败: {e}")
    
    def _save_favorites(self):
        """保存收藏"""
        try:
            with open(self.favorites_file, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存收藏失败: {e}")
    
    def add_task(self, instruction: str, success: bool, 
                 steps_count: int = 0, duration: float = 0) -> None:
        """
        添加任务到历史记录
        
        Args:
            instruction: 用户指令
            success: 是否成功
            steps_count: 步骤数
            duration: 执行时长（秒）
        """
        task = {
            "id": f"task_{int(datetime.now().timestamp() * 1000)}",
            "instruction": instruction,
            "success": success,
            "steps_count": steps_count,
            "duration": round(duration, 2),
            "timestamp": datetime.now().isoformat()
        }
        
        self.history.append(task)
        
        # 限制历史记录数量
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        
        self._save_history()
    
    def get_recent_tasks(self, limit: int = 20) -> Dict[str, Any]:
        """获取最近的任务"""
        recent = self.history[-limit:][::-1]  # 最新的在前
        
        # 格式化显示
        for task in recent:
            if "timestamp" in task:
                dt = datetime.fromisoformat(task["timestamp"])
                task["time_display"] = dt.strftime("%m-%d %H:%M")
        
        return {
            "success": True,
            "message": f"最近 {len(recent)} 条任务记录",
            "data": {"tasks": recent}
        }
    
    def search_history(self, keyword: str) -> Dict[str, Any]:
        """搜索历史记录"""
        results = []
        for task in self.history:
            if keyword.lower() in task.get("instruction", "").lower():
                results.append(task)
        
        return {
            "success": True,
            "message": f"找到 {len(results)} 条匹配的记录",
            "data": {"tasks": results[-20:][::-1]}
        }
    
    def add_favorite(self, instruction: str, name: str = None) -> Dict[str, Any]:
        """
        添加到收藏
        
        Args:
            instruction: 要收藏的指令
            name: 收藏名称（可选，默认使用指令内容）
        """
        # 检查是否已收藏
        for fav in self.favorites:
            if fav.get("instruction") == instruction:
                return {"success": False, "message": "该指令已在收藏中"}
        
        favorite = {
            "id": f"fav_{int(datetime.now().timestamp() * 1000)}",
            "name": name or instruction[:30],
            "instruction": instruction,
            "created_at": datetime.now().isoformat()
        }
        
        self.favorites.append(favorite)
        self._save_favorites()
        
        return {
            "success": True,
            "message": f"已收藏: {favorite['name']}",
            "data": {"id": favorite["id"]}
        }
    
    def remove_favorite(self, favorite_id: str) -> Dict[str, Any]:
        """移除收藏"""
        for i, fav in enumerate(self.favorites):
            if fav.get("id") == favorite_id:
                removed = self.favorites.pop(i)
                self._save_favorites()
                return {"success": True, "message": f"已移除收藏: {removed['name']}"}
        
        return {"success": False, "message": "未找到该收藏"}
    
    def list_favorites(self) -> Dict[str, Any]:
        """列出所有收藏"""
        return {
            "success": True,
            "message": f"共有 {len(self.favorites)} 个收藏",
            "data": {"favorites": self.favorites}
        }
    
    def clear_history(self) -> Dict[str, Any]:
        """清空历史记录"""
        self.history = []
        self._save_history()
        return {"success": True, "message": "已清空历史记录"}


# 全局实例
_task_history: Optional[TaskHistory] = None


def get_task_history() -> TaskHistory:
    """获取全局任务历史管理器实例"""
    global _task_history
    if _task_history is None:
        _task_history = TaskHistory()
    return _task_history
