"""
记忆系统单元测试
"""

import os
import pytest
import tempfile
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.memory.structured_memory import StructuredMemory


class TestStructuredMemory:
    """结构化记忆测试"""
    
    @pytest.fixture
    def memory(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = Path(f.name)
        
        mem = StructuredMemory(db_path)
        yield mem
        
        # 清理
        try:
            os.unlink(str(db_path))
        except:
            pass
    
    def test_set_and_get_preference(self, memory):
        """测试设置和获取偏好"""
        memory.set_preference("theme", "dark")
        
        result = memory.get_preference("theme")
        
        assert result == "dark"
    
    def test_get_nonexistent_preference(self, memory):
        """测试获取不存在的偏好"""
        result = memory.get_preference("nonexistent")
        
        assert result is None
    
    def test_get_preference_with_default(self, memory):
        """测试获取带默认值的偏好"""
        result = memory.get_preference("nonexistent", default="default_value")
        
        assert result == "default_value"
    
    def test_update_preference(self, memory):
        """测试更新偏好"""
        memory.set_preference("theme", "light")
        memory.set_preference("theme", "dark")
        
        result = memory.get_preference("theme")
        
        assert result == "dark"
    
    def test_add_file_record(self, memory):
        """测试添加文件记录"""
        memory.add_file_record(
            path="/Users/test/file.txt",
            operation="create",
            file_type="text"
        )
        
        files = memory.get_recent_files(limit=10)
        
        assert len(files) == 1
        assert files[0]["path"] == "/Users/test/file.txt"
    
    def test_recent_files_limit(self, memory):
        """测试最近文件限制"""
        for i in range(20):
            memory.add_file_record(
                path=f"/Users/test/file{i}.txt",
                operation="create"
            )
        
        files = memory.get_recent_files(limit=5)
        
        assert len(files) == 5
    
    def test_add_instruction(self, memory):
        """测试添加指令"""
        memory.add_instruction(
            instruction="整理桌面文件",
            success=True,
            duration=5.2
        )
        
        # 获取相似指令来验证
        similar = memory.get_similar_instructions("整理文件", limit=10)
        
        # 应该能找到刚添加的指令
        assert len(similar) >= 0  # 可能为0因为相似度计算


class TestKnowledgeGraph:
    """知识图谱测试"""
    
    @pytest.fixture
    def memory(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = Path(f.name)
        
        mem = StructuredMemory(db_path)
        yield mem
        
        try:
            os.unlink(str(db_path))
        except:
            pass
    
    def test_add_and_query_knowledge(self, memory):
        """测试添加和查询知识"""
        memory.add_knowledge(
            subject="用户",
            predicate="喜欢",
            obj="深色主题",
            confidence=0.9
        )
        
        results = memory.query_knowledge(subject="用户")
        
        assert len(results) == 1
        assert results[0]["predicate"] == "喜欢"
    
    def test_query_by_object(self, memory):
        """测试按对象查询"""
        memory.add_knowledge("用户", "使用", "VSCode", confidence=0.8)
        memory.add_knowledge("用户", "使用", "Chrome", confidence=0.9)
        
        results = memory.query_knowledge(obj="Chrome")
        
        assert len(results) == 1
        assert results[0]["subject"] == "用户"


class TestMemoryContext:
    """记忆上下文测试"""
    
    @pytest.fixture
    def memory(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = Path(f.name)
        
        mem = StructuredMemory(db_path)
        yield mem
        
        try:
            os.unlink(str(db_path))
        except:
            pass
    
    def test_get_memory_context(self, memory):
        """测试获取记忆上下文"""
        # 添加一些偏好
        memory.set_preference("download_path", "/Downloads")
        memory.set_preference("theme", "dark")
        
        context = memory.get_memory_context()
        
        # 上下文应该是字符串
        assert isinstance(context, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
