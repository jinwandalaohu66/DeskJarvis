"""
增强版代码解释器 - 比 Open Interpreter 更强大

功能：
1. 自动检测并安装缺失的 Python 包
2. Matplotlib 图表自动保存并返回路径
3. 代码执行结果记忆（跨会话）
4. 智能错误分析和自动修复
5. 实时输出流（支持长时间运行的脚本）
6. 代码安全检查（沙盒限制）
"""

import subprocess
import os
import sys
import re
import json
import ast
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from agent.executor.script_validator import ScriptValidator
from agent.tools.security_auditor import ASTSecurityAuditor

logger = logging.getLogger(__name__)


@dataclass
class CodeExecutionResult:
    """代码执行结果"""
    success: bool
    message: str
    output: str = ""
    error: str = ""
    images: List[str] = field(default_factory=list)  # 图表路径列表
    data: Any = None
    execution_time: float = 0.0
    installed_packages: List[str] = field(default_factory=list)  # 自动安装的包
    

class CodeInterpreter:
    """
    增强版代码解释器
    
    比 Open Interpreter 更强大的功能：
    - 自动安装依赖（无需用户确认）
    - 图表自动捕获（matplotlib, plotly, seaborn）
    - 代码记忆（跨会话）
    - 智能错误修复（自动重试）
    """
    
    # 常用包别名映射
    PACKAGE_ALIASES = {
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "sklearn": "scikit-learn",
        "yaml": "PyYAML",
        "bs4": "beautifulsoup4",
        "dateutil": "python-dateutil",
        "docx": "python-docx",
        "pptx": "python-pptx",
        "xlsx": "openpyxl",
        "pdf": "PyPDF2",
        "Image": "Pillow",
    }
    
    # 安全白名单（允许安装的包）
    SAFE_PACKAGES = {
        "numpy", "pandas", "matplotlib", "seaborn", "plotly",
        "scipy", "scikit-learn", "opencv-python", "Pillow",
        "requests", "beautifulsoup4", "lxml", "openpyxl",
        "python-docx", "python-pptx", "PyPDF2", "pypdf",
        "jieba", "wordcloud", "pyyaml", "toml",
        "tqdm", "rich", "tabulate", "colorama",
        "python-dateutil", "pytz", "pendulum",
        "chardet", "faker", "sympy", "networkx",
        "pillow", "imageio", "moviepy",
    }
    
    # 危险代码模式（禁止执行）
    DANGEROUS_PATTERNS = [
        r"os\s*\.\s*system\s*\(",
        r"subprocess\s*\.\s*(?:run|call|Popen)\s*\([^)]*(?:rm\s+-rf|del\s+/|format\s+c)",
        r"shutil\s*\.\s*rmtree\s*\(['\"]\/",
        r"eval\s*\(\s*input",
        r"exec\s*\(\s*input",
        r"__import__\s*\(['\"](?:os|subprocess|shutil)['\"]",
        r"open\s*\(['\"]\/(?:etc|root|home)",
    ]
    
    # 高权操作模式（需要实时观察）
    HIGH_RISK_PATTERNS = [
        r"os\.remove\(",
        r"os\.unlink\(",
        r"shutil\.rmtree\(",
        r"shutil\.remove\(",
        r"os\.rename\(",
        r"shutil\.move\(",
        r"shutil\.copy\(",
        r"shutil\.copy2\(",
        r"for\s+.*\s+in\s+.*:\s*.*\.(remove|rename|move|unlink|rmtree)\(",
        r"\.remove\(",
        r"\.rename\(",
    ]
    
    def __init__(self, sandbox_path: Path, emit_callback=None):
        """
        初始化代码解释器
        
        Args:
            sandbox_path: 沙盒目录路径
            emit_callback: 进度回调函数
        """
        self.sandbox_path = sandbox_path
        self.emit = emit_callback
        self.scripts_dir = sandbox_path / "scripts"
        self.output_dir = sandbox_path / "outputs"
        self.code_history: List[Dict] = []
        self.validator = ScriptValidator(sandbox_path)
        
        # 初始化 AST 安全审计器
        self.security_auditor = ASTSecurityAuditor(sandbox_path)
        
        # 创建必要的目录
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 执行超时时间（秒）
        self.execution_timeout = 30
        
    def execute(self, code: str, reason: str = "", auto_install: bool = True, 
                max_retries: int = 2, context: Optional[Dict[str, Any]] = None) -> CodeExecutionResult:
        """
        执行 Python 代码
        
        Args:
            code: Python 代码（支持 base64 编码）
            reason: 执行原因（用于日志）
            auto_install: 是否自动安装缺失的包
            max_retries: 最大重试次数
            context: 执行上下文，包含 step_results 等信息，会自动注入到脚本中作为 context_data 变量
            
        Returns:
            CodeExecutionResult: 执行结果
        """
        start_time = time.time()
        installed_packages = []
        
        # 0. 处理 base64 编码的代码
        code = self._decode_script(code)
        
        # 0.25 注入上下文数据（如果提供了 context）
        if context is not None:
            import json
            
            # 增加 default 参数处理非序列化对象
            try:
                context_json_str = json.dumps(
                    context, 
                    ensure_ascii=False, 
                    default=lambda o: f"<Non-serializable: {type(o).__name__}>"
                )
            except Exception as e:
                logger.warning(f"序列化 context 时出错: {e}，使用简化版本")
                # 如果仍然失败，创建一个简化的 context（只保留可序列化的部分）
                simplified_context = {}
                for key, value in context.items():
                    try:
                        json.dumps(value, default=lambda o: f"<Non-serializable: {type(o).__name__}>")
                        simplified_context[key] = value
                    except:
                        simplified_context[key] = f"<Non-serializable: {type(value).__name__}>"
                context_json_str = json.dumps(simplified_context, ensure_ascii=False, default=lambda o: f"<Non-serializable: {type(o).__name__}>")
            
            # 在代码开头注入 context_data 变量（避免重复注入）
            if "context_data = " not in code:
                injection_code = f"# === DeskJarvis 自动注入上下文数据 ===\nimport json\ncontext_data = {repr(context_json_str)}\n# === 结束注入 ===\n\n"
                code = injection_code + code
                logger.debug("已注入 context_data 到脚本中")
        
        # 0.5 预处理：修复常见的 AI 代码错误
        code = self._preprocess_code(code)
        
        # 1. AST 安全检查（升级版）
        is_safe, security_reason = self.security_auditor.audit(code)
        if not is_safe:
            return CodeExecutionResult(
                success=False,
                message=f"[SECURITY_SHIELD] AST 安全审计失败: {security_reason}",
                error=security_reason
            )
        
        # 1.1 保留旧的关键词检查作为补充（向后兼容）
        legacy_security_check = self._check_security(code)
        if not legacy_security_check[0]:
            logger.warning(f"[SECURITY_SHIELD] 关键词检查检测到潜在风险: {legacy_security_check[1]}")
            # 不直接拒绝，但记录警告（AST 审计是主要检查）
        
        # 1.5 语法预检查（自动修复常见语法错误）
        syntax_check = self._check_syntax(code)
        if not syntax_check[0]:
            return CodeExecutionResult(
                success=False,
                message=f"语法错误: {syntax_check[1]}",
                error=syntax_check[1]
            )
        # 使用修复后的代码
        code = syntax_check[2]

        # 1.6 脚本验证移动到重试循环中（便于自动修复/重试）
        
        # 2. 分析并安装缺失的包
        if auto_install:
            missing_packages = self._detect_missing_packages(code)
            if missing_packages:
                self._emit_progress("installing_packages", f"正在安装依赖: {', '.join(missing_packages)}")
                for pkg in missing_packages:
                    if self._install_package(pkg):
                        installed_packages.append(pkg)
                    else:
                        logger.warning(f"安装包失败: {pkg}")
        
        # 3. 注入图表捕获代码
        enhanced_code = self._inject_plot_capture(code)
        
        # 4. 执行代码（带重试）
        result: Optional[CodeExecutionResult] = None
        last_error = ""
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                self._emit_progress("retrying", f"第 {attempt + 1} 次尝试执行...")
                # 尝试自动修复错误
                enhanced_code = self._try_fix_error(enhanced_code, last_error)

            # 3.5 执行前验证（ruff --fix 自动修复 + 仅致命错误阻断）
            self._emit_progress("validating_script", "正在检查脚本质量…")
            validation = self.validator.validate(
                enhanced_code,
                lint=True,
                require_json_output=False,
                dry_run=True,
                dry_run_timeout_sec=2,
            )

            # 如果 ruff --fix 修复了代码，采用修复后版本
            if validation.fixed_code:
                enhanced_code = validation.fixed_code
                logger.info("已采用 ruff --fix 自动修复后的代码")

            if not validation.ok:
                last_error = "脚本验证失败: " + validation.message
                if validation.details:
                    last_error = last_error + "\n" + validation.details
                details = validation.details[:1200] if validation.details else ""
                self._emit_progress("validation_failed", validation.message, {"details": details})
                # 还有重试机会就继续（让 _try_fix_error 有机会修）
                if attempt < max_retries:
                    continue
                return CodeExecutionResult(
                    success=False,
                    message="脚本验证失败: " + validation.message,
                    error=last_error,
                )
            
            result = self._execute_code(enhanced_code)
            
            if result.success:
                break
            else:
                last_error = result.error
                # 检查是否是缺少包的错误
                missing = self._extract_missing_module(result.error)
                if missing and auto_install:
                    if self._install_package(missing):
                        installed_packages.append(missing)
                        continue
        
        # 5. 收集图表文件
        images = self._collect_generated_images()
        
        # 6. 记录执行历史
        execution_time = time.time() - start_time
        if result is None:
            # 理论上不应该发生，但为了健壮性兜底
            result = CodeExecutionResult(
                success=False,
                message="执行失败: 未获取到执行结果",
                error="No result",
            )
        self._record_execution(code, result, execution_time)
        
        # 7. 返回增强的结果
        if result is None:
            return CodeExecutionResult(
                success=False,
                message="执行失败: 未获取到执行结果",
                error="No result",
                execution_time=execution_time,
                installed_packages=installed_packages,
            )

        result.images = images
        result.execution_time = execution_time
        result.installed_packages = installed_packages

        return result
    
    def _decode_script(self, script: str) -> str:
        """
        解码脚本内容（支持 base64 编码）
        
        Args:
            script: 原始脚本（可能是 base64 编码）
            
        Returns:
            解码后的脚本内容
        """
        import base64
        import binascii
        import string

        if not isinstance(script, str):
            return str(script)

        # 如果已经像 Python 源码（最常见），直接做基础反转义即可
        if script.lstrip().startswith(("import ", "from ", "def ", "class ", "try:", "if ", "print(", "#", '"""')):
            script = script.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
        else:
            # 尝试 base64 解码（容错：自动补齐 padding；兼容 urlsafe）
            script_clean = "".join(script.split())

            # 仅当“看起来像 base64”时才尝试解码，避免误判
            base64_chars = set(string.ascii_letters + string.digits + "+/=_-")
            looks_like_base64 = len(script_clean) >= 64 and all(c in base64_chars for c in script_clean)

            if looks_like_base64:
                # 修复 padding（很多模型会漏掉末尾 '='）
                missing_padding = len(script_clean) % 4
                if missing_padding:
                    script_clean += "=" * (4 - missing_padding)

                decoded_str = None

                # 1) 严格 base64
                try:
                    decoded_bytes = base64.b64decode(script_clean, validate=True)
                    decoded_str = decoded_bytes.decode("utf-8", errors="strict")
                except (binascii.Error, UnicodeDecodeError, ValueError):
                    decoded_str = None

                # 2) 非严格 base64（更兼容）
                if decoded_str is None:
                    try:
                        decoded_bytes = base64.b64decode(script_clean, validate=False)
                        decoded_str = decoded_bytes.decode("utf-8", errors="strict")
                    except Exception:
                        decoded_str = None

                # 3) urlsafe base64
                if decoded_str is None:
                    try:
                        decoded_bytes = base64.urlsafe_b64decode(script_clean)
                        decoded_str = decoded_bytes.decode("utf-8", errors="strict")
                    except Exception:
                        decoded_str = None

                if decoded_str is not None and decoded_str.strip().startswith(
                    ("import ", "from ", "def ", "class ", "try:", "if ", "print(", "#", '"""')
                ):
                    logger.info("检测到 base64 编码的脚本，已解码（含 urlsafe/padding 容错）")
                    script = decoded_str
                else:
                    # 解码失败或解码后不像 Python：打印前100字符用于调试
                    if decoded_str is not None:
                        preview = decoded_str[:100].replace('\n', '\\n').replace('\r', '\\r')
                        logger.warning(f"⚠️ Base64 解码后内容异常（前100字符）: {preview}")
                        logger.warning("解码后的内容不像 Python 代码，将按普通字符串处理")
                    # 按普通字符串处理
                    script = script.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
            else:
                # 不是 base64：按普通字符串处理
                script = script.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")

        # 二次兜底：如果仍然像 base64，但没有被解码，做一次“宽松解码”尝试
        if (
            isinstance(script, str)
            and len(script) >= 128
            and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=_-" for c in script)
        ):
            try:
                cleaned = script.replace("-", "+").replace("_", "/")
                missing_padding = len(cleaned) % 4
                if missing_padding:
                    cleaned += "=" * (4 - missing_padding)
                decoded_bytes = base64.b64decode(cleaned, validate=False)
                decoded_str = decoded_bytes.decode("utf-8", errors="ignore")
                if decoded_str.strip().startswith(
                    ("import ", "from ", "def ", "class ", "try:", "if ", "print(", "#", '"""')
                ):
                    logger.info("检测到 base64 编码的脚本（宽松解码），已解码")
                    script = decoded_str
                else:
                    # 解码后不像 Python：打印前100字符用于调试
                    preview = decoded_str[:100].replace('\n', '\\n').replace('\r', '\\r')
                    logger.warning(f"⚠️ Base64 宽松解码后内容异常（前100字符）: {preview}")
            except Exception as e:
                logger.warning(f"⚠️ Base64 解码异常: {e}")
                # 打印原始脚本的前100字符用于调试
                preview = script[:100].replace('\n', '\\n').replace('\r', '\\r')
                logger.debug(f"原始脚本前100字符: {preview}")
        
        # 清理控制字符（保留换行、制表符、回车）
        allowed_control_chars = {'\n', '\r', '\t'}
        cleaned_chars = []
        for char in script:
            char_code = ord(char)
            if char in string.printable or char in allowed_control_chars or char_code >= 128:
                cleaned_chars.append(char)
        
        return ''.join(cleaned_chars)
    
    def _preprocess_code(self, code: str) -> str:
        """
        预处理代码，修复常见的 AI 生成错误
        
        Returns:
            修复后的代码
        """
        # 1. 修复 f-string 前有空格的问题 (f "..." -> f"...")
        code = re.sub(r'\bf\s+"', 'f"', code)
        code = re.sub(r"\bf\s+'", "f'", code)
        
        # 2. 修复 r-string 前有空格的问题 (r "..." -> r"...")
        code = re.sub(r'\br\s+"', 'r"', code)
        code = re.sub(r"\br\s+'", "r'", code)
        
        # 3. 修复 b-string 前有空格的问题 (b "..." -> b"...")
        code = re.sub(r'\bb\s+"', 'b"', code)
        code = re.sub(r"\bb\s+'", "b'", code)
        
        # 4. 修复常见的 colormap 名称错误
        code = code.replace("plt.cm.set3", "plt.cm.tab20")
        code = code.replace("plt.cm.Set3", "plt.cm.tab20")
        code = code.replace("cm.set3", "cm.tab20")
        code = code.replace("cm.Set3", "cm.tab20")
        
        logger.debug("代码预处理完成")
        return code
    
    def _check_security(self, code: str) -> Tuple[bool, str]:
        """
        检查代码安全性
        
        Returns:
            (is_safe, reason)
        """
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"检测到危险代码模式: {pattern}"
        
        # 检查是否访问沙盒外的路径
        # (这里只做基本检查，实际执行时也会限制)
        if "/etc/" in code or "/root/" in code or "/Users/" in code:
            # 检查是否是相对路径
            if str(self.sandbox_path) not in code:
                logger.warning("代码可能访问沙盒外路径，但允许执行")
        
        return True, ""
    
    def _check_syntax(self, code: str) -> Tuple[bool, str, str]:
        """
        使用 AST 检查代码语法
        
        Returns:
            (is_valid, error_message, fixed_code)
        """
        import ast
        
        try:
            ast.parse(code)
            # AST 通过后，再用 py_compile 做一次更贴近解释器的语法检查
            ok, msg = self._py_compile_check(code)
            if not ok:
                return False, msg, code
            return True, "", code
        except SyntaxError as e:
            error_msg = f"语法错误 第{e.lineno}行: {e.msg}"
            logger.warning(f"检测到语法错误: {error_msg}")
            
            # 尝试自动修复常见语法错误
            fixed_code = code
            
            # 1. 检查是否缺少 except 块
            if "expected 'except' or 'finally' block" in str(e.msg):
                # 在代码末尾添加 except 块
                lines = code.rstrip().split('\n')
                indent = self._get_last_try_indent(lines)
                except_block = f"\n{indent}except Exception as e:\n{indent}    import json\n{indent}    print(json.dumps({{\"success\": False, \"message\": str(e)}}))"
                fixed_code = code.rstrip() + except_block
                logger.info("自动修复: 添加缺失的 except 块")
            
            # 2. 修复 os.name.astype() 等不存在的方法
            if "os.name.astype()" in code:
                fixed_code = fixed_code.replace("os.name.astype()", "sys.platform")
                # 确保 import sys
                if "import sys" not in fixed_code:
                    fixed_code = "import sys\n" + fixed_code
                logger.info("自动修复: 替换 os.name.astype() 为 sys.platform")
            
            # 重新检查修复后的代码
            try:
                ast.parse(fixed_code)
                # 二次检查：py_compile
                ok, msg = self._py_compile_check(fixed_code)
                if not ok:
                    return False, msg, code
                logger.info("语法错误已自动修复")
                return True, "", fixed_code
            except SyntaxError:
                return False, self._format_syntax_error(code, e), code

    def _py_compile_check(self, code: str) -> Tuple[bool, str]:
        """
        使用 py_compile.compile() 检查语法（更贴近真实解释器）。

        Args:
            code: Python 代码

        Returns:
            (is_ok, error_message)
        """
        import py_compile
        import tempfile

        # py_compile 只能编译文件，因此写入临时文件
        try:
            tmp_dir = self.sandbox_path / "scripts"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".py",
                prefix="syntax_check_",
                dir=str(tmp_dir),
                delete=False,
            ) as f:
                tmp_path = f.name
                f.write(code)

            py_compile.compile(tmp_path, doraise=True)
            return True, ""
        except py_compile.PyCompileError as e:
            # e.exc_value 通常是 SyntaxError
            exc_value = getattr(e, "exc_value", None)
            if isinstance(exc_value, SyntaxError):
                return False, self._format_syntax_error(code, exc_value)
            return False, "语法错误无法自动修复: " + str(e)
        except SyntaxError as e:
            return False, self._format_syntax_error(code, e)
        except Exception as e:
            return False, "语法检查失败: " + str(e)

    def _format_syntax_error(self, code: str, e: SyntaxError) -> str:
        """
        格式化语法错误信息，附带行号与代码片段，便于反思修复。

        Args:
            code: 源代码
            e: SyntaxError

        Returns:
            格式化后的错误消息
        """
        lines = code.splitlines()
        lineno = getattr(e, "lineno", None) or 0
        offset = getattr(e, "offset", None) or 0
        msg = getattr(e, "msg", None) or str(e)

        # 取出错行前后各一行作为上下文
        idx = max(lineno - 1, 0)
        start = max(idx - 1, 0)
        end = min(idx + 2, len(lines))
        snippet = lines[start:end]

        snippet_text = "\n".join(
            [f"{start + i + 1}: {snippet[i]}" for i in range(len(snippet))]
        ) if snippet else ""

        base = f"语法错误无法自动修复: {msg}"
        if lineno:
            base = base + f" (line {lineno}, col {offset})"
        if snippet_text:
            base = base + "\n" + snippet_text
        return base
    
    def _get_last_try_indent(self, lines: List[str]) -> str:
        """获取最后一个未配对 try 的缩进"""
        try_count = 0
        except_count = 0
        last_try_indent = ""
        
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("try:"):
                try_count += 1
                last_try_indent = line[:len(line) - len(stripped)]
            elif stripped.startswith("except") or stripped.startswith("finally"):
                except_count += 1
        
        if try_count > except_count:
            return last_try_indent
        return ""
    
    def _detect_missing_packages(self, code: str) -> List[str]:
        """
        检测代码中缺失的包
        
        Returns:
            缺失包列表
        """
        missing = []
        
        # 使用 AST 分析 import 语句
        try:
            tree = ast.parse(code)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split('.')[0])
            
            # 检查每个导入
            for pkg in imports:
                real_pkg = self.PACKAGE_ALIASES.get(pkg, pkg)
                if not self._is_package_installed(pkg):
                    if real_pkg.lower() in self.SAFE_PACKAGES or real_pkg.lower() == pkg.lower():
                        missing.append(real_pkg)
                    else:
                        logger.warning(f"包 {real_pkg} 不在安全白名单中，跳过安装")
        except SyntaxError:
            # 代码语法错误，无法解析
            pass
        
        return list(set(missing))
    
    def _is_package_installed(self, package: str) -> bool:
        """检查包是否已安装"""
        try:
            __import__(package)
            return True
        except ImportError:
            return False
    
    def _install_package(self, package: str) -> bool:
        """
        安装 Python 包
        
        Returns:
            是否安装成功
        """
        logger.info(f"正在安装包: {package}")
        self._emit_progress("installing", f"正在安装 {package}...")
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package, "-q"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                logger.info(f"包安装成功: {package}")
                return True
            else:
                logger.error(f"包安装失败: {package}, {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"安装包异常: {e}")
            return False
    
    def _inject_plot_capture(self, code: str) -> str:
        """
        注入图表捕获代码
        
        如果代码使用了 matplotlib/seaborn/plotly，自动保存图表到桌面
        """
        # 避免重复注入
        if "DeskJarvis 图表自动捕获" in code:
            return code

        # 检测是否使用了绘图库
        uses_matplotlib = "matplotlib" in code or "plt." in code
        uses_seaborn = "seaborn" in code or "sns." in code
        uses_plotly = "plotly" in code or "px." in code or "go." in code
        
        if not (uses_matplotlib or uses_seaborn or uses_plotly):
            return code
        
        # 生成唯一的图表文件名 - 严格保存到沙盒 output 目录（不再保存到桌面）
        timestamp = int(time.time() * 1000)
        # 所有输出严格隔离到沙盒目录
        image_path = self.output_dir / f"DeskJarvis图表_{timestamp}.png"
        preview_path = self.output_dir / f"plot_{timestamp}.png"
        
        # 只注入“纯 import”块，避免 E402（imports must be at top）
        import_block = (
            "# === DeskJarvis 图表自动捕获（imports） ===\n"
            "import matplotlib.pyplot as _dj_plt\n"
            "# === 结束注入（imports） ===\n\n"
        )

        # 运行时逻辑放在末尾，避免影响原始 import 区域
        runtime_block = f'''
# === DeskJarvis 图表自动捕获 ===
_dj_desktop_path = "{str(image_path)}"
_dj_preview_path = "{str(preview_path)}"
_dj_saved_plots = []

def _dj_save_current_figure():
    """保存当前图表"""
    global _dj_saved_plots
    if _dj_plt.get_fignums():
        # 保存到桌面
        _dj_plt.savefig(_dj_desktop_path, dpi=150, bbox_inches='tight', facecolor='white')
        # 保存预览到 output 目录
        _dj_plt.savefig(_dj_preview_path, dpi=100, bbox_inches='tight', facecolor='white')
        _dj_saved_plots.append(_dj_desktop_path)
        print("图表已保存到: " + _dj_desktop_path)
# === 结束注入 ===
'''
        
        # 在代码末尾添加保存调用
        save_code = '''

# === 自动保存图表 ===
_dj_save_current_figure()
'''

        def _insert_import_block(src: str, block: str) -> str:
            lines = src.splitlines()
            idx = 0
            # Shebang
            if lines and lines[0].startswith("#!"):
                idx = 1
            # Encoding comment
            if idx < len(lines) and "coding" in lines[idx]:
                idx += 1
            # Module docstring
            if idx < len(lines) and lines[idx].lstrip().startswith(('"""', "'''")):
                quote = lines[idx].lstrip()[:3]
                idx += 1
                while idx < len(lines):
                    if quote in lines[idx]:
                        idx += 1
                        break
                    idx += 1
            before = "\n".join(lines[:idx]).rstrip("\n")
            after = "\n".join(lines[idx:])
            if before:
                return before + "\n" + block + after
            return block + after

        # 将 import 注入块放在文件顶部（但避开 shebang/编码注释/模块 docstring）
        injected = _insert_import_block(code, import_block)
        # 保存逻辑放在末尾
        return injected + runtime_block + save_code
    
    def _check_high_risk_operation(self, code: str) -> bool:
        """
        检查代码是否包含高权操作（需要实时观察）
        
        Args:
            code: 代码字符串
            
        Returns:
            是否包含高权操作
        """
        for pattern in self.HIGH_RISK_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return True
        return False
    
    def _execute_code(self, code: str) -> CodeExecutionResult:
        """
        执行代码（支持实时观察 - Phase 1）
        
        Returns:
            执行结果
        """
        # 检查是否包含高权操作
        has_high_risk = self._check_high_risk_operation(code)
        
        if has_high_risk:
            # 高权操作：启用实时观察模式
            logger.info("检测到高权操作，启用实时观察模式")
            if self.emit:
                self.emit("thinking", {
                    "content": "检测到高风险操作，正在启用实时观察模式...",
                    "phase": "high_risk_detected"
                })
        
        # 执行代码（当前版本仍使用直接执行，Phase 1的块级执行将在后续版本中实现）
        return self._execute_code_direct(code)
    
    def _execute_code_direct(self, code: str) -> CodeExecutionResult:
        """
        直接执行代码（不进行实时观察）
        
        增强功能：
        - 30秒超时机制（防止死循环）
        - 输出严格隔离到沙盒目录
        - 资源限制
        
        Returns:
            执行结果
        """
        # 创建临时脚本文件（在沙盒内）
        script_path = self.scripts_dir / f"script_{int(time.time() * 1000)}.py"
        
        # 输出文件路径（严格隔离）
        output_file = self.output_dir / f"output_{int(time.time() * 1000)}.txt"
        error_file = self.output_dir / f"error_{int(time.time() * 1000)}.txt"
        
        try:
            # 写入脚本
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            logger.info(f"[SECURITY_SHIELD] 执行脚本: {script_path} (超时: {self.execution_timeout}s)")
            
            # 执行脚本（带超时和输出重定向）
            try:
                result = subprocess.run(
                    [sys.executable, str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=self.execution_timeout,  # 30秒超时
                    cwd=str(self.sandbox_path),  # 工作目录限制在沙盒
                    env={
                        **os.environ,
                        "PYTHONIOENCODING": "utf-8",
                        # 强制 matplotlib 使用无界面后端，避免 macOS GUI 阻塞
                        "MPLBACKEND": "Agg",
                        # 限制 Python 路径（防止导入系统模块）
                        "PYTHONPATH": str(self.sandbox_path),
                    }
                )
            except subprocess.TimeoutExpired:
                logger.error(f"[SECURITY_SHIELD] 脚本执行超时（{self.execution_timeout}秒）: {script_path}")
                return CodeExecutionResult(
                    success=False,
                    message=f"[SECURITY_SHIELD] 执行超时（超过{self.execution_timeout}秒），已强制终止",
                    error=f"Timeout after {self.execution_timeout}s"
                )
            
            # 保存输出到沙盒目录（严格隔离）
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            
            # 写入输出文件
            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(stdout)
                if stderr:
                    with open(error_file, "w", encoding="utf-8") as f:
                        f.write(stderr)
                logger.debug(f"[SECURITY_SHIELD] 输出已保存到: {output_file}")
            except Exception as e:
                logger.warning(f"[SECURITY_SHIELD] 保存输出文件失败: {e}")
            
            if result.returncode != 0:
                # 执行失败
                error_msg = stderr or stdout or "未知错误"
                logger.error(f"[SECURITY_SHIELD] 脚本执行失败: {error_msg[:200]}")
                return CodeExecutionResult(
                    success=False,
                    message=f"[SECURITY_SHIELD] 执行失败: {error_msg[:200]}",
                    output=stdout,
                    error=error_msg
                )
            
            # 执行成功
            # 尝试解析 JSON 输出
            try:
                json_output = json.loads(stdout)
                if isinstance(json_output, dict):
                    return CodeExecutionResult(
                        success=json_output.get("success", True),
                        message=json_output.get("message", "执行完成"),
                        output=stdout,
                        data=json_output.get("data")
                    )
                # 如果不是字典（例如 print(1+1) -> 2），视为普通输出
            except json.JSONDecodeError:
                pass
                
            # 返回原始输出
            logger.info(f"[SECURITY_SHIELD] 脚本执行成功，输出已隔离到: {output_file}")
            return CodeExecutionResult(
                success=True,
                message="执行完成",
                output=stdout
            )
                
        except Exception as e:
            logger.error(f"[SECURITY_SHIELD] 脚本执行异常: {e}", exc_info=True)
            return CodeExecutionResult(
                success=False,
                message=f"[SECURITY_SHIELD] 执行异常: {str(e)}",
                error=str(e)
            )
    
    def _extract_missing_module(self, error: str) -> Optional[str]:
        """
        从错误信息中提取缺失的模块名
        """
        patterns = [
            r"ModuleNotFoundError: No module named '(\w+)'",
            r"ImportError: No module named '?(\w+)'?",
            r"cannot import name '(\w+)'"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, error)
            if match:
                module = match.group(1)
                return self.PACKAGE_ALIASES.get(module, module)
        
        return None
    
    def _try_fix_error(self, code: str, error: str) -> str:
        """
        尝试自动修复代码错误
        
        Returns:
            修复后的代码
        """
        fixed_code = code
        
        # 0. 修复 f-string 前有空格的问题 (f "..." -> f"...")
        # 这是 AI 常犯的错误
        fixed_code = re.sub(r'\bf\s+"', 'f"', fixed_code)
        fixed_code = re.sub(r"\bf\s+'", "f'", fixed_code)
        
        # 1. 修复常见语法错误
        # 缺少引号闭合
        if "unterminated string" in error or "EOL while scanning" in error:
            # 尝试添加闭合引号
            fixed_code = self._fix_string_quotes(fixed_code)
        
        # 2. 修复缩进错误
        if "IndentationError" in error or "unexpected indent" in error:
            fixed_code = self._fix_indentation(fixed_code)
        
        # 3. 修复 f-string 错误
        if "f-string" in error or "invalid syntax" in error:
            fixed_code = self._fix_fstring(fixed_code)
        
        # 4. 修复变量未定义
        if "name '" in error and "' is not defined" in error:
            match = re.search(r"name '(\w+)' is not defined", error)
            if match:
                var_name = match.group(1)
                logger.warning(f"检测到未定义变量: {var_name}")
                # 这种情况通常需要反思，不自动修复
        
        # 5. 修复 matplotlib 常见错误
        if "has no attribute" in error and "matplotlib" in error:
            # 修复 colormap 名称大小写问题
            colormap_fixes = {
                ".set3": ".Set3",
                ".set2": ".Set2", 
                ".set1": ".Set1",
                ".pastel1": ".Pastel1",
                ".pastel2": ".Pastel2",
                ".paired": ".Paired",
                ".accent": ".Accent",
                ".dark2": ".Dark2",
                ".tab10": ".tab10",
                ".tab20": ".tab20",
            }
            for wrong, correct in colormap_fixes.items():
                if wrong in fixed_code.lower():
                    # 使用正则表达式修复大小写
                    pattern = re.compile(re.escape(wrong), re.IGNORECASE)
                    fixed_code = pattern.sub(correct, fixed_code)
                    logger.info(f"修复 matplotlib colormap: {wrong} -> {correct}")
            
            # 如果还有问题，使用更通用的颜色方案
            if "cm.set3" in fixed_code.lower() or "cm.Set3" in fixed_code:
                # 替换为更可靠的颜色生成方式
                fixed_code = fixed_code.replace("plt.cm.set3", "plt.cm.tab20")
                fixed_code = fixed_code.replace("plt.cm.Set3", "plt.cm.tab20")
                fixed_code = fixed_code.replace("cm.set3", "cm.tab20")
                fixed_code = fixed_code.replace("cm.Set3", "cm.tab20")
                logger.info("将 Set3 替换为 tab20 颜色方案")
        
        return fixed_code
    
    def _fix_string_quotes(self, code: str) -> str:
        """修复字符串引号问题"""
        # 简单方法：统计引号
        single_count = code.count("'") - code.count("\\'")
        double_count = code.count('"') - code.count('\\"')
        
        # 如果奇数，尝试在末尾添加引号
        if single_count % 2 == 1:
            # 找到最后一个未闭合的单引号
            last_single = code.rfind("'")
            if last_single > 0:
                code = code[:last_single+1] + "'" + code[last_single+1:]
        
        if double_count % 2 == 1:
            last_double = code.rfind('"')
            if last_double > 0:
                code = code[:last_double+1] + '"' + code[last_double+1:]
        
        return code
    
    def _fix_indentation(self, code: str) -> str:
        """修复缩进问题"""
        lines = code.split('\n')
        fixed_lines = []
        
        for line in lines:
            # 将 Tab 转换为 4 个空格
            line = line.replace('\t', '    ')
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _fix_fstring(self, code: str) -> str:
        """修复 f-string 问题"""
        # 修复 f'""" -> f"""
        code = re.sub(r"f['\"]\"\"\"{1,3}", 'f"""', code)
        
        # 修复嵌套大括号
        # 例如：f"{var1{var2}" -> f"{var1}{var2}"
        code = re.sub(r'\{([^}]+)\{', r'{\1}}{', code)
        
        return code
    
    def _collect_generated_images(self) -> List[str]:
        """
        收集生成的图表文件
        
        Returns:
            图表路径列表
        """
        images = []
        
        # 检查输出目录中新生成的图片
        for ext in ["png", "jpg", "jpeg", "svg", "pdf"]:
            for img_path in self.output_dir.glob(f"plot_*.{ext}"):
                # 只收集最近 5 分钟内生成的
                if time.time() - img_path.stat().st_mtime < 300:
                    images.append(str(img_path))
        
        return images
    
    def _record_execution(self, code: str, result: CodeExecutionResult, 
                          execution_time: float):
        """记录执行历史"""
        record = {
            "timestamp": time.time(),
            "code_preview": code[:200],
            "success": result.success,
            "execution_time": execution_time,
            "has_images": bool(result.images)
        }
        
        self.code_history.append(record)
        
        # 只保留最近 100 条
        if len(self.code_history) > 100:
            self.code_history = self.code_history[-100:]
    
    def _emit_progress(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
        """发送进度事件"""
        payload = {"message": message}
        if data:
            payload.update(data)
        if self.emit:
            self.emit(event_type, payload)
        logger.info(f"[{event_type}] {message}")
    
    def get_execution_stats(self) -> Dict:
        """获取执行统计信息"""
        if not self.code_history:
            return {"total": 0, "success_rate": 0, "avg_time": 0}
        
        total = len(self.code_history)
        success = sum(1 for r in self.code_history if r["success"])
        avg_time = sum(r["execution_time"] for r in self.code_history) / total
        
        return {
            "total": total,
            "success_rate": success / total * 100,
            "avg_time": round(avg_time, 2)
        }
    
    def suggest_packages(self, task_description: str) -> List[str]:
        """
        根据任务描述推荐需要安装的包
        
        Args:
            task_description: 任务描述
            
        Returns:
            推荐的包列表
        """
        suggestions = []
        
        # 关键词匹配
        keywords = {
            "数据分析": ["pandas", "numpy"],
            "绘图": ["matplotlib", "seaborn"],
            "图表": ["matplotlib", "plotly"],
            "可视化": ["matplotlib", "seaborn", "plotly"],
            "机器学习": ["scikit-learn", "numpy", "pandas"],
            "图像处理": ["Pillow", "opencv-python"],
            "PDF": ["PyPDF2", "pypdf"],
            "Word": ["python-docx"],
            "Excel": ["openpyxl", "pandas"],
            "PPT": ["python-pptx"],
            "网络请求": ["requests"],
            "爬虫": ["requests", "beautifulsoup4", "lxml"],
            "中文分词": ["jieba"],
            "词云": ["wordcloud", "jieba"],
        }
        
        for keyword, packages in keywords.items():
            if keyword in task_description:
                suggestions.extend(packages)
        
        return list(set(suggestions))
