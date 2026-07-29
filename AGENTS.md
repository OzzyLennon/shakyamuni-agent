# shakyamuni-agent 导览

> **一句话**: Flask + LLM (MiniMax M2.7) + buddha-cli 佛经检索, 对话式佛学 Agent, SSE 流式输出, 米色禅意风 Web UI。

## 架构

```
┌──────────────────────────────────────────────────────────┐
│ 浏览器                                                     │
│  templates/index.html (米色禅意风, 字体切换, 历史 panel)         │
└──────────────┬───────────────────────────────────────────┘
               │ fetch + ReadableStream
               ▼
┌──────────────────────────────────────────────────────────┐
│ Flask app.py                                              │
│  ├─ GET  /                  → 渲染 index.html               │
│  ├─ POST /api/chat          → 一次性 (兼容)                │
│  └─ GET  /api/chat/stream   → SSE 流式 (主路径)            │
└──────────────┬───────────────────────────────────────────┘
               │ yield content chunks
               ▼
┌──────────────────────────────────────────────────────────┐
│ ShakyamuniAgent (shakyamuni_agent.py)                    │
│  ├─ ask_stream(user_msg) → generator                     │
│  │   ├─ extract_search_keywords() (4 级降级)              │
│  │   ├─ call_buddha(keywords)    → 5 条 CBETA 经文片段     │
│  │   ├─ call_llm_stream(prompt)  → MiniMax M2.7 流式     │
│  │   └─ stripToneDescriptions()   → 清标点 + 控速          │
│  └─ WEB_SEARCH_ENABLED = False (DuckDuckGo 限流)          │
└──────────┬──────────────────┬────────────────────────────┘
           │ subprocess       │ HTTP POST
           ▼                  ▼
   buddha.exe           api.minimaxi.com
   (Rust, 4995 XML)     /v1/text/chatcompletion_v2
```

## 关键文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `shakyamuni_agent.py` | ~860 | 核心 Agent 类, 所有业务逻辑都在这 |
| `app.py` | ~70 | Flask 入口, 3 个路由 |
| `templates/index.html` | ~1600 | 前端 (含手写 markdown 渲染, 字体切换, 历史 panel) |
| `static/agent_logo.png` | 786KB | 1024×1024 圆 logo |
| `config.py` | ~30 | **API key 在这, 已 gitignore** |
| `config.py.example` | ~15 | 模板, 提交进仓 |
| `chat.py` | ~60 | CLI 模式, 单轮新建 Agent (跟 app.py 单 instance 不一致, 已知) |
| `kill_flask.ps1` | ~10 | 一键杀 Flask 进程 (5001 端口) |
| `SKILL.md` | ~140 | skill 元数据 (触发词/能力/示例) |

## 关键 bug 历史 (避免重踩)

### 1. `call_buddha()` 必须显式传 HOME env
buddha-cli 用 Rust `dirs` crate 找 `~/.buddha`, 但 Windows 下 Python subprocess
默认不传 `HOME`, 导致 `buddha.exe` 找不到索引。**修法**: 在 `subprocess.run` 时
`env={**os.environ, 'HOME': user_home}`, `user_home` 用 `Path.home().as_posix()`。

### 2. cbeta 索引会"损坏"
4995 个 XML 索引文件偶尔会 corrupt。**修法**: `buddha.exe cbeta-index` 重建,
输出在 `C:\Users\PC\.buddha\cache\cbeta-index.json`。5005 个文件, 约 30 秒。

### 3. 假模型名 `Pro/deepseek-ai/DeepSeek-V3.2`
硅基流动早就不存在这个 endpoint, 调用必失败。**修法**: 换 `deepseek-ai/DeepSeek-V3`
或直接用 MiniMax M2.7。**已切 MiniMax**, 别再换回 deepseek 除非用户明确要求。

### 4. markdown 渲染破坏 block
`stripToneDescriptions()` 用 `.replace(/\s+/g, ' ')` 把 `\n\n` 合并掉, 导致 markdown
的 block 边界丢失。**修法**: `[ \t]+ → ' '` + `[ \t]+\n → \n` (保留换行, 只压
连续空格/制表符)。

### 5. 端口 5000 → 5001
5000 容易被 macOS AirPlay 占用, 全栈统一 5001 (README, kill_flask.ps1, app.py)。

## 跑起来

```powershell
cd D:\workspace\.claude\skills\shyakyamuni-agent  # 注意: 真实目录名少一个 'aky'
python app.py
# 浏览器: http://127.0.0.1:5001

# 杀进程
.\kill_flask.ps1
```

> ⚠️ **Mavis 平台 30 分钟硬限**: 后台 Flask 进程跑 30 分钟会被平台回收。
> 长期跑需要 Windows Service / nssm / Task Scheduler, 不要再依赖后台 bash。

## LLM 集成细节

- **endpoint**: `https://api.minimaxi.com/v1/text/chatcompletion_v2`
- **model**: `MiniMax-M2.7` (reasoning model, 会输出 `<think>...</think>`)
- **流式取内容**: `delta.content` 优先, `reasoning_content` 兜底
- **max_tokens**: 2000 (reasoning 要预算)
- **key**: `config.py` 里的 `MINIMAX_API_KEY`, **别 commit 这个文件**

## 已知小毛病 (没改, 后续可优化)

- 前几条经文引用经常是 CBETA 文件头/版权信息, 不是真正经文内容 (要后处理过滤)
- `ACTUAL_SUTRA_NAMES` 列表太短, 新经名搜不到 (BUDDHIST_CONCEPTS 30+ 词已扩)
- `chat.py` CLI 模式每轮新建 ShakyamuniAgent, 跟 app.py 单 instance 不一致
- `/favicon.ico` 404 (浏览器噪音, 不影响 UI, 懒得加)
- DuckDuckGo HTML 限流, 已默认关闭, 保留函数入口 (要开改 `WEB_SEARCH_ENABLED = True`)
- `app.py` 用 `debug=False, threaded=True` (debug=True 会让 reloader 干扰 SSE stream)

## 改代码 checklist

1. 改 `shakyamuni_agent.py` → 重启 Flask (新进程才生效, `kill_flask.ps1` + `python app.py`)
2. 改 `templates/index.html` → 用户浏览器强刷 (`Ctrl+Shift+R`), 已加 `cache-control` meta
3. 改完记得 `git status` 确认没漏, 再 commit
4. `.buddha/` / `.claude/` / `*.bak` 已在 .gitignore, 不会被 commit
