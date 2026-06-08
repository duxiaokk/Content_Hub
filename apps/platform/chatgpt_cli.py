#!/usr/bin/env python3
"""简易 ChatGPT CLI - 直接调用 OpenAI 兼容 API。"""

import argparse
import json
import os
import sys

import httpx

# 强制 UTF-8 输出，避免 Windows 终端乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_API_KEY = "sk-GNrCkGsN2ClLz99POkR5L69g9Cj0F7q1zMsJJuSgRS3IH6cK"
DEFAULT_BASE_URL = "https://api.sbbbbbbbbb.xyz/v1"
DEFAULT_MODEL = "gpt-5.4-openai-compact"


def chat_completion(api_key: str, base_url: str, model: str, messages: list, stream: bool = True):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": 0.7,
    }
    with httpx.Client(timeout=60) as client:
        if not stream:
            resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line == "data: [DONE]":
                    break
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue


def main():
    parser = argparse.ArgumentParser(description="ChatGPT CLI")
    parser.add_argument("prompt", nargs="?", help="单次提问内容")
    parser.add_argument("--api-key", "-k", default=os.getenv("OPENAI_API_KEY", DEFAULT_API_KEY), help="API Key")
    parser.add_argument("--base-url", "-u", default=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL), help="API Base URL")
    parser.add_argument("--model", "-m", default=os.getenv("OPENAI_MODEL", DEFAULT_MODEL), help="模型名称")
    parser.add_argument("--chat", "-c", action="store_true", help="进入交互聊天模式")
    parser.add_argument("--system", "-s", default="You are a helpful assistant.", help="系统提示词")
    args = parser.parse_args()

    if not args.api_key:
        print("错误: 未提供 API Key。请使用 -k 参数指定。")
        sys.exit(1)

    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})

    if args.chat:
        print(f"🤖 ChatGPT CLI")
        print(f"   API: {args.base_url}")
        print(f"   模型: {args.model}")
        print("输入内容开始对话，输入 exit/quit 退出。\n")
        while True:
            try:
                user_input = input("你: ")
            except (EOFError, KeyboardInterrupt):
                print("\n再见!")
                break
            user_input = user_input.strip()
            if user_input.lower() in ("exit", "quit", "q"):
                print("再见!")
                break
            messages.append({"role": "user", "content": user_input})
            print("AI: ", end="", flush=True)
            reply = ""
            for chunk in chat_completion(args.api_key, args.base_url, args.model, messages, stream=True):
                print(chunk, end="", flush=True)
                reply += chunk
            print("\n")
            messages.append({"role": "assistant", "content": reply})
    else:
        if not args.prompt:
            print("错误: 未提供提问内容。请直接传入内容，或使用 --chat 进入交互模式。")
            print(f'示例: python chatgpt_cli.py "你好"')
            sys.exit(1)
        messages.append({"role": "user", "content": args.prompt})
        print("AI: ", end="", flush=True)
        for chunk in chat_completion(args.api_key, args.base_url, args.model, messages, stream=True):
            print(chunk, end="", flush=True)
        print("")


if __name__ == "__main__":
    main()
