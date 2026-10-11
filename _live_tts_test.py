# -*- coding: utf-8 -*-
"""临时脚本：向默认音频设备播放用户提供的测试对话（句间0.5s停顿），用于实测UI版弹幕效果"""
import subprocess
import time

sentences = [
    ("Microsoft David Desktop", "Hi, I want to talk about our project timeline."),
    ("Microsoft Huihui Desktop", "下一个交付节点是什么时候？"),
    ("Microsoft David Desktop", "We need to finish the prototype before next Friday."),
    ("Microsoft Huihui Desktop", "这个文档我稍后发到群里。"),
    ("Microsoft David Desktop", "Can you share the latest design document with me?"),
    ("Microsoft Huihui Desktop", "这个文档我稍后发到群里。"),
    ("Microsoft David Desktop", "I am worried about the performance issue."),
    ("Microsoft David Desktop", "Do we have extra engineers to help with testing?"),
    ("Microsoft Huihui Desktop", "测试人手目前有点紧张。"),
    ("Microsoft David Desktop", "OK, I will adjust my schedule and join the test."),
    ("Microsoft Huihui Desktop", "那我们下午三点开个短会对齐一下。"),
    ("Microsoft David Desktop", "Sounds good, see you then."),
]

for voice, text in sentences:
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SetOutputToDefaultAudioDevice(); "
        f"$s.SelectVoice('{voice}'); "
        "$s.Volume = 100; "
        f"$s.Speak('{text}'); "
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-Command", ps],
                   capture_output=True, timeout=60)
    time.sleep(0.5)

print("对话播放完毕")
