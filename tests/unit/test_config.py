"""
配置模块单元测试
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.tools.config import Config


class TestConfigModels:
    """配置模型映射测试"""
    
    def test_claude_models(self):
        """测试 Claude 模型"""
        assert "claude" in Config.DEFAULT_MODELS
        assert Config.DEFAULT_MODELS["claude"] == "claude-3-5-sonnet-20241022"
    
    def test_deepseek_models(self):
        """测试 DeepSeek 模型"""
        assert "deepseek" in Config.DEFAULT_MODELS
        assert Config.DEFAULT_MODELS["deepseek"] == "deepseek-chat"
    
    def test_openai_models(self):
        """测试 OpenAI 模型"""
        assert "openai" in Config.DEFAULT_MODELS
    
    def test_grok_models(self):
        """测试 Grok 模型"""
        assert "grok" in Config.DEFAULT_MODELS


class TestDefaultConfig:
    """默认配置测试"""
    
    def test_default_config_exists(self):
        """测试默认配置存在"""
        assert hasattr(Config, 'DEFAULT_CONFIG')
        assert "provider" in Config.DEFAULT_CONFIG
        assert "model" in Config.DEFAULT_CONFIG
    
    def test_all_providers_have_models(self):
        """测试所有提供商都有模型"""
        providers = ["claude", "openai", "deepseek", "grok"]
        for provider in providers:
            assert provider in Config.DEFAULT_MODELS, f"Provider {provider} not found"
    
    def test_default_provider(self):
        """测试默认提供商"""
        assert Config.DEFAULT_CONFIG["provider"] in Config.DEFAULT_MODELS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
