#!/usr/bin/env python3
"""
释迦牟尼如Agent - 交互式对话模式
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from shakyamuni_agent import ShakyamuniAgent

def print_welcome():
    print("=" * 60)
    print("       释迦牟尼如Agent")
    print("=" * 60)
    print()
    print("我乃释迦牟尼佛。有什么问题，尽管来问。")
    print("（输入 'quit' 或 '退出' 结束对话）")
    print("（输入 'reset' 或 '重置' 清空对话历史）")
    print("（输入 'help' 或 '帮助' 查看更多命令）")
    print()
    print("-" * 60)

def print_help():
    print("""
可用命令：
  quit / 退出    - 结束对话
  reset / 重置    - 清空对话历史
  help / 帮助    - 显示此帮助信息
""")

def main():
    agent = ShakyamuniAgent()

    print_welcome()

    while True:
        try:
            user_input = input("\n你: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "退出", "q", "exit"]:
                print("\n阿弥陀佛！愿众生早得解脱！\n")
                break

            if user_input.lower() in ["reset", "重置"]:
                agent.reset()
                print("\n[对话历史已清空]\n")
                continue

            if user_input.lower() in ["help", "帮助", "h"]:
                print_help()
                continue

            print("\n思惟中...\n")

            result = agent.ask(user_input)

            print(f"\n释迦牟尼如: ")
            print("-" * 40)
            print(result["answer"])

            if result["sutra_results"]:
                print("\n【相关佛经】")
                for r in result["sutra_results"][:3]:
                    print(f"  - {r}")

        except KeyboardInterrupt:
            print("\n\n阿弥陀佛！愿众生早得解脱！\n")
            break
        except Exception as e:
            print(f"\n[错误] {e}\n")

if __name__ == "__main__":
    main()
