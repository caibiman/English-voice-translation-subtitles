# -*- coding: utf-8 -*-
"""侧边可拖动小面板：展示最新【推荐英文回复】 + 一键复制

依赖：pip install pyqt6
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

_PANEL_QSS = """
QWidget {
    background: rgba(15, 15, 15, 215);
    border-radius: 12px;
}
QLabel {
    color: #FFFFFF;
    background: transparent;
    font-size: 14px;
}
QLabel#title {
    color: #7FD48A;
    font-weight: bold;
    font-size: 13px;
}
QPushButton {
    color: #FFFFFF;
    background: rgba(255, 255, 255, 28);
    border: 1px solid rgba(255, 255, 255, 60);
    border-radius: 8px;
    padding: 6px 10px;
}
QPushButton:hover {
    background: rgba(255, 255, 255, 48);
}
"""


class ReplyPanel(QWidget):
    """半透明黑色侧边面板：最新推荐英文回复 + 一键复制，支持鼠标拖动"""

    def __init__(self):
        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("推荐回复")
        self.setFixedSize(300, 170)

        self._reply = ""
        self._drag_offset = None

        title = QLabel("推荐英文回复")
        title.setObjectName("title")
        self._content = QLabel("（暂无）")
        self._content.setWordWrap(True)
        self._copy_btn = QPushButton("一键复制")
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(self._copy_reply)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self._content, 1)
        layout.addWidget(self._copy_btn)
        self.setStyleSheet(_PANEL_QSS)

    def set_reply(self, text: str):
        """更新最新推荐英文回复"""
        self._reply = (text or "").strip()
        self._content.setText(self._reply or "（暂无）")

    def _copy_reply(self):
        """一键复制推荐回复到剪贴板，并短暂反馈"""
        if not self._reply:
            return
        QGuiApplication.clipboard().setText(self._reply)
        self._copy_btn.setText("已复制")
        QTimer.singleShot(1200, lambda: self._copy_btn.setText("一键复制"))

    # ---- 鼠标拖动移动窗口 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
