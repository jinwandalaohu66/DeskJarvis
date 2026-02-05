"""
DeskJarvis 简化版多代理协作系统

不依赖 CrewAI，使用原生 Python 实现多代理协作
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class SimpleAgent:
    """简化版 Agent 基类"""
    
    def __init__(
        self,
        name: str,
        role: str,
        goal: str,
        backstory: str,
        llm_caller: Optional[Callable] = None
    ):
        self.name = name
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.llm_caller = llm_caller
    
    def execute(self, task: str, context: str = "") -> str:
        """执行任务"""
        if not self.llm_caller:
            return f"[{self.name}] LLM 不可用"
        
        prompt = f"""你是 {self.role}。

你的目标：{self.goal}

背景：{self.backstory}

{context}

任务：{task}

请完成上述任务。"""
        
        return self.llm_caller(prompt)


class SimpleCrew:
    """
    简化版多代理协作系统
    
    不依赖 CrewAI，使用简单的顺序执行
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        emit_callback: Optional[Callable] = None
    ):
        self.config = config or {}
        self.emit = emit_callback
        
        # LLM 配置
        self.provider = self.config.get("ai_provider", "deepseek")
        self.model = self.config.get("ai_model", "deepseek-chat")
        self.api_key = self.config.get("api_key", "")
        
        # 创建 Agents
        self.agents = self._create_agents()
    
    def _emit_progress(self, event_type: str, data: Dict[str, Any]):
        """发送进度事件"""
        if self.emit:
            self.emit(event_type, data)
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        try:
            if self.provider == "deepseek":
                return self._call_deepseek(prompt)
            elif self.provider == "claude":
                return self._call_claude(prompt)
            elif self.provider == "openai":
                return self._call_openai(prompt)
            else:
                return self._call_deepseek(prompt)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return f"LLM 调用失败: {e}"
    
    def _call_deepseek(self, prompt: str) -> str:
        """调用 DeepSeek API"""
        import openai
        
        client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com/v1"
        )
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7
        )
        
        return response.choices[0].message.content or ""
    
    def _call_claude(self, prompt: str) -> str:
        """调用 Claude API"""
        import anthropic
        
        client = anthropic.Anthropic(api_key=self.api_key)
        
        response = client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text if response.content else ""
    
    def _call_openai(self, prompt: str) -> str:
        """调用 OpenAI API"""
        import openai
        
        client = openai.OpenAI(api_key=self.api_key)
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7
        )
        
        return response.choices[0].message.content or ""
    
    def _create_agents(self) -> Dict[str, SimpleAgent]:
        """创建所有 Agent"""
        return {
            "planner": SimpleAgent(
                name="Planner",
                role="任务规划专家",
                goal="将用户的自然语言指令分解为可执行的步骤计划",
                backstory="你是一位经验丰富的任务规划专家，擅长将复杂任务分解为简单、可执行的步骤。",
                llm_caller=self._call_llm
            ),
            "executor": SimpleAgent(
                name="Executor",
                role="任务执行专家",
                goal="高效、准确地执行每个步骤",
                backstory="你是一位高效的任务执行专家，擅长使用各种工具完成任务。",
                llm_caller=self._call_llm
            ),
            "reflector": SimpleAgent(
                name="Reflector",
                role="质量检查专家",
                goal="分析失败原因，给出精准的修复建议",
                backstory="你是一位经验丰富的质量检查专家，擅长分析问题根因。",
                llm_caller=self._call_llm
            ),
            "summarizer": SimpleAgent(
                name="Summarizer",
                role="结果总结专家",
                goal="将执行结果总结为用户易懂的报告",
                backstory="你是一位专业的结果总结专家，擅长将技术细节翻译为用户语言。",
                llm_caller=self._call_llm
            ),
        }
    
    def execute(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行多代理协作任务
        """
        start_time = time.time()
        context = context or {}
        
        self._emit_progress("crew_started", {
            "instruction": instruction,
            "agents": ["Planner", "Executor", "Reflector", "Summarizer"]
        })
        
        try:
            # ========== Step 1: 规划 ==========
            self._emit_progress("agent_progress", {
                "agent": "Planner",
                "message": "正在分析任务并制定计划..."
            })
            
            plan_prompt = f"""分析以下用户指令，制定详细的执行计划。

用户指令：{instruction}

上下文：{json.dumps(context.get("memory_context", ""), ensure_ascii=False)[:500]}

请输出：
1. 任务分析（简要）
2. 执行步骤（编号列表）
3. 每步需要的操作类型

输出格式为 JSON：
{{
    "analysis": "任务分析",
    "steps": [
        {{"step": 1, "action": "操作描述", "type": "操作类型"}}
    ]
}}"""
            
            plan_result = self.agents["planner"].execute(plan_prompt)
            logger.info(f"Planner 输出: {plan_result[:200]}")
            
            # 解析计划
            try:
                # 尝试从 markdown 代码块中提取 JSON
                if "```json" in plan_result:
                    json_str = plan_result.split("```json")[1].split("```")[0].strip()
                elif "```" in plan_result:
                    json_str = plan_result.split("```")[1].split("```")[0].strip()
                else:
                    json_str = plan_result
                
                plan = json.loads(json_str)
                steps = plan.get("steps", [])
            except:
                # 如果解析失败，创建一个默认步骤
                steps = [{"step": 1, "action": instruction, "type": "execute"}]
            
            self._emit_progress("agent_progress", {
                "agent": "Planner",
                "message": f"计划完成，共 {len(steps)} 个步骤"
            })
            
            # ========== Step 2: 执行 ==========
            self._emit_progress("agent_progress", {
                "agent": "Executor",
                "message": "开始执行任务..."
            })
            
            execution_results = []
            for i, step in enumerate(steps):
                step_desc = step.get("action", str(step))
                
                self._emit_progress("agent_progress", {
                    "agent": "Executor",
                    "message": f"执行步骤 {i+1}/{len(steps)}: {step_desc[:50]}..."
                })
                
                exec_prompt = f"""执行以下步骤：

步骤描述：{step_desc}

原始用户指令：{instruction}

请描述你如何完成这个步骤，以及执行结果。如果需要生成代码，请提供完整的 Python 代码。

注意：
- 对于系统信息查询，使用 Python 的 psutil、subprocess 等库
- 对于文件操作，使用 pathlib
- 输出 JSON 格式结果

输出格式：
{{
    "success": true/false,
    "action": "执行的操作",
    "result": "执行结果",
    "code": "如果需要执行代码，提供代码"
}}"""
                
                exec_result = self.agents["executor"].execute(exec_prompt)
                execution_results.append({
                    "step": step,
                    "result": exec_result
                })
            
            self._emit_progress("agent_progress", {
                "agent": "Executor",
                "message": f"所有步骤执行完成"
            })
            
            # ========== Step 3: 总结 ==========
            self._emit_progress("agent_progress", {
                "agent": "Summarizer",
                "message": "正在总结执行结果..."
            })
            
            summary_prompt = f"""总结以下任务的执行结果。

用户原始指令：{instruction}

执行步骤和结果：
{json.dumps(execution_results, ensure_ascii=False, indent=2)[:2000]}

请用自然、亲切的语言总结：
1. 完成了什么
2. 如果有文件，告诉用户位置
3. 如果有失败，解释原因

直接输出总结文字，不要 JSON 格式。"""
            
            summary = self.agents["summarizer"].execute(summary_prompt)
            
            duration = time.time() - start_time
            
            self._emit_progress("crew_completed", {
                "success": True,
                "duration": duration,
                "result": summary
            })
            
            return {
                "success": True,
                "message": summary,
                "duration": duration,
                "mode": "simple-multi-agent"
            }
            
        except Exception as e:
            logger.exception("SimpleCrew 执行失败")
            duration = time.time() - start_time
            
            self._emit_progress("crew_completed", {
                "success": False,
                "error": str(e),
                "duration": duration
            })
            
            return {
                "success": False,
                "fallback": True,
                "message": f"多代理执行失败: {e}",
                "mode": "simple-multi-agent"
            }
    
    def is_available(self) -> bool:
        """检查是否可用"""
        return bool(self.api_key)
