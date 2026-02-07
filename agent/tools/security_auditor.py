"""
AST 安全审计器 - 代码执行安全加固

功能：
- 使用 AST 解析代码树，检测危险操作
- 封禁系统敏感库（os, subprocess, shutil）
- 检测混淆手段（__subclasses__, __builtins__, getattr）
"""

import ast
import logging
from typing import List, Tuple, Set
from pathlib import Path

logger = logging.getLogger(__name__)


class ASTSecurityAuditor:
    """
    AST 安全审计器
    
    使用 Python AST 模块解析代码树，检测危险操作。
    比正则表达式更可靠，能检测混淆手段。
    """
    
    # 禁止导入的模块
    FORBIDDEN_MODULES: Set[str] = {
        'os', 'subprocess', 'shutil', 'sys', 'platform',
        'ctypes', 'multiprocessing', 'threading',
        '__builtin__', '__builtins__', 'builtins',
        'importlib', 'imp', 'pkgutil'
    }
    
    # 禁止访问的属性（危险的内省操作）
    FORBIDDEN_ATTRIBUTES: Set[str] = {
        '__subclasses__', '__class__', '__bases__', '__mro__',
        '__builtins__', '__builtin__', '__dict__', '__globals__',
        '__code__', '__func__', '__self__', '__module__',
        'getattr', 'setattr', 'delattr', 'hasattr',
        '__import__', 'eval', 'exec', 'compile', 'execfile'
    }
    
    # 禁止的函数调用
    # 注意：open() 不在禁止列表中，而是通过 _check_file_operations 检查路径权限
    FORBIDDEN_FUNCTIONS: Set[str] = {
        'eval', 'exec', 'compile', '__import__',
        'file', 'input', 'raw_input'
    }
    
    def __init__(self, sandbox_path: Path):
        """
        初始化安全审计器
        
        Args:
            sandbox_path: 沙盒目录路径，用于路径验证
        """
        self.sandbox_path = sandbox_path.resolve()
    
    def audit(self, code: str) -> Tuple[bool, str]:
        """
        审计代码安全性
        
        Args:
            code: Python 代码字符串
            
        Returns:
            (is_safe, reason) - 是否安全，如果不安全则返回原因
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # 语法错误不是安全问题，交给语法检查器处理
            return True, ""
        
        violations: List[str] = []
        
        # 遍历 AST 节点
        for node in ast.walk(tree):
            # 1. 检查禁止的导入
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                violations.extend(self._check_import(node))
            
            # 2. 检查禁止的属性访问
            if isinstance(node, ast.Attribute):
                violations.extend(self._check_attribute(node))
            
            # 3. 检查禁止的函数调用
            if isinstance(node, ast.Call):
                violations.extend(self._check_call(node))
            
            # 4. 检查文件操作（open 调用）
            if isinstance(node, ast.Call):
                violations.extend(self._check_file_operations(node))
        
        if violations:
            reason = "[SECURITY_SHIELD] 检测到危险操作:\n" + "\n".join(f"  - {v}" for v in violations)
            logger.error(reason)
            return False, reason
        
        return True, ""
    
    def _check_import(self, node: ast.Import | ast.ImportFrom) -> List[str]:
        """检查导入语句"""
        violations = []
        
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split('.')[0]  # 只检查顶级模块
                if module_name in self.FORBIDDEN_MODULES:
                    violations.append(f"禁止导入模块: {module_name}")
        
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_name = node.module.split('.')[0]
                if module_name in self.FORBIDDEN_MODULES:
                    violations.append(f"禁止从模块导入: {module_name}")
        
        return violations
    
    def _check_attribute(self, node: ast.Attribute) -> List[str]:
        """检查属性访问"""
        violations = []
        
        attr_name = node.attr
        if attr_name in self.FORBIDDEN_ATTRIBUTES:
            violations.append(f"禁止访问属性: {attr_name}")
        
        # === 加强：检查通过 getattr 等动态访问 ===
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                if node.value.func.id in ('getattr', 'hasattr', 'setattr', 'delattr'):
                    violations.append(f"禁止使用动态属性访问: {node.value.func.id}")
        
        # === 加强：检查 __builtins__ 或 builtins 的属性访问 ===
        # 例如：__builtins__.eval 或 builtins.exec
        if isinstance(node.value, ast.Name):
            if node.value.id in ('__builtins__', '__builtin__', 'builtins'):
                if attr_name in ('eval', 'exec', 'compile', '__import__'):
                    violations.append(f"禁止通过 {node.value.id} 访问危险函数: {attr_name}")
        
        return violations
    
    def _check_call(self, node: ast.Call) -> List[str]:
        """检查函数调用"""
        violations = []
        
        # 检查直接调用禁止的函数
        if isinstance(node.func, ast.Name):
            if node.func.id in self.FORBIDDEN_FUNCTIONS:
                violations.append(f"禁止调用函数: {node.func.id}")
        
        # === 加强：检查 getattr/setattr/delattr 调用 ===
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in ('getattr', 'setattr', 'delattr', 'hasattr'):
                # 检查第二个参数（属性名）是否是字符串常量
                if len(node.args) >= 2:
                    second_arg = node.args[1]
                    if isinstance(second_arg, ast.Constant) and isinstance(second_arg.value, str):
                        attr_name = second_arg.value
                        if attr_name in self.FORBIDDEN_ATTRIBUTES:
                            violations.append(f"禁止通过 {func_name} 访问危险属性: {attr_name}")
                    # 即使不是常量，也记录警告（可能是动态构造的）
                    elif isinstance(second_arg, ast.Str):  # Python < 3.8 兼容
                        attr_name = second_arg.s
                        if attr_name in self.FORBIDDEN_ATTRIBUTES:
                            violations.append(f"禁止通过 {func_name} 访问危险属性: {attr_name}")
        
        # === 加强：检查动态代码执行变体 ===
        # 检查 getattr(__builtins__, 'eval') 或 getattr(__builtins__, 'exec')
        if isinstance(node.func, ast.Call):
            if isinstance(node.func.func, ast.Name):
                if node.func.func.id == 'getattr':
                    # 检查第一个参数是否是 __builtins__ 或 __builtin__
                    if len(node.func.args) >= 1:
                        first_arg = node.func.args[0]
                        if isinstance(first_arg, ast.Name):
                            if first_arg.id in ('__builtins__', '__builtin__', 'builtins'):
                                # 检查第二个参数（属性名）
                                if len(node.func.args) >= 2:
                                    second_arg = node.func.args[1]
                                    if isinstance(second_arg, ast.Constant) and isinstance(second_arg.value, str):
                                        attr_name = second_arg.value
                                        if attr_name in ('eval', 'exec', 'compile', '__import__'):
                                            violations.append(f"禁止通过 getattr 动态获取危险函数: {attr_name}")
                                    elif isinstance(second_arg, ast.Str):  # Python < 3.8 兼容
                                        attr_name = second_arg.s
                                        if attr_name in ('eval', 'exec', 'compile', '__import__'):
                                            violations.append(f"禁止通过 getattr 动态获取危险函数: {attr_name}")
                
                # 检查其他动态调用方式
                if node.func.func.id in ('getattr', '__import__'):
                    violations.append(f"禁止动态调用函数: {node.func.func.id}")
        
        # === 加强：检查 exec/eval 的变体调用 ===
        # 检查 exec(...) 或 eval(...) 的调用（open 不在禁止列表中，由文件操作检查处理）
        if isinstance(node.func, ast.Name):
            if node.func.id in ('exec', 'eval', 'compile'):
                violations.append(f"禁止调用代码执行函数: {node.func.id}")
        
        # === 加强：检查通过属性访问调用 eval/exec ===
        # 例如：__builtins__.eval(...) 或 builtins.exec(...)
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id in ('__builtins__', '__builtin__', 'builtins'):
                    if node.func.attr in ('eval', 'exec', 'compile', '__import__'):
                        violations.append(f"禁止通过 {node.func.value.id} 调用危险函数: {node.func.attr}")
        
        return violations
    
    def _check_file_operations(self, node: ast.Call) -> List[str]:
        """检查文件操作（限制在沙盒内和特定安全目录）"""
        violations = []
        
        # 禁止访问的敏感目录（即使用户主目录下）
        FORBIDDEN_HOME_SUBDIRS = [
            '.ssh', 'Library', '.config', '.local', '.cache',
            '.gnupg', '.aws', '.kube', '.docker', '.vagrant'
        ]
        
        # 允许访问的安全子目录（用户主目录下）
        ALLOWED_HOME_SUBDIRS = [
            'Desktop', 'Downloads', 'Documents', 'Pictures', 'Movies', 'Music',
            'Documents/DeskJarvis',  # 特定工作目录
        ]
        
        # 检查 open() 调用
        if isinstance(node.func, ast.Name) and node.func.id == 'open':
            # 检查文件路径参数
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant):
                    file_path = first_arg.value
                    if isinstance(file_path, str):
                        # 检查是否在沙盒外
                        try:
                            # 展开 ~ 和 ~user 路径
                            if file_path.startswith('~'):
                                import os
                                file_path = os.path.expanduser(file_path)
                            
                            abs_path = Path(file_path).resolve()
                            # 允许相对路径（会在当前工作目录执行，通常是沙盒目录）
                            if abs_path.is_absolute():
                                # 1. 优先检查是否在沙盒内（完全允许）
                                try:
                                    abs_path.relative_to(self.sandbox_path)
                                    # 在沙盒内，允许
                                    return violations
                                except ValueError:
                                    pass
                                
                                # 2. 检查是否在用户主目录下
                                home = Path.home()
                                try:
                                    rel_path = abs_path.relative_to(home)
                                    # 在用户主目录下，需要进一步检查
                                    
                                    # 2.1 检查是否是禁止的敏感子目录
                                    first_part = rel_path.parts[0] if rel_path.parts else ""
                                    if first_part in FORBIDDEN_HOME_SUBDIRS:
                                        violations.append(f"[SECURITY_SHIELD] 禁止访问敏感目录: ~/{first_part}")
                                        return violations
                                    
                                    # 2.2 检查是否在允许的安全子目录下
                                    if first_part in ALLOWED_HOME_SUBDIRS:
                                        # 在允许的目录下，允许访问
                                        return violations
                                    
                                    # 2.3 如果不在允许列表中，检查是否是 Documents/DeskJarvis 这样的嵌套路径
                                    if len(rel_path.parts) >= 2:
                                        if rel_path.parts[0] == 'Documents' and rel_path.parts[1] == 'DeskJarvis':
                                            # 允许 Documents/DeskJarvis 目录
                                            return violations
                                    
                                    # 2.4 其他用户主目录下的路径，默认拒绝（收紧权限）
                                    violations.append(f"[SECURITY_SHIELD] 路径不在允许的安全目录内: ~/{first_part} (允许的目录: {', '.join(ALLOWED_HOME_SUBDIRS)})")
                                    return violations
                                    
                                except ValueError:
                                    # 不在用户主目录下，拒绝
                                    violations.append(f"[SECURITY_SHIELD] 禁止访问沙盒外路径: {file_path}")
                                    return violations
                        except Exception:
                            # 路径解析失败，可能是变量，允许但记录警告
                            logger.warning(f"[SECURITY_SHIELD] 无法静态分析文件路径: {first_arg}")
                elif isinstance(first_arg, ast.Str):  # Python < 3.8 兼容
                    file_path = first_arg.s
                    if isinstance(file_path, str):
                        # 同样的检查逻辑
                        try:
                            # 展开 ~ 和 ~user 路径
                            if file_path.startswith('~'):
                                import os
                                file_path = os.path.expanduser(file_path)
                            
                            abs_path = Path(file_path).resolve()
                            if abs_path.is_absolute():
                                try:
                                    abs_path.relative_to(self.sandbox_path)
                                    return violations
                                except ValueError:
                                    pass
                                
                                home = Path.home()
                                try:
                                    rel_path = abs_path.relative_to(home)
                                    first_part = rel_path.parts[0] if rel_path.parts else ""
                                    if first_part in FORBIDDEN_HOME_SUBDIRS:
                                        violations.append(f"[SECURITY_SHIELD] 禁止访问敏感目录: ~/{first_part}")
                                        return violations
                                    if first_part not in ALLOWED_HOME_SUBDIRS and not (len(rel_path.parts) >= 2 and rel_path.parts[0] == 'Documents' and rel_path.parts[1] == 'DeskJarvis'):
                                        violations.append(f"[SECURITY_SHIELD] 路径不在允许的安全目录内: ~/{first_part}")
                                        return violations
                                except ValueError:
                                    violations.append(f"[SECURITY_SHIELD] 禁止访问沙盒外路径: {file_path}")
                                    return violations
                        except Exception:
                            logger.warning(f"[SECURITY_SHIELD] 无法静态分析文件路径: {first_arg}")
        
        return violations
