"""
Claude AI规划器 - 简化重构版

核心理念：
- AI 自主思考，写代码解决问题
- 不再硬编码规则，让 AI 自己决定
- 只提供必要的能力描述和安全约束

遵循 docs/ARCHITECTURE.md 中的Planner模块规范
"""

import anthropic
import logging
import json
import base64
from typing import List, Dict, Any, Optional
from pathlib import Path

from agent.planner.base_planner import BasePlanner
from agent.tools.config import Config
from agent.tools.exceptions import PlannerError

logger = logging.getLogger(__name__)


class ClaudePlanner(BasePlanner):
    """
    Claude AI规划器 - 简化重构版
    
    核心改进：
    - 简化 prompt，不再硬编码工具规则
    - 让 AI 自主决定用工具还是写代码
    - 添加反思能力
    """
    
    def __init__(self, config: Config):
        """
        初始化Claude规划器
        
        Args:
            config: 配置对象
        """
        super().__init__(config)
        self.client = anthropic.Anthropic(api_key=config.api_key)
        self.model = config.model or "claude-sonnet-4-20250514"
        logger.info(f"Claude规划器已初始化，使用模型: {self.model}")
    
    def plan(
        self,
        user_instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        规划任务：将用户指令转换为可执行步骤
        
        Args:
            user_instruction: 用户自然语言指令
            context: 上下文信息
        
        Returns:
            任务步骤列表
        """
        logger.info(f"开始规划任务: {user_instruction}")
        
        try:
            # 构建提示词
            prompt = self._build_prompt(user_instruction, context)
            
            # 调用Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            logger.debug(f"Claude响应: {content[:500]}...")
            
            # 解析响应
            steps = self._parse_response(content)
            logger.info(f"规划完成，共 {len(steps)} 个步骤")
            
            return steps
            
        except anthropic.APIError as e:
            logger.error(f"Claude API调用失败: {e}")
            raise PlannerError(f"规划失败: Claude API错误 - {e}")
        except Exception as e:
            logger.error(f"规划失败: {e}", exc_info=True)
            raise PlannerError(f"规划失败: {e}")
    
    def _build_prompt(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建规划提示词 - 简化版
        
        核心理念：
        - 简洁清晰，不硬编码规则
        - 告诉 AI 它有什么能力
        - 让 AI 自己决定怎么做
        
        Args:
            instruction: 用户指令
            context: 上下文信息
        
        Returns:
            提示词
        """
        # 获取用户主目录
        home_dir = str(Path.home())
        
        # 构建上下文信息（增强版：帮助AI理解指代词）
        context_str = ""
        if context:
            context_parts = []
            
            # 0. 处理记忆上下文（AI对用户的长期记忆）
            memory_context = context.get("memory_context", "")
            if memory_context:
                context_parts.append(f"""### AI记忆（用户偏好和习惯）
{memory_context}

**重要**: 请根据这些记忆信息，更好地理解用户的习惯和偏好，生成符合用户期望的执行计划。""")
            
            # 0.5 处理工作流建议
            workflow_suggestion = context.get("workflow_suggestion")
            if workflow_suggestion:
                pattern = workflow_suggestion.get("pattern", {})
                action_seq = pattern.get("action_sequence", [])
                if action_seq:
                    context_parts.append(f"""### 工作流建议
用户经常执行类似任务，建议参考之前成功的步骤模式：
步骤序列：{' → '.join(action_seq)}
成功率：{pattern.get('success_rate', 0) * 100:.0f}%""")
            
            # 1. 处理最近创建/操作的文件
            last_file = context.get("last_created_file")
            created_files = context.get("created_files", [])
            
            if last_file:
                context_parts.append(f"""### 最近操作的文件
**路径**: `{last_file}`
**重要**: 当用户说"这个文件"、"那个文件"、"刚才的文件"、"这张图片"、"那张截图"等指代词时，
指的就是这个文件：`{last_file}`""")
            
            if created_files and len(created_files) > 1:
                files_list = "\n".join([f"- `{f}`" for f in created_files[-5:]])  # 只显示最近5个
                context_parts.append(f"""### 本次会话创建的所有文件
{files_list}""")
            
            # 2. 处理用户附加的路径
            attached_path = context.get("attached_path")
            if attached_path:
                context_parts.append(f"""### 用户指定的目标路径
用户拖拽或选择了这个路径：`{attached_path}`
请在任务中使用这个路径。""")
            
            # 3. 处理聊天历史（让AI理解对话上下文）
            chat_history = context.get("chat_history", [])
            if chat_history:
                history_parts = []
                for msg in chat_history[-5:]:  # 只保留最近5条
                    role = "用户" if msg.get("role") == "user" else "AI"
                    content = msg.get("content", "")
                    # 截断过长的内容
                    if len(content) > 200:
                        content = content[:200] + "..."
                    history_parts.append(f"**{role}**: {content}")
                
                if history_parts:
                    context_parts.append(f"""### 对话历史
{chr(10).join(history_parts)}

**重要**: 请根据对话历史理解用户的意图。如果用户提到"这个"、"那个"、"它"等指代词，
请结合对话历史和上面的"最近操作的文件"来确定具体指的是什么。""")
            
            if context_parts:
                context_str = "\n## 上下文信息\n\n" + "\n\n".join(context_parts) + "\n"
        
        prompt = f"""你是 DeskJarvis，一个智能桌面助手。请用中文思考和输出。

## 你的能力

### 1. 浏览器操作
- browser_navigate: 访问网页，params: {{url: "..."}}
- browser_click: 点击元素，params: {{selector: "..."}} 或 {{text: "..."}}
- browser_input: 输入文本，params: {{selector: "...", text: "..."}}
- browser_screenshot: 截取当前页面，params: {{}}
- download_file: 下载文件，params: {{url: "...", save_path: "..."}}
- request_login: 请求用户登录（弹出登录对话框），params: {{site_name: "网站名", username_selector: "用户名输入框选择器", password_selector: "密码输入框选择器", submit_selector: "提交按钮选择器（可选）"}}
- request_captcha: 请求验证码（截取验证码图片并弹出输入框），params: {{site_name: "网站名", captcha_image_selector: "验证码图片选择器", captcha_input_selector: "验证码输入框选择器"}}

### 2. 系统操作
- screenshot_desktop: 截取桌面，params: {{save_path: "保存路径（可选）"}}
- open_folder: 打开文件夹，params: {{folder_path: "..."}}
- open_file: 打开文件，params: {{file_path: "..."}}
- open_app: 打开应用，params: {{app_name: "..."}}
- close_app: 关闭应用，params: {{app_name: "..."}}

### 2.5 文件操作工具（简单操作可用，复杂操作建议用脚本）
- file_read: 读取文件，params: {{file_path: "文件路径"}}
- file_write: 写入文件，params: {{file_path: "文件路径", content: "内容"}}
- file_create: 创建文件，params: {{file_path: "文件路径", content: "内容"}}
- file_rename: 重命名文件，params: {{file_path: "原文件路径", new_name: "新文件名"}}
- file_move: 移动文件，params: {{file_path: "原路径", destination: "目标路径"}}
- file_copy: 复制文件，params: {{file_path: "原路径", destination: "目标路径"}}
- file_delete: 删除文件，params: {{file_path: "文件路径"}}

### 2.6 系统控制工具
- set_volume: 设置音量，params: {{level: 0-100}} 或 {{action: "mute/unmute/up/down"}}
- set_brightness: 设置屏幕亮度，params: {{level: 0.0-1.0}} 或 {{action: "up/down/max/min"}}
- send_notification: 发送系统通知，params: {{title: "标题", message: "内容"}}
- speak: 语音播报，params: {{text: "要播报的内容"}}
- clipboard_read: 读取剪贴板，params: {{}}
- clipboard_write: 写入剪贴板，params: {{content: "内容"}}
- keyboard_type: 键盘输入，params: {{text: "要输入的文本"}}
- keyboard_shortcut: 快捷键，params: {{keys: "command+c"}}
- mouse_click: 鼠标点击，params: {{x: 100, y: 200}}
- window_minimize: 最小化窗口，params: {{app_name: "应用名（可选）"}}
- window_maximize: 最大化窗口，params: {{app_name: "应用名（可选）"}}

**系统信息和图片处理**：
- get_system_info: 获取系统信息，params: {{info_type: "battery/disk/memory/apps/network/all", save_path: "~/Desktop/系统报告.md（可选，指定后自动保存）"}}
  **重要：查询系统信息必须使用这个工具，不要自己写脚本！如果用户要求保存，直接在 save_path 中指定路径！**
- image_process: 图片处理，params: {{image_path: "图片路径", action: "compress/resize/convert/info", width: 800, height: 600, format: "jpg/png/webp", quality: 80}}

**定时提醒**：
- set_reminder: 设置提醒，params: {{message: "提醒内容", delay: "5分钟/1小时/30秒", repeat: "daily/hourly（可选）"}}
- list_reminders: 列出提醒，params: {{}}
- cancel_reminder: 取消提醒，params: {{reminder_id: "提醒ID"}}

**工作流管理**：
- create_workflow: 创建工作流，params: {{name: "工作流名", commands: ["命令1", "命令2"], description: "描述"}}
- list_workflows: 列出工作流，params: {{}}
- delete_workflow: 删除工作流，params: {{name: "工作流名"}}

**任务历史**：
- get_task_history: 获取历史，params: {{limit: 20}}
- search_history: 搜索历史，params: {{keyword: "关键词"}}
- add_favorite: 添加收藏，params: {{instruction: "指令内容", name: "收藏名（可选）"}}
- list_favorites: 列出收藏，params: {{}}
- remove_favorite: 移除收藏，params: {{favorite_id: "收藏ID"}}

**文本AI处理**：
- text_process: AI文本处理，params: {{text: "要处理的文本", action: "translate/summarize/polish/expand/fix_grammar", target_lang: "目标语言（翻译时使用）"}}

### 3. Python 脚本（推荐用于文件操作和批量操作）
使用 execute_python_script 执行自定义 Python 代码。

execute_python_script 的 params:
- script: base64 编码的 Python 脚本（必须）
- reason: 为什么需要脚本（必须）
- safety: 安全说明（必须）

**脚本必须遵循的规范**：
1. 必须是完整可执行的 Python 代码
2. 输出格式必须是：print(json.dumps({{"success": True, "message": "xxx"}})) 或 print(json.dumps({{"success": False, "message": "xxx"}}))
3. **禁止使用 f-string**！所有字符串拼接必须用 + 号
4. **语法检查（极其重要）**：
   - 每个引号必须配对闭合
   - 每个括号必须配对闭合
   - **每个 try 必须有 except**（最常见错误！）
   - 字符串拼接格式: "文字" + str(变量) + "文字"
   - **平台检测**：`import sys; sys.platform == "darwin"/"win32"/"linux"`
5. 注释使用中文，变量名使用英文
6. 用户主目录: {home_dir}
7. **错误处理**：所有操作必须在 try-except 中，except 中输出 JSON 格式的错误信息
8. **HTTP 请求（重要！）**：
   - **必须使用 requests 库**，不要用 urllib！urllib 不会自动解压 gzip！
   - `import requests` → `response = requests.get(url)`
   - 下载二进制文件用 `response.content`，下载文本用 `response.text`
   - 示例：
     ```python
     import requests
     response = requests.get(url)
     html = response.text  # 文本
     with open(path, "wb") as f:
         f.write(response.content)  # 二进制文件
     ```

**脚本示例（删除文件）**：
```python
import os
import json
import glob
from pathlib import Path

# 目标目录
desktop = Path.home() / "Desktop"
pattern = str(desktop / "*screenshot*.png")

# 查找匹配文件
files = glob.glob(pattern)
deleted = []
errors = []

for f in files:
    try:
        os.remove(f)
        deleted.append(os.path.basename(f))
    except Exception as e:
        errors.append(str(e))

# 输出结果（必须是有效JSON）
if deleted:
    result = {{"success": True, "message": "成功删除 " + str(len(deleted)) + " 个文件", "data": {{"deleted": deleted}}}}
else:
    result = {{"success": True, "message": "没有找到匹配的文件", "data": {{}}}}

print(json.dumps(result, ensure_ascii=False))
```

**脚本示例（重命名文件）**：
```python
import os
import json
from pathlib import Path

# 目标目录
folder = Path.home() / "Desktop" / "images"

# 获取所有图片并按大小排序
images = [(f, f.stat().st_size) for f in folder.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg"]]
images.sort(key=lambda x: x[1])

# 重命名
renamed = []
for i, (img, size) in enumerate(images, 1):
    new_name = folder / (str(i) + img.suffix)
    os.rename(img, new_name)
    renamed.append({{"old": img.name, "new": new_name.name}})

result = {{"success": True, "message": "成功重命名 " + str(len(renamed)) + " 个文件", "data": {{"renamed": renamed}}}}
print(json.dumps(result, ensure_ascii=False))
```

**重要：message 字符串必须使用字符串拼接（"xxx " + str(n) + " yyy"），不要使用 f-string！**

**脚本示例（搜索并操作文件 - 当用户说的文件名可能不完整时）**：
      ```python
      import os
import json
from pathlib import Path

# 用户说"强制执行申请书"，可能是部分文件名，需要搜索
desktop = Path.home() / "Desktop"
keyword = "强制执行"  # 从用户指令中提取关键词

# 搜索匹配的文件
matches = []
for f in desktop.iterdir():
    if f.is_file() and keyword in f.name:
        matches.append(f)

if not matches:
    result = {{"success": False, "message": "未找到包含'" + keyword + "'的文件"}}
elif len(matches) > 1:
    files_str = ", ".join([m.name for m in matches])
    result = {{"success": False, "message": "找到多个匹配文件: " + files_str + "，请指定具体文件"}}
else:
    target = matches[0]
    # 然后对 target 进行操作...
    result = {{"success": True, "message": "找到文件: " + target.name}}

print(json.dumps(result, ensure_ascii=False))
```

**脚本示例（Word文档文字替换）**：
**警告：.docx 是 ZIP 压缩包，绝对禁止用 open() 读取！必须用 python-docx 库！**
**重要：必须遍历 runs 而不是直接修改 para.text，否则可能替换失败！**
    ```python
import json
from pathlib import Path

try:
    from docx import Document
except ImportError:
    print(json.dumps({{"success": False, "message": "请先安装 python-docx: pip install python-docx"}}))
    exit(0)

# 目标文件
file_path = Path.home() / "Desktop" / "文档.docx"
old_text = "原文字"
new_text = "新文字"

if not file_path.exists():
    print(json.dumps({{"success": False, "message": "文件不存在: " + str(file_path)}}))
    exit(0)

doc = Document(file_path)
count = 0

# 正确方式：遍历 runs（Word 可能把一个词拆成多个 run）
for para in doc.paragraphs:
    if old_text in para.text:  # 先检查整段
        for run in para.runs:  # 再遍历每个 run
            if old_text in run.text:
                run.text = run.text.replace(old_text, new_text)
                count += 1

# 表格也要遍历 runs
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            if old_text in cell.text:
                for para in cell.paragraphs:
                    for run in para.runs:
                        if old_text in run.text:
                            run.text = run.text.replace(old_text, new_text)
                            count += 1

doc.save(file_path)
result = {{"success": True, "message": "替换完成，共替换 " + str(count) + " 处"}}
print(json.dumps(result, ensure_ascii=False))
```

## 任务
{instruction}
{context_str}
## 文件名理解规则

当用户提到文件名时：
1. **用户说的可能是部分文件名**（如"强制执行申请书"可能指"强制执行申请书-张三.docx"）
2. **先搜索匹配的文件**，再进行操作
3. **不要猜测完整文件名**，使用关键词搜索

## 关键警告

1. **绝对禁止 f-string**：不要用 f"xxx{{变量}}xxx" 格式！会导致编码错误！必须用 "xxx" + str(变量) + "xxx"
2. **JSON 输出必须正确**：脚本最后一行必须是 print(json.dumps(..., ensure_ascii=False))
3. **错误也要 JSON 格式**：except 中也要用 print(json.dumps({{"success": False, "message": str(e)}})) 输出

## Matplotlib 图表绑定用法（画图必看）

1. 饼图颜色使用列表，不要用 cm.Set3：
   ```python
   colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE']
   plt.pie(sizes, labels=labels, colors=colors[:len(labels)], autopct='%1.1f%%')
   ```
2. 中文显示：`plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']`
3. 保存图表：`plt.savefig(路径, dpi=150, bbox_inches='tight', facecolor='white')`
4. **不要使用** `plt.cm.set3`、`plt.cm.Set3` 等，会报错！

## 输出格式

返回一个 JSON 数组，每个元素是一个步骤：
```json
[
  {{
    "type": "步骤类型（如 execute_python_script、screenshot_desktop、open_folder 等）",
    "action": "简短操作描述（中文，如：批量重命名图片）",
  "params": {{}},
    "description": "给用户看的详细描述（中文）"
  }}
]
```

## 重要规则

1. **所有文件操作使用 execute_python_script**：包括重命名、删除、移动、复制、批量处理等
2. **脚本代码必须正确**：检查变量名、语法、缩进，确保可执行
3. **中文描述**：所有 description 和 action 使用中文
4. **路径处理**：使用 Path 对象处理路径，支持 ~ 和中文路径
5. **只返回 JSON 数组**：不要有任何其他解释文字

现在请规划任务："""
        
        return prompt
    
    def _call_reflection_api(self, prompt: str) -> Dict[str, Any]:
        """
        调用Claude API进行反思
        
        Args:
            prompt: 反思提示词
        
        Returns:
            包含分析和新计划的字典
        """
        logger.info("调用Claude进行反思...")
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
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
            return {
                "analysis": f"解析失败: {e}",
                "new_plan": []
            }
