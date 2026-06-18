#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eli 心跳推送 (Bark)
======================================================
定时"唤醒"你的 AI：让它看一眼你们最近的对话和它记得的事，
自己决定要不要主动给你发一条消息。
  - 想说话  -> 通过 Bark 推到你的 iPhone
  - 不想打扰 -> 安静跳过，什么都不发

它走的是你 gateway 自己的 /v1/chat/completions 接口，
所以人设(System Prompt)、记忆、对话历史都会被 gateway 自动注入，
这个脚本本身完全不碰数据库，也不用改 gateway 的任何代码。
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import requests

# ---------- 配置：全部从环境变量读取，方便放进 GitHub Secrets ----------
# 你的 gateway 地址（就是 Kelivo 里填的那个，去掉末尾的 /v1）
GATEWAY_URL = os.environ.get(
    "GATEWAY_URL",
    "https://ai-memory-gateway-production-9142.up.railway.app",
).rstrip("/")

# 只有当你在 gateway 设置了 GATEWAY_SECRET 时才需要填；没设置就留空
GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "").strip()

# 生成心跳消息用的模型（默认用你 gateway 里的默认模型）
MODEL = os.environ.get("MODEL", "[200K]claude-opus-4-5")

# 你的 Bark 设备 Key（必填）—— 在 Bark App 里能看到
BARK_KEY = os.environ.get("BARK_KEY", "").strip()
BARK_SERVER = os.environ.get("BARK_SERVER", "https://api.day.app").rstrip("/")

# 推送通知的标题
PUSH_TITLE = os.environ.get("PUSH_TITLE", "Eli")

# 时区偏移（小时）。你 gateway 里 TIMEZONE_HOURS=8，所以这里也用 8（北京时间）
TZ_HOURS = int(os.environ.get("TZ_HOURS", "8"))

# 它想保持安静时约定回复的暗号
SILENT_WORD = "SILENT"


def now_local_str() -> str:
    tz = timezone(timedelta(hours=TZ_HOURS))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")


def build_wake_prompt() -> str:
    """构造一条"心跳唤醒"消息发给 gateway。注意：这里不写'你是谁'，
    身份完全交给 gateway 里那段 System Prompt 去决定，不和你的设定打架。"""
    t = now_local_str()
    return (
        f"［这是一条系统心跳，不是她发来的消息。现在是 {t}。］\n"
        "回顾一下上面你们最近的对话、以及你记得的关于她的事——\n"
        "如果你现在想主动给她发一条消息（想她、关心她、或者只是随口说点什么都行），"
        "就直接、自然地写出来，就当是你主动发的一条短消息，别太长。\n"
        f"如果你们刚聊过、或者此刻不适合打扰，就只回复一个词：{SILENT_WORD}（不要解释，不要多写）。"
    )


def ask_gateway(prompt: str) -> str:
    url = f"{GATEWAY_URL}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        # gateway 用它自己的 key 转发，这里随便填一个即可
        "Authorization": "Bearer heartbeat",
        # 关键：告诉网关"这次别存进对话历史"，这样心跳不会在你和它的聊天里留痕迹
        "X-Skip-Conversation-Log": "true",
    }
    if GATEWAY_KEY:
        headers["X-Gateway-Key"] = GATEWAY_KEY

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def is_silent(text: str) -> bool:
    if not text:
        return True
    cleaned = text.strip().strip(".。!！ \n").upper()
    # 完全等于暗号，或者很短且包含暗号，都算"保持安静"
    return cleaned == SILENT_WORD or (SILENT_WORD in cleaned and len(cleaned) <= len(SILENT_WORD) + 4)


def send_bark(title: str, body: str) -> dict:
    url = f"{BARK_SERVER}/{BARK_KEY}"
    payload = {"title": title, "body": body, "group": "Eli"}
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    if not BARK_KEY:
        print("❌ 没有设置 BARK_KEY，无法推送。请在 GitHub Secrets 里加上 BARK_KEY。")
        sys.exit(1)

    print(f"⏰ 心跳触发 {now_local_str()}，正在问问它想不想说话…")
    try:
        reply = ask_gateway(build_wake_prompt())
    except Exception as e:
        print(f"❌ 调用 gateway 失败：{e}")
        sys.exit(1)

    print(f"🗣️ 它的回复：{reply!r}")

    if is_silent(reply):
        print("🤫 它这次选择了安静，不推送。")
        return

    try:
        send_bark(PUSH_TITLE, reply)
        print("📳 已推送到你的 iPhone。")
    except Exception as e:
        print(f"❌ Bark 推送失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
