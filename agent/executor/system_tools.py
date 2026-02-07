"""
系统工具：系统级操作（截图、系统命令等）

遵循 docs/ARCHITECTURE.md 中的Executor模块规范
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import sys
import subprocess
import time
import platform
import json
import base64
from datetime import datetime, timedelta
from pathlib import Path
from agent.tools.exceptions import BrowserError, FileManagerError
from agent.tools.config import Config
from agent.executor.code_interpreter import CodeInterpreter
from agent.executor.document_processor import DocumentProcessor
from agent.executor.ocr_helper import OCRHelper
from agent.executor.base_executor import BaseExecutor

logger = logging.getLogger(__name__)


class SystemTools(BaseExecutor):
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
        super().__init__(config, emit_callback)
        self.sandbox_path = Path(config.sandbox_path).resolve()
        self.sandbox_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化增强版代码解释器
        self.code_interpreter = CodeInterpreter(self.sandbox_path, emit_callback)
        
        # 初始化文档处理器
        self.doc_processor = DocumentProcessor()
        
        # 初始化OCR助手（用于视觉辅助的OCR降级）
        self.ocr_helper = OCRHelper()
        
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
    
    def execute_step(self, step: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行系统操作步骤
        
        Args:
            step: 任务步骤，包含type、action、params等
        
        Returns:
            执行结果
        """
        self._log_execution_start(step)
        step_type = step.get("type")
        action = step.get("action", "")
        params = step.get("params", {})
        
        try:
            if step_type == "screenshot_desktop":
                return self._screenshot_desktop(params)
            elif step_type == "open_folder":
                return self._open_folder(params)
            elif step_type == "open_file":
                return self._open_file(params)
            elif step_type == "list_files":
                return self._list_files(params)
            elif step_type == "open_app":
                return self._open_app(params)
            elif step_type == "close_app":
                return self._close_app(params)
            elif step_type == "execute_python_script":
                return self._execute_python_script(params, context)
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
            # ========== 下载 ==========
            elif step_type == "download_latest_python_installer":
                return self._download_latest_python_installer(params)
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
            # ========== 文本AI处理与进阶分析 ==========
            elif step_type == "text_process":
                return self._text_process(params)
            elif step_type == "analyze_document":
                return self._analyze_document(params)
            elif step_type == "run_applescript":
                return self._run_applescript(params)
            elif step_type == "manage_calendar_event":
                return self._manage_calendar_event(params)
            elif step_type == "manage_reminder":
                return self._manage_reminder(params)
            # ========== 视觉交互助手 (Phase 39) ==========
            elif step_type == "visual_assist":
                return self._visual_assist(params, context)
            else:
                # 如果是不支持的操作，返回明确的错误信息
                # 列出 SystemTools 支持的所有操作类型，避免 AI 误解
                supported_types = [
                    "screenshot_desktop", "open_folder", "open_file", "list_files",
                    "open_app", "close_app", "execute_python_script",
                    "set_volume", "set_brightness", "send_notification",
                    "clipboard_read", "clipboard_write", "keyboard_type", "keyboard_shortcut",
                    "mouse_click", "mouse_move", "window_minimize", "window_maximize", "window_close",
                    "speak", "get_system_info", "image_process",
                    "set_reminder", "list_reminders", "cancel_reminder",
                    "create_workflow", "list_workflows", "delete_workflow",
                    "get_task_history", "search_history", "add_favorite", "list_favorites", "remove_favorite",
                    "text_process", "analyze_document", "run_applescript",
                    "manage_calendar_event", "manage_reminder",
                    "visual_assist"  # Phase 39: 视觉交互助手
                ]
                
                # 检测是否是文件操作相关的错误类型
                file_related_types = ["file_manager", "FileManager", "file_operation", "app_control"]
                if step_type in file_related_types:
                    return {
                        "success": False,
                        "message": f"错误：'{step_type}' 不是有效的操作类型。文件操作应使用标准类型：file_delete, file_read, file_write, file_create, file_rename, file_move, file_copy。当前操作类型 '{step_type}' 无效。",
                        "data": None,
                        "suggested_type": "file_delete" if "delete" in str(step.get("action", "")).lower() else "file_read"
                    }
                
                return {
                    "success": False,
                    "message": f"SystemTools 不支持的操作类型: '{step_type}'。支持的类型: {', '.join(supported_types[:10])}...",
                    "data": None
                }
                
        except Exception as e:
            logger.error(f"执行系统操作失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"操作失败: {e}",
                "data": {
                    "error_type": "execution_exception",
                    "exception": str(e),
                    "step_type": step_type,
                    "suggestion": "请检查操作参数和系统状态"
                }
            }

    def _resolve_user_path(self, path_str: str, default_base: Optional[Path] = None) -> Path:
        """
        将用户输入的路径解析为绝对路径，并限制在用户主目录下。

        Args:
            path_str: 用户输入路径（支持 ~、相对路径）
            default_base: 相对路径的基准目录，默认用户主目录

        Returns:
            解析后的绝对路径

        Raises:
            BrowserError: 路径不在用户主目录下
        """
        home = Path.home()
        base = default_base or home

        path_str = (path_str or "").strip()
        if not path_str:
            raise BrowserError("路径不能为空")

        if path_str.startswith("~/"):
            path_str = str(home / path_str[2:])
        elif path_str.startswith("~"):
            path_str = str(home / path_str[1:])

        path = Path(path_str)
        if not path.is_absolute():
            path = base / path

        path = path.resolve()

        try:
            path.relative_to(home)
        except ValueError as e:
            raise BrowserError(f"路径不在允许的范围内（仅允许用户主目录下）: {path}") from e

        return path

    def _fetch_latest_python_version(self, timeout: int = 30) -> str:
        """
        从 python.org 获取最新 Python 3 版本号。

        Args:
            timeout: 超时秒数

        Returns:
            版本号字符串，例如 "3.13.1"
        """
        import re
        import requests

        url = "https://www.python.org/downloads/"
        logger.info(f"获取最新 Python 版本: {url}")
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "DeskJarvis/1.0"})
        resp.raise_for_status()

        # 常见页面格式：Latest Python 3 Release - Python 3.x.y
        m = re.search(r"Latest Python 3 Release\s*-\s*Python\s+(\d+\.\d+\.\d+)", resp.text)
        if m:
            return m.group(1)

        # 回退：抓第一个 “Download Python 3.x.y”
        m2 = re.search(r"Download Python\s+(\d+\.\d+\.\d+)", resp.text)
        if m2:
            return m2.group(1)

        raise BrowserError("无法从 python.org 解析最新 Python 版本号")

    def _pick_python_installer_filename(self, version: str) -> Tuple[str, str]:
        """
        根据当前平台选择 Python 安装包文件名候选，并返回首个可用项。

        Args:
            version: Python 版本号，如 "3.13.1"

        Returns:
            (filename, download_url)
        """
        import requests

        base_url = f"https://www.python.org/ftp/python/{version}/"
        platform = sys.platform

        if platform == "darwin":
            candidates = [
                f"python-{version}-macos11.pkg",
                f"python-{version}-macos10.9.pkg",
                f"python-{version}-macosx10.9.pkg",
            ]
        elif platform == "win32":
            candidates = [
                f"python-{version}-amd64.exe",
                f"python-{version}-amd64-webinstall.exe",
            ]
        elif platform.startswith("linux"):
            candidates = [
                f"Python-{version}.tar.xz",
                f"Python-{version}.tgz",
            ]
        else:
            raise BrowserError(f"不支持的操作系统: {platform}")

        for filename in candidates:
            url = base_url + filename
            try:
                r = requests.head(url, timeout=15, allow_redirects=True, headers={"User-Agent": "DeskJarvis/1.0"})
                if r.status_code == 200:
                    return filename, url
            except Exception:
                continue

        raise BrowserError("未找到可用的 Python 安装包文件（可能是版本/平台文件名规则变化）")

    def _download_latest_python_installer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        下载最新 Python 安装包（确定性工具，不依赖 AI 生成脚本）。

        Params:
            - save_dir: 保存目录（可选，默认桌面）
            - save_path: 保存路径（可选，若提供则优先使用；可为目录或完整文件路径）
            - timeout: 超时毫秒（可选，默认 180000）

        Returns:
            dict: {"success": bool, "message": str, "data": {...}}
        """
        import requests

        timeout_ms = int(params.get("timeout", 180000))
        timeout_s = max(10, timeout_ms // 1000)

        home = Path.home()
        desktop = home / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)

        save_path_param = params.get("save_path")
        save_dir_param = params.get("save_dir")

        # 1) 解析目标保存目录/路径
        target_base = desktop
        if save_dir_param:
            target_base = self._resolve_user_path(str(save_dir_param), default_base=home)
            target_base.mkdir(parents=True, exist_ok=True)

        explicit_path: Optional[Path] = None
        if save_path_param:
            explicit_path = self._resolve_user_path(str(save_path_param), default_base=target_base)

        # 2) 获取最新版本并选择安装包
        version = self._fetch_latest_python_version(timeout=30)
        filename, download_url = self._pick_python_installer_filename(version)

        # 3) 确定最终保存路径
        if explicit_path is not None:
            if explicit_path.exists() and explicit_path.is_dir():
                file_path = explicit_path / filename
            else:
                # 如果看起来像目录（以分隔符结尾），也当目录处理
                if str(save_path_param).endswith("/") or str(save_path_param).endswith("\\"):
                    explicit_path.mkdir(parents=True, exist_ok=True)
                    file_path = explicit_path / filename
                else:
                    # 若用户给的是文件名但没扩展名，也保留原样；这里不强行改名
                    explicit_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path = explicit_path
        else:
            file_path = target_base / filename

        logger.info(f"准备下载 Python 安装包: version={version}, url={download_url}")
        logger.info(f"保存路径: {file_path}")

        # 4) 下载（stream）
        try:
            with requests.get(download_url, stream=True, timeout=(30, timeout_s), headers={"User-Agent": "DeskJarvis/1.0"}) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", "0") or "0")
                written = 0
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if not chunk:
                            continue
                        f.write(chunk)
                        written += len(chunk)
                if total > 0 and written == 0:
                    raise BrowserError("下载失败：写入 0 字节")

            if not file_path.exists() or file_path.stat().st_size == 0:
                raise BrowserError("下载失败：文件未生成或大小为 0")

            size_bytes = file_path.stat().st_size
            return {
                "success": True,
                "message": "已下载最新 Python 安装包: " + str(file_path),
                "data": {
                    "version": version,
                    "url": download_url,
                    "file_path": str(file_path),
                    "size_bytes": size_bytes,
                },
            }
        except Exception as e:
            logger.error(f"下载 Python 安装包失败: {e}", exc_info=True)
            return {"success": False, "message": "下载 Python 安装包失败: " + str(e), "data": None}
    
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
        if save_path.suffix == "":
            try:
                # 尝试判断是否为已有目录
                if save_path.exists() and save_path.is_dir():
                    # 是目录，追加默认文件名
                    import time
                    save_path = save_path / f"screenshot_{int(time.time())}.png"
                    logger.info(f"目标路径是目录，自动追加文件名: {save_path}")
                elif str(save_path).endswith("/") or str(save_path).endswith("\\"):
                    # 以斜杠结尾，视为目录
                    save_path.mkdir(parents=True, exist_ok=True)
                    import time
                    save_path = save_path / f"screenshot_{int(time.time())}.png"
                else: 
                     # 可能是文件名但没有后缀，加上 .png
                     save_path = save_path.with_suffix(".png")
            except Exception as e:
                logger.warning(f"判断路径类型出错，默认视为文件: {e}")

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
        
        # === 新增：类型检查守卫（最后防线）===
        # 检查是否包含文件路径特征，防止误将文件路径当作应用名称
        file_path_indicators = ['/', '\\', '.txt', '.jpg', '.png', '.pdf', '.docx', '.py', 
                               '.mp4', '.zip', '.rar', '~/', 'Desktop/', 'Downloads/']
        
        if any(indicator in str(app_name) for indicator in file_path_indicators):
            error_msg = f"拒绝执行：'{app_name}' 看起来像是一个文件路径，而不是应用程序名称。请检查您的指令是否为'删除文件'或'文件操作'。"
            logger.error(f"[SystemTools] {error_msg}")
            raise ValueError(error_msg)
        
        # 检查是否包含明显的文件操作关键词
        file_keywords = ['删除', '删除文件', '删除图片', '删除文档', 'file', '文件', '图片', '文档']
        app_name_lower = str(app_name).lower()
        if any(kw in app_name_lower for kw in file_keywords):
            error_msg = f"拒绝执行：'{app_name}' 包含文件操作关键词，这可能是意图路由错误。请使用文件操作工具（file_delete）而不是关闭应用。"
            logger.error(f"[SystemTools] {error_msg}")
            raise ValueError(error_msg)
        
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
    
    def _execute_python_script(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行Python脚本 - 增强版（使用 CodeInterpreter）
        
        功能：
        - 自动检测并安装缺失的 Python 包
        - Matplotlib 图表自动保存
        - 智能错误修复和自动重试
        - 代码执行结果记忆
        - 自动注入上下文数据（context_data）
        
        Args:
            params: 包含script（Python脚本代码，必需）、reason（原因，可选）、safety（安全检查说明，可选）
            context: 执行上下文，包含 step_results 等信息，会自动注入到脚本中
        
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
        
        # 检查脚本是否包含 Base64 编码（避免 Planner 错误使用 Base64）
        import base64
        import string
        script_clean = "".join(script.split())
        base64_chars = set(string.ascii_letters + string.digits + "+/=_-")
        looks_like_base64 = len(script_clean) >= 64 and all(c in base64_chars for c in script_clean)
        if looks_like_base64 and not script.lstrip().startswith(("import ", "from ", "def ", "class ", "#", '"""')):
            logger.warning("⚠️ 检测到脚本可能是 Base64 编码，建议 Planner 直接使用 Python 源码，避免 Base64 包装")
            logger.warning("💡 提示：对于包含中文的字符串，使用 json.dumps() 或原始字符串（r''）处理，不要使用 Base64")
        
        # 使用增强版代码解释器执行（传递 context 以便注入 context_data）
        try:
            result = self.code_interpreter.execute(
                code=script,
                reason=reason,
                auto_install=auto_install,
                max_retries=max_retries,
                context=context
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
        模拟键盘输入（支持中文、英文、数字、符号）
        
        Args:
            params: 包含 text (要输入的文本)
        """
        text = params.get("text", "")
        
        try:
            if sys.platform == "darwin":
                # macOS 的 osascript keystroke 支持中文，但需要特殊处理
                # 方法1：直接使用 keystroke（支持中文）
                # 对于包含中文的文本，使用剪贴板方式更可靠
                import re
                
                # 检测是否包含中文字符
                has_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))
                
                if has_chinese:
                    # 方法：使用剪贴板 + Cmd+V（更可靠的中文输入方式）
                    # 1. 先复制到剪贴板
                    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                    process.communicate(text.encode("utf-8"))
                    process.wait()
                    
                    # 2. 等待一下确保复制完成
                    import time
                    time.sleep(0.1)
                    
                    # 3. 粘贴（Cmd+V）
                    subprocess.run(
                        ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
                        check=True
                    )
                else:
                    # 纯英文/数字/符号，直接使用 keystroke
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
            params: 包含 keys (如 "command+c", "command+shift+s", "enter", "tab")
                - repeat: 重复次数（可选，默认 1）
                - delay_ms: 每次按键间延迟毫秒（可选，默认 80）
        """
        keys = params.get("keys", "")
        repeat = int(params.get("repeat", 1) or 1)
        delay_ms = int(params.get("delay_ms", 80) or 80)
        
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

                # 特殊按键映射：这些不能用 keystroke "enter"（会打出字母），必须用 key code
                special_key_codes = {
                    "enter": 36,
                    "return": 36,
                    "tab": 48,
                    "esc": 53,
                    "escape": 53,
                    "delete": 51,          # backspace
                    "backspace": 51,
                    "forwarddelete": 117,  # fn+delete
                    "space": 49,
                    "left": 123,
                    "right": 124,
                    "down": 125,
                    "up": 126,
                }

                def build_applescript() -> str:
                    # 优先识别特殊键
                    if key in special_key_codes:
                        code = special_key_codes[key]
                        if modifier_str:
                            return f'tell application "System Events" to key code {code} using {{{modifier_str}}}'
                        return f'tell application "System Events" to key code {code}'

                    # 普通字符（含字母、数字、符号）
                    if modifier_str:
                        return f'tell application "System Events" to keystroke "{key}" using {{{modifier_str}}}'
                    return f'tell application "System Events" to keystroke "{key}"'

                script_once = build_applescript()
                # repeat 次执行（避免在 AppleScript 内拼 repeat，保持简单可靠）
                for _ in range(max(1, repeat)):
                    subprocess.run(["osascript", "-e", script_once], check=True)
                    if delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)

                return {
                    "success": True,
                    "message": "已发送按键: " + keys + (" ×" + str(repeat) if repeat > 1 else ""),
                    "data": {"keys": keys, "repeat": repeat},
                }
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
    
    def _list_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        列出目录下的文件 (Grounding Protocol G)
        
        Args:
            params: 包含 path (可选，默认桌面)
        """
        path_str = params.get("path", "~/Desktop")
        try:
            full_path = Path(path_str).expanduser().resolve()
            if not full_path.exists():
                # SMART 回馈：如果父目录存在，报错时附带父目录内容
                parent = full_path.parent
                suggestion = ""
                if parent.exists():
                    suggestion = f" 目录不存在，但父目录包含: {[f.name for f in parent.iterdir()][:10]}"
                return {"success": False, "message": f"目录不存在: {path_str}{suggestion}"}
            
            items = []
            for item in full_path.iterdir():
                items.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0
                })
            
            return {
                "success": True,
                "message": f"成功列出 {path_str} 下的 {len(items)} 个项目",
                "data": {"path": str(full_path), "items": items}
            }
        except Exception as e:
            return {"success": False, "message": f"列出文件失败: {e}"}

    def _get_smart_suggestions(self, target_path: Path) -> Dict[str, Any]:
        """
        SMART 错误反馈：生成智能建议（模糊匹配、目录内容等）
        
        Args:
            target_path: 目标文件路径
        
        Returns:
            包含建议信息的字典
        """
        import difflib
        import os
        
        parent = target_path.parent
        suggestions = {
            "parent_directory": str(parent),
            "directory_contents": [],
            "similar_files": [],
            "same_extension_files": [],
            "subdirectories": []
        }
        
        # 如果父目录不存在，尝试搜索常见目录
        if not parent.exists():
            # 尝试在用户主目录下搜索
            home = Path.home()
            common_dirs = [
                home / "Desktop",
                home / "Downloads",
                home / "Documents",
                home
            ]
            
            for common_dir in common_dirs:
                if common_dir.exists():
                    suggestions["parent_directory"] = str(common_dir)
                    parent = common_dir
                    break
        
        if not parent.exists():
            return suggestions
        
        # 收集目录内容
        try:
            all_items = list(parent.iterdir())
            
            # 1. 获取所有文件（带详细信息）
            files = []
            for item in all_items:
                if item.is_file():
                    try:
                        stat = item.stat()
                        files.append({
                            "name": item.name,
                            "type": "file",
                            "size": stat.st_size,
                            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
                        })
                    except Exception:
                        files.append({
                            "name": item.name,
                            "type": "file",
                            "size": 0,
                            "modified": "unknown"
                        })
            
            # 2. 获取子目录
            dirs = [item.name for item in all_items if item.is_dir()]
            
            # 3. 模糊匹配相似文件名
            all_file_names = [f["name"] for f in files]
            if target_path.name and all_file_names:
                similar = difflib.get_close_matches(
                    target_path.name, 
                    all_file_names, 
                    n=5, 
                    cutoff=0.3  # 降低阈值以匹配更多文件
                )
                suggestions["similar_files"] = similar
            
            # 4. 同扩展名文件
            if target_path.suffix:
                same_ext = [
                    f["name"] for f in files 
                    if f["name"].lower().endswith(target_path.suffix.lower())
                ][:10]
                suggestions["same_extension_files"] = same_ext
            
            # 5. 限制返回的文件数量（避免信息过载）
            suggestions["directory_contents"] = files[:20]
            suggestions["subdirectories"] = dirs[:10]
            
        except Exception as e:
            logger.warning(f"生成智能建议时出错: {e}")
        
        return suggestions

    def _analyze_document(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        智能文档分析 (Phase 37)
        """
        file_path = params.get("file_path")
        action = params.get("action", "map")
        
        if not file_path:
            return {"success": False, "message": "缺失文档路径"}

        # 缓存检查 (Protocol R3)
        cache = (context or {}).get("_file_context_buffer", {})
        
        # 1. 尝试从文件夹智能搜索
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            # SMART Error Reporting: 如果文件不存在，提供智能建议 (Protocol G+)
            suggestions = self._get_smart_suggestions(path)
            
            error_msg = f"未找到文档: {file_path}"
            if suggestions.get("similar_files"):
                error_msg += f"。发现相似文件: {', '.join(suggestions['similar_files'][:3])}"
            elif suggestions.get("directory_contents"):
                error_msg += f"。目录内容: {', '.join([f['name'] for f in suggestions['directory_contents'][:5]])}"
            
            return {
                "success": False,
                "message": error_msg,
                "suggestions": suggestions
            }
        
        file_key = str(path)

        # 2. 执行处理逻辑
        try:
            if action == "map":
                # 检查缓存
                if file_key in cache and "map" in cache[file_key]:
                    return {"success": True, "message": "从缓存中恢复报告", "data": cache[file_key]["map"]}
                
                data = self.doc_processor.get_document_map(file_key)
                if "error" not in data:
                    if file_key not in cache: cache[file_key] = {}
                    cache[file_key]["map"] = data # 存入缓存
            elif action == "read":
                page_num = params.get("page_num")
                # 读特定页
                data = self.doc_processor.read_specific_chunk(file_key, page_num=page_num, keywords=params.get("keywords"))
            elif action == "analyze":
                # 深度分析逻辑
                doc_map = self.doc_processor.get_document_map(file_key)
                if "error" in doc_map: return {"success": False, "message": doc_map["error"]}
                
                content_data = self.doc_processor.read_specific_chunk(file_key, page_num=1)
                content = content_data.get("content", "")
                
                query = params.get("query", "请总结这份文档。")
                prompt = f"文件: {path.name}\n结构: {json.dumps(doc_map)}\n\n内容:\n{content}\n\n问题: {query}"
                return self._text_process({"text": prompt, "action": "summarize"})
            else:
                return {"success": False, "message": f"不支持的操作: {action}"}

            return {
                "success": "error" not in data,
                "message": "文档处理成功" if "error" not in data else data["error"],
                "data": data
            }
        except Exception as e:
            return {"success": False, "message": f"处理失败: {e}"}

    def _run_applescript(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行 AppleScript (Phase 38 伏笔)
        """
        script = params.get("script")
        if not script:
            return {"success": False, "message": "缺失脚本内容"}
            
        try:
            process = subprocess.Popen(
                ['osascript', '-e', script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                return {"success": True, "message": "AppleScript 执行成功", "data": stdout.strip()}
            else:
                return {"success": False, "message": f"AppleScript 报错: {stderr}"}
        except Exception as e:
            return {"success": False, "message": f"执行异常: {e}"}

    def _parse_calendar_events(self, list_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        解析日历事件列表（从 AppleScript 返回的 JSON）
        
        Args:
            list_result: list 操作的返回结果
        
        Returns:
            事件列表，每个事件包含 title, start, end
        """
        events = []
        
        if not list_result.get("success"):
            return events
        
        data = list_result.get("data", "")
        if not data:
            return events
        
        try:
            # 尝试解析 JSON
            if data.strip().startswith("["):
                events = json.loads(data)
            else:
                # 如果不是 JSON，尝试从原始文本中提取
                # AppleScript 可能返回 "event 1, event 2" 格式
                logger.warning("日历事件列表不是 JSON 格式，无法解析")
        except json.JSONDecodeError as e:
            logger.warning(f"解析日历事件 JSON 失败: {e}")
        
        return events
    
    def _check_time_conflicts(self, start_time: str, end_time: Optional[str], existing_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        检查时间冲突
        
        Args:
            start_time: 新事件的开始时间（格式: "2026-02-07 10:00:00"）
            end_time: 新事件的结束时间（可选）
            existing_events: 现有事件列表
        
        Returns:
            冲突事件列表
        """
        conflicts = []
        
        try:
            # 解析新事件的时间
            new_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            
            # 如果没有提供结束时间，默认1小时
            if end_time:
                new_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            else:
                new_end = new_start + timedelta(hours=1)
            
            # 检查每个现有事件
            for event in existing_events:
                event_start_str = event.get("start")
                event_end_str = event.get("end")
                event_title = event.get("title", "未知事件")
                
                if not event_start_str:
                    continue
                
                try:
                    # 解析现有事件的时间（可能格式不同）
                    event_start = datetime.strptime(event_start_str, "%Y-%m-%d %H:%M:%S")
                    
                    if event_end_str:
                        event_end = datetime.strptime(event_end_str, "%Y-%m-%d %H:%M:%S")
                    else:
                        # 如果没有结束时间，默认1小时
                        event_end = event_start + timedelta(hours=1)
                    
                    # 检查时间重叠
                    if self._is_time_overlapping(new_start, new_end, event_start, event_end):
                        conflicts.append({
                            "title": event_title,
                            "start": event_start_str,
                            "end": event_end_str
                        })
                except ValueError:
                    # 时间格式不匹配，跳过
                    continue
        
        except ValueError as e:
            logger.warning(f"解析时间失败: {e}")
        
        return conflicts
    
    def _is_time_overlapping(self, start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
        """
        检查两个时间范围是否重叠
        
        Args:
            start1, end1: 第一个时间范围
            start2, end2: 第二个时间范围
        
        Returns:
            如果重叠返回 True
        """
        return start1 < end2 and start2 < end1

    def _manage_calendar_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        管理日历事件 (Phase 38)
        
        Args:
            params: 包含
                - action: create/delete/list (必需)
                - title: 事件标题 (create/delete时)
                - start_time: 开始时间 (如 "2026-02-07 10:00:00")
                - end_time: 结束时间 (可选)
                - duration: 时长 (分钟, 可选)
        """
        action = params.get("action")
        title = params.get("title", "新会议")
        start_time = params.get("start_time")
        end_time = params.get("end_time")
        duration = params.get("duration")  # 分钟
        
        if platform.system() != "Darwin":
            return {"success": False, "message": "目前仅支持 macOS 系统操控日历"}

        if action == "create":
            if not start_time: 
                return {"success": False, "message": "创建事件需要 start_time"}
            
            # Protocol Phase 38+: 冲突预警 - 先检查冲突
            logger.info("🔵 Phase 38+: 创建日历事件前检查冲突...")
            list_result = self._manage_calendar_event({"action": "list"})
            existing_events = self._parse_calendar_events(list_result)
            
            # 计算结束时间
            if not end_time and duration:
                start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                end_dt = start_dt + timedelta(minutes=int(duration))
                end_time = end_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            # 检查冲突
            conflicts = self._check_time_conflicts(start_time, end_time, existing_events)
            
            # 创建事件
            script = f'''
            tell application "Calendar"
                tell calendar "Work"
                    make new event with properties {{summary:"{title}", start date:date "{start_time}"}}
                end tell
            end tell
            '''
            # 如果 Work 日历不存在，尝试使用第一个日历
            fallback_script = f'''
            tell application "Calendar"
                set theCalendar to first calendar
                make new event at theCalendar with properties {{summary:"{title}", start date:date "{start_time}"}}
            end tell
            '''
            res = self._run_applescript({"script": script})
            if not res["success"]:
                res = self._run_applescript({"script": fallback_script})
            
            # 如果有冲突，添加警告信息
            if conflicts and res.get("success"):
                conflict_titles = [c["title"] for c in conflicts]
                res["warnings"] = conflicts
                res["message"] = res.get("message", "事件已创建") + f"。⚠️ 检测到时间冲突: {', '.join(conflict_titles)}"
                logger.warning(f"⚠️ 日历事件创建成功，但检测到冲突: {conflict_titles}")
            
            return res
            
        elif action == "list":
            # 改进 list 操作：返回 JSON 格式的事件列表
            script = '''
            tell application "Calendar"
                set theCalendar to first calendar
                set eventsList to {}
                set allEvents to events of theCalendar
                repeat with e in allEvents
                    try
                        set eventInfo to "{\\"title\\":\\"" & (summary of e) & "\\",\\"start\\":\\"" & (start date of e as string) & "\\""
                        if end date of e is not missing value then
                            set eventInfo to eventInfo & ",\\"end\\":\\"" & (end date of e as string) & "\\""
                        end if
                        set eventInfo to eventInfo & "}"
                        set end of eventsList to eventInfo
                    end try
                end repeat
                return "[" & (eventsList as string) & "]"
            end tell
            '''
            result = self._run_applescript({"script": script})
            
            # 尝试解析 JSON
            if result.get("success") and result.get("data"):
                try:
                    events_json = json.loads(result["data"])
                    result["data"] = events_json
                    result["events"] = events_json  # 兼容字段
                except json.JSONDecodeError:
                    logger.warning("无法解析日历事件 JSON，返回原始数据")
            
            return result
            
        return {"success": False, "message": f"不支持的操作: {action}"}

    def _manage_reminder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        管理提醒事项 (Phase 38)
        """
        action = params.get("action")
        title = params.get("title")
        
        if platform.system() != "Darwin":
            return {"success": False, "message": "目前仅支持 macOS 系统操控提醒事项"}

        if action == "create":
            if not title: return {"success": False, "message": "创建提醒需要 title"}
            script = f'''
            tell application "Reminders"
                make new reminder with properties {{name:"{title}"}}
            end tell
            '''
            return self._run_applescript({"script": script})
        
        elif action == "list":
            script = 'tell application "Reminders" to get name of reminders'
            return self._run_applescript({"script": script})

        return {"success": False, "message": f"不支持的操作: {action}"}

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

    def _visual_assist(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        视觉助手：分析截图并回答问题（Phase 39）
        
        分级调度策略（成本优先）：
        - L1: 本地OCR（如果查询是文本查找类，成本0，速度<500ms）
        - L2: VLM语义理解（如果查询需要理解界面布局、外观等，成本较高）
        
        Args:
            params: 包含
                - action: "query"（问答，默认）/ "locate"（定位）/ "extract_text"（提取文本）
                - query: 问题（必需），如"屏幕上那个红色的按钮写什么？"
                - image_path: 图片路径（可选，如果不提供则自动截图）
                - force_vlm: 是否强制使用VLM（默认False，优先OCR）
        
        Returns:
            分析结果，包含：
            - answer: 答案文本
            - coordinates: 坐标信息（如果定位到元素）{"x": 100, "y": 200}
            - confidence: 置信度（0.0-1.0）
            - method: 使用的方法（"ocr" 或 "vlm"）
            - timestamp: 截图时间戳（用于坐标系验证）
        """
        import os
        
        action = params.get("action", "query")
        query = params.get("query", "")
        image_path = params.get("image_path")
        force_vlm = params.get("force_vlm", False)
        
        # extract_text 操作不需要 query 参数（提取所有文本）
        # query 和 locate 操作需要 query 参数
        if action != "extract_text" and not query:
            return {
                "success": False,
                "message": f"缺少query参数（{action}操作需要query参数）",
                "data": {
                    "error_type": "missing_parameter",
                    "missing_param": "query",
                    "suggestion": f"{action}操作需要提供query参数"
                }
            }
        
        # 对于 extract_text，如果没有 query，使用默认值
        if action == "extract_text" and not query:
            query = "提取图片中的所有文字"
        
        # 1. 如果没有提供图片路径，先截图
        if not image_path:
            logger.info("🔵 visual_assist: 未提供图片路径，自动截图...")
            screenshot_result = self._screenshot_desktop({})
            if not screenshot_result.get("success"):
                return {
                    "success": False,
                    "message": f"截图失败: {screenshot_result.get('message')}",
                    "data": {
                        "error_type": "screenshot_failed",
                        "suggestion": "检查截图权限或手动提供图片路径"
                    }
                }
            image_path = screenshot_result["data"]["path"]
            screenshot_timestamp = time.time()  # 截图完成时间
            logger.info(f"✅ 截图完成: {image_path}")
        else:
            # 验证图片是否存在
            image_path_obj = Path(image_path).expanduser()
            if not image_path_obj.exists():
                return {
                    "success": False,
                    "message": f"图片不存在: {image_path}",
                    "data": {
                        "error_type": "file_not_found",
                        "file_path": image_path,
                        "suggestion": "请检查图片路径是否正确"
                    }
                }
            image_path = str(image_path_obj)
            # 使用文件修改时间作为时间戳
            screenshot_timestamp = image_path_obj.stat().st_mtime
        
        # 2. 检查坐标系时效性（如果距离截图时间超过5秒，警告）
        current_time = time.time()
        if current_time - screenshot_timestamp > 5:
            logger.warning(f"⚠️ 警告：截图时间戳已过期（{current_time - screenshot_timestamp:.1f}秒），坐标可能不准确")
        
        # 3. 分级调度：判断是否可以使用OCR
        use_ocr_first = not force_vlm and self._should_use_ocr(query)
        
        if use_ocr_first and action in ["query", "locate", "extract_text"]:
            # L1: 尝试OCR优先（成本0，速度快）
            logger.info("🔵 visual_assist: 使用OCR优先策略（成本0）")
            ocr_result = self._analyze_with_ocr(image_path, query, action)
            
            if ocr_result.get("success"):
                # 确保 data 字段存在
                if "data" not in ocr_result:
                    ocr_result["data"] = {}
                ocr_result["data"]["method"] = "ocr"
                ocr_result["data"]["timestamp"] = screenshot_timestamp
                logger.info("✅ OCR分析成功，跳过VLM调用（节省成本）")
                return ocr_result
            
            # OCR 失败，检查是否需要继续尝试 VLM
            ocr_data = ocr_result.get("data", {})
            requires_vlm = ocr_data.get("requires_vlm", False)
            
            if requires_vlm:
                # 视觉理解任务，OCR 无法处理是正常的，继续尝试 VLM
                logger.info("🔵 OCR 无法处理视觉理解任务（颜色/图标/布局），继续使用 VLM")
            else:
                # 文本提取任务但 OCR 失败，记录警告但继续尝试 VLM
                logger.warning(f"⚠️ OCR 提取文本失败: {ocr_result.get('message')}，继续尝试 VLM")
        
        # L2: 使用VLM语义理解（或OCR失败后的降级）
        logger.info("🔵 visual_assist: 使用VLM语义理解")
        vlm_result = self._analyze_with_vlm(image_path, query, action)
        
        if vlm_result.get("success"):
            # 确保 data 字段存在
            if "data" not in vlm_result:
                vlm_result["data"] = {}
            vlm_result["data"]["timestamp"] = screenshot_timestamp
            return vlm_result
        else:
            # VLM失败，尝试OCR降级
            logger.warning("⚠️ VLM分析失败，尝试OCR降级")
            ocr_result = self._analyze_with_ocr(image_path, query, action)
            if ocr_result.get("success"):
                # 确保 data 字段存在
                if "data" not in ocr_result:
                    ocr_result["data"] = {}
                ocr_result["data"]["method"] = "ocr_fallback"
                ocr_result["data"]["timestamp"] = screenshot_timestamp
                return ocr_result
            
            # 构建详细的错误信息
            vlm_error = vlm_result.get("message", "未知错误")
            ocr_error = ocr_result.get("message", "未知错误") if not ocr_result.get("success") else None
            
            # 提取建议
            suggestions = []
            if "DeepSeek" in vlm_error or "不支持视觉" in vlm_error:
                suggestions.append("切换到支持视觉的模型：在 config.json 中设置 provider='claude' 或 'openai'，并配置对应的 API Key")
            if "ddddocr 未安装" in (ocr_error or ""):
                suggestions.append("安装OCR依赖：运行 'pip install ddddocr'")
            
            error_message = "视觉分析失败：VLM和OCR均不可用"
            if suggestions:
                error_message += "\n\n修复建议：\n" + "\n".join(f"- {s}" for s in suggestions)
            
            # 判断是否为配置错误（不可恢复）
            is_config_error = (
                "DeepSeek" in vlm_error or 
                "不支持视觉" in vlm_error or 
                "未配置API Key" in vlm_error or
                "ddddocr 未安装" in (ocr_error or "") or
                "pip install" in (ocr_error or "")
            )
            
            return {
                "success": False,
                "message": error_message,
                "data": {
                    "timestamp": screenshot_timestamp,
                    "vlm_error": vlm_error,
                    "ocr_error": ocr_error,
                    "vlm_data": vlm_result.get("data"),
                    "ocr_data": ocr_result.get("data") if not ocr_result.get("success") else None,
                    "suggestions": suggestions,
                    "is_config_error": is_config_error,  # 标记为配置错误
                    "requires_user_action": is_config_error  # 需要用户操作
                }
            }
    
    def _should_use_ocr(self, query: str) -> bool:
        """
        判断查询是否适合使用OCR（文本查找类查询）
        
        Args:
            query: 用户查询
        
        Returns:
            True 如果适合OCR，False 如果需要VLM语义理解
        """
        # 首先检查是否是视觉理解任务（坐标、颜色、位置等），这些必须使用 VLM
        if self._is_visual_understanding_query(query):
            return False
        
        query_lower = query.lower()
        
        # OCR适合的场景：文本查找、文字识别
        ocr_keywords = [
            "有没有", "找到", "查找", "识别", "提取", "读取",
            "写什么", "是什么字", "什么文字", "什么内容",
            "包含", "显示", "显示什么"
        ]
        
        # VLM适合的场景：布局、外观、理解、描述
        vlm_keywords = [
            "外观", "排版", "布局", "样式", "设计", "界面",
            "描述", "分析", "理解", "问题", "错误", "异常"
        ]
        
        # 如果包含VLM关键词，优先VLM
        if any(kw in query_lower for kw in vlm_keywords):
            return False
        
        # 如果包含OCR关键词，优先OCR
        if any(kw in query_lower for kw in ocr_keywords):
            return True
        
        # 默认：短查询用OCR，长查询用VLM
        return len(query) < 30
    
    def _is_visual_understanding_query(self, query: str) -> bool:
        """
        判断查询是否是视觉理解任务（OCR 无法处理，必须使用 VLM）
        
        Args:
            query: 用户查询
        
        Returns:
            True 如果是视觉理解任务（颜色、图标、布局等）
        """
        query_lower = query.lower()
        
        # 视觉理解任务关键词：颜色、图标、形状、位置、坐标、布局等
        visual_keywords = [
            "颜色", "图标", "形状", "位置", "坐标", "布局",
            "icon", "color", "position", "coordinate", "location",
            "最明显", "最突出", "左上角", "右下角", "中间", "归一化",
            "什么颜色", "什么图标", "在哪里", "哪个位置", "给出坐标",
            "坐标", "位置", "定位", "在哪里", "哪个位置"
        ]
        
        return any(kw in query_lower for kw in visual_keywords)
    
    def _analyze_with_ocr(self, image_path: str, query: str, action: str) -> Dict[str, Any]:
        """
        使用OCR分析图片（L1：成本0，速度快）
        
        Args:
            image_path: 图片路径
            query: 查询问题
            action: 操作类型
        
        Returns:
            OCR分析结果
        """
        try:
            # 读取图片并转换为base64
            with open(image_path, "rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode()
            
            # 检查OCR是否可用
            if not self.ocr_helper.is_available():
                return {
                    "success": False,
                    "message": "OCR不可用：ddddocr 未安装。请运行 'pip install ddddocr' 安装OCR依赖",
                    "data": {
                        "error_type": "missing_dependency",
                        "dependency": "ddddocr",
                        "install_command": "pip install ddddocr",
                        "suggestion": "安装 ddddocr 库以启用OCR功能"
                    }
                }
            
            # 使用OCR提取文本（优先使用extract_text方法）
            if hasattr(self.ocr_helper, 'extract_text'):
                ocr_text = self.ocr_helper.extract_text(image_base64)
            else:
                # 降级到recognize_captcha（不限制长度）
                ocr_text = self.ocr_helper.recognize_captcha(
                    image_base64, 
                    confidence_check=False  # 不限制长度，提取所有文本
                )
            
            if not ocr_text:
                # 检查是否是视觉理解任务（颜色、图标等），OCR 无法处理这些任务
                is_visual_task = self._is_visual_understanding_query(query)
                if is_visual_task:
                    # 视觉理解任务，OCR 无法处理是正常的，返回特殊标记，让调用者继续尝试 VLM
                    return {
                        "success": False,
                        "message": "OCR无法处理视觉理解任务（颜色/图标/布局等），需要VLM",
                        "data": {
                            "error_type": "ocr_visual_task",
                            "requires_vlm": True,  # 标记需要 VLM
                            "suggestion": "此任务需要视觉理解能力，请使用支持视觉的模型（Claude 或 OpenAI）"
                        }
                    }
                else:
                    # 文本提取任务，OCR 失败
                    return {
                        "success": False,
                        "message": "OCR未能提取到文本（可能是图片中没有文字，或OCR识别失败）",
                        "data": {
                            "error_type": "ocr_no_text",
                            "suggestion": "如果图片包含文字但识别失败，请检查图片质量或尝试使用VLM"
                        }
                    }
            
            logger.info(f"✅ OCR提取文本成功（长度: {len(ocr_text)}）")
            
            # 检查提取的文字是否过少（可能是OCR能力限制）
            if len(ocr_text) < 10:
                logger.warning(f"⚠️ OCR提取的文字较少（{len(ocr_text)}字符），可能不完整")
                logger.info("💡 如果桌面有更多文字但未识别，建议：1) 安装 Tesseract OCR (brew install tesseract && pip install pytesseract pillow) 2) 或使用支持视觉的模型（Claude/OpenAI）")
            
            # 根据action处理
            if action == "extract_text":
                # 直接返回提取的文本
                return {
                    "success": True,
                    "message": f"文本提取成功（{len(ocr_text)}字符）" + ("（文字较少，可能不完整）" if len(ocr_text) < 10 else ""),
                    "data": {
                        "text": ocr_text,
                        "method": "ocr",
                        "text_length": len(ocr_text),
                        "warning": "文字较少，可能不完整" if len(ocr_text) < 10 else None
                    }
                }
            elif action == "locate":
                # OCR 无法提供坐标信息，locate 操作必须使用 VLM
                return {
                    "success": False,
                    "message": "OCR无法提供坐标信息，locate操作需要VLM视觉理解能力",
                    "data": {
                        "error_type": "ocr_no_coordinates",
                        "requires_vlm": True,  # 标记需要 VLM
                        "text": ocr_text,  # 提供OCR文本作为参考
                        "suggestion": "定位操作需要视觉理解能力，请使用支持视觉的模型（Claude 或 OpenAI）"
                    }
                }
            else:  # action == "query"
                # 检查查询是否涉及视觉理解（位置、坐标、颜色等）
                # 即使 OCR 提取到了文本，如果查询需要视觉理解，也应该使用 VLM
                if self._is_visual_understanding_query(query):
                    return {
                        "success": False,
                        "message": "查询涉及视觉理解（位置/坐标/颜色等），OCR无法提供这些信息，需要VLM",
                        "data": {
                            "error_type": "ocr_visual_query",
                            "requires_vlm": True,  # 标记需要 VLM
                            "text": ocr_text,  # 提供OCR文本作为参考
                            "suggestion": "此查询需要视觉理解能力，请使用支持视觉的模型（Claude 或 OpenAI）"
                        }
                    }
                
                # 使用LLM分析OCR文本（纯文本查询）
                prompt = f"""
这是一张截图的OCR文本内容：
{ocr_text}

请回答以下问题：{query}

注意：如果问题涉及视觉元素的位置、颜色、布局等，OCR无法提供这些信息，请如实说明。
"""
                
                # 调用文本处理（使用现有的text_process）
                text_result = self._text_process({
                    "text": prompt,
                    "action": "summarize"  # 使用summarize作为通用分析
                })
                
                if text_result.get("success"):
                    return {
                        "success": True,
                        "message": "OCR+LLM分析成功",
                        "data": {
                            "answer": text_result["data"].get("result", ""),
                            "ocr_text": ocr_text,
                            "method": "ocr_llm"
                        }
                    }
                else:
                    return {
                        "success": False,
                        "message": f"LLM分析失败: {text_result.get('message')}",
                        "data": {
                            "error_type": "llm_analysis_failed",
                            "llm_error": text_result.get('message'),
                            "suggestion": "请检查AI配置或重试"
                        }
                    }
                    
        except Exception as e:
            logger.error(f"OCR分析失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"OCR分析失败: {e}",
                "data": {
                    "error_type": "ocr_exception",
                    "exception": str(e),
                    "suggestion": "请检查OCR依赖是否正确安装"
                }
            }
    
    def _analyze_with_vlm(self, image_path: str, query: str, action: str) -> Dict[str, Any]:
        """
        使用VLM（视觉语言模型）分析图片（L2：成本较高，但理解能力强）
        
        Args:
            image_path: 图片路径
            query: 查询问题
            action: 操作类型
        
        Returns:
            VLM分析结果
        """
        try:
            # 检测VLM是否可用
            if not self._is_vlm_available():
                provider = self.config.provider.lower()
                if provider == "deepseek":
                    return {
                        "success": False,
                        "message": "VLM不可用：DeepSeek 不支持视觉功能。请在 config.json 中切换到 Claude (claude-3-5-sonnet) 或 OpenAI (gpt-4o-mini)，并配置对应的 API Key",
                        "data": {
                            "provider": provider,
                            "suggestion": "切换到支持视觉的模型：Claude 或 OpenAI"
                        }
                    }
                else:
                    return {
                        "success": False,
                        "message": f"VLM不可用：当前配置 (provider={provider}, model={self.config.model}) 不支持视觉。请切换到 Claude (claude-3-5-sonnet) 或 OpenAI (gpt-4o-mini)",
                        "data": {
                            "provider": provider,
                            "model": self.config.model,
                            "suggestion": "切换到支持视觉的模型"
                        }
                    }
            
            # 读取图片
            with open(image_path, "rb") as f:
                image_data = f.read()
            
            # 根据provider选择VLM API
            provider = self.config.provider.lower()
            
            if provider == "claude":
                return self._call_claude_vision(image_path, image_data, query, action)
            elif provider in ["openai", "chatgpt"]:
                return self._call_openai_vision(image_path, image_data, query, action)
            elif provider == "deepseek":
                # DeepSeek 不支持视觉，直接返回错误（不应该到达这里，因为 _is_vlm_available 已经检查）
                return {
                    "success": False,
                    "message": "DeepSeek 不支持视觉功能。请在 config.json 中切换到 Claude (claude-3-5-sonnet) 或 OpenAI (gpt-4o-mini)",
                    "data": {
                        "provider": provider,
                        "suggestion": "切换到支持视觉的模型"
                    }
                }
            else:
                return {
                    "success": False,
                    "message": f"VLM不支持该提供商: {provider}",
                    "data": None
                }
                
        except Exception as e:
            logger.error(f"VLM分析失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"VLM分析失败: {e}",
                "data": {
                    "error_type": "vlm_exception",
                    "exception": str(e),
                    "suggestion": "请检查VLM配置或重试"
                }
            }
    
    def _is_vlm_available(self) -> bool:
        """
        检测VLM是否可用
        
        Returns:
            True 如果VLM可用
        """
        # 检查API Key
        if not self.config.api_key:
            logger.warning("⚠️ VLM不可用：未配置API Key")
            return False
        
        # 检查provider是否支持视觉
        provider = self.config.provider.lower()
        
        # DeepSeek 明确不支持视觉
        if provider == "deepseek":
            logger.warning("⚠️ VLM不可用：DeepSeek 不支持视觉功能。请切换到 Claude (claude-3-5-sonnet) 或 OpenAI (gpt-4o-mini)")
            return False
        
        vision_supported = provider in ["claude", "openai", "chatgpt"]
        
        # 检查模型是否支持视觉
        model = self.config.model.lower()
        if provider == "claude":
            # Claude 3.5 Sonnet 支持视觉
            vision_supported = vision_supported and "sonnet" in model
            if not vision_supported:
                logger.warning(f"⚠️ VLM不可用：Claude 模型 '{model}' 不支持视觉。请使用 claude-3-5-sonnet")
        elif provider in ["openai", "chatgpt"]:
            # GPT-4o, GPT-4o-mini 支持视觉
            vision_supported = vision_supported and ("gpt-4o" in model or "gpt-4-vision" in model)
            if not vision_supported:
                logger.warning(f"⚠️ VLM不可用：OpenAI 模型 '{model}' 不支持视觉。请使用 gpt-4o 或 gpt-4o-mini")
        
        return vision_supported
    
    def _call_claude_vision(self, image_path: str, image_data: bytes, query: str, action: str) -> Dict[str, Any]:
        """调用Claude Vision API"""
        try:
            from anthropic import Anthropic
            
            client = Anthropic(api_key=self.config.api_key)
            model = self.config.model or "claude-3-5-sonnet-20241022"
            
            image_base64 = base64.b64encode(image_data).decode()
            
            # 构建prompt（根据action调整）
            if action == "locate":
                prompt = f"""
请分析这张截图，找到描述为"{query}"的元素。

如果找到，请返回JSON格式：
{{
    "found": true,
    "x": 100,  # 元素中心X坐标（屏幕坐标系，考虑Retina缩放）
    "y": 200,  # 元素中心Y坐标
    "description": "元素描述",
    "confidence": 0.95
}}

如果未找到，返回：
{{
    "found": false,
    "reason": "未找到原因"
}}

注意：macOS Retina屏幕的截图像素可能是2880px，但系统坐标系只有1440px，请返回系统坐标系坐标。
"""
            elif action == "extract_text":
                prompt = """
请提取这张截图中的所有文本内容，返回纯文本格式。
"""
            else:  # query
                prompt = f"""
请分析这张截图，回答以下问题：{query}

如果问题涉及元素位置，请尽可能提供坐标信息（系统坐标系，考虑Retina缩放）。
"""
            
            message = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }]
            )
            
            response_text = message.content[0].text
            
            # 解析响应（尝试提取JSON）
            result = self._parse_vlm_response(response_text, action)
            result["method"] = "vlm_claude"
            
            return {
                "success": True,
                "message": "VLM分析成功",
                "data": result
            }
            
        except ImportError:
            return {
                "success": False,
                "message": "anthropic库未安装",
                "data": {
                    "error_type": "missing_dependency",
                    "dependency": "anthropic",
                    "install_command": "pip install anthropic",
                    "suggestion": "安装 anthropic 库以使用 Claude Vision"
                }
            }
        except Exception as e:
            logger.error(f"Claude Vision API调用失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Claude Vision API调用失败: {e}",
                "data": {
                    "error_type": "claude_api_error",
                    "exception": str(e),
                    "suggestion": "请检查API Key和网络连接"
                }
            }
    
    def _call_openai_vision(self, image_path: str, image_data: bytes, query: str, action: str) -> Dict[str, Any]:
        """调用OpenAI Vision API (GPT-4o-mini)"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.config.api_key)
            model = self.config.model or "gpt-4o-mini"
            
            image_base64 = base64.b64encode(image_data).decode()
            
            # 构建prompt
            if action == "locate":
                prompt = f"""
请分析这张截图，找到描述为"{query}"的元素。

如果找到，请返回JSON格式：
{{
    "found": true,
    "x": 100,
    "y": 200,
    "description": "元素描述",
    "confidence": 0.95
}}

注意：macOS Retina屏幕的截图像素可能是2880px，但系统坐标系只有1440px，请返回系统坐标系坐标。
"""
            elif action == "extract_text":
                prompt = "请提取这张截图中的所有文本内容，返回纯文本格式。"
            else:
                prompt = f"请分析这张截图，回答以下问题：{query}"
            
            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }],
                max_tokens=1024
            )
            
            response_text = response.choices[0].message.content
            
            # 解析响应
            result = self._parse_vlm_response(response_text, action)
            result["method"] = "vlm_openai"
            
            return {
                "success": True,
                "message": "VLM分析成功",
                "data": result
            }
            
        except ImportError:
            return {
                "success": False,
                "message": "openai库未安装",
                "data": {
                    "error_type": "missing_dependency",
                    "dependency": "openai",
                    "install_command": "pip install openai",
                    "suggestion": "安装 openai 库以使用 OpenAI Vision"
                }
            }
        except Exception as e:
            logger.error(f"OpenAI Vision API调用失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"OpenAI Vision API调用失败: {e}",
                "data": {
                    "error_type": "openai_api_error",
                    "exception": str(e),
                    "suggestion": "请检查API Key和网络连接"
                }
            }
    
    def _call_deepseek_vision(self, image_path: str, image_data: bytes, query: str, action: str) -> Dict[str, Any]:
        """调用DeepSeek Vision API（如果支持）"""
        # DeepSeek目前可能不支持视觉，返回错误
        return {
            "success": False,
            "message": "DeepSeek目前不支持视觉功能",
            "data": {
                "error_type": "provider_not_supported",
                "provider": "deepseek",
                "suggestion": "请切换到支持视觉的模型（Claude 或 OpenAI）"
            }
        }
    
    def _parse_vlm_response(self, response_text: str, action: str) -> Dict[str, Any]:
        """
        解析VLM响应（尝试提取JSON，处理坐标信息）
        
        Args:
            response_text: VLM返回的文本
            action: 操作类型
        
        Returns:
            解析后的结果字典
        """
        import json
        import re
        
        result = {
            "answer": response_text,
            "coordinates": None,
            "confidence": 0.8,  # 默认置信度
            "found": False
        }
        
        # 尝试提取JSON（如果响应包含JSON）
        try:
            # 查找JSON对象
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                parsed = json.loads(json_str)
                
                # 提取坐标信息
                if "x" in parsed and "y" in parsed:
                    result["coordinates"] = {
                        "x": int(parsed["x"]),
                        "y": int(parsed["y"])
                    }
                    result["found"] = parsed.get("found", True)
                    result["confidence"] = parsed.get("confidence", 0.8)
                
                # 提取其他字段
                if "description" in parsed:
                    result["description"] = parsed["description"]
                if "reason" in parsed:
                    result["reason"] = parsed["reason"]
        except (json.JSONDecodeError, ValueError):
            # 如果不是JSON，尝试从文本中提取坐标
            coord_match = re.search(r'[xX]:\s*(\d+)[,\s]+[yY]:\s*(\d+)', response_text)
            if coord_match:
                result["coordinates"] = {
                    "x": int(coord_match.group(1)),
                    "y": int(coord_match.group(2))
                }
                result["found"] = True
        
        # 处理Retina缩放（如果坐标看起来是像素坐标）
        if result["coordinates"]:
            x, y = result["coordinates"]["x"], result["coordinates"]["y"]
            # 如果坐标很大（>2000），可能是Retina像素坐标，需要缩放
            if x > 2000 or y > 2000:
                logger.warning(f"⚠️ 检测到可能的Retina像素坐标 ({x}, {y})，自动缩放为系统坐标")
                result["coordinates"]["x"] = x // 2
                result["coordinates"]["y"] = y // 2
                result["retina_scaled"] = True
        
        return result