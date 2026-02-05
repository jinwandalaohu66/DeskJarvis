"""
OpenAI规划器：使用OpenAI API（ChatGPT）规划任务

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


class OpenAIPlanner(BasePlanner):
    """
    OpenAI规划器：调用OpenAI API规划任务
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
            self.client = OpenAI(api_key=api_key)
            self.model = config.model
            logger.info(f"OpenAI规划器已初始化，模型: {self.model}")
        except Exception as e:
            raise PlannerError(f"初始化OpenAI客户端失败: {e}")
    
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

**核心原则**：
- 理解用户的真实意图，而不是匹配关键词
- 思考如何完成任务，而不是选择工具
- 简单任务用工具，复杂任务用脚本
- 以结果为导向，只要能达到目标，用什么方法都可以

**你的能力**：
1. **文件操作**：读取、写入、创建、删除、重命名、移动、复制文件
2. **浏览器操作**：导航网页、点击、填写表单、下载文件、截图网页
3. **系统操作**：桌面截图、打开/关闭应用、打开文件/文件夹
4. **脚本执行**：生成并执行Python脚本完成复杂任务

**可用工具**（简单任务优先使用）：
- file_read: 读取文件内容（支持.txt, .docx等）
- file_write: 写入文件内容（支持覆盖/追加模式）
- file_create: 创建新文件
- file_rename: 重命名文件
- file_move: 移动文件（可移动到回收站）。target_dir 参数支持完整路径（如 "~/Desktop/文件夹名"）或文件夹名（如 "8888"），系统会自动智能搜索文件夹。
- file_copy: 复制文件
- file_batch_rename: 批量重命名文件夹内的文件
- file_batch_copy: 批量复制文件夹内的文件
- file_batch_organize: 批量整理文件（按关键词、类型、时间分类）
- browser_navigate: 导航到网页URL
- browser_click: 点击页面元素
- browser_fill: 填写表单
- browser_wait: 等待页面加载
- browser_screenshot: 截图网页
- download_file: 下载文件（通过点击下载链接）
- screenshot_desktop: 截图整个桌面
- open_file: 用默认应用打开文件（只在用户明确说"打开文件"时使用）
- open_folder: 在文件管理器中打开文件夹（只在用户明确说"打开文件夹"时使用）
- open_app: 打开应用程序
- close_app: 关闭应用程序
- execute_python_script: 执行Python脚本（用于复杂任务或工具无法满足的需求）

**Python脚本执行**（复杂任务或工具无法满足时使用）：
- script: Python代码，**必须使用 base64 编码**（避免JSON转义问题）
- reason: 为什么使用脚本而不是工具
- safety: 安全检查说明
- **脚本要求**：
  * 安全：文件操作限制在用户主目录或沙盒目录（~/Desktop, ~/Downloads, ~/.deskjarvis/sandbox）
  * 禁止危险命令：rm -rf /, sudo, chmod 777 等
  * 必须使用 try-except 包裹可能失败的操作
  * 输出格式：`print(json.dumps({{"success": True/False, "message": "...", "data": {{...}}}}))`
  * Python布尔值：使用 `True`/`False`（首字母大写），不是 `true`/`false`
  * 浏览器操作：使用 `playwright.sync_api` 模块
  * 文件操作：使用 `os`, `shutil`, `pathlib` 模块
  * **Word文档处理**：使用 `python-docx` 库，导入方式：`from docx import Document`（**不要使用** `import docxplr` 或其他库名）
  * **文件路径**：脚本中应该**直接使用文件路径**（硬编码），不要从环境变量读取。使用 `os.path.expanduser()` 或 `pathlib.Path.home()` 处理 `~` 符号。例如：`file_path = os.path.expanduser("~/Desktop/file.docx")`
  * **重要**：文件路径**不要进行 URL 编码**（不要使用 `urllib.parse.quote()` 或类似函数），直接使用原始的中文文件名。例如：`"~/Desktop/强制执行申请书.docx"` 而不是 `"~/Desktop/%E5%BC%BA%E5%88%B6%E6%89%A7%E8%A1%8C%E7%94%B3%E8%AF%B7%E4%B9%A6.docx"`
  * **文件名必须准确**：必须使用用户指令中提到的**完整准确的文件名**，不要随意更改、替换或编码文件名。
    - **重要**：文件名必须**逐字逐句完全匹配**用户指令中的文件名，包括中文字符、英文、数字、扩展名等。
    - **示例1**：如果用户说"强制执行申请书.docx"，脚本中必须使用 `"强制执行申请书.docx"`，**绝对不要**改成 `"大取同学名称.docx"`、`"求正放接探底作品.docx"` 或其他任何名称。
    - **示例2**：如果用户说"总结.txt"，必须使用 `"总结.txt"`，**绝对不要**改成 `"连排.txt"`、`"输克.txt"` 或其他任何名称。
    - **检查方法**：生成脚本后，检查脚本中的文件名是否与用户指令中的文件名完全一致，如果不一致，必须修正。
  * **Python语法**：
    - f-string 的正确语法是 f\"...\" 或 f\"\"\"...\"\"\"（f 和引号之间不能有空格），**必须使用双引号**，不要写成 f'\"\"\" 或 f'\"...\"（单引号+双引号混用）
    - **重要**：f-string 的三引号形式必须是 f\"\"\"...\"\"\"（双引号），**绝对不要**写成 f'\"\"\"（单引号+三引号），这会导致语法错误
    - 多行字符串使用 f\"\"\"...\"\"\" 或 f\"...\" + \"\\n\"，确保引号正确闭合
    - 字符串拼接使用 + 时要注意格式，确保引号匹配
    - **重要**：所有字符串必须正确闭合，不要出现未闭合的引号。例如：summary = f\"\"\"[Document Summary]...\"\"\" 而不是 summary = f\"\"[Document Summary]... 或 summary = f'\"\"\"[Document Summary]...
    - **错误消息必须简洁**：错误消息应该简短明了，如 \"文件不存在\" 或 \"文件路径错误\"，不要重复文本或生成超长字符串
    - **字符串闭合检查**：每个字符串字面量（用引号包围的文本）都必须有开始和结束引号，确保引号数量匹配
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

示例：
[
  {{
    "type": "file_read",
    "action": "读取文件",
    "params": {{"file_path": "~/Desktop/test.txt"}},
    "description": "读取桌面上的test.txt文件"
  }},
  {{
    "type": "execute_python_script",
    "action": "处理文件内容",
    "params": {{
      "script": "aW1wb3J0IGpzb24KcHJpbnQoanNvbi5kdW1wcyh7InN1Y2Nlc3MiOiBUcnVlLCAibWVzc2FnZSI6ICJjb21wbGV0ZSJ9KSk=",
      "reason": "需要处理文件内容并生成总结",
      "safety": "文件操作限制在用户主目录，使用try-except包裹"
    }},
    "description": "执行Python脚本处理文件内容"
  }}
]"""
        
        return prompt
