# 🤖 DeskJarvis - AI 桌面智能助手

<p align="center">
  <img src="src-tauri/icons/icon.png" alt="DeskJarvis Logo" width="128" height="128">
</p>

<p align="center">
  <strong>用自然语言控制电脑，让 AI 成为你的私人助理</strong>
</p>

<p align="center">
  <a href="#-功能特性">功能特性</a> •
  <a href="#-快速开始">快速开始</a> •
  <a href="#-技术架构">技术架构</a> •
  <a href="#-开发文档">开发文档</a>
</p>

---

## ✨ 功能特性

### 🎯 核心功能
- **自然语言交互** - 像聊天一样控制电脑，无需学习命令
- **智能任务规划** - AI 自动分解复杂任务，逐步执行
- **自我反思修正** - 执行失败自动分析原因，调整方案重试
- **安全沙盒执行** - 所有操作限制在指定目录，保护你的数据

### 🛠️ 支持的操作

| 类别 | 功能 |
|------|------|
| 📁 文件管理 | 创建、删除、重命名、移动、搜索、整理文件 |
| 🌐 浏览器自动化 | 打开网页、搜索、点击、填写表单、下载文件 |
| 📸 桌面截图 | 截取桌面截图并保存 |
| 📊 数据可视化 | 自动生成图表（饼图、柱状图、折线图等） |
| 🔊 系统控制 | 音量调节、通知发送、剪贴板操作 |
| 📝 文本处理 | AI 翻译、总结、润色、纠错 |
| 🖼️ 图片处理 | 压缩、调整大小、格式转换 |
| ⏰ 定时任务 | 设置提醒和定时执行 |
| 📋 任务历史 | 查看历史记录，收藏常用任务 |

### 🧠 智能特性
- **增强版代码解释器** - AI 可以编写并执行 Python 代码
- **自动安装依赖** - 缺少的 Python 包自动安装
- **智能错误修复** - 语法错误自动修正，失败自动重试
- **长期记忆系统** - 记住你的偏好、习惯和历史操作
- **上下文理解** - 理解"这张图片"、"刚才的文件"等指代

## 🚀 快速开始

### 环境要求
- **macOS** 12.0+ / **Windows** 10+ / **Linux**
- **Node.js** 18+
- **Python** 3.11+
- **Rust** (用于 Tauri 编译)

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/YOUR_USERNAME/DeskJarvis.git
cd DeskJarvis

# 2. 安装前端依赖
npm install

# 3. 安装 Python 依赖
pip install -r requirements.txt
playwright install chromium

# 4. 启动开发模式
npm run tauri:dev
```

### 配置 API Key

首次启动后，点击左下角 ⚙️ 设置图标，配置你的 AI API：

| 提供商 | 推荐模型 | 说明 |
|--------|----------|------|
| Claude | claude-3-5-sonnet | 最智能，推荐 |
| DeepSeek | deepseek-chat | 性价比高，中文好 |
| OpenAI | gpt-4o | 稳定可靠 |

## 📸 界面预览

```
┌─────────────────────────────────────────────────────────────────┐
│  ☰  DeskJarvis                                            ⚙️   │
├─────┬───────────────────────────────────────────┬───────────────┤
│     │                                           │  任务进度      │
│ 聊  │  你: 统计桌面文件，画个饼图                  │               │
│ 天  │                                           │  ✅ 统计文件   │
│ 记  │  AI: 好的，我来帮你统计并生成图表...         │  ✅ 生成图表   │
│ 录  │      [图表已保存到桌面]                     │               │
│     │                                           │  执行日志      │
│     │                                           │  [SUCCESS]    │
├─────┴───────────────────────────────────────────┴───────────────┤
│  📎  输入你的指令...                                      发送   │
└─────────────────────────────────────────────────────────────────┘
```

## 🏗️ 技术架构

```
DeskJarvis/
├── src/                    # React 前端 (TypeScript)
│   ├── components/         # UI 组件
│   ├── utils/              # 工具函数
│   └── types/              # 类型定义
├── src-tauri/              # Tauri 后端 (Rust)
│   └── src/main.rs         # Rust 入口
├── agent/                  # Python AI Agent
│   ├── planner/            # AI 规划器 (Claude/DeepSeek/OpenAI)
│   ├── executor/           # 执行器 (浏览器/文件/系统)
│   ├── memory/             # 记忆系统 (SQLite + ChromaDB)
│   └── main.py             # Agent 入口
└── docs/                   # 开发文档
```

### 技术栈
- **前端**: React + TypeScript + Tailwind CSS + Framer Motion
- **桌面框架**: Tauri (Rust)
- **AI Agent**: Python + LangGraph
- **浏览器自动化**: Playwright
- **记忆系统**: SQLite + ChromaDB (向量数据库)

## 📚 开发文档

| 文档 | 说明 |
|------|------|
| [架构设计](docs/ARCHITECTURE.md) | 整体架构和模块设计 |
| [开发规范](docs/DEVELOPMENT.md) | 代码规范和开发流程 |
| [AI 工作流](docs/AI_WORKFLOW.md) | AI 辅助开发指南 |
| [技术决策](docs/DECISIONS.md) | 重要技术决策记录 |
| [多代理系统](docs/MULTI_AGENT.md) | 多 Agent 协作设计 |

## 🤝 贡献指南

欢迎贡献代码、提交 Issue 或改进文档！

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

## 📜 开源协议

本项目采用 [GPLv3](LICENSE) 协议开源。

## 🙏 致谢

- [Tauri](https://tauri.app/) - 轻量级桌面应用框架
- [Anthropic Claude](https://www.anthropic.com/) - 强大的 AI 模型
- [Playwright](https://playwright.dev/) - 浏览器自动化
- [ChromaDB](https://www.trychroma.com/) - 向量数据库

---

<p align="center">
  Made with ❤️ by 今晚打老虎🐯
</p>
