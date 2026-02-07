# Orchestrator 与 Executor 协作逻辑优化补丁说明

**日期**: 2026-02-07  
**版本**: v1.0  
**作者**: AI Assistant

---

## 📋 优化概述

本次优化针对 `PlanExecutor` 和 `TaskOrchestrator` 的协作逻辑进行了四个方面的增强：

1. **增强占位符防御**：检测 `NULL_ID` 占位符，抛出特定异常，触发 Reflector 重新分析
2. **重构执行器路由**：引入注册机制，替代硬编码列表，提高可维护性
3. **线程安全记忆存储**：使用队列 + 文件锁，防止并发写入冲突
4. **日志脱敏**：自动检测并脱敏敏感参数（password, key, token 等）

---

## 🔧 详细变更

### 1. 增强占位符防御

#### 问题背景
当占位符替换失败（返回 `NULL_ID`）时，系统会继续执行，导致后续步骤失败。需要提前拦截并触发 Reflector 重新分析上下文。

#### 实现方案

**新增异常类** (`agent/tools/exceptions.py`):
```python
class PlaceholderError(DeskJarvisError):
    """占位符错误：当占位符替换失败（NULL_ID）时抛出"""
    def __init__(self, message: str, placeholder: str = "", step: Dict[str, Any] = None):
        super().__init__(message)
        self.placeholder = placeholder
        self.step = step
```

**增强 `_dispatch_execution`** (`agent/orchestrator/plan_executor.py`):
- 在替换占位符后，递归检查 `params` 中是否包含 `NULL_ID`
- 如果发现 `NULL_ID`，立即抛出 `PlaceholderError`
- 在 `_execute_step_with_retry` 中捕获 `PlaceholderError`，强制触发 Reflector 重新分析

**关键代码**:
```python
# 检测 NULL_ID
null_id_paths = check_null_id(params)
if null_id_paths:
    raise PlaceholderError(
        message=f"[SECURITY_SHIELD] 占位符替换失败，检测到 NULL_ID 在以下路径: {', '.join(null_id_paths)}",
        placeholder=", ".join(null_id_paths),
        step=step
    )
```

**效果**:
- ✅ 提前拦截占位符错误，避免无效执行
- ✅ 自动触发 Reflector 重新分析，提高自愈能力
- ✅ 明确的错误信息，便于调试

---

### 2. 重构执行器路由

#### 问题背景
`_get_executor_for_step` 方法使用硬编码列表，难以维护和扩展。

#### 实现方案

**引入注册机制** (`agent/orchestrator/plan_executor.py`):
- 在 `__init__` 中初始化 `self.executor_registry: Dict[str, str]`
- 新增 `_register_executors()` 方法，统一注册所有路由规则
- `_get_executor_for_step` 优先使用注册表查找，保留向后兼容

**注册表结构**:
```python
self.executor_registry = {
    "file_create": "file_manager",
    "browser_navigate": "browser_executor",
    "python_script": "system_tools",
    # ... 更多路由规则
}
```

**优势**:
- ✅ 集中管理路由规则，易于维护
- ✅ 支持动态注册新执行器
- ✅ 保留向后兼容（错误类型修复）

---

### 3. 线程安全记忆存储

#### 问题背景
记忆保存使用简单的 `threading.Thread`，可能导致并发写入冲突（多个任务同时保存记忆）。

#### 实现方案

**新增 `ThreadSafeMemoryQueue`** (`agent/tools/memory_queue.py`):
- 使用 `queue.Queue` 缓冲记忆保存任务
- 后台工作线程处理队列（非阻塞）
- 文件锁（`fcntl`/`msvcrt`）防止并发写入冲突
- 跨平台支持（Unix/Windows）

**关键特性**:
```python
class ThreadSafeMemoryQueue:
    def __init__(self, memory_manager, lock_file_path=None):
        self.queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._start_worker()
    
    def enqueue_save(self, instruction, steps, result, ...):
        """非阻塞加入队列"""
        self.queue.put(task, block=False)
    
    def _process_task(self, task):
        """带文件锁的保存操作"""
        with file_lock:
            self.memory_manager.save_task_result(...)
```

**集成到 `TaskOrchestrator`**:
```python
if not hasattr(self, '_memory_queue'):
    from agent.tools.memory_queue import ThreadSafeMemoryQueue
    self._memory_queue = ThreadSafeMemoryQueue(self.memory)

self._memory_queue.enqueue_save(...)
```

**效果**:
- ✅ 非阻塞：主流程不等待记忆保存
- ✅ 线程安全：文件锁防止并发冲突
- ✅ 可靠性：队列缓冲，避免任务丢失

---

### 4. 日志脱敏

#### 问题背景
日志中可能包含敏感信息（密码、API Key、Token），存在泄露风险。

#### 实现方案

**新增 `LogSanitizer`** (`agent/tools/log_sanitizer.py`):
- 检测敏感参数名（password, key, token 等）
- 脱敏值：只显示前3位和后3位，中间用 `***` 替代
- 支持字典、列表的递归脱敏

**敏感关键词列表**:
```python
SENSITIVE_KEYWORDS = [
    'password', 'passwd', 'pwd', 'pass',
    'key', 'api_key', 'apikey', 'secret',
    'token', 'access_token', 'refresh_token',
    'auth', 'authorization', 'credential',
    'private', 'private_key', 'secret_key'
]
```

**使用示例**:
```python
from agent.tools.log_sanitizer import LogSanitizer

# 脱敏字典
sanitized = LogSanitizer.sanitize_dict(params)
logger.debug(f"参数（已脱敏）: {sanitized}")

# 脱敏日志消息
message = LogSanitizer.sanitize_log_message(message, params)
```

**集成位置**:
- `_replace_placeholders`: 占位符日志脱敏
- `_dispatch_execution`: 执行参数日志脱敏

**效果**:
- ✅ 自动检测敏感参数
- ✅ 智能脱敏（保留部分信息用于调试）
- ✅ 不影响正常参数显示

---

## 📁 文件变更清单

### 新增文件
- `agent/tools/exceptions.py` - 新增 `PlaceholderError` 异常类
- `agent/tools/log_sanitizer.py` - 日志脱敏工具
- `agent/tools/memory_queue.py` - 线程安全记忆存储队列

### 修改文件
- `agent/orchestrator/plan_executor.py`
  - 新增 `PlaceholderError` 导入
  - 新增 `LogSanitizer` 导入
  - 新增 `_register_executors()` 方法
  - 重构 `_get_executor_for_step()` 使用注册表
  - 增强 `_dispatch_execution()` 检测 `NULL_ID`
  - 增强 `_execute_step_with_retry()` 捕获 `PlaceholderError`
  - 集成日志脱敏到 `_replace_placeholders()` 和 `_dispatch_execution()`

- `agent/orchestrator/task_orchestrator.py`
  - 使用 `ThreadSafeMemoryQueue` 替代简单线程

---

## 🧪 测试验证

### 1. 语法检查
```bash
python3.12 -c "import ast; ast.parse(open('agent/orchestrator/plan_executor.py').read())"
```
✅ 通过

### 2. 日志脱敏测试
```python
from agent.tools.log_sanitizer import LogSanitizer

params = {'password': 'mysecret123', 'api_key': 'sk-1234567890abcdef'}
sanitized = LogSanitizer.sanitize_dict(params)
# 结果: {'password': 'mys***123', 'api_key': 'sk-***def'}
```
✅ 通过

### 3. 占位符防御测试
- 模拟 `NULL_ID` 场景，验证 `PlaceholderError` 抛出
- 验证 Reflector 被正确触发
✅ 通过

---

## 🔒 安全增强

1. **占位符防御**: 提前拦截无效占位符，避免执行失败
2. **日志脱敏**: 防止敏感信息泄露
3. **线程安全**: 文件锁防止并发写入冲突

---

## 📈 性能优化

1. **非阻塞记忆存储**: 使用队列，主流程不等待
2. **注册表查找**: O(1) 时间复杂度，替代列表遍历

---

## 🚀 后续建议

1. **动态执行器注册**: 支持运行时注册新执行器
2. **占位符验证增强**: 支持更复杂的占位符格式验证
3. **日志脱敏配置**: 允许用户自定义敏感关键词列表
4. **记忆存储监控**: 添加队列长度监控和告警

---

## 📝 注意事项

1. **文件锁兼容性**: Windows 使用 `msvcrt`，Unix 使用 `fcntl`
2. **占位符错误处理**: `PlaceholderError` 会触发 Reflector，可能需要多次重试
3. **日志脱敏**: 脱敏后的日志仍保留部分信息，用于调试，但不会泄露完整敏感值

---

## ✅ 完成状态

- [x] 增强占位符防御
- [x] 重构执行器路由
- [x] 线程安全记忆存储
- [x] 日志脱敏
- [x] 语法检查
- [x] 功能测试
- [x] 文档编写

---

**优化完成时间**: 2026-02-07  
**影响范围**: `agent/orchestrator/`, `agent/tools/`  
**向后兼容**: ✅ 是（保留原有接口和行为）
