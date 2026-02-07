"""
API Key 加密器 - 简单的混淆存储

功能：
- 使用 base64 + 硬件 UUID 混淆 API Key
- 确保 config.json 中的 Key 不再是明文可见
"""

import base64
import hashlib
import logging
import platform
import uuid

logger = logging.getLogger(__name__)


class KeyEncryptor:
    """
    API Key 加密器
    
    使用简单的混淆算法（base64 + 硬件 UUID），
    不是真正的加密，但足以防止明文泄露。
    """
    
    @staticmethod
    def _get_machine_id() -> str:
        """
        获取机器唯一标识（用于混淆）
        
        Returns:
            机器唯一标识字符串
        """
        try:
            # 尝试获取 MAC 地址
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                           for elements in range(0, 8*6, 8)][::-1])
            return mac
        except Exception:
            # 降级：使用平台信息
            return f"{platform.system()}-{platform.machine()}"
    
    @staticmethod
    def encrypt(plain_key: str) -> str:
        """
        混淆 API Key（增强版：XOR + Base64）
        
        算法：
        1. 使用机器 Salt 对原始 Key 进行 XOR 处理
        2. 然后进行 Base64 编码
        3. 增加反混淆难度
        
        Args:
            plain_key: 明文 API Key
            
        Returns:
            混淆后的字符串（base64 编码）
        """
        if not plain_key:
            return ""
        
        machine_id = KeyEncryptor._get_machine_id()
        # 使用机器 ID 作为盐值（生成固定长度的 Salt）
        salt_bytes = hashlib.sha256(machine_id.encode()).digest()[:len(plain_key)]
        
        # === XOR 混淆 ===
        # 将 plain_key 转换为字节
        key_bytes = plain_key.encode('utf-8')
        
        # 如果 Salt 长度不足，循环使用
        if len(salt_bytes) < len(key_bytes):
            # 扩展 Salt 到与 Key 相同长度
            salt_bytes = (salt_bytes * ((len(key_bytes) // len(salt_bytes)) + 1))[:len(key_bytes)]
        
        # 执行 XOR 操作
        xor_result = bytes(a ^ b for a, b in zip(key_bytes, salt_bytes))
        
        # Base64 编码
        encoded = base64.b64encode(xor_result).decode()
        
        # 添加标识前缀，便于识别
        return f"ENC:{encoded}"
    
    @staticmethod
    def decrypt(encrypted_key: str) -> str:
        """
        解密 API Key（增强版：XOR + Base64）
        
        Args:
            encrypted_key: 混淆后的字符串
            
        Returns:
            明文 API Key
        """
        if not encrypted_key:
            return ""
        
        # 检查是否是混淆格式
        if not encrypted_key.startswith("ENC:"):
            # 旧格式（可能是明文或旧版混淆），尝试兼容
            # 检查是否包含 ":" 分隔符（旧格式）
            if ":" in encrypted_key and not encrypted_key.startswith("ENC:"):
                try:
                    # 尝试旧格式解密（向后兼容）
                    decoded = base64.b64decode(encrypted_key.encode()).decode()
                    plain_key = decoded.split(":")[0]
                    logger.warning("[SECURITY_SHIELD] 检测到旧格式 API Key，将在下次保存时升级为新格式")
                    return plain_key
                except Exception:
                    # 解密失败，可能是明文
                    logger.warning("[SECURITY_SHIELD] 检测到明文 API Key，将在下次保存时自动混淆")
                    return encrypted_key
            else:
                # 明文，直接返回
                logger.warning("[SECURITY_SHIELD] 检测到明文 API Key，将在下次保存时自动混淆")
                return encrypted_key
        
        try:
            # 移除前缀
            encoded = encrypted_key[4:]
            # Base64 解码
            xor_result = base64.b64decode(encoded.encode())
            
            # === XOR 解密 ===
            machine_id = KeyEncryptor._get_machine_id()
            salt_bytes = hashlib.sha256(machine_id.encode()).digest()[:len(xor_result)]
            
            # 如果 Salt 长度不足，循环使用
            if len(salt_bytes) < len(xor_result):
                salt_bytes = (salt_bytes * ((len(xor_result) // len(salt_bytes)) + 1))[:len(xor_result)]
            
            # 执行 XOR 解密（XOR 的逆操作就是 XOR 本身）
            key_bytes = bytes(a ^ b for a, b in zip(xor_result, salt_bytes))
            
            # 转换为字符串
            plain_key = key_bytes.decode('utf-8')
            return plain_key
        except Exception as e:
            logger.error(f"[SECURITY_SHIELD] API Key 解密失败: {e}")
            # 解密失败，返回空字符串
            return ""
