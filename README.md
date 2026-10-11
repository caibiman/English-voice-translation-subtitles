# 视频通话实时中英音频Agent（SenseVoice流式ASR）

采集**虚拟环路声卡**中视频通话对方的声音（中英混杂），使用 SenseVoiceSmall 实时语音识别并自动判语种；
路由Agent按规则分流识别结果：英文完整句调用LLM生成【中文弹幕】+【推荐英文回复】，中文仅输出弹幕不调LLM，其他语种丢弃。
提供两种运行方式：**控制台版（main.py）** 与 **PyQt6悬浮弹幕UI版（main_ui.py）**。

## 功能特性

- 虚拟声卡/扬声器回环采集，16kHz 单声道 16bit PCM（原生48kHz设备自动重采样）
- SenseVoiceSmall 流式ASR：逐段返回 `text / lang / is_final`（能量VAD切分 + 增量识别模拟流式）
- 路由Agent：
  - partial（is_final=False）仅预览弹幕，禁止调用LLM
  - 英文 final：单词数≥4 且 距上次LLM≥1.2秒 才调用LLM，否则打印跳过原因
  - 中文 final：只输出中文弹幕，禁止调用LLM
  - 其他语种：丢弃
- LLM 兼容 OpenAI 协议（DeepSeek/通义千问等），Prompt 严格输出两行，正则解析
- 对话上下文最多保留最近4轮，自动截断
- PyQt6 UI：置顶透明弹幕层（右→左滚动、自动淡出、数量上限、preview低优先级）、侧边推荐回复面板（可拖动+一键复制）、`queue.Queue` 线程安全通信

## 目录结构

```
video_call_real_time_agent/
├── README.md
├── requirements.txt
├── config.py                 # 全局配置：LLM密钥、音频参数、冷却时间、历史轮数
├── main.py                   # 控制台版：音频循环 + SenseVoice流式ASR + 路由Agent
├── main_ui.py                # UI版：后台线程跑Agent + PyQt6主线程渲染
├── agent/
│   ├── router.py             # 路由Agent核心逻辑（分流规则、冷却控制）
│   ├── llm_client.py         # LLM请求、prompt、正则解析、对话上下文
│   └── utils.py              # 英文单词计数、历史文本拼接
├── ui/
│   ├── bullet_window.py      # 置顶透明弹幕滚动窗口
│   └── reply_panel.py        # 侧边推荐回复面板 + 一键复制
└── logs/
```

## 环境安装

```bash
# 建议 Python 3.10+
pip install -r requirements.txt
# torch 未装好时按需选择（CPU版示例）：
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
```

## 虚拟声卡配置（Windows）

**方案A（强烈推荐）：VB-CABLE 虚拟声卡** —— 实测回环采集会被 Realtek 音效增强（响度均衡等）处理，导致英文摩擦音被毁、识别变中文乱码；VB-CABLE 是纯数字零处理链路，识别准确率与离线测试一致。

1. 安装 [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)（无需重启）；
2. 视频通话软件的扬声器/输出设为 `CABLE Input (VB-Audio Virtual Cable)`（浏览器通话可在 Win11 设置 → 系统 → 声音 → 应用音量和设备首选项中单独指定）；
3. **让自己也能听到对方**：右键任务栏喇叭 → 声音设置 → 更多声音设置 →「录制」→ 双击 `CABLE Output` →「侦听」→ 勾选「侦听此设备」、播放设备选耳机 → 确定；
4. `config.py` 保持 `INPUT_DEVICE_INDEX = "auto_cable"`（自动优先 CABLE Output，未装 VB-CABLE 时自动回退系统回环）。

**方案B：WASAPI 回环采集（无需装虚拟声卡）**

已依赖 `pyaudiowpatch`，`INPUT_DEVICE_INDEX = "auto_loopback"` 即可自动跟随默认播放设备回环。
注意：若英文识别差、被识别成中文，先到 Realtek Audio Console（或声音设置→设备属性）**关闭响度均衡等所有音效增强**再试。

其他可用：Realtek「立体声混音」、OBS 音频捕获等。设为 `None` 使用默认麦克风，设为数字指定设备索引（`python main.py --list-devices` 查看）。

## LLM 配置

```bash
# 环境变量方式（推荐）
set LLM_API_KEY=sk-xxxx
set LLM_BASE_URL=https://api.deepseek.com/v1
set LLM_MODEL=deepseek-chat
```

或直接修改 [config.py](config.py)。通义千问示例：`LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`，`LLM_MODEL=qwen-turbo`。

## 启动

```bash
python main.py --list-devices   # 查看输入设备索引
python main.py                  # 控制台版
python main_ui.py               # PyQt6 悬浮弹幕UI版
```

## 控制台输出格式

```
[预览弹幕][en] i think we should
[中文弹幕] 今天天气挺不错的
====对方英文完整句子====
原文: I think we should ship it today
[中文弹幕] 我觉得咱们今天就发了吧
[推荐英文回复] Sounds good, let's ship it!
[跳过LLM] ok fine | 原因：单词不足（2 < 4）
```

## 常见问题

- 模型首次运行会自动从 ModelScope 下载 `iic/SenseVoiceSmall`（约1GB）；
- 弹幕层不接收鼠标点击（不挡视频窗口操作），回复面板可拖动、可复制；
- 无声/不识别：检查视频通话软件输出是否指向 `CABLE Input`，`--list-devices` 确认设备；
- 英文识别成中文乱码：优先用方案A（VB-CABLE）；用回环时关闭 Realtek 音效增强；
- 识别调优（config.py）：`SILENCE_ENDPOINT_SEC=0.45` 句子切分灵敏度（调小切得更细）、`AGC_TARGET_RMS=2500` 自动增益目标电平、`MAX_SEGMENT_SEC=8` 最长单段；
- LLM 报 401：检查 `LLM_API_KEY` 是否配置正确。
