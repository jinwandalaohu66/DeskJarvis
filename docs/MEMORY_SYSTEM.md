# DeskJarvis 记忆系统

> 三层架构，让 AI 越用越懂你

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    MemoryManager（统一入口）                   │
├─────────────────────────────────────────────────────────────┤
│  层3: 高级记忆 (AdvancedMemory)                              │
│  - 情绪分析：理解用户情绪，调整响应方式                           │
│  - 工作流发现：自动识别重复任务模式                              │
│  - 主动学习：发现偏好后主动询问确认                              │
├─────────────────────────────────────────────────────────────┤
│  层2: 向量记忆 (VectorMemory) - Chroma                       │
│  - 语义搜索：找相似对话/任务                                    │
│  - 记忆压缩：旧记忆自动摘要                                     │
│  - 指令匹配：复用成功的执行方案                                  │
├─────────────────────────────────────────────────────────────┤
│  层1: 结构化记忆 (StructuredMemory) - SQLite                  │
│  - 用户偏好：key-value 存储                                    │
│  - 文件历史：最近操作的文件                                     │
│  - 知识图谱：三元组关系                                        │
│  - 习惯模式：高频操作统计                                       │
└─────────────────────────────────────────────────────────────┘
```

## 数据存储位置

```
~/.deskjarvis/
├── memory.db              # SQLite 结构化记忆
├── vector_memory/         # Chroma 向量数据库
│   └── chroma.sqlite3
└── advanced_state.json    # 高级记忆状态
```

## 核心功能

### 1. 自动记忆注入

每次规划任务前，系统会自动注入相关记忆到 prompt：

```python
# 在 main.py 的 execute() 方法中
memory_context = self.memory.get_context_for_instruction(user_instruction)
context["memory_context"] = memory_context
```

注入内容包括：
- 用户偏好（下载路径、命名规则等）
- 最近文件历史
- 相似任务的历史执行记录
- 用户情绪（调整 AI 响应方式）

### 2. 任务结果保存

每次任务完成后，自动保存：

```python
self.memory.save_task_result(
    instruction=user_instruction,
    steps=steps,
    result=result,
    success=True,
    duration=10.5,
    files_involved=["/Users/xxx/Desktop/report.pdf"]
)
```

### 3. 偏好管理

```python
# 设置偏好
memory.set_preference("download_path", "~/Downloads/AI")
memory.set_preference("naming_style", "date_prefix", confirmed=True)

# 获取偏好
path = memory.get_preference("download_path", default="~/Downloads")
```

### 4. 语义搜索

```python
# 搜索相似对话
results = memory.semantic_search("整理发票文件")

# 查找相似指令
similar = memory.find_similar_instructions("下载并整理文件")
```

### 5. 工作流发现

系统会自动发现用户的重复任务模式：

```python
patterns = memory.discover_workflows()
# 返回: [{"pattern_name": "下载+整理工作流", "occurrences": 5, ...}]

# 获取工作流建议
suggestion = memory.get_workflow_suggestion("下载那个报告")
# 返回: {"message": "发现你经常执行「下载+整理」（5次），使用之前的方式？"}
```

### 6. 情绪感知

```python
emotion = memory.analyze_emotion("这个任务怎么又失败了，烦死了")
# 返回: {"emotion": "frustrated", "suggestion": "用户可能遇到困难，保持耐心..."}
```

## API 参考

### MemoryManager

| 方法 | 说明 |
|------|------|
| `get_context_for_instruction(instruction)` | 获取与指令相关的记忆上下文 |
| `save_task_result(...)` | 保存任务执行结果 |
| `set_preference(key, value, ...)` | 设置用户偏好 |
| `get_preference(key, default)` | 获取用户偏好 |
| `add_file_record(path, operation)` | 添加文件操作记录 |
| `get_recent_files(limit)` | 获取最近文件 |
| `semantic_search(query)` | 语义搜索所有记忆 |
| `find_similar_instructions(instruction)` | 查找相似指令 |
| `discover_workflows()` | 发现工作流模式 |
| `analyze_emotion(text)` | 分析用户情绪 |
| `get_stats()` | 获取记忆系统统计 |
| `export_all_memories()` | 导出所有记忆（备份） |
| `shutdown()` | 关闭并保存状态 |

### 知识图谱

```python
# 添加知识
memory.add_knowledge(
    subject="用户",
    predicate="发送",
    obj="发票.pdf",
    target="张三"
)

# 查询知识
results = memory.query_knowledge(obj="发票", target="张三")
# 返回: [{"subject": "用户", "predicate": "发送", ...}]
```

## 记忆压缩策略

| 时间范围 | 存储形式 |
|---------|---------|
| 24小时内 | 完整对话记录 |
| 7天内 | 每日摘要 |
| 30天内 | 每周摘要 |
| 30天+ | 核心偏好提取 |

## 记忆衰减机制

- **时间衰减**：越久远的记忆权重越低
- **重要性保护**：用户确认的偏好永不删除
- **自动清理**：90天前的低重要性记忆自动清理

## 安装依赖

```bash
pip install chromadb sentence-transformers
```

首次运行时，系统会自动下载嵌入模型（约 400MB）。

## 性能说明

- **SQLite**：毫秒级查询，无额外 token 消耗
- **向量搜索**：本地运行，不消耗 API token
- **嵌入模型**：使用 `paraphrase-multilingual-MiniLM-L12-v2`，支持中英文
- **记忆上下文**：限制在 500 token 以内，不影响主要对话

## 隐私说明

- 所有数据本地存储，不上传任何服务器
- 用户可随时删除 `~/.deskjarvis/` 目录清除所有记忆
- 支持导出备份：`memory.export_all_memories()`
