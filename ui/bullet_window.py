# -*- coding: utf-8 -*-
"""置顶透明弹幕滚动窗口：横向滚动弹幕、自动淡出、限制同时显示数量

依赖：pip install pyqt6
"""

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QPoint, Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication, QGraphicsOpacityEffect, QLabel, QWidget

import config

# 弹幕样式：半透明黑色背景 + 白色文字；preview更淡（优先级低）、en_final高亮
_STYLE = {
    "preview": "background: rgba(0,0,0,90); color: rgba(255,255,255,170); font-style: italic;",
    "zh_final": "background: rgba(0,0,0,170); color: #FFFFFF;",
    "en_final": "background: rgba(20,90,50,190); color: #FFFFFF; font-weight: bold;",
}
_LABEL_H = 38   # 单条弹幕高度（像素）
_GAP = 40       # 同行弹幕最小间距（像素）


class BulletWindow(QWidget):
    """屏幕顶部全宽透明置顶弹幕层，经典右->左滚动弹幕，不遮挡视频通话窗口焦点"""

    def __init__(self):
        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool
                 | Qt.WindowType.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        screen = QApplication.primaryScreen().availableGeometry()
        self._row_h = 46
        self._rows = max(1, config.BULLET_ROWS)
        self.setGeometry(screen.x() + 20, screen.y() + 10,
                         max(600, screen.width() - 40), self._row_h * self._rows)
        self._row_last = [None] * self._rows  # 每行最近一条弹幕，用于错行
        self._bullets = []                    # 当前存活的 (label, row)，用于数量限制

    def add_bullet(self, text: str, kind: str = "zh_final"):
        """新增一条弹幕；超过数量上限时优先淘汰最早的preview弹幕"""
        text = (text or "").strip()
        if not text:
            return

        # 限制同时显示弹幕数量
        while len(self._bullets) >= max(1, config.BULLET_MAX_COUNT):
            victim_idx = next((i for i, (lb, _) in enumerate(self._bullets)
                               if lb._kind == "preview"), 0)
            self._remove(self._bullets[victim_idx])

        label = QLabel(text, self)
        label._kind = kind
        label.setStyleSheet(_STYLE.get(kind, _STYLE["zh_final"]) + " border-radius: 18px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 依据字宽定尺寸，过长则省略
        fm = QFontMetrics(label.font())
        max_w = int(self.width() * 0.7)
        shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w - 28)
        if shown != text:
            label.setText(shown)
            fm = QFontMetrics(label.font())
        label.setFixedSize(min(fm.horizontalAdvance(shown) + 28, max_w), _LABEL_H)

        row = self._pick_row(label.width())
        y = row * self._row_h + (self._row_h - _LABEL_H) // 2
        start = QPoint(self.width() + 10, y)
        label.move(start)
        label.show()
        self._row_last[row] = label

        rec = (label, row)
        label._rec = rec
        self._bullets.append(rec)

        # 右 -> 左匀速滚动，走完后自动淡出销毁
        dist = self.width() + 20 + label.width()
        anim = QPropertyAnimation(label, b"pos", self)
        anim.setStartValue(start)
        anim.setEndValue(QPoint(-label.width() - 10, y))
        anim.setDuration(max(2000, int(dist / max(40, config.BULLET_SPEED_PX_SEC) * 1000)))
        anim.setEasingCurve(QEasingCurve.Type.Linear)
        anim.finished.connect(lambda: self._fade_out(label))
        label._anim = anim
        anim.start()

    def _pick_row(self, _w: int) -> int:
        """挑一行：优先空行；否则选尾部空隙最大的行（避免重叠）"""
        best, best_gap = 0, -1
        for r in range(self._rows):
            last = self._row_last[r]
            gap = self.width() if last is None else self.width() - (last.x() + last.width() + _GAP)
            if gap > best_gap:
                best, best_gap = r, gap
        return best

    def _fade_out(self, label: QLabel):
        """滚动到头后淡出并回收"""
        rec = getattr(label, "_rec", None)
        effect = QGraphicsOpacityEffect(label)
        label.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", label)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(350)
        anim.finished.connect(lambda: self._remove(rec) if rec else None)
        label._fade = anim
        anim.start()

    def _remove(self, rec):
        """从窗口移除一条弹幕，释放行资源"""
        if rec is None or rec not in self._bullets:
            return
        label, row = rec
        anim = getattr(label, "_anim", None)
        if anim is not None:
            anim.stop()
        if self._row_last[row] is label:
            self._row_last[row] = None
        self._bullets.remove(rec)
        label.hide()
        label.deleteLater()
