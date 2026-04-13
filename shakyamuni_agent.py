#!/usr/bin/env python3
"""
释迦摩尼 Agent - 基于 buddha-cli 佛经检索
结合释迦摩尼 SKILL.md 人格框架
"""

import sys
import re
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import SILICONFLOW_API_KEY, LLM_URL, WEB_SEARCH_ENABLED, WEB_SEARCH_TOP_K

# ============ API调用 ============
def call_llm(messages, model="Pro/deepseek-ai/DeepSeek-V3.2"):
    import requests
    headers = {"Authorization": f"Bearer {SILICONFLOW_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.7}
    response = requests.post(LLM_URL, headers=headers, json=payload, timeout=300)
    if response.status_code != 200:
        raise Exception(f"LLM API error: {response.status_code}")
    result = response.json()
    return result["choices"][0]["message"]["content"]

# ============ Buddha-CLI 调用 ============
def call_buddha(args):
    """
    调用 buddha-cli 获取佛经原文
    args: list of strings, e.g. ["cbeta-search", "--query", "阿弥陀佛", "--max-results", "5"]
    """
    # 假设 buddha 安装在 PATH 中
    cmd = ["buddha"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
        else:
            print(f"[buddha-cli error] {result.stderr.decode('utf-8', errors='replace')}", file=sys.stderr)
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
        return []

    try:
        data = json.loads(output)
        results = []
        result_items = data.get("result", {}).get("results", [])
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
                    results.append(f"《{title}》第{line}行：{clean_context}")
        return results
    except (json.JSONDecodeError, KeyError):
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
    使用网络搜索补充最新信息
    """
    if not WEB_SEARCH_ENABLED:
        return []

    try:
        from mcp__MiniMax__web_search import web_search as mini_max_search
        result = mini_max_search(query)

        if not result or "organic" not in result:
            return []

        results = []
        for item in result["organic"][:top_k]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
                "date": item.get("date", "")
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
def analyze_question(question: str) -> dict:
    """
    分析问题类型和检索需求
    """
    q = question.lower()

    # 检测现代话题（需要联网搜索）
    modern_keywords = ["ai", "人工智能", "互联网", "电脑", "手机", "网络", "元宇宙",
                      "区块链", "chatgpt", "现代", "当今", "今年", "去年", "明年",
                      "科技", "技术", "算法", "程序员", "互联网", "新冠", "疫情"]
    is_modern = any(kw in q for kw in modern_keywords)

    # 佛教话题但非具体经文
    is_buddhist_topic = any(kw in q for kw in ["佛教", "佛", "修行", "解脱", "轮回", "因果"])

    # 是否涉及具体经文
    sutra_names = ["金刚经", "心经", "法华经", "华严经", "阿弥陀经", "地藏经",
                   "楞严经", "楞伽经", "四谛", "八正道", "缘起", "无常", "无我", "涅槃"]
    has_sutra_name = any(name in question for name in sutra_names)

    return {
        "is_modern": is_modern,
        "is_buddhist_topic": is_buddhist_topic,
        "has_sutra_name": has_sutra_name,
        "needs_web_search": is_modern or (is_buddhist_topic and not has_sutra_name)
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

    # 检测是否涉及具体佛经名
    sutra_names = ["金刚经", "心经", "法华经", "华严经", "阿弥陀经", "地藏经",
                   "楞严经", "楞伽经", "四谛", "八正道", "缘起", "无常", "无我", "涅槃"]
    has_sutra_name = any(name in q for name in sutra_names)

    # 检测问题类型
    is_factual = any(kw in q for kw in ["哪一部", "哪篇", "哪个", "何处", "何经", "何人"])
    is_explanation = any(kw in q for kw in ["是什么", "何意", "为何", "为何", "解释"])
    is_practice = any(kw in q for kw in ["如何修", "怎么念", "怎样", "修行", "念佛"])

    if is_factual:
        strategy = "search"
        corpus = "cbeta"
    elif has_sutra_name:
        strategy = "fetch"
        corpus = "cbeta"
    elif is_practice:
        strategy = "search"
        corpus = "cbeta"
    else:
        strategy = "search"
        corpus = "cbeta"

    return {
        "strategy": strategy,
        "corpus": corpus,
        "has_sutra_name": has_sutra_name
    }

# ============ 核心 Agent ============
class ShakyamuniAgent:
    """
    释迦摩尼 Agent

    整合 SKILL.md 人格 + buddha-cli 检索
    """

    def __init__(self):
        self.conversation_history = []
        self.disclaimer_given = False
        self.short_term_memory = []

    def ask(self, question: str) -> dict:
        sys.stdout.reconfigure(encoding='utf-8')

        # 1. 情感检测
        emotion = detect_emotional_context(question)

        # 2. 问题分析
        question_analysis = analyze_question(question)

        # 3. 检索策略
        retrieval = determine_retrieval_strategy(question)

        # 4. 佛经检索
        sutra_results = []
        if retrieval["strategy"] == "search":
            sutra_results = search_sutra(question, max_results=5, corpus=retrieval["corpus"])

        # 5. 联网检索（如果需要）
        web_results = []
        if question_analysis.get("needs_web_search"):
            print(f"[联网检索] 检测到现代话题，正在搜索...")
            web_results = web_search(question)
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

        return {
            "answer": answer,
            "emotion": emotion,
            "question_analysis": question_analysis,
            "retrieval": retrieval,
            "sutra_results": sutra_results,
            "web_results": web_results
        }

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
        return f"""你以太梵牟尼佛的身份回答问题。

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

        # 佛经检索结果
        sutra_note = ""
        if sutra_results:
            sutra_note = "\n【相关佛经原文】：\n" + "\n".join(sutra_results[:5])
        else:
            sutra_note = "\n【佛经检索】未找到直接相关原文，请以教法回应。"

        # 联网检索结果
        web_note = ""
        if web_results:
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

请以太梵牟尼佛的口吻回答。若有佛经原文，当以"如经中所说"或"在《某某经》中"的方式引用。
如问法者有苦难，当先予安慰。对于联网搜索的现实信息，可结合佛教教义进行点评。"""

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
