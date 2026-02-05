"""
用户输入请求模块

用于在自动化过程中请求用户输入（登录、验证码等）
通过事件通知前端，通过文件交换数据
"""

import os
import json
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any

logger = logging.getLogger(__name__)


class UserInputRequest:
    """用户输入请求"""
    
    def __init__(
        self,
        request_type: str,  # "login", "captcha", "custom"
        title: str,
        fields: List[Dict[str, Any]],
        message: Optional[str] = None,
        captcha_image: Optional[str] = None,  # base64
    ):
        self.id = str(uuid.uuid4())
        self.type = request_type
        self.title = title
        self.message = message
        self.fields = fields
        self.captcha_image = captcha_image
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "fields": self.fields,
            "captchaImage": self.captcha_image,
        }


class UserInputManager:
    """用户输入管理器"""
    
    def __init__(self, emit_callback: Optional[Callable] = None):
        """
        初始化用户输入管理器
        
        Args:
            emit_callback: 事件发送回调函数
        """
        self.emit = emit_callback
        self.data_dir = Path.home() / ".deskjarvis"
        self.response_file = self.data_dir / "user_input_response.json"
        
        # 确保目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def request_login(
        self,
        site_name: str = "网站",
        username_label: str = "用户名",
        password_label: str = "密码",
        message: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        请求登录信息
        
        Args:
            site_name: 网站名称
            username_label: 用户名标签
            password_label: 密码标签
            message: 额外提示信息
            
        Returns:
            {"username": "...", "password": "..."} 或 None（取消）
        """
        request = UserInputRequest(
            request_type="login",
            title=f"登录 {site_name}",
            message=message or f"请输入您在 {site_name} 的登录信息",
            fields=[
                {
                    "name": "username",
                    "label": username_label,
                    "type": "text",
                    "placeholder": f"请输入{username_label}",
                    "required": True,
                },
                {
                    "name": "password",
                    "label": password_label,
                    "type": "password",
                    "placeholder": f"请输入{password_label}",
                    "required": True,
                },
            ],
        )
        
        return self._send_request_and_wait(request)
    
    def request_captcha(
        self,
        captcha_image: str,  # base64 编码的图片
        site_name: str = "网站",
        message: Optional[str] = None,
    ) -> Optional[str]:
        """
        请求验证码输入
        
        Args:
            captcha_image: base64 编码的验证码图片
            site_name: 网站名称
            message: 额外提示信息
            
        Returns:
            验证码字符串 或 None（取消）
        """
        request = UserInputRequest(
            request_type="captcha",
            title=f"输入验证码 - {site_name}",
            message=message or "请输入图片中的验证码",
            captcha_image=captcha_image,
            fields=[
                {
                    "name": "captcha",
                    "label": "验证码",
                    "type": "text",
                    "placeholder": "请输入验证码",
                    "required": True,
                },
            ],
        )
        
        result = self._send_request_and_wait(request)
        return result.get("captcha") if result else None
    
    def request_custom(
        self,
        title: str,
        fields: List[Dict[str, Any]],
        message: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        请求自定义输入
        
        Args:
            title: 对话框标题
            fields: 字段列表
            message: 额外提示信息
            
        Returns:
            字段值字典 或 None（取消）
        """
        request = UserInputRequest(
            request_type="custom",
            title=title,
            message=message,
            fields=fields,
        )
        
        return self._send_request_and_wait(request)
    
    def _send_request_and_wait(
        self,
        request: UserInputRequest,
        timeout: int = 300,  # 5分钟超时
    ) -> Optional[Dict[str, str]]:
        """
        发送请求并等待用户响应
        
        Args:
            request: 用户输入请求
            timeout: 超时时间（秒）
            
        Returns:
            用户输入的值 或 None（取消/超时）
        """
        # 清除旧的响应文件
        if self.response_file.exists():
            self.response_file.unlink()
        
        # 发送事件通知前端
        if self.emit:
            self.emit("request_input", request.to_dict())
            logger.info(f"发送用户输入请求: {request.id}, 类型: {request.type}")
        else:
            logger.error("没有设置 emit 回调，无法发送用户输入请求")
            return None
        
        # 等待响应
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.response_file.exists():
                try:
                    with open(self.response_file, "r", encoding="utf-8") as f:
                        response = json.load(f)
                    
                    # 检查是否是我们的请求
                    if response.get("request_id") == request.id:
                        # 删除响应文件
                        self.response_file.unlink()
                        
                        # 检查是否取消
                        if response.get("cancelled"):
                            logger.info(f"用户取消了输入请求: {request.id}")
                            return None
                        
                        values = response.get("values", {})
                        logger.info(f"收到用户输入: {request.id}")
                        return values
                        
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"读取响应文件失败: {e}")
            
            # 短暂等待
            time.sleep(0.2)
        
        logger.warning(f"用户输入请求超时: {request.id}")
        return None


# 便捷函数
def create_login_request(site_name: str = "网站") -> Dict[str, Any]:
    """创建登录请求的数据结构（用于 AI 规划）"""
    return {
        "type": "request_login",
        "site_name": site_name,
    }


def create_captcha_request(captcha_selector: str) -> Dict[str, Any]:
    """创建验证码请求的数据结构（用于 AI 规划）"""
    return {
        "type": "request_captcha",
        "captcha_selector": captcha_selector,
    }
