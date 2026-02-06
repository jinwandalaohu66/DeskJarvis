# 应用名解析流程说明

> **问题**：AI为什么不能正确解析应用名？  
> **回答**：AI确实在解析，但有时候会出错。我们需要让AI更可靠。

---

## 📊 当前解析流程

### 1. **AI解析阶段**（Planner）

```
用户输入："打开企业微信控制键盘输入zhangxuzheng按空格"
    ↓
AI（Claude/DeepSeek/OpenAI）读取Prompt
    ↓
AI生成JSON步骤列表
    ↓
返回步骤列表
```

**代码位置**：`agent/planner/claude_planner.py` → `plan()` 方法

```python
# 1. 构建Prompt（包含应用名解析规则）
prompt = self._build_prompt(user_instruction, context)

# 2. 调用AI API
response = self.client.messages.create(
    model=self.model,
    messages=[{"role": "user", "content": prompt}]
)

# 3. 解析AI返回的JSON
steps = self._parse_response(response.content[0].text)
```

**问题**：AI有时候会忽略Prompt中的规则，把整个句子当作应用名。

---

### 2. **后处理阶段**（Safety Net）

```
AI返回的步骤列表
    ↓
检查open_app步骤的app_name
    ↓
如果包含动作词 → 自动拆分
    ↓
返回修正后的步骤列表
```

**代码位置**：`agent/main.py` → `_fix_app_name_parsing()` 方法

```python
# 在_execute_steps之前调用
steps = self._fix_app_name_parsing(steps)
```

**作用**：作为"安全网"，防止AI出错。

---

## 🤔 为什么AI会出错？

### 原因分析

1. **Prompt不够强**
   - 虽然写了规则，但AI可能忽略
   - 特别是当指令没有明确的连接词（如"然后"）时

2. **AI的"理解偏差"**
   - AI可能认为"企业微信控制键盘输入zhangxuzheng按空格"是一个完整的应用名
   - 没有意识到这应该拆分为多个步骤

3. **Prompt位置不够显眼**
   - 规则可能被其他内容淹没
   - AI没有"看到"或"重视"这些规则

---

## ✅ 解决方案

### 方案1：强化Prompt（主要方案）

**改进**：
1. ✅ 在Prompt开头就强调应用名解析规则
2. ✅ 添加详细的解析示例（包括用户的具体案例）
3. ✅ 添加"检查清单"，让AI在生成后自检
4. ✅ 使用更强烈的语言（"极其重要"、"必须严格遵守"）

**已实施**：
- ✅ 在`claude_planner.py`中添加了详细的应用名解析规则
- ✅ 添加了"最后检查"部分，让AI在返回前自检

### 方案2：后处理逻辑（安全网）

**作用**：
- 如果AI还是出错，后处理逻辑会自动修正
- 这是"双重保险"

**已实施**：
- ✅ 在`main.py`中添加了`_fix_app_name_parsing()`方法

---

## 🎯 理想状态

**目标**：AI自己就能正确解析，不需要后处理。

**当前状态**：
- ✅ Prompt已强化
- ✅ 后处理作为安全网
- ⚠️ 需要测试验证AI是否能正确解析

---

## 📝 测试建议

请测试以下场景，看看AI是否能正确解析：

1. **"打开企业微信控制键盘输入zhangxuzheng按空格"**
   - 期望：3个步骤（open_app + keyboard_type + keyboard_shortcut）
   - 如果AI还是出错，后处理会自动修正

2. **"打开Chrome然后搜索Python"**
   - 期望：2个步骤（open_app + browser_navigate）

3. **"打开Visual Studio Code"**
   - 期望：1个步骤（open_app，没有后续操作）

---

## 🔍 如何验证AI是否正确解析？

**方法1：查看日志**
```bash
# 查看AI返回的原始步骤
grep "规划完成" logs/agent.log
```

**方法2：查看后处理日志**
```bash
# 如果后处理修正了，会看到警告日志
grep "检测到应用名解析错误" logs/agent.log
```

**方法3：前端显示**
- 如果后处理修正了，前端会显示修正后的步骤
- 如果AI正确解析，不会触发后处理

---

## 💡 总结

1. **AI确实在解析**：在`planner`中，AI根据Prompt生成步骤
2. **AI有时候会出错**：可能忽略Prompt中的规则
3. **解决方案**：
   - ✅ 强化Prompt（让AI更可靠）
   - ✅ 后处理逻辑（作为安全网）
4. **理想状态**：AI自己就能正确解析，后处理只作为备用

**当前架构**：
```
用户输入
    ↓
AI解析（Planner）← 主要解析
    ↓
后处理修正（Safety Net）← 备用修正
    ↓
执行步骤
```
