"""
Result 模块单元测试
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.tools.result import Result, ok, err


class TestResult:
    """Result 类测试"""
    
    def test_ok_result(self):
        """测试成功结果"""
        result = ok("操作成功", data={"file": "/path/to/file"})
        
        assert result.success is True
        assert result.message == "操作成功"
        assert result.data == {"file": "/path/to/file"}
        assert result.error is None
    
    def test_err_result(self):
        """测试失败结果"""
        result = err("操作失败", error="详细错误信息")
        
        assert result.success is False
        assert result.message == "操作失败"
        assert result.error == "详细错误信息"
    
    def test_err_result_without_error(self):
        """测试没有详细错误的失败结果"""
        result = err("操作失败")
        
        assert result.success is False
        assert result.error == "操作失败"
    
    def test_to_dict(self):
        """测试转换为字典"""
        result = ok("成功", data={"count": 42})
        d = result.to_dict()
        
        assert d["success"] is True
        assert d["message"] == "成功"
        assert d["data"] == {"count": 42}
        assert d["error"] is None
    
    def test_from_dict(self):
        """测试从字典创建"""
        d = {
            "success": True,
            "message": "成功",
            "data": {"count": 42},
            "error": None,
        }
        
        result = Result.from_dict(d)
        
        assert result.success is True
        assert result.message == "成功"
        assert result.data == {"count": 42}
    
    def test_from_dict_missing_fields(self):
        """测试从不完整字典创建"""
        d = {"message": "部分数据"}
        
        result = Result.from_dict(d)
        
        assert result.success is False
        assert result.message == "部分数据"


class TestResultDataTypes:
    """Result 数据类型测试"""
    
    def test_result_with_list_data(self):
        """测试列表数据"""
        result = ok("获取成功", data={"files": ["/a.txt", "/b.txt"]})
        
        assert result.data["files"] == ["/a.txt", "/b.txt"]
    
    def test_result_with_nested_data(self):
        """测试嵌套数据"""
        result = ok("获取成功", data={
            "user": {
                "name": "test",
                "settings": {"theme": "dark"}
            }
        })
        
        assert result.data["user"]["settings"]["theme"] == "dark"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
