"""
DeskJarvis 记忆系统

三层架构：
- 层1：结构化记忆（SQLite）- 偏好、历史、知识图谱
- 层2：向量记忆（Chroma）- 语义搜索、相似匹配
- 层3：高级记忆（情绪、工作流）- 情绪感知、模式发现
"""

from agent.memory.structured_memory import StructuredMemory
from agent.memory.vector_memory import VectorMemory
from agent.memory.advanced_memory import AdvancedMemory
from agent.memory.memory_manager import MemoryManager

__all__ = [
    "StructuredMemory",
    "VectorMemory", 
    "AdvancedMemory",
    "MemoryManager",
]
