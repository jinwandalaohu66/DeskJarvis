"""
快捷命令和工作流模板管理
支持用户自定义命令别名和工作流
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class WorkflowManager:
    """工作流管理器"""
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path.home() / ".deskjarvis"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.workflows_file = self.data_dir / "workflows.json"
        
        self.workflows: Dict[str, Dict[str, Any]] = {}
        self._load_workflows()
        self._init_default_workflows()
    
    def _load_workflows(self):
        """从文件加载工作流"""
        if self.workflows_file.exists():
            try:
                with open(self.workflows_file, "r", encoding="utf-8") as f:
                    self.workflows = json.load(f)
                logger.info(f"已加载 {len(self.workflows)} 个工作流")
            except Exception as e:
                logger.error(f"加载工作流失败: {e}")
    
    def _save_workflows(self):
        """保存工作流到文件"""
        try:
            with open(self.workflows_file, "w", encoding="utf-8") as f:
                json.dump(self.workflows, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存工作流失败: {e}")
    
    def _init_default_workflows(self):
        """初始化默认工作流"""
        defaults = {
            "工作模式": {
                "name": "工作模式",
                "description": "打开常用工作应用，静音",
                "commands": [
                    "打开企业微信",
                    "打开飞书",
                    "静音"
                ]
            },
            "下班模式": {
                "name": "下班模式",
                "description": "关闭工作应用，播放音乐",
                "commands": [
                    "关闭企业微信",
                    "关闭飞书",
                    "取消静音",
                    "打开网易云音乐"
                ]
            },
            "截图整理": {
                "name": "截图整理",
                "description": "整理桌面上的截图文件",
                "commands": [
                    "把桌面上的截图文件移动到 ~/Pictures/Screenshots 文件夹"
                ]
            },
            "清理下载": {
                "name": "清理下载",
                "description": "清理7天前的下载文件",
                "commands": [
                    "删除下载文件夹中7天前的文件"
                ]
            }
        }
        
        # 只添加不存在的默认工作流
        for name, workflow in defaults.items():
            if name not in self.workflows:
                self.workflows[name] = workflow
        
        self._save_workflows()
    
    def add_workflow(self, name: str, commands: List[str], 
                    description: str = "") -> Dict[str, Any]:
        """
        添加工作流
        
        Args:
            name: 工作流名称（也是触发命令）
            commands: 要执行的命令列表
            description: 描述
        
        Returns:
            添加结果
        """
        if not name or not commands:
            return {"success": False, "message": "请提供工作流名称和命令列表"}
        
        self.workflows[name] = {
            "name": name,
            "description": description,
            "commands": commands
        }
        self._save_workflows()
        
        return {
            "success": True,
            "message": f"已创建工作流 '{name}'，包含 {len(commands)} 个命令",
            "data": {"name": name, "commands": commands}
        }
    
    def delete_workflow(self, name: str) -> Dict[str, Any]:
        """删除工作流"""
        if name in self.workflows:
            del self.workflows[name]
            self._save_workflows()
            return {"success": True, "message": f"已删除工作流 '{name}'"}
        return {"success": False, "message": f"未找到工作流 '{name}'"}
    
    def get_workflow(self, name: str) -> Optional[Dict[str, Any]]:
        """获取工作流"""
        return self.workflows.get(name)
    
    def list_workflows(self) -> Dict[str, Any]:
        """列出所有工作流"""
        workflows_list = []
        for name, workflow in self.workflows.items():
            workflows_list.append({
                "name": name,
                "description": workflow.get("description", ""),
                "commands_count": len(workflow.get("commands", []))
            })
        
        message = f"共有 {len(workflows_list)} 个工作流"
        return {"success": True, "message": message, "data": {"workflows": workflows_list}}
    
    def match_workflow(self, instruction: str) -> Optional[Dict[str, Any]]:
        """
        匹配用户指令是否对应某个工作流
        
        Args:
            instruction: 用户指令
        
        Returns:
            匹配的工作流，如果没有匹配则返回 None
        """
        # 精确匹配
        if instruction in self.workflows:
            return self.workflows[instruction]
        
        # 模糊匹配
        instruction_lower = instruction.lower()
        for name, workflow in self.workflows.items():
            if name.lower() in instruction_lower or instruction_lower in name.lower():
                return workflow
        
        return None


# 全局工作流管理器实例
_workflow_manager: Optional[WorkflowManager] = None


def get_workflow_manager() -> WorkflowManager:
    """获取全局工作流管理器实例"""
    global _workflow_manager
    if _workflow_manager is None:
        _workflow_manager = WorkflowManager()
    return _workflow_manager
