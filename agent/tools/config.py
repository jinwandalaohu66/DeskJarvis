"""
配置管理模块：管理项目配置

遵循 docs/ARCHITECTURE.md 中的配置管理规范
"""

from typing import Optional, Dict, Any
from pathlib import Path
import json
import logging
from agent.tools.exceptions import ConfigError
from agent.tools.key_encryptor import KeyEncryptor

logger = logging.getLogger(__name__)


class Config:
    """
    配置管理类：加载和管理项目配置
    
    配置项：
    - api_key: Claude API密钥
    - model: 使用的模型名称
    - sandbox_path: 沙盒目录路径
    - auto_confirm: 是否自动确认操作
    - log_level: 日志级别
    """
    
    DEFAULT_CONFIG = {
        "provider": "claude",  # AI提供商: claude, openai, deepseek, grok
        "api_key": "",
        "model": "claude-3-5-sonnet-20241022",  # 根据provider自动选择默认模型
        "sandbox_path": str(Path.home() / ".deskjarvis" / "sandbox"),
        "auto_confirm": False,
        "log_level": "INFO",
    }
    
    # 各提供商的默认模型
    DEFAULT_MODELS = {
        "claude": "claude-3-5-sonnet-20241022",
        "openai": "gpt-4-turbo-preview",
        "chatgpt": "gpt-4-turbo-preview",
        "deepseek": "deepseek-chat",  # DeepSeek-V3，最强通用模型
        "grok": "grok-beta",
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        if config_path is None:
            config_dir = Path.home() / ".deskjarvis"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = str(config_dir / "config.json")
        
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """
        加载配置文件（自动解密 API Key）
        
        Raises:
            ConfigError: 当配置文件格式错误时
        """
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                
                # 自动解密 API Key（如果已加密）
                if "api_key" in self._config:
                    encrypted_key = self._config["api_key"]
                    if encrypted_key and encrypted_key.startswith("ENC:"):
                        self._config["api_key"] = KeyEncryptor.decrypt(encrypted_key)
                        logger.debug("[SECURITY_SHIELD] API Key 已自动解密")
                
                logger.info(f"配置文件已加载: {self.config_path}")
            else:
                # 使用默认配置
                self._config = self.DEFAULT_CONFIG.copy()
                self.save()
                logger.info("使用默认配置并创建配置文件")
        except json.JSONDecodeError as e:
            raise ConfigError(f"配置文件格式错误: {e}")
        except Exception as e:
            raise ConfigError(f"加载配置文件失败: {e}")
    
    def reload(self) -> None:
        """从磁盘强制重新加载配置"""
        logger.info("强制从磁盘重新加载配置...")
        self.load()
    
    def save(self) -> None:
        """
        保存配置到文件（自动加密 API Key）
        
        Raises:
            ConfigError: 当保存失败时
        """
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建副本用于保存（加密 API Key）
            config_to_save = self._config.copy()
            if "api_key" in config_to_save:
                plain_key = config_to_save["api_key"]
                if plain_key and not plain_key.startswith("ENC:"):
                    # 加密 API Key
                    config_to_save["api_key"] = KeyEncryptor.encrypt(plain_key)
                    logger.debug("[SECURITY_SHIELD] API Key 已自动加密")
            
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config_to_save, f, indent=2, ensure_ascii=False)
            logger.debug(f"配置已保存: {self.config_path}")
        except Exception as e:
            raise ConfigError(f"保存配置文件失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        
        Args:
            key: 配置键
            default: 默认值
        
        Returns:
            配置值
        """
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置项
        
        Args:
            key: 配置键
            value: 配置值
        """
        self._config[key] = value
        logger.debug(f"配置已更新: {key} = {value}")
    
    def validate(self) -> bool:
        """
        验证配置是否完整
        
        Returns:
            配置是否有效
        """
        if not self.get("api_key"):
            logger.warning("API密钥未设置")
            return False
        return True
    
    @property
    def api_key(self) -> str:
        """获取API密钥"""
        return self.get("api_key", "")
    
    @property
    def provider(self) -> str:
        """获取AI提供商"""
        return self.get("provider", self.DEFAULT_CONFIG["provider"])
    
    @property
    def model(self) -> str:
        """获取模型名称"""
        model = self.get("model")
        if not model:
            # 如果没有设置模型，根据provider使用默认模型
            provider = self.provider
            model = self.DEFAULT_MODELS.get(provider, self.DEFAULT_CONFIG["model"])
        return model
    
    @property
    def sandbox_path(self) -> Path:
        """获取沙盒路径"""
        return Path(self.get("sandbox_path", self.DEFAULT_CONFIG["sandbox_path"]))
    
    @property
    def auto_confirm(self) -> bool:
        """是否自动确认"""
        return self.get("auto_confirm", False)
    
    @property
    def log_level(self) -> str:
        """获取日志级别"""
        return self.get("log_level", "INFO")

    @property
    def email_sender(self) -> Optional[str]:
        """获取发件人邮箱"""
        return self.get("email_sender")

    @property
    def email_password(self) -> Optional[str]:
        """获取发件人密码"""
        return self.get("email_password")

    @property
    def email_smtp_server(self) -> str:
        """获取SMTP服务器"""
        return self.get("email_smtp_server", "smtp.gmail.com")

    @property
    def email_smtp_port(self) -> int:
        """获取SMTP端口"""
        return int(self.get("email_smtp_port", 587))

    @property
    def email_imap_server(self) -> str:
        """获取IMAP服务器"""
        # 如果未设置，尝试根据SMTP服务器推断
        imap = self.get("email_imap_server")
        if not imap:
            smtp = self.email_smtp_server
            if "smtp.qq.com" in smtp:
                return "imap.qq.com"
            if "smtp.gmail.com" in smtp:
                return "imap.gmail.com"
            if "smtp.outlook.com" in smtp:
                return "outlook.office365.com"
            # 默认尝试替换前缀
            if smtp.startswith("smtp."):
                return smtp.replace("smtp.", "imap.")
            return "imap.gmail.com"
        return imap

    @property
    def email_imap_port(self) -> int:
        """获取IMAP端口"""
        return int(self.get("email_imap_port", 993))
