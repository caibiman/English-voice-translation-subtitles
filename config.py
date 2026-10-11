# -*- coding: utf-8 -*-
"""
全局配置文件：视频通话实时中英音频Agent（SenseVoice流式ASR）

依赖安装：
    pip install pyaudio openai funasr
    pip install pyqt6                       # UI版（main_ui.py）需要
    Windows 回环采集推荐：pip install pyaudiowpatch
"""

import os

# ==================== LLM 配置（OpenAI协议兼容：DeepSeek / 通义千问等） ====================
# 推荐用环境变量注入密钥，避免硬编码泄露；也可以直接改这里
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-请填入你的APIKey")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")  # DeepSeek示例
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# ==================== 路由Agent业务规则 ====================
LLM_COOLDOWN_SEC = 1.2      # 全局LLM冷却：两次调用最小间隔（秒），防止高频API调用
MIN_EN_WORD_COUNT = 4       # 英文句子最少单词数，达到才触发LLM
MAX_HISTORY_ROUND = 4       # 对话上下文最多保留最近N轮（一轮 = user + assistant）

# ==================== 音频参数（虚拟环路声卡） ====================
CHUNK = 1600                # 每次读取的帧数（16000Hz下约0.1秒）
FORMAT = "paInt16"          # 16bit PCM
CHANNELS = 1                # 单声道
RATE = 16000                # 采样率16kHz
INPUT_DEVICE_INDEX = "auto_cable"  # auto_cable:优先VB-Cable虚拟声卡(纯数字零处理),无则回退系统回环; auto_loopback:跟随默认播放设备回环; None:系统麦克风; 整数:指定设备索引
#   "auto_loopback" = 自动跟随默认播放设备的回环采集（推荐，直接录对方声音，需 pyaudiowpatch）
#   None            = 系统默认麦克风输入
#   数字            = 指定设备索引（--list-devices 查看，如 10 = 扬声器回环 / 16 = 耳机回环）

# ==================== SenseVoice ASR ====================
SENSEVOICE_MODEL = "iic/SenseVoiceSmall"  # ModelScope模型ID（也可用 FunAudioLLM/SenseVoiceSmall）
DEVICE = "cpu"              # 固定使用CPU版torch（auto / cpu / cuda:0）
USE_ITN = False             # 逆文本正则化（数字/日期规范化）

# ==================== 流式识别参数（VAD切分 + 增量识别模拟流式） ====================
PARTIAL_INTERVAL_SEC = 1.5      # partial预览弹幕刷新间隔（秒），太大刷屏、太小费CPU
SILENCE_ENDPOINT_SEC = 0.45     # 静音判定一句结束（秒），0.45可按句子切分，避免多句合并
SILENCE_RMS_THRESHOLD = 60      # 16bit PCM的RMS能量阈值，低于视为静音（回环为数字信号，静音RMS≈0，可设低些）
MAX_SEGMENT_SEC = 8             # 单段语音最长秒数，超过强制切分（防止多句粘连成一坨）
MIN_SPEECH_SEC = 0.4            # 有效语音最短时长（秒），过滤点击/短噪声，避免垃圾弹幕
AGC_TARGET_RMS = 2500           # AGC目标语音电平（16bit满幅32768），把低电平回环语音归一到此幅度提升识别率
AGC_MAX_GAIN = 16.0             # AGC最大增益（+24dB封顶），防止把静音噪声放大过头
LOG_TO_FILE = True              # 控制台输出同步写入 logs/agent.log（排查问题用）

# ==================== UI（PyQt6悬浮弹幕） ====================
BULLET_ROWS = 5             # 弹幕层数
BULLET_MAX_COUNT = 6        # 同时显示弹幕数量上限
BULLET_SPEED_PX_SEC = 130   # 弹幕横向滚动速度（像素/秒）
