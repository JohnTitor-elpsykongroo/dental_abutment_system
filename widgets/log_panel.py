# widgets/log_panel.py
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QTextEdit,
    QPushButton,
    QApplication,
)


class LogPanel(QWidget):
    """
    日志输出区
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(8)

        group = QGroupBox("日志输出")
        group_layout = QVBoxLayout(group)

        toolbar_layout = QHBoxLayout()
        self.btn_clear = QPushButton("清空日志")
        self.btn_copy = QPushButton("复制日志")

        toolbar_layout.addWidget(self.btn_clear)
        toolbar_layout.addWidget(self.btn_copy)
        toolbar_layout.addStretch(1)

        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setPlaceholderText("系统日志将在此输出。")

        group_layout.addLayout(toolbar_layout)
        group_layout.addWidget(self.log_text_edit)

        root_layout.addWidget(group)

        self.btn_clear.clicked.connect(self.clear_log)
        self.btn_copy.clicked.connect(self.copy_log)

    def append_log(self, message: str):
        current_time = datetime.now().strftime("%H:%M:%S")
        line = "[{}] {}".format(current_time, message)
        self.log_text_edit.append(line)

    def clear_log(self):
        self.log_text_edit.clear()

    def copy_log(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_text_edit.toPlainText())