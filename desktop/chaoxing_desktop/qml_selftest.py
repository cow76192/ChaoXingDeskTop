"""Offline smoke for the default QML launcher and the actual worker executable."""
import json
import time

from PySide6.QtCore import QObject, QTimer


def check_accounts(backend):
    """Exercise frozen DPAPI and switching with synthetic data only."""
    from .accounts import AccountStore, read_cookie, write_cookie
    from .config import data_dir
    from .qml_backend import Backend
    backend.setValue('common', 'username', 'offline-account-a')
    first = backend.ensure_account()
    write_cookie(backend.cookie_path(), {'_uid': 'offline-a', 'session': 'OFFLINE_SESSION_A'})
    backend.account_store.update(first['id'], uid='offline-a', label='离线验收账号 A')
    backend.addAccount()
    backend.setValue('common', 'username', 'offline-account-b')
    second = backend.ensure_account()
    write_cookie(backend.cookie_path(), {'_uid': 'offline-b', 'session': 'OFFLINE_SESSION_B'})
    backend.account_store.update(second['id'], uid='offline-b', label='离线验收账号 B')
    backend.on_event(dict(type='courses', demo=False, courses=[dict(courseId='offline', clazzId='b', title='离线隔离验收')]))
    backend.selectVisible(True)
    backend.controller.active = True
    try:
        backend.switchAccount(first['id'])
        assert backend.summary['activeAccount'] == second['id'], 'Switch was not locked during run'
    finally:
        backend.controller.active = False
    backend.switchAccount(first['id'])
    assert not backend.courses and not backend.selected, 'Previous account courses leaked'
    assert read_cookie(backend.cookie_path())['session'] == 'OFFLINE_SESSION_A'
    assert b'OFFLINE_SESSION_A' not in backend.cookie_path().read_bytes(), 'Cookie saved in plaintext'
    reopened = Backend()
    assert reopened.summary['activeAccount'] == first['id'], reopened.message
    assert reopened.config['common']['use_cookies'] == 'true'
    assert len(reopened.accountRows) == 2
    reopened.switchAccount(second['id'])
    assert read_cookie(reopened.cookie_path())['session'] == 'OFFLINE_SESSION_B'
    reopened.switchAccount(first['id'])
    reopened.deleteLater()
    legacy = AccountStore(data_dir() / 'synthetic-legacy')
    legacy.root.mkdir()
    (legacy.root / 'cookies.txt').write_text('_uid=offline-old; session=OFFLINE_LEGACY', encoding='utf-8')
    legacy.migrate('offline-old')
    assert not (legacy.root / 'cookies.txt').exists(), 'Legacy plaintext retained after migration'
    assert read_cookie(legacy.cookie_path(legacy.active))['session'] == 'OFFLINE_LEGACY'


def start_smoke(app, engine, backend, destination):
    destination.mkdir(parents=True, exist_ok=True)
    root = engine.rootObjects()[0]
    phase = [0]
    started = time.monotonic()
    timer = QTimer(backend)
    timer.setInterval(100)
    warnings = engine.load_warnings

    def snapshot(name):
        image = root.grabWindow()
        assert not image.isNull(), "QML screenshot is empty"
        assert image.save(str(destination / (name + ".png"))), "Cannot save QML screenshot"

    def finish(success, message):
        timer.stop()
        result = dict(success=success, message=message, warnings=warnings, multiAccount=success)
        (destination / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        root.close()
        app.exit(0 if success else 1)

    def tick():
        try:
            if time.monotonic() - started > 45:
                raise AssertionError("QML smoke timed out")
            if phase[0] == 0:
                snapshot("首次启动")
                check_accounts(backend)
                snapshot('多账号登录')
                backend.loadDemo()
                phase[0] = 1
            elif phase[0] == 1 and not backend.controller.active:
                assert len(backend.courses) == 3, backend.message
                backend.selectVisible(True)
                snapshot("课程与账号")
                backend.searchCourses("Python")
                assert backend.state["hiddenCount"] == 2
                backend.searchCourses("")
                backend.startTasks()
                phase[0] = 2
            elif phase[0] == 2 and backend.tasks:
                snapshot("任务运行中")
                phase[0] = 3
            elif phase[0] == 3 and not backend.controller.active:
                assert backend.state["success"] == 9, backend.message
                snapshot("任务与日志")
                assert backend.summary['questionCount'] == 3, backend.summary
                tabs = root.findChild(QObject, 'resultTabs')
                tabs.setProperty('currentIndex', 1)
                app.processEvents()
                snapshot('逐题结果')
                tabs.setProperty('currentIndex', 0)
                backend.offlineCheck()
                assert '未连接真实服务' in backend.bank_status
                backend.startTasks()
                phase[0] = 4
            elif phase[0] == 4 and backend.tasks:
                backend.stop()
                phase[0] = 5
            elif phase[0] == 5 and not backend.controller.active:
                assert any(t["status"] == "stopped" for t in backend.tasks)
                backend.setValue("ai", "key", "QML_SMOKE_SECRET")
                backend.setValue("question_bank", "yanxi_tokens", "QML_SMOKE_TOKEN")
                backend.setValue("common", "speed", "1.5")
                backend.setValue("common", "use_cookies", "true")
                backend.toggleProvider("TikuGo", True)
                backend.toggleProvider("TikuYanxi", True)
                assert backend.save(), backend.message
                from .config import data_dir
                text = (data_dir() / "settings.ini").read_text(encoding="utf-8")
                assert "QML_SMOKE_SECRET" not in text and "QML_SMOKE_TOKEN" not in text
                from .qml_backend import Backend
                reopened = Backend()
                assert reopened.startup_error is None, reopened.startup_error
                assert reopened.config["ai"]["key"] == "QML_SMOKE_SECRET"
                assert reopened.config["question_bank"]["yanxi_tokens"] == "QML_SMOKE_TOKEN"
                assert reopened.config["common"]["speed"] == "1.5"
                assert reopened.config["common"]["use_cookies"] == "true"
                reopened.deleteLater()
                root.setProperty("pageIndex", 1)
                phase[0] = 6
            elif phase[0] == 6:
                snapshot("学习设置")
                root.setProperty("pageIndex", 2)
                phase[0] = 7
            elif phase[0] == 7:
                snapshot("题库与AI")
                root.setWidth(980); root.setHeight(700)
                phase[0] = 8
            elif phase[0] == 8:
                snapshot("services-980")
                root.setWidth(1600); root.setHeight(900)
                phase[0] = 9
            elif phase[0] == 9:
                snapshot("services-1600")
                root.setWidth(1200); root.setHeight(840)
                phase[0] = 10
            elif phase[0] == 10:
                snapshot("services-1200")
                root.setProperty("pageIndex", 3)
                phase[0] = 11
            elif phase[0] == 11:
                snapshot("高级设置")
                # Show an offline interaction using the real QML dialog.
                backend.controller.active = True
                backend.controller.stopping = False
                backend.on_event(dict(type="input", kind="question", question=dict(type="multiple", title="离线示例：请选择正确的操作", options="A. 先读取课程\nB. 选择所需课程\nC. 检查任务日志")))
                phase[0] = 12
            elif phase[0] == 12:
                assert root.findChild(QObject, "manualDialog").property("visible"), "Manual dialog did not open"
                snapshot("人工补全")
                backend.clear_input()
                backend.controller.active = False
                assert not warnings, "QML warnings: " + "\n".join(warnings[:6])
                finish(True, "QML and worker: multiple encrypted accounts, switch isolation/lock, restart, legacy Cookie migration, demo (9 chapters), stop, hidden selections, encrypted credential restoration and page screenshots passed.")
        except Exception as exc:
            finish(False, str(exc))
    timer.timeout.connect(tick)
    timer.start()
