"""
异常模块：定义项目自定义异常类

遵循 docs/DEVELOPMENT.md 中的错误处理规范
"""

from typing import Dict, Any


class DeskJarvisError(Exception):
    """
    基础异常类：所有项目异常的基类
    
    Attributes:
        message: 错误消息
        details: 错误详情（可选）
    """
    
    def __init__(self, message: str, details: str | None = None):
        """
        初始化异常
        
        Args:
            message: 错误消息
            details: 错误详情，可选
        """
        self.message = message
        self.details = details
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """返回异常字符串表示"""
        if self.details:
            return f"{self.message} | 详情: {self.details}"
        return self.message


class BrowserError(DeskJarvisError):
    """浏览器操作错误"""
    pass


class FileManagerError(DeskJarvisError):
    """文件管理错误"""
    pass


class PlannerError(DeskJarvisError):
    """AI规划错误"""
    pass


class ConfigError(DeskJarvisError):
    """配置错误"""
    pass


class PlaceholderError(DeskJarvisError):
    """
    占位符错误：当占位符替换失败（NULL_ID）时抛出
    
    用于触发 Reflector 重新分析上下文，而不是直接执行失败的操作。
    """
    def __init__(self, message: str, placeholder: str = "", step: Dict[str, Any] = None):
        """
        Args:
            message: 错误消息
            placeholder: 失败的占位符（如 "{{step1.id}}"）
            step: 相关的步骤信息
        """
        super().__init__(message)
        self.placeholder = placeholder
        self.step = step


class TaskInterruptedException(DeskJarvisError):
    """
    任务中断异常：当任务被用户停止时抛出
    
    用于在等待用户输入或其他长时间操作时响应停止信号。
    """
    pass
