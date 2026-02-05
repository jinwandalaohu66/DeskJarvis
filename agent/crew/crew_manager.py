"""
DeskJarvis 多代理协作管理器

简化版，直接使用 SimpleCrew
"""

import logging
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)

# 导入简化版多代理系统
try:
    from agent.crew.simple_crew import SimpleCrew
    SIMPLE_CREW_AVAILABLE = True
except ImportError:
    SIMPLE_CREW_AVAILABLE = False
    logger.warning("SimpleCrew 导入失败")


class CrewManager:
    """
    多代理协作管理器
    
    使用 SimpleCrew 实现多代理协作
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        emit_callback: Optional[Callable] = None
    ):
        """
        初始化协作管理器
        
        Args:
            config: 配置，包含 llm 设置等
            emit_callback: 进度回调函数
        """
        self.config = config or {}
        self.emit = emit_callback
        
        # LLM 配置
        self.llm_config = {
            "provider": self.config.get("ai_provider", "deepseek"),
            "model": self.config.get("ai_model", "deepseek-chat"),
            "api_key": self.config.get("api_key", ""),
        }
    
    def _emit_progress(self, event_type: str, data: Dict[str, Any]):
        """发送进度事件"""
        if self.emit:
            self.emit(event_type, data)
    
    def execute(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行多代理协作任务
        """
        if not SIMPLE_CREW_AVAILABLE:
            return self._fallback_execute(instruction, context)
        
        try:
            simple_crew = SimpleCrew(
                config={
                    "ai_provider": self.llm_config.get("provider"),
                    "ai_model": self.llm_config.get("model"),
                    "api_key": self.llm_config.get("api_key"),
                },
                emit_callback=self.emit
            )
            return simple_crew.execute(instruction, context)
        except Exception as e:
            logger.exception(f"SimpleCrew 执行失败: {e}")
            return self._fallback_execute(instruction, context)
    
    def _fallback_execute(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        回退到单代理模式
        """
        self._emit_progress("agent_progress", {
            "agent": "System",
            "message": "多代理不可用，使用单代理模式..."
        })
        
        return {
            "success": False,
            "fallback": True,
            "message": "请使用单代理模式执行",
            "mode": "single-agent"
        }
    
    def is_available(self) -> bool:
        """检查多代理功能是否可用"""
        return SIMPLE_CREW_AVAILABLE and bool(self.llm_config.get("api_key"))


class TaskComplexityAnalyzer:
    """
    任务复杂度分析器
    
    决定是否使用多代理模式
    """
    
    # 简单任务关键词
    SIMPLE_KEYWORDS = [
        "打开", "截图", "删除", "关闭", "打开应用", "截个图",
        "open", "screenshot", "delete", "close"
    ]
    
    # 复杂任务关键词
    COMPLEX_KEYWORDS = [
        "批量", "分析", "整理", "报告", "下载并", "然后", "接着",
        "所有文件", "每个", "遍历", "总结",
        "batch", "analyze", "organize", "report", "download and", "then"
    ]
    
    @classmethod
    def analyze(cls, instruction: str) -> str:
        """
        分析任务复杂度
        
        Returns:
            "simple": 简单任务，用单代理
            "normal": 普通任务，可选多代理
            "complex": 复杂任务，推荐多代理
        """
        instruction_lower = instruction.lower()
        
        # 检查复杂任务关键词
        complex_count = sum(1 for kw in cls.COMPLEX_KEYWORDS if kw in instruction_lower)
        if complex_count >= 2:
            return "complex"
        
        # 检查简单任务关键词
        simple_count = sum(1 for kw in cls.SIMPLE_KEYWORDS if kw in instruction_lower)
        if simple_count >= 1 and complex_count == 0:
            return "simple"
        
        # 根据指令长度判断
        if len(instruction) > 50:
            return "normal"
        
        return "simple"
