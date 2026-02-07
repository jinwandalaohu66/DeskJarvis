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
        
        for i, step in enumerate(plan):
            if context.get("_stop_execution", False):
                logger.info("检测到停止标志，终止执行")
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
                step_type = current_step.get("type", "")
                executor = self._get_executor_for_step(step_type)
                
                if not executor:
                    return {"success": False, "message": f"未找到执行器: {step_type}"}

                # 核心调度执行
                result = self._dispatch_execution(executor, current_step, context)
                last_result = result
                
                if result.get("success"):
                    return result
                    
                error_msg = result.get('message', 'Unknown Error')
                error_data = result.get('data') or {}  # 处理 data 为 None 的情况
                
                # 检查是否为配置错误（不可恢复，需要用户操作）
                is_config_error = error_data.get('is_config_error', False) or error_data.get('requires_user_action', False)
                
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
                    
            except Exception as e:
                logger.error(f"步骤 {step_index} 严重异常: {e}", exc_info=True)
                if attempt == max_attempts:
                    return {"success": False, "message": f"Runtime Error: {str(e)}"}
        
        return last_result

    def _get_executor_for_step(self, step_type: str) -> Any:
        """根据步骤类型获取执行器实例"""
        # 文件操作：统一路由到 FileManager（包括错误类型修复）
        file_operations = [
            "file_create", "file_read", "file_write", "file_delete",
            "file_rename", "file_move", "file_copy", "file_organize",
            "file_classify", "file_batch_rename", "file_batch_copy",
            "file_batch_organize", "create_file", "read_file", 
            "list_dir", "delete_file"
        ]
        # 兼容错误的类型名称（由 Reflector 错误生成）
        file_related_error_types = ["file_manager", "FileManager", "file_operation"]
        if step_type in file_operations or step_type in file_related_error_types:
            return self.tools.get("file_manager")
        
        if step_type in ["open_url", "click", "type", "scroll", "scrape", "screenshot_web"]:
            return self.tools.get("browser_executor")
        
        if step_type in ["python_script", "python", "code_interpreter"]:
            return self.tools.get("system_tools")
        
        if step_type in ["screenshot_desktop", "open_app", "close_app", "set_volume", "set_brightness", "get_system_info", "open_folder", "open_file", "text_process"]:
             return self.tools.get("system_tools")
        
        if step_type in ["send_email", "search_emails", "get_email_details", "download_attachments", "manage_emails", "compress_files"]:
            return self.tools.get("email_executor")
        
        return self.tools.get("system_tools")

    def _dispatch_execution(self, executor: Any, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """实际调度执行逻辑"""
        step_type = step.get("type", "")
        params = step.get("params", {})
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
