# -*- coding: utf-8 -*-
"""
程序入口（控制台版）：虚拟声卡音频采集 + SenseVoice流式ASR + 路由Agent + 控制台输出

依赖安装：
    pip install pyaudio openai funasr
    Windows 虚拟声卡/扬声器回环采集推荐：pip install pyaudiowpatch（代码自动优先使用）

启动命令：
    python main.py --list-devices   # 查看输入设备索引，找虚拟声卡（CABLE Output / 立体声混音等）
    python main.py                  # 控制台版运行
"""

import os
import re
import sys

import numpy as np

try:
    import pyaudiowpatch as pyaudio  # Windows WASAPI回环采集增强版
except ImportError:
    import pyaudio

import config
from scipy.signal import resample_poly

from agent.router import route_asr_segment

# SenseVoice 富文本标签：语种标记与所有 <|...|> 标签
_LANG_TAG_RE = re.compile(r"<\|(zh|yue|en|ja|ko|nospeech)\|>")
_TAG_RE = re.compile(r"<\|[^|]*\|>")

# 模块级重采样器实例（单音频流场景，随源采样率变化自动重建）
_RESAMPLER = None


class _PolyResampler:
    """带状态的抗混叠重采样器（scipy resample_poly + 跨chunk重叠保持，避免块边界滤波瞬态）"""

    def __init__(self, src_rate: int, dst_rate: int):
        from math import gcd
        g = gcd(dst_rate, src_rate)
        self.up = dst_rate // g
        self.down = src_rate // g
        self.src_rate = src_rate
        self.dst_rate = dst_rate
        self._tail = np.zeros(0, dtype=np.float32)

    def process(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self._tail, x]) if self._tail.size else x
        y = resample_poly(buf, self.up, self.down)
        cut = int(round(self._tail.size * self.dst_rate / self.src_rate))
        n_out = int(round(x.size * self.dst_rate / self.src_rate))
        self._tail = x[-64:].copy()  # 保留尾部样本供下一块滤波器连续
        if y.size < cut + n_out:
            y = np.pad(y, (0, cut + n_out - y.size))
        return y[cut:cut + n_out]


# ============================================================
# SenseVoice 流式ASR封装
# ============================================================
class SenseVoiceStreamASR:
    """SenseVoiceSmall 流式ASR封装（model.stream_infer 等价接口）

    说明：SenseVoiceSmall 本身是非流式模型，这里采用「能量VAD切分 + 增量识别」模拟流式：
    - 说话过程中每隔 PARTIAL_INTERVAL_SEC 输出一次 partial（is_final=False，仅预览）
    - 检测到静音端点后输出 final（is_final=True，完整句子可触发LLM）
    每个分段返回：{"text": 纯文本, "lang": 语种, "is_final": bool}
    """

    def __init__(self):
        from funasr import AutoModel  # 延迟导入，加快启动
        import torch

        device = config.DEVICE
        if device == "auto":
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print(f"正在加载 SenseVoice 模型（{config.SENSEVOICE_MODEL} @ {device}，首次运行需下载）...")
        self.model = AutoModel(
            model=config.SENSEVOICE_MODEL,
            device=device,
            disable_update=True,
        )
        # 流式状态：当前语音段缓冲、静音/语音帧计数、距上次partial的帧数
        self._buf = np.zeros(0, dtype=np.int16)
        self._speaking = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._since_partial = 0
        # AGC状态：语音电平估计与平滑增益（VAD用原始电平，识别用放大后音频）
        self._agc_est = None
        self._agc_gain = 1.0

    def feed(self, pcm_bytes: bytes) -> list:
        """送入一帧16kHz单声道16bit PCM，返回本次产生的ASR分段列表"""
        out = []
        pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
        if pcm.size == 0:
            return out
        x = pcm.astype(np.float32)
        rms = float(np.sqrt(np.mean(x ** 2)))
        voiced = rms >= config.SILENCE_RMS_THRESHOLD

        # AGC：仅在有声时更新电平估计，把语音归一到 AGC_TARGET_RMS（低电平回环不增益会导致语种误判）
        if voiced:
            if self._agc_est is None:
                self._agc_est = rms
            else:
                self._agc_est = 0.95 * self._agc_est + 0.05 * rms
            target_gain = min(config.AGC_MAX_GAIN,
                              max(1.0, config.AGC_TARGET_RMS / max(self._agc_est, 1.0)))
            self._agc_gain += 0.3 * (target_gain - self._agc_gain)  # 平滑变化避免爆音
        pcm = np.clip(x * self._agc_gain, -32768, 32767).astype(np.int16)

        # 静音期：丢弃音频，等待语音起点
        if not self._speaking:
            if voiced:
                self._speaking = True
                self._buf = pcm.copy()
                self._silence_frames = 0
                self._speech_frames = pcm.size
                self._since_partial = 0
            return out

        # 说话中：持续积累音频
        self._buf = np.concatenate([self._buf, pcm])
        self._since_partial += pcm.size
        if voiced:
            self._speech_frames += pcm.size
            self._silence_frames = 0
        else:
            self._silence_frames += pcm.size

        endpoint = self._silence_frames >= int(config.SILENCE_ENDPOINT_SEC * config.RATE)
        force_cut = self._speech_frames >= int(config.MAX_SEGMENT_SEC * config.RATE)

        # partial：说话中且距上次预览超过间隔（预览弹幕，禁止调用LLM）
        if (not endpoint and not force_cut
                and len(self._buf) >= config.RATE
                and self._since_partial >= int(config.PARTIAL_INTERVAL_SEC * config.RATE)):
            self._since_partial = 0
            text, lang = self._recognize(self._buf)
            if text:
                out.append({"text": text, "lang": lang, "is_final": False})

        # 端点/强制切分：输出 final（完整句子，英文可触发LLM）；太短的有效语音视为噪声丢弃
        if endpoint or force_cut:
            if self._speech_frames >= int(config.MIN_SPEECH_SEC * config.RATE):
                text, lang = self._recognize(self._buf)
                if text:
                    out.append({"text": text, "lang": lang, "is_final": True})
            self._reset()

        return out

    def _recognize(self, pcm_int16: np.ndarray):
        """调用SenseVoice识别，解析语种标签并去除所有<|...|>标签"""
        if pcm_int16.size < int(config.RATE * 0.2):  # 太短视为噪声
            return "", ""
        audio = pcm_int16.astype(np.float32) / 32768.0
        try:
            res = self.model.generate(
                input=audio, cache={},
                language="auto", use_itn=config.USE_ITN,
            )
        except Exception as e:
            print(f"[ASR异常] {e}")
            return "", ""
        raw = res[0].get("text", "") if res else ""
        m = _LANG_TAG_RE.search(raw)
        lang = m.group(1) if m else "unknown"
        text = _TAG_RE.sub("", raw).strip()
        return text, lang

    def _reset(self):
        """重置流式状态，开始新的语音段"""
        self._buf = np.zeros(0, dtype=np.int16)
        self._speaking = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._since_partial = 0


# ============================================================
# 音频设备工具
# ============================================================
def list_input_devices(pya):
    """列出所有输入设备，并提示可能的虚拟声卡/回环设备"""
    print("========== 可用输入设备 ==========")
    for i in range(pya.get_device_count()):
        info = pya.get_device_info_by_index(i)
        if int(info.get("maxInputChannels", 0)) > 0:
            name = str(info.get("name", ""))
            low = name.lower()
            mark = ""
            if any(k in low for k in ("cable", "loopback", "立体声混音", "stereo mix", "virtual")):
                mark = "  <== 可能是虚拟声卡/回环设备"
            print(f"[{i}] {name} | 采样率={info.get('defaultSampleRate')} | 声道={info.get('maxInputChannels')}{mark}")
    print("==================================")
    print("提示：将设备索引填入 config.py 的 INPUT_DEVICE_INDEX")


def open_input_stream(pya):
    """打开输入流：优先16kHz单声道；失败则退回设备原生采样率（之后代码重采样到16k）

    设备选择规则（config.INPUT_DEVICE_INDEX）：
    - "auto_loopback"：自动跟随默认播放设备的WASAPI回环（录对方声音，需pyaudiowpatch）
    - None：系统默认输入（麦克风）
    - 整数：指定设备索引
    返回 (stream, 实际采样率, 实际声道数, 设备名)
    """
    dev_idx = config.INPUT_DEVICE_INDEX
    if dev_idx == "auto_cable":
        # 优先VB-Cable虚拟声卡的CABLE Output录制端（纯数字信号，无音效处理），不存在则回退默认回环
        cable_idx = None
        for i in range(pya.get_device_count()):
            d = pya.get_device_info_by_index(i)
            if (d.get("maxInputChannels", 0) and not d.get("isLoopbackDevice")
                    and "CABLE Output" in str(d.get("name", ""))):
                cable_idx = d["index"]
                break
        dev_idx = cable_idx if cable_idx is not None else pya.get_default_wasapi_loopback()["index"]
    elif dev_idx == "auto_loopback":
        if not hasattr(pya, "get_default_wasapi_loopback"):
            raise RuntimeError("auto_loopback 需要 pyaudiowpatch（pip install pyaudiowpatch）")
        dev_idx = pya.get_default_wasapi_loopback()["index"]
    elif dev_idx is None:
        dev_idx = pya.get_default_input_device_info()["index"]
    info = pya.get_device_info_by_index(dev_idx)
    dev_name = info.get("name")
    native_rate = int(info.get("defaultSampleRate") or config.RATE)
    max_ch = int(info.get("maxInputChannels", 1)) or 1

    # 依次尝试：16k单声道 -> 原生采样率单声道 -> 原生采样率双声道
    for rate, ch in ((config.RATE, 1), (native_rate, 1), (native_rate, min(2, max_ch))):
        try:
            stream = pya.open(
                format=getattr(pyaudio, config.FORMAT),
                channels=ch,
                rate=rate,
                input=True,
                input_device_index=dev_idx,
                frames_per_buffer=config.CHUNK if rate == config.RATE
                else config.CHUNK * rate // config.RATE,
            )
            return stream, rate, ch, dev_name
        except Exception:
            continue
    raise RuntimeError(f"无法打开输入设备[{dev_idx}] {dev_name}，请检查虚拟声卡配置")


def to_16k_mono(pcm: np.ndarray, src_rate: int, src_channels: int) -> np.ndarray:
    """多声道下混为单声道 + 抗混叠重采样到16kHz（虚拟声卡常用48kHz）

    必须用带低通滤波的重采样（resample_poly），不能用线性插值直接抽取：
    48k->16k时8kHz以上频谱会混叠折叠，英文摩擦音(s/sh/th)能量在8-12kHz，
    混叠后辅音被毁，SenseVoice会把英文误判成中文。
    """
    global _RESAMPLER
    if src_channels == 2:
        pcm = pcm.reshape(-1, 2).mean(axis=1)
    x = pcm.astype(np.float32)
    if src_rate != config.RATE and x.size > 0:
        if _RESAMPLER is None or _RESAMPLER.src_rate != src_rate:
            _RESAMPLER = _PolyResampler(src_rate, config.RATE)
        x = _RESAMPLER.process(x)
    return np.clip(x, -32768, 32767).astype(np.int16)


# ============================================================
# 路由结果输出（控制台打印 + 可选推送UI消息队列）
# ============================================================
def handle_route_result(result, message_sink=None):
    """控制台打印路由结果，并可选推送结构化消息到UI队列"""
    if result is None:  # 其他语种/空文本：已丢弃
        return
    action = result["action"]
    if action == "preview":
        print(f"[预览弹幕][{result['lang']}] {result['text']}")
        if message_sink:
            message_sink({"type": "preview_bullet", "text": result["text"], "lang": result["lang"]})
    elif action == "zh_final":
        print(f"[中文弹幕] {result['text']}")
        if message_sink:
            message_sink({"type": "zh_final", "text": result["text"]})
    elif action == "en_final":
        print("====对方英文完整句子====")
        print(f"原文: {result['text']}")
        print(f"[中文弹幕] {result['zh']}")
        print(f"[推荐英文回复] {result['reply']}")
        if message_sink:
            message_sink({"type": "en_final", "text": result["text"],
                          "zh": result["zh"], "reply": result["reply"]})
    elif action == "skip":
        print(f"[跳过LLM] {result['text']} | 原因：{result['reason']}")


# ============================================================
# 主音频循环
# ============================================================
def audio_loop(message_sink=None):
    """主音频循环：打开声卡 -> 流式送入SenseVoice -> 路由Agent -> 控制台输出/UI消息"""
    asr = SenseVoiceStreamASR()
    pya = pyaudio.PyAudio()
    stream = None
    try:
        stream, src_rate, src_channels, dev_name = open_input_stream(pya)
        read_frames = config.CHUNK if src_rate == config.RATE else config.CHUNK * src_rate // config.RATE
        print(f"音频输入已打开：{dev_name} | {src_rate}Hz x {src_channels}ch -> 重采样到 {config.RATE}Hz 单声道")
        print("开始实时识别（Ctrl+C 退出）...")

        while True:
            data = stream.read(read_frames, exception_on_overflow=False)
            pcm = to_16k_mono(np.frombuffer(data, dtype=np.int16), src_rate, src_channels)
            for seg in asr.feed(pcm.tobytes()):
                handle_route_result(route_asr_segment(seg), message_sink)
    except KeyboardInterrupt:
        print("\n收到中断信号，正在优雅关闭...")
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        pya.terminate()
        print("音频流已关闭，资源已释放。")


# ============================================================
# 文件日志（控制台输出同步写入 logs/agent.log）
# ============================================================
class _Tee:
    """把print同时写到终端和日志文件"""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass
        return len(data)

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


def setup_file_logging():
    """开启后所有控制台输出同步追加到 logs/agent.log"""
    if not config.LOG_TO_FILE:
        return
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "agent.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    f = open(log_path, "a", encoding="utf-8", buffering=1)  # 行缓冲
    sys.stdout = _Tee(sys.stdout, f)
    sys.stderr = _Tee(sys.stderr, f)


if __name__ == "__main__":
    setup_file_logging()
    if "--list-devices" in sys.argv:
        _pya = pyaudio.PyAudio()
        try:
            list_input_devices(_pya)
        finally:
            _pya.terminate()
        sys.exit(0)
    audio_loop()
