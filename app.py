#!/usr/bin/env python3
"""
释迦牟尼如Agent - Flask Web应用
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, request, jsonify
from shakyamuni_agent import ShakyamuniAgent

app = Flask(__name__)

# 全局Agent实例
agent = ShakyamuniAgent()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
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
            "sutra_results": result["sutra_results"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/reset", methods=["POST"])
def reset():
    agent.reset()
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    print("=" * 60)
    print("       释迦牟尼如Agent Web服务启动中...")
    print("请访问: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
