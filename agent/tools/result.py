"""
统一结果模块：标准化所有操作返回值

使用示例:
    from agent.tools.result import Result, ok, err

    def do_something() -> Result:
        try:
            # 操作成功
            return ok("操作成功", data={"file": "/path/to/file"})
        except Exception as e:
            return err(f"操作失败: {e}")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TypeVar, Generic


@dataclass
class Result:
    """
    统一操作结果
    
    Attributes:
        success: 是否成功
        message: 结果消息
        data: 结果数据（可选）
        error: 错误详情（可选）
    """
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "error": self.error,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Result":
        """从字典创建"""
        return cls(
            success=d.get("success", False),
            message=d.get("message", ""),
            data=d.get("data"),
            error=d.get("error"),
        )


def ok(message: str = "成功", data: Optional[Dict[str, Any]] = None) -> Result:
    """创建成功结果"""
    return Result(success=True, message=message, data=data)


def err(message: str, error: Optional[str] = None) -> Result:
    """创建失败结果"""
    return Result(success=False, message=message, error=error or message)
