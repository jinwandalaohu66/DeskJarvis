"""
系统工具：系统级操作（截图、系统命令等）

遵循 docs/ARCHITECTURE.md 中的Executor模块规范
"""

from typing import Dict, Any, List, Optional
import logging
import sys
import subprocess
import time
from pathlib import Path
from agent.tools.exceptions import BrowserError
from agent.tools.config import Config
from agent.executor.code_interpreter import CodeInterpreter

logger = logging.getLogger(__name__)


class SystemTools:
    """
    系统工具：执行系统级操作
    
    职责：
    - 桌面截图
    - 系统命令执行（未来扩展）
    """
    
    def __init__(self, config: Config, emit_callback=None):
        """
        初始化系统工具
        
        Args:
            config: 配置对象
            emit_callback: 进度回调函数
        """
        self.config = config
        self.emit = emit_callback
        self.sandbox_path = Path(config.sandbox_path).resolve()
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化增强版代码解释器
        self.code_interpreter = CodeInterpreter(self.sandbox_path, emit_callback)
        
        logger.info(f"系统工具已初始化，沙盒目录: {self.sandbox_path}")
    
    def _find_folder(self, folder_name: str, search_dirs: List[Path] = None) -> Optional[Path]:
        """
        智能搜索文件夹：在指定目录中搜索文件夹名
        
        支持：
        - 精确匹配（如 "8888"）
        - 部分匹配（如 "88" 可以匹配 "8888"）
        
        Args:
            folder_name: 文件夹名（如 "8888"）
            search_dirs: 搜索目录列表，默认为用户主目录下的常用目录
        
        Returns:
            找到的文件夹路径，如果未找到返回None
        """
        if search_dirs is None:
            home = Path.home()
            search_dirs = [
                home / "Desktop",
                home / "Downloads",
                home / "Documents",
                home,  # 也在主目录下搜索
                self.sandbox_path,
            ]
        
        # 规范化文件夹名（去除前后空格）
        folder_name = folder_name.strip()
        
        # 1. 先尝试直接匹配文件夹名（精确匹配）
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            candidate = search_dir / folder_name
            if candidate.exists() and candidate.is_dir():
                logger.info(f"精确匹配找到文件夹: {candidate}")
                return candidate
        
        # 2. 部分匹配：文件夹名包含在文件夹名的开头
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            try:
                for item in search_dir.iterdir():
                    if item.is_dir():
                        item_name = item.name
                        # 如果用户输入的文件夹名包含在文件夹名的开头，或者文件夹名包含用户输入
                        if folder_name in item_name or item_name.startswith(folder_name):
                            logger.info(f"部分匹配找到文件夹: {item} (匹配: {folder_name})")
                            return item
            except (PermissionError, OSError):
                continue
        
        # 3. 递归搜索（限制深度为2）
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            try:
                # 先尝试精确匹配
                for item in search_dir.rglob(folder_name):
                    if item.is_dir():
                        logger.info(f"递归搜索找到文件夹: {item}")
                        return item
                
                # 再尝试部分匹配（递归）
                for item in search_dir.rglob("*"):
                    if item.is_dir():
                        item_name = item.name
                        if folder_name in item_name or item_name.startswith(folder_name):
                            logger.info(f"递归部分匹配找到文件夹: {item} (匹配: {folder_name})")
                            return item
            except (PermissionError, OSError):
                continue
        
        logger.warning(f"未找到文件夹: {folder_name}")
        return None
    
    def execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行系统操作步骤
        
        Args:
            step: 任务步骤，包含type、action、params等
        
        Returns:
            执行结果
        """
        step_type = step.get("type")
        action = step.get("action", "")
        params = step.get("params", {})
        
        logger.info(f"执行系统操作: {step_type} - {action}")
        
        try:
            if step_type == "screenshot_desktop":
                return self._screenshot_desktop(params)
            elif step_type == "open_folder":
                return self._open_folder(params)
            elif step_type == "open_file":
                return self._open_file(params)
            elif step_type == "open_app":
                return self._open_app(params)
            elif step_type == "close_app":
                return self._close_app(params)
            elif step_type == "execute_python_script":
                return self._execute_python_script(params)
            # ========== 新增系统控制功能 ==========
            elif step_type == "set_volume":
                return self._set_volume(params)
            elif step_type == "set_brightness":
                return self._set_brightness(params)
            elif step_type == "send_notification":
                return self._send_notification(params)
            elif step_type == "clipboard_read":
                return self._clipboard_read(params)
            elif step_type == "clipboard_write":
                return self._clipboard_write(params)
            elif step_type == "keyboard_type":
                return self._keyboard_type(params)
            elif step_type == "keyboard_shortcut":
                return self._keyboard_shortcut(params)
            elif step_type == "mouse_click":
                return self._mouse_click(params)
            elif step_type == "mouse_move":
                return self._mouse_move(params)
            elif step_type == "window_minimize":
                return self._window_minimize(params)
            elif step_type == "window_maximize":
                return self._window_maximize(params)
            elif step_type == "window_close":
                return self._window_close(params)
            elif step_type == "speak":
                return self._speak(params)
            # ========== 系统信息和图片处理 ==========
            elif step_type == "get_system_info":
                return self._get_system_info(params)
            elif step_type == "image_process":
                return self._image_process(params)
            # ========== 定时提醒 ==========
            elif step_type == "set_reminder":
                return self._set_reminder(params)
            elif step_type == "list_reminders":
                return self._list_reminders(params)
            elif step_type == "cancel_reminder":
                return self._cancel_reminder(params)
            # ========== 工作流 ==========
            elif step_type == "create_workflow":
                return self._create_workflow(params)
            elif step_type == "list_workflows":
                return self._list_workflows(params)
            elif step_type == "delete_workflow":
                return self._delete_workflow(params)
            # ========== 任务历史 ==========
            elif step_type == "get_task_history":
                return self._get_task_history(params)
            elif step_type == "search_history":
                return self._search_history(params)
            elif step_type == "add_favorite":
                return self._add_favorite(params)
            elif step_type == "list_favorites":
                return self._list_favorites(params)
            elif step_type == "remove_favorite":
                return self._remove_favorite(params)
            # ========== 文本AI处理 ==========
            elif step_type == "text_process":
                return self._text_process(params)
            else:
                raise BrowserError(f"未知的系统操作类型: {step_type}")
                
        except Exception as e:
            logger.error(f"执行系统操作失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"操作失败: {e}",
                "data": None
            }
    
    def _screenshot_desktop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        桌面截图
        
        Args:
            params: 包含save_path（保存路径，可选）
                    - 可以是相对路径（相对于用户主目录）
                    - 可以是绝对路径（必须在用户主目录下）
                    - 支持 ~ 符号（如 ~/Desktop/screenshot.png）
        
        Returns:
            截图结果，包含保存路径
        """
        save_path_str = params.get("save_path")
        home = Path.home()
        
        # 如果没有指定路径，使用默认路径（沙盒目录下）
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
            
            # 安全：确保路径在用户主目录下（禁止操作系统关键路径）
            try:
                save_path.relative_to(home)
            except ValueError:
                # 不在用户主目录下，使用默认路径
                screenshots_dir = self.sandbox_path / "screenshots"
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                import time
                save_path = screenshots_dir / f"desktop_{int(time.time())}.png"
                logger.warning(f"路径不在用户主目录下，使用默认路径: {save_path}")
        else:
            # 默认保存到沙盒目录的screenshots子目录
            screenshots_dir = self.sandbox_path / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            import time
            save_path = screenshots_dir / f"desktop_{int(time.time())}.png"
        
        # 确保目录存在
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存原始路径，用于查找实际保存的文件
        original_save_path = save_path
        
        # 根据操作系统选择截图方法
        platform = sys.platform
        
        try:
            if platform == "darwin":  # macOS
                # 使用 screencapture 命令
                # -x: 不播放快门声音
                # -T 0: 立即截图（无延迟）
                result = subprocess.run(
                    ["screencapture", "-x", str(save_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"截图失败: {result.stderr}")
                
                # macOS 的 screencapture 如果文件已存在，会自动添加序号（如 screenshot_1.png）
                # 需要检查实际保存的文件路径
                if not save_path.exists():
                    # 尝试查找带序号的文件
                    parent_dir = save_path.parent
                    stem = save_path.stem
                    suffix = save_path.suffix
                    counter = 1
                    found_path = None
                    # 最多尝试查找 100 个序号（防止无限循环）
                    while counter <= 100:
                        candidate_path = parent_dir / f"{stem}_{counter}{suffix}"
                        if candidate_path.exists():
                            found_path = candidate_path
                            logger.info(f"找到实际保存的截图文件（带序号）: {found_path}")
                            break
                        counter += 1
                    
                    if found_path:
                        save_path = found_path
                    else:
                        # 如果找不到带序号的文件，尝试查找任何匹配的文件
                        # 这可能是 screencapture 使用了其他命名规则
                        logger.warning(f"未找到预期的截图文件: {original_save_path}，尝试查找匹配的文件...")
                        # 列出目录中所有以相同 stem 开头的文件
                        matching_files = list(parent_dir.glob(f"{stem}*{suffix}"))
                        if matching_files:
                            # 按修改时间排序，取最新的
                            matching_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                            save_path = matching_files[0]
                            logger.info(f"找到匹配的截图文件: {save_path}")
                
            elif platform == "win32":  # Windows
                try:
                    # 尝试使用 mss 库（如果已安装）
                    import mss
                    with mss.mss() as sct:
                        # 截图整个屏幕
                        monitor = sct.monitors[1]  # 主显示器
                        sct_img = sct.grab(monitor)
                        mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(save_path))
                except ImportError:
                    # 如果没有 mss，使用 pyautogui
                    try:
                        import pyautogui
                        screenshot = pyautogui.screenshot()
                        screenshot.save(str(save_path))
                    except ImportError:
                        raise BrowserError(
                            "Windows截图需要安装 mss 或 pyautogui 库。"
                            "运行: pip install mss 或 pip install pyautogui"
                        )
            
            elif platform.startswith("linux"):  # Linux
                try:
                    # 尝试使用 gnome-screenshot（GNOME）
                    result = subprocess.run(
                        ["gnome-screenshot", "-f", str(save_path)],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode != 0:
                        # 尝试使用 import（需要 X11）
                        try:
                            from PIL import ImageGrab
                            screenshot = ImageGrab.grab()
                            screenshot.save(str(save_path))
                        except ImportError:
                            raise BrowserError(
                                "Linux截图需要安装 gnome-screenshot 或 PIL。"
                                "运行: sudo apt-get install gnome-screenshot 或 pip install Pillow"
                            )
                except FileNotFoundError:
                    # 尝试使用 import
                    try:
                        from PIL import ImageGrab
                        screenshot = ImageGrab.grab()
                        screenshot.save(str(save_path))
                    except ImportError:
                        raise BrowserError(
                            "Linux截图需要安装 gnome-screenshot 或 PIL。"
                            "运行: sudo apt-get install gnome-screenshot 或 pip install Pillow"
                        )
            else:
                raise BrowserError(f"不支持的操作系统: {platform}")
            
            # 验证文件已创建
            if not save_path.exists():
                raise BrowserError(f"截图文件未创建: {save_path}")
            
            logger.info(f"✅ 桌面截图已保存: {save_path}")
            
            return {
                "success": True,
                "message": f"桌面截图已保存: {save_path}",
                "data": {"path": str(save_path)}
            }
            
        except subprocess.TimeoutExpired:
            raise BrowserError("截图超时（超过10秒）")
        except Exception as e:
            logger.error(f"截图失败: {e}", exc_info=True)
            raise BrowserError(f"截图失败: {e}")
    
    def _open_folder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        在文件管理器中打开文件夹（支持智能搜索）
        
        Args:
            params: 包含folder_path（文件夹路径，必需）
                    - 可以是相对路径（相对于用户主目录）
                    - 可以是绝对路径（必须在用户主目录下）
                    - 支持 ~ 符号（如 ~/Desktop）
                    - 支持特殊路径（如 ~/Downloads, ~/Desktop, ~/Documents）
                    - 支持文件夹名（如 "8888"），会自动搜索
        
        Returns:
            打开结果
        """
        folder_path_str = params.get("folder_path")
        if not folder_path_str:
            raise BrowserError("缺少folder_path参数")
        
        home = Path.home()
        
        # 处理 ~ 符号
        if folder_path_str.startswith("~/"):
            folder_path_str = str(home / folder_path_str[2:])
        elif folder_path_str.startswith("~"):
            folder_path_str = str(home / folder_path_str[1:])
        
        folder_path = Path(folder_path_str)
        
        # 如果只是文件夹名（不包含路径分隔符），尝试智能搜索
        if "/" not in folder_path_str and "\\" not in folder_path_str and not folder_path_str.startswith("~"):
            logger.info(f"检测到文件夹名格式，开始智能搜索: {folder_path_str}")
            found_folder = self._find_folder(folder_path_str)
            if found_folder:
                folder_path = found_folder
                logger.info(f"找到文件夹: {folder_path}")
            else:
                raise BrowserError(
                    f"未找到文件夹: {folder_path_str}。"
                    f"请提供完整路径，如 '~/Desktop/{folder_path_str}' 或 '/Users/username/Desktop/{folder_path_str}'"
                )
        # 如果是相对路径，相对于用户主目录
        elif not folder_path.is_absolute():
            folder_path = home / folder_path
        
        folder_path = folder_path.resolve()
        
        # 安全：确保路径在用户主目录下
        try:
            folder_path.relative_to(home)
        except ValueError:
            raise BrowserError(
                f"文件夹路径不在允许的范围内: {folder_path}。"
                f"只允许打开用户主目录下的文件夹。"
            )
        
        # 检查文件夹是否存在
        if not folder_path.exists():
            raise BrowserError(f"文件夹不存在: {folder_path}")
        
        if not folder_path.is_dir():
            raise BrowserError(f"路径不是文件夹: {folder_path}")
        
        # 根据操作系统选择打开方法
        platform = sys.platform
        
        try:
            if platform == "darwin":  # macOS
                # 使用 open 命令打开文件夹
                result = subprocess.run(
                    ["open", str(folder_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"打开文件夹失败: {result.stderr}")
                
            elif platform == "win32":  # Windows
                # 使用 explorer 命令打开文件夹
                result = subprocess.run(
                    ["explorer", str(folder_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"打开文件夹失败: {result.stderr}")
                
            elif platform.startswith("linux"):  # Linux
                # 尝试使用 xdg-open（大多数 Linux 发行版）
                result = subprocess.run(
                    ["xdg-open", str(folder_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"打开文件夹失败: {result.stderr}")
            else:
                raise BrowserError(f"不支持的操作系统: {platform}")
            
            logger.info(f"✅ 已打开文件夹: {folder_path}")
            
            return {
                "success": True,
                "message": f"已打开文件夹: {folder_path}",
                "data": {"path": str(folder_path)}
            }
            
        except subprocess.TimeoutExpired:
            raise BrowserError("打开文件夹超时（超过10秒）")
        except Exception as e:
            logger.error(f"打开文件夹失败: {e}", exc_info=True)
            raise BrowserError(f"打开文件夹失败: {e}")
    
    def _open_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用默认应用程序打开文件（支持智能搜索）
        
        Args:
            params: 包含file_path（文件路径，必需）
                    - 可以是相对路径（相对于用户主目录）
                    - 可以是绝对路径（必须在用户主目录下）
                    - 支持 ~ 符号（如 ~/Desktop/file.pdf）
                    - 支持文件名（如 "强制执行申请书.pdf"），会自动搜索
        
        Returns:
            打开结果
        """
        file_path_str = params.get("file_path")
        if not file_path_str:
            raise BrowserError("缺少file_path参数")
        
        home = Path.home()
        
        # 处理 ~ 符号
        if file_path_str.startswith("~/"):
            file_path_str = str(home / file_path_str[2:])
        elif file_path_str.startswith("~"):
            file_path_str = str(home / file_path_str[1:])
        
        file_path = Path(file_path_str)
        
        # 如果只是文件名（不包含路径分隔符），尝试智能搜索
        if "/" not in file_path_str and "\\" not in file_path_str and not file_path_str.startswith("~"):
            logger.info(f"检测到文件名格式，开始智能搜索: {file_path_str}")
            # 使用 FileManager 的搜索方法
            from agent.executor.file_manager import FileManager
            file_manager = FileManager(self.config)
            found_file = file_manager._find_file(file_path_str)
            if found_file:
                file_path = found_file
                logger.info(f"找到文件: {file_path}")
            else:
                raise BrowserError(
                    f"未找到文件: {file_path_str}。"
                    f"请提供完整路径，如 '~/Desktop/{file_path_str}' 或 '/Users/username/Desktop/{file_path_str}'"
                )
        # 如果是相对路径，相对于用户主目录
        elif not file_path.is_absolute():
            file_path = home / file_path
        
        file_path = file_path.resolve()
        
        # 安全：确保路径在用户主目录下
        try:
            file_path.relative_to(home)
        except ValueError:
            raise BrowserError(
                f"文件路径不在允许的范围内: {file_path}。"
                f"只允许打开用户主目录下的文件。"
            )
        
        # 检查文件是否存在
        if not file_path.exists():
            raise BrowserError(f"文件不存在: {file_path}")
        
        if not file_path.is_file():
            raise BrowserError(f"路径不是文件: {file_path}")
        
        # 根据操作系统选择打开方法
        platform = sys.platform
        
        try:
            if platform == "darwin":  # macOS
                # 使用 open 命令打开文件（会自动使用默认应用程序）
                result = subprocess.run(
                    ["open", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"打开文件失败: {result.stderr}")
                
            elif platform == "win32":  # Windows
                # 使用 start 命令打开文件
                result = subprocess.run(
                    ["start", "", str(file_path)],
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"打开文件失败: {result.stderr}")
                
            elif platform.startswith("linux"):  # Linux
                # 使用 xdg-open 打开文件
                result = subprocess.run(
                    ["xdg-open", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"打开文件失败: {result.stderr}")
            else:
                raise BrowserError(f"不支持的操作系统: {platform}")
            
            logger.info(f"✅ 已打开文件: {file_path}")
            
            return {
                "success": True,
                "message": f"已打开文件: {file_path}",
                "data": {"path": str(file_path)}
            }
            
        except subprocess.TimeoutExpired:
            raise BrowserError("打开文件超时（超过10秒）")
        except Exception as e:
            logger.error(f"打开文件失败: {e}", exc_info=True)
            raise BrowserError(f"打开文件失败: {e}")
    
    def _open_app(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        打开应用程序（支持后台运行）
        
        Args:
            params: 包含app_name（应用程序名称，必需）
                    - 可以是应用程序的完整名称（如 "汽水音乐"、"Spotify"）
                    - 可以是应用程序的bundle identifier（如 "com.spotify.client"）
                    - background: 是否在后台运行（可选，布尔值），如果为 true，应用程序会在后台运行，不显示窗口；如果为 false 或未指定，正常打开窗口
                    - **注意**：某些应用程序（如企业微信）可能需要窗口来操作，后台运行可能无法正常使用
        
        Returns:
            打开结果
        """
        app_name = params.get("app_name")
        background = params.get("background", False)
        if not app_name:
            raise BrowserError("缺少app_name参数")
        
        platform = sys.platform
        
        try:
            if platform == "darwin":  # macOS
                # 尝试多种方式打开应用程序
                app_variants = [
                    app_name,  # 原始名称
                    app_name + ".app",  # 带 .app 后缀
                ]
                
                # 尝试常见的应用程序名称映射
                app_mapping = {
                    "汽水音乐": ["汽水音乐", "汽水音乐.app"],
                    "spotify": ["Spotify", "Spotify.app"],
                    "chrome": ["Google Chrome", "Google Chrome.app"],
                    "safari": ["Safari", "Safari.app"],
                    "firefox": ["Firefox", "Firefox.app"],
                    "vscode": ["Visual Studio Code", "Visual Studio Code.app"],
                    "code": ["Visual Studio Code", "Visual Studio Code.app"],
                }
                
                if app_name.lower() in app_mapping:
                    app_variants.extend(app_mapping[app_name.lower()])
                
                # 尝试在 /Applications 目录下查找应用程序
                applications_dir = Path("/Applications")
                if applications_dir.exists():
                    for variant in app_variants:
                        app_path = applications_dir / variant
                        if app_path.exists() and app_path.is_dir():
                            logger.info(f"找到应用程序: {app_path}")
                            app_variants.insert(0, str(app_path))
                            break
                
                # 尝试打开应用程序
                opened = False
                last_error = None
                
                for variant in app_variants:
                    logger.info(f"尝试打开应用程序: {variant}（后台模式: {background}）")
                    # 如果需要在后台运行，使用 -g 选项（不激活应用程序窗口，在后台运行）
                    if background:
                        result = subprocess.run(
                            ["open", "-g", "-a", variant],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                    else:
                        result = subprocess.run(
                            ["open", "-a", variant],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                    
                    if result.returncode == 0:
                        # 验证应用程序是否真的打开了（检查进程）
                        import time
                        time.sleep(0.5)  # 等待应用程序启动
                        
                        # 检查进程是否在运行
                        check_result = subprocess.run(
                            ["pgrep", "-f", variant.replace(".app", "")],
                            capture_output=True,
                            text=True
                        )
                        
                        if check_result.returncode == 0 or variant in ["汽水音乐", "汽水音乐.app"]:
                            # 对于某些应用程序，pgrep 可能找不到，但如果 open 命令成功，通常表示已打开
                            opened = True
                            mode_str = "后台" if background else "前台"
                            logger.info(f"✅ 成功打开应用程序（{mode_str}模式）: {variant}")
                            break
                        else:
                            logger.warning(f"应用程序可能未成功启动: {variant}")
                            last_error = f"应用程序 {variant} 启动后未找到运行进程"
                    else:
                        last_error = result.stderr or f"打开 {variant} 失败"
                        logger.warning(f"尝试打开 {variant} 失败: {last_error}")
                
                if not opened:
                    raise BrowserError(
                        f"无法打开应用程序 '{app_name}'。"
                        f"已尝试: {', '.join(app_variants[:3])}。"
                        f"最后错误: {last_error}。"
                        f"请确认应用程序已安装且名称正确。"
                    )
                
            elif platform == "win32":  # Windows
                # Windows 使用 start 命令
                result = subprocess.run(
                    ["start", app_name],
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"打开应用程序失败: {result.stderr}")
                
            elif platform.startswith("linux"):  # Linux
                # Linux 使用应用程序名称直接启动
                result = subprocess.run(
                    [app_name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"打开应用程序失败: {result.stderr}")
            else:
                raise BrowserError(f"不支持的操作系统: {platform}")
            
            logger.info(f"✅ 已打开应用程序: {app_name}")
            
            return {
                "success": True,
                "message": f"已打开应用程序: {app_name}",
                "data": {"app_name": app_name}
            }
            
        except subprocess.TimeoutExpired:
            raise BrowserError("打开应用程序超时（超过10秒）")
        except Exception as e:
            logger.error(f"打开应用程序失败: {e}", exc_info=True)
            raise BrowserError(f"打开应用程序失败: {e}")
    
    def _close_app(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        关闭应用程序
        
        Args:
            params: 包含app_name（应用程序名称，必需）
                    - 可以是应用程序的完整名称（如 "汽水音乐"、"Spotify"）
                    - 可以是应用程序的bundle identifier（如 "com.spotify.client"）
        
        Returns:
            关闭结果
        """
        app_name = params.get("app_name")
        if not app_name:
            raise BrowserError("缺少app_name参数")
        
        platform = sys.platform
        
        try:
            if platform == "darwin":  # macOS
                # 尝试多种方式关闭应用程序
                app_variants = [
                    app_name,  # 原始名称
                    app_name.replace(".app", ""),  # 去除 .app 后缀
                ]
                
                # 尝试常见的应用程序名称映射
                app_mapping = {
                    "汽水音乐": ["汽水音乐", "汽水音乐.app"],
                    "spotify": ["Spotify"],
                    "chrome": ["Google Chrome"],
                    "safari": ["Safari"],
                    "firefox": ["Firefox"],
                    "vscode": ["Visual Studio Code"],
                    "code": ["Visual Studio Code"],
                }
                
                if app_name.lower() in app_mapping:
                    app_variants.extend(app_mapping[app_name.lower()])
                
                # 方法1：使用 osascript 优雅关闭（推荐）
                closed = False
                last_error = None
                
                for variant in app_variants:
                    try:
                        logger.info(f"尝试使用 osascript 关闭应用程序: {variant}")
                        result = subprocess.run(
                            ["osascript", "-e", f'tell application "{variant}" to quit'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        
                        if result.returncode == 0:
                            # 等待应用程序关闭
                            import time
                            time.sleep(0.5)
                            
                            # 验证应用程序是否真的关闭了
                            check_result = subprocess.run(
                                ["pgrep", "-f", variant.replace(".app", "")],
                                capture_output=True,
                                text=True
                            )
                            
                            if check_result.returncode != 0:
                                # 进程不存在，说明已关闭
                                closed = True
                                logger.info(f"✅ 成功关闭应用程序: {variant}")
                                break
                            else:
                                logger.warning(f"应用程序可能未完全关闭: {variant}")
                    except Exception as e:
                        logger.warning(f"osascript 关闭失败: {variant}, 错误: {e}")
                        last_error = str(e)
                
                # 方法2：如果 osascript 失败，使用 killall 强制关闭
                if not closed:
                    logger.info("osascript 关闭失败，尝试使用 killall 强制关闭")
                    for variant in app_variants:
                        process_name = variant.replace(".app", "")
                        try:
                            result = subprocess.run(
                                ["killall", process_name],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            
                            if result.returncode == 0:
                                closed = True
                                logger.info(f"✅ 成功强制关闭应用程序: {process_name}")
                                break
                            elif "No matching processes" not in result.stderr:
                                last_error = result.stderr
                        except Exception as e:
                            logger.warning(f"killall 关闭失败: {process_name}, 错误: {e}")
                            last_error = str(e)
                
                if not closed:
                    raise BrowserError(
                        f"无法关闭应用程序 '{app_name}'。"
                        f"已尝试: {', '.join(app_variants[:3])}。"
                        f"最后错误: {last_error or '应用程序可能未运行'}。"
                    )
                
            elif platform == "win32":  # Windows
                # Windows 使用 taskkill 命令
                result = subprocess.run(
                    ["taskkill", "/IM", app_name, "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0 and "not found" not in result.stderr.lower():
                    raise BrowserError(f"关闭应用程序失败: {result.stderr}")
                
            elif platform.startswith("linux"):  # Linux
                # Linux 使用 killall 命令
                result = subprocess.run(
                    ["killall", app_name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise BrowserError(f"关闭应用程序失败: {result.stderr}")
            else:
                raise BrowserError(f"不支持的操作系统: {platform}")
            
            logger.info(f"✅ 已关闭应用程序: {app_name}")
            
            return {
                "success": True,
                "message": f"已关闭应用程序: {app_name}",
                "data": {"app_name": app_name}
            }
            
        except subprocess.TimeoutExpired:
            raise BrowserError("关闭应用程序超时（超过10秒）")
        except Exception as e:
            logger.error(f"关闭应用程序失败: {e}", exc_info=True)
            raise BrowserError(f"关闭应用程序失败: {e}")
    
    def _execute_python_script(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Python脚本 - 增强版（使用 CodeInterpreter）
        
        功能：
        - 自动检测并安装缺失的 Python 包
        - Matplotlib 图表自动保存
        - 智能错误修复和自动重试
        - 代码执行结果记忆
        
        Args:
            params: 包含script（Python脚本代码，必需）、reason（原因，可选）、safety（安全检查说明，可选）
        
        Returns:
            执行结果，包含success、message、data、images等
        """
        script = params.get("script")
        if not script:
            raise BrowserError("缺少script参数")
        
        if not isinstance(script, str) or not script.strip():
            raise BrowserError("script参数必须是非空字符串")
        
        reason = params.get("reason", "未提供原因")
        safety = params.get("safety", "未提供安全检查说明")
        auto_install = params.get("auto_install", True)  # 是否自动安装缺失的包
        max_retries = params.get("max_retries", 2)  # 最大重试次数
        
        logger.info(f"执行Python脚本，原因: {reason}")
        logger.debug(f"安全检查说明: {safety}")
        logger.debug(f"脚本内容（前500字符）:\n{script[:500]}")
        
        # 使用增强版代码解释器执行
        try:
            result = self.code_interpreter.execute(
                code=script,
                reason=reason,
                auto_install=auto_install,
                max_retries=max_retries
            )
            
            # 构建返回结果
            response = {
                "success": result.success,
                "message": result.message,
                "data": result.data
            }
            
            # 如果有生成的图表，添加到结果中
            if result.images:
                response["images"] = result.images
                response["message"] += f" (生成了 {len(result.images)} 个图表)"
            
            # 如果自动安装了包，添加信息
            if result.installed_packages:
                response["installed_packages"] = result.installed_packages
                logger.info(f"自动安装了以下包: {', '.join(result.installed_packages)}")
            
            # 添加执行时间
            response["execution_time"] = result.execution_time
            
            if not result.success and result.error:
                response["error"] = result.error
            
            return response
            
        except Exception as e:
            logger.error(f"执行脚本失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"执行脚本失败: {str(e)}",
                "data": None,
                "error": str(e)
            }
    
    # === 保留旧方法作为备用（如果 CodeInterpreter 不可用）===
    def _execute_python_script_legacy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Python脚本（旧版本，保留作为备用）
        """
        script = params.get("script")
        reason = params.get("reason", "未提供原因")
        
        try:
            # 创建临时脚本文件
            import tempfile
            import os
            
            # 在沙盒目录中创建临时脚本文件
            temp_script_dir = self.sandbox_path / "scripts"
            temp_script_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建临时脚本文件
            import time as time_module
            temp_script_path = temp_script_dir / f"script_{int(time_module.time())}.py"
            
            # 处理脚本内容：可能是 base64 编码，也可能是普通字符串
            import base64
            script_content = None
            
            # 首先尝试 base64 解码
            try:
                # 移除所有空白字符
                script_clean = ''.join(script.split())
                script_to_decode = script_clean.strip()
                
                # 修复 padding
                missing_padding = len(script_to_decode) % 4
                if missing_padding:
                    script_to_decode += '=' * (4 - missing_padding)
                
                decoded_bytes = base64.b64decode(script_to_decode, validate=True)
                script_content = decoded_bytes.decode("utf-8")
            except Exception:
                script_content = script.replace("\\n", "\n")
            
            # 写入脚本文件
            with open(temp_script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            
            # 执行脚本
            result = subprocess.run(
                [sys.executable, str(temp_script_path)],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(self.sandbox_path)
            )
            
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "message": f"脚本执行失败: {stderr or stdout}",
                    "data": None,
                    "error": stderr or stdout
                }
            
            # 尝试解析 JSON 输出
            try:
                import json
                script_result = json.loads(stdout)
                return {
                    "success": script_result.get("success", True),
                    "message": script_result.get("message", "脚本执行完成"),
                    "data": script_result.get("data")
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "message": "脚本执行完成",
                    "data": {"output": stdout}
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "脚本执行超时",
                "error": "Timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"执行脚本失败: {str(e)}",
                "error": str(e)
            }
    # ========== 系统控制功能 ==========
    
    def _set_volume(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        设置系统音量
        
        Args:
            params: 包含 level (0-100) 或 action (mute/unmute/up/down)
        """
        level = params.get("level")
        action = params.get("action")
        
        try:
            if sys.platform == "darwin":
                if action == "mute":
                    subprocess.run(["osascript", "-e", "set volume with output muted"], check=True)
                    return {"success": True, "message": "已静音", "data": {"muted": True}}
                elif action == "unmute":
                    subprocess.run(["osascript", "-e", "set volume without output muted"], check=True)
                    return {"success": True, "message": "已取消静音", "data": {"muted": False}}
                elif action == "up":
                    subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 10)"], check=True)
                    return {"success": True, "message": "音量已增加", "data": {}}
                elif action == "down":
                    subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 10)"], check=True)
                    return {"success": True, "message": "音量已降低", "data": {}}
                elif level is not None:
                    level = max(0, min(100, int(level)))
                    subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=True)
                    return {"success": True, "message": "音量已设置为 " + str(level), "data": {"level": level}}
                else:
                    # 获取当前音量
                    result = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"], capture_output=True, text=True)
                    current = result.stdout.strip()
                    return {"success": True, "message": "当前音量: " + current, "data": {"level": int(current) if current.isdigit() else 0}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "设置音量失败: " + str(e), "data": None}
    
    def _set_brightness(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        设置屏幕亮度 (仅 macOS)
        
        Args:
            params: 包含 level (0.0-1.0) 或 action ("up"/"down"/"max"/"min")
        """
        level = params.get("level")
        action = params.get("action")
        
        try:
            if sys.platform == "darwin":
                # 方法1：使用 brightness 命令行工具
                try:
                    if action == "max" or level == 1.0 or level == 1:
                        result = subprocess.run(["brightness", "1"], capture_output=True, text=True)
                        if result.returncode == 0:
                            return {"success": True, "message": "亮度已调到最亮", "data": {"level": 1.0}}
                    elif action == "min" or level == 0.0 or level == 0:
                        result = subprocess.run(["brightness", "0"], capture_output=True, text=True)
                        if result.returncode == 0:
                            return {"success": True, "message": "亮度已调到最暗", "data": {"level": 0.0}}
                    elif level is not None:
                        level = max(0.0, min(1.0, float(level)))
                        result = subprocess.run(["brightness", str(level)], capture_output=True, text=True)
                        if result.returncode == 0:
                            return {"success": True, "message": "亮度已设置为 " + str(int(level * 100)) + "%", "data": {"level": level}}
                except FileNotFoundError:
                    pass  # brightness 工具未安装，尝试备选方案
                
                # 方法2：使用键盘快捷键模拟（通过 F1/F2 键）
                if action == "up":
                    # 模拟按下亮度增加键
                    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 144'], check=True)
                    return {"success": True, "message": "亮度已增加", "data": {}}
                elif action == "down":
                    # 模拟按下亮度降低键
                    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 145'], check=True)
                    return {"success": True, "message": "亮度已降低", "data": {}}
                elif action == "max" or level == 1.0 or level == 1:
                    # 连续按亮度增加键
                    for _ in range(16):
                        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 144'], capture_output=True)
                        time.sleep(0.05)
                    return {"success": True, "message": "亮度已调到最亮", "data": {"level": 1.0}}
                elif action == "min" or level == 0.0 or level == 0:
                    # 连续按亮度降低键
                    for _ in range(16):
                        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 145'], capture_output=True)
                        time.sleep(0.05)
                    return {"success": True, "message": "亮度已调到最暗", "data": {"level": 0.0}}
                else:
                    return {"success": False, "message": "请指定亮度级别 (0-1) 或操作 (up/down/max/min)。建议安装 brightness 工具: brew install brightness", "data": None}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "设置亮度失败: " + str(e), "data": None}
    
    def _send_notification(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送系统通知
        
        Args:
            params: 包含 title, message, subtitle (可选), sound (可选)
        """
        title = params.get("title", "DeskJarvis")
        message = params.get("message", "")
        subtitle = params.get("subtitle", "")
        sound = params.get("sound", True)
        
        try:
            if sys.platform == "darwin":
                script = f'display notification "{message}"'
                if title:
                    script += f' with title "{title}"'
                if subtitle:
                    script += f' subtitle "{subtitle}"'
                if sound:
                    script += ' sound name "default"'
                
                subprocess.run(["osascript", "-e", script], check=True)
                return {"success": True, "message": "通知已发送", "data": {"title": title, "message": message}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "发送通知失败: " + str(e), "data": None}
    
    def _clipboard_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        读取剪贴板内容
        """
        try:
            if sys.platform == "darwin":
                result = subprocess.run(["pbpaste"], capture_output=True, text=True)
                content = result.stdout
                return {"success": True, "message": "已读取剪贴板", "data": {"content": content}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "读取剪贴板失败: " + str(e), "data": None}
    
    def _clipboard_write(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        写入剪贴板
        
        Args:
            params: 包含 content (要复制的文本)
        """
        content = params.get("content", "")
        
        try:
            if sys.platform == "darwin":
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                process.communicate(content.encode("utf-8"))
                return {"success": True, "message": "已复制到剪贴板", "data": {"content": content[:50] + "..." if len(content) > 50 else content}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "写入剪贴板失败: " + str(e), "data": None}
    
    def _keyboard_type(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        模拟键盘输入
        
        Args:
            params: 包含 text (要输入的文本)
        """
        text = params.get("text", "")
        
        try:
            if sys.platform == "darwin":
                # 使用 osascript 模拟键盘输入
                escaped_text = text.replace('"', '\\"').replace("'", "\\'")
                script = f'tell application "System Events" to keystroke "{escaped_text}"'
                subprocess.run(["osascript", "-e", script], check=True)
                return {"success": True, "message": "已输入文本", "data": {"text": text[:30] + "..." if len(text) > 30 else text}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "键盘输入失败: " + str(e), "data": None}
    
    def _keyboard_shortcut(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送键盘快捷键
        
        Args:
            params: 包含 keys (如 "command+c", "command+shift+s")
        """
        keys = params.get("keys", "")
        
        try:
            if sys.platform == "darwin":
                # 解析快捷键
                parts = keys.lower().split("+")
                modifiers = []
                key = parts[-1] if parts else ""
                
                for part in parts[:-1]:
                    if part in ["cmd", "command"]:
                        modifiers.append("command down")
                    elif part in ["ctrl", "control"]:
                        modifiers.append("control down")
                    elif part in ["alt", "option"]:
                        modifiers.append("option down")
                    elif part in ["shift"]:
                        modifiers.append("shift down")
                
                modifier_str = ", ".join(modifiers) if modifiers else ""
                
                if modifier_str:
                    script = f'tell application "System Events" to keystroke "{key}" using {{{modifier_str}}}'
                else:
                    script = f'tell application "System Events" to keystroke "{key}"'
                
                subprocess.run(["osascript", "-e", script], check=True)
                return {"success": True, "message": "已发送快捷键: " + keys, "data": {"keys": keys}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "发送快捷键失败: " + str(e), "data": None}
    
    def _mouse_click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        模拟鼠标点击
        
        Args:
            params: 包含 x, y (屏幕坐标), button (left/right), clicks (点击次数)
        """
        x = params.get("x", 0)
        y = params.get("y", 0)
        button = params.get("button", "left")
        clicks = params.get("clicks", 1)
        
        try:
            if sys.platform == "darwin":
                # 使用 cliclick 工具（需要安装：brew install cliclick）
                click_cmd = "c" if button == "left" else "rc"
                if clicks == 2:
                    click_cmd = "dc"  # double click
                
                result = subprocess.run(["cliclick", f"{click_cmd}:{x},{y}"], capture_output=True, text=True)
                if result.returncode == 0:
                    return {"success": True, "message": "已点击坐标 (" + str(x) + ", " + str(y) + ")", "data": {"x": x, "y": y}}
                else:
                    return {"success": False, "message": "鼠标点击失败，请安装 cliclick: brew install cliclick", "data": None}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except FileNotFoundError:
            return {"success": False, "message": "请先安装 cliclick: brew install cliclick", "data": None}
        except Exception as e:
            return {"success": False, "message": "鼠标点击失败: " + str(e), "data": None}
    
    def _mouse_move(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        移动鼠标
        
        Args:
            params: 包含 x, y (屏幕坐标)
        """
        x = params.get("x", 0)
        y = params.get("y", 0)
        
        try:
            if sys.platform == "darwin":
                result = subprocess.run(["cliclick", f"m:{x},{y}"], capture_output=True, text=True)
                if result.returncode == 0:
                    return {"success": True, "message": "已移动鼠标到 (" + str(x) + ", " + str(y) + ")", "data": {"x": x, "y": y}}
                else:
                    return {"success": False, "message": "鼠标移动失败，请安装 cliclick: brew install cliclick", "data": None}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except FileNotFoundError:
            return {"success": False, "message": "请先安装 cliclick: brew install cliclick", "data": None}
        except Exception as e:
            return {"success": False, "message": "鼠标移动失败: " + str(e), "data": None}
    
    def _window_minimize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        最小化窗口
        
        Args:
            params: 包含 app_name (应用名称，可选，默认当前窗口)
        """
        app_name = params.get("app_name")
        
        try:
            if sys.platform == "darwin":
                if app_name:
                    script = f'tell application "{app_name}" to set miniaturized of window 1 to true'
                else:
                    script = 'tell application "System Events" to set miniaturized of window 1 of (first process whose frontmost is true) to true'
                
                subprocess.run(["osascript", "-e", script], check=True)
                return {"success": True, "message": "已最小化窗口", "data": {"app": app_name or "当前窗口"}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "最小化窗口失败: " + str(e), "data": None}
    
    def _window_maximize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        最大化窗口
        
        Args:
            params: 包含 app_name (应用名称，可选，默认当前窗口)
        """
        app_name = params.get("app_name")
        
        try:
            if sys.platform == "darwin":
                if app_name:
                    script = f'''
                    tell application "{app_name}"
                        activate
                        tell application "System Events"
                            keystroke "f" using {{control down, command down}}
                        end tell
                    end tell
                    '''
                else:
                    script = 'tell application "System Events" to keystroke "f" using {control down, command down}'
                
                subprocess.run(["osascript", "-e", script], check=True)
                return {"success": True, "message": "已最大化窗口", "data": {"app": app_name or "当前窗口"}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "最大化窗口失败: " + str(e), "data": None}
    
    def _window_close(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        关闭窗口
        
        Args:
            params: 包含 app_name (应用名称，可选，默认当前窗口)
        """
        app_name = params.get("app_name")
        
        try:
            if sys.platform == "darwin":
                if app_name:
                    script = f'tell application "{app_name}" to close window 1'
                else:
                    script = 'tell application "System Events" to keystroke "w" using command down'
                
                subprocess.run(["osascript", "-e", script], check=True)
                return {"success": True, "message": "已关闭窗口", "data": {"app": app_name or "当前窗口"}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "关闭窗口失败: " + str(e), "data": None}
    
    def _speak(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        语音播报
        
        Args:
            params: 包含 text (要播报的文本), voice (声音名称，可选)
        """
        text = params.get("text", "")
        voice = params.get("voice")
        
        try:
            if sys.platform == "darwin":
                cmd = ["say"]
                if voice:
                    cmd.extend(["-v", voice])
                cmd.append(text)
                
                subprocess.run(cmd, check=True)
                return {"success": True, "message": "已播报", "data": {"text": text[:30] + "..." if len(text) > 30 else text}}
            else:
                return {"success": False, "message": "此功能仅支持 macOS", "data": None}
        except Exception as e:
            return {"success": False, "message": "语音播报失败: " + str(e), "data": None}
    
    # ========== 系统信息查询 ==========
    
    def _get_system_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取系统信息
        
        Args:
            params: 包含 info_type (信息类型: battery/disk/memory/cpu/network/apps)
        """
        info_type = params.get("info_type", "all")
        
        try:
            result_data = {}
            
            if info_type in ["battery", "all"]:
                # 获取电池信息
                if sys.platform == "darwin":
                    battery_result = subprocess.run(
                        ["pmset", "-g", "batt"],
                        capture_output=True, text=True
                    )
                    if battery_result.returncode == 0:
                        output = battery_result.stdout
                        # 解析电池百分比
                        import re
                        match = re.search(r'(\d+)%', output)
                        if match:
                            result_data["battery"] = {
                                "percentage": int(match.group(1)),
                                "charging": "charging" in output.lower() or "ac power" in output.lower()
                            }
            
            if info_type in ["disk", "all"]:
                # 获取磁盘信息
                disk_result = subprocess.run(
                    ["df", "-h", "/"],
                    capture_output=True, text=True
                )
                if disk_result.returncode == 0:
                    lines = disk_result.stdout.strip().split("\n")
                    if len(lines) > 1:
                        parts = lines[1].split()
                        if len(parts) >= 5:
                            result_data["disk"] = {
                                "total": parts[1],
                                "used": parts[2],
                                "available": parts[3],
                                "use_percent": parts[4]
                            }
            
            if info_type in ["memory", "all"]:
                # 获取内存信息
                if sys.platform == "darwin":
                    mem_result = subprocess.run(
                        ["vm_stat"],
                        capture_output=True, text=True
                    )
                    if mem_result.returncode == 0:
                        # 简化内存信息
                        result_data["memory"] = {"info": "macOS 内存使用正常"}
            
            if info_type in ["apps", "all"]:
                # 获取运行中的应用
                if sys.platform == "darwin":
                    apps_result = subprocess.run(
                        ["osascript", "-e", 'tell application "System Events" to get name of every process whose background only is false'],
                        capture_output=True, text=True
                    )
                    if apps_result.returncode == 0:
                        apps = [app.strip() for app in apps_result.stdout.split(",")]
                        result_data["running_apps"] = apps[:20]  # 最多显示20个
            
            if info_type in ["network", "all"]:
                # 获取网络信息
                if sys.platform == "darwin":
                    # 获取 IP
                    ip_result = subprocess.run(
                        ["ipconfig", "getifaddr", "en0"],
                        capture_output=True, text=True
                    )
                    if ip_result.returncode == 0:
                        result_data["network"] = {
                            "local_ip": ip_result.stdout.strip()
                        }
            
            # 构建消息
            message_parts = []
            report_lines = ["# 系统信息报告", ""]
            report_lines.append("生成时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))
            report_lines.append("")
            
            if "battery" in result_data:
                b = result_data["battery"]
                status = "充电中" if b["charging"] else "使用电池"
                message_parts.append("电池: " + str(b["percentage"]) + "% (" + status + ")")
                report_lines.append("## 电池状态")
                report_lines.append("- 电量: " + str(b["percentage"]) + "%")
                report_lines.append("- 状态: " + status)
                report_lines.append("")
            
            if "disk" in result_data:
                d = result_data["disk"]
                message_parts.append("磁盘: 已用 " + d["used"] + " / 总共 " + d["total"] + " (" + d["use_percent"] + ")")
                report_lines.append("## 磁盘空间")
                report_lines.append("- 总容量: " + d["total"])
                report_lines.append("- 已使用: " + d["used"])
                report_lines.append("- 可用: " + d["available"])
                report_lines.append("- 使用率: " + d["use_percent"])
                report_lines.append("")
            
            if "memory" in result_data:
                report_lines.append("## 内存状态")
                report_lines.append("- 状态: " + result_data["memory"].get("info", "正常"))
                report_lines.append("")
            
            if "running_apps" in result_data:
                apps = result_data["running_apps"]
                message_parts.append("运行中应用: " + str(len(apps)) + " 个")
                report_lines.append("## 运行中的应用 (" + str(len(apps)) + " 个)")
                for app in apps:
                    report_lines.append("- " + app)
                report_lines.append("")
            
            if "network" in result_data:
                n = result_data["network"]
                message_parts.append("本机IP: " + n.get("local_ip", "未知"))
                report_lines.append("## 网络信息")
                report_lines.append("- 本机IP: " + n.get("local_ip", "未知"))
                report_lines.append("")
            
            message = "; ".join(message_parts) if message_parts else "系统信息获取完成"
            
            # 如果指定了保存路径，保存报告
            save_path = params.get("save_path", "")
            if save_path:
                import os
                if save_path.startswith("~"):
                    save_path = os.path.expanduser(save_path)
                
                # 确保目录存在
                save_dir = os.path.dirname(save_path)
                if save_dir:
                    os.makedirs(save_dir, exist_ok=True)
                
                report_content = "\n".join(report_lines)
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(report_content)
                
                message = message + "，报告已保存到: " + save_path
                result_data["saved_path"] = save_path
            
            return {"success": True, "message": message, "data": result_data}
        except Exception as e:
            return {"success": False, "message": "获取系统信息失败: " + str(e), "data": None}
    
    # ========== 图片处理 ==========
    
    def _image_process(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        图片处理
        
        Args:
            params: 包含 
                - image_path: 图片路径
                - action: 操作类型 (compress/resize/convert/info)
                - width: 目标宽度 (resize时使用)
                - height: 目标高度 (resize时使用)
                - format: 目标格式 (convert时使用，如 jpg/png/webp)
                - quality: 压缩质量 (compress时使用，1-100)
        """
        image_path = params.get("image_path", "")
        action = params.get("action", "info")
        
        try:
            from PIL import Image
            import os
            
            # 解析路径
            if image_path.startswith("~"):
                image_path = os.path.expanduser(image_path)
            
            if not os.path.exists(image_path):
                return {"success": False, "message": "图片不存在: " + image_path, "data": None}
            
            img = Image.open(image_path)
            original_size = os.path.getsize(image_path)
            
            if action == "info":
                # 获取图片信息
                return {
                    "success": True,
                    "message": "图片: " + str(img.width) + "x" + str(img.height) + ", " + img.format + ", " + self._format_size(original_size),
                    "data": {
                        "width": img.width,
                        "height": img.height,
                        "format": img.format,
                        "mode": img.mode,
                        "size_bytes": original_size
                    }
                }
            
            elif action == "compress":
                quality = params.get("quality", 80)
                output_path = self._get_output_path(image_path, "_compressed")
                
                # 转换为 RGB 如果需要
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                img.save(output_path, "JPEG", quality=quality, optimize=True)
                new_size = os.path.getsize(output_path)
                
                return {
                    "success": True,
                    "message": "已压缩图片，从 " + self._format_size(original_size) + " 到 " + self._format_size(new_size),
                    "data": {"path": output_path, "original_size": original_size, "new_size": new_size}
                }
            
            elif action == "resize":
                width = params.get("width")
                height = params.get("height")
                
                if width and not height:
                    ratio = width / img.width
                    height = int(img.height * ratio)
                elif height and not width:
                    ratio = height / img.height
                    width = int(img.width * ratio)
                elif not width and not height:
                    return {"success": False, "message": "请指定宽度或高度", "data": None}
                
                output_path = self._get_output_path(image_path, "_resized")
                resized = img.resize((int(width), int(height)), Image.Resampling.LANCZOS)
                resized.save(output_path)
                
                return {
                    "success": True,
                    "message": "已调整图片大小为 " + str(width) + "x" + str(height),
                    "data": {"path": output_path, "width": width, "height": height}
                }
            
            elif action == "convert":
                target_format = params.get("format", "jpg").lower()
                format_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "gif": "GIF"}
                
                if target_format not in format_map:
                    return {"success": False, "message": "不支持的格式: " + target_format, "data": None}
                
                # 修改扩展名
                base = os.path.splitext(image_path)[0]
                output_path = base + "." + target_format
                
                # 转换模式
                if target_format in ["jpg", "jpeg"] and img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                img.save(output_path, format_map[target_format])
                
                return {
                    "success": True,
                    "message": "已转换为 " + target_format.upper() + " 格式",
                    "data": {"path": output_path}
                }
            
            else:
                return {"success": False, "message": "未知的操作: " + action, "data": None}
                
        except ImportError:
            return {"success": False, "message": "需要安装 Pillow 库: pip install Pillow", "data": None}
        except Exception as e:
            return {"success": False, "message": "图片处理失败: " + str(e), "data": None}
    
    def _get_output_path(self, original_path: str, suffix: str) -> str:
        """生成输出路径"""
        import os
        base, ext = os.path.splitext(original_path)
        return base + suffix + ext
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return str(size_bytes) + " B"
        elif size_bytes < 1024 * 1024:
            return str(round(size_bytes / 1024, 1)) + " KB"
        else:
            return str(round(size_bytes / (1024 * 1024), 1)) + " MB"
    
    # ========== 定时提醒 ==========
    
    def _set_reminder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        设置提醒
        
        Args:
            params: 包含
                - message: 提醒内容
                - delay: 延迟时间（如 "5分钟", "1小时"）
                - repeat: 重复类型 (可选: daily/hourly/weekly)
        """
        from agent.scheduler import get_scheduler, parse_time_expression
        
        message = params.get("message", "提醒时间到了")
        delay_expr = params.get("delay", "")
        repeat = params.get("repeat")
        
        if not delay_expr:
            return {"success": False, "message": "请指定延迟时间，如 '5分钟后'", "data": None}
        
        delay_seconds = parse_time_expression(delay_expr)
        if not delay_seconds:
            return {"success": False, "message": "无法解析时间: " + delay_expr, "data": None}
        
        scheduler = get_scheduler()
        return scheduler.add_reminder(message=message, delay_seconds=delay_seconds, repeat=repeat)
    
    def _list_reminders(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出所有提醒"""
        from agent.scheduler import get_scheduler
        scheduler = get_scheduler()
        return scheduler.list_reminders()
    
    def _cancel_reminder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """取消提醒"""
        from agent.scheduler import get_scheduler
        reminder_id = params.get("reminder_id", "")
        if not reminder_id:
            return {"success": False, "message": "请指定提醒ID", "data": None}
        scheduler = get_scheduler()
        return scheduler.cancel_reminder(reminder_id)
    
    # ========== 工作流管理 ==========
    
    def _create_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """创建工作流"""
        from agent.workflows import get_workflow_manager
        name = params.get("name", "")
        commands = params.get("commands", [])
        description = params.get("description", "")
        return get_workflow_manager().add_workflow(name, commands, description)
    
    def _list_workflows(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出工作流"""
        from agent.workflows import get_workflow_manager
        return get_workflow_manager().list_workflows()
    
    def _delete_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """删除工作流"""
        from agent.workflows import get_workflow_manager
        name = params.get("name", "")
        return get_workflow_manager().delete_workflow(name)
    
    # ========== 任务历史 ==========
    
    def _get_task_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取任务历史"""
        from agent.history import get_task_history
        limit = params.get("limit", 20)
        return get_task_history().get_recent_tasks(limit)
    
    def _search_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索历史"""
        from agent.history import get_task_history
        keyword = params.get("keyword", "")
        return get_task_history().search_history(keyword)
    
    def _add_favorite(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """添加收藏"""
        from agent.history import get_task_history
        instruction = params.get("instruction", "")
        name = params.get("name")
        return get_task_history().add_favorite(instruction, name)
    
    def _list_favorites(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """列出收藏"""
        from agent.history import get_task_history
        return get_task_history().list_favorites()
    
    def _remove_favorite(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """移除收藏"""
        from agent.history import get_task_history
        favorite_id = params.get("favorite_id", "")
        return get_task_history().remove_favorite(favorite_id)
    
    # ========== 文本AI处理 ==========
    
    def _text_process(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        文本AI处理（翻译、总结、润色等）
        
        Args:
            params: 包含
                - text: 要处理的文本
                - action: 操作类型 (translate/summarize/polish/expand/fix_grammar)
                - target_lang: 目标语言（翻译时使用，如 "英文"、"日文"）
        """
        text = params.get("text", "")
        action = params.get("action", "")
        target_lang = params.get("target_lang", "英文")
        
        if not text:
            return {"success": False, "message": "请提供要处理的文本", "data": None}
        
        # 构建处理提示
        prompts = {
            "translate": f"请将以下文本翻译成{target_lang}，只输出翻译结果，不要有其他内容：\n\n{text}",
            "summarize": f"请总结以下文本的主要内容，简洁明了：\n\n{text}",
            "polish": f"请润色以下文本，使其更加通顺优美：\n\n{text}",
            "expand": f"请扩写以下文本，添加更多细节：\n\n{text}",
            "fix_grammar": f"请修正以下文本中的语法和拼写错误：\n\n{text}"
        }
        
        if action not in prompts:
            return {"success": False, "message": "未知的操作: " + action + "，支持: translate/summarize/polish/expand/fix_grammar", "data": None}
        
        try:
            # 使用配置的 AI 进行处理
            from agent.tools.config import Config
            import os
            
            config = Config()
            provider = config.provider
            
            if provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=config.api_key)
                response = client.messages.create(
                    model=config.model,
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompts[action]}]
                )
                result_text = response.content[0].text
            elif provider == "deepseek":
                import openai
                client = openai.OpenAI(
                    api_key=config.api_key,
                    base_url="https://api.deepseek.com/v1"
                )
                response = client.chat.completions.create(
                    model=config.model,
                    messages=[{"role": "user", "content": prompts[action]}],
                    max_tokens=2000
                )
                result_text = response.choices[0].message.content
            else:
                return {"success": False, "message": "不支持的AI提供商: " + provider, "data": None}
            
            action_names = {
                "translate": "翻译",
                "summarize": "总结", 
                "polish": "润色",
                "expand": "扩写",
                "fix_grammar": "语法修正"
            }
            
            return {
                "success": True,
                "message": action_names.get(action, action) + "完成",
                "data": {"result": result_text, "action": action}
            }
            
        except Exception as e:
            return {"success": False, "message": "文本处理失败: " + str(e), "data": None}