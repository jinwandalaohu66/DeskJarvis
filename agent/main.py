"""
DeskJarvis Agent主入口 - 智能化重构版

核心特性：
1. AI 先输出思考过程和计划（类似 Cursor）
2. 步骤实时执行，完成即打勾
3. 失败时自动反思并重试
4. 所有过程对用户可见
5. 三层记忆系统：结构化、向量、高级记忆
6. 多代理协作：Planner, Executor, Reflector, Reviser, Summarizer

遵循 docs/ARCHITECTURE.md 中的架构设计
"""

import sys
import json
import logging
import time
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools.config import Config
from agent.tools.logger import setup_logger
from agent.planner.planner_factory import create_planner
from agent.executor.browser import BrowserExecutor
from agent.executor.file_manager import FileManager
from agent.executor.system_tools import SystemTools
from agent.memory import MemoryManager

# 多代理协作（可选）
try:
    from agent.crew import CrewManager
    CREW_AVAILABLE = True
except ImportError:
    CREW_AVAILABLE = False

logger = logging.getLogger(__name__)


class DeskJarvisAgent:
    """
    DeskJarvis Agent主类 - 智能化重构版
    
    核心设计：
    - AI 先思考，输出计划，用户可见
    - 步骤逐个执行，实时反馈
    - 失败时反思，调整方案
    """
    
    def __init__(self, config: Config, use_crew: bool = False):
        """
        初始化Agent
        
        Args:
            config: 配置对象
            use_crew: 是否使用多代理协作模式（默认关闭，因为太慢）
        """
        self.config = config
        # 暂时禁用多代理模式，单代理+反思循环已经足够好
        self.use_crew = False  # use_crew and CREW_AVAILABLE
        
        self.planner = create_planner(config)
        self.file_manager = FileManager(config)
        self.system_tools = SystemTools(config)
        self.max_reflection_attempts = 3
        self._emit_callback = None
        # BrowserExecutor 需要 emit_callback，在 execute 方法中设置
        self.browser_executor = None
        
        # ========== 方案1: 记忆系统懒加载 ==========
        # 不在 __init__ 中初始化，首次访问 self.memory 时才初始化
        # 快速通道（翻译/截图等）完全跳过记忆系统，节省 15-20s
        self._memory: Optional[MemoryManager] = None
        
        # 初始化多代理协作管理器（如果可用）
        self.crew_manager = None
        if self.use_crew:
            try:
                self.crew_manager = CrewManager(
                    config={
                        "ai_provider": config.provider,
                        "ai_model": config.model,
                        "api_key": config.api_key,
                    }
                )
                logger.info("多代理协作模式已启用")
            except Exception as e:
                logger.warning(f"多代理协作初始化失败，将使用单代理模式: {e}")
                self.use_crew = False
        
        mode = "多代理协作" if self.use_crew else "单代理"
        logger.info(f"DeskJarvis Agent已初始化，使用{config.provider}规划器，{mode}模式，记忆系统懒加载")
    
    @property
    def memory(self) -> MemoryManager:
        """
        懒加载记忆管理器。
        
        首次访问时才初始化（~0.1s SQLite + Chroma，嵌入模型在后台异步加载）。
        快速通道任务永远不会触发此属性。
        """
        if self._memory is None:
            logger.info("首次访问记忆系统，正在初始化...")
            start = time.time()
            self._memory = MemoryManager()
            logger.info("记忆系统初始化完成，耗时 %.1fs" % (time.time() - start))
        return self._memory
    
    def execute(
        self, 
        user_instruction: str, 
        progress_callback: Optional[Callable] = None, 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行用户指令
        
        核心流程：
        1. AI 思考 → 输出思考过程
        2. AI 规划 → 输出步骤列表
        3. 逐步执行 → 实时打勾
        4. 失败反思 → 调整重试
        """
        def emit(event_type: str, data: Dict[str, Any]):
            """发送事件到前端"""
            event = {
                "type": event_type,
                "timestamp": time.time(),
                "data": data
            }
            if progress_callback:
                progress_callback(event)
            else:
                # 输出到 stdout，Tauri 会捕获
                print(json.dumps(event, ensure_ascii=False), flush=True)
        
        # 保存 emit 回调并初始化 browser_executor
        self._emit_callback = emit
        if self.browser_executor is None:
            self.browser_executor = BrowserExecutor(self.config, emit_callback=emit)
        else:
            # 更新 emit 回调
            self.browser_executor.emit = emit
        
        # 更新 system_tools 的 emit 回调（用于代码解释器）
        self.system_tools.emit = emit
        if hasattr(self.system_tools, 'code_interpreter'):
            self.system_tools.code_interpreter.emit = emit
            self.browser_executor.user_input_manager.emit = emit
        
        try:
            logger.info(f"收到用户指令: {user_instruction}")
            
            # ========== 快速通道：简单任务跳过 LLM 规划 ==========
            # 翻译/总结/截图/打开应用等不需要完整规划流程
            fast_result = self._try_fast_path(user_instruction, context, emit)
            if fast_result is not None:
                logger.info("快速通道命中，跳过完整规划流程")
                return fast_result
            
            # ========== 阶段0: 获取记忆上下文 ==========
            memory_context = self.memory.get_context_for_instruction(user_instruction)
            if memory_context:
                logger.debug(f"注入记忆上下文: {memory_context[:200]}...")
            
            # 合并记忆上下文到 context
            if context is None:
                context = {}
            context["memory_context"] = memory_context
            
            # 检查是否有工作流建议
            workflow_suggestion = self.memory.get_workflow_suggestion(user_instruction)
            if workflow_suggestion:
                context["workflow_suggestion"] = workflow_suggestion
            
            # ========== 阶段1: AI 思考 ==========
            emit("thinking", {
                "content": "好的，我来帮你处理：" + user_instruction[:50] + ("..." if len(user_instruction) > 50 else ""),
                "phase": "analyzing"
            })
            
            # 判断任务复杂度
            task_complexity = "simple"
            if self.use_crew and CREW_AVAILABLE:
                from agent.crew import TaskComplexityAnalyzer
                task_complexity = TaskComplexityAnalyzer.analyze(user_instruction)
                logger.info(f"任务复杂度分析: {task_complexity}")
            else:
                task_complexity = "simple" if self._is_simple_task(user_instruction) else "normal"
            
            # ========== 决定使用哪种模式 ==========
            use_multi_agent = (
                self.use_crew 
                and self.crew_manager is not None 
                and task_complexity in ["normal", "complex"]
            )
            
            if use_multi_agent:
                emit("thinking", {
                    "content": "这是个复杂任务，我召集团队一起来处理...",
                    "phase": "multi_agent"
                })
            else:
                emit("thinking", {
                    "content": "让我想想怎么做...",
                    "phase": "planning"
                })
            
            is_simple = task_complexity == "simple"
            max_attempts = 1 if is_simple else self.max_reflection_attempts
            
            # ========== 阶段2: 执行 ==========
            start_time = time.time()
            
            if use_multi_agent:
                # 使用多代理协作模式
                result = self._execute_with_crew(
                    instruction=user_instruction,
                    context=context,
                    emit=emit
                )
                
                # 如果多代理模式要求回退，使用单代理
                if result.get("fallback"):
                    emit("thinking", {
                        "content": "团队模式遇到问题，我自己来处理...",
                        "phase": "fallback"
                    })
                    result = self._execute_with_reflection(
                        instruction=user_instruction,
                        context=context,
                        max_attempts=max_attempts,
                        emit=emit
                    )
            else:
                # 使用单代理模式
                result = self._execute_with_reflection(
                    instruction=user_instruction,
                    context=context,
                    max_attempts=max_attempts,
                    emit=emit
                )
            
            duration = time.time() - start_time
            
            # ========== 阶段3: 保存记忆 ==========
            try:
                # 提取涉及的文件
                files_involved = []
                for step_result in result.get("steps", []):
                    step = step_result.get("step", {})
                    params = step.get("params", {})
                    for key in ["path", "file_path", "save_path", "target_path"]:
                        if key in params:
                            files_involved.append(params[key])
                
                # 保存任务结果到记忆
                self.memory.save_task_result(
                    instruction=user_instruction,
                    steps=[sr.get("step", {}) for sr in result.get("steps", [])],
                    result=result,
                    success=result.get("success", False),
                    duration=duration,
                    files_involved=files_involved
                )
                
                # 添加文件记录
                for file_path in files_involved:
                    self.memory.add_file_record(
                        path=file_path,
                        operation="create" if result.get("success") else "failed"
                    )
                
                logger.debug("任务结果已保存到记忆系统")
            except Exception as mem_error:
                logger.warning(f"保存记忆失败: {mem_error}")
            
            return result
            
        except Exception as e:
            logger.error(f"执行失败: {e}", exc_info=True)
            emit("error", {"message": str(e)})
            return {
                "success": False,
                "message": f"执行失败: {e}",
                "steps": [],
                "user_instruction": user_instruction
            }
    
    # ========== 快速通道 ==========
    
    def _try_fast_path(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]],
        emit: Callable
    ) -> Optional[Dict[str, Any]]:
        """
        快速通道：对于明确的简单任务，跳过完整 LLM 规划，直接执行。
        
        翻译/总结 等文本处理：30秒 → 3秒
        截图/打开应用 等系统操作：15秒 → 1秒
        
        Returns:
            执行结果字典，如果不是快速通道任务则返回 None
        """
        # 1. 文本处理快速通道
        text_match = self._detect_text_fast_path(instruction)
        if text_match:
            action, text, target_lang = text_match
            action_names = {
                "translate": "翻译文本",
                "summarize": "总结文本",
                "polish": "润色文本",
                "expand": "扩写文本",
                "fix_grammar": "修正语法",
            }
            step = {
                "type": "text_process",
                "action": action_names.get(action, "处理文本"),
                "params": {"text": text, "action": action, "target_lang": target_lang},
                "description": action_names.get(action, "处理文本"),
            }
            return self._execute_fast_path(instruction, step, emit, "收到，直接处理文本...")
        
        # 2. 简单系统操作快速通道
        simple_step = self._detect_simple_fast_path(instruction, context)
        if simple_step:
            return self._execute_fast_path(instruction, simple_step, emit, "好的，马上执行...")
        
        return None
    
    def _execute_fast_path(
        self,
        instruction: str,
        step: Dict[str, Any],
        emit: Callable,
        thinking_msg: str,
    ) -> Dict[str, Any]:
        """执行快速通道的单步任务，发送完整的前端事件"""
        emit("thinking", {"content": thinking_msg, "phase": "fast_path"})
        emit("plan_ready", {
            "content": step.get("action", "执行任务"),
            "steps": [step],
            "step_count": 1,
        })
        emit("execution_started", {"step_count": 1, "attempt": 1})
        emit("step_started", {
            "step_index": 0,
            "total_steps": 1,
            "step": step,
            "action": step.get("action", ""),
        })
        
        result = self._execute_single_step(step)
        
        if result.get("success"):
            emit("step_completed", {
                "step_index": 0,
                "total_steps": 1,
                "step": step,
                "result": result,
                "status": "success",
            })
            emit("task_completed", {
                "success": True,
                "message": "任务完成",
                "success_count": 1,
                "total_count": 1,
            })
        else:
            emit("step_failed", {
                "step_index": 0,
                "total_steps": 1,
                "step": step,
                "result": result,
                "error": result.get("message", ""),
                "status": "failed",
            })
            emit("task_completed", {
                "success": False,
                "message": result.get("message", "执行失败"),
                "success_count": 0,
                "total_count": 1,
            })
        
        step_result = {"step": step, "result": result}
        
        # ⚠️ 快速通道任务完全跳过记忆保存，保持"快速"特性
        # 原因：
        # 1. 快速通道任务（翻译/截图等）通常是简单、重复的操作，不需要记忆
        # 2. 记忆保存（特别是向量嵌入）会显著拖慢速度（10-30秒）
        # 3. 如果用户需要记忆，应该走完整的规划流程
        # 如果未来需要为快速通道任务保存记忆，应该使用异步方式，不阻塞返回
        
        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "steps": [step_result],
            "user_instruction": instruction,
            "attempts": 1,
            "fast_path": True,
        }
    
    def _detect_text_fast_path(self, instruction: str):
        """
        检测是否为纯文本处理任务（翻译/总结/润色/扩写/语法修正）。
        
        Returns:
            (action, text, target_lang) 或 None
        """
        # 排除涉及文件操作的指令
        file_keywords = ["文件", "文档", "Word", "word", "docx", "xlsx",
                         "pdf", "图片", "照片", "桌面上的"]
        for kw in file_keywords:
            if kw in instruction:
                return None
        
        # 文本处理关键词映射
        action_keywords = [
            ("translate", ["翻译"]),
            ("summarize", ["总结", "概括", "摘要"]),
            ("polish", ["润色"]),
            ("expand", ["扩写"]),
            ("fix_grammar", ["修正语法", "纠正语法", "语法修正", "修改语法"]),
        ]
        
        for action, keywords in action_keywords:
            for kw in keywords:
                if kw in instruction:
                    text = self._extract_text_for_processing(instruction, kw)
                    if text and len(text) >= 2:
                        target_lang = "英文"
                        if action == "translate":
                            target_lang = self._detect_target_lang(instruction)
                        return (action, text, target_lang)
        
        return None
    
    def _extract_text_for_processing(self, instruction: str, keyword: str) -> str:
        """从指令中提取要处理的文本"""
        import re
        
        # 移除常见前缀
        text = instruction
        for prefix in ["帮我", "请帮我", "请", "麻烦"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        
        # 找到关键词位置
        idx = text.find(keyword)
        if idx == -1:
            return ""
        
        after = text[idx + len(keyword):].strip()
        
        # 移除常见中缀词（"一下"、"以下内容"、"成英文"、分隔符等）
        remove_patterns = [
            r'^一下[：:]*\s*',
            r'^下[：:]*\s*',
            r'^以下内容[：:]*\s*',
            r'^以下[：:]*\s*',
            r'^这段话[：:]*\s*',
            r'^这段文字[：:]*\s*',
            r'^这段[：:]*\s*',
            r'^成[^\s：:]{1,6}[：:]*\s*',
            r'^为[^\s：:]{1,6}[：:]*\s*',
            r'^到[^\s：:]{1,6}[：:]*\s*',
            r'^[：:；;\s]+',
        ]
        for pattern in remove_patterns:
            after = re.sub(pattern, '', after, count=1)
        
        return after.strip()
    
    def _detect_target_lang(self, instruction: str) -> str:
        """检测翻译目标语言"""
        lang_keywords = {
            "英文": ["英文", "英语", "english"],
            "中文": ["中文", "汉语", "chinese"],
            "日文": ["日文", "日语", "japanese"],
            "韩文": ["韩文", "韩语", "korean"],
            "法文": ["法文", "法语", "french"],
            "德文": ["德文", "德语", "german"],
            "西班牙文": ["西班牙文", "西班牙语"],
        }
        inst_lower = instruction.lower()
        for lang, kws in lang_keywords.items():
            for kw in kws:
                if kw in inst_lower:
                    return lang
        
        # 智能检测：中文多则翻译成英文，否则翻译成中文
        chinese_count = sum(1 for c in instruction if '\u4e00' <= c <= '\u9fff')
        if chinese_count > len(instruction) * 0.3:
            return "英文"
        return "中文"
    
    def _detect_simple_fast_path(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        检测是否为简单的单步系统操作。
        
        Returns:
            构造好的 step 字典，或 None
        """
        import re
        inst = instruction.strip()
        
        # --- 截图桌面 ---
        if any(kw in inst for kw in ["截图桌面", "桌面截图", "截屏", "截个图"]):
            params: Dict[str, Any] = {}
            if "保存" in inst and "桌面" in inst:
                params["save_path"] = "~/Desktop/screenshot.png"
            return {
                "type": "screenshot_desktop",
                "action": "截图桌面",
                "params": params,
                "description": "截取桌面截图",
            }
        
        # --- 打开应用 ---
        match = re.match(r'^(?:帮我)?(?:请)?打开\s*(.+)$', inst)
        if match:
            target = match.group(1).strip()
            # 排除复杂指令（"打开浏览器然后xxx"）
            if any(kw in target for kw in ["然后", "并且", "接着", "之后"]):
                return None
            # 判断是路径还是应用名
            if '/' in target or target.startswith('~'):
                dot_in_last = '.' in target.split('/')[-1]
                if dot_in_last:
                    return {
                        "type": "open_file",
                        "action": "打开 " + target,
                        "params": {"file_path": target},
                        "description": "打开文件 " + target,
                    }
                return {
                    "type": "open_folder",
                    "action": "打开 " + target,
                    "params": {"folder_path": target},
                    "description": "打开文件夹 " + target,
                }
            return {
                "type": "open_app",
                "action": "打开 " + target,
                "params": {"app_name": target},
                "description": "打开应用 " + target,
            }
        
        # --- 关闭应用 ---
        match = re.match(r'^(?:帮我)?(?:请)?关闭\s*(.+)$', inst)
        if match:
            target = match.group(1).strip()
            if not any(kw in target for kw in ["然后", "并且", "接着"]):
                return {
                    "type": "close_app",
                    "action": "关闭 " + target,
                    "params": {"app_name": target},
                    "description": "关闭应用 " + target,
                }
        
        # --- 音量控制 ---
        if any(kw in inst for kw in ["音量", "声音", "静音"]):
            params_vol: Dict[str, Any] = {}
            if "静音" in inst and "取消" not in inst:
                params_vol["action"] = "mute"
            elif "取消静音" in inst:
                params_vol["action"] = "unmute"
            elif any(kw in inst for kw in ["调大", "大点", "大一点", "增大"]):
                params_vol["action"] = "up"
            elif any(kw in inst for kw in ["调小", "小点", "小一点", "减小"]):
                params_vol["action"] = "down"
            else:
                nums = re.findall(r'\d+', inst)
                if nums:
                    params_vol["level"] = int(nums[0])
                else:
                    return None  # 无法确定操作，走正常流程
            return {
                "type": "set_volume",
                "action": "调整音量",
                "params": params_vol,
                "description": "调整系统音量",
            }
        
        # --- 亮度控制 ---
        if any(kw in inst for kw in ["亮度", "屏幕亮度"]):
            params_br: Dict[str, Any] = {}
            if any(kw in inst for kw in ["最亮", "最大"]):
                params_br["action"] = "max"
            elif any(kw in inst for kw in ["最暗", "最小"]):
                params_br["action"] = "min"
            elif any(kw in inst for kw in ["调大", "亮一点", "亮点"]):
                params_br["action"] = "up"
            elif any(kw in inst for kw in ["调小", "暗一点", "暗点"]):
                params_br["action"] = "down"
            else:
                nums = re.findall(r'[\d.]+', inst)
                if nums:
                    level = float(nums[0])
                    if level > 1:
                        level = level / 100
                    params_br["level"] = level
                else:
                    return None
            return {
                "type": "set_brightness",
                "action": "调整亮度",
                "params": params_br,
                "description": "调整屏幕亮度",
            }
        
        # --- 系统信息 ---
        if any(kw in inst for kw in ["系统信息", "查看系统", "电池状态", "磁盘空间", "内存使用"]):
            info_type = "all"
            if "电池" in inst:
                info_type = "battery"
            elif "磁盘" in inst:
                info_type = "disk"
            elif "内存" in inst:
                info_type = "memory"
            params_info: Dict[str, Any] = {"info_type": info_type}
            if "保存" in inst:
                params_info["save_path"] = "~/Desktop/系统报告.md"
            return {
                "type": "get_system_info",
                "action": "获取系统信息",
                "params": params_info,
                "description": "获取系统信息",
            }
        
        return None
    
    # ========== 任务复杂度判断 ==========
    
    def _is_simple_task(self, instruction: str) -> bool:
        """判断是否为简单任务"""
        instruction_lower = instruction.lower()
        
        # 简单任务：单一操作
        simple_patterns = ["截图", "screenshot", "打开", "open", "关闭", "close",
                           "翻译", "总结", "润色", "音量", "亮度", "系统信息"]
        
        # 复杂任务：多步骤
        complex_patterns = ["下载", "download", "整理", "批量", "重命名", "并且", "然后"]
        
        for pattern in complex_patterns:
            if pattern in instruction_lower:
                return False
        
        for pattern in simple_patterns:
            if pattern in instruction_lower:
                return True
        
        return False  # 默认按复杂任务处理
    
    def _execute_with_crew(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]],
        emit: Callable
    ) -> Dict[str, Any]:
        """
        使用多代理协作执行任务
        
        流程：
        1. Planner Agent 分析任务，制定计划
        2. Executor Agent 执行任务
        3. 如果失败，Reflector Agent 分析原因
        4. Reviser Agent 修正方案
        5. Summarizer Agent 总结结果
        """
        if not self.crew_manager:
            return {"fallback": True, "success": False, "message": "多代理管理器不可用"}
        
        try:
            # 更新 crew_manager 的 emit 回调
            self.crew_manager.emit = emit
            self.crew_manager.tools.emit = emit
            
            # 执行多代理协作
            result = self.crew_manager.execute(
                instruction=instruction,
                context=context
            )
            
            # 如果返回 fallback，让调用者处理
            if result.get("fallback"):
                return result
            
            # 转换结果格式以兼容现有逻辑
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "steps": [],  # 多代理模式不返回详细步骤
                "user_instruction": instruction,
                "mode": "multi-agent",
                "duration": result.get("duration", 0)
            }
            
        except Exception as e:
            logger.error(f"多代理执行失败: {e}", exc_info=True)
            # 请求回退到单代理模式
            return {
                "fallback": True,
                "success": False,
                "message": f"多代理执行失败: {e}"
            }
    
    def _execute_with_reflection(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]],
        max_attempts: int,
        emit: Callable
    ) -> Dict[str, Any]:
        """
        带反思循环的执行
        
        流程：
        1. 规划 → 输出步骤
        2. 执行 → 实时打勾
        3. 如果失败 → 反思 → 重新规划 → 重新执行
        """
        last_error = None
        last_plan = None
        all_step_results = []
        
        for attempt in range(max_attempts):
            try:
                # ========== 规划阶段 ==========
                if attempt == 0:
                    # 调用 AI 规划
                    steps = self.planner.plan(instruction, context=context)
                    
                else:
                    # 反思模式
                    emit("thinking", {
                        "content": "刚才的方法没成功，让我换个方式试试...",
                        "phase": "reflecting"
                    })
                    
                    emit("reflection_started", {
                        "attempt": attempt + 1,
                        "previous_error": last_error
                    })
                    
                    # 调用 AI 反思
                    reflection = self.planner.reflect(
                        instruction=instruction,
                        last_plan=last_plan,
                        error=last_error,
                        context=context
                    )
                    
                    analysis = reflection.get("analysis", "")
                    steps = reflection.get("new_plan", [])
                    
                    emit("thinking", {
                        "content": "我知道问题在哪了：" + analysis[:100] + ("..." if len(analysis) > 100 else "") + "\n换个方法试试...",
                        "phase": "re_planning"
                    })
                    
                    emit("reflection_completed", {
                        "analysis": analysis,
                        "new_step_count": len(steps)
                    })
                
                if not steps:
                    emit("error", {"message": "规划失败：没有生成任何步骤"})
                    return {
                        "success": False,
                        "message": "规划失败：没有生成任何步骤",
                        "steps": [],
                        "user_instruction": instruction
                    }
                
                last_plan = steps
                
                # ========== 输出计划 ==========
                # 告诉用户我打算怎么做
                plan_description = self._format_plan_for_user(steps)
                emit("plan_ready", {
                    "content": plan_description,
                    "steps": steps,
                    "step_count": len(steps)
                })
                
                # ========== 执行阶段 ==========
                emit("execution_started", {
                    "step_count": len(steps),
                    "attempt": attempt + 1
                })
                
                step_results = self._execute_steps(steps, emit)
                all_step_results = step_results
                
                # ========== 检查结果 ==========
                success_count = sum(1 for r in step_results if r["result"].get("success"))
                total_count = len(step_results)
                all_success = success_count == total_count
                
                if all_success:
                    # 全部成功
                    emit("task_completed", {
                        "success": True,
                        "message": f"任务完成！{success_count}/{total_count} 个步骤成功",
                        "success_count": success_count,
                        "total_count": total_count
                    })
                    
                    return {
                        "success": True,
                        "message": f"任务完成：{success_count}/{total_count} 个步骤成功",
                        "steps": step_results,
                        "user_instruction": instruction,
                        "attempts": attempt + 1
                    }
                else:
                    # 有失败的步骤
                    failed_steps = [r for r in step_results if not r["result"].get("success")]
                    # 反思必须拿到“真实错误细节”（例如 ruff 输出、Traceback），
                    # 仅使用 message 会丢失关键上下文，导致反思空转。
                    formatted_errors = []
                    for r in failed_steps:
                        step_action = r["step"].get("action", "") or r["step"].get("type", "")
                        msg = r["result"].get("message", "未知错误")
                        detail = r["result"].get("error", "")
                        if detail and detail != msg:
                            # 控制长度，避免 prompt 过长
                            formatted_errors.append(
                                "步骤 '" + str(step_action) + "' 失败: " + str(msg) + "\n"
                                + "错误详情:\n"
                                + str(detail)[:2000]
                            )
                        else:
                            formatted_errors.append("步骤 '" + str(step_action) + "' 失败: " + str(msg))

                    last_error = "\n\n".join(formatted_errors)
                    
                    if attempt < max_attempts - 1:
                        emit("thinking", {
                            "content": "这个方法不太对，让我想想别的办法...",
                            "phase": "preparing_reflection"
                        })
                    else:
                        # 最后一次尝试
                        emit("task_completed", {
                            "success": False,
                            "message": f"任务部分完成：{success_count}/{total_count} 个步骤成功（已尝试 {attempt + 1} 次）",
                            "success_count": success_count,
                            "total_count": total_count,
                            "last_error": last_error
                        })
                        
                        return {
                            "success": False,
                            "message": f"任务部分完成：{success_count}/{total_count} 个步骤成功",
                            "steps": step_results,
                            "user_instruction": instruction,
                            "attempts": attempt + 1,
                            "last_error": last_error
                        }
                        
            except Exception as e:
                last_error = str(e)
                logger.error(f"尝试 {attempt + 1} 出错: {e}", exc_info=True)
                
                if attempt < max_attempts - 1:
                    # 发送错误事件，让用户知道发生了什么
                    emit("step_failed", {
                        "step_index": 0,
                        "total_steps": 1,
                        "step": {"type": "planning", "action": "规划任务"},
                        "error": str(e)[:200],
                        "result": {"success": False, "message": str(e)[:200]}
                    })
                    emit("thinking", {
                        "content": "遇到点问题，让我换个方法试试...",
                        "phase": "error_recovery"
                    })
                else:
                    emit("task_completed", {
                        "success": False,
                        "message": f"任务失败：{e}",
                        "error": str(e)
                    })
                    
                    return {
                        "success": False,
                        "message": f"任务失败（已尝试 {attempt + 1} 次）: {e}",
                        "steps": all_step_results,
                        "user_instruction": instruction,
                        "attempts": attempt + 1,
                        "last_error": str(e)
                    }
        
        # 不应该到这里
        return {
            "success": False,
            "message": "未知错误",
            "steps": [],
            "user_instruction": instruction
        }
    
    def _format_plan_for_user(self, steps: List[Dict[str, Any]]) -> str:
        """格式化计划，让用户看到我要做什么"""
        if len(steps) == 1:
            action = steps[0].get("action", steps[0].get("description", "处理任务"))
            return f"我来{action}..."
        else:
            lines = ["我打算这样做：\n"]
            for i, step in enumerate(steps, 1):
                action = step.get("action", step.get("type", "操作"))
                lines.append(f"{i}. {action}")
            lines.append("\n现在开始...")
            return "\n".join(lines)
    
    def _execute_steps(
        self, 
        steps: List[Dict[str, Any]], 
        emit: Callable
    ) -> List[Dict[str, Any]]:
        """
        执行步骤列表，每完成一步就发送事件
        """
        results = []
        browser_started = False
        
        # 检查是否需要浏览器
        browser_needed = any(
            step.get("type", "").startswith("browser_") or step.get("type") == "download_file"
            for step in steps
        )
        
        if browser_needed:
            emit("thinking", {"content": "我需要用浏览器来完成这个任务...", "phase": "browser_init"})
            self.browser_executor.start()
            browser_started = True
        
        try:
            for i, step in enumerate(steps):
                step_type = step.get("type", "")
                step_action = step.get("action", step_type)
                
                # 发送步骤开始事件
                emit("step_started", {
                    "step_index": i,
                    "total_steps": len(steps),
                    "step": step,
                    "action": step_action
                })
                
                # 执行步骤
                result = self._execute_single_step(step)
                
                results.append({
                    "step": step,
                    "result": result
                })
                
                # 发送步骤完成事件
                if result.get("success"):
                    emit("step_completed", {
                        "step_index": i,
                        "total_steps": len(steps),
                        "step": step,
                        "result": result,
                        "status": "success"
                    })
                else:
                    # 步骤失败，发送事件并立即中断
                    emit("step_failed", {
                        "step_index": i,
                        "total_steps": len(steps),
                        "step": step,
                        "result": result,
                        "error": result.get("message", "未知错误"),
                        "status": "failed"
                    })
                    # 中断执行，不再继续后续步骤，让反思循环处理
                    logger.info(f"步骤 {i+1} 失败，中断执行，等待反思循环")
                    break
                    
        finally:
            if browser_started:
                emit("thinking", {"content": "浏览器用完了，收拾一下...", "phase": "browser_cleanup"})
                self.browser_executor.stop()
        
        return results
    
    def _execute_single_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个步骤"""
        step_type = step.get("type", "")
        
        try:
            if step_type.startswith("browser_"):
                return self.browser_executor.execute_step(step)
            elif step_type == "download_file":
                return self.browser_executor.execute_step(step)
            elif step_type in ["request_login", "request_captcha", "fill_login", "fill_captcha"]:
                # 登录和验证码相关的步骤，路由到 browser_executor
                return self.browser_executor.execute_step(step)
            elif step_type.startswith("file_"):
                return self.file_manager.execute_step(step)
            elif step_type in ["screenshot_desktop", "open_folder", "open_file", 
                              "open_app", "close_app", "execute_python_script",
                              # 新增系统控制工具
                              "set_volume", "set_brightness", "send_notification",
                              "clipboard_read", "clipboard_write", "speak",
                              "keyboard_type", "keyboard_shortcut",
                              "mouse_click", "mouse_move",
                              "window_minimize", "window_maximize", "window_close",
                              "get_system_info", "image_process",
                              "download_latest_python_installer",
                              "set_reminder", "list_reminders", "cancel_reminder",
                              "create_workflow", "list_workflows", "delete_workflow",
                              "get_task_history", "search_history",
                              "add_favorite", "list_favorites", "remove_favorite",
                              "text_process"]:
                return self.system_tools.execute_step(step)
            else:
                return {
                    "success": False,
                    "message": f"未知的步骤类型: {step_type}",
                    "data": None
                }
        except Exception as e:
            logger.error(f"执行步骤失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"执行失败: {e}",
                "data": None
            }


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DeskJarvis Agent")
    parser.add_argument("instruction", nargs="?", help="用户指令")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--json", action="store_true", help="JSON输出模式")
    parser.add_argument("--context", help="上下文JSON")
    
    args = parser.parse_args()
    
    if args.json:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    else:
        setup_logger(log_level=args.log_level)
    
    try:
        config = Config(config_path=args.config)
        
        if not config.validate():
            error = {"success": False, "message": "配置无效", "steps": [], "user_instruction": ""}
            print(json.dumps(error, ensure_ascii=False))
            sys.exit(1)
        
        context = None
        if args.context:
            try:
                context = json.loads(args.context)
            except Exception:
                pass
        
        agent = DeskJarvisAgent(config)
        
        if args.instruction:
            result = agent.execute(args.instruction, context=context)
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if args.json:
                print(json.dumps({"success": False, "message": "需要提供指令", "steps": []}, ensure_ascii=False))
                sys.exit(1)
            print("请提供指令")
            
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "message": str(e), "steps": []}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
