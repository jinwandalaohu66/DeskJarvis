"""
浏览器执行器：使用Playwright控制浏览器

遵循 docs/ARCHITECTURE.md 中的Executor模块规范
"""

from typing import Dict, Any, Optional, Callable
import logging
import time
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from agent.tools.exceptions import BrowserError
from agent.tools.config import Config
from agent.user_input import UserInputManager

logger = logging.getLogger(__name__)


class BrowserExecutor:
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
        self.config = config
        self.emit = emit_callback
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.download_path = config.sandbox_path / "downloads"
        self.download_path.mkdir(parents=True, exist_ok=True)
        
        # 用户输入管理器
        self.user_input_manager = UserInputManager(emit_callback=emit_callback)
        
        logger.info(f"浏览器执行器已初始化，下载目录: {self.download_path}")
    
    def start(self) -> None:
        """
        启动浏览器实例
        
        Raises:
            BrowserError: 当启动失败时
        """
        try:
            logger.info("正在启动浏览器...")
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ]
            )
            self.context = self.browser.new_context(
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="zh-CN",
            )
            self.page = self.context.new_page()
            
            # 隐藏自动化特征
            self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            
            logger.info("✅ 浏览器已启动")
        except Exception as e:
            error_msg = f"启动浏览器失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise BrowserError(error_msg) from e
    
    def stop(self) -> None:
        """停止浏览器实例"""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("浏览器已停止")
        except Exception as e:
            logger.warning(f"停止浏览器时出错: {e}")
    
    def execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个任务步骤
        
        Args:
            step: 任务步骤，包含type、action、params等
        
        Returns:
            执行结果，包含success、message、data等
        
        Raises:
            BrowserError: 当执行失败时
        """
        if not self.page:
            raise BrowserError("浏览器未启动，请先调用start()")
        
        step_type = step.get("type")
        action = step.get("action", "")
        params = step.get("params", {})
        
        logger.info(f"执行步骤: {step_type} - {action}")
        
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
            elif step_type == "fill_login":
                return self._fill_login(params)
            elif step_type == "fill_captcha":
                return self._fill_captcha(params)
            else:
                raise BrowserError(f"未知的步骤类型: {step_type}")
                
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
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 额外等待一下让页面完全渲染
            self.page.wait_for_timeout(1000)
            
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
        点击元素（增强版：支持文本定位 + 等待可见 + 滚动 + 多元素处理）
        
        Args:
            params: 参数字典
                - selector: CSS选择器（可选）
                - text: 文本内容（可选，优先使用）
                - timeout: 超时时间（毫秒，默认60000）
        
        Returns:
            执行结果字典
        
        Raises:
            BrowserError: 当点击失败时
        """
        selector = params.get("selector")
        text = params.get("text")  # 新增：文本定位参数
        timeout = params.get("timeout", 60000)
        
        if not selector and not text:
            raise BrowserError("点击参数缺少selector或text")
        
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
                # 元素不存在，先截图调试
                screenshot_path = self.download_path / f"click_error_{int(time.time())}.png"
                self.page.screenshot(path=str(screenshot_path))
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
            
            # 步骤6: 执行点击
            logger.info("执行点击...")
            visible_locator.click(timeout=timeout)
            
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
        """填写表单字段"""
        selector = params.get("selector")
        value = params.get("value")
        
        if not selector or value is None:
            raise BrowserError("填写参数缺少selector或value")
        
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
            
            # 请求用户输入
            credentials = self.user_input_manager.request_login(
                site_name=site_name,
                username_label=username_label,
                password_label=password_label,
                message=f"请输入您在 {site_name} 的登录信息"
            )
            
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
            
            return {
                "success": True,
                "message": "已填写登录信息",
                "data": {"site_name": site_name}
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