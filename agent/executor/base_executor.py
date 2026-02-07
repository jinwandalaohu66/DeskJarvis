"""
Base Executor - 执行器基类

功能：
- 定义统一的 Executor 接口
- 统一错误处理和日志格式
- 确保所有 Executor 行为一致
"""

import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from agent.tools.config import Config

logger = logging.getLogger(__name__)


class BaseExecutor(ABC):
    """
    执行器基类
    
    所有 Executor 必须继承此类，实现 execute_step 方法。
    基类提供统一的错误处理和日志格式。
    """
    
    def __init__(self, config: Config, emit_callback=None):
        """
        初始化执行器
        
        Args:
            config: 配置对象
            emit_callback: 事件发送回调函数
        """
        self.config = config
        self.emit = emit_callback
    
    @abstractmethod
    def execute_step(self, step: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行单个任务步骤（子类必须实现）
        
        Args:
            step: 任务步骤，包含type、action、params等
            context: 上下文信息（可选）
            
        Returns:
            执行结果字典，格式：
            {
                "success": bool,
                "message": str,
                "data": Any (可选)
            }
        """
        pass
    
    def error_handle(self, error: Exception, step: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        统一错误处理（子类可重写以自定义错误处理）
        
        Args:
            error: 异常对象
            step: 失败的步骤
            context: 上下文信息
            
        Returns:
            标准错误结果字典
        """
        error_type = type(error).__name__
        error_msg = str(error)
        
        logger.error(
            f"[{self.__class__.__name__}] 步骤执行失败: {step.get('type', 'unknown')} - {error_type}: {error_msg}",
            exc_info=True
        )
        
        return {
            "success": False,
            "message": f"{error_type}: {error_msg}",
            "data": {
                "error_type": error_type,
                "step_type": step.get("type", "unknown"),
                "step_action": step.get("action", ""),
            }
        }
    
    def _log_execution_start(self, step: Dict[str, Any]):
        """记录执行开始日志"""
        step_type = step.get("type", "unknown")
        action = step.get("action", "")
        logger.info(f"[{self.__class__.__name__}] 执行步骤: {step_type} - {action}")
    
    def _log_execution_success(self, step: Dict[str, Any], result: Dict[str, Any]):
        """记录执行成功日志"""
        step_type = step.get("type", "unknown")
        logger.info(f"[{self.__class__.__name__}] ✅ 步骤执行成功: {step_type}")
    
    def _log_execution_failure(self, step: Dict[str, Any], error: Exception):
        """记录执行失败日志"""
        step_type = step.get("type", "unknown")
        logger.error(f"[{self.__class__.__name__}] ❌ 步骤执行失败: {step_type} - {error}", exc_info=True)
