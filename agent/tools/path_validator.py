"""
路径验证工具 - 统一路径安全检查

功能：
- 统一所有 Executor 的路径验证逻辑
- 确保所有文件操作限制在安全范围内
"""

import logging
from pathlib import Path
from agent.tools.exceptions import FileManagerError

logger = logging.getLogger(__name__)


def validate_path(file_path: Path, sandbox_path: Path, allow_home: bool = True) -> Path:
    """
    验证文件路径是否安全（统一路径验证函数）
    
    安全策略：
    1. 优先检查是否在用户主目录下（如果 allow_home=True）
    2. 检查是否在沙盒目录下（允许）
    3. 检查是否是禁止的系统关键路径
    
    Args:
        file_path: 文件路径（可以是相对路径或绝对路径）
        sandbox_path: 沙盒目录路径
        allow_home: 是否允许访问用户主目录
        
    Returns:
        解析后的绝对路径
        
    Raises:
        FileManagerError: 如果路径不安全
    """
    # 转换为绝对路径
    try:
        abs_path = file_path.resolve()
    except (OSError, RuntimeError) as e:
        raise FileManagerError(f"路径解析失败: {e}")
    
    home = Path.home()
    sandbox_abs = sandbox_path.resolve()
    
    # 优先检查：是否在用户主目录下（如果允许）
    if allow_home:
        try:
            abs_path.relative_to(home)
            logger.debug(f"[SECURITY_SHIELD] 路径在用户主目录下，允许: {abs_path}")
            return abs_path
        except ValueError:
            pass
    
    # 检查是否在沙盒目录下（允许）
    try:
        abs_path.relative_to(sandbox_abs)
        logger.debug(f"[SECURITY_SHIELD] 路径在沙盒目录下，允许: {abs_path}")
        return abs_path
    except ValueError:
        pass
    
    # 禁止的系统关键路径
    forbidden_paths = [
        Path("/System"),
        Path("/Library"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/etc"),
        Path("/var"),
        Path("/private"),
    ]
    
    # 检查是否是禁止的系统关键路径
    for forbidden in forbidden_paths:
        try:
            abs_path.relative_to(forbidden)
            raise FileManagerError(f"[SECURITY_SHIELD] 禁止操作系统关键路径: {abs_path}")
        except ValueError:
            pass
    
    # 检查根路径（特殊处理）
    if abs_path == Path("/"):
        raise FileManagerError(f"[SECURITY_SHIELD] 禁止操作系统根路径: {abs_path}")
    
    # 如果路径不在允许范围内，拒绝
    raise FileManagerError(
        f"[SECURITY_SHIELD] 路径不在允许范围内（必须在用户主目录或沙盒目录内）: {abs_path}"
    )
