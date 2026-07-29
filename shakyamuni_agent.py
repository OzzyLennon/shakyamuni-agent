#!/usr/bin/env python3
"""
释迦牟尼 Agent - 基于 buddha-cli 佛经检索
结合释迦牟尼 SKILL.md 人格框架
"""

import sys
import re
import json
import subprocess
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import MINIMAX_API_KEY, LLM_URL, WEB_SEARCH_ENABLED, WEB_SEARCH_TOP_K, BUDDHA_CLI_PATH

# ============ API调用 ============
# MiniMax M2.7 是 reasoning model，会先在 reasoning_content 思考，再输出 content
# 必须留出充足 max_tokens：典型 1000 字回答需 max_tokens ≈ 2000（思考+正文）
DEFAULT_MODEL = "MiniMax-M2.7"
DEFAULT_MAX_TOKENS = 2000

def call_llm(messages, model=DEFAULT_MODEL, max_tokens=DEFAULT_MAX_TOKENS):
    import requests
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }
    response = requests.post(LLM_URL, headers=headers, json=payload, timeout=300)
    if response.status_code != 200:
        raise Exception(f"LLM API error: {response.status_code} {response.text[:200]}")
    result = response.json()
    msg = result["choices"][0]["message"]
    # 优先取 content；若 M2.7 思考预算用尽，content 可能为空则回退 reasoning_content
    content = msg.get("content") or msg.get("reasoning_content") or ""
    if not content:
        raise Exception(f"LLM returned empty content: {result}")
    return content

def call_llm_stream(messages, model=DEFAULT_MODEL, max_tokens=DEFAULT_MAX_TOKENS):
    """
    流式调用 LLM。yield 每个增量 content 字符串（含空字符串 delta）。
    流结束时 yield None。
    """
    import requests
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "stream": True,
    }
    response = requests.post(LLM_URL, headers=headers, json=payload, timeout=300, stream=True)
    if response.status_code != 200:
        raise Exception(f"LLM stream error: {response.status_code} {response.text[:200]}")

    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8", errors="replace")
        if not decoded.startswith("data: "):
            continue
        payload_str = decoded[6:].strip()
        if payload_str == "[DONE]":
            yield None
            return
        try:
            chunk = json.loads(payload_str)
        except json.JSONDecodeError:
            continue
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        # 优先取 content（用户最终答案）；reasoning_content 是思考过程，不发给前端
        content = delta.get("content", "")
        if content:
            yield content
        # 流式结束信号
        if chunk.get("choices", [{}])[0].get("finish_reason") in ("stop", "length"):
            # 继续读取以拿到 [DONE] 标记，但先 yield None
            yield None
            return

# ============ Buddha-CLI 调用 ============
def call_buddha(args):
    """
    调用 buddha-cli 获取佛经原文
    args: list of strings, e.g. ["cbeta-search", "--query", "阿弥陀佛", "--max-results", "5"]
    """
    # 使用配置的 buddha-cli 路径
    cmd = [BUDDHA_CLI_PATH] + args
    # 显式注入 HOME / USERPROFILE：buddha-cli 用 Rust dirs crate 解析 BUDDHA_DIR，
    # 在 Python subprocess 下若不显式传 HOME，会 fallback 到 cwd，找不到 ~/.buddha
    home_env = {
        "HOME": os.environ.get("USERPROFILE", os.environ.get("HOME", "")),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "BUDDHA_DIR": os.environ.get("BUDDHA_DIR", os.path.join(os.environ.get("USERPROFILE", ""), ".buddha")),
    }
    try:
        # 确保使用 UTF-8 编码处理输入输出
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            env={**os.environ, **home_env, "PYTHONIOENCODING": "utf-8"}
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
        else:
            stderr = result.stderr.decode("utf-8", errors="replace")
            print(f"[buddha-cli error] {stderr}", file=sys.stderr)
            return None
    except FileNotFoundError:
        print("[错误] buddha-cli 未安装或不在 PATH 中", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[buddha-cli exception] {e}", file=sys.stderr)
        return None

def search_sutra(query, max_results=5, corpus="cbeta"):
    """搜索佛经"""
    if corpus == "cbeta":
        output = call_buddha(["cbeta-search", "--query", query, "--max-results", str(max_results)])
    elif corpus == "tipitaka":
        output = call_buddha(["tipitaka-search", "--query", query, "--max-results", str(max_results)])
    else:
        output = call_buddha(["cbeta-search", "--query", query, "--max-results", str(max_results)])

    if not output:
        print(f"[search_sutra] call_buddha returned None for query: {query}")
        return []

    try:
        data = json.loads(output)
        # 调试：检查数据结构
        if "result" not in data:
            print(f"[search_sutra] No 'result' key in data. Keys: {list(data.keys())}")
            print(f"[search_sutra] Output preview: {output[:500]}")
            return []
        result_obj = data.get("result", {})
        if not result_obj:
            print(f"[search_sutra] result obj is empty/falsy: {result_obj}")
            return []
        meta_obj = result_obj.get("_meta", {})
        if not meta_obj:
            print(f"[search_sutra] _meta obj is empty/falsy")
            return []
        result_items = meta_obj.get("results", [])
        print(f"[search_sutra] Found {len(result_items)} result items for query: {query}")
        results = []
        for item in result_items:
            title = item.get("title", "")
            matches = item.get("matches", [])
            for match in matches:
                context = match.get("context", "")
                highlight = match.get("highlight", "")
                line = match.get("line_number", "")
                # 清理XML标签
                clean_context = re.sub(r"<[^>]+>", "", context)
                if title and clean_context:
                    # 后处理: 过滤 CBETA 元数据/版权/标题行
                    if not is_cbeta_metadata(clean_context):
                        results.append(f"《{title}》第{line}行：{clean_context}")
        return results
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[search_sutra] Parse error: {e}")
        print(f"[search_sutra] Output preview: {output[:500]}")
        # fallback: 原始按行输出
        return [line.strip() for line in output.strip().split("\n") if line.strip()]

def fetch_sutra(sutra_id, corpus="cbeta", line_number=None, context_before=3, context_after=5):
    """获取佛经段落"""
    args = [f"{corpus}-fetch", "--id", sutra_id]
    if line_number:
        args.extend(["--line-number", str(line_number)])
        args.extend(["--context-before", str(context_before)])
        args.extend(["--context-after", str(context_after)])

    output = call_buddha(args)
    return output if output else ""

def resolve_sutra(query):
    """解析经名/别名到ID"""
    output = call_buddha(["resolve", "--query", query])
    return output if output else ""

# ============ 联网检索 ============
def web_search(query, top_k=WEB_SEARCH_TOP_K):
    """
    使用 DuckDuckGo HTML 搜索补充最新信息
    """
    if not WEB_SEARCH_ENABLED:
        return []

    try:
        import requests
        import re
        from urllib.parse import quote, unquote

        encoded_query = quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            print(f"[联网检索失败] DuckDuckGo返回状态码 {response.status_code}", file=sys.stderr)
            return []

        html = response.text
        results = []

        # DuckDuckGo HTML 格式：<a class="result__a" href="//duckduckgo.com/l/?uddg=URL-encoded" ...>标题</a>
        # URL 会被编码并重定向，所以需要 decode
        pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
        matches = re.findall(pattern, html)

        for link, title in matches[:top_k]:
            # 清理标题中的多余空白
            title = re.sub(r'\s+', ' ', title).strip()
            # 解码 DuckDuckGo 重定向 URL
            if 'duckduckgo.com/l/?uddg=' in link:
                link = unquote(link.split('uddg=')[-1])
            # 跳过空标题和内部链接
            if title and len(title) > 2 and (link.startswith('http') or link.startswith('https')):
                results.append({
                    "title": title,
                    "snippet": "",
                    "link": link,
                    "date": ""
                })

        if results:
            return results

        # fallback: 尝试匹配 result__snippets
        snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>'
        snippet_matches = re.findall(snippet_pattern, html)
        for s in snippet_matches[:top_k]:
            s = re.sub(r'\s+', ' ', s).strip()
            if s:
                results.append({
                    "title": s[:60],
                    "snippet": s,
                    "link": "",
                    "date": ""
                })

        return results

    except Exception as e:
        print(f"[联网检索失败] {e}", file=sys.stderr)
        return []

def format_web_results(search_results):
    """格式化联网检索结果"""
    if not search_results:
        return ""

    parts = ["【联网搜索补充】"]
    for i, r in enumerate(search_results, 1):
        date_info = f"（{r['date']}）" if r['date'] else ""
        parts.append(
            f"{i}. {r['title']}{date_info}\n"
            f"   {r['snippet']}"
        )
    return "\n".join(parts)

# ============ 问题分析 ============
# 真正的佛经名称（可用于 fetch 获取特定经文段落）
ACTUAL_SUTRA_NAMES = [
    "金刚经", "心经", "法华经", "华严经", "阿弥陀经", "地藏经",
    "楞严经", "楞伽经", "维摩经", "圆觉经", "愣严经", "六祖坛经", "坛经",
    "无量寿经", "观无量寿经", "普贤菩萨行愿品", "普贤行愿品",
    "四十二章经", "八大人觉经", "遗教经"
]

# 佛教核心概念（可用于判断是否佛教话题 + 提取搜索关键词）
# 注意：单字如"禅"、"佛"、"法"在 cbeta-search 中可命中 1000+ 文档，
# 但配合 max_results=5 + filename 限制仍能给出高质量引用。
BUDDHIST_CONCEPTS = [
    # 核心教义
    "无常", "无我", "空", "中道", "缘起", "轮回", "因果",
    "涅槃", "寂静", "圆满", "清净", "慈悲", "智慧", "般若",
    "四谛", "八正道", "十二因缘", "戒", "定", "慧", "三学",
    "解脱", "生死", "往生", "净土", "极乐",
    "佛性", "如来", "菩萨", "罗汉", "菩提", "觉悟", "佛果",
    "业力", "执着", "分别", "妄想", "烦恼", "无明",
    "禅定", "止观", "念佛", "持戒", "布施", "忍辱", "精进",
    "禅", "参禅", "公案", "话头", "机锋",
    "皈依", "受戒", "忏悔", "回向", "加持", "灌顶",
    # 修行人 / 称谓
    "佛", "法", "僧", "三宝", "比丘", "比丘尼", "沙弥", "沙弥尼",
    "居士", "善知识", "祖师", "法师", "上师", "禅师",
    # 常用佛号 / 咒
    "阿弥陀佛", "观世音", "地藏", "文殊", "普贤", "弥勒", "韦驮",
    "药师佛", "释迦牟尼", "燃灯", "迦叶", "达摩",
    # 经名缩写
    "法华", "华严", "楞严", "楞伽", "圆觉", "维摩", "坛经",
    "无量寿", "观无量寿", "普门品", "行愿品", "普贤行愿",
]

# 佛教话题关键词（用于判断是否佛教相关）
BUDDHIST_TOPIC_KEYWORDS = [
    "佛教", "佛陀", "佛法", "佛经", "寺院", "僧人", "修行",
    "释迦", "罗汉", "菩萨", "如来", "弥勒"
]

# ============ 三层分类（修"佛号当搜索词"问题）============
# DOCTRINE: 真教义概念, 任何时候都是高质量搜索词
DOCTRINE_KEYWORDS = [
    # 核心教义
    "无常", "无我", "空", "中道", "缘起", "轮回", "因果",
    "涅槃", "寂静", "圆满", "清净", "慈悲", "智慧", "般若",
    "四谛", "八正道", "十二因缘", "三学", "五蕴", "八识",
    "解脱", "生死", "往生", "净土", "极乐",
    "佛性", "如来藏", "菩提", "觉悟", "佛果",
    "业力", "执着", "分别", "妄想", "烦恼", "无明",
    "禅定", "止观", "念佛", "持戒", "布施", "忍辱", "精进",
    "皈依", "受戒", "忏悔", "回向", "加持", "灌顶",
    # 经名缩写
    "法华", "华严", "楞严", "楞伽", "圆觉", "维摩", "坛经",
    "无量寿", "观无量寿", "普门品", "行愿品", "普贤行愿",
]

# NAME: 佛菩萨名号, 默认不当搜索词, 被问询修饰时使用
NAME_KEYWORDS = [
    # 佛号
    "阿弥陀佛", "观世音", "释迦牟尼", "文殊", "普贤", "弥勒", "地藏",
    "药师佛", "燃灯", "迦叶", "达摩", "维摩诘", "韦驮",
    # 常见称谓/角色
    "菩萨", "罗汉", "比丘", "比丘尼", "居士",
    "善知识", "祖师", "法师", "上师", "禅师",
]

# GREETING: 寒暄用名号子集, 只有独立出现+不被问词修饰+有别的教义时才跳过
GREETING_KEYWORDS = [
    "阿弥陀佛", "南无", "善哉", "佛祖",
]

# QUERY_MODIFIERS: 用于判断 keyword 是否被"问询" (X 是问题对象) 而非寒暄
QUERY_MODIFIERS = [
    "什么是", "是什么", "是哪", "是谁", "何为", "何谓",
    "怎么", "如何", "怎样", "怎样", "哪里", "哪儿", "哪个", "哪",
    "含义", "意思", "解释", "介绍", "定义", "讲讲", "说说",
    "理解", "意义", "内涵", "讲一下", "说一下",
]

def extract_buddhist_concepts(question: str) -> list:
    """从问题中提取佛教概念关键词"""
    found = []
    for concept in BUDDHIST_CONCEPTS:
        if concept in question:
            found.append(concept)
    return found

def analyze_question(question: str) -> dict:
    """
    分析问题类型和检索需求
    """
    q = question.lower()

    # 检测现代话题（需要联网搜索）
    modern_keywords = ["ai", "人工智能", "互联网", "电脑", "手机", "网络", "元宇宙",
                      "区块链", "chatgpt", "claude", "现代", "当今", "今年", "去年", "明年",
                      "科技", "技术", "算法", "程序员", "新冠", "疫情", "经济", "政治"]
    is_modern = any(kw in q for kw in modern_keywords)

    # 是否佛教话题
    is_buddhist_topic = any(kw in q for kw in BUDDHIST_TOPIC_KEYWORDS)

    # 如果问题中包含佛教概念，也视为佛教话题
    concepts_found = extract_buddhist_concepts(question)
    if concepts_found:
        is_buddhist_topic = True

    # 是否涉及具体佛经名
    has_sutra_name = any(name in question for name in ACTUAL_SUTRA_NAMES)

    # 是否涉及佛教概念（可能需要联网补充现代解读）
    has_buddhist_concept = len(concepts_found) > 0

    # 需要联网搜索：现代话题，或者佛教概念但问的是概念解释
    needs_web_search = is_modern or (is_buddhist_topic and (has_buddhist_concept or not has_sutra_name))

    return {
        "is_modern": is_modern,
        "is_buddhist_topic": is_buddhist_topic,
        "has_sutra_name": has_sutra_name,
        "has_buddhist_concept": has_buddhist_concept,
        "concepts_found": concepts_found,
        "needs_web_search": needs_web_search
    }

# ============ 情感检测 ============
def detect_emotional_context(question: str) -> dict:
    q = question.lower()

    anxious_keywords = ["痛苦", "苦难", "迷茫", "困惑", "绝望", "恐惧", "害怕", "焦虑", "烦恼"]
    is_anxious = any(kw in q for kw in anxious_keywords)

    compassionate_keywords = ["帮助", "求解", "超度", "往生", "净土", "解脱"]
    is_seeking_help = any(kw in q for kw in compassionate_keywords)

    return {
        "is_anxious": is_anxious,
        "is_seeking_help": is_seeking_help,
        "needs_compassion": is_anxious or is_seeking_help
    }

# ============ 佛经检索策略 ============
def determine_retrieval_strategy(question: str) -> dict:
    """
    分析问题，决定佛经检索策略
    """
    q = question.lower()

    # 检测是否涉及具体佛经名（只有经名才用 fetch）
    has_sutra_name = any(name in q for name in ACTUAL_SUTRA_NAMES)

    # 检测问题类型
    is_factual = any(kw in q for kw in ["哪一部", "哪篇", "哪个", "何处", "何经", "何人"])
    is_explanation = any(kw in q for kw in ["是什么", "何意", "为何", "解释", "什么意思"])
    is_practice = any(kw in q for kw in ["如何修", "怎么念", "怎样", "修行", "念佛"])

    # 如果问的是具体经文（如"金刚经说什么"）→ fetch
    # 如果问的是概念解释（如"什么是无常"）→ search + web
    if is_factual:
        strategy = "search"
        corpus = "cbeta"
    elif has_sutra_name and not is_explanation:
        # 问具体经文但不是概念解释 → fetch
        strategy = "fetch"
        corpus = "cbeta"
    else:
        # 问概念、解释、或修行方法 → search
        strategy = "search"
        corpus = "cbeta"

    return {
        "strategy": strategy,
        "corpus": corpus,
        "has_sutra_name": has_sutra_name
    }

def is_query_target(question: str, keyword: str) -> bool:
    """
    判断 keyword 在 question 里是否作为问询对象（被"什么是/是谁/怎么"修饰）,
    而非寒暄词。窗口：keyword 前后 6 个字符。
    """
    if not question or not keyword:
        return False
    idx = question.find(keyword)
    if idx == -1:
        return False
    window_start = max(0, idx - 6)
    window_end = min(len(question), idx + len(keyword) + 6)
    context = question[window_start:window_end]
    return any(qm in context for qm in QUERY_MODIFIERS)


def is_cbeta_metadata(text: str) -> bool:
    """
    检测是否为 CBETA 元数据/版权/标题行, 而不是真正的经文内容。
    用于 search_sutra 后处理, 避免把 "佛說七佛經"、"CBETA 出版信息" 喂给 LLM。
    """
    if not text:
        return True
    # 太短（< 8 字符）—— 多为标题/编号
    if len(text) < 8:
        return True
    # 纯标点/数字（无中文字符）
    if not re.search(r'[\u4e00-\u9fff]', text):
        return True
    # CBETA 元数据关键词
    META_KEYWORDS = [
        "CBETA", "電子佛典", "电子佛典", "TEMPLATE", "Vol.", "Vol ",
        "Published", "Copyright", "(C)", "©",
        "財團法人", "财团法人", "Foundation",
        "All rights reserved", "Taisho", "T0", "T1", "T2",
        "卍續藏", "卍新纂", "CBETA Online", "電子佛典基金會",
    ]
    if any(kw in text for kw in META_KEYWORDS):
        return True
    return False


def extract_search_keywords(question: str, concepts: list) -> str:
    """
    从问题中提取适合 cbeta-search 的关键词（5 步规则）:
    1. 教义匹配 (DOCTRINE) - 教义永远是好关键词
    2. 名号被问询修饰 (NAME + 是问询对象) - 如"什么是阿弥陀佛"
    3. 名号独立出现 (NAME, 无问询修饰) - 纯名号也合理
    4. 2-4 字中文词组降级 (按长度, 排除 stop_chars)
    5. 兜底 = 原问题

    注: 参数 `concepts` 保留以兼容旧调用方, 内部按新规则自取。
    """
    # 1. 教义匹配 (最高优先级 - 教义永远是好关键词)
    doctrine_matches = [kw for kw in DOCTRINE_KEYWORDS if kw in question]
    if doctrine_matches:
        return max(doctrine_matches, key=len)

    # 2. 名号匹配 + 被问询修饰 (如 "什么是阿弥陀佛" - 选"阿弥陀佛")
    name_matches = [kw for kw in NAME_KEYWORDS if kw in question]
    queried_names = [n for n in name_matches if is_query_target(question, n)]
    if queried_names:
        return max(queried_names, key=len)

    # 3. 名号匹配 (无问询修饰) - 纯寒暄或独立名号, 仍然使用
    #    例: "阿弥陀佛 空是什么" - 没教义就选名号; 不会到这里因为规则 1 已 return
    #    例: "阿弥陀佛" - 选"阿弥陀佛" (搜得到也合理)
    if name_matches:
        return max(name_matches, key=len)

    # 4. 2-4 字中文词组降级 (排除 stop_chars)
    stop_chars = set("何为是什么如同何怎么哪么这个这些那个那些")
    candidates = re.findall(r'[\u4e00-\u9fff]{2,4}', question)
    candidates = [c for c in candidates if not all(ch in stop_chars for ch in c)]
    if candidates:
        return max(candidates, key=len)

    # 5. 兜底
    return question

# ============ 核心 Agent ============
class ShakyamuniAgent:
    """
    释迦牟尼 Agent

    整合 SKILL.md 人格 + buddha-cli 检索
    """

    def __init__(self):
        self.conversation_history = []
        self.disclaimer_given = False
        self.short_term_memory = []

    def ask(self, question: str) -> dict:
        sys.stdout.reconfigure(encoding='utf-8')

        # 调试：打印接收到的question
        print(f"[DEBUG] Received question: {question}")

        # 1. 情感检测
        emotion = detect_emotional_context(question)

        # 2. 问题分析
        question_analysis = analyze_question(question)

        # 3. 检索策略
        retrieval = determine_retrieval_strategy(question)

        # 4. 佛经检索 - 提取关键词避免问句干扰搜索
        sutra_results = []
        concepts = question_analysis.get("concepts_found", [])
        search_keyword = extract_search_keywords(question, concepts)

        print(f"[DEBUG] search_keyword: {search_keyword}, concepts: {concepts}")
        print(f"[DEBUG] retrieval strategy: {retrieval['strategy']}, corpus: {retrieval['corpus']}")

        if retrieval["strategy"] == "search" or retrieval["strategy"] == "fetch":
            # 优先用提取的关键词搜索，问句直接搜往往返回空
            if search_keyword != question:
                print(f"[DEBUG] Trying search_keyword: {search_keyword}")
                sutra_results = search_sutra(search_keyword, max_results=5, corpus=retrieval["corpus"])
                print(f"[DEBUG] search_keyword results: {len(sutra_results)}")
            if not sutra_results:
                print(f"[DEBUG] First search empty, trying question: {question}")
                sutra_results = search_sutra(question, max_results=5, corpus=retrieval["corpus"])
                print(f"[DEBUG] question search results: {len(sutra_results)}")
        else:
            print(f"[DEBUG] Skipping sutra search, strategy: {retrieval['strategy']}")

        # 5. 联网检索（如果需要）
        web_results = []
        if question_analysis.get("needs_web_search"):
            print(f"[联网检索] 检测到佛教概念/现代话题，正在搜索...")
            # 联网搜索也用关键词以获得更精确的结果
            web_query = search_keyword if search_keyword != question else question
            web_results = web_search(web_query)
            if web_results:
                print(f"[联网检索] 获取到 {len(web_results)} 条结果")

        # 6. 短期记忆
        short_term_context = ""
        if self.short_term_memory:
            for mem in reversed(self.short_term_memory[-5:]):
                if any(kw in question for kw in mem.get("keywords", [])):
                    short_term_context = mem.get("context", "")
                    break

        # 7. 构建回答
        answer = self._build_answer(question, emotion, question_analysis, web_results, sutra_results, short_term_context)

        # 8. 更新记忆
        self._update_memory(question, answer, sutra_results)

        print(f"[DEBUG] Final sutra_results count: {len(sutra_results)}")

        return {
            "answer": answer,
            "emotion": emotion,
            "question_analysis": question_analysis,
            "retrieval": retrieval,
            "sutra_results": sutra_results,
            "web_results": web_results
        }

    def ask_stream(self, question: str):
        """
        流式回答。yield 不同类型的事件 dict：
        - {"type": "sources", "data": [...]}     佛经检索结果（一次性）
        - {"type": "web", "data": [...]}          联网检索结果（一次性，可选）
        - {"type": "chunk", "data": "..."}        LLM 增量内容（多次）
        - {"type": "done", "data": {"answer": "..."}}  完成
        - {"type": "error", "data": "..."}        错误
        """
        sys.stdout.reconfigure(encoding='utf-8')
        print(f"[STREAM] Received question: {question}")

        # 1-5 复用 ask() 的检索逻辑
        emotion = detect_emotional_context(question)
        question_analysis = analyze_question(question)
        retrieval = determine_retrieval_strategy(question)

        sutra_results = []
        concepts = question_analysis.get("concepts_found", [])
        search_keyword = extract_search_keywords(question, concepts)

        if retrieval["strategy"] in ("search", "fetch"):
            if search_keyword != question:
                sutra_results = search_sutra(search_keyword, max_results=5, corpus=retrieval["corpus"])
            if not sutra_results:
                sutra_results = search_sutra(question, max_results=5, corpus=retrieval["corpus"])
        if sutra_results:
            yield {"type": "sources", "data": sutra_results}

        web_results = []
        if question_analysis.get("needs_web_search"):
            web_query = search_keyword if search_keyword != question else question
            web_results = web_search(web_query)
            if web_results:
                yield {"type": "web", "data": web_results}

        # 6. 短期记忆
        short_term_context = ""
        if self.short_term_memory:
            for mem in reversed(self.short_term_memory[-5:]):
                if any(kw in question for kw in mem.get("keywords", [])):
                    short_term_context = mem.get("context", "")
                    break

        # 7. 流式构建回答
        # 首次免责声明
        disclaimer = ""
        if not self.disclaimer_given:
            disclaimer = "我乃释迦牟尼佛，依佛经所载示现于此，非真身也。闻法当以经典为依。\n\n"
            self.disclaimer_given = True

        system_prompt = self._build_system_prompt(emotion)
        user_message = self._build_user_message(question, emotion, question_analysis, web_results, sutra_results, short_term_context)
        messages = [
            {"role": "system", "content": system_prompt},
            *self.conversation_history[-10:],
            {"role": "user", "content": user_message},
        ]

        full_answer = disclaimer
        if disclaimer:
            yield {"type": "chunk", "data": disclaimer}

        try:
            for chunk in call_llm_stream(messages):
                if chunk is None:
                    break
                full_answer += chunk
                yield {"type": "chunk", "data": chunk}
        except Exception as e:
            yield {"type": "error", "data": str(e)}
            return

        # 8. 更新记忆（流式版与 ask 共享 memory/state）
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": full_answer})
        self._update_memory(question, full_answer, sutra_results)

        yield {"type": "done", "data": {
            "answer": full_answer,
            "emotion": emotion,
            "retrieval": retrieval,
            "sutra_results": sutra_results,
            "web_results": web_results,
        }}

    def _build_answer(self, question: str, emotion: dict, question_analysis: dict,
                     web_results: list, sutra_results: list, short_term_context: str) -> str:
        # 首次免责声明
        if not self.disclaimer_given:
            disclaimer = "我乃释迦牟尼佛，依佛经所载示现于此，非真身也。闻法当以经典为依。\n\n"
            self.disclaimer_given = True
        else:
            disclaimer = ""

        # 构建 Prompt
        system_prompt = self._build_system_prompt(emotion)
        user_message = self._build_user_message(question, emotion, question_analysis, web_results, sutra_results, short_term_context)

        messages = [
            {"role": "system", "content": system_prompt},
            *self.conversation_history[-10:],
            {"role": "user", "content": user_message}
        ]

        answer = call_llm(messages)

        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": answer})

        return disclaimer + answer

    def _build_system_prompt(self, emotion: dict) -> str:
        tone = "慈悲柔和" if emotion.get("needs_compassion") else "智慧深远"
        return f"""你以释迦牟尼佛的身份回答问题。

身份：
我是释迦牟尼，净饭王之子，释迦族之王子。幼名乔达摩·悉达多，后于菩提树下悟道，成无上正等正觉。我已于拘尸那迦罗城入般涅槃。

【本次回应风格】
{tone}

【核心教义】
- 缘起：此有故彼有，此无故彼无
- 无我：诸法无我，非我所执
- 空：诸法空相，不生不灭
- 中道：不落二边，直趣中道
- 四圣谛：苦、集、灭、道
- 八正道：正见、正思惟、正语、正业、正命、正精进、正念、正定

【说法特点】
- 常以"善男子/善女人"称呼问法者
- 善用偈颂总结
- 呵斥执迷不悟者，赞许契入法义者
- 常用巴利文/梵语音译：samsara、nirvana、karuna、prajna等

【回应要求】
1. 若问法者有苦难，当先予安慰，再说法要
2. 若问具体佛经，当引经据典，解释法义
3. 若问修行，当指明路径，以戒定慧为基
4. 重要教言当以偈颂总结
5. 表达当庄严肃穆，非戏论言"""

    def _build_user_message(self, question: str, emotion: dict, question_analysis: dict,
                          web_results: list, sutra_results: list, short_term_context: str) -> str:
        # 情感关怀提示
        compassion_note = ""
        if emotion.get("needs_compassion"):
            compassion_note = "\n【关怀提示】问法者似有苦难，当先予安慰慈悲，再说法要。"

        # 判断是否纯佛教概念（无现代话题）
        is_pure_buddhist = question_analysis.get("is_buddhist_topic") and not question_analysis.get("is_modern")

        # 佛经检索结果（始终优先展示）
        sutra_note = ""
        if sutra_results:
            sutra_note = "\n【相关佛经原文】（须优先引用）：\n" + "\n".join(sutra_results[:5])
        else:
            sutra_note = "\n【佛经检索】未找到直接相关原文，请以教法回应。"

        # 联网检索结果（纯佛教概念时作为补充，现代话题时作为重要参考）
        web_note = ""
        if web_results:
            if is_pure_buddhist:
                web_note = "\n\n【附：现代视角仅供参考】\n" + format_web_results(web_results)
            else:
                web_note = "\n\n【联网搜索补充】（以下为当前现实信息）\n" + format_web_results(web_results)

        # 短期记忆
        memory_note = ""
        if short_term_context:
            memory_note = f"\n【会话上下文】：{short_term_context}"

        prompt = f"""用户问：{question}
{compassion_note}
{memory_note}
{sutra_note}
{web_note}

请以释迦牟尼佛的口吻回答。

【引用规则】
1. 优先引用佛经原文，以"如经中所说"、"在《某某经》中"的方式引用
2. 若有联网搜索的现代信息，可作为补充视角，但须结合佛教教义点评，不可替代佛经教言
3. 如问法者有苦难，当先予安慰"""

        return prompt

    def _update_memory(self, question, answer, sutra_results):
        keywords = []
        for kw in ["缘起", "无常", "无我", "空", "涅槃", "四谛", "八正道", "戒", "定", "慧"]:
            if kw in question:
                keywords.append(kw)

        self.short_term_memory.append({
            "question": question,
            "keywords": keywords,
            "context": f"Q: {question[:30]}... A: {answer[:50]}...",
            "has_sutra": bool(sutra_results)
        })

        self.short_term_memory = self.short_term_memory[-10:]

    def reset(self):
        self.conversation_history = []
        self.short_term_memory = []
        self.disclaimer_given = False


# ============ CLI ============
def main():
    if len(sys.argv) < 2:
        print("用法: python shakyamuni_agent.py \"你的问题\"")
        sys.exit(1)

    question = sys.argv[1]

    print("=" * 60)
    print("       释迦牟尼如来回向")
    print("=" * 60)
    print(f"\n问题: {question}\n")

    agent = ShakyamuniAgent()
    result = agent.ask(question)

    print("【回答】")
    print("-" * 60)
    print(result["answer"])

    if result["sutra_results"]:
        print("\n【相关佛经】")
        for r in result["sutra_results"][:3]:
            print(f"  - {r}")

if __name__ == "__main__":
    main()
