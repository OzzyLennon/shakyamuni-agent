# 释迦牟尼如Agent

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
pip install flask requests
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

### 5. 启动

```bash
python app.py
```

访问 http://127.0.0.1:5000

## 命令行使用

```bash
python chat.py
```

## 项目结构

```
shakyamuni-agent/
├── SKILL.md                 # 释迦牟尼人格框架
├── app.py                   # Flask Web 服务
├── chat.py                  # 命令行对话模式
├── shakyamuni_agent.py     # 核心 Agent
├── config.py.example       # 配置文件模板
├── templates/
│   └── index.html         # Web 前端
└── README.md
```

## API 配置

使用 [硅基流动](https://siliconflow.cn/) API：

- LLM: `Pro/deepseek-ai/DeepSeek-V3.2`

## 佛经数据来源

- CBETA 中文大藏经
- Tipitaka 巴利文五部
- GRETIL 梵文文献
- SARIT 梵文校勘本
- 藏文大藏经

## 免责声明

本项目仅供学习和研究使用。释迦牟尼如的回答基于佛经教法推断，不代表历史真实。
