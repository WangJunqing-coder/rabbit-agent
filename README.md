# 🐇 Rabbit Agent

一个轻量级本地 AI  Agent，仅用几千行代码就实现了类似Hermes Agent、Claude Code等Agent的大部分功能，支持 CLI 和 TUI 两种交互模式。

## ✨ 特性

- 🤖 **多 LLM 支持** — DeepSeek / OpenAI / Ollama / Anthropic
- 🔧 **25+ 工具** — 文件操作、终端执行、Git、网页、搜索等
- 💬 **流式输出** — 实时显示思考过程、工具调用、执行结果
- 🧠 **记忆系统** — 跨会话记忆用户偏好和项目知识
- 📦 **插件/技能** — 可扩展的技能系统
- 🖥️ **双模式** — CLI 命令行 + TUI 交互界面
- 📊 **上下文管理** — 可视化 token 用量和上下文窗口占用

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置

创建 `config.yaml`：

```yaml
llm:
  provider: deepseek          # ollama / openai / deepseek / anthropic
  model: deepseek-chat        # 模型名称
  api_key: your-api-key       # API 密钥
  api_base: https://api.deepseek.com/v1
  max_tokens: 4096
  temperature: 0.7

agent:
  max_iterations: 100         # 最大迭代轮次
  max_context_messages: 50    # 上下文消息数

ui:
  language: zh
```

或使用环境变量：

```bash
export LITE_AGENT_PROVIDER=deepseek
export LITE_AGENT_MODEL=deepseek-chat
export LITE_AGENT_API_KEY=your-key
```

### 运行

```bash
# TUI 模式（推荐）
python main.py --tui

# CLI 模式
python main.py

# 单次查询
python main.py -c "帮我查看项目结构"

# 指定配置
python main.py --tui --config config.yaml

# 指定模型
python main.py --tui --provider ollama --model gemma4:latest
```

## 🎯 使用示例

```
rabbit> 帮我写一个 Python 爬虫，抓取豆瓣电影 Top250

  🔄 Iteration 1/100
  💭 Thinking:
    我来创建一个爬虫脚本...
  🏷 TOOL write_file
    Args: {"path": "douban_spider.py", "content": "..."}
    ⏳ Running...
  ✓ Done

  📊 Tokens: 1234 in + 567 out = 1801 total
```

## 📋 命令

| 命令         | 说明          |
| ---------- | ----------- |
| `/help`    | 显示帮助        |
| `/tools`   | 列出所有工具      |
| `/skills`  | 列出已加载技能     |
| `/memory`  | 查看记忆统计      |
| `/config`  | 显示当前配置      |
| `/status`  | 显示状态栏       |
| `/history` | 查看对话历史      |
| `/session` | 切换会话（方向键选择） |
| `/delete`  | 删除会话（方向键选择） |
| `/new`     | 新建会话        |
| `/save`    | 保存当前会话      |
| `/clear`   | 清屏          |
| `/quit`    | 退出          |

## 🔧 内置工具

| 工具               | 说明           |
| ---------------- | ------------ |
| `terminal`       | 执行终端命令       |
| `read_file`      | 读取文件内容       |
| `write_file`     | 创建/覆盖写入文件    |
| `edit_file`      | 精确编辑文件（查找替换） |
| `search_files`   | 搜索文件内容（grep） |
| `find_files`     | 查找文件（glob）   |
| `list_directory` | 列出目录内容       |
| `batch_edit`     | 批量编辑多个文件     |
| `git_status`     | 查看 Git 状态    |
| `git_diff`       | 查看文件差异       |
| `git_commit`     | 提交变更         |
| `git_push`       | 推送到远程        |
| `git_pull`       | 拉取更新         |
| `git_branch`     | 分支操作         |
| `web_fetch`      | 获取网页内容       |
| `web_search`     | 搜索网页         |
| `delegate_task`  | 委派任务给子 Agent |

## 🏗️ 项目结构

```
LiteAgent/
├── main.py              # 入口文件
├── config.py            # 配置管理
├── cli.py               # CLI 模式（Rich 美化）
├── tui.py               # TUI 模式（prompt_toolkit）
├── agent/
│   ├── core.py          # Agent 核心逻辑
│   └── llm.py           # LLM 接口层
├── tools/
│   ├── registry.py      # 工具注册中心
│   ├── terminal.py      # 终端执行
│   ├── file_ops.py      # 文件操作
│   ├── search.py        # 搜索工具
│   ├── git_ops.py       # Git 操作
│   ├── web.py           # 网页工具
│   ├── browser.py       # 浏览器控制
│   └── sub_agent.py     # 子 Agent 委派
├── memory/
│   ├── store.py         # 记忆存储
│   └── tools.py         # 记忆工具
├── sessions/
│   └── __init__.py      # 会话管理
├── plugins/
│   └── manager.py       # 插件管理
├── context/
│   └── __init__.py      # 项目上下文感知
└── skills/              # 技能目录
```

## ⚙️ 支持的 LLM Provider

| Provider    | 模型示例                                             |
| ----------- | ------------------------------------------------ |
| `ollama`    | gemma4:latest, qwen3:4b, llama3                  |
| `openai`    | gpt-4o, gpt-4o-mini                              |
| `deepseek`  | deepseek-chat, deepseek-coder, deepseek-v4-flash |
| `anthropic` | claude-3-5-sonnet, claude-3-opus                 |

## 📄 License

MIT
