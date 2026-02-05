"""
异常模块单元测试
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.tools.exceptions import (
    DeskJarvisError,
    BrowserError,
    FileManagerError,
    PlannerError,
    ConfigError,
)


class TestDeskJarvisError:
    """基础异常类测试"""
    
    def test_basic_error(self):
        """测试基本错误"""
        error = DeskJarvisError("测试错误")
        
        assert error.message == "测试错误"
        assert error.details is None
        assert str(error) == "测试错误"
    
    def test_error_with_details(self):
        """测试带详情的错误"""
        error = DeskJarvisError("测试错误", details="详细信息")
        
        assert error.message == "测试错误"
        assert error.details == "详细信息"
        assert "详情: 详细信息" in str(error)
    
    def test_error_inheritance(self):
        """测试错误继承"""
        error = DeskJarvisError("测试")
        
        assert isinstance(error, Exception)


class TestBrowserError:
    """浏览器错误测试"""
    
    def test_browser_error(self):
        """测试浏览器错误"""
        error = BrowserError("页面加载失败")
        
        assert isinstance(error, DeskJarvisError)
        assert error.message == "页面加载失败"
    
    def test_browser_error_with_details(self):
        """测试带详情的浏览器错误"""
        error = BrowserError("元素未找到", details="selector: #submit-btn")
        
        assert "selector: #submit-btn" in str(error)


class TestFileManagerError:
    """文件管理错误测试"""
    
    def test_file_manager_error(self):
        """测试文件管理错误"""
        error = FileManagerError("文件不存在")
        
        assert isinstance(error, DeskJarvisError)
        assert error.message == "文件不存在"


class TestPlannerError:
    """规划器错误测试"""
    
    def test_planner_error(self):
        """测试规划器错误"""
        error = PlannerError("API 调用失败")
        
        assert isinstance(error, DeskJarvisError)
        assert error.message == "API 调用失败"


class TestConfigError:
    """配置错误测试"""
    
    def test_config_error(self):
        """测试配置错误"""
        error = ConfigError("配置文件格式错误")
        
        assert isinstance(error, DeskJarvisError)
        assert error.message == "配置文件格式错误"


class TestExceptionRaising:
    """异常抛出测试"""
    
    def test_raise_and_catch_base_error(self):
        """测试抛出和捕获基础错误"""
        with pytest.raises(DeskJarvisError) as exc_info:
            raise DeskJarvisError("测试抛出")
        
        assert exc_info.value.message == "测试抛出"
    
    def test_catch_subclass_as_base(self):
        """测试捕获子类作为基类"""
        with pytest.raises(DeskJarvisError):
            raise BrowserError("浏览器错误")
    
    def test_catch_specific_error(self):
        """测试捕获特定错误"""
        with pytest.raises(BrowserError):
            raise BrowserError("浏览器错误")
        
        # 不应该捕获其他类型
        with pytest.raises(BrowserError):
            try:
                raise FileManagerError("文件错误")
            except BrowserError:
                pass  # 不应该到这里
            except FileManagerError:
                raise BrowserError("转换后的错误")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
