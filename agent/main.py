"""
DeskJarvis Agent主入口 - 智能化重构版 (Facade)

核心特性：
1. 遵循 Facade 模式，仅作为 Rust/Tauri 的入口
2. 核心逻辑委托给 TaskOrchestrator
3. 保持与旧版 API 兼容
4. 线程安全的并发处理
5. 完善的错误处理和资源清理

遵循 docs/ARCHITECTURE.md 中的架构设计
"""

# === 在导入任何其他模块之前应用 nest_asyncio ===
# 这允许 Playwright 的同步 API 在 asyncio 事件循环中使用
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    # nest_asyncio 未安装，会在浏览器启动时给出明确错误提示
    pass

import sys
import logging
import time
import json
import traceback
import contextvars
from typing import Dict, Any, Optional, Callable, Set
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

# === 线程安全的上下文变量（用于传递 emit 回调）===
# 每个任务拥有独立的事件流上下文，避免并发竞态
_emit_context: contextvars.ContextVar[Optional[Callable]] = contextvars.ContextVar('emit_callback', default=None)


class DeskJarvisAgent:
    """
    DeskJarvis Agent - Facade Layer
    
    所有实际逻辑由 Orchestrator 处理。
    此类仅负责组件初始化和请求转发。
    
    线程安全改进：
    - 使用 contextvars 传递 emit 回调，避免并发竞态
    - 每个任务拥有独立的事件流上下文
    """
    
    def __init__(self, config: Config, use_crew: bool = False):
        """
        初始化Agent components
        """
        self.config = config
        
        # 1. 初始化基础工具（使用 dummy emit，后续通过上下文注入）
        self.file_manager = FileManager(config)
        self.system_tools = SystemTools(config)
        self.planner = create_planner(config)
        
        # 2. 初始化 Intent Router (使用共享嵌入模型)
        self.embedding_model = SharedEmbeddingModel.get_instance()
        self.embedding_model.start_loading()  # 后台预加载
        self.intent_router = IntentRouter(self.embedding_model)
        
        # 3. 记忆系统 (懒加载，但在 facade 中声明)
        self._memory: Optional[MemoryManager] = None
        
        # 4. 初始化执行器（使用 dummy emit，后续通过上下文注入）
        self.browser_executor = BrowserExecutor(config, emit_callback=self._dummy_emit)
        self.email_executor = EmailExecutor(config, emit_callback=self._dummy_emit)
        
        # 5. 构建工具映射
        self.tools_map = {
            "file_manager": self.file_manager,
            "system_tools": self.system_tools,
            "browser_executor": self.browser_executor,
            "email_executor": self.email_executor
        }
        
        # 6. 初始化 Orchestrator (延迟初始化，因为依赖 lazy memory 和 dynamic emit)
        self._orchestrator: Optional[TaskOrchestrator] = None
        
        logger.info("DeskJarvis Agent Initialized (Refactored Facade with Thread Safety)")

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
        """占位 emit 函数（初始化时使用）"""
        # 尝试从上下文获取真实的 emit
        emit = _emit_context.get()
        if emit:
            emit(event_type, data)
    
    def _inject_emit_recursive(self, obj: Any, emit_callback: Callable, visited: Optional[Set[int]] = None):
        """
        递归注入 emit 回调到所有需要的地方
        
        消除硬编码的 hasattr 补丁，自动发现并设置所有 emit 属性
        
        Args:
            obj: 要注入的对象
            emit_callback: emit 回调函数
            visited: 已访问的对象集合（防止循环引用）
        """
        if visited is None:
            visited = set()
        
        # 防止循环引用
        obj_id = id(obj)
        if obj_id in visited:
            return
        visited.add(obj_id)
        
        # 如果对象有 emit 属性，直接设置
        if hasattr(obj, 'emit'):
            try:
                obj.emit = emit_callback
                logger.debug(f"[SECURITY_SHIELD] 已注入 emit 到 {type(obj).__name__}")
            except Exception as e:
                logger.warning(f"[SECURITY_SHIELD] 注入 emit 到 {type(obj).__name__} 失败: {e}")
        
        # 递归处理对象的属性
        for attr_name in dir(obj):
            # 跳过私有属性和方法
            if attr_name.startswith('_'):
                continue
            
            try:
                attr = getattr(obj, attr_name)
                # 跳过方法和不可访问的属性
                if callable(attr) or isinstance(attr, (int, float, str, bool, type(None))):
                    continue
                
                # 递归处理对象属性
                if isinstance(attr, object):
                    self._inject_emit_recursive(attr, emit_callback, visited)
            except Exception:
                # 忽略无法访问的属性
                continue

    def _create_orchestrator(self, emit_callback: Callable) -> TaskOrchestrator:
        """
        创建新的 Orchestrator 实例（每次调用创建新实例，避免并发竞态）
        
        使用 contextvars 传递 emit，确保每个任务拥有独立的事件流上下文
        
        Args:
            emit_callback: emit 回调函数
            
        Returns:
            TaskOrchestrator 实例
        """
        # === 设置上下文变量（线程安全）===
        _emit_context.set(emit_callback)
        
        # === 递归注入 emit 到所有工具 ===
        for tool_name, tool in self.tools_map.items():
            self._inject_emit_recursive(tool, emit_callback)
            logger.debug(f"[SECURITY_SHIELD] 已为 {tool_name} 注入 emit 回调")
        
        # === 创建 PlanExecutor（传入 emit）===
        plan_executor = PlanExecutor(
            config=self.config,
            tools_map=self.tools_map,
            emit_callback=emit_callback
        )
        
        # === 创建 Orchestrator ===
        orchestrator = TaskOrchestrator(
            config=self.config,
            intent_router=self.intent_router,
            planner=self.planner,
            executor=plan_executor,
            memory_manager=self.memory  # 触发 Memory 加载
        )
        
        return orchestrator

    def _try_intent_shortcut(self, user_instruction: str, emit: Callable, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        意图路由快路径：在进入昂贵的 LLM 规划之前，尝试使用 intent_router 快速处理
        
        支持的简单系统控制操作：
        - 截图 (screenshot)
        - 音量控制 (volume_control)
        - 亮度控制 (brightness_control)
        - 系统信息 (system_info)
        - 应用打开/关闭 (app_open/app_close)
        
        Args:
            user_instruction: 用户指令
            emit: emit 回调函数
            context: 上下文信息
            
        Returns:
            如果匹配快路径，返回执行结果；否则返回 None
        """
        # === 等待嵌入模型就绪（非阻塞，最多等待2秒）===
        if not self.embedding_model.wait_until_ready(timeout=2.0):
            logger.debug("[SECURITY_SHIELD] 嵌入模型未就绪，跳过快路径")
            return None
        
        try:
            # 尝试意图识别
            match = self.intent_router.detect(user_instruction, threshold=0.65)
            if not match:
                return None
            
            intent_type = match.intent_type
            metadata = match.metadata
            
            # 只处理简单的系统控制操作（不需要复杂规划）
            supported_intents = [
                "screenshot", "volume_control", "brightness_control", 
                "system_info", "app_open", "app_close"
            ]
            
            if intent_type not in supported_intents:
                logger.debug(f"[SECURITY_SHIELD] 意图 '{intent_type}' 不在快路径支持列表中")
                return None
            
            logger.info(f"[SECURITY_SHIELD] 快路径匹配: {intent_type} (置信度: {match.confidence:.2f})")
            
            # 构造简单步骤列表
            step = {
                "type": metadata.get("type", "unknown"),
                "action": metadata.get("action", "unknown"),
                "params": {
                    "instruction": user_instruction,
                    "action": metadata.get("action", ""),
                },
                "description": f"快路径执行: {intent_type}",
            }
            
            # 特殊处理：system_control 类型映射到具体操作类型
            if metadata.get("type") == "system_control":
                action = metadata.get("action", "")
                if action == "volume":
                    step["type"] = "set_volume"
                    # 尝试从指令中解析音量值或操作
                    step["params"] = self._parse_volume_params(user_instruction)
                elif action == "brightness":
                    step["type"] = "set_brightness"
                    # 尝试从指令中解析亮度值或操作
                    step["params"] = self._parse_brightness_params(user_instruction)
                elif action == "sys_info":
                    step["type"] = "get_system_info"
                    step["params"] = {"info_type": "all"}
                else:
                    logger.warning(f"[SECURITY_SHIELD] 未知的 system_control action: {action}，回退到正常规划")
                    return None
            
            # 特殊处理：文本处理
            elif metadata.get("type") == "text_process":
                step["params"]["text"] = user_instruction
                step["params"]["target_lang"] = "English"
            
            # 特殊处理：应用操作
            elif intent_type in ["app_open", "app_close"]:
                # 从 TaskOrchestrator 借用应用名提取逻辑
                app_name = self._extract_app_name(user_instruction)
                if app_name:
                    step["params"]["app_name"] = app_name
                    if intent_type == "app_open":
                        step["type"] = "open_app"
                    elif intent_type == "app_close":
                        step["type"] = "close_app"
                else:
                    logger.warning("[SECURITY_SHIELD] 无法提取应用名，回退到正常规划")
                    return None
            
            # 构造计划并执行
            plan = [step]
            emit("thinking", {"content": f"快路径: {intent_type}", "phase": "fast_path"})
            
            # 创建临时 Orchestrator 执行快路径
            temp_orchestrator = self._create_orchestrator(emit)
            return temp_orchestrator.executor.execute_plan(plan, user_instruction, context or {})
            
        except Exception as e:
            logger.warning(f"[SECURITY_SHIELD] 快路径执行失败: {e}，回退到正常规划")
            return None
    
    def _extract_app_name(self, instruction: str) -> Optional[str]:
        """
        从用户指令中提取应用名称（从 TaskOrchestrator 借用）
        
        Args:
            instruction: 用户指令
            
        Returns:
            提取的应用名称，如果无法提取则返回None
        """
        import re
        
        instruction = instruction.strip()
        open_keywords = ["打开", "启动", "运行", "开启", "open", "launch", "start", "run"]
        close_keywords = ["关闭", "退出", "结束", "停止", "close", "quit", "exit", "stop", "kill"]
        all_keywords = open_keywords + close_keywords
        
        pattern1 = r'(?:' + '|'.join(re.escape(kw) for kw in all_keywords) + r')\s+(.+)'
        match1 = re.search(pattern1, instruction, re.IGNORECASE)
        if match1:
            app_name = match1.group(1).strip()
            app_name = re.split(r'[然后并和,，]', app_name)[0].strip()
            if app_name:
                return app_name
        
        if len(instruction) < 50 and not any(kw in instruction for kw in ["然后", "并", "和", "再"]):
            return instruction.strip()
        
        return None
    
    def _parse_volume_params(self, instruction: str) -> Dict[str, Any]:
        """
        从用户指令中解析音量参数
        
        Args:
            instruction: 用户指令
            
        Returns:
            音量参数字典，包含 level 或 action
        """
        import re
        
        instruction_lower = instruction.lower()
        
        # 检查静音/取消静音
        if any(kw in instruction_lower for kw in ["静音", "mute", "关闭声音", "关声音"]):
            return {"action": "mute"}
        if any(kw in instruction_lower for kw in ["取消静音", "unmute", "打开声音", "开声音"]):
            return {"action": "unmute"}
        
        # 检查调大/调小
        if any(kw in instruction_lower for kw in ["调大", "增大", "增加", "up", "increase", "raise"]):
            return {"action": "up"}
        if any(kw in instruction_lower for kw in ["调小", "减小", "降低", "down", "decrease", "lower", "降低"]):
            return {"action": "down"}
        
        # 尝试提取具体数值（0-100）
        numbers = re.findall(r'\d+', instruction)
        if numbers:
            level = int(numbers[0])
            if 0 <= level <= 100:
                return {"level": level}
        
        # 默认调大
        return {"action": "up"}
    
    def _parse_brightness_params(self, instruction: str) -> Dict[str, Any]:
        """
        从用户指令中解析亮度参数
        
        Args:
            instruction: 用户指令
            
        Returns:
            亮度参数字典，包含 level 或 action
        """
        import re
        
        instruction_lower = instruction.lower()
        
        # 检查最亮/最暗
        if any(kw in instruction_lower for kw in ["最亮", "最亮", "max", "maximum", "brightest"]):
            return {"action": "max"}
        if any(kw in instruction_lower for kw in ["最暗", "最暗", "min", "minimum", "darkest"]):
            return {"action": "min"}
        
        # 检查调亮/调暗
        if any(kw in instruction_lower for kw in ["调亮", "调高", "增加", "up", "increase", "raise", "brighten"]):
            return {"action": "up"}
        if any(kw in instruction_lower for kw in ["调暗", "调低", "降低", "down", "decrease", "lower", "dim"]):
            return {"action": "down"}
        
        # 尝试提取百分比数值（0-100）
        percent_match = re.search(r'(\d+)%', instruction)
        if percent_match:
            percent = int(percent_match.group(1))
            if 0 <= percent <= 100:
                return {"level": percent / 100.0}
        
        # 尝试提取小数（0.0-1.0）
        float_match = re.search(r'(\d+\.?\d*)', instruction)
        if float_match:
            level = float(float_match.group(1))
            if 0.0 <= level <= 1.0:
                return {"level": level}
            elif 0 <= level <= 100:
                return {"level": level / 100.0}
        
        # 默认调亮
        return {"action": "up"}

    def execute(
        self, 
        user_instruction: str, 
        progress_callback: Optional[Callable] = None, 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        入口方法：转发给 Orchestrator
        
        改进：
        1. 线程安全的 emit 传递（使用 contextvars）
        2. 意图路由快路径（避免不必要的 LLM 调用）
        3. 完善的错误处理和资源清理
        4. 非阻塞等待嵌入模型就绪
        5. 事件流过滤和精简（UX 优化）
        
        Args:
            user_instruction: 用户指令
            progress_callback: 进度回调函数
            context: 上下文信息
            
        Returns:
            执行结果字典
        """
        # === 状态去重：记录最近发送的事件（用于去重检查）===
        _last_event_key: Optional[str] = None
        _last_event_data: Optional[Dict[str, Any]] = None
        
        # === 事件映射：将底层事件映射到前端友好的事件类型 ===
        def map_event_type(event_type: str) -> Optional[str]:
            """将底层事件类型映射到前端友好的事件类型"""
            event_mapping = {
                'thinking': 'thinking',
                'execution_started': 'executing',
                'step_started': 'executing',
                'step_completed': 'success',
                'step_failed': 'error',
                'plan_ready': 'thinking',  # 规划完成也算 thinking
                'sensitive_operation_detected': 'thinking',  # 敏感操作检测也算 thinking
                'error': 'error',
                # 🔴 CRITICAL: 用户输入相关事件必须透传，不被过滤
                'request_input': 'request_input',  # 用户输入请求（登录、验证码等）
                'waiting_for_input': 'waiting_for_input',  # 等待用户输入心跳
            }
            return event_mapping.get(event_type, None)
        
        # === 精简事件内容 ===
        def sanitize_event_data(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
            """精简事件数据，移除技术细节"""
            sanitized = {}
            
            # 🔴 CRITICAL: 用户输入相关事件必须完整透传，不进行精简
            if event_type in ['request_input', 'waiting_for_input']:
                # 完整透传用户输入请求数据，确保前端能正确显示
                return data
            
            if event_type == 'thinking':
                # thinking 事件：只保留 phase 和简洁摘要
                sanitized['phase'] = data.get('phase', 'unknown')
                content = data.get('content', '')
                # 提取简洁摘要（最多50字符）
                if len(content) > 50:
                    sanitized['summary'] = content[:47] + '...'
                else:
                    sanitized['summary'] = content
                # 移除原始 content 和其他技术细节
                
            elif event_type == 'executing':
                # executing 事件：只保留 description，移除原始 params
                step = data.get('step', {})
                if step:
                    # 有 step 对象，提取 description
                    sanitized['description'] = step.get('description', step.get('action', '执行中...'))
                else:
                    # 没有 step 对象（如 execution_started），使用通用描述
                    sanitized['description'] = '开始执行任务'
                
                # 添加 step_index 和 total_steps（如果存在）
                if 'step_index' in data:
                    sanitized['step_index'] = data['step_index']
                elif 'step_count' in data:
                    # execution_started 使用 step_count
                    sanitized['total_steps'] = data['step_count']
                if 'total_steps' in data:
                    sanitized['total_steps'] = data['total_steps']
                # 移除原始 step、action、params 等技术细节
                
            elif event_type == 'success':
                # success 事件：精简成功信息
                step = data.get('step', {})
                sanitized['description'] = step.get('description', step.get('action', '执行成功'))
                if 'step_index' in data:
                    sanitized['step_index'] = data['step_index']
                if 'total_steps' in data:
                    sanitized['total_steps'] = data['total_steps']
                # 移除原始 step、result 等技术细节
                
            elif event_type == 'error':
                # error 事件：保留错误信息，但精简堆栈
                sanitized['message'] = data.get('message', data.get('error', '执行失败'))
                step = data.get('step', {})
                if step:
                    sanitized['description'] = step.get('description', step.get('action', '执行失败'))
                if 'step_index' in data:
                    sanitized['step_index'] = data['step_index']
                if 'total_steps' in data:
                    sanitized['total_steps'] = data['total_steps']
                # 移除 traceback、原始 step 等技术细节
            
            return sanitized
        
        # === 构造过滤后的 emit 函数 ===
        def emit(event_type: str, data: Dict[str, Any]):
            """
            过滤和精简事件，只发送前端需要的核心事件
            
            功能：
            1. 事件类型白名单过滤
            2. 内容精简（移除技术细节）
            3. 状态去重（避免重复事件）
            4. 添加 step_index 和 total_steps（前端友好）
            """
            nonlocal _last_event_key, _last_event_data
            
            # 1. 映射事件类型
            mapped_type = map_event_type(event_type)
            if not mapped_type:
                # 不在白名单中的事件类型，直接丢弃
                logger.debug(f"[UX_FILTER] 丢弃事件类型: {event_type}")
                return
            
            # 2. 精简事件数据
            sanitized_data = sanitize_event_data(mapped_type, data)
            
            # 3. 状态去重：检查是否与上次事件相同
            # 构建去重键：基于事件类型、description 和 step_index
            description = sanitized_data.get('description', '')
            step_index = sanitized_data.get('step_index')
            event_key = f"{mapped_type}:{description}:{step_index}"
            
            # 如果与上次事件完全相同，则去重
            if event_key == _last_event_key:
                logger.debug(f"[UX_FILTER] 去重事件: {event_key}")
                return
            
            # 4. 记录本次事件
            _last_event_key = event_key
            _last_event_data = sanitized_data.copy()
            
            # 5. 构造最终事件
            event = {
                "type": mapped_type,
                "timestamp": time.time(),
                "data": sanitized_data
            }
            
            # 6. 发送到前端
            if progress_callback:
                try:
                    progress_callback(event)
                    # 🔴 CRITICAL: 对于关键事件（如 request_input），确保立即刷新
                    if mapped_type in ['request_input', 'waiting_for_input']:
                        import sys
                        sys.stdout.flush()  # 立即刷新 stdout，确保消息立即发送
                except Exception as e:
                    logger.error(f"[SECURITY_SHIELD] 进度回调失败: {e}")
            else:
                print(json.dumps(event, ensure_ascii=False), flush=True)
        
        # === 非阻塞等待嵌入模型就绪（最多等待3秒）===
        if not self.embedding_model.wait_until_ready(timeout=3.0):
            logger.warning("[SECURITY_SHIELD] 嵌入模型未就绪，可能影响意图路由，但继续执行")
        
        # === 尝试快路径（意图路由）===
        try:
            shortcut_result = self._try_intent_shortcut(user_instruction, emit, context)
            if shortcut_result:
                logger.info("[SECURITY_SHIELD] 快路径执行成功，跳过 LLM 规划")
                return shortcut_result
        except Exception as e:
            logger.warning(f"[SECURITY_SHIELD] 快路径失败: {e}，继续正常流程")
        
        # === 正常流程：创建 Orchestrator 并执行 ===
        orchestrator = None
        try:
            # 创建新的 Orchestrator（每次创建新实例，避免并发竞态）
            orchestrator = self._create_orchestrator(emit)
            
            if not orchestrator:
                return {
                    "success": False,
                    "message": "Orchestrator 创建失败",
                    "user_instruction": user_instruction
                }
            
            # 执行任务
            return orchestrator.run(user_instruction, emit, context)
            
        except KeyboardInterrupt:
            logger.warning("[SECURITY_SHIELD] 任务被用户中断")
            return {
                "success": False,
                "message": "任务被用户中断",
                "user_instruction": user_instruction
            }
        except Exception as e:
            # === 完善的错误处理：捕获堆栈并通知前端 ===
            error_traceback = traceback.format_exc()
            logger.error(f"[SECURITY_SHIELD] Agent 执行失败: {e}", exc_info=True)
            
            # 发送错误事件到前端
            try:
                emit("error", {
                    "message": str(e),
                    "traceback": error_traceback,
                    "user_instruction": user_instruction
                })
            except Exception:
                pass
            
            return {
                "success": False,
                "message": f"Critical Error: {str(e)}",
                "error_type": type(e).__name__,
                "traceback": error_traceback,
                "user_instruction": user_instruction
            }
        finally:
            # === 资源清理：确保浏览器驱动和文件句柄不会挂起 ===
            try:
                # 清理浏览器资源（如果存在）
                if hasattr(self, 'browser_executor') and self.browser_executor:
                    # 注意：不在这里关闭浏览器，因为可能还有其他任务在使用
                    # 只在真正需要时才关闭（由 BrowserExecutor 自己管理）
                    pass
                
                # 清理上下文变量
                _emit_context.set(None)
                
            except Exception as cleanup_error:
                logger.warning(f"[SECURITY_SHIELD] 资源清理失败: {cleanup_error}")
