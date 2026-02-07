"""
Plan Executor - Agent Execution Engine

功能：
- 接收一个 Plan（步骤列表）并逐个执行
- 管理执行上下文 (Context)
- 处理反思逻辑 (Reflection)
- 向前端发送实时事件 (Emit)
"""

import time
import logging
from typing import Dict, Any, List, Callable, Optional

from agent.tools.exceptions import PlaceholderError
from agent.tools.log_sanitizer import LogSanitizer

logger = logging.getLogger(__name__)

class PlanExecutor:
    """
    负责执行规划好的步骤列表，并处理单步重试与反思。
    """
    
    def __init__(self, config, tools_map: Dict[str, Any], emit_callback: Callable):
        """
        Args:
            config: 配置对象
            tools_map: 工具映射 {executor_name: instance}
            emit_callback: 事件发送回调函数
        """
        self.config = config
        self.tools = tools_map
        self.emit = emit_callback
        self.reflector = None
        
        # === 执行器注册机制（替代硬编码列表）===
        self.executor_registry: Dict[str, str] = {}
        self._register_executors()
        
    def execute_plan(
        self, 
        plan: List[Dict[str, Any]], 
        user_instruction: str, 
        context: Dict[str, Any],
        max_attempts: int = 3
    ) -> Dict[str, Any]:
        """
        执行完整计划
        """
        step_results = []
        overall_success = True
        failed_reason = ""
        
        # Orchestrator 已经刷新了配置，所以这里只需要重置 Reflector
        # 确保在每波计划执行开始时，反思器重新加载最新配置
        self.reflector = None
        
        self.emit("execution_started", {
            "step_count": len(plan),
            "attempt": 1
        })
        
        # 初始化 step_results 用于占位符替换
        if "step_results" not in context:
            context["step_results"] = []
        
        for i, step in enumerate(plan):
            # 检查停止标志（支持两种方式：直接标志或检查函数）
            check_stop = context.get("_check_stop")
            if check_stop and callable(check_stop):
                if check_stop():
                    logger.info("检测到停止标志（通过检查函数），终止执行")
                    break
            elif context.get("_stop_execution", False):
                logger.info("检测到停止标志（直接标志），终止执行")
                break
                
            self.emit("step_started", {
                "step_index": i,
                "total_steps": len(plan),
                "step": step,
                "action": step.get("action", "")
            })
            
            # 执行单步（包含重试逻辑）
            step_result = self._execute_step_with_retry(step, i, max_attempts, context)
            
            step_result_record = {
                "step": step,
                "result": step_result
            }
            step_results.append(step_result_record)
            # 更新 context 中的 step_results 供占位符替换使用
            context["step_results"] = step_results
            
            if step_result.get("success"):
                self.emit("step_completed", {
                    "step_index": i,
                    "total_steps": len(plan),
                    "step": step,
                    "result": step_result,
                    "status": "success"
                })
            else:
                overall_success = False
                failed_reason = step_result.get("message", "Unknown error")
                self.emit("step_failed", {
                    "step_index": i,
                    "total_steps": len(plan),
                    "step": step,
                    "result": step_result,
                    "error": failed_reason,
                    "status": "failed"
                })
                break
                
        return {
            "success": overall_success,
            "message": "执行完成" if overall_success else f"执行失败: {failed_reason}",
            "steps": step_results,
            "user_instruction": user_instruction
        }
    
    def _register_executors(self):
        """
        注册执行器路由规则（替代硬编码列表）
        
        格式：{step_type: executor_name}
        """
        # 文件操作
        file_ops = [
            "file_create", "file_read", "file_write", "file_delete",
            "file_rename", "file_move", "file_copy", "file_organize",
            "file_classify", "file_batch_rename", "file_batch_copy",
            "file_batch_organize", "create_file", "read_file", 
            "list_dir", "delete_file"
        ]
        for op in file_ops:
            self.executor_registry[op] = "file_manager"
        
        # 浏览器操作
        browser_ops = [
            "browser_navigate", "browser_click", "browser_fill", "browser_wait",
            "browser_screenshot", "browser_check_element", "download_file",
            "request_login", "request_captcha", "request_qr_login",
            "open_url", "click", "type", "scroll", "scrape", "screenshot_web"
        ]
        for op in browser_ops:
            self.executor_registry[op] = "browser_executor"
        
        # 系统操作
        system_ops = [
            "screenshot_desktop", "open_app", "close_app", "set_volume", 
            "set_brightness", "get_system_info", "open_folder", "open_file", 
            "text_process", "python_script", "python", "code_interpreter"
        ]
        for op in system_ops:
            self.executor_registry[op] = "system_tools"
        
        # 邮件操作
        email_ops = [
            "send_email", "search_emails", "get_email_details", 
            "download_attachments", "manage_emails", "compress_files"
        ]
        for op in email_ops:
            self.executor_registry[op] = "email_executor"
        
        logger.debug(f"[SECURITY_SHIELD] 执行器注册完成，共 {len(self.executor_registry)} 个路由规则")

    def _execute_step_with_retry(self, step: Dict[str, Any], step_index: int, max_attempts: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行单步，带重试机制"""
        # 初始化 Reflector (延迟加载)
        if self.reflector is None:
            from agent.orchestrator.reflector import Reflector
            self.reflector = Reflector(self.config)

        current_step = step
        last_result = {"success": False, "message": "None"}

        for attempt in range(1, max_attempts + 1):
            try:
                # 在执行前检查停止标志
                check_stop = context.get("_check_stop")
                if check_stop and callable(check_stop) and check_stop():
                    logger.info(f"步骤 {step_index} 在执行前已被停止")
                    return {"success": False, "message": "任务已取消"}
                
                # === 敏感操作确认：检查步骤是否标记为 [SENSITIVE] ===
                step_description = current_step.get("description", "")
                if step_description.startswith("[SENSITIVE]"):
                    logger.warning(f"[SECURITY_SHIELD] 步骤 {step_index} 标记为敏感操作，需要用户确认")
                    
                    # 通过 emit 发送确认请求
                    self.emit("sensitive_operation_detected", {
                        "step_index": step_index,
                        "step": current_step,
                        "description": step_description,
                        "message": f"检测到敏感操作：{step_description}\n\n此操作可能具有破坏性，是否继续执行？"
                    })
                    
                    # 等待用户确认（通过 context 中的确认标志）
                    # 注意：这里需要前端配合，通过 context 设置确认结果
                    confirmation_key = f"_sensitive_confirmation_{step_index}"
                    if confirmation_key not in context:
                        # 如果没有确认结果，等待用户响应（最多等待30秒）
                        import time
                        wait_start = time.time()
                        while confirmation_key not in context and (time.time() - wait_start) < 30:
                            time.sleep(0.5)
                            check_stop = context.get("_check_stop")
                            if check_stop and callable(check_stop) and check_stop():
                                return {"success": False, "message": "任务已取消"}
                        
                        if confirmation_key not in context:
                            logger.error(f"[SECURITY_SHIELD] 用户未在30秒内确认敏感操作，取消执行")
                            return {"success": False, "message": "用户未确认敏感操作，执行已取消"}
                    
                    # 检查确认结果
                    confirmed = context.get(confirmation_key, False)
                    if not confirmed:
                        logger.warning(f"[SECURITY_SHIELD] 用户拒绝了敏感操作")
                        return {"success": False, "message": "用户拒绝了敏感操作，执行已取消"}
                    else:
                        logger.info(f"[SECURITY_SHIELD] 用户已确认敏感操作，继续执行")
                
                step_type = current_step.get("type", "")
                executor = self._get_executor_for_step(step_type)
                
                if not executor:
                    return {"success": False, "message": f"未找到执行器: {step_type}"}

                # 核心调度执行
                result = self._dispatch_execution(executor, current_step, context)
                last_result = result
                
                # 执行后检查停止标志
                if check_stop and callable(check_stop) and check_stop():
                    logger.info(f"步骤 {step_index} 在执行后检测到停止标志")
                    return {"success": False, "message": "任务已取消"}
                
                if result.get("success"):
                    return result
                    
                error_msg = result.get('message', 'Unknown Error')
                error_data = result.get('data') or {}  # 处理 data 为 None 的情况
                
                # 检查是否为配置错误（不可恢复，需要用户操作）
                # 增加空值保护，防止 'NoneType' object has no attribute 'get' 错误
                is_config_error = error_data.get('is_config_error', False) if error_data else False
                requires_action = error_data.get('requires_user_action', False) if error_data else False
                is_config_error = is_config_error or requires_action
                
                if is_config_error:
                    logger.warning(f"步骤 {step_index} 失败：配置错误（不可恢复，需要用户操作）")
                    logger.info(f"错误详情: {error_msg}")
                    # 配置错误不需要重试，直接返回
                    return result
                
                logger.warning(f"步骤 {step_index} 失败 (尝试 {attempt}/{max_attempts}): {error_msg}")
                
                if attempt < max_attempts:
                    self.emit("thinking", {"content": "步骤异常，正在分析修复方案...", "phase": "reflection"})
                    reflection = self.reflector.analyze_failure(current_step, error_msg, str(current_step.get("params", {})))
                    
                    if reflection.is_retryable and reflection.modified_step:
                        logger.info(f"Reflector 建议修复: {reflection.reason}")
                        current_step = reflection.modified_step
                        self.emit("thinking", {"content": f"应用修复: {reflection.reason}", "phase": "reflection_applied"})
                    else:
                        logger.info(f"Reflector 判断为不可恢复错误: {reflection.reason}")
                        time.sleep(1)
                else:
                    return result
                    
            except PlaceholderError as e:
                # === 占位符错误：强制触发 Reflector 重新分析 ===
                logger.error(f"[SECURITY_SHIELD] 步骤 {step_index} 占位符错误: {e.placeholder}")
                logger.info(f"[SECURITY_SHIELD] 触发 Reflector 重新分析上下文以修复占位符")
                
                # 构造占位符错误的上下文信息
                placeholder_context = f"占位符替换失败: {e.placeholder}。请检查上一步的执行结果，确保返回了正确的数据。"
                
                # 强制触发 Reflector 分析
                if self.reflector is None:
                    from agent.orchestrator.reflector import Reflector
                    self.reflector = Reflector(self.config)
                
                self.emit("thinking", {"content": "占位符替换失败，正在重新分析上下文...", "phase": "placeholder_reflection"})
                reflection = self.reflector.analyze_failure(
                    current_step, 
                    str(e), 
                    placeholder_context
                )
                
                if reflection.is_retryable and reflection.modified_step:
                    logger.info(f"[SECURITY_SHIELD] Reflector 建议修复占位符问题: {reflection.reason}")
                    current_step = reflection.modified_step
                    self.emit("thinking", {"content": f"应用修复: {reflection.reason}", "phase": "placeholder_fix_applied"})
                    # 继续重试
                    if attempt < max_attempts:
                        continue
                else:
                    logger.error(f"[SECURITY_SHIELD] Reflector 无法修复占位符问题: {reflection.reason}")
                    return {"success": False, "message": f"占位符错误无法修复: {e.placeholder}"}
            except Exception as e:
                logger.error(f"步骤 {step_index} 严重异常: {e}", exc_info=True)
                if attempt == max_attempts:
                    return {"success": False, "message": f"Runtime Error: {str(e)}"}
        
        return last_result

    def _get_executor_for_step(self, step_type: str) -> Any:
        """
        根据步骤类型获取执行器实例（使用注册机制）
        
        Args:
            step_type: 步骤类型
            
        Returns:
            执行器实例，如果未找到返回 None
        """
        # 1. 优先使用注册表查找
        executor_name = self.executor_registry.get(step_type)
        if executor_name:
            executor = self.tools.get(executor_name)
            if executor:
                return executor
        
        # 2. 兼容错误的类型名称（由 Reflector 错误生成）
        file_related_error_types = ["file_manager", "FileManager", "file_operation"]
        if step_type in file_related_error_types:
            return self.tools.get("file_manager")
        
        # 3. 默认返回 system_tools
        logger.warning(f"[SECURITY_SHIELD] 未注册的步骤类型: {step_type}，使用默认执行器 (system_tools)")
        return self.tools.get("system_tools")

    def _replace_placeholders(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        替换占位符，如 {{step1.id}} 或 {{step1.result[0].id}}
        支持复杂路径和索引语法：
        - 支持 stepN.field 格式
        - 支持 stepN.field[index] 格式
        - 支持 stepN.field1.field2[index].field3 等嵌套路径
        如果路径中任何一级不存在，返回 None（会被拦截逻辑识别为 NULL_ID）
        """
        import re
        
        def get_deep_value(obj: Any, path: str) -> Any:
            """
            根据路径获取深层值，支持索引语法
            例如：result[0].id 或 data.emails[1].subject
            """
            if obj is None:
                return None
            
            parts = path.split('.')
            current = obj
            
            for part in parts:
                if current is None:
                    return None
                
                # 检查是否有索引，如 result[0] 或 emails[1]
                match = re.match(r'(\w+)\[(\d+)\]', part)
                if match:
                    key, idx_str = match.groups()
                    idx = int(idx_str)
                    
                    # 先获取对象（通过 key）
                    if isinstance(current, dict):
                        current = current.get(key)
                    elif isinstance(current, list):
                        # 如果 current 是列表，key 应该是数字索引
                        try:
                            current = current[int(key)]
                        except (IndexError, ValueError, TypeError):
                            return None
                    else:
                        return None
                    
                    # 再获取索引（通过 idx）
                    if isinstance(current, (list, tuple)):
                        try:
                            current = current[idx]
                        except (IndexError, TypeError):
                            return None
                    else:
                        # 如果 current 不是列表/元组，说明路径错误
                        return None
                else:
                    # 没有索引，直接获取属性
                    if isinstance(current, dict):
                        current = current.get(part)
                    elif isinstance(current, (list, tuple)):
                        # 如果 current 是列表/元组，part 应该是数字索引
                        if part.isdigit():
                            try:
                                current = current[int(part)]
                            except (IndexError, ValueError, TypeError):
                                return None
                        else:
                            return None
                    else:
                        return None
            
            return current
        
        def replace_value(value: Any) -> Any:
            """递归替换值中的占位符"""
            if isinstance(value, str):
                # 查找 {{stepN.path}} 格式的占位符，支持复杂路径
                # 例如：{{step1.id}} 或 {{step1.result[0].id}} 或 {{step1.data.emails[1].subject}}
                pattern = r'\{\{step(\d+)\.([^}]+)\}\}'
                matches = re.findall(pattern, value)
                
                if matches:
                    for step_num_str, path in matches:
                        step_num = int(step_num_str)
                        
                        # 从 context 中获取步骤结果
                        step_results = context.get("step_results", [])
                        if step_num > 0 and step_num <= len(step_results):
                            step_result = step_results[step_num - 1]
                            step_data = step_result.get("result", {}).get("data", {})
                            
                            # 使用 get_deep_value 获取深层值
                            extracted_value = get_deep_value(step_data, path)
                            
                            # 如果结果为 None，替换为 "NULL_ID"（脱敏日志）
                            if extracted_value is None:
                                sanitized_path = LogSanitizer.sanitize_value(path, "")
                                logger.warning(f"[SECURITY_SHIELD] 占位符 {{step{step_num}.{sanitized_path}}} 提取结果为 None，替换为 'NULL_ID'")
                                extracted_value = "NULL_ID"
                            
                            # 替换占位符
                            placeholder = f"{{{{step{step_num}.{path}}}}}"
                            value = value.replace(placeholder, str(extracted_value))
                        else:
                            # 步骤不存在（脱敏日志）
                            sanitized_path = LogSanitizer.sanitize_value(path, "")
                            logger.warning(f"[SECURITY_SHIELD] 占位符 {{step{step_num}.{sanitized_path}}} 引用的步骤不存在，替换为 'NULL_ID'")
                            placeholder = f"{{{{step{step_num}.{path}}}}}"
                            value = value.replace(placeholder, "NULL_ID")
                
                return value
            elif isinstance(value, dict):
                return {k: replace_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [replace_value(item) for item in value]
            else:
                return value
        
        return replace_value(params)
    
    def _dispatch_execution(self, executor: Any, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        实际调度执行逻辑
        
        增强功能：
        - 检测 NULL_ID 占位符，抛出 PlaceholderError
        - 日志脱敏：敏感参数值自动脱敏
        """
        step_type = step.get("type", "")
        params = step.get("params", {})
        
        # 替换占位符（如 {{step1.id}}）
        params = self._replace_placeholders(params, context)
        step["params"] = params  # 更新 step 中的 params
        
        # === 增强占位符防御：检测 NULL_ID ===
        def check_null_id(obj: Any, path: str = "") -> List[str]:
            """递归检查对象中是否包含 NULL_ID"""
            null_ids = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    if isinstance(value, str) and value == "NULL_ID":
                        null_ids.append(current_path)
                    elif isinstance(value, (dict, list)):
                        null_ids.extend(check_null_id(value, current_path))
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    current_path = f"{path}[{idx}]" if path else f"[{idx}]"
                    if isinstance(item, str) and item == "NULL_ID":
                        null_ids.append(current_path)
                    elif isinstance(item, (dict, list)):
                        null_ids.extend(check_null_id(item, current_path))
            elif isinstance(obj, str) and obj == "NULL_ID":
                null_ids.append(path if path else "root")
            return null_ids
        
        null_id_paths = check_null_id(params)
        if null_id_paths:
            # 发现 NULL_ID，抛出 PlaceholderError 触发 Reflector 重新分析
            error_msg = f"[SECURITY_SHIELD] 占位符替换失败，检测到 NULL_ID 在以下路径: {', '.join(null_id_paths)}"
            logger.error(error_msg)
            raise PlaceholderError(
                message=error_msg,
                placeholder=", ".join(null_id_paths),
                step=step
            )
        
        # === 日志脱敏：打印参数时自动脱敏敏感信息 ===
        sanitized_params = LogSanitizer.sanitize_dict(params)
        logger.debug(f"[SECURITY_SHIELD] 执行步骤参数（已脱敏）: {LogSanitizer.sanitize_log_message(str(sanitized_params), sanitized_params)}")
        
        action = step.get("action", "").lower()
        
        # 错误类型修复：如果 Reflector 生成了错误的类型，尝试修复
        if step_type in ["file_manager", "FileManager", "file_operation"]:
            # 根据 action 推断正确的类型
            if "delete" in action or "删除" in action:
                step_type = "file_delete"
                step["type"] = "file_delete"
                logger.warning(f"🔧 修复错误类型: {step.get('type')} → file_delete")
            elif "read" in action or "读取" in action:
                step_type = "file_read"
                step["type"] = "file_read"
            elif "write" in action or "写入" in action:
                step_type = "file_write"
                step["type"] = "file_write"
            else:
                step_type = "file_delete"  # 默认
                step["type"] = "file_delete"
        
        if step_type == "app_control":
            # app_control 应该根据 action 转换为 open_app 或 close_app
            if "close" in action or "关闭" in action:
                step_type = "close_app"
                step["type"] = "close_app"
                logger.warning("🔧 修复错误类型: app_control → close_app")
            else:
                step_type = "open_app"
                step["type"] = "open_app"
        
        # 1. Python Code Execution
        if step_type in ["python_script", "python"]:
            code = params.get("code", "")
            if hasattr(executor, "code_interpreter"):
                res = executor.code_interpreter.execute(code)
                if hasattr(res, "success"): 
                    return {
                        "success": res.success,
                        "message": res.message,
                        "output": res.output,
                        "error": res.error,
                        "images": res.images if hasattr(res, "images") else []
                    }
                if isinstance(res, dict):
                    return res
            return {"success": False, "message": "CodeInterpreter不可用"}
            
        # 2. FileManager Execution
        if hasattr(executor, "execute_file_operation"):
             return executor.execute_file_operation(step_type, params, context)
             
        # 3. BrowserExecutor Execution
        if hasattr(executor, "execute_browser_action"):
            return executor.execute_browser_action(step_type, params)
            
        # 4. Generic execute_step (Catch-all for SystemTools, EmailExecutor, etc.)
        if hasattr(executor, "execute_step"):
            return executor.execute_step(step, context)

        return {"success": False, "message": f"No execution method found on {executor}"}
