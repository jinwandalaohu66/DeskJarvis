"""
基础规划器接口：定义所有AI规划器必须实现的接口

遵循 docs/ARCHITECTURE.md 中的Planner模块规范
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from agent.tools.config import Config


class BasePlanner(ABC):
    """
    基础规划器抽象类：所有AI规划器必须继承此类
    
    职责：
    - 定义统一的规划接口
    - 确保所有规划器返回相同格式的结果
    """
    
    def __init__(self, config: Config):
        """
        初始化规划器
        
        Args:
            config: 配置对象
        """
        self.config = config
    
    @abstractmethod
    def plan(
        self,
        user_instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        规划任务：将用户指令转换为可执行步骤
        
        Args:
            user_instruction: 用户自然语言指令
            context: 上下文信息（可选）
        
        Returns:
            任务步骤列表，每个步骤包含：
            - type: 步骤类型（browser_navigate, browser_click, download_file等）
            - action: 具体操作
            - params: 操作参数
            - description: 步骤描述
        """
        pass
    
    @abstractmethod
    def _build_prompt(
        self,
        instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建规划提示词
        
        Args:
            instruction: 用户指令
            context: 上下文信息
        
        Returns:
            完整的提示词
        """
        pass
    
    def reflect(
        self,
        instruction: str,
        last_plan: List[Dict[str, Any]],
        error: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        反思失败并重新规划
        
        Args:
            instruction: 原始用户指令
            last_plan: 上次失败的计划
            error: 错误信息
            context: 上下文信息
        
        Returns:
            包含分析结果和新计划的字典：
            - analysis: 错误分析
            - new_plan: 新的执行计划
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"开始反思失败原因，错误: {error[:100]}...")
        
        # 构建反思 prompt
        reflection_prompt = self._build_reflection_prompt(
            instruction, last_plan, error, context
        )
        
        # 调用AI进行反思（子类应该重写这个方法）
        try:
            reflection_result = self._call_reflection_api(reflection_prompt)
            return reflection_result
        except Exception as e:
            logger.error(f"反思失败: {e}")
            # 返回一个简单的重试方案
            return {
                "analysis": f"反思失败: {e}，将使用原计划重试",
                "new_plan": last_plan
            }
    
    def _build_reflection_prompt(
        self,
        instruction: str,
        last_plan: List[Dict[str, Any]],
        error: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建反思提示词（增强版 - 包含常见错误模式和解决方案知识库）
        
        Args:
            instruction: 原始指令
            last_plan: 失败的计划
            error: 错误信息
            context: 上下文
        
        Returns:
            反思提示词
        """
        import json
        
        plan_str = json.dumps(last_plan, ensure_ascii=False, indent=2)
        
        # 提取失败的脚本代码（如果有）
        failed_script = ""
        for step in last_plan:
            if step.get("type") == "execute_python_script":
                script = step.get("params", {}).get("script", "")
                if script:
                    # 尝试 base64 解码
                    try:
                        import base64
                        script_clean = "".join(str(script).split())
                        # 补齐 padding（模型经常漏掉末尾 '='）
                        missing_padding = len(script_clean) % 4
                        if missing_padding:
                            script_clean += "=" * (4 - missing_padding)
                        decoded = base64.b64decode(script_clean, validate=False).decode("utf-8", errors="strict")
                        failed_script = decoded
                    except Exception:
                        failed_script = script
                    break
        
        script_section = ""
        if failed_script:
            script_section = f"""
## 失败的脚本代码
```python
{failed_script[:2000]}
```
"""
        
        prompt = f"""你是一个**专业的错误分析专家**。你的任务是分析执行失败的原因，并给出**正确的修复方案**。

## 原始任务
{instruction}

## 失败的计划
{plan_str}
{script_section}
## 错误信息
{error}

---

## 🔴 常见错误模式及正确解决方案（重要！请对照检查）

### 1. UTF-8 解码错误 / gzip 错误
**错误特征**: `'utf-8' codec can't decode byte 0x8b` 或 `invalid start byte`
**原因**: 使用 urllib 下载网页，但网站返回 gzip 压缩内容，urllib 不会自动解压
**正确修复**:
```python
# 错误: urllib.request.urlopen(url).read().decode('utf-8')
# 正确: 使用 requests 库（自动处理 gzip）
import requests
response = requests.get(url)
html = response.text  # 文本内容，自动解码
binary = response.content  # 二进制内容（下载文件用）
```

### 2. f-string 语法错误
**错误特征**: `name 'f' is not defined` 或 `SyntaxError: invalid syntax` 在 f" 附近
**原因**: f-string 和引号使用错误，或 f 和引号之间有空格
**正确修复**:
```python
# 错误: f "xxx" 或 f'{{var}}'  
# 正确: 禁止使用 f-string！使用字符串拼接
message = "下载成功: " + str(filename)
```

### 3. Word 文档操作错误
**错误特征**: `UnicodeDecodeError` 或替换 0 处
**原因**: 用 open() 读取 .docx，或直接替换 paragraph.text
**正确修复**:
```python
# 必须使用 python-docx
from docx import Document
doc = Document(path)
# 遍历每个 run（格式块）替换
for para in doc.paragraphs:
    for run in para.runs:
        if old_text in run.text:
            run.text = run.text.replace(old_text, new_text)
doc.save(path)
```

### 4. 元素不可见 / 点击超时
**错误特征**: `element is not visible` 或 `Timeout exceeded`
**原因**: 页面未加载完成、有弹窗遮挡、元素在视口外
**正确修复**:
- 增加等待时间：`page.wait_for_load_state("networkidle")`
- 滚动到元素：`element.scroll_into_view_if_needed()`
- 关闭弹窗：先检查并关闭可能的弹窗

### 5. 文件路径错误
**错误特征**: `FileNotFoundError` 或 `No such file`
**原因**: 路径中有特殊字符、未展开 ~、路径不存在
**正确修复**:
```python
from pathlib import Path
# 正确处理路径
path = Path.home() / "Desktop" / "文件名.txt"
path.parent.mkdir(parents=True, exist_ok=True)  # 确保目录存在
```

### 6. 模块不存在
**错误特征**: `ModuleNotFoundError: No module named 'xxx'`
**正确修复**: 使用系统自带库，或使用 execute_python_script 自动安装

### 7. colormap 错误
**错误特征**: `has no attribute 'set3'` 或 colormap 相关
**正确修复**: 使用 `plt.cm.tab20` 或直接使用颜色列表 `['#ff0000', '#00ff00', ...]`

---

## 你的任务
1. **仔细阅读上面的错误模式**，判断当前错误属于哪一类
2. **分析具体原因**（1-2句话）
3. **生成修复后的新计划**（必须解决上述问题）

## 输出格式
只返回 JSON，不要有其他文字：
{{
  "analysis": "错误分析：属于[模式X]，原因是[具体原因]，需要[具体修复]",
  "new_plan": [
    {{
      "type": "步骤类型",
      "action": "操作描述",
      "params": {{...}},
      "description": "步骤描述"
    }}
  ]
}}

**重要**：
- 如果错误是脚本语法/库使用问题，新脚本必须**完全重写**，不能只改一点点
- 使用 requests 替换 urllib
- 使用字符串拼接替换 f-string
- 使用 python-docx 处理 Word 文档
"""
        return prompt
    
    def _call_reflection_api(self, prompt: str) -> Dict[str, Any]:
        """
        调用API进行反思（子类应该重写）
        
        Args:
            prompt: 反思提示词
        
        Returns:
            反思结果
        """
        raise NotImplementedError("子类必须实现 _call_reflection_api 方法")
    
    def _parse_response(self, content: str) -> List[Dict[str, Any]]:
        """
        解析API响应（通用实现，子类可覆盖）
        
        Args:
            content: API返回的文本内容
        
        Returns:
            解析后的步骤列表
        """
        import json
        import logging
        import re
        import time
        
        logger = logging.getLogger(__name__)
        
        def _escape_newlines_in_json_strings(text: str) -> str:
            """
            修复 LLM 常见输出：在 JSON 字符串内出现未转义换行，导致 json.loads 报：
            - Unterminated string starting at ...
            - Invalid control character ...
            """
            out_chars: list[str] = []
            in_string = False
            escape = False
            for ch in text:
                if in_string:
                    if escape:
                        out_chars.append(ch)
                        escape = False
                        continue
                    if ch == "\\":
                        out_chars.append(ch)
                        escape = True
                        continue
                    if ch == "\"":
                        out_chars.append(ch)
                        in_string = False
                        continue
                    if ch == "\n":
                        out_chars.append("\\n")
                        continue
                    if ch == "\r":
                        out_chars.append("\\n")
                        continue
                    out_chars.append(ch)
                else:
                    out_chars.append(ch)
                    if ch == "\"":
                        in_string = True
                        escape = False
            return "".join(out_chars)

        def _extract_json_fragment(text: str) -> str:
            """
            从混杂文本中提取第一个“完整闭合”的 JSON 片段。

            修复点：
            - 之前简单使用 find('[') + rfind(']')，会被字符串内的括号干扰，导致截断/解析失败
            - 这里使用状态机：忽略字符串内部的括号，并做深度计数，找到真正闭合的数组/对象
            """
            text = (text or "").strip()
            if not text:
                return ""

            def scan(open_ch: str, close_ch: str) -> str:
                in_string = False
                escape = False
                depth = 0
                start = -1
                for i, ch in enumerate(text):
                    if in_string:
                        if escape:
                            escape = False
                            continue
                        if ch == "\\":
                            escape = True
                            continue
                        if ch == "\"":
                            in_string = False
                        continue

                    # not in string
                    if ch == "\"":
                        in_string = True
                        escape = False
                        continue

                    if ch == open_ch:
                        if depth == 0:
                            start = i
                        depth += 1
                        continue
                    if ch == close_ch:
                        if depth > 0:
                            depth -= 1
                            if depth == 0 and start != -1:
                                return text[start : i + 1]
                return ""

            # 优先提取数组，其次对象
            arr = scan("[", "]")
            if arr:
                return arr
            obj = scan("{", "}")
            if obj:
                return obj
            return ""

        try:
            # 尝试提取JSON（可能包含markdown代码块）
            original_content = content
            content = content.strip()
            
            # 移除markdown代码块标记（如果有）
            if content.startswith("```"):
                lines = content.split("\n")
                # 移除第一行和最后一行（代码块标记）
                if len(lines) > 2:
                    content = "\n".join(lines[1:-1])
                else:
                    content = ""
            
            # 尝试提取JSON片段（数组优先；忽略字符串内括号）
            extracted = _extract_json_fragment(content)
            if extracted:
                content = extracted

            # 检查是否有超长的字段（content 或 script）可能导致JSON解析失败
            # 如果 JSON 内容超过5KB，尝试修复（降低阈值，更早检测和修复）
            if len(content) > 5000:  # 5KB
                logger.warning(f"检测到超长JSON内容（{len(content)}字符），尝试修复...")
                import re
                
                # 优先处理 script 字段（base64 编码的字符串通常很长）
                script_pattern = r'"script"\s*:\s*"'
                script_matches = list(re.finditer(script_pattern, content))
                if script_matches:
                    # 找到最后一个 script 字段（通常是 execute_python_script 的 script 字段）
                    last_script_match = script_matches[-1]
                    script_match_end = last_script_match.end()  # script": " 的结束位置
                    
                    # 从 script 字段开始位置查找，找到下一个应该闭合引号的位置
                    after_script = content[script_match_end:]
                    
                    # 查找下一个引号、逗号、右括号或右方括号
                    next_comma = after_script.find(',')
                    next_brace = after_script.find('}')
                    next_bracket = after_script.find(']')
                    next_quote = after_script.find('"')
                    
                    # 找到最近的结束位置
                    end_positions = []
                    if next_comma != -1:
                        end_positions.append(('comma', next_comma))
                    if next_brace != -1:
                        end_positions.append(('brace', next_brace))
                    if next_bracket != -1:
                        end_positions.append(('bracket', next_bracket))
                    # 如果引号很近（前200个字符内），可能是闭合引号
                    if next_quote != -1 and next_quote < 200:
                        end_positions.append(('quote', next_quote))
                    
                    if end_positions:
                        # 找到最近的结束位置
                        min_type, min_pos = min(end_positions, key=lambda x: x[1])
                        insert_pos = script_match_end + min_pos
                        
                        # 检查这个位置前是否有闭合引号
                        before_insert = content[script_match_end:insert_pos]
                        has_quote = '"' in before_insert
                        
                        if not has_quote:
                            # 没有闭合引号，需要在结束位置前插入
                            content = content[:insert_pos] + '"' + content[insert_pos:]
                            logger.info(f"✅ 修复了未闭合的 script 字段（在位置 {insert_pos} 插入引号，类型: {min_type}）")
                        elif min_type == 'quote':
                            # 已经有引号，检查引号后的字符是否正确
                            after_quote_pos = script_match_end + next_quote + 1
                            if after_quote_pos < len(content):
                                after_quote_char = content[after_quote_pos:after_quote_pos+1].strip()
                                if after_quote_char and after_quote_char not in [',', '}', ']']:
                                    # 引号后不是正确的JSON结构，需要修复
                                    content = content[:insert_pos] + '"' + content[insert_pos:]
                                    logger.info(f"✅ 修复了未正确闭合的 script 字段（在位置 {insert_pos} 插入引号）")
                    else:
                        # 没有找到结束位置，尝试在JSON结束前插入引号
                        # 找到最后一个 ] 的位置
                        last_bracket = content.rfind(']')
                        if last_bracket != -1 and last_bracket > script_match_end:
                            content = content[:last_bracket] + '"' + content[last_bracket:]
                            logger.info("✅ 修复了未闭合的 script 字段（在JSON结束前插入引号）")
                
                # 然后处理 content 字段（如果 script 字段已修复，可能不需要再处理 content）
                content_pattern = r'"content"\s*:\s*"'
                content_matches = list(re.finditer(content_pattern, content))
                if content_matches:
                    # 找到最后一个匹配（通常是 file_write 的 content 字段）
                    last_match = content_matches[-1]
                    match_end = last_match.end()  # content": " 的结束位置
                    
                    # 从匹配结束位置开始查找，找到下一个应该闭合引号的位置
                    after_match = content[match_end:]
                    
                    # 查找下一个引号、逗号、右括号或右方括号
                    # 注意：超长字符串中可能没有引号，需要找到JSON结构的结束位置
                    next_comma = after_match.find(',')
                    next_brace = after_match.find('}')
                    next_bracket = after_match.find(']')
                    next_quote = after_match.find('"')
                    
                    # 找到最近的结束位置
                    end_positions = []
                    if next_comma != -1:
                        end_positions.append(('comma', next_comma))
                    if next_brace != -1:
                        end_positions.append(('brace', next_brace))
                    if next_bracket != -1:
                        end_positions.append(('bracket', next_bracket))
                    # 如果引号很近（前100个字符内），可能是闭合引号
                    if next_quote != -1 and next_quote < 100:
                        end_positions.append(('quote', next_quote))
                    
                    if end_positions:
                        # 找到最近的结束位置
                        min_type, min_pos = min(end_positions, key=lambda x: x[1])
                        insert_pos = match_end + min_pos
                        
                        # 检查这个位置前是否有闭合引号
                        before_insert = content[match_end:insert_pos]
                        has_quote = '"' in before_insert
                        
                        if not has_quote:
                            # 没有闭合引号，需要在结束位置前插入
                            content = content[:insert_pos] + '"' + content[insert_pos:]
                            logger.info(f"✅ 修复了未闭合的 content 字段（在位置 {insert_pos} 插入引号，类型: {min_type}）")
                        elif min_type == 'quote':
                            # 已经有引号，检查引号后的字符是否正确
                            after_quote_pos = match_end + next_quote + 1
                            if after_quote_pos < len(content):
                                after_quote_char = content[after_quote_pos:after_quote_pos+1].strip()
                                if after_quote_char and after_quote_char not in [',', '}', ']']:
                                    # 引号后不是正确的JSON结构，需要修复
                                    content = content[:insert_pos] + '"' + content[insert_pos:]
                                    logger.info(f"✅ 修复了未正确闭合的 content 字段（在位置 {insert_pos} 插入引号）")
                    else:
                        # 没有找到结束位置，尝试在JSON结束前插入引号
                        # 找到最后一个 ] 的位置
                        last_bracket = content.rfind(']')
                        if last_bracket != -1 and last_bracket > match_end:
                            content = content[:last_bracket] + '"' + content[last_bracket:]
                            logger.info("✅ 修复了未闭合的 content 字段（在JSON结束前插入引号）")
            
            # 尝试解析JSON（可能失败，需要修复）
            steps = None
            parse_error = None
            
            try:
                steps = json.loads(content)
            except json.JSONDecodeError as e:
                parse_error = e
                logger.warning(f"首次JSON解析失败: {e}，尝试修复...")

                # 第一优先：修复“字符串内未转义换行”（最常见导致 Unterminated string 的原因）
                if "Unterminated string" in str(e) or "Invalid control character" in str(e):
                    try:
                        fixed = _escape_newlines_in_json_strings(content)
                        steps = json.loads(fixed)
                        content = fixed
                        parse_error = None
                        logger.info("✅ 通过转义字符串内换行修复了JSON解析失败")
                    except json.JSONDecodeError:
                        steps = None
                # 第二优先：再次尝试提取 JSON 片段（有时模型输出前后带了噪音）
                if steps is None:
                    frag = _extract_json_fragment(content)
                    if frag and frag != content:
                        try:
                            steps = json.loads(frag)
                            content = frag
                            parse_error = None
                            logger.info("✅ 通过重新提取 JSON 片段修复了解析失败")
                        except json.JSONDecodeError:
                            steps = None
                
                # 尝试修复 script 字段中的问题
                # 策略：找到所有 "script": "..." 的部分，尝试修复其中的特殊字符
                try:
                    # 使用正则表达式找到 script 字段
                    script_pattern = r'"script"\s*:\s*"([^"]*(?:\\.[^"]*)*)"'
                    
                    def fix_script_string(match):
                        script_content = match.group(1)
                        # 修复未转义的换行符
                        script_content = script_content.replace('\n', '\\n').replace('\r', '\\r')
                        # 修复未转义的双引号（但保留已转义的）
                        script_content = re.sub(r'(?<!\\)"', '\\"', script_content)
                        # 修复未转义的反斜杠（但保留已转义的）
                        script_content = re.sub(r'(?<!\\)\\(?![\\"nrtbf])', '\\\\', script_content)
                        return f'"script": "{script_content}"'
                    
                    # 尝试修复 script 字段
                    fixed_content = re.sub(script_pattern, fix_script_string, content, flags=re.DOTALL)
                    
                    # 再次尝试解析
                    try:
                        steps = json.loads(fixed_content)
                        logger.info("✅ 通过修复 script 字段成功解析JSON")
                    except json.JSONDecodeError as e2:
                        logger.warning(f"修复后仍然失败: {e2}，尝试更激进的方法...")
                        # 尝试更激进的方法：查找未闭合的 script 字段并手动闭合
                        try:
                            # 查找 "script": " 的位置
                            script_pattern = r'"script"\s*:\s*"'
                            script_matches = list(re.finditer(script_pattern, content))
                            
                            if script_matches:
                                # 找到最后一个 script 字段
                                last_script_match = script_matches[-1]
                                script_start = last_script_match.end()  # script": " 的结束位置
                                
                                # 从 script 开始位置查找，找到下一个应该闭合引号的位置
                                after_script = content[script_start:]
                                
                                # base64 字符串中不会包含 }, ], , 这些 JSON 结构字符
                                # 所以直接找到第一个这些字符，就是 script 字段的结束位置
                                # 优先顺序：}, ], ,
                                next_brace = after_script.find('}')
                                next_bracket = after_script.find(']')
                                next_comma = after_script.find(',')
                                
                                # 找到最近的结束位置（优先顺序：}, ], ,）
                                end_pos = -1
                                if next_brace != -1:
                                    end_pos = script_start + next_brace
                                elif next_bracket != -1:
                                    end_pos = script_start + next_bracket
                                elif next_comma != -1:
                                    end_pos = script_start + next_comma
                                
                                # 如果还是没找到（可能 JSON 被截断），尝试在最后一个 } 或 ] 前插入引号
                                if end_pos == -1:
                                    # 查找最后一个 JSON 结构字符
                                    last_brace = content.rfind('}')
                                    last_bracket = content.rfind(']')
                                    last_comma = content.rfind(',')
                                    
                                    # 找到 script_start 之后最近的结构字符
                                    if last_brace > script_start:
                                        end_pos = last_brace
                                    elif last_bracket > script_start:
                                        end_pos = last_bracket
                                    elif last_comma > script_start:
                                        end_pos = last_comma
                                    else:
                                        # 如果连这些都没有，说明 JSON 可能被严重截断
                                        # 尝试在内容末尾添加闭合引号和 JSON 结构
                                        # 先检查是否以 base64 字符结尾
                                        if len(after_script) > 0:
                                            # 在末尾添加闭合引号和必要的 JSON 结构
                                            # 需要闭合：script 字符串、params 对象、步骤对象、数组
                                            # 检查 content 是否以 ] 结尾
                                            if not content.rstrip().endswith(']'):
                                                # 添加闭合引号、闭合 params 对象、闭合步骤对象、闭合数组
                                                content = content + '"' + '}' + '}' + ']'
                                            else:
                                                # 如果已经有 ]，在它前面插入引号
                                                last_bracket_pos = content.rfind(']')
                                                if last_bracket_pos > script_start:
                                                    content = content[:last_bracket_pos] + '"' + content[last_bracket_pos:]
                                                else:
                                                    # 如果 ] 在 script_start 之前，在末尾添加
                                                    content = content + '"' + '}' + '}' + ']'
                                            logger.info("✅ 通过添加 JSON 结构修复了被截断的 script 字段")
                                            try:
                                                steps = json.loads(content)
                                                logger.info("✅ 通过添加 JSON 结构成功解析JSON")
                                            except json.JSONDecodeError as e4:
                                                logger.error(f"添加 JSON 结构后仍然失败: {e4}")
                                                raise e2 from e4
                                        else:
                                            raise e2
                                
                                if end_pos != -1 and end_pos > script_start:
                                    # 检查这个位置前是否有闭合引号
                                    before_end = content[script_start:end_pos]
                                    has_quote = '"' in before_end
                                    
                                    if not has_quote:
                                        # 没有闭合引号，在结束位置前插入引号
                                        content = content[:end_pos] + '"' + content[end_pos:]
                                        logger.info(f"✅ 通过激进方法修复了未闭合的 script 字段（在位置 {end_pos} 插入引号）")
                                        
                                        # 再次尝试解析
                                        try:
                                            steps = json.loads(content)
                                            logger.info("✅ 通过激进方法成功解析JSON")
                                        except json.JSONDecodeError as e3:
                                            logger.error(f"激进修复后仍然失败: {e3}")
                                            # 如果还是失败，尝试在最后一个 ] 前插入引号
                                            last_bracket = content.rfind(']')
                                            if last_bracket > script_start:
                                                content2 = content[:last_bracket] + '"' + content[last_bracket:]
                                                try:
                                                    steps = json.loads(content2)
                                                    logger.info("✅ 通过在最后一个]前插入引号成功解析JSON")
                                                    content = content2
                                                except Exception as e5:
                                                    raise e2 from e5
                                            else:
                                                raise e2
                                    else:
                                        raise e2
                            else:
                                raise e2
                        except Exception as e3:
                            logger.error(f"所有修复尝试都失败: {e3}")
                            raise e from e3
                except Exception as fix_error:
                    logger.error(f"修复JSON时出错: {fix_error}")
                    raise parse_error from fix_error
            
            if steps is None:
                # === 增强解析器：尝试识别 Markdown 列表格式 ===
                logger.warning("[SECURITY_SHIELD] JSON解析失败，尝试识别 Markdown 列表格式...")
                steps = self._parse_markdown_list(content)
                if steps is None:
                    raise ValueError("无法解析JSON，也无法识别Markdown列表格式")
            
            # 验证格式
            if isinstance(steps, dict):
                # 兼容模型返回 {"steps":[...]} 的情况
                if "steps" in steps and isinstance(steps["steps"], list):
                    steps = steps["steps"]
                elif "new_plan" in steps and isinstance(steps["new_plan"], list):
                    steps = steps["new_plan"]
                else:
                    raise ValueError("响应不是数组格式")
            if not isinstance(steps, list):
                raise ValueError("响应不是数组格式")
            
            # 验证每个步骤的格式，并自动修复删除操作
            import base64
            fixed_steps = []
            
            # === 逻辑闭环验证：验证 browser_click 步骤 ===
            for i, step in enumerate(steps):
                step_type = step.get("type", "")
                if step_type == "browser_click":
                    params = step.get("params", {})
                    has_selector = bool(params.get("selector"))
                    has_coordinates = (params.get("x") is not None and params.get("y") is not None)
                    
                    if not has_selector and not has_coordinates:
                        logger.error(f"[SECURITY_SHIELD] 步骤{i}: browser_click 缺少 selector 和坐标 (x, y)，无法执行")
                        raise ValueError(f"步骤{i}: browser_click 必须提供 selector 或坐标 (x, y)")
            
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    raise ValueError(f"步骤{i}不是对象格式")
                required_fields = ["type", "action", "params"]
                for field in required_fields:
                    if field not in step:
                        raise ValueError(f"步骤{i}缺少字段: {field}")
                
                # description 字段可选，如果没有则自动生成
                if "description" not in step:
                    step["description"] = step.get("action", f"执行步骤: {step.get('type', 'unknown')}")
                    logger.info(f"步骤{i}缺少description字段，已自动生成: {step['description']}")
                
                # 自动修复：如果使用 file_move 但没有 target_dir，说明可能是误用（如删除文件）
                step_type = step.get("type", "")
                step_action = step.get("action", "")
                step_description = step.get("description", "")
                step_params = step.get("params", {})
                
                is_delete_operation = (
                    "删除" in str(step_action) or "删除" in str(step_description) or
                    (step_type == "file_move" and "target_dir" not in step_params)
                )
                
                if is_delete_operation and step_type == "file_move":
                    logger.warning(f"步骤{i}: 检测到 file_move 工具用于删除操作（缺少 target_dir 或包含'删除'关键词），自动转换为脚本")
                    # 生成删除文件的脚本
                    file_path = step_params.get("file_path", "")
                    if not file_path:
                        # 如果 params 中没有 file_path，尝试从其他字段获取
                        file_path = step_params.get("source", "") or step_params.get("source_path", "")
                    
                    if not file_path:
                        raise ValueError(f"步骤{i}: 无法确定要删除的文件路径")
                    
                    # 转义单引号，避免语法错误
                    file_path_escaped = file_path.replace("'", "\\'")
                    # 生成删除文件的脚本，支持智能文件搜索
                    script_content = f"""import os
import json
from pathlib import Path

def find_file(filename, search_dirs):
    '''智能搜索文件'''
    for search_dir in search_dirs:
        search_path = Path(search_dir)
        if not search_path.exists():
            continue
        # 精确匹配
        exact_path = search_path / filename
        if exact_path.exists():
            return exact_path
        # 部分匹配（文件名包含）
        for item in search_path.iterdir():
            if item.is_file() and filename.lower() in item.name.lower():
                return item
    return None

try:
    home = Path.home()
    search_dirs = [
        home / 'Desktop',
        home / 'Downloads',
        home / 'Documents',
        home
    ]
    
    file_name = '{file_path_escaped}'
    
    # 如果 file_name 是完整路径，直接使用
    if '/' in file_name or file_name.startswith('~'):
        target_path = Path(os.path.expanduser(file_name))
    else:
        # 否则智能搜索
        target_path = find_file(file_name, search_dirs)
        if not target_path:
            print(json.dumps({{'success': False, 'message': f'文件不存在: {{file_name}}'}}))
            exit(0)
    
    if target_path.exists():
        os.remove(target_path)
        print(json.dumps({{'success': True, 'message': f'文件删除成功: {{target_path}}'}}))
    else:
        print(json.dumps({{'success': False, 'message': f'文件不存在: {{target_path}}'}}))
except Exception as e:
    print(json.dumps({{'success': False, 'message': str(e)}}))"""
                    
                    # 替换为删除脚本步骤
                    fixed_step = {
                        "type": "execute_python_script",
                        "action": "删除文件",
                        "params": {
                            "script": base64.b64encode(script_content.encode('utf-8')).decode('utf-8'),
                            "reason": "删除文件需要使用 os.remove()，没有预定义工具",
                            "safety": "只操作用户指定路径，无危险命令"
                        },
                        "description": "删除文件"
                    }
                    fixed_steps.append(fixed_step)
                    logger.info(f"步骤{i}: 已自动转换为删除脚本步骤")
                else:
                    fixed_steps.append(step)
                
                # 如果是脚本步骤，验证 script 字段并检测敏感操作
                if fixed_steps[-1].get("type") == "execute_python_script":
                    params = fixed_steps[-1].get("params", {})
                    if "script" not in params:
                        raise ValueError(f"步骤{i}（execute_python_script）缺少 script 字段")
                    script = params.get("script", "")
                    if not isinstance(script, str) or not script.strip():
                        raise ValueError(f"步骤{i}（execute_python_script）的 script 字段无效")
                    
                    # === 敏感操作确认：检测毁灭性操作 ===
                    script_decoded = script
                    try:
                        # 尝试 base64 解码
                        import base64
                        script_decoded = base64.b64decode(script).decode('utf-8', errors='ignore')
                    except Exception:
                        # 如果不是 base64，直接使用原字符串
                        pass
                    
                    # 检测敏感操作模式
                    dangerous_patterns = [
                        (r'os\.system\s*\(\s*["\']rm\s+-rf\s+/', "删除根目录"),
                        (r'os\.system\s*\(\s*["\']rm\s+-rf\s+~', "删除用户主目录"),
                        (r'subprocess\.(call|run|Popen)\s*\(\s*["\']rm\s+-rf', "使用subprocess删除文件"),
                        (r'os\.system\s*\(\s*["\']format\s+', "格式化磁盘"),
                        (r'os\.system\s*\(\s*["\']del\s+/f\s+/s\s+/q\s+', "Windows强制删除"),
                        (r'shutil\.rmtree\s*\(\s*["\']/', "删除根目录"),
                        (r'__import__\s*\(\s*["\']os["\']\s*\)\.system\s*\(\s*["\']rm', "动态导入执行删除"),
                    ]
                    
                    is_sensitive = False
                    for pattern, description in dangerous_patterns:
                        import re
                        if re.search(pattern, script_decoded, re.IGNORECASE):
                            is_sensitive = True
                            logger.error(f"[SECURITY_SHIELD] 步骤{i}: 检测到敏感操作 - {description}")
                            break
                    
                    if is_sensitive:
                        # 在 description 中添加 [SENSITIVE] 前缀
                        current_desc = fixed_steps[-1].get("description", "")
                        if not current_desc.startswith("[SENSITIVE]"):
                            fixed_steps[-1]["description"] = f"[SENSITIVE] {current_desc}"
                            logger.warning(f"[SECURITY_SHIELD] 步骤{i}: 已标记为敏感操作，将在执行前触发用户确认")
            
            return fixed_steps
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.error(f"错误位置: line {e.lineno}, column {e.colno}")
            
            # 保存实际生成的JSON内容到文件以便调试
            try:
                from pathlib import Path
                debug_dir = Path.home() / ".deskjarvis" / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_file = debug_dir / f"failed_json_{int(time.time())}.txt"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write("=== 原始响应内容 ===\n")
                    f.write(original_content)
                    f.write("\n\n=== 提取的JSON内容 ===\n")
                    f.write(content)
                    f.write("\n\n=== 错误信息 ===\n")
                    f.write(str(e))
                logger.error(f"已保存失败的JSON内容到: {debug_file}")
            except Exception as save_error:
                logger.warning(f"保存调试文件失败: {save_error}")
            
            # 记录更多调试信息
            if hasattr(e, 'pos'):
                logger.debug(f"错误位置（字符索引）: {e.pos}")
                # 显示错误位置附近的内容
                start = max(0, e.pos - 100)
                end = min(len(content), e.pos + 100)
                logger.debug(f"错误位置附近的内容:\n{content[start:end]}")
            
            logger.debug(f"完整响应内容（前500字符）:\n{original_content[:500]}")
            logger.debug(f"完整响应内容（后500字符）:\n{original_content[-500:]}")
            
            from agent.tools.exceptions import PlannerError
            raise PlannerError(f"解析规划结果失败: {e}。请检查生成的JSON格式是否正确，特别是 script 字段中的引号和换行符是否正确转义。失败的JSON内容已保存到调试文件。")
        except Exception as e:
            logger.error(f"解析响应失败: {e}", exc_info=True)
            logger.debug(f"响应内容（前1000字符）:\n{original_content[:1000]}")
            from agent.tools.exceptions import PlannerError
            raise PlannerError(f"解析规划结果失败: {e}")
    
    def _parse_markdown_list(self, content: str) -> Optional[List[Dict[str, Any]]]:
        """
        解析 Markdown 列表格式并转换为步骤格式
        
        如果 LLM 返回了 "1. 导航到... 2. 点击..." 格式，尝试转换为步骤格式
        
        Args:
            content: 原始响应内容
            
        Returns:
            解析后的步骤列表，如果无法解析则返回 None
        """
        import re
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # 匹配 Markdown 列表格式：1. 或 - 或 * 开头
            # 例如：
            # 1. 导航到 https://example.com
            # 2. 点击登录按钮
            # 或
            # - 导航到 https://example.com
            # - 点击登录按钮
            
            list_pattern = r'(?:^|\n)(?:\d+\.\s*|[-*]\s*)(.+?)(?=\n(?:\d+\.\s*|[-*]\s*)|\n\n|$)'
            matches = re.findall(list_pattern, content, re.MULTILINE | re.DOTALL)
            
            if not matches or len(matches) < 2:
                # 如果匹配项少于2个，可能不是列表格式
                logger.debug("[SECURITY_SHIELD] Markdown列表格式匹配项不足，跳过")
                return None
            
            logger.info(f"[SECURITY_SHIELD] 识别到 {len(matches)} 个Markdown列表项，尝试转换为步骤格式")
            
            steps = []
            for i, item in enumerate(matches):
                item = item.strip()
                if not item:
                    continue
                
                # 尝试识别操作类型和参数
                step_type = None
                action = item
                params = {}
                
                # 识别浏览器导航
                if re.search(r'导航|访问|打开.*(http|www|\.com|\.cn)', item, re.IGNORECASE):
                    step_type = "browser_navigate"
                    # 提取URL
                    url_match = re.search(r'(https?://[^\s]+|www\.[^\s]+|[^\s]+\.(com|cn|org|net)[^\s]*)', item)
                    if url_match:
                        params["url"] = url_match.group(1)
                    else:
                        params["url"] = item.split()[-1]  # 取最后一个词作为URL
                
                # 识别点击操作
                elif re.search(r'点击|选择|按下', item, re.IGNORECASE):
                    step_type = "browser_click"
                    # 提取选择器或文本
                    if '按钮' in item or 'button' in item.lower():
                        # 尝试提取按钮文本
                        text_match = re.search(r'["\']([^"\']+)["\']|([^点击选择按下]+(?:按钮|链接|元素))', item)
                        if text_match:
                            params["text"] = text_match.group(1) or text_match.group(2)
                    else:
                        # 尝试提取选择器
                        selector_match = re.search(r'["\']([^"\']+)["\']|(#[\w-]+|\.\w+|[\w-]+)', item)
                        if selector_match:
                            params["selector"] = selector_match.group(1) or selector_match.group(2)
                
                # 识别填写操作
                elif re.search(r'填写|输入|输入框', item, re.IGNORECASE):
                    step_type = "browser_fill"
                    # 提取选择器和值
                    parts = re.split(r'[:：]|为|输入', item, maxsplit=1)
                    if len(parts) >= 2:
                        selector_part = parts[0].strip()
                        value_part = parts[1].strip()
                        # 提取选择器
                        selector_match = re.search(r'["\']([^"\']+)["\']|(#[\w-]+|\.\w+)', selector_part)
                        if selector_match:
                            params["selector"] = selector_match.group(1) or selector_match.group(2)
                        # 提取值
                        value_match = re.search(r'["\']([^"\']+)["\']|([^\s]+)', value_part)
                        if value_match:
                            params["value"] = value_match.group(1) or value_match.group(2)
                
                # 识别文件操作
                elif re.search(r'下载|保存|创建文件|写入', item, re.IGNORECASE):
                    if '下载' in item or 'download' in item.lower():
                        step_type = "download_file"
                    elif '创建' in item or '写入' in item or 'create' in item.lower():
                        step_type = "file_write"
                        # 提取文件路径
                        path_match = re.search(r'["\']([^"\']+)["\']|(/[^\s]+|~/[^\s]+|[\w-]+\.(txt|json|py))', item)
                        if path_match:
                            params["file_path"] = path_match.group(1) or path_match.group(2)
                
                # 如果无法识别，使用通用类型
                if not step_type:
                    step_type = "unknown"
                    logger.warning(f"[SECURITY_SHIELD] 无法识别步骤类型: {item}")
                
                step = {
                    "type": step_type,
                    "action": action,
                    "params": params,
                    "description": item
                }
                steps.append(step)
            
            if steps:
                logger.info(f"[SECURITY_SHIELD] 成功将Markdown列表转换为 {len(steps)} 个步骤")
                return steps
            else:
                return None
                
        except Exception as e:
            logger.warning(f"[SECURITY_SHIELD] Markdown列表解析失败: {e}")
            return None
