# -*- coding: utf-8 -*-
"""工具函数：英文单词计数、对话历史文本拼接"""

import re

# 英文单词正则：连续英文字母（允许撇号连接，如 don't）
_EN_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
# 中文字符正则
_ZH_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def count_english_words(text: str) -> int:
    """统计文本中的英文单词数量（正则提取英文字母单词）"""
    return len(_EN_WORD_RE.findall(text or ""))


def count_chinese_chars(text: str) -> int:
    """统计文本中的中文字符数量"""
    return len(_ZH_CHAR_RE.findall(text or ""))


def is_english_dominated(text: str, min_words: int = 5) -> bool:
    """判断文本是否以英文为主（用于混合语种句子纠偏）

    ASR对中英混杂句只给一个语种标签，可能把英文为主的句子标成zh；
    当英文单词数达标且英文多于中文时，视为英文句子（可触发LLM翻译）。
    """
    en_words = count_english_words(text)
    zh_chars = count_chinese_chars(text)
    return en_words >= min_words and en_words > zh_chars


def build_history_text(history_list: list) -> str:
    """将对话历史拼接成文本，作为上下文传给LLM

    history结构：[{"role":"user","text":"对方英文"},{"role":"assistant","text":"推荐回复"}]
    """
    lines = []
    for item in history_list or []:
        who = "对方" if item.get("role") == "user" else "我方"
        lines.append(f"{who}: {item.get('text', '')}")
    return "\n".join(lines)
