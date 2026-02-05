"""
定时任务调度器
支持：
- 延时提醒（如 "5分钟后提醒我喝水"）
- 定时任务（如 "每天9点打开微信"）
"""

import threading
import time
import json
import logging
from typing import Dict, Any, List, Callable, Optional
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys

logger = logging.getLogger(__name__)


class Reminder:
    """单个提醒任务"""
    
    def __init__(self, reminder_id: str, message: str, trigger_time: datetime,
                 repeat: Optional[str] = None, command: Optional[str] = None):
        self.id = reminder_id
        self.message = message
        self.trigger_time = trigger_time
        self.repeat = repeat  # None, "daily", "hourly", "weekly"
        self.command = command  # 可选的执行命令
        self.triggered = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "message": self.message,
            "trigger_time": self.trigger_time.isoformat(),
            "repeat": self.repeat,
            "command": self.command,
            "triggered": self.triggered
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Reminder":
        return cls(
            reminder_id=data["id"],
            message=data["message"],
            trigger_time=datetime.fromisoformat(data["trigger_time"]),
            repeat=data.get("repeat"),
            command=data.get("command")
        )


class Scheduler:
    """定时任务调度器"""
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path.home() / ".deskjarvis"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reminders_file = self.data_dir / "reminders.json"
        
        self.reminders: Dict[str, Reminder] = {}
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.callbacks: List[Callable] = []
        
        self._load_reminders()
    
    def _load_reminders(self):
        """从文件加载提醒"""
        if self.reminders_file.exists():
            try:
                with open(self.reminders_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        reminder = Reminder.from_dict(item)
                        # 只加载未触发的或重复的提醒
                        if not reminder.triggered or reminder.repeat:
                            self.reminders[reminder.id] = reminder
                logger.info(f"已加载 {len(self.reminders)} 个提醒")
            except Exception as e:
                logger.error(f"加载提醒失败: {e}")
    
    def _save_reminders(self):
        """保存提醒到文件"""
        try:
            data = [r.to_dict() for r in self.reminders.values()]
            with open(self.reminders_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存提醒失败: {e}")
    
    def add_reminder(self, message: str, delay_seconds: int = None,
                    trigger_time: datetime = None, repeat: str = None,
                    command: str = None) -> Dict[str, Any]:
        """
        添加提醒
        
        Args:
            message: 提醒内容
            delay_seconds: 延迟秒数（与 trigger_time 二选一）
            trigger_time: 触发时间（与 delay_seconds 二选一）
            repeat: 重复类型 (None, "daily", "hourly", "weekly")
            command: 触发时执行的命令
        
        Returns:
            添加结果
        """
        reminder_id = f"reminder_{int(time.time() * 1000)}"
        
        if delay_seconds:
            trigger_time = datetime.now() + timedelta(seconds=delay_seconds)
        elif not trigger_time:
            return {"success": False, "message": "请指定延迟时间或触发时间"}
        
        reminder = Reminder(
            reminder_id=reminder_id,
            message=message,
            trigger_time=trigger_time,
            repeat=repeat,
            command=command
        )
        
        self.reminders[reminder_id] = reminder
        self._save_reminders()
        
        # 格式化时间显示
        time_str = trigger_time.strftime("%H:%M:%S")
        if trigger_time.date() != datetime.now().date():
            time_str = trigger_time.strftime("%m-%d %H:%M")
        
        return {
            "success": True,
            "message": f"已设置提醒，将在 {time_str} 提醒你: {message}",
            "data": {"id": reminder_id, "trigger_time": trigger_time.isoformat()}
        }
    
    def cancel_reminder(self, reminder_id: str) -> Dict[str, Any]:
        """取消提醒"""
        if reminder_id in self.reminders:
            del self.reminders[reminder_id]
            self._save_reminders()
            return {"success": True, "message": "已取消提醒"}
        return {"success": False, "message": "未找到该提醒"}
    
    def list_reminders(self) -> Dict[str, Any]:
        """列出所有提醒"""
        now = datetime.now()
        pending = []
        for r in self.reminders.values():
            if not r.triggered or r.repeat:
                pending.append({
                    "id": r.id,
                    "message": r.message,
                    "trigger_time": r.trigger_time.strftime("%m-%d %H:%M:%S"),
                    "repeat": r.repeat,
                    "remaining": self._format_remaining(r.trigger_time - now)
                })
        
        pending.sort(key=lambda x: x["trigger_time"])
        
        if pending:
            message = f"你有 {len(pending)} 个待处理的提醒"
        else:
            message = "没有待处理的提醒"
        
        return {"success": True, "message": message, "data": {"reminders": pending}}
    
    def _format_remaining(self, delta: timedelta) -> str:
        """格式化剩余时间"""
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "已过期"
        
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}小时{minutes}分钟后"
        elif minutes > 0:
            return f"{minutes}分钟后"
        else:
            return f"{seconds}秒后"
    
    def start(self, callback: Callable = None):
        """启动调度器"""
        if callback:
            self.callbacks.append(callback)
        
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("定时任务调度器已启动")
    
    def stop(self):
        """停止调度器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("定时任务调度器已停止")
    
    def _run_loop(self):
        """调度循环"""
        while self.running:
            now = datetime.now()
            triggered_ids = []
            
            for reminder_id, reminder in list(self.reminders.items()):
                if reminder.triggered and not reminder.repeat:
                    continue
                
                if now >= reminder.trigger_time:
                    self._trigger_reminder(reminder)
                    
                    if reminder.repeat:
                        # 计算下次触发时间
                        if reminder.repeat == "daily":
                            reminder.trigger_time += timedelta(days=1)
                        elif reminder.repeat == "hourly":
                            reminder.trigger_time += timedelta(hours=1)
                        elif reminder.repeat == "weekly":
                            reminder.trigger_time += timedelta(weeks=1)
                    else:
                        reminder.triggered = True
                        triggered_ids.append(reminder_id)
            
            # 清理已触发的非重复提醒
            for rid in triggered_ids:
                if rid in self.reminders and not self.reminders[rid].repeat:
                    del self.reminders[rid]
            
            if triggered_ids:
                self._save_reminders()
            
            time.sleep(1)  # 每秒检查一次
    
    def _trigger_reminder(self, reminder: Reminder):
        """触发提醒"""
        logger.info(f"触发提醒: {reminder.message}")
        
        # 发送系统通知
        if sys.platform == "darwin":
            try:
                script = f'''
                display notification "{reminder.message}" with title "DeskJarvis 提醒" sound name "Glass"
                '''
                subprocess.run(["osascript", "-e", script], check=True)
            except Exception as e:
                logger.error(f"发送通知失败: {e}")
        
        # 语音播报
        if sys.platform == "darwin":
            try:
                subprocess.run(["say", reminder.message], check=True)
            except Exception as e:
                logger.error(f"语音播报失败: {e}")
        
        # 执行命令
        if reminder.command:
            try:
                for callback in self.callbacks:
                    callback(reminder.command)
            except Exception as e:
                logger.error(f"执行命令失败: {e}")


# 全局调度器实例
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """获取全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
        _scheduler.start()
    return _scheduler


def parse_time_expression(expr: str) -> Optional[int]:
    """
    解析时间表达式，返回秒数
    
    支持：
    - "5分钟后" -> 300
    - "1小时后" -> 3600
    - "30秒后" -> 30
    - "2小时30分钟后" -> 9000
    """
    import re
    
    total_seconds = 0
    
    # 匹配小时
    hours_match = re.search(r'(\d+)\s*小时', expr)
    if hours_match:
        total_seconds += int(hours_match.group(1)) * 3600
    
    # 匹配分钟
    minutes_match = re.search(r'(\d+)\s*分钟?', expr)
    if minutes_match:
        total_seconds += int(minutes_match.group(1)) * 60
    
    # 匹配秒
    seconds_match = re.search(r'(\d+)\s*秒', expr)
    if seconds_match:
        total_seconds += int(seconds_match.group(1))
    
    return total_seconds if total_seconds > 0 else None
