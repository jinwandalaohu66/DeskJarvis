"""
配置管理模块：管理项目配置

遵循 docs/ARCHITECTURE.md 中的配置管理规范
"""

from typing import Optional, Dict, Any
from pathlib import Path
import json
import logging
from agent.tools.exceptions import ConfigError

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
        加载配置文件
        
        Raises:
            ConfigError: 当配置文件格式错误时
        """
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
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
    
    def save(self) -> None:
        """
        保存配置到文件
        
        Raises:
            ConfigError: 当保存失败时
        """
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
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
