# 语义路由准确性与存储安全性强化补丁说明

**日期**: 2026-02-07  
**版本**: v1.0  
**作者**: AI Assistant

---

## 📋 优化概述

本次优化针对 `IntentRouter` 和 `KeyEncryptor` 进行了四个方面的强化：

1. **动态意图阈值**：每个意图使用独立的 `min_confidence` 阈值，替代全局阈值
2. **名词惩罚列表扩充**：自动生成文件后缀名关键词，增加绝对路径正则检测
3. **加密算法增强**：KeyEncryptor 使用 XOR + Base64，增加反混淆难度
4. **意图库热更新**：支持运行时动态添加意图示例，丰富意图库

---

## 🔧 详细变更

### 1. 动态意图阈值

#### 问题背景
之前所有意图使用统一的全局阈值（0.65），但不同意图的识别难度不同。例如：
- 应用关闭操作需要更高置信度（避免误判）
- 系统操作可以接受较低置信度（更宽松）

#### 实现方案

**修改 `intent_metadata`** (`agent/core/intent_router.py`):
```python
self.intent_metadata = {
    "translate": {"type": "text_process", "action": "translate", "min_confidence": 0.65},
    "summarize": {"type": "text_process", "action": "summarize", "min_confidence": 0.65},
    "polish": {"type": "text_process", "action": "polish", "min_confidence": 0.65},
    "screenshot": {"type": "screenshot_desktop", "action": "screenshot", "min_confidence": 0.6},
    "volume_control": {"type": "system_control", "action": "volume", "min_confidence": 0.6},
    "brightness_control": {"type": "system_control", "action": "brightness", "min_confidence": 0.6},
    "system_info": {"type": "system_control", "action": "sys_info", "min_confidence": 0.6},
    "app_open": {"type": "open_app", "action": "open", "min_confidence": 0.7},
    "app_close": {"type": "close_app", "action": "close", "min_confidence": 0.8},  # 最高阈值
}
```

**修改 `detect` 方法**:
```python
# 动态阈值判断（使用意图的 min_confidence，如果没有则使用默认 threshold）
intent_meta = self.intent_metadata.get(best_intent, {})
dynamic_threshold = intent_meta.get("min_confidence", threshold)

if best_score >= dynamic_threshold:
    # 匹配成功
```

**阈值设计原则**:
- **文本处理类** (0.65): 中等阈值，平衡准确性和召回率
- **系统操作类** (0.6): 较低阈值，更宽松（用户可能用不同表达）
- **应用打开** (0.7): 较高阈值，避免误判
- **应用关闭** (0.8): 最高阈值，防止误关闭应用

**效果**:
- ✅ 不同意图使用最适合的阈值
- ✅ 降低误判率（特别是应用关闭）
- ✅ 提高识别准确性

---

### 2. 名词惩罚列表扩充

#### 问题背景
之前的文件关键词列表是硬编码的，不完整。需要：
- 自动生成常见文件后缀名关键词
- 检测绝对路径（`/Users/`, `C:\` 等）

#### 实现方案

**新增 `_generate_file_keywords` 方法**:
```python
def _generate_file_keywords(self) -> List[str]:
    """自动生成文件关键词列表（从常见文件后缀名）"""
    # 常见文件后缀名（93个）
    common_extensions = [
        '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.pdf', '.txt',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
        '.mp4', '.avi', '.mov', '.mkv',
        '.mp3', '.wav', '.flac', '.aac',
        '.zip', '.rar', '.7z', '.tar', '.gz',
        '.py', '.js', '.ts', '.java', '.cpp', '.c', '.html', '.css',
        # ... 更多
    ]
    
    # 文件相关中文/英文关键词
    chinese_keywords = ['文件', '文档', '图片', '照片', '视频', ...]
    english_keywords = ['file', 'document', 'image', 'photo', ...]
    
    return common_extensions + chinese_keywords + english_keywords
```

**新增 `_check_absolute_path` 方法**:
```python
def _check_absolute_path(self, text: str) -> bool:
    """检测文本中是否包含绝对路径"""
    import re
    # Unix 绝对路径：/Users/, /home/, /var/, /etc/, /tmp/, /opt/
    unix_pattern = r'/(Users|home|var|etc|tmp|opt|usr|bin|sbin|lib|mnt|media|root|srv|sys|dev|proc)/'
    # Windows 绝对路径：C:\, D:\, E:\ 等
    windows_pattern = r'[A-Z]:\\'
    
    return bool(re.search(unix_pattern, text, re.IGNORECASE) or 
                re.search(windows_pattern, text))
```

**增强惩罚机制**:
```python
# 使用自动生成的文件关键词列表
has_file_keyword = any(kw in user_text for kw in self.file_keywords)
# 检测绝对路径
has_absolute_path = self._check_absolute_path(text)

if has_file_keyword or has_absolute_path:
    penalty = 0.4  # 扣掉 0.4 分
    best_score -= penalty
```

**效果**:
- ✅ 自动生成 93 个文件关键词（包含常见后缀名）
- ✅ 检测 Unix/Windows 绝对路径
- ✅ 更准确的冲突检测，降低误判

---

### 3. 加密算法增强

#### 问题背景
之前的加密算法只是简单的 `key + salt` 然后 Base64，容易被逆向。需要增加 XOR 混淆层。

#### 实现方案

**增强 `encrypt` 方法** (`agent/tools/key_encryptor.py`):
```python
@staticmethod
def encrypt(plain_key: str) -> str:
    """混淆 API Key（增强版：XOR + Base64）"""
    # 1. 生成机器 Salt（固定长度）
    machine_id = KeyEncryptor._get_machine_id()
    salt_bytes = hashlib.sha256(machine_id.encode()).digest()[:len(plain_key)]
    
    # 2. 如果 Salt 长度不足，循环使用
    if len(salt_bytes) < len(plain_key):
        salt_bytes = (salt_bytes * ((len(plain_key) // len(salt_bytes)) + 1))[:len(plain_key)]
    
    # 3. XOR 混淆
    key_bytes = plain_key.encode('utf-8')
    xor_result = bytes(a ^ b for a, b in zip(key_bytes, salt_bytes))
    
    # 4. Base64 编码
    encoded = base64.b64encode(xor_result).decode()
    
    return f"ENC:{encoded}"
```

**增强 `decrypt` 方法**:
```python
@staticmethod
def decrypt(encrypted_key: str) -> str:
    """解密 API Key（增强版：XOR + Base64）"""
    # 1. Base64 解码
    xor_result = base64.b64decode(encoded.encode())
    
    # 2. XOR 解密（XOR 的逆操作就是 XOR 本身）
    salt_bytes = hashlib.sha256(machine_id.encode()).digest()[:len(xor_result)]
    if len(salt_bytes) < len(xor_result):
        salt_bytes = (salt_bytes * ((len(xor_result) // len(salt_bytes)) + 1))[:len(xor_result)]
    
    key_bytes = bytes(a ^ b for a, b in zip(xor_result, salt_bytes))
    
    # 3. 转换为字符串
    return key_bytes.decode('utf-8')
```

**向后兼容**:
- ✅ 支持旧格式（`key:salt` Base64）
- ✅ 支持明文（自动检测）

**效果**:
- ✅ XOR 混淆增加反混淆难度
- ✅ 机器 Salt 确保不同机器无法互解
- ✅ 向后兼容，平滑升级

---

### 4. 意图库热更新

#### 问题背景
意图库是静态的，无法根据用户反馈动态调整。需要支持运行时添加新示例。

#### 实现方案

**新增 `add_intent_example` 方法** (`agent/core/intent_router.py`):
```python
def add_intent_example(self, intent: str, text: str) -> bool:
    """
    动态添加意图示例（热更新意图库）
    
    功能：
    - 允许系统在运行过程中通过用户的纠正行为，动态丰富 intent_registry
    - 自动重新计算该意图的 Embeddings
    
    Args:
        intent: 意图类型（必须是已存在的意图）
        text: 新的示例文本
        
    Returns:
        是否成功添加
    """
    # 1. 验证意图存在
    if intent not in self.intent_registry:
        return False
    
    # 2. 添加到意图库
    if text not in self.intent_registry[intent]:
        self.intent_registry[intent].append(text.strip())
    
    # 3. 更新 Embeddings（延迟计算，不阻塞）
    if intent in self.intent_embeddings:
        new_vec = self.embedding_model.encode(text.strip())
        if new_vec:
            existing_vecs = self.intent_embeddings[intent]
            new_vec_array = np.array([new_vec])
            self.intent_embeddings[intent] = np.vstack([existing_vecs, new_vec_array])
    
    return True
```

**使用场景**:
- 用户纠正：当用户指出意图识别错误时，可以添加正确示例
- 自适应学习：根据用户常用表达，动态丰富意图库
- A/B 测试：测试不同示例对识别准确性的影响

**效果**:
- ✅ 运行时动态更新意图库
- ✅ 自动更新 Embeddings，无需重启
- ✅ 提高识别准确性（通过用户反馈）

---

## 📁 文件变更清单

### 修改文件
- `agent/core/intent_router.py`
  - 新增 `min_confidence` 字段到 `intent_metadata`
  - 新增 `_generate_file_keywords()` 方法
  - 新增 `_check_absolute_path()` 方法
  - 修改 `detect()` 使用动态阈值
  - 增强名词惩罚机制（使用自动生成的关键词 + 绝对路径检测）
  - 新增 `add_intent_example()` 方法（意图库热更新）

- `agent/tools/key_encryptor.py`
  - 增强 `encrypt()` 方法（XOR + Base64）
  - 增强 `decrypt()` 方法（XOR + Base64）
  - 保持向后兼容（旧格式 + 明文）

---

## 🧪 测试验证

### 1. 语法检查
```bash
python3.12 -c "import ast; ast.parse(open('agent/core/intent_router.py').read())"
```
✅ 通过

### 2. KeyEncryptor 加密/解密测试
```python
test_key = 'sk-1234567890abcdefghijklmnopqrstuvwxyz'
encrypted = KeyEncryptor.encrypt(test_key)
decrypted = KeyEncryptor.decrypt(encrypted)
assert decrypted == test_key
```
✅ 通过

### 3. IntentRouter 功能测试
- ✅ 文件关键词自动生成：93 个关键词
- ✅ 绝对路径检测：Unix/Windows 路径识别正确
- ✅ 动态阈值配置：所有意图都有 `min_confidence`
- ✅ 意图库热更新：成功添加示例并更新 Embeddings

---

## 🔒 安全增强

1. **动态阈值**: 不同意图使用最适合的阈值，降低误判率
2. **文件关键词扩充**: 更全面的冲突检测，避免误判
3. **XOR 加密**: 增加反混淆难度，保护 API Key
4. **热更新**: 支持根据用户反馈动态调整，提高准确性

---

## 📈 性能优化

1. **文件关键词预生成**: 启动时生成一次，避免重复计算
2. **Embeddings 增量更新**: 热更新时只更新新增示例的 Embeddings

---

## 🚀 后续建议

1. **阈值自动调优**: 根据历史数据自动调整 `min_confidence`
2. **文件关键词配置化**: 允许用户自定义文件关键词列表
3. **意图库持久化**: 将热更新的示例保存到配置文件
4. **加密算法升级**: 考虑使用 AES 等更强的加密算法（如果需要）

---

## 📝 注意事项

1. **动态阈值**: 如果意图没有 `min_confidence`，会使用默认阈值（0.65）
2. **XOR 加密**: 不是真正的加密，只是混淆。如果需要更强的安全性，建议使用 AES
3. **热更新**: 新增的示例不会持久化，重启后会丢失。建议后续添加持久化功能
4. **向后兼容**: KeyEncryptor 支持旧格式和明文，确保平滑升级

---

## ✅ 完成状态

- [x] 动态意图阈值
- [x] 名词惩罚列表扩充
- [x] 加密算法增强
- [x] 意图库热更新
- [x] 语法检查
- [x] 功能测试
- [x] 文档编写

---

**优化完成时间**: 2026-02-07  
**影响范围**: `agent/core/intent_router.py`, `agent/tools/key_encryptor.py`  
**向后兼容**: ✅ 是（保留原有接口和行为）
