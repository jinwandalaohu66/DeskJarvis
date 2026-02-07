"""
Reflector Component - AI Error Analysis & Self-Healing

Responsibility:
- Analyze execution failures
- Determine if the error is recoverable
- Propose a fixed step (Self-Healing)
- Visual Grounding: Use screenshots to locate elements when selectors fail
"""

import logging
import json
import base64
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
from openai import OpenAI
from agent.tools.config import Config

logger = logging.getLogger(__name__)

@dataclass
class ReflectorResult:
    is_retryable: bool
    modified_step: Optional[Dict[str, Any]]
    reason: str

class Reflector:
    def __init__(self, config: Config, use_async: bool = True):
        """
        初始化 Reflector
        
        Args:
            config: 配置对象
            use_async: 是否使用异步客户端（默认 True，提升性能）
        """
        self.config = config
        self.client = None
        self.async_client = None
        self.provider = config.provider.lower()
        self.model = config.model
        self.sandbox_path = Path(config.sandbox_path).resolve()
        self.use_async = use_async
        self._temp_files: List[Path] = []  # 跟踪临时文件，用于清理
        
        api_key = config.api_key
        logger.info(f"Reflector: config.provider='{config.provider}', config.api_key exists={'Yes' if api_key else 'No'}, use_async={use_async}")
        
        if not api_key:
            logger.warning("Reflector: No API Key found. Self-healing disabled.")
            return

        try:
            p_clean = self.provider.strip().lower()
            if p_clean == "claude":
                from anthropic import Anthropic
                self.client = Anthropic(api_key=api_key)
                logger.info(f"Reflector initialized with Anthropic client (Provider: {p_clean})")
                
                # 尝试初始化异步客户端
                if use_async:
                    try:
                        from anthropic import AsyncAnthropic
                        self.async_client = AsyncAnthropic(api_key=api_key)
                        logger.info("✅ Reflector 异步客户端已初始化 (AsyncAnthropic)")
                    except ImportError:
                        logger.warning("⚠️ AsyncAnthropic 不可用，将使用同步客户端")
            elif p_clean == "deepseek":
                self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                logger.info(f"Reflector initialized with DeepSeek client (Base URL: {self.client.base_url})")
                
                # 尝试初始化异步客户端
                if use_async:
                    try:
                        from openai import AsyncOpenAI
                        self.async_client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                        logger.info("✅ Reflector 异步客户端已初始化 (AsyncOpenAI)")
                    except ImportError:
                        logger.warning("⚠️ AsyncOpenAI 不可用，将使用同步客户端")
            elif p_clean == "grok":
                self.client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
                logger.info(f"Reflector initialized with Grok client (Base URL: {self.client.base_url})")
                
                if use_async:
                    try:
                        from openai import AsyncOpenAI
                        self.async_client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
                        logger.info("✅ Reflector 异步客户端已初始化 (AsyncOpenAI)")
                    except ImportError:
                        logger.warning("⚠️ AsyncOpenAI 不可用，将使用同步客户端")
            else:
                # Default to OpenAI
                self.client = OpenAI(api_key=api_key)
                logger.info(f"Reflector initialized with DEFAULT OpenAI client (Provider: '{p_clean}', Base URL: {self.client.base_url})")
                
                if use_async:
                    try:
                        from openai import AsyncOpenAI
                        self.async_client = AsyncOpenAI(api_key=api_key)
                        logger.info("✅ Reflector 异步客户端已初始化 (AsyncOpenAI)")
                    except ImportError:
                        logger.warning("⚠️ AsyncOpenAI 不可用，将使用同步客户端")
        except Exception as e:
            logger.warning(f"Reflector initialization failed (Self-healing disabled): {e}")
        
        # 初始化OCR助手（用于视觉定位）
        try:
            from agent.executor.ocr_helper import OCRHelper
            self.ocr_helper = OCRHelper()
        except Exception as e:
            logger.warning(f"OCR助手初始化失败，视觉定位功能将受限: {e}")
            self.ocr_helper = None

    def analyze_failure(
        self, 
        step: Dict[str, Any], 
        error_message: str, 
        context_summary: str = ""
    ) -> ReflectorResult:
        """
        Analyze the failed step and error to propose a fix.
        
        Enhanced with Visual Grounding: If browser error detected, searches for error screenshots
        and uses visual analysis to locate elements by coordinates.
        """
        if not self.client:
            return ReflectorResult(False, None, "Reflector not configured (No API Key)")

        logger.info(f"Reflector process started for step: {step.get('action')}")
        
        # === 新增：视觉定位（Visual Grounding）===
        # 检测浏览器错误，查找错误截图
        screenshot_data = None
        screenshot_path = None
        is_browser_error = any(keyword in error_message.lower() for keyword in [
            "browsererror", "未找到元素", "element not found", "selector", "点击失败", 
            "填写失败", "login_error", "click_error", "无法找到", "密码", "用户名"
        ])
        
        if is_browser_error:
            screenshot_path = self._find_latest_error_screenshot()
            if screenshot_path:
                logger.info(f"🔍 检测到浏览器错误，找到错误截图: {screenshot_path}")
                screenshot_data = self._encode_screenshot(screenshot_path)
                screenshot_info = self._get_screenshot_info(screenshot_path)
                if screenshot_data:
                    logger.info(f"✅ 截图已编码，将用于视觉分析 (尺寸: {screenshot_info.get('screenshot_width', 'unknown')}x{screenshot_info.get('screenshot_height', 'unknown')})")
            else:
                screenshot_info = {}
        else:
            screenshot_info = {}
        
        prompt = self._build_reflection_prompt(step, error_message, context_summary, screenshot_data, screenshot_info)
        
        try:
            if self.provider == "claude":
                # Anthropic API call (supports vision)
                messages = [{"role": "user", "content": []}]
                
                # 添加文本内容
                messages[0]["content"].append({"type": "text", "text": prompt})
                
                # 如果有截图，添加图片（Claude支持多模态）
                if screenshot_data:
                    messages[0]["content"].append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_data
                        }
                    })
                    logger.info("📸 已添加截图到Claude API请求（多模态分析）")
                
                # 使用真正的异步客户端（如果可用）
                if self.async_client:
                    try:
                        import asyncio
                        logger.info("[SECURITY_SHIELD] 使用异步客户端调用 Claude API（真正的 async/await）")
                        
                        async def call_claude():
                            response = await self.async_client.messages.create(
                                model=self.model,
                                max_tokens=4000,
                                system="You are an expert Python Debugger and Agentic Planner. Your goal is to fix failed automation steps. Respond ONLY with a JSON object.",
                                messages=messages,
                                temperature=0.1,
                            )
                            return response
                        
                        # 运行异步调用（如果已有事件循环，使用它；否则创建新的）
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # 事件循环已在运行，使用线程池执行
                                import concurrent.futures
                                with concurrent.futures.ThreadPoolExecutor() as executor:
                                    future = executor.submit(asyncio.run, call_claude())
                                    response = future.result(timeout=60.0)
                            else:
                                response = loop.run_until_complete(call_claude())
                        except RuntimeError:
                            # 没有事件循环，创建新的
                            response = asyncio.run(call_claude())
                        
                        content = response.content[0].text
                    except Exception as e:
                        logger.warning(f"[SECURITY_SHIELD] 异步调用失败，降级到同步调用: {e}")
                        # 降级到同步调用
                        response = self.client.messages.create(
                            model=self.model,
                            max_tokens=4000,
                            system="You are an expert Python Debugger and Agentic Planner. Your goal is to fix failed automation steps. Respond ONLY with a JSON object.",
                            messages=messages,
                            temperature=0.1,
                        )
                        content = response.content[0].text
                else:
                    # 使用同步客户端
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=4000,
                        system="You are an expert Python Debugger and Agentic Planner. Your goal is to fix failed automation steps. Respond ONLY with a JSON object.",
                        messages=messages,
                        temperature=0.1,
                    )
                    content = response.content[0].text
            else:
                # OpenAI / DeepSeek / Grok API call
                messages = [
                    {"role": "system", "content": "You are an expert Python Debugger and Agentic Planner. Your goal is to fix failed automation steps. Respond ONLY with a JSON object."},
                ]
                
                # 构建用户消息（支持多模态）
                user_content = []
                user_content.append({"type": "text", "text": prompt})
                
                # 如果有截图，检查模型是否支持视觉
                if screenshot_data:
                    # DeepSeek-V3 和 OpenAI GPT-4V 支持视觉
                    vision_models = ["deepseek-chat", "deepseek-v3", "gpt-4-vision", "gpt-4o", "gpt-4-turbo"]
                    if any(vm in self.model.lower() for vm in vision_models):
                        user_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_data}"
                            }
                        })
                        logger.info(f"📸 已添加截图到API请求（{self.model}支持多模态）")
                    else:
                        # 如果不支持视觉，使用OCR提取文本和位置信息
                        logger.info("⚠️ 模型不支持视觉，使用OCR提取文本信息")
                        ocr_info = self._extract_ocr_info(screenshot_path)
                        if ocr_info:
                            prompt += f"\n\n**OCR提取的页面文本信息**:\n{ocr_info}"
                
                messages.append({"role": "user", "content": user_content})
                
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1,
                }
                
                # DeepSeek and newer OpenAI models support JSON mode
                if self.provider in ["openai", "deepseek"]:
                    kwargs["response_format"] = {"type": "json_object"}
                
                # 使用真正的异步客户端（如果可用）
                if self.async_client:
                    try:
                        import asyncio
                        logger.info("[SECURITY_SHIELD] 使用异步客户端调用 LLM API（真正的 async/await）")
                        
                        async def call_llm():
                            response = await self.async_client.chat.completions.create(**kwargs)
                            return response
                        
                        # 运行异步调用
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # 事件循环已在运行，使用线程池执行
                                import concurrent.futures
                                with concurrent.futures.ThreadPoolExecutor() as executor:
                                    future = executor.submit(asyncio.run, call_llm())
                                    response = future.result(timeout=60.0)
                            else:
                                response = loop.run_until_complete(call_llm())
                        except RuntimeError:
                            # 没有事件循环，创建新的
                            response = asyncio.run(call_llm())
                        
                        content = response.choices[0].message.content
                    except Exception as e:
                        logger.warning(f"[SECURITY_SHIELD] 异步调用失败，降级到同步调用: {e}")
                        # 降级到同步调用
                        response = self.client.chat.completions.create(**kwargs)
                        content = response.choices[0].message.content
                else:
                    # 使用同步客户端
                    response = self.client.chat.completions.create(**kwargs)
                    content = response.choices[0].message.content

            # Parse JSON with fallback extraction
            try:
                result_json = json.loads(content)
            except json.JSONDecodeError:
                # Manual extraction if AI included preamble/postamble
                import re
                match = re.search(r'(\{.*\})', content, re.DOTALL)
                if match:
                    result_json = json.loads(match.group(1))
                else:
                    raise
            
            # 清理临时文件
            self._cleanup_temp_files()
            
            return ReflectorResult(
                is_retryable=result_json.get("is_retryable", False),
                modified_step=result_json.get("modified_step"),
                reason=result_json.get("reason", "No reason provided")
            )
            
        except Exception as e:
            logger.error(f"Reflector analysis failed: {e}", exc_info=True)
            # 即使失败也要清理临时文件
            self._cleanup_temp_files()
            return ReflectorResult(False, None, f"Reflector Error: {e}")

    def _find_latest_error_screenshot(self) -> Optional[Path]:
        """
        查找最新的错误截图
        
        Returns:
            最新截图路径，如果未找到返回None
        """
        try:
            # 浏览器错误截图通常保存在 downloads 目录
            downloads_dir = self.sandbox_path / "downloads"
            if not downloads_dir.exists():
                return None
            
            # 查找错误截图（按文件名模式）
            error_patterns = ["*error_*.png", "*login_error*.png", "*click_error*.png", "*fill_error*.png"]
            latest_screenshot = None
            latest_time = 0
            
            for pattern in error_patterns:
                for screenshot_path in downloads_dir.glob(pattern):
                    mtime = screenshot_path.stat().st_mtime
                    if mtime > latest_time:
                        latest_time = mtime
                        latest_screenshot = screenshot_path
            
            return latest_screenshot
        except Exception as e:
            logger.warning(f"查找错误截图失败: {e}")
            return None
    
    def _get_screenshot_info(self, screenshot_path: Optional[Path]) -> Dict[str, Any]:
        """
        获取截图信息（尺寸等），用于坐标归一化
        
        Args:
            screenshot_path: 截图文件路径
            
        Returns:
            包含截图尺寸信息的字典
        """
        if not screenshot_path or not screenshot_path.exists():
            return {}
        
        try:
            from PIL import Image
            with Image.open(screenshot_path) as img:
                width, height = img.size
                return {
                    "screenshot_width": width,
                    "screenshot_height": height,
                    "screenshot_path": str(screenshot_path)
                }
        except Exception as e:
            logger.warning(f"获取截图信息失败: {e}")
            return {}
    
    def _encode_screenshot(self, screenshot_path: Path) -> Optional[str]:
        """
        将截图编码为Base64（带图片预处理优化）
        
        优化功能：
        - 如果图片宽度超过 1920px，等比例缩放至 1920px 宽度内
        - 使用适当的压缩率保存为临时文件，节省 Token 成本
        - 自动清理临时文件
        
        Args:
            screenshot_path: 截图文件路径
            
        Returns:
            Base64编码的图片数据，失败返回None
        """
        temp_file = None
        try:
            from PIL import Image
            
            # 打开原始图片
            with Image.open(screenshot_path) as img:
                original_width, original_height = img.size
                
                # 如果宽度超过 1920px，进行缩放
                if original_width > 1920:
                    # 计算缩放比例（保持宽高比）
                    scale_ratio = 1920 / original_width
                    new_width = 1920
                    new_height = int(original_height * scale_ratio)
                    
                    logger.info(f"[SECURITY_SHIELD] 图片尺寸过大 ({original_width}x{original_height})，缩放至 {new_width}x{new_height} 以节省 Token")
                    
                    # 缩放图片（使用高质量重采样）
                    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # 创建临时文件保存压缩后的图片
                    temp_dir = self.sandbox_path / "temp"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    
                    temp_file = temp_dir / f"compressed_{screenshot_path.stem}.png"
                    # 保存为 PNG（质量 85，平衡文件大小和质量）
                    img_resized.save(temp_file, "PNG", optimize=True, compress_level=6)
                    
                    # 记录临时文件，用于后续清理
                    self._temp_files.append(temp_file)
                    
                    # 读取压缩后的图片
                    with open(temp_file, "rb") as f:
                        image_bytes = f.read()
                else:
                    # 图片尺寸合适，直接读取
                    with open(screenshot_path, "rb") as f:
                        image_bytes = f.read()
                
                # Base64 编码
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                
                # 记录优化效果
                original_size = screenshot_path.stat().st_size
                if temp_file:
                    compressed_size = temp_file.stat().st_size
                    reduction = (1 - compressed_size / original_size) * 100
                    logger.info(f"[SECURITY_SHIELD] 图片压缩完成: {original_size / 1024:.1f}KB -> {compressed_size / 1024:.1f}KB (减少 {reduction:.1f}%)")
                
                return image_base64
        except ImportError:
            # PIL 不可用，降级到原始方法
            logger.warning("[SECURITY_SHIELD] PIL 不可用，跳过图片预处理")
            try:
                with open(screenshot_path, "rb") as f:
                    image_bytes = f.read()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                return image_base64
            except Exception as e:
                logger.warning(f"编码截图失败: {e}")
                return None
        except Exception as e:
            logger.warning(f"[SECURITY_SHIELD] 图片预处理失败: {e}，降级到原始方法")
            try:
                with open(screenshot_path, "rb") as f:
                    image_bytes = f.read()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                return image_base64
            except Exception as e2:
                logger.warning(f"编码截图失败: {e2}")
                return None
    
    def _cleanup_temp_files(self):
        """
        清理临时文件（防止沙盒目录溢出）
        
        清理所有在图片预处理过程中创建的临时压缩文件。
        """
        cleaned_count = 0
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    cleaned_count += 1
            except Exception as e:
                logger.warning(f"[SECURITY_SHIELD] 清理临时文件失败: {temp_file} - {e}")
        
        if cleaned_count > 0:
            logger.debug(f"[SECURITY_SHIELD] 已清理 {cleaned_count} 个临时文件")
        
        # 清空列表
        self._temp_files.clear()
    
    def _extract_ocr_info(self, screenshot_path: Optional[Path]) -> Optional[str]:
        """
        使用OCR提取截图中的文本信息（用于不支持视觉的模型）
        
        Args:
            screenshot_path: 截图文件路径
            
        Returns:
            OCR提取的文本信息，失败返回None
        """
        if not screenshot_path or not self.ocr_helper:
            return None
        
        try:
            # 读取图片并编码
            with open(screenshot_path, "rb") as f:
                image_bytes = f.read()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            
            # 使用OCR提取文本
            if hasattr(self.ocr_helper, 'extract_text'):
                ocr_text = self.ocr_helper.extract_text(image_base64)
                if ocr_text:
                    return f"页面文本内容:\n{ocr_text[:1000]}"  # 限制长度
        except Exception as e:
            logger.warning(f"OCR提取失败: {e}")
        
        return None
    
    def _build_reflection_prompt(self, step: Dict[str, Any], error: str, context: str, screenshot_data: Optional[str] = None, screenshot_info: Optional[Dict[str, Any]] = None) -> str:
        # 构建基础提示词
        prompt = f"""
The following agent step failed during execution.
Please analyze the error and provide a fixed version of the step if possible.

**Failed Step**:
{json.dumps(step, indent=2, ensure_ascii=False)}

**Error Message**:
{error}

**Context**:
{context}
"""
        
        # 如果有截图，添加视觉定位说明
        if screenshot_data:
            # 获取截图尺寸信息（用于坐标归一化）
            screenshot_width = screenshot_info.get("screenshot_width", 0) if screenshot_info else 0
            screenshot_height = screenshot_info.get("screenshot_height", 0) if screenshot_info else 0
            
            # 构建视口信息提示
            viewport_warning = ""
            if screenshot_width > 0:
                # 检测是否是Retina屏幕（截图宽度 > 1920 通常是Retina）
                if screenshot_width > 1920:
                    # 估算CSS视口宽度（通常是截图宽度的一半）
                    estimated_viewport_width = screenshot_width // 2
                    viewport_warning = f"""
**⚠️ CRITICAL: Retina Screen Coordinate Scaling (Retina屏幕坐标缩放)**:
- Screenshot size: {screenshot_width}x{screenshot_height} pixels (物理像素)
- Estimated viewport size: ~{estimated_viewport_width}x{screenshot_height // 2} pixels (CSS像素)
- **You MUST return coordinates in CSS pixels, NOT screenshot pixels**
- **Conversion formula**: CSS_x = Screenshot_x / 2, CSS_y = Screenshot_y / 2
- **Example**: If password field appears at x=2000 in screenshot, return x=1000 (CSS coordinate)
- **Safe range**: Keep coordinates within 0-{estimated_viewport_width} for width, 0-{screenshot_height // 2} for height
"""
                else:
                    viewport_warning = f"""
**⚠️ Coordinate Format (坐标格式)**:
- Screenshot size: {screenshot_width}x{screenshot_height} pixels
- Browser viewport is typically 1920x1080 or 1440x900 (CSS pixels)
- **Return coordinates in CSS pixels, matching the browser viewport**
- **Safe range**: Keep coordinates within 0-1920 for width, 0-1080 for height
"""
            
            # 构建视觉定位提示（包含视口警告）
            visual_grounding_prompt = f"""
**📸 Visual Grounding (视觉定位)**:
A screenshot of the error page has been provided. Use it to:
1. **Locate elements visually**: If selectors failed (e.g., "未找到元素", "ElementNotFound"), analyze the screenshot to find the target element.
2. **Use coordinates as fallback**: If you cannot find a reliable selector, you can use coordinate-based operations:
   - For browser click: `{{"type": "browser_click", "params": {{"x": 100, "y": 200}}}}`
   - For browser fill (click + type): `{{"type": "browser_fill", "params": {{"x": 500, "y": 300, "value": "password123"}}}}` (系统会自动点击坐标并输入文本)
   - For system operations: `{{"type": "mouse_click", "params": {{"x": 100, "y": 200}}}}`
3. **Identify form fields**: Look for "密码" (password), "用户名" (username), "登录" (login) buttons visually.
4. **⚠️ CRITICAL: Coordinate Format (坐标格式)**:
   - **Return coordinates in CSS pixels (视口坐标系), NOT screenshot pixels**
   - **Retina屏幕警告**: Mac Retina屏幕的截图可能是2880px宽，但浏览器视口只有1440px宽
   - **坐标归一化**: 如果截图是2880px宽，但视口是1440px，请将坐标除以2
   - **安全范围**: 确保坐标在视口范围内（通常 0-1920 for width, 0-1080 for height）
   - **示例**: 如果截图显示密码框在x=2000（截图像素），但视口是1440px，返回x=1000（CSS像素）
{viewport_warning}

**Example of coordinate-based fill fix**:
If the original step was:
```json
{{"type": "browser_fill", "params": {{"selector": "input[name='password']", "value": "123456"}}}}
```
And the selector failed, you can fix it to (single step, click + type):
```json
{{"type": "browser_fill", "params": {{"x": 500, "y": 300, "value": "123456", "visual_description": "位于页面中心偏左的白色输入框，标签为'密码'"}}}}
```
The system will automatically click at (500, 300) and type the text.
"""
            prompt += visual_grounding_prompt
            
            prompt += """
**⚠️ CRITICAL: Visual Description Requirement (视觉特征描述要求)**:
When returning coordinates, you **MUST** also include a `visual_description` field in the params that describes the visual characteristics of the element at that location. This helps with:
- Human verification (日志中可以看到视觉特征)
- Automatic secondary confirmation (自动二次确认)
- Debugging (调试时更容易定位问题)

**Visual Description Format**:
- Describe the element's appearance: color, size, position relative to page
- Describe nearby elements or labels: "密码输入框", "登录按钮", "白色背景"
- Example: "位于页面中心偏左的白色输入框，标签为'密码'，下方有'忘记密码'链接"

**Important**: 
- When using coordinates, ensure they are accurate by analyzing the screenshot carefully
- Always return CSS pixel coordinates, not screenshot pixel coordinates
- **Always include `visual_description` when using coordinates** for better traceability
- For form filling, prefer `browser_fill` with coordinates over `browser_click` + `keyboard_type` (single step is more reliable)
"""
        
        prompt += """
**Instructions**:
1. Analyze why the step failed (e.g., SyntaxError, FileNotFoundError, Invalid Parameter, ElementNotFound).
2. If the error is specific to Python script content (e.g., SyntaxError, missing import), rewrite the 'code' or 'script' parameter in the `modified_step`.
3. If the path was wrong, try to correct it based on common conventions or safety rules (e.g. use `~/Desktop`).
4. **For browser errors with selectors**: If you have a screenshot, analyze it visually to find the correct selector or use coordinates.
5. **Important**: Return a JSON object with the following structure:
{{
    "is_retryable": boolean,      // Can we try again with a fix?
    "reason": "string",           // Brief explanation of the fix
    "modified_step": object|null  // The complete, corrected step object (or null if not retryable)
}}

**Rules for Fixes**:
- If it's a Python Syntax Error, fix the code.
- If it's a "File Not Found" for a screenshot/download, ensure the path exists or use a more robust path.
- If it's a browser selector error and you have a screenshot, analyze the screenshot to find the correct selector or coordinates.
- Keep the `type` of the step the same unless the tool itself was wrong.
- **For coordinate-based fixes**: You can change `browser_fill` to `browser_click` + `keyboard_type` if the selector is unreliable.

**NON-RETRYABLE ERRORS (Set is_retryable: false)**:
These errors require **user configuration** and cannot be fixed by modifying the step:
- **Configuration errors**: Missing API Key, wrong provider/model configuration (e.g., "DeepSeek 不支持视觉功能", "VLM不可用：未配置API Key")
- **Missing dependencies**: Missing Python packages that require manual installation (e.g., "ddddocr 未安装", "pip install ddddocr")
- **System requirements**: Missing system tools or permissions that require user action
- **Invalid configuration**: Provider/model mismatch (e.g., using DeepSeek for vision tasks)

**When you see these errors**:
- Set `is_retryable: false`
- Set `modified_step: null`
- In `reason`, explain: "This error requires user configuration. [具体说明需要用户做什么]"

**Examples of NON-RETRYABLE errors**:
- "VLM不可用：DeepSeek 不支持视觉功能" → `is_retryable: false` (用户需要切换模型)
- "OCR不可用：ddddocr 未安装" → `is_retryable: false` (用户需要安装依赖)
- "视觉分析失败：VLM和OCR均不可用" + 包含配置建议 → `is_retryable: false` (用户需要配置)

**CRITICAL: Parameter Extraction Rules**:
- **NEVER use placeholders** like `[REPLACE_WITH_ACTUAL_APP_NAME]`, `extract_from_context_or_ask_user`, or any text containing `[ ]` brackets.
- **ALWAYS extract real values** from the `Context` or `Failed Step`:
  - If `app_name` is missing, extract it from the original instruction in Context (e.g., "打开汽水音乐" → "汽水音乐").
  - If `file_path` is missing, extract it from Context or use safe defaults (e.g., `~/Desktop`).
  - If you cannot find the real value in Context, set `is_retryable: false` and explain why.
- **Forbidden patterns** (DO NOT USE):
  - `[REPLACE_WITH_ACTUAL_APP_NAME]`
  - `extract_from_context_or_ask_user`
  - `[ANY_TEXT_IN_BRACKETS]`
  - `placeholder`, `TODO`, `FIXME`
- **If a required parameter is missing and cannot be extracted**:
  - Set `is_retryable: false`
  - In `reason`, explain: "Cannot extract [parameter_name] from context. User must provide it explicitly."
- **Example of CORRECT fix**:
  - Error: "缺少app_name参数"
  - Context: "用户指令: 打开汽水音乐"
  - Fix: `{{"params": {{"app_name": "汽水音乐"}}}}` ✅
- **Example of WRONG fix**:
  - Fix: `{{"params": {{"app_name": "[REPLACE_WITH_ACTUAL_APP_NAME]"}}}}` ❌
"""
