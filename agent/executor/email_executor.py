"""
Email Executor

处理邮件发送相关的任务步骤
"""

import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

from agent.executor.email_sender import EmailSender
from agent.executor.email_reader import EmailReader
from agent.executor.file_compressor import FileCompressor
from agent.tools.config import Config
from agent.user_input import UserInputManager

logger = logging.getLogger(__name__)


class EmailExecutor:
    """
    邮件执行器
   
    职责：
    - 发送邮件（带附件）
    - 搜索邮件 (IMAP)
    - 获取邮件详情 (IMAP)
    - 管理邮件 (归档/移动/标记已读)
    - 压缩文件
    """
    
    def __init__(self, config: Config, emit_callback: Optional[Callable] = None):
        """
        初始化邮件执行器
        """
        self.config = config
        self._emit = emit_callback
        
        # 初始化邮件发送器 (SMTP)
        self.email_sender = EmailSender(
            smtp_server=getattr(config, 'email_smtp_server', 'smtp.gmail.com'),
            smtp_port=getattr(config, 'email_smtp_port', 587)
        )
        
        # 懒加载邮件读取器 (IMAP)
        self.email_reader = None
        
        # 文件压缩器
        self.file_compressor = FileCompressor()
        
        # 用户输入管理器
        self.user_input_manager = UserInputManager(emit_callback=emit_callback)
        
        logger.info("邮件执行器已初始化")
    
    @property
    def emit(self) -> Optional[Callable]:
        return self._emit
        
    @emit.setter
    def emit(self, value: Optional[Callable]):
        self._emit = value
        if hasattr(self, 'user_input_manager'):
            self.user_input_manager.emit = value
        if hasattr(self, 'file_compressor') and hasattr(self.file_compressor, 'emit'):
            self.file_compressor.emit = value

    def execute_step(self, step: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行单个任务步骤
        """
        step_type = step.get("type")
        params = step.get("params", {})
        
        logger.info(f"执行步骤: {step_type}")
        
        try:
            if step_type == "send_email":
                return self._send_email(params)
            elif step_type == "search_emails":
                return self._search_emails(params)
            elif step_type == "get_email_details":
                return self._get_email_details(params, context)
            elif step_type == "download_attachments":
                return self._download_attachments(params)
            elif step_type == "manage_emails":
                return self._manage_emails(params)
            elif step_type == "compress_files":
                return self._compress_files(params)
            else:
                return {
                    "success": False,
                    "message": f"未知的步骤类型: {step_type}",
                    "data": None
                }
                
        except Exception as e:
            logger.error(f"执行步骤失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"执行失败: {e}",
                "data": None
            }
    
    def _send_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送邮件
        
        Args:
            params: 参数字典
                - recipient: 收件人（必需）
                - subject: 主题（可选，默认"文件"）
                - body: 正文（可选，默认"请查收附件"）
                - attachments: 附件路径列表（可选）
                - sender: 发件人（可选，从配置读取）
                - password: 密码（可选，从配置读取）
                - cc: 抄送列表（可选）
                - html: 是否HTML格式（可选，默认False）
        
        Returns:
            执行结果字典
        """
        recipient = params.get("recipient")
        if not recipient:
            return {
                "success": False,
                "message": "缺少收件人（recipient）",
                "data": None
            }
        
        subject = params.get("subject", "文件")
        body = params.get("body", "请查收附件")
        attachments = params.get("attachments", [])
        
        # 从配置获取 SMTP 服务器和端口
        smtp_server = self.config.email_smtp_server
        smtp_port = self.config.email_smtp_port

        # 容错处理：自动补全常见的 SMTP 地址错误
        if smtp_server.lower() == "qq":
            smtp_server = "smtp.qq.com"
            logger.info(f"自动纠正 SMTP 服务器: qq -> {smtp_server}")
        elif smtp_server.lower() == "gmail":
            smtp_server = "smtp.gmail.com"
            logger.info(f"自动纠正 SMTP 服务器: gmail -> {smtp_server}")
        elif smtp_server.lower() == "outlook":
            smtp_server = "smtp.office365.com"
            logger.info(f"自动纠正 SMTP 服务器: outlook -> {smtp_server}")

        # 更新 EmailSender 实例的服务器和端口
        self.email_sender.smtp_server = smtp_server
        self.email_sender.smtp_port = smtp_port

        # 从配置或环境变量获取发件人信息
        sender_email = params.get("sender") or getattr(self.config, 'email_sender', None)
        sender_password = params.get("password") or getattr(self.config, 'email_password', None)
        
        if not sender_email or not sender_password:
            logger.info("邮件配置缺失，请求用户输入...")
            if self.emit:
                self.emit("status_update", {"message": "检测到尚未设置发件箱，请在弹出的窗口中填写配置..."})
            
            # 请求用户输入配置
            email_conf = self.user_input_manager.request_email_config()
            
            if email_conf:
                sender_email = email_conf.get("sender_email")
                sender_password = email_conf.get("password")
                smtp_server = email_conf.get("smtp_server")
                smtp_port = int(email_conf.get("smtp_port", 587))
                
                # 更新持久化配置
                self.config.set("email_sender", sender_email)
                self.config.set("email_password", sender_password)
                self.config.set("email_smtp_server", smtp_server)
                self.config.set("email_smtp_port", smtp_port)
                self.config.save()
                
                # 重新初始化发送器（如果 SMTP 服务器或端口变了）
                self.email_sender = EmailSender(smtp_server=smtp_server, smtp_port=smtp_port)
                
                logger.info("✅ 邮件配置已保存并应用")
            else:
                return {
                    "success": False,
                    "message": "用户取消了邮件配置，无法发送邮件",
                    "data": None
                }
        
        # 验证邮箱格式
        if not EmailSender.validate_email(recipient):
            return {
                "success": False,
                "message": f"无效的收件人邮箱格式: {recipient}",
                "data": None
            }
        
        # 解析附件路径
        if attachments:
            resolved_attachments = []
            for attachment in attachments:
                path = Path(attachment).expanduser().resolve()
                if path.exists():
                    resolved_attachments.append(str(path))
                else:
                    logger.warning(f"附件不存在，跳过: {attachment}")
            attachments = resolved_attachments
        
        # 如果有多个附件且未压缩，自动压缩
        if len(attachments) > 1 and not any(str(a).endswith('.zip') for a in attachments):
            logger.info("检测到多个附件，自动压缩...")
            try:
                zip_path = f"/tmp/attachments_{int(time.time())}.zip"
                self.file_compressor.compress_files(attachments, zip_path)
                attachments = [zip_path]
                logger.info(f"✅ 已压缩为: {zip_path}")
            except Exception as e:
                logger.warning(f"压缩失败，将分别发送: {e}")
        
        # 发送邮件
        try:
            result = self.email_sender.send_email(
                sender_email=sender_email,
                sender_password=sender_password,
                recipient=recipient,
                subject=subject,
                body=body,
                attachments=attachments,
                cc=params.get("cc"),
                bcc=params.get("bcc"),
                html=params.get("html", False)
            )
            
            return result
            
        except Exception as e:
            error_msg = f"发送邮件失败: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg,
                "data": None
            }
    
    def _ensure_reader(self) -> bool:
        """确保 EmailReader 已初始化并连接"""
        if self.email_reader and self.email_reader.mail:
            return True
            
        # 获取配置
        imap_server = self.config.email_imap_server
        imap_port = self.config.email_imap_port
        sender_email = self.config.email_sender
        sender_password = self.config.email_password
        
        if not sender_email or not sender_password:
            logger.warning("邮件配置缺失，无法连接 IMAP")
            return False
            
        self.email_reader = EmailReader(imap_server, imap_port)
        # 连接时已设置 timeout=10
        return self.email_reader.connect(sender_email, sender_password)

    def _search_emails(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        搜索邮件
        
        注意：此方法仅执行 IMAP 搜索，不进行语义搜索或向量化。
        如果将来需要添加 SentenceTransformer 或嵌入模型进行语义搜索，
        请添加判断：如果邮件数量超过1封，或者在非语义搜索模式下，跳过嵌入步骤。
        
        Args:
            params: 参数字典
                - query: IMAP 搜索查询（如 "ALL", "(FROM \"xxx\")"）
                - folder: 邮件文件夹（可选，默认 "INBOX"）
                - limit: 返回的最大邮件数量（可选，默认 10）
                - keyword_filter: 关键词过滤（可选，在主题或发件人中搜索）
        """
        if not self._ensure_reader():
            return {"success": False, "message": "无法连接到邮件服务器"}
            
        # 处理查询
        query = params.get("query", "ALL")
        folder = params.get("folder", "INBOX")
        limit = params.get("limit", 10)
        keyword_filter = params.get("keyword_filter")  # 新增：关键词过滤
        
        # 简单处理中文搜索 (IMAP 搜索比较复杂，这里做一个基础转换)
        # 注意：这里的 query 应该是符合 IMAP 语法的，如 '(FROM "xxx")'
        
        results = self.email_reader.search_emails(query, folder, limit, keyword_filter=keyword_filter)
        
        # 性能优化：如果邮件数量较多，避免进行耗时的向量化操作
        # 当前实现不包含向量化，但如果将来添加，应在此处添加判断：
        # if len(results) > 1 or not params.get("semantic_search", False):
        #     # 跳过嵌入步骤，直接返回结果
        #     pass
        
        filter_info = f"（关键词过滤: {keyword_filter}）" if keyword_filter else ""
        
        # 确保返回纯数据字典，不包含任何方法引用
        # results 已经是 List[Dict[str, Any]]，每个字典包含 id, subject, from, date 等纯数据字段
        return {
            "success": True,
            "message": f"搜索到 {len(results)} 封邮件{filter_info}",
            "data": {"emails": results}  # results 是纯数据列表，不包含方法引用
        }

    def _get_email_details(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取邮件详情"""
        # 同步纠错：在入口处检查并修正中文或描述性ID
        msg_id_raw = params.get("id", "")
        msg_id_str = str(msg_id_raw).strip()
        
        # 检测中文或描述性文字
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in msg_id_str)
        has_descriptive = "ID" in msg_id_str.upper() or "邮件" in msg_id_str or "第一个" in msg_id_str or "上一步" in msg_id_str
        
        # 如果包含中文或描述性文字，且不是占位符格式，进行自动修正
        if (has_chinese or has_descriptive) and not msg_id_str.startswith("{{"):
            logger.warning(f"🔧 AI语法自动修改：检测到中文或描述性ID '{msg_id_str}'，自动修正为标准占位符")
            # 强制重置为标准占位符（假设第一步总是搜索）
            params['id'] = "{{step1.result[0].id}}"
            msg_id_raw = params.get("id")
            logger.info("已自动修正为: {{step1.result[0].id}}")
        
        # 统一ID提取逻辑：使用 params.get('id') 而不是 params['id']
        id_raw = params.get("id")
        
        # 防御字典解析：如果 id 是一个字典（比如上一阶段返回的完整对象），使用 id.get('id') 提取字符串
        # 如果 id 是字符串，直接使用
        if isinstance(id_raw, dict):
            msg_id = id_raw.get("id")
            logger.info(f"从字典中提取邮件ID: {msg_id}")
        elif isinstance(id_raw, list) and len(id_raw) > 0:
            # 如果 id 是列表（如 search_emails 返回的结果），取第一个元素的 id
            first_item = id_raw[0]
            if isinstance(first_item, dict):
                msg_id = first_item.get("id")
                logger.info(f"从列表第一个元素中提取邮件ID: {msg_id}")
            else:
                msg_id = first_item
        else:
            msg_id = id_raw
        
        # 检查是否为有效类型
        if not isinstance(msg_id, (str, bytes)):
            logger.warning(f"邮件ID类型无效: {type(msg_id)}, 值: {repr(msg_id)}")
            return {"success": False, "message": "未能识别邮件ID，请重试"}
        
        # 检查是否为空字符串或仅包含空白字符
        msg_id_str = str(msg_id).strip()
        if not msg_id_str:
            logger.warning("邮件ID为空字符串")
            return {"success": False, "message": "未能识别邮件ID，请重试"}
        
        # 如果仍然是占位符格式，尝试从 context 中替换（同步纠错的后续处理）
        if msg_id_str.startswith("{{") and context:
            import re
            pattern = r'\{\{step(\d+)\.([^}]+)\}\}'
            matches = re.findall(pattern, msg_id_str)
            if matches:
                step_num_str, path = matches[0]
                step_num = int(step_num_str)
                step_results = context.get("step_results", [])
                if step_num > 0 and step_num <= len(step_results):
                    step_result = step_results[step_num - 1]
                    step_data = step_result.get("result", {}).get("data", {})
                    # 使用简单的路径解析（因为这是同步纠错，不需要完整的 get_deep_value）
                    if path == "result[0].id":
                        if isinstance(step_data, dict) and "emails" in step_data:
                            emails = step_data.get("emails", [])
                            if isinstance(emails, list) and len(emails) > 0:
                                first_email = emails[0]
                                if isinstance(first_email, dict):
                                    msg_id_str = str(first_email.get("id", ""))
                                    logger.info(f"🔧 同步纠错：从 step{step_num} 提取ID: {msg_id_str}")
        
        # 类型强转：确保经过 .strip() 和编码检查
        msg_id_str = str(msg_id_str).strip()
        
        # 拦截无效交付：在调用 reader.get_email_content 之前，加一个硬判断
        if msg_id_str.startswith("{{") or not msg_id_str:
            logger.warning(f"未能识别邮件ID: {repr(msg_id_str)}")
            return {"success": False, "message": "未能识别邮件ID，请重试"}
        
        # 正则判断：只有全是数字，或者特定的 IMAP UID 格式才允许通过
        import re
        if not re.match(r'^[0-9]+$', msg_id_str):
            logger.warning(f"错误的邮件ID格式: {msg_id_str}")
            return {"success": False, "message": f"错误的邮件ID格式: {msg_id_str}。请确保使用 {{stepN.result[0].id}} 语法。"}
        
        # id 验证通过后，再连接服务器
        if not self._ensure_reader():
            return {"success": False, "message": "无法连接到邮件服务器"}
            
        folder = params.get("folder", "INBOX")
        details = self.email_reader.get_email_content(msg_id_str, folder)
        
        # 修复 Subscriptable 错误：确保 details 不为 None 时再访问
        if not details:
            logger.error("get_email_content 返回了 None 或空值")
            return {"success": False, "message": "获取邮件详情失败：返回结果为空"}
        
        # 安全访问 error 字段
        if details.get("error"):
            return {"success": False, "message": details.get("error", "未知错误")}
        
        # 确保返回纯数据字典，不包含任何方法引用
        # details 应该包含 id, subject, from, body, date 等纯数据字段
        # 如果 details 中包含非序列化对象，创建一个纯数据副本
        clean_details = {}
        for key, value in details.items():
            # 只保留可序列化的基本类型（str, int, float, bool, None, dict, list）
            if isinstance(value, (str, int, float, bool, type(None), dict, list)):
                clean_details[key] = value
            else:
                logger.warning(f"过滤掉非序列化字段: {key} (类型: {type(value).__name__})")
        
        return {
            "success": True,
            "message": "已获取邮件正文",
            "data": clean_details  # 确保返回纯数据字典
        }

    def _download_attachments(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """下载邮件附件"""
        if not self._ensure_reader():
            return {"success": False, "message": "无法连接到邮件服务器"}
            
        msg_id = params.get("id")
        save_dir = params.get("save_dir")
        if not msg_id or not save_dir:
            return {"success": False, "message": "缺少 ID 或 save_dir"}
            
        # 安全路径拦截器 (Protocol B)
        # 强制下载到桌面的专用文件夹，防止 AI 幻觉攻击敏感目录
        base_dir = Path("~/Desktop/DeskJarvis_Downloads").expanduser().resolve()
        requested_dir = Path(save_dir).expanduser().resolve()
        
        if not str(requested_dir).startswith(str(base_dir)):
            # 提取用户想用的文件夹名，如果没有则使用默认名
            folder_name = requested_dir.name if requested_dir.name not in ["", ".", "Desktop"] else "Attachments"
            final_save_dir = str(base_dir / folder_name)
            logger.info(f"安全拦截：路径已从 {save_dir} 修正为 {final_save_dir}")
        else:
            final_save_dir = str(requested_dir)

        file_type = params.get("file_type")
        limit = params.get("limit")
        folder = params.get("folder", "INBOX")
        
        saved_paths = self.email_reader.download_attachments(
            msg_id=msg_id, 
            save_dir=final_save_dir, 
            folder=folder, 
            file_type=file_type, 
            limit=limit
        )
        
        return {
            "success": True,
            "message": f"已下载 {len(saved_paths)} 个附件到 {final_save_dir}",
            "data": {"saved_paths": saved_paths, "save_dir": final_save_dir}
        }

    def _manage_emails(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """管理邮件（移动/标记已读）"""
        if not self._ensure_reader():
            return {"success": False, "message": "无法连接到邮件服务器"}
            
        msg_id = params.get("id")
        action = params.get("action") # move, mark_read
        if not msg_id or not action:
            return {"success": False, "message": "缺少 ID 或 action"}
            
        target_folder = params.get("target_folder")
        current_folder = params.get("folder", "INBOX")
        
        success = self.email_reader.manage_email(msg_id, action, target_folder, current_folder)
        
        return {
            "success": success,
            "message": f"操作 {action} " + ("成功" if success else "失败"),
            "data": None
        }

    def _compress_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        压缩文件
        
        Args:
            params: 参数字典
                - files: 文件路径列表（必需）
                - output: 输出文件路径（必需）
                - type: 压缩类型（可选，默认zip）
        
        Returns:
            执行结果字典
        """
        files = params.get("files", [])
        output = params.get("output")
        compression_type = params.get("type", "zip")
        
        if not files:
            return {
                "success": False,
                "message": "缺少要压缩的文件列表（files）",
                "data": None
            }
        
        if not output:
            # 自动生成输出路径
            output = f"/tmp/compressed_{int(time.time())}.zip"
            logger.info(f"未指定输出路径，使用默认: {output}")
        
        try:
            # 解析文件路径
            resolved_files = []
            for file_path in files:
                path = Path(file_path).expanduser().resolve()
                if path.exists():
                    resolved_files.append(str(path))
                else:
                    logger.warning(f"文件不存在，跳过: {file_path}")
            
            if not resolved_files:
                return {
                    "success": False,
                    "message": "没有找到有效的文件",
                    "data": None
                }
            
            # 压缩文件
            result_path = self.file_compressor.compress_files(
                files=resolved_files,
                output_path=output,
                compression_type=compression_type
            )
            
            file_size = Path(result_path).stat().st_size
            
            return {
                "success": True,
                "message": f"已压缩 {len(resolved_files)} 个文件到 {result_path}",
                "data": {
                    "output_path": result_path,
                    "file_count": len(resolved_files),
                    "size_bytes": file_size,
                    "size_mb": round(file_size / 1024 / 1024, 2)
                }
            }
            
        except Exception as e:
            error_msg = f"压缩文件失败: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "message": error_msg,
                "data": None
            }
