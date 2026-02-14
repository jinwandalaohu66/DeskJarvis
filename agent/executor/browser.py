"""
浏览器执行器：使用Playwright控制浏览器

遵循 docs/ARCHITECTURE.md 中的Executor模块规范
"""

# === 在导入 Playwright 之前应用 nest_asyncio ===
# 这允许 Playwright 的同步 API 在 asyncio 事件循环中使用
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    # nest_asyncio 未安装，会在启动时给出明确错误提示
    pass

from typing import Dict, Any, Optional, Callable, Tuple
import logging
import time
import base64
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page
from agent.tools.exceptions import BrowserError, TaskInterruptedException
from agent.tools.config import Config
from agent.user_input import UserInputManager
from agent.executor.browser_state_manager import BrowserStateManager
from agent.executor.ocr_helper import OCRHelper
from agent.executor.base_executor import BaseExecutor

logger = logging.getLogger(__name__)


class BrowserExecutor(BaseExecutor):
    """
    浏览器执行器：使用Playwright执行浏览器操作
    
    职责：
    - 控制独立headless浏览器实例
    - 执行导航、点击、填写等操作
    - 下载文件
    - 截图（用于调试）
    - 处理登录和验证码（请求用户输入）
    """
    
    def __init__(self, config: Config, emit_callback: Optional[Callable] = None):
        """
        初始化浏览器执行器
        
        Args:
            config: 配置对象
            emit_callback: 事件发送回调函数
        """
        super().__init__(config, emit_callback)
        self.playwright = None
        # 注意：使用 launch_persistent_context 后，不再有 browser 对象
        # self.browser: Optional[Browser] = None  # 已废弃，使用持久化上下文
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.download_path = config.sandbox_path / "downloads"
        self.download_path.mkdir(parents=True, exist_ok=True)
        
        # 持久化浏览器配置文件路径
        browser_profile_path = Path.home() / ".deskjarvis" / "browser_profile"
        browser_profile_path.mkdir(parents=True, exist_ok=True)
        self.browser_profile_path = browser_profile_path
        
        # 🔴 CRITICAL: 停止事件（threading.Event），用于中断长时间操作
        self.stop_event = threading.Event()
        
        # 用户输入管理器（停止检查函数和 stop_event 将在 execute_step 时动态设置）
        self.user_input_manager = UserInputManager(
            emit_callback=emit_callback,
            stop_event=self.stop_event  # 传递 stop_event
        )
        self._check_stop_callback: Optional[Callable] = None
        
        # 浏览器状态管理器（Cookie持久化）
        self.state_manager = BrowserStateManager()
        
        # OCR助手（验证码识别）
        self.ocr_helper = OCRHelper()
        
        # 设备像素比缓存（用于坐标校正）
        self._device_pixel_ratio: Optional[float] = None
        
        logger.info(f"浏览器执行器已初始化，下载目录: {self.download_path}")
        logger.info(f"浏览器配置文件路径: {self.browser_profile_path}")
    
    def _apply_stealth_mode(self) -> None:
        """
        应用 Stealth 模式（隐藏自动化特征）
        
        尝试使用 playwright-stealth（如果可用），否则使用手动实现
        """
        try:
            # 尝试使用 playwright-stealth（如果已安装）
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(self.page)
                logger.info("[SECURITY_SHIELD] 已应用 playwright-stealth 模式")
                return
            except ImportError:
                # playwright-stealth 未安装，使用手动实现
                logger.debug("[SECURITY_SHIELD] playwright-stealth 未安装，使用手动 Stealth 实现")
                pass
        except Exception as e:
            logger.warning(f"[SECURITY_SHIELD] playwright-stealth 应用失败，使用手动实现: {e}")
        
        # === 手动 Stealth 实现 ===
        stealth_script = """
        // 1. 隐藏 webdriver 属性
        Object.defineProperty(navigator, 'webdriver', { 
            get: () => undefined 
        });
        
        // 2. 伪造 Chrome 对象
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // 3. 伪造权限查询
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // 4. 伪造插件
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // 5. 伪造语言
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en-US', 'en']
        });
        
        // 6. 覆盖 toString 方法（防止检测）
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel Iris OpenGL Engine';
            }
            return getParameter(parameter);
        };
        
        // 7. 伪造 Canvas 指纹
        const toBlob = HTMLCanvasElement.prototype.toBlob;
        const toDataURL = HTMLCanvasElement.prototype.toDataURL;
        const getImageData = CanvasRenderingContext2D.prototype.getImageData;
        
        // 8. 隐藏自动化特征
        Object.defineProperty(navigator, 'webdriver', { 
            get: () => false 
        });
        """
        
        self.page.add_init_script(stealth_script)
        logger.info("[SECURITY_SHIELD] 已应用手动 Stealth 模式")
    
    def _get_device_pixel_ratio(self) -> float:
        """
        获取设备像素比（Device Pixel Ratio）
        
        用于坐标比例校正（Retina 屏幕等）
        
        Returns:
            设备像素比，默认 1.0
        """
        if self._device_pixel_ratio is not None:
            return self._device_pixel_ratio
        
        try:
            if self.page:
                dpr = self.page.evaluate("window.devicePixelRatio || 1")
                self._device_pixel_ratio = float(dpr)
                logger.debug(f"[SECURITY_SHIELD] 设备像素比: {self._device_pixel_ratio}")
                return self._device_pixel_ratio
        except Exception as e:
            logger.warning(f"[SECURITY_SHIELD] 获取设备像素比失败: {e}")
        
        # 默认值
        self._device_pixel_ratio = 1.0
        return 1.0
    
    def _correct_coordinates(self, x: float, y: float) -> Tuple[float, float]:
        """
        校正坐标（根据设备像素比）
        
        Args:
            x: 原始 X 坐标
            y: 原始 Y 坐标
            
        Returns:
            校正后的 (x, y) 坐标
        """
        dpr = self._get_device_pixel_ratio()
        
        # 如果 DPR > 1（Retina 屏幕），坐标需要除以 DPR
        # 因为 Playwright 的坐标系统是基于 CSS 像素的，而不是物理像素
        if dpr > 1.0:
            corrected_x = x / dpr
            corrected_y = y / dpr
            logger.debug(f"[SECURITY_SHIELD] 坐标校正: ({x}, {y}) -> ({corrected_x:.2f}, {corrected_y:.2f}) [DPR={dpr}]")
            return corrected_x, corrected_y
        
        return x, y
    
    def start(self) -> None:
        """
        启动浏览器实例（使用持久化上下文，保存 Cookie 和 Session）
        
        Raises:
            BrowserError: 当启动失败时
        """
        try:
            logger.info("正在启动浏览器（headless 后台模式，持久化上下文）...")
            
            # === 强制应用 nest_asyncio（如果检测到事件循环）===
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # 检测到运行中的事件循环
                logger.info("检测到 asyncio 事件循环，强制应用 nest_asyncio")
                try:
                    import nest_asyncio
                    # 即使之前已经应用过，再次应用也是安全的（幂等操作）
                    nest_asyncio.apply()
                    logger.info("✅ nest_asyncio 已应用，允许嵌套事件循环")
                except ImportError:
                    error_msg = (
                        "检测到 asyncio 事件循环，但 nest_asyncio 未安装。"
                        "请运行: pip install nest-asyncio"
                    )
                    logger.error(error_msg)
                    raise BrowserError(error_msg)
            except RuntimeError:
                # 没有运行中的事件循环，可以直接使用同步 API
                logger.debug("未检测到 asyncio 事件循环，直接使用同步 API")
                pass
            
            # === 正常启动 ===
            # 注意：即使检测到事件循环，nest_asyncio 应该已经应用，可以正常启动
            try:
                self.playwright = sync_playwright().start()
            except RuntimeError as e:
                if "asyncio loop" in str(e).lower() or "async" in str(e).lower():
                    # 如果仍然报错，说明 nest_asyncio 没有生效
                    error_msg = (
                        f"Playwright 启动失败: {e}\n"
                        "即使已应用 nest_asyncio，仍然无法在事件循环中使用同步 API。\n"
                        "这可能是因为 nest_asyncio 应用时机不对，或者 Playwright 版本问题。\n"
                        "请尝试：\n"
                        "1. 确保 nest-asyncio 已安装: pip install nest-asyncio\n"
                        "2. 升级 Playwright: pip install --upgrade playwright"
                    )
                    logger.error(error_msg)
                    raise BrowserError(error_msg) from e
                raise
            
            # 使用 launch_persistent_context 创建持久化上下文
            # 这样 Cookie、Session、LocalStorage 等会自动保存和恢复
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.browser_profile_path),
                headless=True,  # 强制 headless 模式，不显示浏览器窗口
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-CN",
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-gpu",  # 禁用 GPU，确保 headless 模式稳定
                    "--disable-dev-shm-usage",  # 避免共享内存问题
                    "--no-first-run",  # 跳过首次运行设置
                    "--no-default-browser-check",  # 跳过默认浏览器检查
                ]
            )
            
            # launch_persistent_context 返回的是 BrowserContext，不是 Browser
            # 所以不需要 self.browser，直接使用 self.context
            self.page = self.context.new_page()
            
            # === Stealth 模式：隐藏自动化特征 ===
            self._apply_stealth_mode()
            
            logger.info(f"✅ 浏览器已启动（持久化上下文: {self.browser_profile_path}，Stealth 模式已启用）")
            logger.info("💡 Cookie 和 Session 将自动保存，下次启动时自动恢复登录状态")
        except Exception as e:
            error_msg = f"启动浏览器失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e
    
    def _start_in_thread(self) -> None:
        """
        在单独的线程中启动 Playwright（避免与 asyncio 事件循环冲突）
        
        注意：由于 Playwright 对象不能跨线程使用，此方法会创建一个线程本地存储，
        所有后续操作都需要在同一个线程中执行。
        """
        import queue
        import threading
        
        # 使用线程本地存储来保存 Playwright 对象
        self._playwright_thread_local = threading.local()
        
        result_queue = queue.Queue()
        error_queue = queue.Queue()
        
        def start_playwright():
            """在单独线程中运行 Playwright 启动代码"""
            try:
                playwright = sync_playwright().start()
                
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.browser_profile_path),
                    headless=True,
                    accept_downloads=True,
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="zh-CN",
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ]
                )
                
                page = context.new_page()
                
                # 将对象保存到线程本地存储
                self._playwright_thread_local.playwright = playwright
                self._playwright_thread_local.context = context
                self._playwright_thread_local.page = page
                
                # 将对象放入队列（用于验证启动成功）
                result_queue.put((playwright, context, page))
            except Exception as e:
                error_queue.put(e)
        
        # 启动线程
        thread = threading.Thread(target=start_playwright, daemon=False)
        thread.start()
        thread.join(timeout=30)  # 最多等待30秒
        
        if thread.is_alive():
            raise BrowserError("启动浏览器超时（超过30秒）")
        
        # 检查错误
        if not error_queue.empty():
            error = error_queue.get()
            raise BrowserError(f"启动浏览器失败: {error}") from error
        
        # 获取结果（验证启动成功）
        if result_queue.empty():
            raise BrowserError("启动浏览器失败: 线程未返回结果")
        
        # 注意：不能直接使用队列中的对象，因为它们属于另一个线程
        # 我们需要使用线程本地存储中的对象
        # 但由于后续操作在主线程中，我们需要一个不同的策略
        
        # 实际上，Playwright 对象不能跨线程使用
        # 所以我们需要确保所有操作都在同一个线程中
        # 但这会导致架构复杂化
        
        # 注意：此方法已废弃，因为 Playwright 对象不能跨线程使用
        # 现在使用 nest_asyncio 来处理 asyncio 事件循环冲突
        raise BrowserError(
            "此方法已废弃。请确保已安装 nest_asyncio：pip install nest-asyncio"
        )
    
    def stop(self) -> None:
        """停止浏览器实例"""
        try:
            # 使用持久化上下文时，关闭 context 即可（会自动保存状态）
            if self.context:
                self.context.close()
                logger.info("浏览器上下文已关闭（状态已保存）")
            # launch_persistent_context 不返回 browser 对象，所以不需要关闭 browser
            if self.playwright:
                self.playwright.stop()
            logger.info("浏览器已停止")
        except Exception as e:
            logger.warning(f"停止浏览器时出错: {e}")
    
    def execute_step(self, step: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行单个任务步骤
        
        Args:
            step: 任务步骤，包含type、action、params等
            context: 上下文信息（可选，用于传递浏览器状态等）
        
        Returns:
            执行结果，包含success、message、data等
        
        Raises:
            BrowserError: 当执行失败时
        """
        # 自动启动浏览器（如果未启动）- 确保使用 headless 模式
        if not self.page:
            logger.info("浏览器未启动，自动在后台启动 headless 浏览器...")
            self.start()
        
        # 🔴 CRITICAL: 在执行前检查停止标志
        if context:
            check_stop = context.get("_check_stop")
            if check_stop and callable(check_stop):
                self._check_stop_callback = check_stop
                if check_stop():
                    logger.info("任务在执行前已被停止")
                    from agent.tools.exceptions import TaskInterruptedException
                    raise TaskInterruptedException("任务已停止")
        
        # 🔴 CRITICAL: 在执行前检查停止标志（支持 stop_event 和回调函数）
        if context:
            # 优先检查 stop_event（threading.Event）
            stop_event = context.get("_stop_event")
            if stop_event and isinstance(stop_event, threading.Event):
                self.stop_event = stop_event
                self.user_input_manager.stop_event = stop_event  # 同步更新 UserInputManager
                if stop_event.is_set():
                    logger.info("任务在执行前已被停止（通过 stop_event）")
                    raise TaskInterruptedException("任务已停止")
            
            # 检查回调函数（向后兼容）
            check_stop = context.get("_check_stop")
            if check_stop and callable(check_stop):
                self._check_stop_callback = check_stop
                self.user_input_manager.check_stop = check_stop  # 同步更新 UserInputManager
                if check_stop():
                    logger.info("任务在执行前已被停止（通过回调函数）")
                    raise TaskInterruptedException("任务已停止")
        
        self._log_execution_start(step)
        step_type = step.get("type")
        params = step.get("params", {})
        
        try:
            if step_type == "browser_navigate":
                return self._navigate(params)
            elif step_type == "browser_click":
                return self._click(params)
            elif step_type == "browser_fill":
                return self._fill(params)
            elif step_type == "browser_wait":
                return self._wait(params)
            elif step_type == "browser_check_element":
                return self._check_element(params)
            elif step_type == "browser_screenshot":
                return self._screenshot(params)
            elif step_type == "download_file":
                return self._download_file(params)
            elif step_type == "request_login":
                return self._request_login(params)
            elif step_type == "request_captcha":
                return self._request_captcha(params)
            elif step_type == "request_qr_login":
                return self._request_qr_login(params)
            elif step_type == "fill_login":
                return self._fill_login(params)
            elif step_type == "fill_captcha":
                return self._fill_captcha(params)
            else:
                raise BrowserError(f"未知的步骤类型: {step_type}")
                
        except TaskInterruptedException as e:
            logger.info(f"任务已中断: {e}")
            # 不清理浏览器上下文，因为可能还有其他操作需要浏览器
            # 只是重新抛出异常，让上层处理
            raise
        except Exception as e:
            logger.error(f"执行步骤失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"执行失败: {e}",
                "data": None
            }
    
    def _navigate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        导航到URL（只能用于HTTP/HTTPS URL，不能用于本地文件路径）
        
        Args:
            params: 参数字典，包含url
        
        Returns:
            执行结果字典
        
        Raises:
            BrowserError: 当导航失败时
        """
        url = params.get("url")
        if not url:
            raise BrowserError("导航参数缺少url")
        
        # 检查是否是本地文件路径
        if url.startswith("file://") or url.startswith("/"):
            raise BrowserError(
                f"browser_navigate 不能用于本地文件路径: {url}。"
                f"请使用 open_folder 工具打开本地文件夹。"
            )
        
        try:
            logger.info(f"导航到: {url}")
            
            # 🔴 CRITICAL: 在执行导航前检查停止标志
            if self.stop_event and self.stop_event.is_set():
                logger.info("导航操作已停止")
                from agent.tools.exceptions import TaskInterruptedException
                raise TaskInterruptedException("任务已停止")
            
            # 新增：尝试加载保存的 cookies（Cookie 持久化）
            try:
                if self.state_manager.has_saved_state(url):
                    saved_cookies = self.state_manager.load_cookies(url)
                    if saved_cookies:
                        self.context.add_cookies(saved_cookies)
                        logger.info(f"已加载 {len(saved_cookies)} 个保存的 cookies")
            except Exception as cookie_err:
                logger.warning(f"加载 cookies 失败: {cookie_err}")
            
            # 🔴 CRITICAL: 再次检查停止标志（在 goto 前）
            if self.stop_event and self.stop_event.is_set():
                logger.info("导航操作已停止（在 goto 前）")
                from agent.tools.exceptions import TaskInterruptedException
                raise TaskInterruptedException("任务已停止")
            
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 🔴 CRITICAL: 导航完成后立即检查停止标志
            if self.stop_event and self.stop_event.is_set():
                logger.info("导航操作已停止（在 goto 后）")
                from agent.tools.exceptions import TaskInterruptedException
                raise TaskInterruptedException("任务已停止")
            
            # 额外等待一下让页面完全渲染
            self.page.wait_for_timeout(1000)
            
            # 🔴 CRITICAL: 等待后再次检查停止标志
            if self.stop_event and self.stop_event.is_set():
                logger.info("导航操作已停止（在等待后）")
                from agent.tools.exceptions import TaskInterruptedException
                raise TaskInterruptedException("任务已停止")
            
            # 尝试关闭常见的弹窗/Cookie提示
            try:
                # 针对百度，执行特殊处理
                if "baidu.com" in url:
                    self._handle_baidu_popups()
                else:
                    # 其他网站按 Escape 关闭弹窗
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(300)
            except Exception:
                pass
            
            logger.info(f"✅ 已导航到: {url}")
            
            return {
                "success": True,
                "message": f"已导航到: {url}",
                "data": {"url": url}
            }
        except Exception as e:
            error_msg = f"导航失败: {url} - {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e
    
    def _click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        点击元素（增强版：支持文本定位 + 等待可见 + 滚动 + 多元素处理 + 坐标点击）
        
        Args:
            params: 参数字典
                - selector: CSS选择器（可选）
                - text: 文本内容（可选，优先使用）
                - x: X坐标（可选，用于坐标点击）
                - y: Y坐标（可选，用于坐标点击）
                - timeout: 超时时间（毫秒，默认60000）
        
        Returns:
            执行结果字典
        
        Raises:
            BrowserError: 当点击失败时
        """
        selector = params.get("selector")
        text = params.get("text")  # 新增：文本定位参数
        x = params.get("x")
        y = params.get("y")
        timeout = params.get("timeout", 60000)
        
        # 如果提供了坐标，直接使用坐标点击（视觉定位的降级方案）
        if x is not None and y is not None:
            try:
                # === 坐标比例校正 ===
                corrected_x, corrected_y = self._correct_coordinates(x, y)
                
                # 获取视口大小（用于坐标验证和调试）
                viewport = self.page.viewport_size
                viewport_width = viewport.get("width", 1920) if viewport else 1920
                viewport_height = viewport.get("height", 1080) if viewport else 1080
                
                # 验证坐标是否在视口范围内（使用校正后的坐标）
                if corrected_x < 0 or corrected_x > viewport_width or corrected_y < 0 or corrected_y > viewport_height:
                    logger.warning(f"坐标 ({corrected_x:.2f}, {corrected_y:.2f}) 超出视口范围 ({viewport_width}x{viewport_height})，但仍尝试点击")
                
                logger.info(f"使用坐标点击: ({x}, {y}) -> ({corrected_x:.2f}, {corrected_y:.2f}) (Viewport: {viewport_width}x{viewport_height})")
                
                # 执行坐标点击（使用校正后的坐标）
                self.page.mouse.click(corrected_x, corrected_y)
                logger.info("✅ 已成功点击坐标")
                return {
                    "success": True,
                    "message": f"已点击坐标 ({corrected_x:.2f}, {corrected_y:.2f})",
                    "data": {"x": corrected_x, "y": corrected_y, "original_x": x, "original_y": y, "method": "coordinate", "viewport": {"width": viewport_width, "height": viewport_height}, "dpr": self._get_device_pixel_ratio()}
                }
            except Exception as e:
                error_msg = f"坐标点击失败: ({x}, {y}) - {str(e)}"
                logger.error(error_msg, exc_info=True)
                # 失败时截图
                screenshot_path = self.download_path / f"click_error_{int(time.time())}.png"
                try:
                    self.page.screenshot(path=str(screenshot_path), full_page=True)
                    logger.error(f"坐标点击失败，已截图: {screenshot_path}")
                except Exception:
                    pass
                raise BrowserError(error_msg) from e
        
        if not selector and not text:
            raise BrowserError("点击参数缺少selector、text或坐标(x,y)")
        
        try:
            # 步骤1: 根据参数类型选择定位方式
            if text:
                # 使用文本定位（优先）
                locator = self.page.get_by_text(text, exact=False)
                logger.info(f"使用文本定位: {text}")
            elif selector.startswith("text="):
                # 支持 text= 格式
                text_content = selector[5:].strip()
                locator = self.page.get_by_text(text_content, exact=False)
                logger.info(f"使用text=格式定位: {text_content}")
            elif ":contains(" in selector or "contains" in selector.lower():
                # 检测到 contains 语法，提取文本内容
                import re
                match = re.search(r":contains\(['\"](.*?)['\"]\)", selector)
                if match:
                    text_content = match.group(1)
                    base_selector = re.sub(r":contains\(['\"].*?['\"]\)", "", selector)
                    base_locator = self.page.locator(base_selector)
                    locator = base_locator.filter(has_text=text_content)
                else:
                    locator = self.page.locator(selector)
            else:
                # 使用CSS选择器
                logger.info(f"使用CSS选择器定位: {selector}")
                locator = self.page.locator(selector)
            
            # 步骤2: 等待元素出现并可见（关键修复）
            logger.info("等待元素可见...")
            
            # 检查有多少个匹配元素
            # 使用 all() 方法获取所有匹配的元素，然后获取长度（更可靠）
            try:
                all_elements = locator.all()
                count = len(all_elements)
            except Exception as e:
                # 如果 all() 失败，尝试使用 count 属性
                try:
                    count_value = locator.count
                    # 检查是否是方法（callable）还是属性值
                    if callable(count_value):
                        count = count_value()
                    else:
                        count = count_value
                    # 确保是整数
                    count = int(count) if isinstance(count, (int, float)) else 1
                except Exception:
                    logger.warning(f"无法确定匹配元素数量，假设至少有1个: {e}")
                    count = 1
            
            logger.info(f"找到 {count} 个匹配元素")
            
            if count == 0:
                # 元素不存在，尝试 OCR 视觉对齐
                logger.warning("[SECURITY_SHIELD] 未找到 DOM 元素，尝试 OCR 视觉对齐...")
                
                # 如果提供了文本，尝试使用 OCR 查找坐标
                if text:
                    try:
                        # 截图
                        screenshot_path = self.download_path / f"click_ocr_{int(time.time())}.png"
                        self.page.screenshot(path=str(screenshot_path), full_page=True)
                        
                        # 读取截图并转换为 base64
                        with open(screenshot_path, "rb") as f:
                            image_bytes = f.read()
                        image_base64 = base64.b64encode(image_bytes).decode()
                        
                        # 使用 OCR 查找文本坐标
                        ocr_result = self.ocr_helper.find_text_coordinates(image_base64, text, fuzzy_match=True)
                        
                        if ocr_result:
                            ocr_x = ocr_result["x"]
                            ocr_y = ocr_result["y"]
                            logger.info(f"[SECURITY_SHIELD] OCR找到文本 '{text}' 的坐标: ({ocr_x}, {ocr_y})")
                            
                            # 校正坐标并点击
                            corrected_x, corrected_y = self._correct_coordinates(ocr_x, ocr_y)
                            self.page.mouse.click(corrected_x, corrected_y)
                            
                            logger.info("✅ 已通过 OCR 视觉对齐成功点击")
                            return {
                                "success": True,
                                "message": f"已通过 OCR 视觉对齐点击文本 '{text}'",
                                "data": {
                                    "text": text,
                                    "x": corrected_x,
                                    "y": corrected_y,
                                    "original_x": ocr_x,
                                    "original_y": ocr_y,
                                    "method": "ocr_visual_alignment",
                                    "confidence": ocr_result.get("confidence", 0.0)
                                }
                            }
                        else:
                            logger.warning(f"[SECURITY_SHIELD] OCR未找到文本 '{text}'")
                    except Exception as ocr_err:
                        logger.warning(f"[SECURITY_SHIELD] OCR视觉对齐失败: {ocr_err}")
                
                # OCR 失败或未提供文本，截图并抛出错误
                screenshot_path = self.download_path / f"click_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                raise BrowserError(f"未找到元素，已截图: {screenshot_path}")
            
            # 确保 count 是整数
            count = int(count)
            
            # 步骤3: 选择第一个可见的元素（关键修复）
            # 如果多个匹配，优先选择可见的第一个
            visible_locator = None
            for i in range(min(count, 10)):  # 最多检查前10个
                try:
                    candidate = locator.nth(i)
                    # 检查是否可见（使用 Playwright 的可见性检查）
                    if candidate.is_visible(timeout=1000):
                        visible_locator = candidate
                        logger.info(f"选择第 {i+1} 个可见元素")
                        break
                except Exception:
                    continue
            
            if not visible_locator:
                # 如果都不可见，尝试滚动到第一个并等待
                logger.warning("所有匹配元素都不可见，尝试滚动到第一个元素")
                first_locator = locator.first
                # 滚动到元素（关键修复）
                first_locator.scroll_into_view_if_needed(timeout=timeout)
                # 再次等待可见
                first_locator.wait_for(state="visible", timeout=timeout)
                visible_locator = first_locator
            
            # 步骤4: 确保元素在视口内（滚动）
            visible_locator.scroll_into_view_if_needed(timeout=5000)
            
            # 步骤5: 等待元素稳定（可点击状态）
            visible_locator.wait_for(state="attached", timeout=5000)
            
            # 步骤6: 检查元素是否被遮挡（Overlay）
            try:
                # 检查元素是否可点击（未被遮挡）
                is_clickable = visible_locator.is_visible()
                if not is_clickable:
                    logger.warning("[SECURITY_SHIELD] 元素可能被遮挡，尝试关闭遮挡层...")
                    # 尝试关闭常见的遮挡层（弹窗、模态框等）
                    self._try_close_overlay()
            except Exception:
                pass
            
            # 步骤7: 执行点击（如果被遮挡，使用 force=True）
            logger.info("执行点击...")
            try:
                visible_locator.click(timeout=timeout)
            except Exception as e:
                # 如果点击失败，可能是被遮挡，尝试强制点击
                if "is not visible" in str(e).lower() or "obscured" in str(e).lower():
                    logger.warning("[SECURITY_SHIELD] 元素被遮挡，尝试强制点击...")
                    try:
                        # 先尝试关闭遮挡层
                        self._try_close_overlay()
                        # 再次尝试点击
                        visible_locator.click(timeout=timeout)
                    except Exception:
                        # 最后尝试强制点击
                        logger.warning("[SECURITY_SHIELD] 使用强制点击（force=True）")
                        visible_locator.click(timeout=timeout, force=True)
                else:
                    raise
            
            logger.info("✅ 已成功点击元素")
            
            return {
                "success": True,
                "message": "已点击元素",
                "data": {"selector": selector, "text": text, "matched_count": count}
            }
            
        except Exception as e:
            # 失败时自动截图（关键调试功能）
            screenshot_path = self.download_path / f"click_error_{int(time.time())}.png"
            try:
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                logger.error(f"点击失败，已截图: {screenshot_path}")
            except Exception:
                pass
            
            error_msg = f"点击元素失败: {selector or text} - {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e
    
    def _fill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        填写表单字段（支持选择器填充和坐标点击+键盘输入）
        
        Args:
            params: 参数字典
                - selector: CSS选择器（可选）
                - value: 要填写的值（必需）
                - x: X坐标（可选，用于坐标点击+输入）
                - y: Y坐标（可选，用于坐标点击+输入）
        """
        selector = params.get("selector")
        value = params.get("value")
        x = params.get("x")
        y = params.get("y")
        
        if value is None:
            raise BrowserError("填写参数缺少value")
        
        # === 视觉降级模式：坐标点击+键盘输入 ===
        if x is not None and y is not None:
            try:
                # === 坐标比例校正 ===
                corrected_x, corrected_y = self._correct_coordinates(x, y)
                
                # 获取视口大小（用于坐标验证和调试）
                viewport = self.page.viewport_size
                viewport_width = viewport.get("width", 1920) if viewport else 1920
                viewport_height = viewport.get("height", 1080) if viewport else 1080
                
                logger.info(f"使用坐标填表: ({x}, {y}) -> ({corrected_x:.2f}, {corrected_y:.2f}) -> '{value}' (Viewport: {viewport_width}x{viewport_height})")
                
                # 1. 移动鼠标并点击，激活输入框（使用校正后的坐标）
                self.page.mouse.click(corrected_x, corrected_y)
                
                # 2. 短暂等待，模拟人类反应，防止触发反爬
                self.page.wait_for_timeout(200)
                
                # 3. 清空现有内容（如果有）
                # macOS 使用 Meta+A (Command+A)，Windows/Linux 使用 Control+A
                import platform
                if platform.system() == "Darwin":  # macOS
                    self.page.keyboard.press("Meta+A")
                else:
                    self.page.keyboard.press("Control+A")
                self.page.wait_for_timeout(100)
                
                # 4. 模拟键盘输入（这比 fill 更像人，能绕过很多 React/Vue 的绑定问题）
                self.page.keyboard.type(str(value), delay=50)  # 添加延迟，更像人类输入
                
                logger.info("✅ 已成功通过坐标填表")
                return {
                    "success": True,
                    "message": f"已通过坐标 ({corrected_x:.2f}, {corrected_y:.2f}) 填写: {value}",
                    "data": {"x": corrected_x, "y": corrected_y, "original_x": x, "original_y": y, "value": value, "method": "coordinate_type", "dpr": self._get_device_pixel_ratio()}
                }
            except Exception as e:
                error_msg = f"坐标填表失败: ({x}, {y}) - {str(e)}"
                logger.error(error_msg, exc_info=True)
                # 失败时截图
                screenshot_path = self.download_path / f"fill_error_{int(time.time())}.png"
                try:
                    self.page.screenshot(path=str(screenshot_path), full_page=True)
                    logger.error(f"坐标填表失败，已截图: {screenshot_path}")
                except Exception:
                    pass
                raise BrowserError(error_msg) from e
        
        # === 正常模式：使用选择器填充 ===
        if not selector:
            raise BrowserError("填写参数缺少selector或坐标(x,y)")
        
        try:
            logger.info(f"填写字段: {selector} = {value}")
            
            # 先尝试等待元素可见
            try:
                self.page.wait_for_selector(selector, state="visible", timeout=5000)
            except Exception:
                # 如果等待失败，尝试关闭弹窗
                logger.info("元素不可见，尝试关闭可能的弹窗...")
                
                # 检查是否是百度页面
                current_url = self.page.url
                if "baidu.com" in current_url:
                    self._handle_baidu_popups()
                else:
                    try:
                        self.page.keyboard.press("Escape")
                        self.page.wait_for_timeout(500)
                    except Exception:
                        pass
                
                # 对于百度等网站，尝试备用选择器
                if selector == "#kw" or selector == "input[name='wd']":
                    backup_selectors = [
                        "#kw",
                        "input[name='wd']",
                        ".s_ipt",
                        "input.s_ipt",
                    ]
                    for backup in backup_selectors:
                        try:
                            elem = self.page.locator(backup).first
                            if elem.is_visible(timeout=2000):
                                selector = backup
                                logger.info(f"使用备用选择器: {backup}")
                                break
                        except Exception:
                            continue
            
            # 尝试填写
            try:
                self.page.fill(selector, str(value), timeout=10000)
            except Exception as fill_err:
                logger.info(f"fill 失败: {fill_err}，尝试其他方式...")
                
                # 方法2：使用 JavaScript 直接设置值
                try:
                    js_selectors = ["#kw", "input[name='wd']", ".s_ipt"]
                    for js_sel in js_selectors:
                        result = self.page.evaluate(f'''
                            (function() {{
                                var input = document.querySelector("{js_sel}");
                                if (input) {{
                                    input.value = "{value}";
                                    input.dispatchEvent(new Event("input", {{ bubbles: true }}));
                                    return true;
                                }}
                                return false;
                            }})()
                        ''')
                        if result:
                            logger.info(f"使用 JavaScript 成功填写: {js_sel}")
                            break
                    else:
                        raise Exception("JavaScript 填写也失败")
                except Exception as js_err:
                    # 方法3：点击后逐字输入
                    logger.info(f"JavaScript 失败: {js_err}，尝试 type 方式...")
                    try:
                        self.page.click(selector, timeout=5000, force=True)
                        self.page.keyboard.type(str(value), delay=50)
                    except Exception:
                        # 方法4：强制点击
                        self.page.evaluate('''
                            var input = document.querySelector("#kw") || document.querySelector("input[name='wd']");
                            if (input) {{ input.focus(); input.click(); }}
                        ''')
                        self.page.keyboard.type(str(value), delay=50)
            
            logger.info("✅ 已填写字段")
            
            return {
                "success": True,
                "message": f"已填写字段: {selector}",
                "data": {"selector": selector, "value": value}
            }
        except Exception as e:
            error_msg = f"填写字段失败: {selector} - {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e
    
    def _try_close_overlay(self) -> bool:
        """
        尝试关闭遮挡层（Overlay）
        
        常见的遮挡层包括：
        - 模态框（Modal）
        - 弹窗（Popup）
        - 通知横幅（Notification Banner）
        - Cookie 同意框
        
        Returns:
            是否成功关闭遮挡层
        """
        try:
            logger.info("[SECURITY_SHIELD] 尝试关闭遮挡层...")
            
            # 常见的关闭按钮选择器（按优先级排序）
            close_selectors = [
                # 通用关闭按钮
                "[aria-label*='close' i]",
                "[aria-label*='关闭' i]",
                "[aria-label*='Close' i]",
                ".close",
                ".close-btn",
                ".close-button",
                "[class*='close']",
                "[class*='Close']",
                # 模态框关闭按钮
                ".modal-close",
                ".modal .close",
                "[data-dismiss='modal']",
                # Cookie 同意框
                "#cookie-consent-close",
                ".cookie-consent-close",
                "[id*='cookie'][class*='close']",
                # 通知横幅
                ".notification-close",
                ".alert-close",
                "[class*='notification'][class*='close']",
            ]
            
            # 尝试点击关闭按钮
            for sel in close_selectors:
                try:
                    close_btn = self.page.locator(sel).first
                    if close_btn.is_visible(timeout=500):
                        close_btn.click(timeout=1000)
                        logger.info(f"[SECURITY_SHIELD] 已关闭遮挡层: {sel}")
                        self.page.wait_for_timeout(300)
                        return True
                except Exception:
                    continue
            
            # 尝试按 Escape 键（关闭模态框的通用方法）
            try:
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
                logger.debug("[SECURITY_SHIELD] 已按 Escape 键")
                return True
            except Exception:
                pass
            
            # 尝试点击页面背景（关闭模态框）
            try:
                # 点击页面中心（通常是模态框的背景）
                viewport = self.page.viewport_size
                center_x = viewport.get("width", 1920) // 2
                center_y = viewport.get("height", 1080) // 2
                self.page.mouse.click(center_x, center_y)
                self.page.wait_for_timeout(300)
                logger.debug("[SECURITY_SHIELD] 已点击页面背景")
                return True
            except Exception:
                pass
            
            logger.debug("[SECURITY_SHIELD] 无法关闭遮挡层")
            return False
        except Exception as e:
            logger.warning(f"[SECURITY_SHIELD] 关闭遮挡层时出错: {e}")
            return False
    
    def _handle_baidu_popups(self):
        """处理百度页面的各种弹窗"""
        logger.info("处理百度页面弹窗...")
        
        try:
            # 等待页面稳定
            self.page.wait_for_timeout(1000)
            
            # 1. 关闭登录弹窗（多种可能的关闭按钮）
            close_selectors = [
                "#TANGRAM__PSP_4__closeBtn",
                ".tang-pass-footerBar .close-btn",
                ".passport-login-pop .close",
                "[class*='close']",
                ".c-icon-close",
            ]
            for sel in close_selectors:
                try:
                    close_btn = self.page.locator(sel).first
                    if close_btn.is_visible(timeout=500):
                        close_btn.click(timeout=1000)
                        logger.info(f"已关闭弹窗: {sel}")
                        self.page.wait_for_timeout(300)
                        break
                except Exception:
                    continue
            
            # 2. 按 Escape 键
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
            
            # 3. 点击页面空白处
            try:
                self.page.mouse.click(10, 10)
                self.page.wait_for_timeout(200)
            except Exception:
                pass
            
            # 4. 如果搜索框还是不可见，尝试刷新页面
            try:
                kw_visible = self.page.locator("#kw").is_visible(timeout=1000)
                if not kw_visible:
                    logger.info("搜索框不可见，尝试刷新页面...")
                    self.page.reload(wait_until="domcontentloaded", timeout=10000)
                    self.page.wait_for_timeout(1000)
                    self.page.keyboard.press("Escape")
            except Exception:
                pass
                
        except Exception as e:
            logger.warning(f"处理百度弹窗时出错: {e}")
    
    def _wait(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """等待指定时间或条件"""
        timeout = params.get("timeout", 5000)
        
        try:
            logger.info(f"等待 {timeout} 毫秒...")
            self.page.wait_for_timeout(timeout)
            logger.info("✅ 等待完成")
            
            return {
                "success": True,
                "message": "等待完成",
                "data": {"timeout": timeout}
            }
        except Exception as e:
            error_msg = f"等待失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e

    def _check_element(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查页面元素是否存在/可见（用于兼容 planner 生成的 browser_check_element）。
        
        Params:
            - selector: CSS 选择器（可选）
            - text: 文本内容（可选，优先使用）
            - timeout: 超时时间（毫秒，默认5000）
            - state: "attached"/"visible"/"hidden"/"detached"（默认 visible）
        """
        selector = params.get("selector")
        text = params.get("text")
        timeout = params.get("timeout", 5000)
        state = params.get("state", "visible")

        if not selector and not text:
            raise BrowserError("检查参数缺少 selector 或 text")

        try:
            if text:
                locator = self.page.get_by_text(str(text)).first
                locator.wait_for(state=state, timeout=timeout)
                target = f"text={text}"
            else:
                self.page.wait_for_selector(str(selector), state=state, timeout=timeout)
                target = selector

            return {
                "success": True,
                "message": f"元素可用: {target}",
                "data": {"selector": selector, "text": text, "state": state}
            }
        except Exception as e:
            error_msg = f"元素不可用: {selector or text} - {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e
    
    def _screenshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        浏览器页面截图
        
        Args:
            params: 包含save_path（保存路径，可选）
                    - 可以是相对路径（相对于用户主目录）
                    - 可以是绝对路径（必须在用户主目录下）
                    - 支持 ~ 符号（如 ~/Desktop/github.png）
                    - 如果不指定，默认保存到沙盒下载目录
        """
        save_path_str = params.get("save_path")
        home = Path.home()
        
        if save_path_str:
            # 处理 ~ 符号
            if save_path_str.startswith("~/"):
                save_path_str = str(home / save_path_str[2:])
            elif save_path_str.startswith("~"):
                save_path_str = str(home / save_path_str[1:])
            
            save_path = Path(save_path_str)
            
            # 如果是相对路径，相对于用户主目录
            if not save_path.is_absolute():
                save_path = home / save_path
            
            save_path = save_path.resolve()
            
            # 安全：确保路径在用户主目录下
            try:
                save_path.relative_to(home)
            except ValueError:
                logger.warning(f"路径不在用户主目录下，使用默认路径: {save_path}")
                save_path = self.download_path / f"screenshot_{int(time.time())}.png"
        else:
            save_path = self.download_path / f"screenshot_{int(time.time())}.png"
        
        # 确保目录存在
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            logger.info(f"浏览器页面截图保存到: {save_path}")
            self.page.screenshot(path=str(save_path), full_page=True)
            logger.info("✅ 浏览器页面截图已保存")
            
            return {
                "success": True,
                "message": f"浏览器页面截图已保存: {save_path}",
                "data": {"path": str(save_path)}
            }
        except Exception as e:
            error_msg = f"浏览器页面截图失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e
    
    def _download_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        下载文件（通过点击下载链接，使用增强的点击逻辑）
        
        修复要点：
        1. 使用增强的点击逻辑（等待可见 + 滚动）
        2. 监听下载事件（page.expect_download）
        3. 保存到指定路径（支持 ~、相对路径、绝对路径）
        4. 自动创建目录
        5. 文件存在验证
        6. 截图调试
        7. 超时延长（默认60秒）
        
        Args:
            params: 参数字典
                - selector: CSS选择器或文本定位（必需）
                - save_path: 保存路径（支持 ~、相对路径、绝对路径）
                - timeout: 超时时间（毫秒，默认60000）
        
        Returns:
            执行结果字典
        
        Raises:
            BrowserError: 当下载失败时
        """
        selector = params.get("selector")
        text = params.get("text")  # 文本定位参数（优先使用）
        save_path = params.get("save_path")
        timeout = params.get("timeout", 60000)  # 默认60秒超时
        
        # selector 和 text 至少需要一个
        if not selector and not text:
            raise BrowserError("下载参数缺少selector或text，至少需要提供一个")
        
        try:
            # 步骤1: 解析保存路径（在点击前解析，以便提前创建目录）
            if save_path:
                # 处理中文"桌面"和英文"Desktop"
                save_path_normalized = save_path.strip()
                if save_path_normalized == "桌面" or save_path_normalized.lower() == "desktop":
                    file_path = Path.home() / "Desktop"
                    logger.info(f"检测到'桌面'或'Desktop'，解析为: {file_path}")
                elif save_path_normalized.startswith("~/"):
                    file_path = Path.home() / save_path_normalized[2:]
                elif save_path_normalized.startswith("~"):
                    file_path = Path.home() / save_path_normalized[1:]
                else:
                    file_path = Path(save_path_normalized)
                
                # 如果是相对路径，相对于用户主目录
                if not file_path.is_absolute():
                    file_path = Path.home() / file_path
                
                file_path = file_path.resolve()
                
                # 确保目录存在（如果路径是目录）
                if file_path.exists() and file_path.is_dir():
                    # 路径是目录，稍后会添加文件名
                    logger.info(f"目标保存目录: {file_path}")
                else:
                    # 路径可能是文件路径，确保父目录存在
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    logger.info(f"目标保存路径: {file_path}")
            else:
                # 如果没有指定路径，使用默认下载目录
                file_path = None
                logger.info("未指定保存路径，将使用默认下载目录")
            
            # 步骤2: 定位并点击下载链接
            logger.info(f"准备下载文件，点击链接: {selector or text}")
            
            # 定位元素（支持文本定位和CSS选择器）
            if text:
                # 使用文本定位（优先）
                locator = self.page.get_by_text(text, exact=False)
                logger.info(f"使用文本定位: {text}")
            elif selector and selector.startswith("text="):
                # 支持 text= 格式
                text_content = selector[5:].strip()
                locator = self.page.get_by_text(text_content, exact=False)
                logger.info(f"使用text=格式定位: {text_content}")
            elif selector:
                # 使用CSS选择器
                locator = self.page.locator(selector)
                logger.info(f"使用CSS选择器定位: {selector}")
            else:
                # 理论上不会到这里（前面已经检查过）
                raise BrowserError("下载参数缺少selector或text")
            
            # 检查有多少个匹配元素
            # 使用 all() 方法获取所有匹配的元素，然后获取长度（更可靠）
            try:
                all_elements = locator.all()
                count = len(all_elements)
            except Exception as e:
                # 如果 all() 失败，尝试使用 count 属性
                try:
                    count_value = locator.count
                    # 检查是否是方法（callable）还是属性值
                    if callable(count_value):
                        count = count_value()
                    else:
                        count = count_value
                    # 确保是整数
                    count = int(count) if isinstance(count, (int, float)) else 1
                except Exception:
                    logger.warning(f"无法确定匹配元素数量，假设至少有1个: {e}")
                    count = 1
            
            logger.info(f"找到 {count} 个匹配元素")
            
            if count == 0:
                screenshot_path = self.download_path / f"download_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                raise BrowserError(f"未找到下载链接: {selector or text}，已截图: {screenshot_path}")
            
            # 确保 count 是整数
            count = int(count)
            
            # 选择第一个可见的元素
            visible_locator = None
            for i in range(min(count, 10)):
                try:
                    candidate = locator.nth(i)
                    if candidate.is_visible(timeout=1000):
                        visible_locator = candidate
                        logger.info(f"选择第 {i+1} 个可见的下载链接")
                        break
                except Exception:
                    continue
            
            if not visible_locator:
                # 如果都不可见，尝试滚动到第一个并等待
                logger.warning("所有匹配元素都不可见，尝试滚动到第一个元素")
                visible_locator = locator.first
                visible_locator.scroll_into_view_if_needed(timeout=timeout)
                visible_locator.wait_for(state="visible", timeout=timeout)
            
            # 确保元素在视口内（滚动）
            visible_locator.scroll_into_view_if_needed(timeout=5000)
            
            # 等待元素稳定（可点击状态）
            visible_locator.wait_for(state="attached", timeout=5000)
            
            # 步骤3: 监听下载事件并点击
            logger.info(f"监听下载事件并点击: {selector or text}")
            with self.page.expect_download(timeout=timeout) as download_info:
                visible_locator.click(timeout=timeout)
            
            # 步骤4: 获取下载对象
            download = download_info.value
            # 在 Playwright 同步 API 中，suggested_filename 是属性，不是方法
            # 但为了兼容性，先检查是否是方法
            try:
                suggested_filename = download.suggested_filename  # 属性（同步 API）
                if callable(suggested_filename):
                    suggested_filename = suggested_filename()
            except Exception:
                suggested_filename = "download"
            logger.info(f"检测到下载: {suggested_filename}")
            
            # 步骤5: 确定最终保存路径
            if file_path:
                # 检查路径是否是目录
                is_directory = False
                if file_path.exists():
                    is_directory = file_path.is_dir()
                else:
                    # 如果路径不存在，检查是否有扩展名来判断
                    # 如果没有扩展名，可能是目录
                    if not file_path.suffix:
                        is_directory = True
                
                if is_directory:
                    # 路径是目录，添加下载的文件名
                    file_path = file_path / suggested_filename
                    logger.info(f"路径是目录，添加文件名: {file_path}")
                elif not file_path.suffix and suggested_filename:
                    # 如果路径没有扩展名，使用下载文件的扩展名
                    suggested = Path(suggested_filename)
                    file_path = file_path.with_suffix(suggested.suffix)
                    logger.info(f"路径缺少扩展名，添加扩展名: {file_path}")
                else:
                    # 路径已经是完整文件路径
                    logger.info(f"使用指定的完整文件路径: {file_path}")
            else:
                # 使用默认下载目录
                file_path = self.download_path / suggested_filename
                logger.info(f"使用默认下载目录: {file_path}")
            
            # 确保目录存在（再次检查，防止路径解析后目录不存在）
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 步骤6: 保存文件
            logger.info(f"正在保存文件到: {file_path}")
            download.save_as(str(file_path))
            
            # 步骤7: 验证文件是否存在
            if not file_path.exists():
                screenshot_path = self.download_path / f"download_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                raise BrowserError(f"文件保存失败，文件不存在: {file_path}，已截图: {screenshot_path}")
            
            file_size = file_path.stat().st_size
            logger.info(f"✅ 文件已下载: {file_path} (大小: {file_size} 字节)")
            
            return {
                "success": True,
                "message": f"文件已下载: {file_path}",
                "data": {
                    "path": str(file_path),
                    "size": file_size,
                    "filename": file_path.name
                }
            }
            
        except Exception as e:
            # 失败时自动截图（关键调试功能）
            screenshot_path = self.download_path / f"download_error_{int(time.time())}.png"
            try:
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                logger.error(f"下载失败，已截图: {screenshot_path}")
            except Exception:
                pass
            
            selector_str = selector or text or "未提供selector或text"
            error_msg = f"下载文件失败: {selector_str} - {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e
    
    def _handle_download(self, download) -> None:
        """处理下载事件"""
        # 在 Playwright 同步 API 中，suggested_filename 是属性，不是方法
        try:
            suggested_filename = download.suggested_filename if not callable(download.suggested_filename) else download.suggested_filename()
        except AttributeError:
            suggested_filename = "未知文件名"
        logger.info(f"检测到下载: {suggested_filename}")
    
    # ===== 登录和验证码处理 =====
    
    
    def _verify_login_success(self, initial_url: str, timeout: int = 15000) -> bool:
        """
        智能检测登录是否成功（多策略验证）
        
        Args:
            initial_url: 登录前的URL
            timeout: 超时时间（毫秒）
        
        Returns:
            True 如果检测到登录成功
        """
        logger.info("开始登录成功检测...")
        start_time = time.time()
        initial_cookie_count = len(self.context.cookies())
        
        while (time.time() - start_time) * 1000 < timeout:
            try:
                # 策略1: URL变化（跳转到登录后页面）
                current_url = self.page.url
                if current_url != initial_url:
                    # 检查URL是否离开了登录页面
                    if "login" not in current_url.lower() and "signin" not in current_url.lower():
                        logger.info(f"✅ 策略1成功: URL已变化 {initial_url} → {current_url}")
                        return True
                
                # 策略2: 登录表单消失
                try:
                    password_fields = self.page.locator("input[type='password']").count()
                    if password_fields == 0:
                        logger.info("✅ 策略2成功: 登录表单已消失")
                        self.page.wait_for_timeout(1000)  # 再等1秒确保稳定
                        return True
                except Exception:
                    pass
                
                # 策略3: 用户信息元素出现
                user_indicators = [
                    "img[alt*='头像']", "img[alt*='avatar']", "img[alt*='Avatar']",
                    ".user-info", ".user-profile", ".user-avatar",
                    "a[href*='logout']", "a[href*='signout']",
                    "button:has-text('退出')", "button:has-text('登出')",
                    "a:has-text('退出')", "a:has-text('Logout')",
                    ".username", ".user-name", "[class*='username']"
                ]
                for selector in user_indicators:
                    try:
                        if self.page.locator(selector).first.is_visible(timeout=500):
                            logger.info(f"✅ 策略3成功: 检测到用户元素 {selector}")
                            return True
                    except Exception:
                        pass
                
                # 策略4: Cookie数量显著增加（登录通常会增加session cookie）
                current_cookie_count = len(self.context.cookies())
                if current_cookie_count > initial_cookie_count + 2:  # 至少增加3个cookie
                    logger.info(f"✅ 策略4成功: Cookie增加 {initial_cookie_count} → {current_cookie_count}")
                    self.page.wait_for_timeout(1000)
                    return True
                
            except Exception as e:
                logger.debug(f"检测异常: {e}")
                pass
            
            # 每秒检查一次
            self.page.wait_for_timeout(1000)
        
        logger.warning(f"⚠️ 登录成功检测超时（{timeout/1000}秒），假设失败")
        return False
    
    # ===== 登录和验证码处理 =====
    
    def _request_login(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        请求用户输入登录信息（智能检测登录表单）
        
        Args:
            params: 参数字典
                - site_name: 网站名称
                - username_selector: 用户名输入框选择器（可选，会自动检测）
                - password_selector: 密码输入框选择器（可选，会自动检测）
                - submit_selector: 提交按钮选择器（可选）
                - username_label: 用户名标签（可选）
                - password_label: 密码标签（可选）
        
        Returns:
            执行结果字典
        """
        site_name = params.get("site_name", "网站")
        username_selector = params.get("username_selector")
        password_selector = params.get("password_selector")
        submit_selector = params.get("submit_selector")
        username_label = params.get("username_label", "用户名")
        password_label = params.get("password_label", "密码")
        
        try:
            logger.info(f"请求用户登录信息: {site_name}")
            
            # 如果没有提供选择器，尝试自动检测
            if not username_selector or not password_selector:
                logger.info("未提供选择器，尝试自动检测登录表单...")
                detected = self.detect_login_form()
                
                # 如果没有检测到登录表单，尝试点击"登录"链接进入登录页面
                if not detected:
                    logger.info("未检测到登录表单，尝试点击登录链接...")
                    login_clicked = self._try_click_login_link()
                    if login_clicked:
                        self.page.wait_for_timeout(2000)  # 等待登录页面加载
                        detected = self.detect_login_form()
                
                if detected:
                    username_selector = username_selector or detected.get("username_selector")
                    password_selector = password_selector or detected.get("password_selector")
                    submit_selector = submit_selector or detected.get("submit_selector")
                    logger.info(f"自动检测到登录表单: 用户名={username_selector}, 密码={password_selector}")
            
            # 🔴 CRITICAL: 更新 UserInputManager 的停止检查函数和 stop_event
            # 确保在执行前使用最新的 stop_event（可能在执行过程中被更新）
            if self.stop_event:
                self.user_input_manager.stop_event = self.stop_event
            if self._check_stop_callback:
                self.user_input_manager.check_stop = self._check_stop_callback
            
            # 请求用户输入（可能会抛出 TaskInterruptedException）
            try:
                credentials = self.user_input_manager.request_login(
                    site_name=site_name,
                    username_label=username_label,
                    password_label=password_label,
                    message=f"请输入您在 {site_name} 的登录信息"
                )
            except TaskInterruptedException as e:
                # 🔴 CRITICAL: 捕获任务中断异常，返回 success: False，让 TaskOrchestrator 能够正常收尾
                logger.info(f"登录请求已中断: {e}")
                return {
                    "success": False,
                    "message": "任务已取消",
                    "data": None
                }
            
            if not credentials:
                return {
                    "success": False,
                    "message": "用户取消了登录",
                    "data": None
                }
            
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            
            # 尝试填写用户名
            filled_username = False
            if username_selector:
                filled_username = self._try_fill_field(username_selector, username, "用户名")
            
            # 如果指定的选择器失败，尝试常见选择器
            if not filled_username:
                common_username_selectors = [
                    "input[type='text']:visible",
                    "input[name*='user']",
                    "input[name*='account']",
                    "input[name*='login']",
                    "input[id*='user']",
                    "input[id*='account']",
                    "input[placeholder*='用户名']",
                    "input[placeholder*='账号']",
                    "input[placeholder*='手机']",
                    "input[placeholder*='邮箱']",
                ]
                for sel in common_username_selectors:
                    if self._try_fill_field(sel, username, "用户名"):
                        filled_username = True
                        break
            
            if not filled_username:
                # 截图帮助调试
                screenshot_path = self.download_path / f"login_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                return {
                    "success": False,
                    "message": f"无法找到用户名输入框，已截图: {screenshot_path}",
                    "data": None
                }
            
            # 尝试填写密码
            filled_password = False
            if password_selector:
                filled_password = self._try_fill_field(password_selector, password, "密码")
            
            if not filled_password:
                common_password_selectors = [
                    "input[type='password']",
                    "input[name*='pass']",
                    "input[name*='pwd']",
                    "input[id*='pass']",
                    "input[id*='pwd']",
                ]
                for sel in common_password_selectors:
                    if self._try_fill_field(sel, password, "密码"):
                        filled_password = True
                        break
            
            if not filled_password:
                screenshot_path = self.download_path / f"login_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                return {
                    "success": False,
                    "message": f"无法找到密码输入框，已截图: {screenshot_path}",
                    "data": None
                }
            
            # 点击提交按钮
            if submit_selector:
                try:
                    logger.info(f"点击提交按钮: {submit_selector}")
                    self.page.click(submit_selector, timeout=5000)
                    self.page.wait_for_timeout(2000)
                except Exception as e:
                    logger.warning(f"点击提交按钮失败: {e}，尝试其他方式...")
                    # 尝试按回车
                    self.page.keyboard.press("Enter")
                    self.page.wait_for_timeout(2000)
            
            logger.info("✅ 登录信息已填写")
            
            # 记录初始URL用于登录成功检测
            initial_url = self.page.url
            
            # 新增：智能登录成功检测(替换简单3秒等待)
            if self._verify_login_success(initial_url, timeout=15000):
                logger.info("✅ 登录成功验证通过")
                login_verified = True
            else:
                logger.warning("⚠️ 未能确认登录成功，可能需要人工检查")
                login_verified = False
            
            # 保存 cookies
            try:
                current_url = self.page.url
                cookies = self.context.cookies()
                if cookies:
                    self.state_manager.save_cookies(current_url, cookies)
                    logger.info(f"已保存 {len(cookies)} 个 cookies 到 {site_name}")
            except Exception as cookie_err:
                logger.warning(f"保存 cookies 失败: {cookie_err}")
            
            return {
                "success": login_verified,
                "message": "已填写登录信息" + (" (已验证成功)" if login_verified else " (未确认成功)"),
                "data": {"site_name": site_name, "verified": login_verified}
            }
            
        except Exception as e:
            error_msg = f"请求登录失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # 截图帮助调试
            try:
                screenshot_path = self.download_path / f"login_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                error_msg += f"，已截图: {screenshot_path}"
            except Exception:
                pass
            return {
                "success": False,
                "message": error_msg,
                "data": None
            }
    
    def _request_qr_login(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        二维码登录（检测QR码 → 截图 → 发送给前端 → 等待扫码）
        
        Args:
            params: 参数字典
                - site_name: 网站名称（必需）
                - qr_selector: QR码元素选择器（可选，会自动检测）
                - success_selector: 登录成功后出现的元素选择器（可选）
                - timeout: 超时时间（毫秒，默认120000）
        
        Returns:
            执行结果字典
        """
        site_name = params.get("site_name", "网站")
        qr_selector = params.get("qr_selector")
        success_selector = params.get("success_selector")
        timeout = params.get("timeout", 120000)  # 默认2分钟
        
        try:
            logger.info(f"开始二维码登录: {site_name}")
            
            #步骤1: 检测二维码元素
            qr_locator = None
            if qr_selector:
                try:
                    qr_locator = self.page.locator(qr_selector).first
                    if not qr_locator.is_visible(timeout=2000):
                        qr_locator = None
                except Exception:
                    qr_locator = None
            
            if not qr_locator:
                # 自动检测常见的二维码选择器
                common_qr_selectors = [
                    "img[src*='qrcode']",
                    "img[src*='qr']",
                    ".qrcode img",
                    ".qr-code img",
                    "canvas.qrcode",
                    ".qr-code canvas",
                    ".login-qrcode img",
                    "[class*='qrcode'] img",
                    "[class*='qr-code'] img",
                    "[id*='qrcode']",
                    "[id*='qr']",
                ]
                for sel in common_qr_selectors:
                    try:
                        candidate = self.page.locator(sel).first
                        if candidate.is_visible(timeout=1000):
                            qr_locator = candidate
                            logger.info(f"自动检测到二维码: {sel}")
                            break
                    except Exception:
                        continue
            
            if not qr_locator:
                screenshot_path = self.download_path / f"qr_detect_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                return {
                    "success": False,
                    "message": f"未检测到二维码，已截图: {screenshot_path}",
                    "data": None
                }
            
            # 步骤2: 截图二维码区域
            logger.info("截图二维码...")
            qr_screenshot_path = self.download_path / f"qr_code_{int(time.time())}.png"
            qr_locator.screenshot(path=str(qr_screenshot_path))
            
            # 转换为 base64
            with open(qr_screenshot_path, "rb") as f:
                qr_image_data = f.read()
            qr_base64 = base64.b64encode(qr_image_data).decode("utf-8")
            
            logger.info(f"二维码已截图: {qr_screenshot_path}, 大小: {len(qr_base64)} bytes")
            
            # 🔴 CRITICAL: 更新 UserInputManager 的 stop_event（确保在执行前使用最新的）
            if self.stop_event:
                self.user_input_manager.stop_event = self.stop_event
            if self._check_stop_callback:
                self.user_input_manager.check_stop = self._check_stop_callback
            
            # 步骤3: 请求用户扫码
            success = self.user_input_manager.request_qr_login(
                qr_image=qr_base64,
                site_name=site_name,
                message=f"请使用手机扫描二维码登录 {site_name}"
            )
            
            if not success:
                return {
                    "success": False,
                    "message": "用户取消了二维码登录",
                    "data": None
                }
            
            # 步骤4: 等待登录成功（轮询检测）
            logger.info("等待用户扫码登录...")
            start_time = time.time()
            login_success = False
            
            while (time.time() - start_time) * 1000 < timeout:
                try:
                    # 检查二维码是否消失（常见的登录成功标志）
                    if not qr_locator.is_visible(timeout=1000):
                        logger.info("二维码已消失，可能登录成功")
                        login_success = True
                        break
                    
                    # 如果提供了成功选择器，检查是否出现
                    if success_selector:
                        try:
                            success_elem = self.page.locator(success_selector).first
                            if success_elem.is_visible(timeout=1000):
                                logger.info(f"检测到登录成功元素: {success_selector}")
                                login_success = True
                                break
                        except Exception:
                            pass
                    
                    # 检查URL是否变化（可能跳转到登录后页面）
                    current_url = self.page.url
                    if "login" not in current_url.lower():
                        logger.info(f"URL已变化，可能登录成功: {current_url}")
                        login_success = True
                        break
                    
                except Exception:
                    pass
                
                self.page.wait_for_timeout(2000)  # 每2秒检查一次
            
            if not login_success:
                return {
                    "success": False,
                    "message": f"二维码登录超时（{timeout/1000}秒）",
                    "data": None
                }
            
            # 步骤5: 保存 cookies
            try:
                self.page.wait_for_timeout(3000)  # 等待登录完全完成
                current_url = self.page.url
                cookies = self.context.cookies()
                if cookies:
                    self.state_manager.save_cookies(current_url, cookies)
                    logger.info(f"已保存 {len(cookies)} 个 cookies 到 {site_name}")
            except Exception as cookie_err:
                logger.warning(f"保存 cookies 失败: {cookie_err}")
            
            logger.info("✅ 二维码登录成功")
            
            return {
                "success": True,
                "message": f"二维码登录成功: {site_name}",
                "data": {"site_name": site_name}
            }
            
        except Exception as e:
            error_msg = f"二维码登录失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            try:
                screenshot_path = self.download_path / f"qr_login_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path), full_page=True)
                error_msg += f"，已截图: {screenshot_path}"
            except Exception:
                pass
            return {
                "success": False,
                "message": error_msg,
                "data": None
            }
    
    def _try_fill_field(self, selector: str, value: str, field_name: str) -> bool:
        """尝试填写字段，返回是否成功"""
        try:
            element = self.page.locator(selector).first
            if element.is_visible(timeout=2000):
                element.fill(value, timeout=5000)
                logger.info(f"✅ 成功填写{field_name}: {selector}")
                return True
        except Exception as e:
            logger.debug(f"填写{field_name}失败 ({selector}): {e}")
        return False
    
    def _try_click_login_link(self) -> bool:
        """尝试点击页面上的登录链接/按钮"""
        login_selectors = [
            # 文本匹配
            "a:has-text('登录')",
            "a:has-text('登陆')",
            "button:has-text('登录')",
            "button:has-text('登陆')",
            "span:has-text('登录')",
            "div:has-text('登录')",
            # 英文
            "a:has-text('Login')",
            "a:has-text('Sign in')",
            "a:has-text('Log in')",
            # 常见选择器
            "a[href*='login']",
            "a[href*='signin']",
            ".login-btn",
            ".login-link",
            "#login-link",
        ]
        
        for selector in login_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=1000):
                    logger.info(f"找到登录链接: {selector}")
                    element.click(timeout=5000)
                    logger.info("✅ 已点击登录链接")
                    return True
            except Exception as e:
                logger.debug(f"点击登录链接失败 ({selector}): {e}")
                continue
        
        logger.warning("未找到登录链接")
        return False
    
    def _request_captcha(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        请求用户输入验证码
        
        Args:
            params: 参数字典
                - captcha_image_selector: 验证码图片选择器
                - captcha_input_selector: 验证码输入框选择器
                - site_name: 网站名称（可选）
        
        Returns:
            执行结果字典
        """
        captcha_image_selector = params.get("captcha_image_selector")
        captcha_input_selector = params.get("captcha_input_selector")
        site_name = params.get("site_name", "网站")
        
        if not captcha_image_selector or not captcha_input_selector:
            raise BrowserError("请求验证码需要 captcha_image_selector 和 captcha_input_selector")
        
        try:
            logger.info(f"请求验证码输入: {site_name}")
            
            # 截取验证码图片
            captcha_element = self.page.locator(captcha_image_selector).first
            captcha_element.wait_for(state="visible", timeout=10000)
            
            # 获取验证码图片的 base64
            captcha_bytes = captcha_element.screenshot()
            captcha_base64 = base64.b64encode(captcha_bytes).decode("utf-8")
            captcha_data_url = f"data:image/png;base64,{captcha_base64}"
            
            logger.info("验证码图片已截取")
            
            # 新增：OCR自动识别（优先尝试）
            auto_recognized_text = None
            if self.ocr_helper.is_available():
                logger.info("🤖 尝试OCR自动识别验证码...")
                auto_recognized_text = self.ocr_helper.recognize_captcha(captcha_data_url)
                
                if auto_recognized_text:
                    logger.info(f"✅ OCR识别成功: {auto_recognized_text}")
                    # 策略1：直接填写（速度快）
                    try:
                        self.page.fill(captcha_input_selector, auto_recognized_text, timeout=10000)
                        logger.info("✅ OCR自动填写验证码")
                        return {
                            "success": True,
                            "message": f"OCR自动识别并填写: {auto_recognized_text}",
                            "data": {"captcha": auto_recognized_text, "auto_recognized": True}
                        }
                    except Exception as fill_err:
                        logger.warning(f"OCR填写失败: {fill_err}，回退到用户输入")
                else:
                    logger.info("⚠️ OCR识别失败，回退到用户输入")
            
            # 🔴 CRITICAL: 更新 UserInputManager 的 stop_event（确保在执行前使用最新的）
            if self.stop_event:
                self.user_input_manager.stop_event = self.stop_event
            if self._check_stop_callback:
                self.user_input_manager.check_stop = self._check_stop_callback
            
            # OCR不可用或识别失败，回退到用户输入
            # 请求用户输入验证码
            captcha_text = self.user_input_manager.request_captcha(
                captcha_image=captcha_data_url,
                site_name=site_name,
                message="请输入图片中的验证码"
            )
            
            if not captcha_text:
                return {
                    "success": False,
                    "message": "用户取消了验证码输入",
                    "data": None
                }
            
            # 填写验证码
            logger.info(f"填写验证码: {captcha_input_selector}")
            self.page.fill(captcha_input_selector, captcha_text, timeout=10000)
            
            logger.info("✅ 验证码已填写")
            
            return {
                "success": True,
                "message": "已填写验证码",
                "data": {"captcha": captcha_text}
            }
            
        except Exception as e:
            error_msg = f"请求验证码失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg,
                "data": None
            }
    
    def _fill_login(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        填写登录表单（用于 AI 规划时生成的步骤）
        
        Args:
            params: 参数字典
                - site_name: 网站名称
                - username_selector: 用户名输入框选择器
                - password_selector: 密码输入框选择器
                - submit_selector: 提交按钮选择器（可选）
        
        Returns:
            执行结果字典
        """
        return self._request_login(params)
    
    def _fill_captcha(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        填写验证码（用于 AI 规划时生成的步骤）
        
        Args:
            params: 参数字典
                - captcha_image_selector: 验证码图片选择器
                - captcha_input_selector: 验证码输入框选择器
                - site_name: 网站名称（可选）
        
        Returns:
            执行结果字典
        """
        return self._request_captcha(params)
    
    def detect_login_form(self) -> Optional[Dict[str, Any]]:
        """
        检测页面上是否有登录表单
        
        Returns:
            如果检测到登录表单，返回表单信息；否则返回 None
        """
        if not self.page:
            return None
        
        try:
            # 常见的登录表单选择器
            login_indicators = [
                # 用户名/账号输入框
                ("username", [
                    "input[name='username']",
                    "input[name='user']",
                    "input[name='account']",
                    "input[name='login']",
                    "input[name='email']",
                    "input[type='email']",
                    "input[id*='user']",
                    "input[id*='account']",
                    "input[id*='login']",
                    "input[placeholder*='用户名']",
                    "input[placeholder*='账号']",
                    "input[placeholder*='手机号']",
                    "input[placeholder*='邮箱']",
                ]),
                # 密码输入框
                ("password", [
                    "input[type='password']",
                    "input[name='password']",
                    "input[name='pwd']",
                    "input[id*='password']",
                    "input[id*='pwd']",
                ]),
            ]
            
            detected = {}
            
            for field_name, selectors in login_indicators:
                for selector in selectors:
                    try:
                        element = self.page.locator(selector).first
                        if element.is_visible(timeout=1000):
                            detected[field_name + "_selector"] = selector
                            break
                    except Exception:
                        continue
            
            # 如果同时检测到用户名和密码输入框，认为是登录表单
            if "username_selector" in detected and "password_selector" in detected:
                # 尝试检测提交按钮
                submit_selectors = [
                    "button[type='submit']",
                    "input[type='submit']",
                    "button:has-text('登录')",
                    "button:has-text('登陆')",
                    "button:has-text('Sign in')",
                    "button:has-text('Login')",
                    "[class*='submit']",
                    "[class*='login-btn']",
                ]
                for selector in submit_selectors:
                    try:
                        element = self.page.locator(selector).first
                        if element.is_visible(timeout=500):
                            detected["submit_selector"] = selector
                            break
                    except Exception:
                        continue
                
                logger.info(f"检测到登录表单: {detected}")
                return detected
            
            return None
            
        except Exception as e:
            logger.warning(f"检测登录表单时出错: {e}")
            return None
    
    def detect_captcha(self) -> Optional[Dict[str, Any]]:
        """
        检测页面上是否有验证码
        
        Returns:
            如果检测到验证码，返回验证码信息；否则返回 None
        """
        if not self.page:
            return None
        
        try:
            # 常见的验证码选择器
            captcha_image_selectors = [
                "img[src*='captcha']",
                "img[src*='verify']",
                "img[src*='code']",
                "img[id*='captcha']",
                "img[id*='verify']",
                "img[class*='captcha']",
                "img[class*='verify']",
                ".captcha img",
                ".verify-img",
                "#captcha-img",
            ]
            
            captcha_input_selectors = [
                "input[name='captcha']",
                "input[name='verify']",
                "input[name='code']",
                "input[id*='captcha']",
                "input[id*='verify']",
                "input[placeholder*='验证码']",
                "input[placeholder*='验证']",
                "input[placeholder*='captcha']",
            ]
            
            detected = {}
            
            # 检测验证码图片
            for selector in captcha_image_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=500):
                        detected["captcha_image_selector"] = selector
                        break
                except Exception:
                    continue
            
            # 检测验证码输入框
            for selector in captcha_input_selectors:
                try:
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=500):
                        detected["captcha_input_selector"] = selector
                        break
                except Exception:
                    continue
            
            # 如果同时检测到验证码图片和输入框，认为是验证码
            if "captcha_image_selector" in detected and "captcha_input_selector" in detected:
                logger.info(f"检测到验证码: {detected}")
                return detected
            
            return None
            
        except Exception as e:
            logger.warning(f"检测验证码时出错: {e}")
            return None