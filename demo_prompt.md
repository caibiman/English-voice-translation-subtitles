# 项目需求：视频通话实时中英音频Agent（SenseVoice流式ASR）
## 项目简介
采集虚拟环路声卡的音频（视频通话对方声音，音频中英混杂），使用SenseVoiceSmall流式ASR做实时语音识别，自动识别语种，返回逐段 text / lang / is_final。
构建路由Agent，按规则分流识别结果；英文完整句子调用LLM生成中文弹幕翻译 + 推荐英文回复；中文仅输出弹幕，不调用LLM。
严格遵守所有业务规则，编写完整可运行Python代码，附带注释、配置区。

## 技术栈
Python 3.10+
funasr(SenseVoiceSmall)、pyaudio、openai SDK、re、time

## 核心业务规则（必须全部实现）
1. 音频采集：读取虚拟环路声卡，16000Hz，单声道，16bit PCM
2. SenseVoice流式ASR：使用 model.stream_infer，逐段返回结果，包含 text、lang、is_final
3. 路由Agent逻辑：
   - is_final=False（partial 中间识别结果）：仅预览弹幕，**禁止调用LLM**，控制台打印预览
   - is_final=True：
     - 若 lang == en：统计英文单词数量。单词≥4，并且距离上一次LLM调用间隔≥1.2秒，才调用LLM；否则跳过LLM
     - 若 lang == zh：只输出中文弹幕，**禁止调用LLM**
     - 其他语种：丢弃
4. LLM 相关规则：
   - LLM 接口兼容 OpenAI 协议（DeepSeek/通义千问均可）
   - Prompt：角色是视频通话助手，输入对方英文句子+对话上下文；输出严格固定格式两行：
【中文弹幕】简短口语中文翻译，适合悬浮弹幕
【推荐英文回复】仅1条简短口语英文回复，贴合对话上下文
   - 使用正则提取【中文弹幕】、【推荐英文回复】内容
5. 对话上下文管理：
   - 保存对话历史，结构：[{"role":"user","text":"对方英文"},{"role":"assistant","text":"推荐回复"}]
   - 最多保留最近4轮对话，超出自动截断，防止上下文过长
6. LLM 冷却控制：全局记录上一次LLM调用时间戳，强制最小间隔1.2秒，防止高频API调用
7. 英文单词统计：使用正则提取英文字母单词计数
8. 控制台输出格式（用于调试）：
   - [预览弹幕][语种] 文本
   - [中文弹幕] 中文文本
   - 英文命中LLM时打印：====对方英文完整句子====，原文、中文弹幕、推荐英文回复
   - [跳过LLM] 原文 + 原因（单词不足 / 冷却未到）

## 代码结构要求
video_call_real_time_agent/
├── README.md                     # 项目说明、环境安装、虚拟声卡配置、启动命令
├── requirements.txt              # 依赖列表
├── config.py                     # 全局配置：LLM密钥、音频参数、冷却时间、历史轮数等
├── main.py                       # 程序入口，音频循环 + SenseVoice流式ASR + 路由Agent（控制台版）
├── agent/
│   ├── __init__.py
│   ├── router.py                 # 路由Agent核心逻辑：处理ASR分段、分流规则
│   ├── llm_client.py             # LLM请求、prompt管理、正则解析返回结果、上下文管理
│   └── utils.py                  # 工具函数：英文单词计数、历史文本拼接
├── ui/                           # 【可选，二期开发】PyQt悬浮弹幕面板模块
│   ├── __init__.py
│   ├── bullet_window.py          # 置顶透明弹幕滚动窗口
│   └── reply_panel.py            # 侧边推荐回复面板 + 一键复制
├── logs/                         # 日志目录（自动生成）
│   └── .gitkeep
├── .gitignore                    # 忽略密钥、日志、模型缓存、临时文件
└── demo_prompt.md                # 存放你给AI Coding的提示词备份

1. 配置区：
   - LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
   - LLM_COOLDOWN_SEC=1.2、MIN_EN_WORD_COUNT=4、MAX_HISTORY_ROUND=4
   - 音频参数：CHUNK、FORMAT、CHANNELS、RATE、INPUT_DEVICE_INDEX
2. 全局状态变量：dialog_history（对话历史），last_llm_call_ts（上次LLM调用时间）
3. 函数清单：
   - count_english_words(text): 统计英文单词数量
   - build_history_text(history_list): 将对话历史拼接成文本给LLM
   - call_llm_generate(en_text, history_list): 请求LLM，正则解析返回弹幕和推荐回复
   - route_asr_segment(seg): 路由Agent核心逻辑，接收ASR分段结果，返回结构化结果或None
   - audio_loop(): 主音频循环，打开声卡流，流式送入SenseVoice，遍历ASR结果，调用路由Agent，控制台打印输出
4. 异常处理：捕获KeyboardInterrupt，优雅关闭音频流，释放资源
5. 注释：关键逻辑增加简短中文注释


## 依赖清单（放在代码头部注释）
```bash
pip install pyaudio openai funasr

-----
# 扩展需求：基于上一段SenseVoice视频通话Agent，增加PyQt6桌面UI
## UI功能
1. 顶层透明置顶窗口，用于滚动中文弹幕，不遮挡视频通话窗口；弹幕自动淡出，限制同时显示弹幕数量
2. 独立侧边小面板：展示最新【推荐英文回复】，增加【一键复制】按钮
3. 使用多线程：音频ASR/Agent逻辑在后台子线程；PyQt主线程只负责UI渲染，不能阻塞音频流
4. 线程安全：使用队列queue.Queue，后台Agent把弹幕/推荐回复消息推入队列，UI主线程读取队列更新界面
5. 消息类型：preview_bullet、zh_final、en_final；
   - preview_bullet：临时预览弹幕，优先级低
   - zh_final/en_final：正式弹幕
6. 样式：半透明黑色背景，白色文字；侧边面板可拖动
7. 不要修改原有SenseVoice ASR、路由Agent、LLM调用逻辑，只增加UI和消息队列封装
8. 依赖新增：pip install pyqt6


