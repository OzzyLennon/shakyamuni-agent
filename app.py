#!/usr/bin/env python3
"""
释迦牟尼佛 - Flask Web应用
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from shakyamuni_agent import ShakyamuniAgent

app = Flask(__name__)

# 全局Agent实例
agent = ShakyamuniAgent()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """非流式：保留兼容"""
    data = request.json
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "问题不能为空"}), 400

    try:
        result = agent.ask(question)
        return jsonify({
            "answer": result["answer"],
            "emotion": result["emotion"],
            "retrieval": result["retrieval"],
            "sutra_results": result["sutra_results"],
            "web_results": result.get("web_results", [])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """
    流式 SSE。前端 fetch + ReadableStream 消费。
    每个 event 是一行 `data: {json}\\n\\n`。
    """
    data = request.json
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "问题不能为空"}), 400

    def generate():
        try:
            for event in agent.ask_stream(question):
                # SSE 格式：data: <json>\n\n
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            err = {"type": "error", "data": str(e)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
            "Connection": "keep-alive",
        },
    )


@app.route("/api/reset", methods=["POST"])
def reset():
    agent.reset()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("=" * 60)
    print("       释迦牟尼佛 Web服务启动中...")
    print("请访问: http://127.0.0.1:5001")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
