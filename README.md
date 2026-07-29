# 释迦牟尼佛 Agent

以释迦牟尼佛身份，基于佛经教法的 AI 对话系统。

## 特性

- **人格框架**：SKILL.md 定义释迦牟尼佛的身份、说法风格、核心教义
- **佛经检索**：基于 buddha-cli 查询 CBETA 大藏经、巴利文 Tipitaka 等
- **佛陀风格**：偈颂、呵斥、赞许、问答机锋
- **历史会话**：类似 ChatGPT 的多会话管理

## 安装

### 1. 克隆仓库

```bash
git clone <repo-url>
cd shakyamuni-agent
```

### 2. 安装依赖

```bash
pip install flask requests zhconv
```

### 3. 安装 buddha-cli

buddha-cli 是佛经检索工具，需要单独安装：

```bash
# 需要 Rust 环境
git clone https://github.com/sinryo/buddha-cli.git
cd buddha-cli
cargo build --release
cargo install --path .

# 初始化
buddha init
```

### 4. 配置 API Key

复制配置文件：

```bash
cp config.py.example config.py
# 编辑 config.py，填入你的 API Key
```

> **依赖说明**: `zhconv` 用于 cbeta 检索的简繁转换 (cbeta XML 全文繁体, 简体输入会自动转 "菩萨" -> "菩薩")

### 5. 启动

```bash
python app.py
```

访问 http://127.0.0.1:5001

## 命令行使用

```bash
python chat.py
```

## 项目结构

```
shakyamuni-agent/
├── SKILL.md                 # 释迦牟尼人格框架 (skill 触发词/能力)
├── AGENTS.md                # 项目导览 (架构/buddha-cli/M2.7 集成/已知问题)
├── app.py                   # Flask Web 服务 (3 个路由)
├── chat.py                  # 命令行对话模式 (CLI 单轮)
├── shakyamuni_agent.py     # 核心 Agent (含 5 步关键词 + 简繁转换)
├── config.py.example       # 配置文件模板
├── templates/
│   └── index.html         # Web 前端 (米色禅意风 + 字体切换 + 历史 panel)
├── static/
│   └── agent_logo.png     # 1024x1024 圆 logo
├── kill_flask.ps1          # 一键杀 Flask 进程
└── README.md
```

## API 配置

使用 **MiniMax** 推理模型:

- LLM: `MiniMax-M2.7` (reasoning model, 输出 <think> 块)
- endpoint: `https://api.minimaxi.com/v1/text/chatcompletion_v2`
- max_tokens: 2000 (reasoning 要预留预算)
- 配置文件: `config.py` (在 .gitignore, 见 config.py.example 模板)

## 佛经数据来源

- CBETA 中文大藏经
- Tipitaka 巴利文五部
- GRETIL 梵文文献
- SARIT 梵文校勘本
- 藏文大藏经

## 免责声明

本项目仅供学习和研究使用。释迦牟尼如的回答基于佛经教法推断，不代表历史真实。
