"""
DeepSeek规划器：使用DeepSeek API规划任务

遵循 docs/ARCHITECTURE.md 中的Planner模块规范
"""

from typing import List, Dict, Any, Optional
import logging
import json
import datetime
from openai import OpenAI
from agent.tools.exceptions import PlannerError
from agent.tools.config import Config
from agent.planner.base_planner import BasePlanner

logger = logging.getLogger(__name__)


class DeepSeekPlanner(BasePlanner):
    """
    DeepSeek规划器：调用DeepSeek API规划任务（使用OpenAI兼容接口）
    """
    
    def __init__(self, config: Config):
        """
        初始化规划器
        
        Args:
            config: 配置对象
        
        Raises:
            PlannerError: 当API密钥无效时
        """
        super().__init__(config)
        api_key = config.api_key
        
        if not api_key:
            raise PlannerError("API密钥未设置，请在配置文件中设置api_key")
        
        try:
            # DeepSeek 使用 OpenAI 兼容接口
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            self.model = config.model
            logger.info(f"DeepSeek规划器已初始化，模型: {self.model}")
        except Exception as e:
            raise PlannerError(f"初始化DeepSeek客户端失败: {e}")
    
    def plan(
        self,
        user_instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        规划任务
        
        Args:
            user_instruction: 用户指令（自然语言）
            context: 上下文信息（可选）
        
        Returns:
            任务步骤列表
        """
        try:
            # 注入实时时间 (Protocol Phase 38+)
            # 确保 context 存在
            if context is None:
                context = {}
            current_time = context.get("current_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            # 确保 current_time 被写回 context，供后续使用
            context["current_time"] = current_time
            
            # Protocol G+ 硬性约束：检测模糊词汇，强制插入 list_files
            needs_grounding = self._check_protocol_g_plus(user_instruction, context)
            grounding_path = None
            if needs_grounding:
                grounding_path = self._infer_directory(user_instruction, context)
                logger.warning(f"🔵 Protocol G+ 触发：检测到模糊词汇，强制插入 list_files 步骤，路径: {grounding_path}")
            
            # Build the prompt with real-time context and Protocol G+ enforcement
            prompt = self._build_prompt(user_instruction, context)
            
            logger.info("开始规划任务...")

            def call_llm(messages):
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=4000,
                )

            messages = [
                {
                    "role": "system",
                    "content": "你是一个AI任务规划助手。请理解用户的自然语言指令，生成可执行的任务步骤。只返回JSON数组，不要添加其他文字。",
                },
                {"role": "user", "content": prompt},
            ]

            response = call_llm(messages)
            content = response.choices[0].message.content or ""
            logger.warning("🔵 正在调用DeepSeek API规划任务...")
            logger.warning(f"🔵 DeepSeek原始响应（前2000字符）: {content[:2000]}...")
            logger.debug(f"DeepSeek完整响应: {content}")

            # 解析响应：若 JSON 格式失败，自动重试一次（仅修复输出格式）
            try:
                steps = self._parse_response(content)
                logger.warning(f"🔵 解析后的步骤列表: {steps}")
                
                # 检查是否有open_app步骤，记录app_name用于调试
                for i, step in enumerate(steps):
                    if step.get("type") == "open_app":
                        app_name = step.get("params", {}).get("app_name", "")
                        logger.warning(f"🔵 步骤{i+1} open_app的app_name: '{app_name}' (长度: {len(app_name)})")
                        if len(app_name) > 20 or any(kw in app_name for kw in ["控制", "输入", "搜索", "按"]):
                            logger.error(f"❌ 检测到可疑的app_name: '{app_name}'，可能包含后续操作！AI没有正确拆分步骤！")
            except Exception as e:
                logger.warning(f"解析规划结果失败，将重试一次修复输出格式: {e}")
                retry_messages = [
                    {
                        "role": "system",
                        "content": "你是一个严格的JSON生成器。你只允许输出一个JSON数组（[]），不得包含任何其他字符。",
                    },
                    {
                        "role": "user",
                        "content": (
                            "上一次输出不是合法JSON，解析失败。\n"
                            "错误信息:\n"
                            + str(e)
                            + "\n\n"
                            "上一次原始输出（可能被截断）:\n"
                            + content[:1500]
                            + "\n\n"
                            "请重新输出合法JSON数组。规则：\n"
                            "- 只输出 JSON 数组（以 [ 开头，以 ] 结尾）\n"
                            "- 所有字符串必须使用双引号，且字符串内换行必须写成 \\n\n"
                            "- 不要输出 markdown 代码块\n"
                        ),
                    },
                ]
                response2 = call_llm(retry_messages)
                content2 = response2.choices[0].message.content or ""
                logger.debug(f"AI重试响应: {content2[:500]}...")
                steps = self._parse_response(content2)

            logger.info(f"规划完成，共 {len(steps)} 个步骤")
            
            # Protocol G+ 后处理：如果检测到模糊词汇，强制在第一步插入 list_files
            if needs_grounding and grounding_path:
                # 检查是否已经有 list_files 步骤
                has_list_files = any(step.get("type") == "list_files" for step in steps)
                if not has_list_files:
                    logger.warning(f"🔵 Protocol G+：强制在第一步插入 list_files({grounding_path})")
                    list_files_step = {
                        "type": "list_files",
                        "action": f"列出目录内容以确认文件位置: {grounding_path}",
                        "params": {"path": grounding_path},
                        "description": "Protocol G+ 强制步骤：检测到模糊词汇，必须先确认目录内容再执行后续操作"
                    }
                    steps.insert(0, list_files_step)
                    logger.info("✅ 已插入 list_files 步骤作为第一步")
            
            # 保存用户指令，用于后处理检查
            user_instruction_lower = user_instruction.lower() if user_instruction else ""
            
            # 后处理：检查并修复 screenshot_desktop 缺少 save_path 的情况
            for i, step in enumerate(steps, 1):
                step_type = step.get('type')
                step_params = step.get('params', {})
                
                # 如果是 screenshot_desktop，检查用户是否要求保存到桌面
                if step_type == 'screenshot_desktop':
                    # 检查用户指令中是否包含"保存到桌面"、"保存桌面"等关键词
                    has_save_to_desktop = (
                        "保存到桌面" in user_instruction or
                        "保存桌面" in user_instruction or
                        "保存到 ~/Desktop" in user_instruction or
                        "save to desktop" in user_instruction_lower or
                        "save desktop" in user_instruction_lower or
                        ("保存" in user_instruction and "桌面" in user_instruction) or
                        ("save" in user_instruction_lower and "desktop" in user_instruction_lower)
                    )
                    
                    # 检查是否已经传递了 save_path 参数
                    has_save_path = 'save_path' in step_params and step_params.get('save_path')
                    
                    if has_save_to_desktop and not has_save_path:
                        logger.warning(f"⚠️ 步骤 {i} screenshot_desktop：用户要求保存到桌面，但未传递save_path参数，自动添加")
                        step_params['save_path'] = "~/Desktop/screenshot.png"
                        steps[i-1]['params'] = step_params
                        logger.info("✅ 已自动添加 save_path: ~/Desktop/screenshot.png")
            
            return steps
            
        except Exception as e:
            logger.error(f"规划任务失败: {e}", exc_info=True)
            raise PlannerError(f"规划任务失败: {e}")

    def _check_protocol_g_plus(self, instruction: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        检测是否需要 Protocol G+ 硬性约束
        
        Args:
            instruction: 用户指令
            context: 上下文信息
        
        Returns:
            如果需要强制插入 list_files，返回 True
        """
        # 0. 排除非文件操作场景（视觉操作、系统控制等）
        non_file_operation_keywords = [
            "视觉", "截图", "屏幕", "图标", "颜色", "坐标", "位置",
            "visual_assist", "visual", "screenshot", "screen",
            "音量", "亮度", "通知", "提醒", "日历", "邮件",
            "volume", "brightness", "notification", "calendar", "email"
        ]
        
        # 如果指令明显是视觉操作或其他非文件操作，不触发 Protocol G+
        if any(kw in instruction for kw in non_file_operation_keywords):
            return False
        
        # 1. 检测模糊词汇（仅针对文件相关的模糊词汇）
        ambiguous_keywords = [
            "最后一份", "那份", "桌面上的", "刚才的", "最近的", 
            "那个文件", "这个文件", "它", "这份", "那份文件",
            "刚才下载的", "最近下载的", "下载的"
        ]
        
        # 注意："桌面"单独处理，需要结合上下文判断
        
        # 2. 检测是否涉及文件操作（更精确的关键词）
        file_operation_keywords = [
            "分析", "读取", "打开文件", "处理文件", "整理文件", "删除文件", 
            "移动文件", "复制文件", "重命名文件", "analyze", "read", "open file",
            "处理文档", "查看文件", "编辑文件", "修改文件",
            "文件", "文档", "pdf", "docx", "excel", "file", "document"
        ]
        
        # 3. 检查是否包含模糊词汇
        has_ambiguous = any(kw in instruction for kw in ambiguous_keywords)
        
        # 4. 检查"桌面"关键词（需要结合文件操作上下文）
        has_desktop = "桌面" in instruction or "Desktop" in instruction
        # 只有当"桌面"与文件操作关键词结合时才认为是文件操作
        if has_desktop:
            has_file_op = any(kw in instruction for kw in file_operation_keywords)
            if not has_file_op:
                # "桌面"单独出现，且没有文件操作关键词，可能是视觉操作，不触发
                return False
        
        # 5. 检查是否涉及文件操作
        has_file_op = any(kw in instruction for kw in file_operation_keywords)
        
        # 6. 如果同时包含模糊词汇和文件操作，需要 Protocol G+
        if has_ambiguous and has_file_op:
            return True
        
        # 7. 如果上下文中有 attached_path 或 last_created_file，但指令中使用模糊词汇，也需要 Protocol G+
        if context:
            has_context_file = bool(context.get("attached_path") or context.get("last_created_file"))
            if has_context_file and has_ambiguous and has_file_op:
                return True
        
        return False
    
    def _infer_directory(self, instruction: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        从用户指令中推断目录路径（语义路径映射器）
        
        Args:
            instruction: 用户指令
            context: 上下文信息
        
        Returns:
            推断出的目录路径
        """
        # 1. 优先检查上下文中的路径（最准确）
        if context:
            attached_path = context.get("attached_path")
            if attached_path:
                from pathlib import Path
                path = Path(attached_path).expanduser()
                if path.is_dir():
                    return str(path)
                elif path.is_file():
                    return str(path.parent)
            
            last_created_file = context.get("last_created_file")
            if last_created_file:
                from pathlib import Path
                path = Path(last_created_file).expanduser()
                if path.exists():
                    return str(path.parent)
        
        # 2. 语义路径映射（按优先级排序）
        mapping = {
            "桌面": "~/Desktop",
            "Desktop": "~/Desktop",
            "下载": "~/Downloads",
            "Downloads": "~/Downloads",
            "文档": "~/Documents",
            "Documents": "~/Documents",
            "图片": "~/Pictures",
            "Pictures": "~/Pictures",
            "根目录": "~",
            "主目录": "~",
            "home": "~"
        }
        
        instruction_lower = instruction.lower()
        
        # 优先匹配更具体的路径（如"桌面"优先于"图片"）
        priority_order = ["桌面", "Desktop", "下载", "Downloads", "文档", "Documents", "图片", "Pictures"]
        for key in priority_order:
            if key.lower() in instruction_lower:
                return mapping[key]
        
        # 其他映射
        for key, path in mapping.items():
            if key not in priority_order and key.lower() in instruction_lower:
                return path
        
        # 3. 如果指令中提到具体的文件夹名（如"自定文件"），优先搜索 Desktop
        # 因为用户自定义文件夹通常在 Desktop 或 Documents
        if any(kw in instruction for kw in ["文件夹", "目录", "folder", "directory"]):
            # 检查是否提到具体的文件夹名
            import re
            # 匹配中文文件夹名（如"自定文件"、"我的文件夹"）
            folder_pattern = r'["""]([^"""]+)["""]|到([^到]+)文件夹|到([^到]+)目录'
            matches = re.findall(folder_pattern, instruction)
            if matches:
                # 如果提到具体文件夹名，优先在 Desktop 搜索
                return "~/Desktop"
        
        # 4. 默认返回 Desktop（最常见的操作目录）
        return "~/Desktop"
    
    def _build_prompt(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建规划提示词"""
        # 获取当前时间（从 context 或使用默认值）
        current_time = ""
        if context:
            current_time = context.get("current_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        else:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建上下文信息
        context_info = ""
        if context:
            created_files = context.get("created_files", [])
            last_created_file = context.get("last_created_file")
            attached_path = context.get("attached_path")
            chat_history = context.get("chat_history", [])
            memory_context = context.get("memory_context", "")
            workflow_suggestion = context.get("workflow_suggestion")
            
            # 添加记忆上下文（优先级最高）
            if memory_context:
                context_info += "\n\n**记忆上下文**（AI对用户的了解）：\n"
                context_info += memory_context + "\n"
            
            # 添加工作流建议
            if workflow_suggestion:
                context_info += "\n\n**工作流建议**：\n"
                pattern = workflow_suggestion.get("pattern", {})
                context_info += "用户经常执行类似任务，建议使用之前成功的步骤模式：\n"
                action_seq = pattern.get("action_sequence", [])
                if action_seq:
                    context_info += f"常用步骤序列：{' → '.join(action_seq)}\n"
            
            # 添加聊天历史
            if chat_history:
                context_info += "\n\n**对话历史**：\n"
                for i, msg in enumerate(chat_history[-5:], 1):  # 只保留最近5条
                    role_name = "用户" if msg.get("role") == "user" else "AI助手"
                    content = msg.get("content", "")
                    if len(content) > 200:
                        content = content[:200] + "..."
                    context_info += f"{i}. [{role_name}]: {content}\n"
            
            # 添加文件上下文
            if created_files or attached_path or last_created_file:
                context_info += "\n\n**文件上下文**：\n"
                if attached_path:
                    context_info += f"- 用户附加的文件/文件夹: {attached_path}\n"
                if last_created_file:
                    context_info += f"- 最近操作的文件: {last_created_file}\n"
                if len(created_files) > 1:
                    context_info += f"- 之前操作过的文件: {', '.join(created_files[:5])}\n"
                context_info += "\n提示：如果用户说\"这个文件\"、\"刚才的文件\"等，请结合对话历史和文件上下文判断用户指的是哪个文件。\n"
                
                # *** 关键修复 ***
                # 显式指示优先级，防止 AI 过度关注历史记录中的旧文件
                context_info += """
**重要上下文优先级**：
1. **最高优先级**：[用户附加的文件/文件夹] (attached_path)
   - 如果用户说"这个文件"、"这个文件夹"、"整理它"、"处理它"，且 attached_path 存在，**必须**优先操作 attached_path，忽略对话历史中提到的其他文件。
2. **次高优先级**：[最近操作的文件] (last_created_file)
   - 只有当 attached_path 为空时，才考虑 last_created_file。
3. **最低优先级**：对话历史
   - 只有前两者都为空时，才从历史中推断。
"""
        
        # 按需精简 prompt
        needs_browser = any(kw in instruction for kw in [
            "网页", "网站", "浏览", "搜索", "下载", "http", "www",
            "百度", "谷歌", "google", "访问", "登录",
        ])
        needs_word = any(kw in instruction.lower() for kw in [
            "word", "docx", ".docx", "替换文字", "替换文档",
        ])
        needs_chart = any(kw in instruction for kw in [
            "图表", "柱形图", "饼图", "折线图", "统计", "chart",
        ])
        
        browser_section = ""
        if needs_browser:
            browser_section = """
**浏览器操作**：
- browser_navigate: 导航网页 → params: {{"url": "网址"}}
- browser_click: 点击元素 → params: {{"selector": "选择器"}}
- browser_fill: 填写表单 → params: {{"selector": "选择器", "value": "值"}}
- browser_screenshot: 截图网页 → params: {{"save_path": "保存路径"}}
- download_file: 下载文件 → params: {{"selector": "下载按钮选择器"}} 或 {{"text": "下载按钮文字"}}
- download_latest_python_installer: 下载最新 Python → params: {{"save_dir": "保存目录"}}

**登录和验证码**：
- request_login: 请求登录 → params: {{"site_name": "网站名", "username_selector": "...", "password_selector": "..."}}
- request_captcha: 请求验证码 → params: {{"site_name": "网站名", "captcha_image_selector": "...", "captcha_input_selector": "..."}}
"""
        
        word_section = ""
        if needs_word:
            word_section = """
**Word文档处理（.docx）**：
- **必须使用 python-docx 库**：`from docx import Document`
- **绝对禁止用 open() 读取 .docx 文件**！
- **替换文字必须用 replace_across_runs 函数**：
  ```python
  def replace_across_runs(paragraph, old_text, new_text):
      runs = paragraph.runs
      if not runs:
          return 0
      replaced = 0
      while True:
          full = "".join([r.text for r in runs])
          idx = full.find(old_text)
          if idx == -1:
              break
          mapping = []
          for run_i, r in enumerate(runs):
              for off in range(len(r.text)):
                  mapping.append((run_i, off))
          start = idx
          end = idx + len(old_text) - 1
          if end >= len(mapping):
              break
          s_run, s_off = mapping[start]
          e_run, e_off = mapping[end]
          before = runs[s_run].text[:s_off]
          after = runs[e_run].text[e_off + 1:]
          if s_run == e_run:
              runs[s_run].text = before + new_text + after
          else:
              runs[s_run].text = before + new_text
              for j in range(s_run + 1, e_run):
                  runs[j].text = ""
              runs[e_run].text = after
          replaced += 1
      return replaced
  ```
- 遍历范围：正文段落 + 表格 + 页眉页脚
- 替换 0 处必须返回 `success: False`
"""
        
        chart_section = ""
        if needs_chart:
            chart_section = """
**Matplotlib 图表用法**：
- 颜色列表：`colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8']`
- **不要用** `plt.cm.set3` 或 `plt.cm.Set3`
- 中文：`plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']`
- 保存：`plt.savefig(路径, dpi=150, bbox_inches='tight', facecolor='white')`
"""
        
        prompt = f"""你是一个AI任务规划助手。请理解用户的自然语言指令，生成可执行的任务步骤。

**核心原则**：
- **理解用户的真实意图**：仔细分析用户的自然语言指令，理解用户想做什么
- **拆分多个操作**：如果用户指令包含多个操作（如"打开应用然后输入文本"），必须拆分为多个步骤
- **每个步骤只做一件事**：一个步骤只执行一个操作
- **意图与内容分离**：严禁将控制逻辑（如“重复N次”、“每隔五分钟”）误认为是内容（如邮件正文、文本）。

**重复执行规则**（极其重要）：
- 如果用户要求“重复 N 次”、“执行十遍”、“做三次”：
  - **如果 N <= 5**：直接在 JSON 数组中生成 N 个完全相同的任务步骤。
  - **如果 N > 5**：必须生成一个 `execute_python_script` 步骤，在代码中使用 `for i in range(N):` 循环来调用相应的逻辑。
- 示例：“发邮件给 boss@qq.com，内容是‘开会’，发送三遍”
  → 应生成 3 个独立的 `send_email` 步骤，而不是把“发送三遍”写进 body。

**最重要的规则（必须遵守！）**：
- **调整亮度** → 必须用 `set_brightness` 工具，绝对不要用脚本！
- **调整音量** → 必须用 `set_volume` 工具，绝对不要用脚本！
- **发送通知** → 必须用 `send_notification` 工具，绝对不要用脚本！
- **语音播报** → 必须用 `speak` 工具，绝对不要用脚本！
- **剪贴板操作** → 必须用 `clipboard_read`/`clipboard_write` 工具！

**核心原则**：
- 理解用户的真实意图
- 优先使用已有工具，只有工具无法完成时才用脚本

**你的能力**：
1. **文件操作**：读取、写入、创建、删除、重命名、移动、复制文件
2. **浏览器操作**：导航网页、点击、填写表单、下载文件、截图网页
3. **系统操作**：桌面截图、打开/关闭应用、打开文件/文件夹
4. **脚本执行**：生成并执行Python脚本完成复杂任务

**可用工具及必需参数**（只能使用以下工具，不能自创工具名！）：

**⚠️ 重要：工具类型命名规则**
- **严禁使用**以下非标准类型：`app_control`, `file_manager`, `FileManager`, `file_operation`, `shell`
- **文件操作必须使用标准类型**：`file_delete`, `file_read`, `file_write`, `file_create`, `file_rename`, `file_move`, `file_copy`
- **应用操作必须使用标准类型**：`open_app`, `close_app`（不要用 `app_control`）

**文件操作工具**：
- file_read: 读取文件 → params: {{"file_path": "文件路径"}}
- file_write: 写入文件 → params: {{"file_path": "文件路径", "content": "内容"}}
- file_create: 创建文件 → params: {{"file_path": "文件路径", "content": "内容"}}
- file_rename: 重命名文件 → params: {{"file_path": "原文件路径", "new_name": "新文件名"}}
- file_move: 移动文件 → params: {{"file_path": "原路径", "destination": "目标路径"}}
- file_copy: 复制文件 → params: {{"file_path": "原路径", "destination": "目标路径"}}
- file_delete: 删除文件 → params: {{"file_path": "文件路径"}}
- screenshot_desktop: 截图桌面 → params: {{"save_path": "保存路径（可选）"}}
- open_file: 打开文件 → params: {{"file_path": "文件路径"}}
- open_folder: 打开文件夹 → params: {{"folder_path": "文件夹路径"}}
- list_files: 列出文件 (Grounding) → params: {{"path": "目录路径(如 ~/Desktop)"}}
- open_app: 打开应用 → params: {{"app_name": "应用名称"}}
- close_app: 关闭应用 → params: {{"app_name": "应用名称"}}
- execute_python_script: Python脚本 → params: {{"script": "base64编码的脚本", "reason": "原因", "safety": "安全说明"}}
{browser_section}
**系统控制工具**：
- set_volume: 设置音量 → params: {{"level": 0-100}} 或 {{"action": "mute/unmute/up/down"}}
- set_brightness: 设置屏幕亮度 → params: {{"level": 0.0-1.0}} 或 {{"action": "up/down/max/min"}}（优先使用此工具！）
- send_notification: 发送通知 → params: {{"title": "标题", "message": "内容"}}
- speak: 语音播报 → params: {{"text": "要播报的内容"}}
- clipboard_read: 读取剪贴板 → params: {{}}
- clipboard_write: 写入剪贴板 → params: {{"content": "内容"}}
- keyboard_type: 键盘输入 → params: {{"text": "要输入的文本"}}
- keyboard_shortcut: 按键/快捷键（用于回车/Tab/Esc/方向键/⌘C 等）→ params: {{"keys": "command+c"}}，可选 {{"repeat": 2}}（如按两次回车）
- search_emails: 搜索邮件 → params: {{"query": "搜索词", "folder": "文件夹(可选)", "limit": 10(可选)}}
  - **重要**: query 必须包含 IMAP 语法（如 `(FROM "xxx")`, `(SUBJECT "xxx")`, `UNSEEN`）。
- get_email_details: 获取邮件详情 → params: {{"id": "邮件ID", "folder": "文件夹(可选)"}}
- download_attachments: 下载邮件附件 → params: {{"id": "邮件ID", "save_dir": "保存目录", "file_type": "后缀名(如pdf, 可选)", "limit": 数量(可选), "folder": "文件夹(可选)"}}
- manage_emails: 管理邮件 → params: {{"id": "邮件ID", "action": "move/mark_read", "target_folder": "目标文件夹(如果是move)"}}
- analyze_document: 智能文档分析 (PDF/Docx/Excel) → params: {{"file_path": "路径", "action": "map/read/analyze", "query": "问题", "page_num": 1(可选)}}
  - **重要**: 优先使用 `map` 获取结构，再根据需求 `read` 特定页或 `analyze` 全文。
- run_applescript: 运行 AppleScript (macOS 自动化) → params: {{"script": "脚本内容"}}
- manage_calendar_event: 管理日历 (macOS) → params: {{"action": "create/list", "title": "标题", "start_time": "YYYY-MM-DD HH:MM:SS"}}
- manage_reminder: 管理提醒事项 (macOS) → params: {{"action": "create/list", "title": "标题"}}
- visual_assist: 视觉助手 (Phase 39) → params: {{"action": "query/locate/extract_text", "query": "问题(extract_text时可选)", "image_path": "图片路径(可选，不提供则自动截图)", "force_vlm": false}}
  - **action说明**:
    - `query`: 问答模式（默认），需要query参数，如"屏幕上那个红色的按钮写什么？"
    - `locate`: 定位模式，需要query参数，查找元素位置，返回坐标，如"找到提交按钮的位置"
    - `extract_text`: 提取模式，query参数可选（不提供则提取所有文本），提取截图中的所有文本
  - **参数要求**:
    - `query` 和 `locate` 操作**必须**提供 `query` 参数
    - `extract_text` 操作 `query` 参数**可选**（不提供则提取所有文本）
  - **成本优化**: 系统会自动使用OCR优先策略（成本0），仅在需要语义理解时调用VLM
  - **坐标系注意**: 返回的坐标已处理Retina缩放，可直接用于mouse_click
  - **示例**: 
    - {{"type": "visual_assist", "params": {{"action": "locate", "query": "找到提交按钮的位置"}}}}
    - {{"type": "visual_assist", "params": {{"action": "extract_text"}}}}

**键盘规则（重要！）**：
- **输入文字**用 `keyboard_type`（支持中文、英文、数字、符号）
  - 示例：输入"张旭政" → `{{"type":"keyboard_type","params":{{"text":"张旭政"}}}}`
  - 示例：输入"zhangxuzheng" → `{{"type":"keyboard_type","params":{{"text":"zhangxuzheng"}}}}`
- **按回车/Tab/Esc/方向键**必须用 `keyboard_shortcut`，不要把 "enter" 当文本输入！
  - 按两次回车：`{{"type":"keyboard_shortcut","params":{{"keys":"enter","repeat":2}}}}`
- mouse_click: 鼠标点击 → params: {{"x": 100, "y": 200}}
- window_minimize: 最小化窗口 → params: {{"app_name": "应用名（可选）"}}
- window_maximize: 最大化窗口 → params: {{"app_name": "应用名（可选）"}}

**系统信息和图片处理**：
- get_system_info: 获取系统信息 → params: {{"info_type": "battery/disk/memory/apps/network/all", "save_path": "~/Desktop/系统报告.md（可选，指定后自动保存）"}}
  **重要：查询系统信息必须使用这个工具，不要自己写脚本！如果用户要求保存，直接在 save_path 中指定路径！**
- image_process: 图片处理 → params: {{"image_path": "图片路径", "action": "compress/resize/convert/info", "width": 800, "height": 600, "format": "jpg/png/webp", "quality": 80}}

**定时提醒**：
- set_reminder: 设置提醒 → params: {{"message": "提醒内容", "delay": "5分钟/1小时/30秒", "repeat": "daily/hourly（可选）"}}
- list_reminders: 列出提醒 → params: {{}}
- cancel_reminder: 取消提醒 → params: {{"reminder_id": "提醒ID"}}

**工作流管理**：
- create_workflow: 创建工作流 → params: {{"name": "工作流名", "commands": ["命令1", "命令2"], "description": "描述"}}
- list_workflows: 列出工作流 → params: {{}}
- delete_workflow: 删除工作流 → params: {{"name": "工作流名"}}

**任务历史**：
- get_task_history: 获取历史 → params: {{"limit": 20}}
- search_history: 搜索历史 → params: {{"keyword": "关键词"}}
- add_favorite: 添加收藏 → params: {{"instruction": "指令内容", "name": "收藏名（可选）"}}
- list_favorites: 列出收藏 → params: {{}}
- remove_favorite: 移除收藏 → params: {{"favorite_id": "收藏ID"}}

**文本AI处理**：
- text_process: AI文本处理 → params: {{"text": "要处理的文本", "action": "translate/summarize/polish/expand/fix_grammar", "target_lang": "目标语言（翻译时使用）"}}

**关键规则**：
1. **Word文档(.docx)操作必须用 execute_python_script**，没有 replace_text_in_docx 工具！
2. **批量文件操作必须用 execute_python_script**
3. **不能自创工具名**，只能用上面列出的标准类型
4. **严禁使用非标准类型**：`app_control`, `file_manager`, `FileManager`, `file_operation`, `shell` 等都是无效类型
5. **文件删除必须用 `file_delete`**，不要用 `app_control` 或 `file_manager`
6. **应用关闭必须用 `close_app`**，不要用 `app_control`
7. 如果任务无法用上面工具完成，就用 execute_python_script
8. **音量控制必须用 set_volume 工具**，不要用脚本！
9. **亮度控制必须用 set_brightness 工具**，不要用脚本！
10. **系统通知必须用 send_notification 工具**，不要用脚本！

**Python脚本执行**（复杂任务或工具无法满足时使用）：
- script: Python代码，**必须使用 base64 编码**（避免JSON转义问题）
- reason: 为什么使用脚本而不是工具
- safety: 安全检查说明
- **脚本要求**：
  * 安全：文件操作限制在用户主目录或沙盒目录（~/Desktop, ~/Downloads, ~/.deskjarvis/sandbox）
  * 禁止危险命令：rm -rf /, sudo, chmod 777 等
  * 必须使用 try-except 包裹可能失败的操作
  * **本地文件统计/生成图表必须用 execute_python_script**，不要使用任何 browser_* 工具
  * **必须通过 ruff 快检（E/F/B）**：系统会在执行前自动运行 `ruff check --select E,F,B`，不通过会直接失败并进入反思重试
    - 常见必修点：只 import 你真正用到的（避免 F401），不要引用未定义变量（F821），不要 `except:`（E722），确保没有语法错误（E999），`raise` 保留异常链（B904）
  * 输出格式：`print(json.dumps({{"success": True 或 False, "message": "...", "data": {{...}}}}))`
  * Python布尔值：使用 `True`/`False`（首字母大写），不是 `true`/`false`
  * 浏览器操作：使用 `playwright.sync_api` 模块
  * 文件操作：使用 `os`, `shutil`, `pathlib` 模块
  * **HTTP 请求（重要！）**：
    - **必须使用 requests 库**，不要用 urllib！
    - `import requests` → `response = requests.get(url)`
    - `requests` 会自动处理 gzip 解压，`urllib` 不会！
    - 下载二进制文件：`response.content`（不是 `response.text`）
    - 下载文本：`response.text`（自动处理编码）
    - 示例：
      ```python
      import requests
      response = requests.get(url)
      # 文本内容
      html = response.text
      # 二进制内容（下载文件）
      with open(path, "wb") as f:
          f.write(response.content)
      ```
{word_section}
  * **文件路径**：脚本中应该**直接使用文件路径**（硬编码），不要从环境变量读取。使用 `os.path.expanduser()` 或 `pathlib.Path.home()` 处理 `~` 符号。例如：`file_path = os.path.expanduser("~/Desktop/file.docx")`
  * **重要**：文件路径**不要进行 URL 编码**（不要使用 `urllib.parse.quote()` 或类似函数），直接使用原始的中文文件名。例如：`"~/Desktop/强制执行申请书.docx"` 而不是 `"~/Desktop/%E5%BC%BA%E5%88%B6%E6%89%A7%E8%A1%8C%E7%94%B3%E8%AF%B7%E4%B9%A6.docx"`
  * **文件名必须准确**：必须使用用户指令中提到的**完整准确的文件名**，不要随意更改、替换或编码文件名。
    - **重要**：文件名必须**逐字逐句完全匹配**用户指令中的文件名，包括中文字符、英文、数字、扩展名等。
    - **示例1**：如果用户说"强制执行申请书.docx"，脚本中必须使用 `"强制执行申请书.docx"`，**绝对不要**改成 `"大取同学名称.docx"`、`"求正放接探底作品.docx"` 或其他任何名称。
    - **示例2**：如果用户说"总结.txt"，必须使用 `"总结.txt"`，**绝对不要**改成 `"连排.txt"`、`"输克.txt"` 或其他任何名称。
    - **检查方法**：生成脚本后，检查脚本中的文件名是否与用户指令中的文件名完全一致，如果不一致，必须修正。
  * **Python语法（极其重要！！！）**：
    - **列表/字典定义必须闭合**：检查所有 list `[]` 和 dict `{{}}` 是否正确闭合。
    - **中文列表极其容易出错**：定义包含中文的列表时，必须逐个检查引号。
       正确: `numbers = ["一", "二", "三"]`
       错误: `numbers = ["一", "二", "三]` (缺少闭合引号)
    - **绝对禁止 f-string**：不要用 f"xxx" 格式！因为嵌套引号极易出错。
    - **禁止**在 f-string 中使用复杂嵌套引号。例如 `f"Status: {{json.dumps(...)}}"` 极易出错。请分开写：`status_json = json.dumps(...); print(f"Status: {{status_json}}")`
    - **字符串拼接必须完整**：每个 + 两边都要有完整的字符串
      正确: "成功删除 " + str(count) + " 个文件"
      错误: "成功删除 " + str(count) " 个文件"  (缺少 +)
      错误: "成功删除 " + str(count) + " 个文件  (缺少闭合引号)
    - **try-except 必须完整配对（极其重要！）**：
      正确格式：
      ```python
      try:
          # 代码
      except Exception as e:
          print(json.dumps({{"success": False, "message": str(e)}}))
      ```
      错误：只有 try 没有 except，会导致 SyntaxError！
    - **生成脚本后务必检查**：
      1. 每个引号都有配对
      2. 每个括号都有配对
      3. **每个 try 必须有 except**（最常见错误！）
      4. 字符串拼接的 + 号不能漏
    - **平台检测正确方法**：
      ```python
      import sys
      if sys.platform == "darwin":  # macOS
      elif sys.platform == "win32":  # Windows
      elif sys.platform == "linux":  # Linux
      ```
      **错误**: `os.name.astype()` 根本不存在！
{chart_section}
  * **文件名搜索（关键）**：
    - 用户说的可能是部分文件名（如"强制执行申请书"可能指"强制执行申请书-张三.docx"）
    - **先用 glob 或 os.listdir 搜索匹配的文件**，再进行操作
    - **不要猜测完整文件名**，使用关键词搜索
  * **文件名准确性**：必须使用用户指令中提到的**准确文件名**，不要随意更改文件名。

**路径格式**：
- 支持相对路径（如 "Desktop/file.txt"）
- 支持绝对路径（如 "~/Desktop/file.txt"）
- 支持文件名（系统会自动搜索）
- 支持 ~ 符号（如 "~/Desktop"）

**重要规则**：
- **桌面截图任务**：如果用户说"截图桌面"、"桌面截图"、"保存到桌面"等，**必须使用 screenshot_desktop 工具**，并且**如果用户要求保存到桌面，必须传递 save_path 参数**：
  * 如果用户说"保存到桌面"或"保存桌面"：传递 `"save_path": "~/Desktop/screenshot.png"`（必须包含文件名和 .png 后缀，不要只传目录）
  * 如果用户只说"截图桌面"但没有说保存位置：可以省略 save_path（使用默认位置）
- **只执行用户明确要求的操作**：如果用户说"截图桌面"，就只截图，不要删除文件、移动文件或其他操作
- **准确理解用户意图**：如果用户说"保存到桌面"，必须传递 save_path 参数

**浏览器登录&下载工作流**：
- **下载需要登录的网站**：如果检测到下载需要登录，必须按以下顺序：
  1. `browser_navigate`（导航到网站）
  2. `request_login` 或 `request_qr_login`（请求登录）
  3. 等待2-3秒（`browser_wait`）
  4. `download_file`（下载文件）
  示例："下载GitHub私有仓库" →
  ```json
  [
    {{"type": "browser_navigate", "params": {{"url": "github.com/user/repo"}}}},
    {{"type": "request_login", "params": {{"site_name": "GitHub"}}}},
    {{"type": "browser_wait", "params": {{"timeout": 3000}}}},
    {{"type": "download_file", "params": {{"text": "Download ZIP"}}}}
  ]
  ```
- **二维码登录网站**（微信、QQ等）：
  ```json
  [
    {{"type": "browser_navigate", "params": {{"url": "网站URL"}}}},
    {{"type": "request_qr_login", "params": {{"site_name": "网站名"}}}}
  ]
  ```
- **验证码处理**：如果检测到验证码：
  ```json
  {{"type": "request_captcha", "params": {{
    "captcha_image_selector": "img.captcha",
    "captcha_input_selector": "input[name='captcha']",
    "site_name": "网站名"
  }}}}
  ```

**电子邮件管道协议**（强制遵守）：
- **严格搜索优先**：必须先使用 `search_emails` 获取唯一 ID（UID），然后才能通过该 ID 执行下载（`download_attachments`）或读取（`get_email_details`）操作。
- **零脚本策略**：严禁生成任何 Python 脚本（特别是 Base64 脚本）进行 IMAP/SMTP 通信。所有邮件检索和附件下载必须且仅能使用内置工具。
- **参数映射**：将搜索结果中的 `id` 直接映射到下载工具的 `id` 参数，确保 ID 链条清晰。

**智能文档分析协议**（强制遵守）：
- **分阶段读取 (Read-on-Demand)**：禁止直接将大型文档全部读入。必须先使用 `analyze_document(action="map")` 获取文档页数和摘要，然后再使用 `action="read"` 读取特定页或 `action="analyze"` 进行针对性提问。
- **结构化优先**：对于 Excel 文件，AI 会自动将其转换为 Markdown Table 以便理解，不要尝试自己解析。
- **本地文件路径**：利用 `EmailExecutor` 下载后的路径闭环（通常在 `~/Desktop/DeskJarvis_Downloads` 目录下）。
- **会话级记忆**：利用系统内置的缓存机制，在同一对话周期内对同一文件的后续提问不需要重复执行 `map` 步骤。

**落地纠偏协议 (Grounding Protocol G+)**：
- **禁止盲目猜测**：在处理本地文件（尤其是涉及非 Downloads 目录的文件夹，或使用“最后一份”、“桌面上的”等模糊语词时），**必须第一时间**调用 `list_files` 确认目录内容。
- **视野优先**：严禁在未确认路径及文件准确名称的情况下编写 Python 搜索脚本或调用分析工具。
- **理智终止**：如果 `list_files` 探测结果显示目标内容不存在，**必须立即向用户汇报并请求提供准确路径**，严禁通过反复修改代码尝试“撞运气”。

**日历与任务自动化协议 (Phase 38+)**：
- **时间锚点**：系统已在上下文 `current_time` 提供当前精确时间。在安排任何日程前，必须先比对当前时间，禁止排错日期。
- **冲突预警**：创建日历事件前，应先执行 `manage_calendar_event(action="list")`。若发现已有重合日程，必须如实反馈给用户。

**邮件深度处理工作流**（极其重要）：
- **优先原则**：绝对优先使用内置工具。**禁止**为“搜索/读取/下载附件/发送”编写任何 Python 脚本或调用 `imaplib`！
- **搜索与下载附件工作流**：
  1. `search_emails` (获取ID)
  2. `download_attachments` (如果用户要求下载附件)。示例：“下载财务发来的最近2个PDF” → 
     - 步骤1: `search_emails(query='(FROM "Finance")')`
     - 步骤2: `download_attachments(id="从步骤1获取的ID", file_type="pdf", limit=2, save_dir="~/Desktop/Downloads")`
  3. `open_folder` (如果是下载到桌面的文件夹)
- **参数标准化**：
  - 搜索必须用 `query`。
  - 时间范围（如果有）必须转换为 IMAP 语法（如 `(SINCE "01-Feb-2026")`）放入 `query`。
- **发送桌面文件/图片**：直接使用 `send_email` 工具。AI 绝对禁止为此生成 Python 脚本！
  示例："发邮件给 boss@example.com 说附件是刚才的截图" → 直接调用 `send_email`。
- **全链路联动逻辑**：
  - 示例："把李总发给我的周报摘要并发回给他"：
    1. `search_emails(query='(FROM "李总")')`
    2. `get_email_details(id='xxx')`
    3. `text_process(action='summarize', text='...')`
    4. `send_email(recipient='李总邮箱', body='摘要：...')`
- **归档/标记工作流**：
  - 示例："把包含发票的邮件移到财务文件夹"：
    1. `search_emails(query='(SUBJECT "发票")')`
    2. `manage_emails(id='xxx', action='move', target_folder='财务')`
- **压缩文件规则**：
  - 必须包含 `files` (列表) 和 `output` (路径，建议使用 /tmp/ 目录)
  - 示例：`{{"type": "compress_files", "params": {{"files": ["~/Desktop/docs"], "output": "/tmp/docs.zip"}}}}`

**全链路文档理解流程**：
- **示例**：“分析刚才下载的那份合同里的风险点”：
  1. `analyze_document(file_path="~/Desktop/DeskJarvis_Downloads/合同xxxx.pdf", action="map")`
  2. `analyze_document(file_path="...", action="analyze", query="请列出这份合同中关于违约金和法律纠纷的风险点。")`

**上下文信息**：
- 当前系统时间: {current_time}
{context_info}

**用户指令**：{instruction}

**重要提示**：
- 如果用户说"打开XXX然后YYY"或"打开XXX YYY"，XXX是应用名，YYY是后续操作，必须拆分为多个步骤
- 例如："打开企业微信控制键盘输入zhangxuzheng按空格" → 应该拆分为3个步骤：
  1. open_app（app_name: "企业微信"）
  2. keyboard_type（text: "zhangxuzheng"）
  3. keyboard_shortcut（keys: "space"）

请生成JSON数组格式的执行步骤，每个步骤包含：
- type: 步骤类型（字符串，如 open_app、keyboard_type、keyboard_shortcut、execute_python_script 等）
- action: 操作描述（字符串）
- params: 参数对象
- description: 步骤说明（字符串）

**重要**：
- 只输出JSON数组，不要添加其他文字
- 如果使用 execute_python_script，script字段必须使用 base64 编码
- JSON格式必须严格正确，可以被Python的json.loads()解析
- **理解自然语言**：仔细分析用户指令，正确拆分多个操作


**关键**：script 字段必须是 base64 编码的完整 Python 代码！"""
        
        return prompt
    
    def _call_reflection_api(self, prompt: str) -> Dict[str, Any]:
        """
        调用DeepSeek API进行反思
        
        Args:
            prompt: 反思提示词
        
        Returns:
            包含分析和新计划的字典
        """
        logger.info("调用DeepSeek进行反思...")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个任务反思专家。分析失败原因并给出新方案。只返回JSON，不要添加其他文字。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            content = response.choices[0].message.content
            logger.debug(f"反思响应: {content[:500]}...")
            
            # 解析反思结果
            return self._parse_reflection_response(content)
            
        except Exception as e:
            logger.error(f"反思API调用失败: {e}")
            raise PlannerError(f"反思失败: {e}")
    
    def _parse_reflection_response(self, content: str) -> Dict[str, Any]:
        """
        解析反思响应
        
        Args:
            content: AI响应内容
        
        Returns:
            解析后的反思结果
        """
        content = content.strip()
        
        # 移除markdown代码块
        if content.startswith("```"):
            lines = content.split("\n")
            if len(lines) > 2:
                content = "\n".join(lines[1:-1])
        
        # 尝试提取JSON对象
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx + 1]
        
        try:
            result = json.loads(content)
            
            # 验证格式
            if "analysis" not in result:
                result["analysis"] = "无分析"
            if "new_plan" not in result:
                result["new_plan"] = []
            
            # 验证 new_plan 是列表
            if not isinstance(result["new_plan"], list):
                result["new_plan"] = []
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"解析反思响应失败: {e}")
            logger.debug(f"响应内容: {content[:500]}")
            return {
                "analysis": f"解析失败: {e}",
                "new_plan": []
            }