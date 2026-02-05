# 贡献指南

感谢你考虑为 DeskJarvis 做贡献！这份文档将帮助你了解如何参与项目开发。

## 开始之前

1. 阅读 [README.md](README.md) 了解项目概况
2. 阅读 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 了解技术架构
3. 阅读 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) 了解开发规范

## 如何贡献

### 🐛 报告 Bug

1. 搜索 [Issues](https://github.com/jinwandalaohu940-netizen/DeskJarvis/issues) 确保问题未被报告
2. 使用 Bug 报告模板创建新 Issue
3. 提供详细信息：
   - 操作系统和版本
   - Python/Node.js 版本
   - 完整的错误日志
   - 复现步骤

### 💡 提交功能建议

1. 创建 Issue 描述你的想法
2. 说明使用场景和预期效果
3. 等待讨论和确认后再开始开发

### 🔧 提交代码

#### 1. Fork 并克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/DeskJarvis.git
cd DeskJarvis
```

#### 2. 创建功能分支

```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

#### 3. 安装开发依赖

```bash
# Python 依赖
pip install -r requirements.txt

# Node.js 依赖
npm install

# Playwright 浏览器
playwright install chromium
```

#### 4. 开发和测试

```bash
# 运行 Python 测试
pytest tests/

# 运行前端开发服务器
npm run dev

# 运行 Tauri 开发模式
npm run tauri:dev
```

#### 5. 提交更改

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```bash
git commit -m "feat: 添加新功能"
git commit -m "fix: 修复某个问题"
git commit -m "docs: 更新文档"
git commit -m "style: 代码格式调整"
git commit -m "refactor: 重构代码"
git commit -m "test: 添加测试"
```

#### 6. 推送并创建 Pull Request

```bash
git push origin feature/your-feature-name
```

然后在 GitHub 上创建 Pull Request。

## 代码规范

### Python

- 遵循 PEP 8
- 使用类型提示（Type Hints）
- 使用 Google 风格 docstring
- 使用 `logging` 模块记录日志

```python
def process_file(file_path: str, options: dict) -> bool:
    """处理文件。
    
    Args:
        file_path: 文件路径
        options: 处理选项
        
    Returns:
        处理是否成功
    """
    pass
```

### TypeScript

- 启用严格模式
- 使用函数式组件 + Hooks
- 为所有函数添加类型注解

```typescript
interface Props {
  title: string;
  onClick: () => void;
}

const Button: React.FC<Props> = ({ title, onClick }) => {
  return <button onClick={onClick}>{title}</button>;
};
```

### Git 提交

- 每次提交只做一件事
- 提交信息使用中文或英文（保持一致）
- 提交前运行测试

## 项目结构

```
DeskJarvis/
├── agent/           # Python Agent 核心
│   ├── planner/     # AI 规划器
│   ├── executor/    # 执行器（浏览器、文件、系统）
│   ├── memory/      # 记忆系统
│   └── tools/       # 工具函数
├── src/             # React 前端
│   ├── components/  # UI 组件
│   └── utils/       # 工具函数
├── src-tauri/       # Tauri Rust 后端
├── docs/            # 文档
└── tests/           # 测试
```

## 需要帮助？

- 在 Issues 中提问
- 查看 [文档](docs/)

感谢你的贡献！🎉
