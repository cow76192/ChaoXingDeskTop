"""Qt Quick application state; the worker and INI contracts stay unchanged."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from PySide6.QtWidgets import QFileDialog

from . import __version__
from .answers import option_pairs, plain_text, question_images
from .config import BANKS, Redactor, course_key, data_dir, defaults, is_secret, parse_text, serialize, to_payload, validate
from .controller import Controller
from .qml_schema import SCHEMA
from .settings import restore_credentials, serialize_settings
from .models import LogModel, LogFilter, TaskModel, STATUS, TERMINAL
from .log_store import LogStore, AsyncLogStore
from .question_model import QuestionModel, QuestionFilter
from .discussion_model import DiscussionModel, DiscussionFilter, safe_record as safe_discussion
from .activity_model import ActivityModel, ActivityFilter, safe_record as safe_activity, detail_text
from .query_result import safe_record
from .providers import PROVIDER_SPECS
from .accounts import AccountStore, parse_cookie, write_cookie
from .storage import revision, write_if_unchanged


class Backend(QObject):
    changed = Signal()
    configChanged = Signal()
    inputChanged = Signal()
    providersChanged = Signal()
    coursesChanged = Signal()
    pageRequested = Signal(int)
    questionsReset = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = defaults()
        self._closed = False
        self.startup_error = None
        self.message = "准备就绪。连接账户，或通过离线演示体验学习工作台。"
        self.tone = "info"
        self.save_state = "设置已同步"
        settings = data_dir() / "settings.ini"
        try:
            self._settings_revision = revision(settings)
        except OSError:
            self._settings_revision = None
        if settings.exists():
            try:
                self.config = parse_text(settings.read_text(encoding="utf-8-sig"))
                validate(self.config)
                restore_credentials(self.config)
            except Exception as exc:
                self.startup_error = str(exc)
                # Keep the original file until explicitly saved, including DPAPI failure.
                try:
                    validate(self.config)
                except ValueError:
                    self.config = defaults()
                self.message = "本地设置读取失败：" + self.redact(exc)
                self.tone = "danger"
                self.save_state = "读取失败 · 原文件已保留"
        self.courses = []
        self.account_store = None
        self.account_error = ""
        self.operation_account = ""
        try:
            self.account_store = AccountStore(data_dir())
            self.account_store.migrate(self.config['common']['username'].strip())
            current = self.account_store.get(self.account_store.active)
            if current:
                self.config['common']['username'] = current['username']
                self.config['common']['password'] = ""
                if self.cookie_path().exists():
                    self.config['common']['use_cookies'] = 'true'
            elif self.account_store.path.exists():
                self.config['common'].update(username='', password='', use_cookies='false')
        except Exception as exc:
            self.account_store = None
            self.account_error = "账号读取失败，原文件已保留：" + self.redact(exc)
            self.message, self.tone = self.account_error, 'danger'
        self.selected = set()
        self.search = ""
        self.demo_mode = False
        self.course_identity = None
        self._task_model = TaskModel(self)
        self._log_model = LogModel(self)
        self._log_filter = LogFilter(self._log_model, self)
        self._question_model = QuestionModel(self)
        self._question_filter = QuestionFilter(self._question_model, self)
        self._question_revision = 0
        self._discussion_model = DiscussionModel(self)
        self._discussion_filter = DiscussionFilter(self._discussion_model, self)
        self.discussion_preview = dict(content='', level='', reason='输入示例主题，预览不会发布到课程。')
        self._activity_model = ActivityModel(self)
        self._activity_filter = ActivityFilter(self._activity_model, self)
        self.activity_preview = dict(content='', reason='选择策略后预览混合问卷；不会读取课程或提交。')
        self.bank_status = "尚未检查"
        self.log_store = AsyncLogStore(self)
        self.log_store.failed.connect(self.on_log_failure)
        self.log_store.written.connect(self.on_log_written)
        self.log_save_error = ""
        self._progress_timer = QTimer(self)
        self._progress_timer.setSingleShot(True)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self.changed.emit)
        self.operation = None
        self.outcome = False
        self.mode = "本地工作台"
        self.ai_status = "尚未测试连接"
        self.interaction = {}
        self.provider_order = []
        self.sync_providers()
        self.log_redactor = Redactor({})
        self.controller = Controller(self)
        self.controller.event.connect(self.on_event)
        self.controller.finished.connect(self.on_finished)
        self.controller.busy_changed.connect(lambda _: self.changed.emit())
        self.configChanged.connect(self.refresh_redactor)
        self.refresh_redactor()

    def refresh_redactor(self):
        self._redactor = Redactor({s: dict(self.config[s]) for s in self.config.sections()})
        self._redactor_signature = self.secret_signature()

    def secret_signature(self):
        return tuple((s, k, v) for s in self.config.sections() for k, v in self.config[s].items() if is_secret(k))

    def redact(self, message):
        if getattr(self, '_redactor_signature', None) != self.secret_signature():
            self.refresh_redactor()
        return self._redactor(str(message))

    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property("QVariantMap", constant=True)
    def schema(self):
        return SCHEMA

    @Property("QVariantMap", notify=configChanged)
    def values(self):
        return {s: dict(self.config[s]) for s in self.config.sections()}

    @Property("QVariantMap", notify=changed)
    def state(self):
        """Complete snapshot for tests/tools; QML uses the small summary below."""
        return dict(self.summary, courses=self.courseRows,
                    tasks=[dict(t, statusText=STATUS.get(t["status"], t["status"])) for t in self.tasks],
                    logs="\n".join(self.logs), providers=self.providers)

    @property
    def tasks(self):
        return self._task_model.rows

    @property
    def logs(self):
        return self._log_model.snapshot()

    @Property(QObject, constant=True)
    def taskModel(self):
        return self._task_model

    @Property(QObject, constant=True)
    def questionModel(self):
        return self._question_filter

    @Property(QObject, constant=True)
    def discussionModel(self):
        return self._discussion_filter

    @Property('QVariantMap', notify=changed)
    def discussionPreview(self):
        return dict(self.discussion_preview)

    @Property(QObject, constant=True)
    def activityModel(self):
        return self._activity_filter

    @Property('QVariantMap', notify=changed)
    def activityPreview(self):
        return dict(self.activity_preview)

    @Property(QObject, constant=True)
    def logModel(self):
        return self._log_filter

    @Slot(str, str)
    def filterLogs(self, level, query):
        self._log_filter.set_filter(level, query)

    @Property("QVariantList", notify=coursesChanged)
    def courseRows(self):
        return [dict(c, selected=course_key(c) in self.selected) for c in self.courses
                if self.course_visible(c)]

    def course_visible(self, course):
        return not self.search or self.search.casefold() in (course["title"] + str(course["courseId"])).casefold()

    @Property("QVariantMap", notify=changed)
    def summary(self):
        hidden = sum(course_key(c) in self.selected and not self.course_visible(c) for c in self.courses) if self.search else 0
        counts = self._task_model.counts
        total = len(self.tasks)
        return dict(message=self.message, tone=self.tone, busy=self.controller.active,
                    stopping=self.controller.stopping and self.controller.active,
                    paused=self.controller.paused, bankStatus=self.bank_status,
                    questionCount=len(self._question_model.rows), questionEvicted=self._question_model.evicted,
                    questionRevision=self._question_revision,
                    questionStats=dict(self._question_model.stats),
                    discussionCount=len(self._discussion_model.rows), discussionEvicted=self._discussion_model.evicted,
                    discussionStats={key: sum(r['stage'] == key for r in self._discussion_model.rows)
                                     for key in ('draft', 'published', 'existing', 'publish_unknown', 'pending', 'skipped')},
                    discussionConfirmed=sum(r['task_status'] == 'confirmed' for r in self._discussion_model.rows),
                    activityCount=len(self._activity_model.rows), activityEvicted=self._activity_model.evicted,
                    activityStats={key: sum(r['stage'] == key for r in self._activity_model.rows)
                                   for key in ('draft', 'submitted', 'existing', 'submit_unknown', 'pending', 'rejected')},
                    activitySources={key: sum(a['valid'] and a['source'] == key for r in self._activity_model.rows
                                              for a in r['answers']) for key in ('ai', 'random', 'fixed')},
                    activityConfirmed=sum(r['task_status'] == 'confirmed' for r in self._activity_model.rows),
                    mode=self.mode, demo=self.demo_mode, courseCount=len(self.courses),
                    selectedCount=len(self.selected), hiddenCount=hidden,
                    courseSearch=self.search,
                    total=total, success=counts["success"], pending=counts["pending"] + counts["processed"],
                    failed=counts["failed"], progress=round(100 * sum(counts[s] for s in TERMINAL) / total) if total else 0,
                    saveState=self.save_state, aiStatus=self.ai_status,
                    cookie=self.cookie_path().exists() if self.account_store and self.account_store.active else False,
                    activeAccount=self.account_store.active if self.account_store else '',
                    accountCount=len(self.account_store.rows) if self.account_store else 0,
                    accountError=self.account_error,
                    logDirectory=str(LogStore.resolve(self.config['logging']['directory'])),
                    logSaveError=self.log_save_error)

    @Property("QVariantMap", notify=inputChanged)
    def input(self):
        return self.interaction

    @Property("QVariantList", notify=providersChanged)
    def providers(self):
        enabled = self.enabled_providers()
        return [dict(key=k, title=PROVIDER_SPECS[k].title, enabled=k in enabled,
                     secret=PROVIDER_SPECS[k].secret) for k in self.provider_order]

    def notify(self, message, tone="info"):
        self.message, self.tone = self.redact(message), tone
        self.changed.emit()

    def sync_providers(self):
        enabled = self.enabled_providers()
        self.provider_order = enabled + [k for _, k in BANKS if k not in enabled]

    def enabled_providers(self):
        return [s for s in self.config["question_bank"]["providers"].split(",") if s]

    @Property("QVariantList", notify=changed)
    def accountRows(self):
        if not self.account_store:
            return []
        return [dict(id=row['id'], label=row['label'], username=row['username'],
                     display=row['label'] + (' · Cookie 已保存' if self.account_store.cookie_path(row['id']).exists() else ' · 需登录'))
                for row in self.account_store.rows]

    def cookie_path(self):
        if not self.account_store or not self.account_store.active:
            raise ValueError(self.account_error or '请先添加或选择账号。')
        return self.account_store.cookie_path(self.account_store.active)

    def reset_account_view(self):
        self._discussion_model.clear()
        self._activity_model.clear()
        self.courses, self.selected, self.course_identity = [], set(), None
        self.search, self.demo_mode = '', False
        self.operation_account = ''
        self._task_model.reset([])
        self._question_model.clear()
        self.reset_question_filters()
        self.clear_input()
        self.mode = '本地工作台'
        self.coursesChanged.emit()
        self.configChanged.emit()
        self.changed.emit()

    def require_account_store(self):
        if not self.account_store:
            raise ValueError(self.account_error or '账号存储不可用。')
        return self.account_store

    def ensure_account(self):
        store = self.require_account_store()
        if not store.active:
            username = self.config['common']['username'].strip()
            row = store.add(username)
            self.config['common']['username'] = row['username']
            self.configChanged.emit()
            self.changed.emit()
        return store.get(store.active)

    @Slot()
    def addAccount(self):
        if self.controller.active:
            return
        def run():
            store = self.require_account_store()
            store.commit(store.rows, '')
            self.config['common'].update(username='', password='', use_cookies='false')
            self.reset_account_view()
            self.notify('填写新账号并登录，或导入该账号的 Cookie。原有账号会话已保留。')
        self.execute(run)

    @Slot(str)
    def switchAccount(self, account_id):
        if self.controller.active:
            self.notify('请先停止当前任务，再切换账号。', 'warning')
            return
        def run():
            store = self.require_account_store()
            row = store.get(account_id)
            if not row:
                raise ValueError('账号不存在。')
            if store.active == account_id:
                return
            store.commit(store.rows, account_id)
            self.config['common'].update(username=row['username'], password='',
                                         use_cookies='true' if self.cookie_path().exists() else 'false')
            self.reset_account_view()
            self.notify('已切换到 ' + row['label'] + '，点击「登录并读取」获取该账号课程。')
        self.execute(run)

    @Slot(str)
    def renameAccount(self, label):
        if self.controller.active:
            return
        def run():
            store = self.require_account_store()
            if not label.strip():
                raise ValueError('账号备注不能为空。')
            store.update(store.active, label=label.strip()[:80])
            self.changed.emit()
        self.execute(run)

    @Slot()
    def removeAccount(self):
        if self.controller.active:
            return
        def run():
            store = self.require_account_store()
            store.remove(store.active)
            self.config['common'].update(username='', password='', use_cookies='false')
            self.reset_account_view()
            self.notify('已删除当前账号及其本机 Cookie。其他账号会话已保留。')
        self.execute(run)

    @Slot(str, str, str)
    def setValue(self, section, key, value):
        if self.controller.active or not self.config.has_option(section, key):
            return
        if self.config[section][key] == value:
            return
        if section == 'common' and key == 'username' and self.account_store and self.account_store.active:
            self.notify('修改登录账号请点击「添加账号」，或切换到已有账号。', 'warning')
            return
        self.config[section][key] = value
        self._closed = False
        if section == "ai":
            self.ai_status = "参数已修改 · 请重新测试"
            if key == "provider" and value == "SiliconFlow":
                self.config["ai"]["endpoint"] = "https://api.siliconflow.cn/v1"
                self.config["ai"]["model"] = "deepseek-ai/DeepSeek-R1"
        self.save_state = "有修改 · 未保存"
        self.configChanged.emit()
        self.changed.emit()

    @Slot(str, bool)
    def toggleProvider(self, key, checked):
        if self.controller.active or key not in self.provider_order:
            return
        enabled = set(self.enabled_providers())
        enabled.add(key) if checked else enabled.discard(key)
        self.setValue("question_bank", "providers", ",".join(k for k in self.provider_order if k in enabled))
        self.providersChanged.emit()

    @Slot(int, int)
    def moveProvider(self, index, delta):
        target = index + delta
        if self.controller.active or not (0 <= index < len(self.provider_order) and 0 <= target < len(self.provider_order)):
            return
        self.provider_order[index], self.provider_order[target] = self.provider_order[target], self.provider_order[index]
        enabled = self.enabled_providers()
        self.setValue("question_bank", "providers", ",".join(k for k in self.provider_order if k in enabled))
        self.changed.emit()
        self.providersChanged.emit()

    @Slot(str)
    def searchCourses(self, value):
        self.search = value
        self.coursesChanged.emit()
        self.changed.emit()

    @Slot(str, str, bool)
    def selectCourse(self, course, clazz, checked):
        key = (course, clazz)
        if self.controller.active or key not in {course_key(c) for c in self.courses}:
            return
        self.selected.add(key) if checked else self.selected.discard(key)
        self.coursesChanged.emit()
        self.changed.emit()

    @Slot(bool)
    def selectVisible(self, checked):
        if self.controller.active:
            return
        keys = {course_key(c) for c in self.courses if self.course_visible(c)}
        self.selected.update(keys) if checked else self.selected.difference_update(keys)
        self.coursesChanged.emit()
        self.changed.emit()

    def identity(self):
        c = self.config["common"]
        cookie = self.cookie_path() if self.account_store and self.account_store.active else None
        return (self.account_store.active if self.account_store else '', c["username"], c["password"],
                c["use_cookies"], cookie.stat().st_mtime_ns if cookie and cookie.exists() else None)

    def begin(self, action, demo=False, selected=None, topic=''):
        if self.controller.active:
            raise ValueError("请先停止当前任务。")
        config = defaults() if demo else self.config
        if action == "courses" and not demo:
            account = defaults()
            for key in ('username', 'password', 'use_cookies'):
                account['common'][key] = self.config['common'][key]
            cookie = self.cookie_path() if self.account_store and self.account_store.active else data_dir() / 'no-account-cookie'
            validate(account, login=True, cookie_path=cookie)
            self.ensure_account()
            account['common']['username'] = self.config['common']['username']
            config = account
        else:
            validate(config)
        if action == "run" and not demo:
            if self.identity() != self.course_identity:
                raise ValueError("登录信息已改变，请重新读取课程（包含本机会话文件变化）。")
            validate(config, login=True, cookie_path=self.cookie_path())
        if action == "check_bank":
            target = selected[0]
            isolated = parse_text(serialize(config))
            isolated["question_bank"]["providers"] = target
            isolated["ai"]["enabled"] = "false"
            isolated["notification"]["provider"] = ""
            validate(isolated, services=True)
            config = isolated
        if action == "check_ai":
            ai_only = parse_text(serialize(config))
            ai_only["ai"]["enabled"] = "true"
            ai_only["question_bank"]["providers"] = ""
            ai_only["notification"]["provider"] = ""
            validate(ai_only, services=True)
        if action == 'discussion_preview':
            isolated = parse_text(serialize(config))
            isolated['question_bank']['providers'] = ''
            isolated['notification']['provider'] = ''
            if isolated['ai']['enabled'] != 'true':
                raise ValueError('请先启用并配置 AI 服务，或选择固定回复好。')
            validate(isolated, services=True)
            config = isolated
        if action == 'activity_preview':
            isolated = parse_text(serialize(config))
            isolated['question_bank']['providers'] = ''
            isolated['notification']['provider'] = ''
            if isolated['ai']['enabled'] != 'true':
                raise ValueError('请先启用并配置 AI，或选择随机选择与固定好。')
            validate(isolated, services=True)
            config = isolated
        self.operation, self.outcome = action, False
        self.operation_account = self.account_store.active if self.account_store and not demo and action in ('courses', 'run') else ''
        payload = to_payload(config)
        self.log_redactor = Redactor(payload)
        if action == "courses":
            self.courses, self.selected = [], set()
            self.demo_mode = demo
            self.coursesChanged.emit()
        if action == "run":
            self._task_model.reset([])
            self._question_model.clear()
            self._discussion_model.clear()
            self._activity_model.clear()
            self.reset_question_filters()
            self.pageRequested.emit(4)
        self.mode = "离线演示 · 示例数据" if demo else "检查 AI 连接" if action == "check_ai" else "正在连接超星"
        self.notify("正在读取课程…" if action == "courses" else "正在检查 AI 连接…" if action == "check_ai" else "正在准备任务…")
        command = dict(action=action, demo=demo, config=payload, selected=selected or [], data_dir=str(data_dir()))
        if action == 'discussion_preview':
            command['topic'] = topic
            self.mode = '讨论预览 · 请求已配置 AI 服务'
            self.notify('正在生成讨论预览，将请求已配置 AI 服务，不访问课程或发布接口。')
        if action == 'activity_preview':
            command['topic'] = topic
            self.mode = '投票／问卷预览 · 请求已配置 AI 服务'
            self.notify('正在生成活动示例预览，不读取课程、不提交、不写入活动记录。')
        if self.operation_account:
            command.update(account_id=self.operation_account,
                           account_uid=self.account_store.get(self.operation_account)['uid'])
        self.controller.start(command)

    @Slot()
    def loadDemo(self):
        self.execute(lambda: self.begin("courses", True))

    @Slot()
    def fetchCourses(self):
        self.execute(lambda: self.begin("courses"))

    @Slot()
    def startTasks(self):
        def start():
            if not self.selected:
                raise ValueError("请至少选择一门课程。")
            self.begin("run", self.demo_mode, [list(k) for k in sorted(self.selected)])
        self.execute(start)

    @Slot(bool, str)
    def filterQuestions(self, pending_only, task):
        self._question_filter.set_filter(pending_only, task)

    def reset_question_filters(self):
        self._question_filter.set_filter(False, '')
        self._question_revision += 1
        self.questionsReset.emit()

    @Slot(str, result='QVariantMap')
    def questionDetail(self, record_id):
        row = self._question_model.row_index(record_id)
        return self._question_model.data(self._question_model.index(row)) if row is not None else {}

    @Slot(str, str)
    def filterDiscussions(self, query, stage):
        self._discussion_filter.set_filter(query, stage)

    @Slot(str, str)
    def filterActivities(self, query, stage):
        self._activity_filter.set_filter(query, stage)

    @Slot(str, result='QVariantMap')
    def activityDetail(self, record_id):
        return self._activity_model.detail(record_id)

    @Slot(str)
    def copyActivity(self, record_id):
        from PySide6.QtGui import QGuiApplication
        record = self._activity_model.detail(record_id)
        if record:
            QGuiApplication.clipboard().setText(record['detailText'])
            self.notify('活动逐题草稿已复制。')

    @Slot(str)
    def previewActivity(self, topic):
        def run():
            if self.controller.active:
                raise ValueError('请先结束当前任务，再预览。')
            if not topic.strip() or len(topic) > 2000:
                raise ValueError('请填写不超过 2000 字符的示例文本题干。')
            validate(self.config)
            cfg = self.config['activity']
            if cfg['choice_strategy'] == 'random' and cfg['text_strategy'] == 'fixed_good':
                from types import SimpleNamespace
                from .activity import ActivityGenerator, preview_context
                from .answers import AnswerRouter
                ctx = preview_context(topic.strip())
                answers = ActivityGenerator(AnswerRouter(to_payload(self.config), SimpleNamespace(control=None))).generate(ctx, cfg)
                record = dict(title=ctx.title, course='', chapter='', submit_status='draft', task_status='pending',
                              reason='完全本地 · AI 调用 0 次 · 不读取课程或提交', questions=ctx.questions, answers=answers)
                self.activity_preview = dict(content=detail_text(record), reason=record['reason'])
                self.changed.emit()
                return
            self.begin('activity_preview', topic=topic.strip())
        self.execute(run)

    @Slot(str, result='QVariantMap')
    def discussionDetail(self, record_id):
        return self._discussion_model.detail(record_id)

    @Slot(str)
    def previewDiscussion(self, topic):
        def run():
            if self.controller.active:
                raise ValueError('请先结束当前任务，再生成预览。')
            if not topic.strip() or len(topic) > 12000:
                raise ValueError('请填写不超过 12000 字符的示例讨论主题。')
            if self.config['discussion']['reply_level'] == 'fixed_good':
                self.discussion_preview = dict(content='好', level='fixed_good', reason='本地固定回复 · 模型调用 0 次 · 不发布')
                self.changed.emit()
                return
            self.begin('discussion_preview', topic=topic.strip())
        self.execute(run)

    @Slot(str)
    def copyDiscussion(self, record_id):
        from PySide6.QtGui import QGuiApplication
        record = self._discussion_model.detail(record_id)
        if record.get('content'):
            QGuiApplication.clipboard().setText(record['content'])
            self.notify('讨论正文已复制。')

    @Slot()
    def pause(self):
        self.controller.pause()
        self.notify('暂停后续调度与答题写入；在途请求和当前媒体可能继续。' if self.controller.paused else '已请求恢复，后续任务将复核会话。')

    @Slot()
    def offlineCheck(self):
        if self.controller.active:
            return
        def run():
            from .diagnostics import offline_check
            self.bank_status = offline_check()
            self.notify(self.bank_status, 'success')
        self.execute(run)

    @Slot(str)
    def checkBank(self, provider):
        if provider in PROVIDER_SPECS:
            self.execute(lambda: self.begin('check_bank', selected=[provider]))

    @Slot(str)
    def definitionAction(self, action):
        if self.controller.active:
            return
        def run():
            from .declarative import TEMPLATE, validate_definition
            import json
            if action == 'import':
                name, _ = QFileDialog.getOpenFileName(None, '导入声明式 JSON（不执行 handler）', '', 'JSON (*.json)')
                if not name:
                    return
                text = Path(name).read_text(encoding='utf-8-sig')
                definition = validate_definition(text)
                self.setValue('question_bank', 'declarative_definition', json.dumps(definition, ensure_ascii=False))
                self.notify('已导入受限题库定义，Token 需单独填写并保存。', 'success')
            else:
                text = self.config['question_bank']['declarative_definition']
                definition = validate_definition(text) if text.strip() else TEMPLATE
                name, _ = QFileDialog.getSaveFileName(None, '导出不含 Token 的 JSON 模板', 'question-bank.json', 'JSON (*.json)')
                if name:
                    Path(name).write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding='utf-8')
        self.execute(run)

    @Slot()
    def checkAi(self):
        self.execute(lambda: self.begin("check_ai"))

    def execute(self, command):
        try:
            command()
        except Exception as exc:
            self.notify(exc, "danger")

    @Slot()
    def stop(self):
        if not self.controller.active:
            return
        self.clear_input()
        self.controller.stop()
        self.notify("正在停止后台任务…", "warning")

    def append_log(self, message, level="INFO"):
        line = f"{datetime.now():%H:%M:%S}  {str(level)[:10]:7}  {self.redact(self.log_redactor(str(message)))}"
        if len(line) > LogModel.MAX_LINE_CHARS:
            line = line[:LogModel.MAX_LINE_CHARS - 20] + " …[日志过长，已截断]"
        self._log_model.append(line)
        try:
            self.log_store.append(self.config['logging']['directory'], line)
        except (OSError, ValueError) as exc:
            self.on_log_failure(str(exc))

    @Slot(str)
    def on_log_failure(self, message):
        error = self.redact('日志保存失败：' + message)
        if error != self.log_save_error:
            self.log_save_error = error
            self.notify(error, 'danger')

    @Slot()
    def on_log_written(self):
        if self.log_save_error:
            self.log_save_error = ''
            self.changed.emit()

    def on_event(self, event):
        if event.get('run_id', self.controller.run_id) != self.controller.run_id:
            return
        kind = event.get("type")
        if kind in ('activity_result', 'activity_preview'):
            if event['record']['run_id'] != self.controller.run_id:
                return
            record = safe_activity(event['record'], lambda text: self.redact(self.log_redactor(text)))
            if kind == 'activity_preview':
                self.outcome = True
                self.activity_preview = dict(content=detail_text(record), reason=record['reason'])
                self.mode = '投票／问卷预览已完成'
                self.notify('预览已完成，请逐题检查来源与校验结果。', 'success')
            elif self._activity_model.upsert(record) and not self._progress_timer.isActive():
                self._progress_timer.start()
            return
        if kind == 'discussion_result':
            if event['record']['run_id'] != self.controller.run_id:
                return
            record = safe_discussion(event['record'], lambda text: self.redact(self.log_redactor(text)))
            if self._discussion_model.upsert(record) and not self._progress_timer.isActive():
                self._progress_timer.start()
            return
        if kind == 'discussion_preview':
            self.outcome = True
            self.discussion_preview = dict(content=event['content'], level=event['level'],
                                           reason='已配置 AI 服务生成 · 仅预览，不会发布')
            self.mode = '讨论预览已完成'
            self.notify('讨论预览已生成，请核对内容。', 'success')
            return
        if kind == 'session_ready':
            if (not self.account_store or event.get('account_id') != self.operation_account
                    or self.operation_account != self.account_store.active):
                return
            def remember():
                uid = str(event['uid'])
                row = self.account_store.get(self.operation_account)
                if not uid or not row or (row['uid'] and row['uid'] != uid):
                    raise ValueError('平台会话与当前账号不一致，请重新读取课程。')
                identity = self.identity()
                self.account_store.update(self.operation_account, uid=uid)
                self.config['common']['use_cookies'] = 'true'
                # A verified worker login rewrites its Cookie file even when the
                # user did not change accounts. Trust only that exact revision;
                # external edits and changed login settings still invalidate courses.
                if (self.operation == 'run' and self.controller.active and not self.demo_mode
                        and self.course_identity is not None
                        and identity[:4] == self.course_identity[:4]
                        and identity[-1] is not None
                        and event.get('cookie_mtime_ns') == identity[-1]):
                    self.course_identity = (*identity[:3], 'true', identity[-1])
                self.configChanged.emit()
                self.changed.emit()
            self.execute(remember)
            return
        if kind == 'question_result':
            # Refresh once per record, rather than scanning every setting for
            # each string in the nested result and its provider attempts.
            if self._redactor_signature != self.secret_signature():
                self.refresh_redactor()
            redactor = self._redactor
            record = safe_record(event['record'], lambda text: redactor(self.log_redactor(text)))
            if self._question_model.upsert(record):
                self._question_revision += 1
                if not self._progress_timer.isActive():
                    self._progress_timer.start()
            return
        if kind == 'control':
            self.controller.paused = event['paused']
            self.changed.emit()
            return
        if kind == 'bank_check':
            self.outcome = True
            self.bank_status = event['message']
            self.notify(self.bank_status, 'success' if event.get('ok') else 'warning')
            return
        if kind == "log":
            self.append_log(event.get("message", ""), event.get("level", "INFO"))
            return
        elif kind == "courses":
            self.outcome = True
            self.courses = event["courses"]
            self.demo_mode = event.get("demo", False)
            self.course_identity = self.identity()
            self.coursesChanged.emit()
            self.mode = "离线演示 · 示例数据" if self.demo_mode else "课程已读取"
            self.notify(f"已读取 {len(self.courses)} 门{'演示' if self.demo_mode else '真实'}课程。", "success")
        elif kind == "tasks":
            self._task_model.reset([dict(t, status="waiting") for t in event["tasks"]])
            self.notify("正在处理章节。本轮进度不表示课程学分完成比例。")
        elif kind == "task":
            if self._task_model.update_status(event["id"], event["status"]) and not self._progress_timer.isActive():
                self._progress_timer.start()
            return
        elif kind == "media":
            self._task_model.update_media(event['id'], event)
            return
        elif kind == "ai_check":
            self.outcome = True
            self.ai_status = "服务响应正常 · 图片识别仍需实测"
            self.notify("AI 连接测试通过。", "success")
        elif kind == "input":
            if self.controller.stopping:
                return
            question = event.get("question", {})
            pairs = [("正确", "正确"), ("错误", "错误")] if question.get("type") == "judgement" else option_pairs(question)
            self.interaction = dict(kind=event.get("kind", "question"), type=question.get("type", "text"),
                                    message=plain_text(event.get("message", "")), title=plain_text(question.get("title", "")),
                                    options=[dict(value=k, label=plain_text(v)) for k, v in pairs],
                                    images=question_images(question), choices=event.get("choices", []),
                                    blankCount=question.get('blank_count') if type(question.get('blank_count')) is int else 0,
                                    random=event.get("random_fallback", False))
            self.inputChanged.emit()
            self.notify("等待人工处理，请检查题目后使用答案或跳过。", "warning")
        elif kind == "done":
            self.outcome = True
            self.mode = "离线演示 · 示例数据" if event.get("demo") else "任务已结束"
            text = f"{'演示结束' if event.get('demo') else '任务结束'} · 已完成章节 {event['success']}，待完成章节 {event['pending']}，失败章节 {event['failed']}，跳过章节 {event['skipped']}"
            self.append_log(text)
            self.notify(text + ("。待完成 / 未核验章节请在平台确认。" if event['pending'] else ""), "danger" if event['failed'] else "warning" if event['pending'] or event['skipped'] else "success")
        elif kind in ("error", "cancelled"):
            self.outcome = True
            self.mode = "已停止" if kind == "cancelled" else "运行失败"
            if self.operation == "check_ai":
                self.ai_status = "测试未通过 · 请检查参数"
            self.append_log(event.get("message", "后台运行失败"), "ERROR")
            self.notify(event.get("message", "后台运行失败"), "warning" if kind == "cancelled" else "danger")
        self.changed.emit()

    def clear_input(self):
        self.interaction = {}
        self.inputChanged.emit()

    @Slot(str, bool)
    def reply(self, answer, cancel):
        if not self.interaction or not self.controller.active or self.controller.stopping:
            return
        self.controller.reply(answer, cancel)
        self.clear_input()

    def on_finished(self, code):
        self.clear_input()
        for task in self.tasks:
            if task["status"] not in TERMINAL:
                self._task_model.update_status(task["id"], "stopped")
        self._progress_timer.stop()
        self._log_model.flush()
        if self.controller.stopping:
            self.mode = "已停止"
            self.notify("后台已停止。已发送到平台的请求不会撤销，可重新开始。", "warning")
        elif not self.outcome:
            self.mode = "后台异常退出"
            self.notify(f"后台退出（{code}），未收到完成结果。请检查软件目录及日志。", "danger")
        self.changed.emit()

    @Slot(result=bool)
    def save(self):
        if self.controller.active:
            return False
        try:
            self._closed = False
            validate(self.config)
            path = data_dir() / "settings.ini"
            self._settings_revision = write_if_unchanged(path, serialize_settings(self.config).encode('utf-8'), self._settings_revision)
            self.startup_error = None
            self.save_state = "设置已保存"
            self.notify("设置及服务凭据已在本机保存。登录密码仅用于当前会话。", "success")
            return True
        except Exception as exc:
            self.save_state = "保存失败 · 未保存"
            self.notify(exc, "danger")
            return False

    @Slot(result=bool)
    def close(self):
        return self._close(False)

    @Slot(result=bool)
    def discardAndClose(self):
        return self._close(True)

    def _close(self, discard):
        if self._closed:
            return True
        # Validate/save before stopping, so a failed save preserves the live window.
        if not self.startup_error and not discard:
            try:
                validate(self.config)
                path = data_dir() / "settings.ini"
                self._settings_revision = write_if_unchanged(path, serialize_settings(self.config).encode('utf-8'), self._settings_revision)
            except Exception as exc:
                self.save_state = "保存失败 · 未保存"
                self.notify(exc, "danger")
                return False
        self.stop()
        if self.controller.active:
            if not self.controller.process.waitForFinished(3000):
                self.controller.process.kill()
                self.controller.process.waitForFinished(1000)
        if not self.log_store.close(2, force=discard) and not discard:
            self.notify('日志尚未写完，可稍后重试或放弃修改并退出。', 'warning')
            return False
        self._closed = True
        return True

    @Slot(str)
    def fileAction(self, action):
        if self.controller.active and action not in ("export_logs",):
            return
        def run():
            if action in ("import_config", "import_cookie"):
                title = "导入 INI 配置" if action == "import_config" else "导入 Cookie（name=value; 格式）"
                name, _ = QFileDialog.getOpenFileName(None, title, "", "配置 / 文本 (*.ini *.txt);;所有文件 (*)")
                if not name:
                    return
                text = Path(name).read_text(encoding="utf-8-sig")
                if action == "import_config":
                    new = parse_text(text)
                    restore_credentials(new)
                    validate(new)
                    store = self.require_account_store()
                    if new['common']['username'] != self.config['common']['username']:
                        store.commit(store.rows, '')
                    self.config = new
                    self.reset_account_view()
                    self.sync_providers()
                    self.providersChanged.emit()
                    self.ai_status = "配置已导入 · 请重新测试"
                    self.save_state = "有修改 · 未保存"
                    self.configChanged.emit()
                else:
                    cookies = parse_cookie(text)
                    row = self.ensure_account()
                    write_cookie(self.cookie_path(), cookies, row['uid'])
                    self.setValue("common", "use_cookies", "true")
                    self.reset_account_view()
                self.notify("已导入，请检查设置。", "success")
            elif action == "clear_cookie":
                self.cookie_path().unlink(missing_ok=True)
                self.setValue('common', 'use_cookies', 'false')
                self.reset_account_view()
                self.notify("当前账号的本机 Cookie 已清除，其他账号会话已保留。")
            elif action in ("export_config", "export_logs"):
                is_config = action == "export_config"
                if is_config:
                    validate(self.config)
                name, _ = QFileDialog.getSaveFileName(None, "导出完整 INI（包含密码与密钥）" if is_config else "导出已脱敏日志", "config.ini" if is_config else "chaoxing-desktop.log", "INI (*.ini)" if is_config else "日志 (*.log)")
                if name:
                    Path(name).write_text(serialize(self.config) if is_config else self.redact(self.log_redactor("\n".join(self.logs))), encoding="utf-8")
                    self.notify("文件已导出。", "success")
        self.execute(run)

    @Slot()
    def clearLogs(self):
        self._log_model.clear()

    @Slot()
    def chooseLogDirectory(self):
        if self.controller.active:
            return
        directory = QFileDialog.getExistingDirectory(None, "选择日志保存目录", self.summary['logDirectory'])
        if directory:
            self.setValue('logging', 'directory', directory)

    @Slot()
    def deleteLogs(self):
        def run():
            count = self.log_store.delete(self.config['logging']['directory'])
            self._log_model.clear()
            self.log_save_error = ""
            self.notify(f"已删除当前日志目录中的 {count} 个应用日志文件，并清空显示。后续日志会新建文件。", "success")
        self.execute(run)
