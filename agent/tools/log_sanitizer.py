"""
日志脱敏工具 - 防止敏感信息泄露

功能：
- 检测敏感参数名（password, key, token 等）
- 对敏感值进行脱敏显示（只显示前几位和后几位）
"""

import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


class LogSanitizer:
    """
    日志脱敏器
    
    用于在日志中隐藏敏感信息，防止泄露。
    """
    
    # 敏感参数名关键词（不区分大小写）
    SENSITIVE_KEYWORDS = [
        'password', 'passwd', 'pwd', 'pass',
        'key', 'api_key', 'apikey', 'secret',
        'token', 'access_token', 'refresh_token',
        'auth', 'authorization', 'credential',
        'private', 'private_key', 'secret_key'
    ]
    
    @staticmethod
    def sanitize_value(value: Any, key_name: str = "") -> str:
        """
        脱敏值（只显示前3位和后3位，中间用***替代）
        
        Args:
            value: 要脱敏的值
            key_name: 参数名（用于判断是否需要脱敏）
            
        Returns:
            脱敏后的字符串表示
        """
        if value is None:
            return "None"
        
        value_str = str(value)
        
        # 检查参数名是否包含敏感关键词
        key_lower = key_name.lower()
        is_sensitive = any(kw in key_lower for kw in LogSanitizer.SENSITIVE_KEYWORDS)
        
        # 如果值本身看起来像敏感信息（长度 > 8 且包含字母数字），也进行脱敏
        if not is_sensitive:
            # 检查值是否像密码/密钥（长度 > 8，包含字母和数字）
            if len(value_str) > 8 and re.match(r'^[a-zA-Z0-9_\-]+$', value_str):
                # 可能是敏感信息，但不确定，不脱敏（避免误判）
                pass
        
        if is_sensitive and len(value_str) > 6:
            # 脱敏：显示前3位和后3位
            prefix = value_str[:3]
            suffix = value_str[-3:] if len(value_str) > 6 else ""
            masked = "***"
            return f"{prefix}{masked}{suffix}"
        elif is_sensitive:
            # 太短，全部用***替代
            return "***"
        else:
            # 不是敏感信息，直接返回
            return value_str
    
    @staticmethod
    def sanitize_dict(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        脱敏字典中的所有敏感值
        
        Args:
            params: 参数字典
            
        Returns:
            脱敏后的字典（新字典，不修改原字典）
        """
        sanitized = {}
        for key, value in params.items():
            if isinstance(value, dict):
                sanitized[key] = LogSanitizer.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    LogSanitizer.sanitize_value(item, key) if not isinstance(item, dict) 
                    else LogSanitizer.sanitize_dict(item)
                    for item in value
                ]
            else:
                sanitized[key] = LogSanitizer.sanitize_value(value, key)
        return sanitized
    
    @staticmethod
    def sanitize_log_message(message: str, params: Dict[str, Any] = None) -> str:
        """
        脱敏日志消息中的敏感信息
        
        Args:
            message: 日志消息
            params: 参数字典（可选）
            
        Returns:
            脱敏后的消息
        """
        if params:
            # 如果提供了参数，检查消息中是否包含参数值
            for key, value in params.items():
                if key in LogSanitizer.SENSITIVE_KEYWORDS or any(kw in key.lower() for kw in LogSanitizer.SENSITIVE_KEYWORDS):
                    # 替换消息中的敏感值
                    value_str = str(value)
                    sanitized_value = LogSanitizer.sanitize_value(value, key)
                    message = message.replace(value_str, sanitized_value)
        
        return message
