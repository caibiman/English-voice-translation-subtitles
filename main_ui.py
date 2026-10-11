# -*- coding: utf-8 -*-
"""
程序入口（PyQt6 UI版）：后台子线程运行 音频采集+SenseVoice流式ASR+路由Agent，
通过 queue.Queue 把消息推给UI主线程，PyQt主线程只负责UI渲染，不阻塞音频流。

依赖安装：
    pip install pyaudio openai funasr pyqt6

启动命令：
    python main_ui.py
"""

import queue
import signal
import sys
import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from main import audio_loop, setup_file_logging  # 复用控制台版的音频+ASR+Agent主循环（逻辑不变）
from ui.bullet_window import BulletWindow
from ui.reply_panel import ReplyPanel

# 线程安全消息队列：后台Agent -> UI主线程
msg_queue = queue.Queue()


def agent_worker():
    """后台子线程：跑音频+ASR+路由Agent，结果推入消息队列（控制台打印同时保留）"""

    def sink(msg):
        msg_queue.put(msg)

    try:
        audio_loop(message_sink=sink)
    except Exception as e:  # 线程内异常不能让进程静默挂掉
        import traceback
        traceback.print_exc()
        msg_queue.put({"type": "fatal", "text": f"{type(e).__name__}: {e}"})


def drain_queue(bullet_win: BulletWindow, panel: ReplyPanel):
    """UI主线程定时读取队列并更新界面"""
    while True:
        try:
            msg = msg_queue.get_nowait()
        except queue.Empty:
            return
        mtype = msg.get("type")
        if mtype == "preview_bullet":   # 预览弹幕：优先级低，样式更淡
            bullet_win.add_bullet(msg["text"], kind="preview")
        elif mtype == "zh_final":       # 中文正式弹幕
            bullet_win.add_bullet(msg["text"], kind="zh_final")
        elif mtype == "en_final":       # 英文命中LLM：弹幕显示中文翻译，面板更新推荐回复
            bullet_win.add_bullet(msg["zh"], kind="en_final")
            panel.set_reply(msg["reply"])
        elif mtype == "fatal":
            QMessageBox.warning(None, "Agent线程异常退出", msg["text"])


def main():
    setup_file_logging()
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # 允许Ctrl+C直接退出UI

    # 后台子线程：音频+ASR+Agent（UI不阻塞音频流）
    threading.Thread(target=agent_worker, daemon=True, name="agent-audio").start()

    app = QApplication(sys.argv)

    bullet_win = BulletWindow()
    bullet_win.show()

    panel = ReplyPanel()
    screen = app.primaryScreen().availableGeometry()
    panel.move(screen.right() - panel.width() - 40, screen.bottom() - panel.height() - 40)
    panel.show()

    timer = QTimer()
    timer.timeout.connect(lambda: drain_queue(bullet_win, panel))
    timer.start(80)  # 80ms轮询一次消息队列

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
