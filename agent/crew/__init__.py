"""
DeskJarvis 多代理协作系统

使用 SimpleCrew 实现的多代理协作，让 AI 像团队一样工作：
- Planner Agent: 分析任务，制定计划
- Executor Agent: 执行具体操作
- Reflector Agent: 分析失败，给出建议
- Summarizer Agent: 总结结果，输出给用户
"""

from agent.crew.crew_manager import CrewManager, TaskComplexityAnalyzer
from agent.crew.simple_crew import SimpleCrew

__all__ = [
    "CrewManager",
    "TaskComplexityAnalyzer",
    "SimpleCrew",
]
