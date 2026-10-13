from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import __version__
from .config import (Redactor, course_key, data_dir, defaults, parse_text, resource_root, serialize,
                     to_payload, validate)
from .controller import Controller
from .widgets import InteractionDialog, ProviderPicker

STYLE = """
QWidget { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei'; font-size: 13px; color: #22324c; }
QMainWindow, QWidget#root { background: #f4f6fb; }
QFrame#sidebar { background: #17253e; border-radius: 0; }
QFrame#sidebar QLabel { color: #e7edf9; }
QLabel#brand { font-size: 23px; font-weight: 700; }
QLabel#muted { color: #728198; }
QLabel#heading { font-size: 27px; font-weight: 700; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#number { font-size: 28px; font-weight: 700; color: #355be3; }
QFrame#card { background: white; border: 1px solid #e5e9f2; border-radius: 12px; }
QListWidget#nav { background: transparent; color: #aebbd1; border: 0; outline: none; font-size: 14px; }
QListWidget#nav::item { padding: 14px 18px; margin: 4px 0; border-radius: 8px; }
QListWidget#nav::item:selected { background: #2e4162; color: white; }
QListWidget#nav::item:hover { background: #243655; }
QPushButton { background: white; border: 1px solid #dce2ee; border-radius: 7px; padding: 9px 16px; }
QPushButton:hover { background: #edf1ff; border-color: #b0bff2; }
QPushButton:disabled { color: #a1aabb; background: #f3f5f8; border-color: #e3e7ee; }
QPushButton#primary { background: #4266ed; border-color: #4266ed; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #3154d7; }
QPushButton#primary:disabled { background: #adbbed; border-color: #adbbed; }
QPushButton#danger { color: #bc4759; border-color: #edcfd4; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #dce2ee; border-radius: 6px; padding: 7px 9px; min-height: 20px; }
QLineEdit:focus, QComboBox:focus { border-color: #4266ed; }
QCheckBox { spacing: 8px; padding: 5px 0; }
QCheckBox::indicator { width: 16px; height: 16px; }
QPlainTextEdit { background: #fafbfe; border: 1px solid #e1e6ef; border-radius: 7px; padding: 8px; selection-background-color: #c6d1ff; }
QTableWidget { background: white; border: 0; gridline-color: #edf0f5; selection-background-color: #eaf0ff; selection-color: #22324c; }
QHeaderView::section { background: #f5f7fc; color: #728198; border: 0; padding: 11px; font-weight: 600; }
QTableWidget::item { padding: 8px; }
QProgressBar { border: 0; border-radius: 4px; background: #e8ecf7; height: 8px; text-align: center; }
QProgressBar::chunk { background: #4266ed; border-radius: 4px; }
QScrollArea { border: 0; background: transparent; }
QStatusBar { background: white; color: #728198; border-top: 1px solid #e1e6ef; }
"""

STATUS = {"waiting": "等待", "running": "处理中", "processed": "等待核验", "retry": "等待重试",
          "success": "已完成", "failed": "失败", "skipped": "未开放 / 跳过", "pending": "待完成 / 未核验", "stopped": "已停止"}


def label(text, name=None):
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    result.setWordWrap(True)
    return result


def button(text, callback, primary=False):
    result = QPushButton(text)
    if primary:
        result.setObjectName("primary")
    result.clicked.connect(callback)
    return result


def card(title=None):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(14)
    if title:
        layout.addWidget(label(title, "section"))
    return frame, layout


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"超星桌面版 · {__version__}")
        self.setWindowIcon(QIcon(str(resource_root() / "assets/app.svg")))
        self.resize(1200, 840)
        self.setMinimumSize(980, 700)
        self.config = defaults()
        settings = data_dir() / "settings.ini"
        self.startup_error = None
        if settings.exists():
            try:
                self.config = parse_text(settings.read_text(encoding="utf-8-sig"))
                validate(self.config)
            except Exception as exc:
                self.startup_error = str(exc)
                self.config = defaults()
        self.fields = {}
        self.courses = []
        self.courses_demo = False
        self.course_identity = None
        self.task_rows = {}
        self.task_states = {}
        self.operation = None
        self.outcome = False
        self.input_dialog = None
        self.log_redactor = Redactor({})
        self.controller = Controller(self)
        self.controller.event.connect(self.on_event)
        self.controller.finished.connect(self.on_finished)
        self.controller.busy_changed.connect(self.on_busy)
        self.build_ui()
        self.fill_fields()
        if self.startup_error:
            QTimer.singleShot(0, lambda: self.problem("本地配置读取失败，已载入默认设置：" + self.startup_error))

    def build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 30, 20, 24)
        side.addWidget(label("超星桌面版", "brand"))
        side.addWidget(label("CHAOXING DESKTOP", "muted"))
        side.addSpacing(30)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.addItems(["01   课程与账号", "02   学习设置", "03   题库与 AI", "04   高级设置", "05   任务与日志"])
        side.addWidget(self.nav)
        side.addWidget(label("本地运行 · 开源软件"))
        side.addWidget(label(f"v{__version__}  /  GPL-3.0", "muted"))
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(30, 26, 30, 18)
        content.setSpacing(18)
        top = QHBoxLayout()
        self.heading = label("课程与账号", "heading")
        top.addWidget(self.heading)
        top.addStretch()
        self.mode_label = label("准备就绪", "muted")
        top.addWidget(self.mode_label)
        self.save_button = button("保存设置", self.save_settings, True)
        top.addWidget(self.save_button)
        self.demo_button = button("离线演示", self.load_demo)
        top.addWidget(self.demo_button)
        content.addLayout(top)
        self.stack = QStackedWidget()
        content.addWidget(self.stack)
        outer.addLayout(content, 1)
        self.make_courses()
        self.make_settings()
        self.make_services()
        self.make_advanced()
        self.make_monitor()
        self.nav.currentRowChanged.connect(self.change_page)
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage("登录读取课程，或先体验离线演示。密码与密钥默认不保存。")

    def change_page(self, index):
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        self.heading.setText(["课程与账号", "学习设置", "题库、AI 与通知", "高级设置", "任务与日志"][index])

    def page(self, scroll=False):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        if scroll:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(page)
            self.stack.addWidget(area)
        else:
            self.stack.addWidget(page)
        return page, layout

    def field(self, section, key, kind="text", low=0, high=100, choices=None):
        if kind == "bool":
            widget = QCheckBox()
        elif kind == "int":
            widget = QSpinBox()
            widget.setRange(low, high)
        elif kind == "float":
            widget = QDoubleSpinBox()
            widget.setRange(low, high)
            widget.setDecimals(2)
            widget.setSingleStep(0.1)
        elif kind == "choice":
            widget = QComboBox()
            for title, value in choices:
                widget.addItem(title, value)
        else:
            widget = QLineEdit()
            if kind == "secret":
                widget.setEchoMode(QLineEdit.EchoMode.Password)
        self.fields[(section, key)] = widget
        return widget

    def make_courses(self):
        _, layout = self.page()
        login, body = card("连接你的学习账户")
        row = QHBoxLayout()
        username = self.field("common", "username")
        username.setPlaceholderText("手机号 / 账号")
        password = self.field("common", "password", "secret")
        password.setPlaceholderText("登录密码（仅本次会话）")
        row.addWidget(username, 1)
        row.addWidget(password, 1)
        self.login_button = button("登录并读取课程", self.fetch_courses, True)
        row.addWidget(self.login_button)
        body.addLayout(row)
        row2 = QHBoxLayout()
        cookies = self.field("common", "use_cookies", "bool")
        cookies.setText("使用本机 Cookie 登录")
        row2.addWidget(cookies)
        self.cookie_button = button("导入 Cookie", self.import_cookie)
        row2.addWidget(self.cookie_button)
        self.clear_cookie_button = button("清除 Cookie", self.clear_cookie)
        row2.addWidget(self.clear_cookie_button)
        row2.addStretch()
        body.addLayout(row2)
        self.cookie_label = label("", "muted")
        self.update_cookie_label()
        body.addWidget(self.cookie_label)
        layout.addWidget(login)
        course_card, body = card()
        tools = QHBoxLayout()
        self.course_count = label("我的课程 · 0 门", "section")
        tools.addWidget(self.course_count)
        tools.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索课程名称或 ID")
        self.search.setMaximumWidth(240)
        self.search.textChanged.connect(self.filter_courses)
        tools.addWidget(self.search)
        self.all_button = button("全选可见", lambda: self.check_courses(True))
        self.none_button = button("取消选择", lambda: self.check_courses(False))
        tools.addWidget(self.all_button)
        tools.addWidget(self.none_button)
        body.addLayout(tools)
        self.course_table = QTableWidget(0, 4)
        self.course_table.setHorizontalHeaderLabels(["选择", "课程名称", "课程 ID", "班级 ID"])
        self.course_table.verticalHeader().hide()
        self.course_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.course_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.course_table.setColumnWidth(0, 55)
        self.course_table.setColumnWidth(2, 135)
        self.course_table.setColumnWidth(3, 125)
        self.course_table.itemChanged.connect(self.update_selection)
        body.addWidget(self.course_table)
        self.empty_label = label("还没有课程。登录读取课程，或点击右上角「离线演示」。", "muted")
        body.addWidget(self.empty_label)
        footer = QHBoxLayout()
        self.selection_label = label("已选 0 门课程", "muted")
        footer.addWidget(self.selection_label, 1)
        self.start_button = button("开始所选课程", self.start_tasks, True)
        self.start_button.setEnabled(False)
        footer.addWidget(self.start_button)
        body.addLayout(footer)
        layout.addWidget(course_card, 1)

    def make_settings(self):
        _, layout = self.page(True)
        frame, body = card("学习与任务调度")
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.addRow("视频倍速", self.field("common", "speed", "float", 1, 2))
        form.addRow("同时处理的章节数", self.field("common", "jobs", "int", 1, 16))
        form.addRow("未开放章节", self.field("common", "notopen_action", "choice", choices=[("重试（最多 5 轮）", "retry"), ("询问后跳过或停止", "ask"), ("直接跳过", "continue")]))
        form.addRow("重试间隔 / 秒", self.field("common", "retry_interval", "float", 0.1, 3600))
        body.addLayout(form)
        body.addWidget(label("任务进度按章节处理状态展示；结束后会重新读取平台完成情况。", "muted"))
        layout.addWidget(frame)
        frame, body = card("章节检测与学习次数")
        form = QFormLayout()
        form.addRow("答错后允许重做", self.field("common", "work_redo_enabled", "bool"))
        form.addRow("最多重做次数", self.field("common", "work_max_retries", "int", 0, 20))
        form.addRow("任务结束后追加学习次数", self.field("common", "add_learning_count", "bool"))
        form.addRow("目标总次数", self.field("common", "target_count", "int", 1, 100000))
        body.addLayout(form)
        body.addWidget(label("仅允许一次作答的课程请保持重做关闭。开启重做后，AI 可参考上一轮错误反馈。", "muted"))
        layout.addWidget(frame)
        layout.addStretch()

    def make_services(self):
        _, layout = self.page(True)
        frame, body = card("答题流程")
        body.addWidget(label("① 按顺序查询已启用题库  →  ② AI 补全未解决题目  →  ③ 人工补全（可选）"))
        body.addWidget(label("题库与 AI 独立配置，均可单独使用。AI 不会重复处理题库已解决的题目。", "muted"))
        layout.addWidget(frame)
        columns = QHBoxLayout()
        frame, body = card("题库服务")
        picker = ProviderPicker()
        self.fields[("question_bank", "providers")] = picker
        body.addWidget(label("勾选启用，拖动或使用上移 / 下移调整查询顺序。", "muted"))
        body.addWidget(picker)
        form = QFormLayout()
        form.addRow("言溪 Token", self.field("question_bank", "yanxi_tokens", "secret"))
        form.addRow("LIKE Token", self.field("question_bank", "like_tokens", "secret"))
        form.addRow("Adapter 地址", self.field("question_bank", "adapter_url", "secret"))
        form.addRow("GO 授权（可选）", self.field("question_bank", "go_authorization", "secret"))
        body.addLayout(form)
        body.addWidget(label("可先填写参数，再勾选启用。各题库使用自己的凭据，未勾选时不会调用。", "muted"))
        body.addStretch()
        columns.addWidget(frame, 1)
        frame, body = card("AI 补全")
        enabled = self.field("ai", "enabled", "bool")
        enabled.setText("启用 AI，补全题库未解决的题目")
        body.addWidget(enabled)
        form = QFormLayout()
        form.addRow("服务类型", self.field("ai", "provider", "choice", choices=[("OpenAI 兼容服务", "AI"), ("硅基流动", "SiliconFlow")]))
        endpoint = self.field("ai", "endpoint")
        endpoint.setPlaceholderText("https://服务地址/v1")
        form.addRow("服务地址", endpoint)
        form.addRow("API Key", self.field("ai", "key", "secret"))
        model = self.field("ai", "model")
        model.setPlaceholderText("填写服务提供的模型名称")
        form.addRow("模型", model)
        vision = self.field("ai", "vision", "bool")
        vision.setText("模型支持图片识别")
        form.addRow("图片题", vision)
        form.addRow("首次使用前检查连接", self.field("ai", "check_connection", "bool"))
        body.addLayout(form)
        body.addWidget(label("仅在存在未解决题目时调用 AI。图片识别需要服务与模型支持；关闭后图片题留待人工处理。", "muted"))
        self.ai_check_button = button("测试 AI 连接", self.check_ai)
        body.addWidget(self.ai_check_button)
        body.addStretch()
        columns.addWidget(frame, 1)
        layout.addLayout(columns)
        frame, body = card("答案处理")
        form = QFormLayout()
        manual = self.field("desktop", "manual_fallback", "bool")
        manual.setText("服务未解决的题目，显示题目和选项供人工补全")
        form.addRow("人工补全", manual)
        random_fill = self.field("desktop", "random_fallback", "bool")
        random_fill.setText("随机填写最后仍未解决的选择题和判断题")
        form.addRow("随机补全", random_fill)
        submit = self.field("tiku", "submit", "bool")
        submit.setText("全部题目填完后自动提交章节检测（包括已启用的随机答案）")
        form.addRow("提交方式", submit)
        body.addLayout(form)
        body.addWidget(label("随机补全默认关闭，执行顺序为题库 → AI → 人工补全 → 随机补全。仅支持选择题和判断题，填空与简答保留待处理；随机答案不保证正确。是否自动提交由上面的提交开关控制。", "muted"))
        layout.addWidget(frame)
        frame, body = card("任务结束通知")
        form = QFormLayout()
        form.addRow("通知服务", self.field("notification", "provider", "choice", choices=[("关闭通知", ""), ("Server 酱", "ServerChan"), ("Qmsg", "Qmsg"), ("Bark", "Bark"), ("Telegram", "Telegram")]))
        form.addRow("通知 URL", self.field("notification", "url", "secret"))
        form.addRow("Telegram Chat ID", self.field("notification", "tg_chat_id"))
        body.addLayout(form)
        layout.addWidget(frame)
        layout.addStretch()
        picker.list.itemChanged.connect(self.update_services)
        enabled.toggled.connect(self.update_services)
        self.fields[("ai", "provider")].currentIndexChanged.connect(self.ai_preset)
        self.fields[("notification", "provider")].currentIndexChanged.connect(self.update_services)

    def ai_preset(self):
        if self.fields[("ai", "provider")].currentData() == "SiliconFlow":
            endpoint = self.fields[("ai", "endpoint")]
            if not endpoint.text().strip():
                endpoint.setText("https://api.siliconflow.cn/v1")
            model = self.fields[("ai", "model")]
            if not model.text().strip():
                model.setText("deepseek-ai/DeepSeek-R1")

    def update_services(self, *_):
        busy = self.controller.active
        for (section, key), widget in self.fields.items():
            if section in ("question_bank", "ai", "notification"):
                widget.setEnabled(not busy)
        if hasattr(self, "ai_check_button"):
            self.ai_check_button.setEnabled(not busy)

    def check_ai(self):
        try:
            self.current_config()
            isolated = defaults()
            isolated["ai"].update(self.config["ai"])
            isolated["ai"]["enabled"] = "true"
            validate(isolated, services=True)
            self.begin("check_ai", False, to_payload(isolated))
        except Exception as exc:
            self.problem(str(exc))

    def make_advanced(self):
        _, layout = self.page(True)
        groups = [
            ("请求间隔与恢复", [
                ("题库查询间隔 / 秒", "tiku", "delay", "float", 0, 3600),
                ("AI 请求间隔 / 秒", "ai", "min_interval_seconds", "float", 0, 3600),
                ("AI 请求超时 / 秒", "ai", "timeout", "int", 5, 300),
                ("AI 失败重试次数", "ai", "retries", "int", 0, 5),
                ("AI HTTP 代理（可选）", "ai", "http_proxy", "secret", 0, 0)]),
            ("GO 题库", [
                ("最小请求间隔 / 秒", "question_bank", "go_min_interval", "float", 0, 3600),
                ("最多请求次数", "question_bank", "go_retry_times", "int", 1, 20),
                ("重试退避倍数", "question_bank", "go_retry_backoff", "float", 1, 10)]),
            ("LIKE 知识库", [
                ("启用联网搜索", "question_bank", "likeapi_search", "bool", 0, 0),
                ("启用图片识别", "question_bank", "likeapi_vision", "bool", 0, 0),
                ("模型名称", "question_bank", "likeapi_model", "text", 0, 0),
                ("请求失败时重试", "question_bank", "likeapi_retry", "bool", 0, 0),
                ("最大重试次数", "question_bank", "likeapi_retry_times", "int", 0, 20)]),
            ("判断题答案识别", [
                ("表示正确的词（逗号分隔）", "tiku", "true_list", "text", 0, 0),
                ("表示错误的词（逗号分隔）", "tiku", "false_list", "text", 0, 0)]),
        ]
        for title, fields in groups:
            frame, body = card(title)
            form = QFormLayout()
            form.setVerticalSpacing(12)
            for caption, section, key, kind, low, high in fields:
                form.addRow(caption, self.field(section, key, kind, low, high))
            body.addLayout(form)
            layout.addWidget(frame)
        frame, body = card("配置迁移与备份")
        body.addWidget(label("可导入旧版 INI，自动迁移为独立的题库与 AI 设置。所有设置直接通过表单修改；点击右上角保存。密码和密钥仅保留在本次会话。", "muted"))
        row = QHBoxLayout()
        self.import_button = button("导入配置", self.import_config)
        self.export_button = button("导出完整 INI（含密钥）", self.export_config)
        row.addWidget(self.import_button)
        row.addWidget(self.export_button)
        row.addStretch()
        body.addLayout(row)
        layout.addWidget(frame)
        layout.addStretch()

    def make_monitor(self):
        _, layout = self.page()
        self.metrics = {}
        row = QHBoxLayout()
        for key, title in [("total", "章节总数"), ("success", "已完成"), ("pending", "待完成 / 未核验"), ("failed", "失败 / 跳过")]:
            frame, body = card()
            body.addWidget(label(title, "muted"))
            value = label("0", "number")
            self.metrics[key] = value
            body.addWidget(value)
            row.addWidget(frame)
        layout.addLayout(row)
        frame, body = card()
        line = QHBoxLayout()
        self.run_status = label("等待开始", "section")
        line.addWidget(self.run_status, 1)
        self.stop_button = button("停止任务", self.controller.stop)
        self.stop_button.setObjectName("danger")
        self.stop_button.setEnabled(False)
        line.addWidget(self.stop_button)
        body.addLayout(line)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        body.addWidget(self.progress)
        self.task_table = QTableWidget(0, 3)
        self.task_table.setHorizontalHeaderLabels(["课程", "章节", "状态"])
        self.task_table.verticalHeader().hide()
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.task_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.task_table.setColumnWidth(2, 170)
        body.addWidget(self.task_table)
        layout.addWidget(frame, 3)
        frame, body = card()
        row = QHBoxLayout()
        row.addWidget(label("运行日志", "section"))
        row.addStretch()
        row.addWidget(button("清空显示", lambda: self.log.clear()))
        row.addWidget(button("导出日志", self.export_logs))
        body.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2500)
        body.addWidget(self.log)
        layout.addWidget(frame, 2)

    def read_fields(self):
        for (section, key), widget in self.fields.items():
            if isinstance(widget, QCheckBox):
                value = "true" if widget.isChecked() else "false"
            elif isinstance(widget, QComboBox):
                value = str(widget.currentData())
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                value = str(widget.value())
            else:
                value = widget.text()
            self.config[section][key] = value

    def fill_fields(self):
        for (section, key), widget in self.fields.items():
            value = self.config[section].get(key, "")
            if isinstance(widget, QCheckBox):
                widget.setChecked(value.lower() == "true")
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(value)))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            else:
                widget.setText(value)
        self.update_services()

    def current_config(self, login=False):
        self.read_fields()
        validate(self.config, login=login)
        return to_payload(self.config)

    def problem(self, message):
        QMessageBox.warning(self, "请检查", message)

    def identity(self):
        c = self.config["common"]
        cookie = data_dir() / "cookies.txt"
        return (c["username"], c["password"], c["use_cookies"], cookie.stat().st_mtime_ns if cookie.exists() else None)

    def fetch_courses(self):
        try:
            # Only validate account for course listing; unused question-bank secrets may be absent.
            payload = self.current_config()
            account_only = parse_text(serialize(self.config))
            account_only["tiku"]["provider"] = ""
            account_only["question_bank"]["providers"] = ""
            account_only["ai"]["enabled"] = "false"
            account_only["notification"]["provider"] = ""
            validate(account_only, login=True)
            self.begin("courses", False, payload)
        except Exception as exc:
            self.problem(str(exc))

    def load_demo(self):
        try:
            self.begin("courses", True, to_payload(defaults()))
        except Exception as exc:
            self.problem(str(exc))

    def begin(self, action, demo, payload, selected=None):
        if self.controller.active:
            raise RuntimeError("请先停止当前任务。")
        if action == "courses":
            self.courses = []
            self.show_courses()
        self.operation = action
        self.outcome = False
        self.log_redactor = Redactor(payload)
        self.mode_label.setText("离线演示 · 示例数据" if demo else "正在检查 AI 连接" if action == "check_ai" else "正在连接超星")
        if action == "run":
            self.reset_tasks([])
            self.run_status.setText("正在准备任务…")
            self.nav.setCurrentRow(4)
        self.controller.start(dict(action=action, demo=demo, config=payload,
                                   selected=selected or [], data_dir=str(data_dir())))

    def selected_keys(self):
        return [list(course_key(self.courses[row])) for row in range(len(self.courses))
                if self.course_table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def start_tasks(self):
        try:
            selected = self.selected_keys()
            if not selected:
                raise ValueError("请至少选择一门课程。")
            if self.courses_demo:
                payload = to_payload(defaults())
            else:
                payload = self.current_config(login=True)
                if self.identity() != self.course_identity:
                    raise ValueError("登录信息或 Cookie 已改变，请重新读取课程。")
            self.begin("run", self.courses_demo, payload, selected)
        except Exception as exc:
            self.problem(str(exc))

    def show_courses(self):
        self.course_table.blockSignals(True)
        self.course_table.setRowCount(len(self.courses))
        for row, course in enumerate(self.courses):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.course_table.setItem(row, 0, check)
            for col, key in enumerate(("title", "courseId", "clazzId"), 1):
                self.course_table.setItem(row, col, QTableWidgetItem(str(course[key])))
            self.course_table.setRowHeight(row, 48)
        self.course_table.blockSignals(False)
        self.course_count.setText(f"{'演示课程' if self.courses_demo else '我的课程'} · {len(self.courses)} 门")
        self.empty_label.setVisible(not self.courses)
        self.filter_courses()
        self.update_selection()

    def filter_courses(self):
        query = self.search.text().strip().lower()
        for row, course in enumerate(self.courses):
            self.course_table.setRowHidden(row, query not in (course["title"] + str(course["courseId"])).lower())

    def check_courses(self, checked):
        for row in range(len(self.courses)):
            if not checked or not self.course_table.isRowHidden(row):
                self.course_table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def update_selection(self):
        count = len(self.selected_keys())
        self.selection_label.setText(f"已选 {count} 门课程 · 包括搜索隐藏的已选项")
        self.start_button.setEnabled(bool(count) and not self.controller.active)

    def on_busy(self, busy):
        for widget in [self.login_button, self.demo_button, self.cookie_button, self.clear_cookie_button,
                       self.all_button, self.none_button, self.import_button, self.export_button,
                       self.save_button, self.course_table, *self.fields.values()]:
            widget.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.update_selection()
        self.update_services()
        self.statusBar().showMessage("后台正在运行，停止按钮位于任务与日志页。" if busy else "准备就绪。密码与密钥默认不保存。")

    def on_event(self, event):
        kind = event.get("type")
        if kind == "log":
            self.append_log(event.get("message", ""), event.get("level", "INFO"))
        elif kind == "ai_check":
            self.outcome = True
            self.mode_label.setText("AI 连接正常")
            self.statusBar().showMessage("AI 连接正常。此测试只验证服务响应，图片识别能力需使用图片题确认。")
            self.append_log("AI 服务连接测试通过。")
        elif kind == "courses":
            self.outcome = True
            self.courses = event["courses"]
            self.courses_demo = event.get("demo", False)
            self.course_identity = self.identity()
            self.show_courses()
            self.update_cookie_label()
            self.mode_label.setText("离线演示 · 示例数据" if self.courses_demo else "课程已读取")
            self.append_log(f"已读取 {len(self.courses)} 门{'演示' if self.courses_demo else '真实'}课程。")
        elif kind == "tasks":
            self.reset_tasks(event["tasks"])
            self.run_status.setText("正在处理章节")
        elif kind == "task":
            key, status = event["id"], event["status"]
            self.task_states[key] = status
            if key in self.task_rows:
                item = QTableWidgetItem(STATUS.get(status, status))
                item.setForeground(QColor({"success": "#168c70", "failed": "#c24c5f", "running": "#4266ed"}.get(status, "#728198")))
                self.task_table.setItem(self.task_rows[key], 2, item)
            self.update_metrics()
        elif kind == "input":
            self.request_input(event)
        elif kind == "done":
            self.outcome = True
            text = f"{'演示结束' if event.get('demo') else '任务结束'} · 完成 {event['success']}，待完成 {event['pending']}，失败 {event['failed']}，跳过 {event['skipped']}"
            self.run_status.setText(text)
            self.append_log(text)
            self.mode_label.setText("离线演示 · 示例数据" if event.get("demo") else "任务已结束")
            self.progress.setValue(100)
        elif kind in ("error", "cancelled"):
            self.outcome = True
            message = event.get("message", "后台运行失败")
            self.run_status.setText("任务已停止" if kind == "cancelled" else "运行失败 · 详情见日志")
            self.mode_label.setText("已停止" if kind == "cancelled" else "运行失败")
            self.append_log(message, "ERROR")
            if self.operation in ("courses", "check_ai"):
                self.problem(self.log_redactor(message))

    def append_log(self, message, level="INFO"):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {level}  {self.log_redactor(str(message))}")

    def request_input(self, event):
        if self.controller.stopping or self.input_dialog is not None:
            return
        dialog = InteractionDialog(event, self)
        self.input_dialog = dialog
        dialog.accepted.connect(lambda: self.controller.reply(dialog.answer))
        dialog.rejected.connect(lambda: self.controller.reply(cancel=True))
        dialog.finished.connect(lambda _code: self.clear_input_dialog(dialog))
        # Keep the log scrollable while the user inspects question/options.
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.show()

    def clear_input_dialog(self, dialog):
        if self.input_dialog is dialog:
            self.input_dialog = None
        dialog.deleteLater()

    def on_finished(self, code):
        if self.input_dialog:
            self.input_dialog.reject()
        if self.operation == "run":
            for key, status in list(self.task_states.items()):
                if status in ("running", "waiting", "retry", "processed"):
                    self.task_states[key] = "stopped"
                    self.task_table.setItem(self.task_rows[key], 2, QTableWidgetItem(STATUS["stopped"]))
            self.update_metrics()
        if self.controller.stopping:
            self.run_status.setText("已停止 · 可重新开始")
            self.mode_label.setText("已停止")
            self.append_log("后台进程已停止。已发送到平台的请求不会撤销。")
        elif not self.outcome:
            self.run_status.setText("后台异常退出")
            self.mode_label.setText("运行失败")
            self.append_log(f"后台退出（{code}），未收到完成结果。", "ERROR")
        self.update_cookie_label()
        self.update_selection()

    def reset_tasks(self, tasks):
        self.task_rows = {}
        self.task_states = {}
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.task_rows[task["id"]] = row
            self.task_states[task["id"]] = "waiting"
            for col, value in enumerate((task["course"], task["title"], STATUS["waiting"])):
                self.task_table.setItem(row, col, QTableWidgetItem(value))
            self.task_table.setRowHeight(row, 40)
        self.update_metrics()

    def update_metrics(self):
        states = list(self.task_states.values())
        total = len(states)
        counts = dict(total=total, success=states.count("success"), pending=states.count("pending"),
                      failed=states.count("failed") + states.count("skipped"))
        for key, number in counts.items():
            self.metrics[key].setText(str(number))
        handled = sum(s in ("success", "failed", "skipped", "pending", "processed") for s in states)
        self.progress.setValue(int(100 * handled / total) if total else 0)

    def import_config(self):
        filename, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "INI 配置 (*.ini);;所有文件 (*)")
        if not filename:
            return
        try:
            new = parse_text(Path(filename).read_text(encoding="utf-8-sig"))
            validate(new)
            self.config = new
            self.fill_fields()
            self.statusBar().showMessage("配置已导入，密码和密钥仅保留在当前会话。")
        except Exception as exc:
            self.problem(str(exc))

    def export_config(self):
        try:
            self.current_config()
            filename, _ = QFileDialog.getSaveFileName(self, "导出完整配置（文件包含密码与密钥）", "config.ini", "INI 配置 (*.ini)")
            if filename:
                Path(filename).write_text(serialize(self.config), encoding="utf-8")
        except Exception as exc:
            self.problem(str(exc))

    def save_settings(self):
        try:
            self.current_config()
            path = data_dir() / "settings.ini"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(serialize(self.config, include_secrets=False), encoding="utf-8")
            temporary.replace(path)
            self.statusBar().showMessage("设置已保存；密码、密钥和通知地址未保存。")
        except Exception as exc:
            self.problem(str(exc))

    def update_cookie_label(self):
        exists = (data_dir() / "cookies.txt").exists()
        self.cookie_label.setText("本机已保存登录 Cookie，可用于后续登录。可点击清除退出本机会话。" if exists else "暂无 Cookie。密码不落盘；成功登录后保存本机 Cookie。")

    def import_cookie(self):
        filename, _ = QFileDialog.getOpenFileName(self, "导入 Cookie（name=value; 格式）", "", "文本 (*.txt);;所有文件 (*)")
        if not filename:
            return
        try:
            text = Path(filename).read_text(encoding="utf-8-sig").strip()
            items = [p.strip() for p in text.split(";") if p.strip()]
            if not items or any("=" not in p or not p.split("=", 1)[0].strip() for p in items):
                raise ValueError("Cookie 应为 name=value; name=value 格式。")
            (data_dir() / "cookies.txt").write_text(text, encoding="utf-8")
            self.fields[("common", "use_cookies")].setChecked(True)
            self.update_cookie_label()
            self.courses = []
            self.show_courses()
        except Exception as exc:
            self.problem(str(exc))

    def clear_cookie(self):
        try:
            (data_dir() / "cookies.txt").unlink(missing_ok=True)
            self.courses = []
            self.show_courses()
            self.update_cookie_label()
        except OSError as exc:
            self.problem(str(exc))

    def export_logs(self):
        filename, _ = QFileDialog.getSaveFileName(self, "导出已脱敏日志", "chaoxing-desktop.log", "日志 (*.log)")
        if filename:
            try:
                Path(filename).write_text(self.log_redactor(self.log.toPlainText()), encoding="utf-8")
            except OSError as exc:
                self.problem(str(exc))

    def closeEvent(self, event):
        self.controller.stop()
        if self.controller.process.state() != self.controller.process.ProcessState.NotRunning:
            self.controller.process.waitForFinished(3000)
        event.accept()


def configure_app(app):
    # Qt's offscreen Windows plugin has no native font inventory. Loading the
    # system fonts also makes screenshot tests use the same Chinese faces.
    fonts = Path(__import__("os").environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for filename in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "consola.ttf"):
        path = fonts / filename
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setApplicationName("ChaoxingDesktop")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)


def main():
    import os
    smoke_path = None
    if "--smoke-test" in sys.argv:
        smoke_path = Path(sys.argv[sys.argv.index("--smoke-test") + 1]).resolve()
        os.environ["CHAOXING_DESKTOP_DATA"] = str(smoke_path / "data")
    app = QApplication(sys.argv)
    configure_app(app)
    window = Window()
    window.show()
    if smoke_path:
        from .selftest import start_smoke
        start_smoke(app, window, smoke_path)
    return app.exec()
