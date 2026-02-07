"""
用户输入请求模块

用于在自动化过程中请求用户输入（登录、验证码等）
通过事件通知前端，通过文件交换数据
"""

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
    
    def request_qr_login(
        self,
        qr_image: str,  # base64 编码的二维码图片
        site_name: str = "网站",
        message: Optional[str] = None,
    ) -> bool:
        """
        请求二维码登录
        
        Args:
            qr_image: base64 编码的二维码图片
            site_name: 网站名称
            message: 额外提示信息
            
        Returns:
            True 如果用户确认已扫码，False 如果取消/超时
        """
        request = UserInputRequest(
            request_type="qr_login",
            title=f"扫码登录 - {site_name}",
            message=message or "请使用手机扫描二维码登录",
            captcha_image=qr_image,  # 复用此字段传递 QR 图片
            fields=[],  # QR 登录不需要输入字段
        )
        
        result = self._send_request_and_wait(request, timeout=600)  # QR 登录允许 10 分钟
        # 对于 QR 登录，只要收到响应（未取消）就视为成功
        return result is not None
    
    def request_email_config(
        self,
        default_smtp: str = "smtp.gmail.com",
        default_port: int = 587,
        message: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        请求邮件配置信息
        
        Args:
            default_smtp: 默认 SMTP 服务器
            default_port: 默认端口
            message: 额外提示信息
            
        Returns:
            {"smtp_server": "...", "smtp_port": "...", "sender_email": "...", "password": "..."} 或 None
        """
        request = UserInputRequest(
            request_type="email_config",
            title="配置邮件服务",
            message=message or "请填写您的邮件服务配置，以便 DeskJarvis 可以为您发送邮件。建议使用“应用专用密码”。",
            fields=[
                {
                    "name": "sender_email",
                    "label": "发件人邮箱",
                    "type": "text",
                    "placeholder": "例如: yourname@gmail.com",
                    "required": True,
                },
                {
                    "name": "password",
                    "label": "密码 / 应用专用密码",
                    "type": "password",
                    "placeholder": "请输入密码或 App Password",
                    "required": True,
                },
                {
                    "name": "smtp_server",
                    "label": "SMTP 服务器",
                    "type": "text",
                    "value": default_smtp,
                    "placeholder": "例如: smtp.gmail.com",
                    "required": True,
                },
                {
                    "name": "smtp_port",
                    "label": "SMTP 端口",
                    "type": "number",
                    "value": str(default_port),
                    "placeholder": "例如: 587 或 465",
                    "required": True,
                },
            ],
        )
        
        return self._send_request_and_wait(request)
    
    def _send_request_and_wait(
        self,
        request: UserInputRequest,
        timeout: int = 600,  # 10分钟超时（从300增加）
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
            logger.info(f"响应文件路径: {self.response_file}")
        else:
            logger.error("没有设置 emit 回调，无法发送用户输入请求")
            return None
        
        # 等待响应，增加心跳机制
        start_time = time.time()
        last_heartbeat = start_time
        heartbeat_interval = 5  # 每5秒发送一次心跳
        
        while time.time() - start_time < timeout:
            # 发送心跳事件（让前端知道后端还在等待）
            current_time = time.time()
            if current_time - last_heartbeat >= heartbeat_interval:
                if self.emit:
                    elapsed = int(current_time - start_time)
                    remaining = timeout - elapsed
                    self.emit("waiting_for_input", {
                        "request_id": request.id,
                        "elapsed": elapsed,
                        "remaining": remaining,
                    })
                    logger.debug(f"等待用户输入中... 已等待 {elapsed}秒, 剩余 {remaining}秒")
                last_heartbeat = current_time
            
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
                        logger.info(f"收到用户输入: {request.id}, 值: {list(values.keys())}")
                        return values
                        
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"读取响应文件失败: {e}")
            
            # 增加轮询间隔（从0.2秒增加到0.5秒，减少CPU占用）
            time.sleep(0.5)
        
        logger.warning(f"用户输入请求超时: {request.id}, 超时时间: {timeout}秒")
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
