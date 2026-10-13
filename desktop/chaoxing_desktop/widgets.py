from html import escape

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QTextBrowser, QVBoxLayout, QWidget)
from .answers import option_pairs, plain_text, question_images
from .config import BANKS


class ProviderPicker(QWidget):
    """Checked, ordered providers, without exposing registry identifiers."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setFixedHeight(150)
        for title, key in BANKS:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        for title, offset in (("上移", -1), ("下移", 1)):
            btn = QPushButton(title)
            btn.clicked.connect(lambda _=False, step=offset: self.move(step))
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)

    def move(self, offset):
        row = self.list.currentRow()
        target = row + offset
        if 0 <= row < self.list.count() and 0 <= target < self.list.count():
            item = self.list.takeItem(row)
            self.list.insertItem(target, item)
            self.list.setCurrentRow(target)

    def text(self):
        return ",".join(self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                        if self.list.item(i).checkState() == Qt.CheckState.Checked)

    def setText(self, value):
        selected = [x.strip() for x in value.split(",") if x.strip()]
        order = list(selected)
        order += [key for _, key in BANKS if key not in order]
        self.list.blockSignals(True)
        items = {self.list.item(i).data(Qt.ItemDataRole.UserRole): self.list.item(i) for i in range(self.list.count())}
        detached = {key: self.list.takeItem(self.list.row(item)) for key, item in items.items()}
        for key in order:
            if key in detached:
                item = detached[key]
                item.setCheckState(Qt.CheckState.Checked if key in selected else Qt.CheckState.Unchecked)
                self.list.addItem(item)
        self.list.blockSignals(False)


class InteractionDialog(QDialog):
    def __init__(self, event, parent=None):
        super().__init__(parent)
        self.answer = ""
        self.inputs = []
        self.setWindowTitle("补全题目" if event.get("kind") == "question" else "章节处理")
        self.resize(680, 560)
        layout = QVBoxLayout(self)
        heading = QLabel(event.get("message", "需要你的选择"))
        heading.setWordWrap(True)
        layout.addWidget(heading)
        if event.get("kind") == "choice":
            for choice in event["choices"]:
                btn = QPushButton(choice["label"])
                btn.clicked.connect(lambda _=False, value=choice["value"]: self.choose(value))
                layout.addWidget(btn)
            layout.addStretch()
            return
        question = event.get("question", {})
        browser = QTextBrowser()
        browser.setHtml("<h3>" + escape(plain_text(question.get("title", ""))) + "</h3><p>" +
                        escape(plain_text(question.get("options", ""))).replace("\n", "<br>") + "</p>")
        layout.addWidget(browser, 1)
        urls = question_images(question)
        if urls:
            area = QScrollArea()
            area.setWidgetResizable(True)
            content = QWidget()
            images = QVBoxLayout(content)
            area.setWidget(content)
            layout.addWidget(area, 1)
            self.network = QNetworkAccessManager(self)
            for url in urls:
                preview = QLabel("正在加载题目图片…")
                preview.setWordWrap(True)
                images.addWidget(preview)
                request = QNetworkRequest(QUrl(url))
                request.setTransferTimeout(15000)
                reply = self.network.get(request)
                reply.downloadProgress.connect(lambda received, total, r=reply: r.abort() if max(received, total) > 10 * 1024 * 1024 else None)
                reply.finished.connect(lambda r=reply, target=preview: self.image_finished(r, target))
        kind = question.get("type")
        if kind in ("single", "multiple", "judgement"):
            pairs = [("正确", "正确"), ("错误", "错误")] if kind == "judgement" else option_pairs(question)
            for key, text in pairs:
                check = QCheckBox(key + (" · " + plain_text(text) if key != text else ""))
                self.inputs.append((check, key))
                if kind != "multiple":
                    check.toggled.connect(lambda selected, current=check: self.select_single(current) if selected else None)
                layout.addWidget(check)
            self.text = None
        else:
            self.text = QLineEdit()
            self.text.setPlaceholderText("填写答案；多个填空按顺序填写")
            layout.addWidget(self.text)
        self.hint = QLabel("未找到答案可跳过，选择题和判断题随后按随机补全设置处理。" if event.get("random_fallback") else "未找到答案可跳过，此题将保持待处理。")
        layout.addWidget(self.hint)
        row = QHBoxLayout()
        send = QPushButton("使用答案")
        send.clicked.connect(self.submit_answer)
        skip = QPushButton("跳过此题")
        skip.clicked.connect(lambda: self.choose(""))
        stop = QPushButton("停止任务")
        stop.clicked.connect(self.reject)
        row.addWidget(skip)
        row.addStretch()
        row.addWidget(stop)
        row.addWidget(send)
        layout.addLayout(row)

    def image_finished(self, reply, label):
        pixmap = QPixmap()
        if reply.error() == reply.NetworkError.NoError and pixmap.loadFromData(bytes(reply.readAll())):
            label.setPixmap(pixmap.scaledToWidth(580, Qt.TransformationMode.SmoothTransformation))
        else:
            label.setText("图片加载失败，请在学习平台查看原题。")
        reply.deleteLater()

    def select_single(self, current):
        for check, _ in self.inputs:
            if check is not current:
                check.setChecked(False)

    def submit_answer(self):
        value = self.text.text().strip() if self.text else "".join(key for check, key in self.inputs if check.isChecked())
        if not value:
            self.hint.setText("请先选择或填写答案，也可点击「跳过此题」。")
            return
        self.choose(value)

    def choose(self, value):
        self.answer = value
        self.accept()
