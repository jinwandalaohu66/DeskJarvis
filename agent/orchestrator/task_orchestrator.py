"""
Task Orchestrator - High Level Workflow Manager

功能：
- 接收用户指令
- 协调 IntentRouter (意图识别)
- 协调 Planner (制定计划)
- 协调 PlanExecutor (执行计划)
- 管理记忆上下文 (Memory Context)
"""

import time
import logging
from typing import Dict, Any, Optional, Callable

from agent.core.intent_router import IntentRouter
from agent.orchestrator.plan_executor import PlanExecutor

logger = logging.getLogger(__name__)

class TaskOrchestrator:
    """
    任务编排器 (The Brain)
    负责决策流程：Instruction -> [Router] -> [Planner] -> [Executor] -> Result
    """
    
    def __init__(
        self, 
        config, 
        intent_router: IntentRouter, 
        planner, 
        executor: PlanExecutor,
        memory_manager
    ):
        self.config = config
        self.intent_router = intent_router
        self.planner = planner
        self.executor = executor
        self.memory = memory_manager
        # Session Cache (Protocol R3)
        self.file_context_buffer = {}
        
    def run(
        self, 
        user_instruction: str, 
        emit: Callable,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        运行完整任务流程
        """
        # 初始化计时器
        start_time = time.time()
        
        # 🟢 CRITICAL: 每次运行前刷新配置，并根据最新配置重置规划器和执行器状态
        if hasattr(self.config, "reload"):
            self.config.reload()
            # 重新创建规划器以确保使用最新的 API Key/Provider
            from agent.planner.planner_factory import create_planner
            self.planner = create_planner(self.config)
            logger.info("已根据最新配置刷新规划器状态")

        if context is None:
            context = {}
        
        # 注入实时时间感官 (Protocol Phase 38+)
        current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
        context["current_time"] = current_time_str
        
        # 将会话缓存注入 context，供 Planner 和 Executor 共享 (Protocol R3)
        context["_file_context_buffer"] = self.file_context_buffer
        
        # 检查停止标志（如果 context 中有停止检查函数）
        check_stop = context.get("_check_stop")
        if check_stop and callable(check_stop):
            if check_stop():
                logger.info("任务在执行前已被停止")
                return {
                    "success": False,
                    "message": "任务已取消",
                    "steps": [],
                    "user_instruction": user_instruction
                }
            
        emit("thinking", {
            "content": "Received instruction: " + user_instruction[:50] + "...",
            "phase": "analyzing"
        })

        # 1. 尝试快速通道 (Semantic Intent Router)
        fast_result = self._try_fast_path(user_instruction, emit)
        if fast_result:
            return fast_result
            
        # 2. 获取记忆上下文
        # 注意：这里需要处理 memory 为 None 的情况（懒加载未触发）
        memory_context = ""
        if self.memory:
            memory_context = self.memory.get_context_for_instruction(user_instruction)
            if memory_context:
                context["memory_context"] = memory_context
                
        emit("thinking", {
            "content": "Planning steps...",
            "phase": "planning"
        })
        
        # 3. AI 规划 (Planner)
        try:
             # planner.plan 需要适配现有接口
             # 假设 planner.plan(instruction, context) -> steps
             plan_steps = self.planner.plan(user_instruction, context)
             
             # 规划后再次检查停止标志
             check_stop = context.get("_check_stop")
             if check_stop and callable(check_stop) and check_stop():
                 logger.info("任务在规划后已被停止")
                 return {
                     "success": False,
                     "message": "任务已取消",
                     "steps": [],
                     "user_instruction": user_instruction
                 }
             
             emit("plan_ready", {
                "content": "Plan generated.",
                "steps": plan_steps,
                "step_count": len(plan_steps)
            })
             
        except Exception as e:
            logger.error(f"Planning failed: {e}", exc_info=True)
            return {
                "success": False, 
                "message": f"Planning failed: {str(e)}",
                "steps": [],
                "user_instruction": user_instruction
            }
            
        # 4. 执行计划 (Executor)
        # 🔴 CRITICAL: 确保 context 中包含停止检查函数和 stop_event
        check_stop = context.get("_check_stop")
        if check_stop:
            context["_check_stop"] = check_stop
        
        # 🔴 CRITICAL: 传递 stop_event 给所有 executor（如果存在）
        stop_event = context.get("_stop_event")
        if stop_event:
            context["_stop_event"] = stop_event
            # 设置 PlanExecutor 中所有 executor 的 stop_event
            if hasattr(self.executor, 'tools'):
                for executor_name, executor_instance in self.executor.tools.items():
                    if hasattr(executor_instance, 'stop_event'):
                        executor_instance.stop_event = stop_event
                        logger.debug(f"已设置 {executor_name} 的 stop_event")
        
        # 🔴 CRITICAL: 规划完成后，立即 emit "executing" 事件，通知前端进入执行阶段
        emit("executing", {
            "step_count": len(plan_steps),
            "current_step": 0,
            "total_steps": len(plan_steps),
            "message": "开始执行计划"
        })
        
        # 🔴 CRITICAL: 在执行前再次检查停止标志
        import threading
        if stop_event and isinstance(stop_event, threading.Event) and stop_event.is_set():
            logger.info("任务在执行前已被停止（通过 stop_event）")
            return {
                "success": False,
                "message": "任务已取消",
                "steps": [],
                "user_instruction": user_instruction
            }
        
        check_stop = context.get("_check_stop")
        if check_stop and callable(check_stop) and check_stop():
            logger.info("任务在执行前已被停止（通过检查函数）")
            return {
                "success": False,
                "message": "任务已取消",
                "steps": [],
                "user_instruction": user_instruction
            }
        
        result = self.executor.execute_plan(
            plan=plan_steps,
            user_instruction=user_instruction,
            context=context
        )
        
        duration = time.time() - start_time
        
        # 5. 保存记忆 (Memory) - 使用线程安全队列，避免阻塞和并发冲突
        if self.memory and result.get("success"):
            try:
                # 提取文件
                files_involved = []
                for step_res in result.get("steps", []):
                     p = step_res.get("step", {}).get("params", {})
                     for k in ["path", "file_path", "save_path"]:
                         if k in p:
                             files_involved.append(p[k])
                
                # 使用线程安全队列保存记忆（非阻塞，带文件锁）
                if not hasattr(self, '_memory_queue'):
                    from agent.tools.memory_queue import ThreadSafeMemoryQueue
                    self._memory_queue = ThreadSafeMemoryQueue(self.memory)
                
                self._memory_queue.enqueue_save(
                    instruction=user_instruction,
                    steps=[s["step"] for s in result.get("steps", [])],
                    result=result,
                    success=True,
                    duration=duration,
                    files_involved=files_involved
                )
                logger.debug("[SECURITY_SHIELD] 记忆保存任务已加入线程安全队列")
            except Exception as e:
                logger.warning(f"[SECURITY_SHIELD] 加入记忆存储队列失败: {e}")
                
        return result

    def _try_fast_path(self, instruction: str, emit: Callable) -> Optional[Dict[str, Any]]:
        """尝试快速通道"""
        if not self.intent_router:
            return None
            
        match = self.intent_router.detect(instruction)
        if not match:
            return None
            
        logger.info(f"[Orchestrator] Fast path hit: {match.intent_type}")
        
        # 构造单步计划
        step = {
            "type": match.metadata.get("type", "unknown"),
            "action": match.metadata.get("action", "unknown"),
            "params": {
                "instruction": instruction,
                "action": match.metadata.get("action", ""),
            },
            "description": f"Fast Execute: {match.intent_type}",
        }
        
        if match.metadata.get("type") == "text_process":
             step["params"]["text"] = instruction
             step["params"]["target_lang"] = "English"
        
        # 处理应用操作：提取 app_name
        if match.intent_type in ["app_open", "app_close"]:
            app_name = self._extract_app_name(instruction)
            if app_name:
                step["params"]["app_name"] = app_name
                # 确保 type 正确（虽然 intent_metadata 已经修复，但这里双重保险）
                if match.intent_type == "app_open":
                    step["type"] = "open_app"
                elif match.intent_type == "app_close":
                    step["type"] = "close_app"
            else:
                logger.warning(f"⚠️ Fast path: 无法从指令中提取应用名: {instruction}")
                # 如果无法提取，回退到正常规划流程
                return None

        # 构造一个只包含单步的 plan
        plan = [step]
        
        emit("thinking", {"content": f"Fast path: {match.intent_type}", "phase": "fast_path"})
        
        # 直接调用 executor 执行
        # 使用空的 context
        return self.executor.execute_plan(plan, instruction, context={})
    
    def _extract_app_name(self, instruction: str) -> Optional[str]:
        """
        从用户指令中提取应用名称
        
        例如：
        - "打开汽水音乐" → "汽水音乐"
        - "关闭Safari" → "Safari"
        - "启动计算器" → "计算器"
        - "退出微信" → "微信"
        
        Args:
            instruction: 用户指令
        
        Returns:
            提取的应用名称，如果无法提取则返回None
        """
        import re
        
        # 移除首尾空格
        instruction = instruction.strip()
        
        # 定义关键词模式（用于分割）
        # 打开/启动/运行/启动应用
        open_keywords = ["打开", "启动", "运行", "开启", "open", "launch", "start", "run"]
        # 关闭/退出/结束/关闭应用
        close_keywords = ["关闭", "退出", "结束", "停止", "close", "quit", "exit", "stop", "kill"]
        
        # 合并所有关键词
        all_keywords = open_keywords + close_keywords
        
        # 尝试匹配：关键词 + 应用名
        # 模式1: "打开 应用名" 或 "open 应用名"
        pattern1 = r'(?:' + '|'.join(re.escape(kw) for kw in all_keywords) + r')\s+(.+)'
        match1 = re.search(pattern1, instruction, re.IGNORECASE)
        if match1:
            app_name = match1.group(1).strip()
            # 移除可能的后续操作（如"然后"、"并"等）
            app_name = re.split(r'[然后并和,，]', app_name)[0].strip()
            if app_name:
                return app_name
        
        # 模式2: 如果指令本身就是应用名（没有关键词）
        # 这种情况较少，但可以作为兜底
        if len(instruction) < 50 and not any(kw in instruction for kw in ["然后", "并", "和", "再"]):
            # 可能是直接说应用名
            return instruction.strip()
        
        # 无法提取
        logger.warning(f"⚠️ 无法从指令中提取应用名: {instruction}")
        return None
