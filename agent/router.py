# -*- coding: utf-8 -*-
"""路由Agent核心逻辑：接收ASR分段结果，按规则分流

规则：
- is_final=False（partial 中间结果）：仅预览弹幕，禁止调用LLM
- is_final=True 且 lang==en：单词数>=MIN_EN_WORD_COUNT 且 距上次LLM>=LLM_COOLDOWN_SEC 才调LLM
- is_final=True 且 lang==zh：只输出中文弹幕，禁止调用LLM
- 其他语种：丢弃
"""

import time

import config
from agent.utils import count_english_words, is_english_dominated
from agent.llm_client import call_llm_generate, append_history, dialog_history

# 全局状态：上次LLM调用时间戳（冷却控制）
last_llm_call_ts = 0.0


def _route_english(text: str):
    """英文路由：单词数达标 + 冷却结束 才调用LLM，返回结构化结果"""
    global last_llm_call_ts

    word_count = count_english_words(text)
    now = time.time()
    if word_count < config.MIN_EN_WORD_COUNT:
        return {"action": "skip", "text": text,
                "reason": f"单词不足（{word_count} < {config.MIN_EN_WORD_COUNT}）"}
    if now - last_llm_call_ts < config.LLM_COOLDOWN_SEC:
        return {"action": "skip", "text": text,
                "reason": f"冷却未到（距上次{now - last_llm_call_ts:.1f}s）"}

    last_llm_call_ts = now  # 无论成败都更新冷却时间，防止高频重试打爆API
    try:
        zh, reply = call_llm_generate(text, dialog_history)
    except Exception as e:
        return {"action": "skip", "text": text, "reason": f"LLM调用失败：{e}"}
    if not zh or not reply:
        return {"action": "skip", "text": text, "reason": "LLM返回格式异常"}

    append_history(text, reply)  # 保存本轮对话上下文
    return {"action": "en_final", "text": text, "zh": zh, "reply": reply}


def route_asr_segment(seg: dict):
    """路由Agent核心逻辑：处理ASR分段，返回结构化结果或None（丢弃）

    seg结构：{"text": str, "lang": str, "is_final": bool}
    返回：
      {"action": "preview",  "text":..., "lang":...}                       # partial预览弹幕
      {"action": "zh_final", "text":...}                                   # 中文正式弹幕
      {"action": "en_final", "text":..., "zh":..., "reply":...}            # 英文命中LLM
      {"action": "skip",     "text":..., "reason":...}                     # 跳过LLM（含原因）
      None                                                                 # 丢弃（其他语种/空文本）
    """
    global last_llm_call_ts

    text = (seg.get("text") or "").strip()
    lang = (seg.get("lang") or "").lower()
    is_final = bool(seg.get("is_final"))
    if not text:
        return None

    # partial 中间识别结果：仅预览弹幕，禁止调用LLM
    if not is_final:
        return {"action": "preview", "text": text, "lang": lang}

    # 中文：只输出中文弹幕，禁止调用LLM
    # 混合语种纠偏：ASR标成zh但内容以英文为主的中英混杂句，按英文处理（可触发LLM翻译）
    if lang == "zh":
        if is_english_dominated(text):
            return _route_english(text)
        return {"action": "zh_final", "text": text}

    # 英文：单词数达标 + 冷却结束 才调用LLM
    if lang == "en":
        return _route_english(text)

    # 其他语种：丢弃
    return None
