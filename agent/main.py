"""
DeskJarvis Agent主入口 - 智能化重构版 (Facade)

核心特性：
1. 遵循 Facade 模式，仅作为 Rust/Tauri 的入口
2. 核心逻辑委托给 TaskOrchestrator
3. 保持与旧版 API 兼容

遵循 docs/ARCHITECTURE.md 中的架构设计
"""

import sys
import logging
import time
import json
from typing import Dict, Any, Optional, Callable
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools.config import Config
from agent.planner.planner_factory import create_planner
from agent.executor.browser import BrowserExecutor
from agent.executor.file_manager import FileManager
from agent.executor.system_tools import SystemTools
from agent.executor.email_executor import EmailExecutor
from agent.memory import MemoryManager
from agent.core.embedding_model import SharedEmbeddingModel
from agent.core.intent_router import IntentRouter
from agent.orchestrator.plan_executor import PlanExecutor
from agent.orchestrator.task_orchestrator import TaskOrchestrator

logger = logging.getLogger(__name__)

class DeskJarvisAgent:
    """
    DeskJarvis Agent - Facade Layer
    
    所有实际逻辑由 Orchestrator 处理。
    此类仅负责组件初始化和请求转发。
    """
    
    def __init__(self, config: Config, use_crew: bool = False):
        """
        初始化Agent components
        """
        self.config = config
        
        # 1. 初始化基础工具
        self.file_manager = FileManager(config)
        self.system_tools = SystemTools(config)
        self.planner = create_planner(config)
        
        # 2. 初始化 Intent Router (使用共享嵌入模型)
        self.embedding_model = SharedEmbeddingModel.get_instance()
        self.embedding_model.start_loading()
        self.intent_router = IntentRouter(self.embedding_model)
        
        # 3. 记忆系统 (懒加载，但在 facade 中声明)
        self._memory: Optional[MemoryManager] = None
        
        # 4. 初始化浏览器执行器 (延迟绑定 callback)
        self.browser_executor = BrowserExecutor(config, emit_callback=self._dummy_emit)

        # 5. 构建工具映射
        self.email_executor = EmailExecutor(config, emit_callback=self._dummy_emit)
        self.tools_map = {
            "file_manager": self.file_manager,
            "system_tools": self.system_tools,
            "browser_executor": self.browser_executor,
            "email_executor": self.email_executor
        }
        
        # 6. 初始化 Orchestrator (延迟初始化，因为依赖 lazy memory 和 dynamic emit)
        self._orchestrator: Optional[TaskOrchestrator] = None
        
        logger.info("DeskJarvis Agent Initialized (Refactored Facade)")

    @property
    def memory(self) -> MemoryManager:
        """懒加载记忆管理器"""
        if self._memory is None:
            logger.info("Initializing MemoryManager...")
            start = time.time()
            self._memory = MemoryManager()
            logger.info(f"MemoryManager ready in {time.time() - start:.2f}s")
        return self._memory
        
    def _dummy_emit(self, event_type: str, data: Any):
        pass

    def _ensure_orchestrator(self, emit_callback: Callable):
        """确保 Orchestrator 已初始化且绑定了正确的 emit"""
        
        # 更新工具集的 emit 回调
        self.browser_executor.emit = emit_callback
        self.system_tools.emit = emit_callback
        self.email_executor.emit = emit_callback
        if hasattr(self.system_tools, 'code_interpreter'):
             self.system_tools.code_interpreter.emit = emit_callback
             self.browser_executor.user_input_manager.emit = emit_callback
             self.email_executor.file_compressor.emit = emit_callback # Assuming it might need it later

        # 创建/更新 PlanExecutor
        plan_executor = PlanExecutor(
            config=self.config,
            tools_map=self.tools_map,
            emit_callback=emit_callback
        )
        
        # 创建/更新 Orchestrator
        self._orchestrator = TaskOrchestrator(
            config=self.config,
            intent_router=self.intent_router,
            planner=self.planner,
            executor=plan_executor,
            memory_manager=self.memory # 触发 Memory 加载
        )

    def execute(
        self, 
        user_instruction: str, 
        progress_callback: Optional[Callable] = None, 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        入口方法：转发给 Orchestrator
        """
        # 1. 构造标准 emit 函数
        def emit(event_type: str, data: Dict[str, Any]):
            event = {
                "type": event_type,
                "timestamp": time.time(),
                "data": data
            }
            if progress_callback:
                progress_callback(event)
            else:
                print(json.dumps(event, ensure_ascii=False), flush=True)

        # 2. 准备 Orchestrator
        self._ensure_orchestrator(emit)
        
        if not self._orchestrator:
             return {"success": False, "message": "Orchestrator init failed"}

        # 3. 运行
        try:
            return self._orchestrator.run(user_instruction, emit, context)
        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Critical Error: {str(e)}",
                "user_instruction": user_instruction
            }
