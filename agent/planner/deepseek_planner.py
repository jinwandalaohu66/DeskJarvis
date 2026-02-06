"""
DeepSeek规划器：使用DeepSeek API规划任务

遵循 docs/ARCHITECTURE.md 中的Planner模块规范
"""

from typing import List, Dict, Any, Optional
import logging
import json
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
            prompt = self._build_prompt(user_instruction, context)
            
            logger.info("开始规划任务...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个AI任务规划助手。请理解用户的自然语言指令，生成可执行的任务步骤。只返回JSON数组，不要添加其他文字。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            content = response.choices[0].message.content
            logger.debug(f"AI响应: {content[:500]}...")
            
            steps = self._parse_response(content)
            logger.info(f"规划完成，共 {len(steps)} 个步骤")
            
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
                        logger.info(f"✅ 已自动添加 save_path: ~/Desktop/screenshot.png")
            
            return steps
            
        except Exception as e:
            logger.error(f"规划任务失败: {e}", exc_info=True)
            raise PlannerError(f"规划任务失败: {e}")

    
    def _build_prompt(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建规划提示词"""
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
                context_info += f"用户经常执行类似任务，建议使用之前成功的步骤模式：\n"
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
        
        prompt = f"""你是一个AI任务规划助手。请理解用户的自然语言指令，生成可执行的任务步骤。

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
- open_app: 打开应用 → params: {{"app_name": "应用名"}}
- close_app: 关闭应用 → params: {{"app_name": "应用名"}}
- browser_navigate: 导航网页 → params: {{"url": "网址"}}
- browser_click: 点击元素 → params: {{"selector": "选择器"}}
- browser_fill: 填写表单 → params: {{"selector": "选择器", "value": "值"}}
- browser_screenshot: 截图网页 → params: {{"save_path": "保存路径"}}
- download_file: 下载文件 → params: {{"url": "下载链接", "save_path": "保存路径"}}
- execute_python_script: Python脚本 → params: {{"script": "base64编码的脚本", "reason": "原因", "safety": "安全说明"}}

**登录和验证码工具**（遇到需要登录或验证码的网站时使用）：
- request_login: 请求用户登录 → params: {{"site_name": "网站名", "username_selector": "用户名输入框选择器", "password_selector": "密码输入框选择器", "submit_selector": "提交按钮选择器（可选）"}}
- request_captcha: 请求验证码 → params: {{"site_name": "网站名", "captcha_image_selector": "验证码图片选择器", "captcha_input_selector": "验证码输入框选择器"}}

**系统控制工具**：
- set_volume: 设置音量 → params: {{"level": 0-100}} 或 {{"action": "mute/unmute/up/down"}}
- set_brightness: 设置屏幕亮度 → params: {{"level": 0.0-1.0}} 或 {{"action": "up/down/max/min"}}（优先使用此工具！）
- send_notification: 发送通知 → params: {{"title": "标题", "message": "内容"}}
- speak: 语音播报 → params: {{"text": "要播报的内容"}}
- clipboard_read: 读取剪贴板 → params: {{}}
- clipboard_write: 写入剪贴板 → params: {{"content": "内容"}}
- keyboard_type: 键盘输入 → params: {{"text": "要输入的文本"}}
- keyboard_shortcut: 快捷键 → params: {{"keys": "command+c"}}
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
3. **不能自创工具名**，只能用上面列出的
4. 如果任务无法用上面工具完成，就用 execute_python_script
5. **音量控制必须用 set_volume 工具**，不要用脚本！
6. **亮度控制必须用 set_brightness 工具**，不要用脚本！
7. **系统通知必须用 send_notification 工具**，不要用脚本！

**Python脚本执行**（复杂任务或工具无法满足时使用）：
- script: Python代码，**必须使用 base64 编码**（避免JSON转义问题）
- reason: 为什么使用脚本而不是工具
- safety: 安全检查说明
- **脚本要求**：
  * 安全：文件操作限制在用户主目录或沙盒目录（~/Desktop, ~/Downloads, ~/.deskjarvis/sandbox）
  * 禁止危险命令：rm -rf /, sudo, chmod 777 等
  * 必须使用 try-except 包裹可能失败的操作
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
  * **Word文档处理（.docx）**：
    - **必须使用 python-docx 库**：`from docx import Document`
    - **绝对禁止用 open() 读取 .docx 文件**！.docx 是 ZIP 压缩包，不是文本文件，用 open() 会报 UnicodeDecodeError
    - 正确方式：`doc = Document(file_path)` → 遍历 `doc.paragraphs` 和 `doc.tables`
    - **替换文字的正确方法（极其重要！）**：
      * Word 文档中，一段文字可能被拆分成多个 run（格式块）
      * **错误方式**：`para.text = para.text.replace(old, new)` - 这会丢失格式且可能替换失败
      * **正确方式**：遍历每个 run，在 run.text 中替换
      ```python
      for para in doc.paragraphs:
          if old_text in para.text:  # 先检查整段是否包含目标文字
              for run in para.runs:
                  if old_text in run.text:  # 再在 run 中替换
                      run.text = run.text.replace(old_text, new_text)
                      count += 1
      ```
      * 同样处理表格：`for table in doc.tables: for row in table.rows: for cell in row.cells: ...`
  * **文件路径**：脚本中应该**直接使用文件路径**（硬编码），不要从环境变量读取。使用 `os.path.expanduser()` 或 `pathlib.Path.home()` 处理 `~` 符号。例如：`file_path = os.path.expanduser("~/Desktop/file.docx")`
  * **重要**：文件路径**不要进行 URL 编码**（不要使用 `urllib.parse.quote()` 或类似函数），直接使用原始的中文文件名。例如：`"~/Desktop/强制执行申请书.docx"` 而不是 `"~/Desktop/%E5%BC%BA%E5%88%B6%E6%89%A7%E8%A1%8C%E7%94%B3%E8%AF%B7%E4%B9%A6.docx"`
  * **文件名必须准确**：必须使用用户指令中提到的**完整准确的文件名**，不要随意更改、替换或编码文件名。
    - **重要**：文件名必须**逐字逐句完全匹配**用户指令中的文件名，包括中文字符、英文、数字、扩展名等。
    - **示例1**：如果用户说"强制执行申请书.docx"，脚本中必须使用 `"强制执行申请书.docx"`，**绝对不要**改成 `"大取同学名称.docx"`、`"求正放接探底作品.docx"` 或其他任何名称。
    - **示例2**：如果用户说"总结.txt"，必须使用 `"总结.txt"`，**绝对不要**改成 `"连排.txt"`、`"输克.txt"` 或其他任何名称。
    - **检查方法**：生成脚本后，检查脚本中的文件名是否与用户指令中的文件名完全一致，如果不一致，必须修正。
  * **Python语法（极其重要！！！）**：
    - **绝对禁止 f-string**：不要用 f"xxx" 格式！
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
  * **Matplotlib 图表绑定用法**：
    - 使用 `plt.pie()` 画饼图，使用 `plt.bar()` 画柱状图
    - 饼图颜色使用列表：`colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8']`
    - **不要使用** `plt.cm.set3` 或 `plt.cm.Set3`，使用上面的颜色列表
    - 中文显示：`plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']`
    - 保存图表：`plt.savefig(路径, dpi=150, bbox_inches='tight', facecolor='white')`
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
  * 如果用户说"保存到桌面"或"保存桌面"：必须传递 `"save_path": "~/Desktop/screenshot.png"` 或 `"save_path": "~/Desktop"`
  * 如果用户只说"截图桌面"但没有说保存位置：可以省略 save_path（使用默认位置）
- **只执行用户明确要求的操作**：如果用户说"截图桌面"，就只截图，不要删除文件、移动文件或其他操作
- **准确理解用户意图**：如果用户说"保存到桌面"，必须传递 save_path 参数

**上下文理解**：
{context_info}

**用户指令**：{instruction}

请生成JSON数组格式的执行步骤，每个步骤包含：
- type: 步骤类型（字符串）
- action: 操作描述（字符串）
- params: 参数对象
- description: 步骤说明（字符串）

**重要**：
- 只输出JSON数组，不要添加其他文字
- 如果使用 execute_python_script，script字段必须使用 base64 编码
- JSON格式必须严格正确，可以被Python的json.loads()解析

示例（Word文档替换 - 正确的 runs 遍历方式）：
[
  {{
    "type": "execute_python_script",
    "action": "替换Word文档中的文字",
    "params": {{
      "script": "aW1wb3J0IGpzb24KaW1wb3J0IG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAoKdHJ5OgogICAgZnJvbSBkb2N4IGltcG9ydCBEb2N1bWVudApleGNlcHQgSW1wb3J0RXJyb3I6CiAgICBwcmludChqc29uLmR1bXBzKHsic3VjY2VzcyI6IEZhbHNlLCAibWVzc2FnZSI6ICLpnIDopoHlronoo4UgcHl0aG9uLWRvY3g6IHBpcCBpbnN0YWxsIHB5dGhvbi1kb2N4In0pKQogICAgZXhpdCgwKQoKIyDmkJzntKLmlofku7YKZGVza3RvcCA9IFBhdGguaG9tZSgpIC8gIkRlc2t0b3AiCmtleXdvcmQgPSAi5by65Yi25omn6KGMIgpvbGRfdGV4dCA9ICLlvKDmlofnpoQiCm5ld190ZXh0ID0gIuW8oOaXreaUvyIKCm1hdGNoZXMgPSBbZiBmb3IgZiBpbiBkZXNrdG9wLml0ZXJkaXIoKSBpZiBmLmlzX2ZpbGUoKSBhbmQga2V5d29yZCBpbiBmLm5hbWUgYW5kIGYuc3VmZml4ID09ICIuZG9jeCJdCgppZiBub3QgbWF0Y2hlczoKICAgIHByaW50KGpzb24uZHVtcHMoeyJzdWNjZXNzIjogRmFsc2UsICJtZXNzYWdlIjogIuacquaJvuWIsOWMheWQqyciICsga2V5d29yZCArICIn55qEV29yZOaWh+ahoyJ9KSkKICAgIGV4aXQoMCkKCmZpbGVfcGF0aCA9IG1hdGNoZXNbMF0KZG9jID0gRG9jdW1lbnQoZmlsZV9wYXRoKQpjb3VudCA9IDAKCiMg5q2j56Gu55qE5pu/5o2i5pa55rOV77ya6YGN5Y6GIHJ1bnMKZm9yIHBhcmEgaW4gZG9jLnBhcmFncmFwaHM6CiAgICBpZiBvbGRfdGV4dCBpbiBwYXJhLnRleHQ6CiAgICAgICAgZm9yIHJ1biBpbiBwYXJhLnJ1bnM6CiAgICAgICAgICAgIGlmIG9sZF90ZXh0IGluIHJ1bi50ZXh0OgogICAgICAgICAgICAgICAgcnVuLnRleHQgPSBydW4udGV4dC5yZXBsYWNlKG9sZF90ZXh0LCBuZXdfdGV4dCkKICAgICAgICAgICAgICAgIGNvdW50ICs9IDEKCiMg5Lmf5qOA5p+l6KGo5qC8CmZvciB0YWJsZSBpbiBkb2MudGFibGVzOgogICAgZm9yIHJvdyBpbiB0YWJsZS5yb3dzOgogICAgICAgIGZvciBjZWxsIGluIHJvdy5jZWxsczoKICAgICAgICAgICAgaWYgb2xkX3RleHQgaW4gY2VsbC50ZXh0OgogICAgICAgICAgICAgICAgZm9yIHBhcmEgaW4gY2VsbC5wYXJhZ3JhcGhzOgogICAgICAgICAgICAgICAgICAgIGZvciBydW4gaW4gcGFyYS5ydW5zOgogICAgICAgICAgICAgICAgICAgICAgICBpZiBvbGRfdGV4dCBpbiBydW4udGV4dDoKICAgICAgICAgICAgICAgICAgICAgICAgICAgIHJ1bi50ZXh0ID0gcnVuLnRleHQucmVwbGFjZShvbGRfdGV4dCwgbmV3X3RleHQpCiAgICAgICAgICAgICAgICAgICAgICAgICAgICBjb3VudCArPSAxCgpkb2Muc2F2ZShmaWxlX3BhdGgpCnByaW50KGpzb24uZHVtcHMoeyJzdWNjZXNzIjogVHJ1ZSwgIm1lc3NhZ2UiOiAi5pu/5o2i5a6M5oiQ77yM5YWx5pu/5o2iICIgKyBzdHIoY291bnQpICsgIiDlpIQifSkpCg==",
      "reason": "Word文档替换需要使用python-docx库，必须遍历runs",
      "safety": "只操作桌面文件，使用try-except"
    }},
    "description": "搜索并替换Word文档中的文字（遍历runs方式）"
  }}
]

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