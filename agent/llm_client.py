# -*- coding: utf-8 -*-
"""LLM客户端：OpenAI协议兼容请求、prompt管理、正则解析返回结果、对话上下文管理

依赖：pip install openai
"""

import re

from openai import OpenAI

import config
from agent.utils import build_history_text

# ==================== 全局状态：对话历史 ====================
# 结构：[{"role":"user","text":"对方英文"},{"role":"assistant","text":"推荐回复"}]
dialog_history = []

# LLM客户端（OpenAI协议兼容，DeepSeek/通义千问均可）
_client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)

# 系统提示词：角色是视频通话助手，输出严格固定两行格式
SYSTEM_PROMPT = (
    "你是视频通话实时翻译助手。对方正在说英文，你需要帮用户实时看懂并快速回复。"
    "请结合对话上下文，严格按以下两行格式输出，不要输出任何其他内容：\n"
    "【中文弹幕】简短口语化的中文翻译，适合悬浮弹幕展示\n"
    "【推荐英文回复】仅1条简短口语化的英文回复，贴合对话上下文"
)

# 正则：提取【中文弹幕】与【推荐英文回复】内容
_ZH_RE = re.compile(r"【中文弹幕】\s*(.+)")
_REPLY_RE = re.compile(r"【推荐英文回复】\s*(.+)")


def call_llm_generate(en_text: str, history_list: list):
    """请求LLM生成翻译+推荐回复，正则解析后返回 (中文弹幕, 推荐英文回复)

    输出格式异常时返回 (None, None)，由路由Agent按规则跳过。
    """
    if not config.LLM_API_KEY or "请填入" in config.LLM_API_KEY:
        raise RuntimeError("未配置LLM_API_KEY，请在config.py或环境变量中设置")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history_list:
        messages.append({
            "role": "system",
            "content": "对话上下文（最近几轮）：\n" + build_history_text(history_list),
        })
    messages.append({"role": "user", "content": f"对方英文句子：{en_text}"})

    resp = _client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=200,
        timeout=15,
    )
    content = resp.choices[0].message.content or ""

    zh_m = _ZH_RE.search(content)
    reply_m = _REPLY_RE.search(content)
    zh = zh_m.group(1).strip() if zh_m else None
    reply = reply_m.group(1).strip() if reply_m else None
    return zh, reply


def append_history(en_text: str, reply: str):
    """追加一轮对话历史，最多保留最近 MAX_HISTORY_ROUND 轮，防止上下文过长"""
    dialog_history.append({"role": "user", "text": en_text})
    dialog_history.append({"role": "assistant", "text": reply})
    max_items = config.MAX_HISTORY_ROUND * 2
    while len(dialog_history) > max_items:
        dialog_history.pop(0)
