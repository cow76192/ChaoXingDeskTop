"""Real Qt/QProcess flow, no network or user account. Run from desktop folder."""
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from chaoxing_desktop.gui import Window, configure_app


def wait_until(predicate, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("GUI smoke timed out")


with tempfile.TemporaryDirectory() as directory:
    os.environ["CHAOXING_DESKTOP_DATA"] = directory
    app = QApplication([])
    configure_app(app)
    window = Window()
    window.show()
    assert not window.start_button.isEnabled()
    window.nav.setCurrentRow(2)
    assert not window.fields[("ai", "enabled")].isChecked()
    # Reproduce the reported default state: every service can be configured first.
    for key in [("question_bank", "yanxi_tokens"), ("question_bank", "like_tokens"),
                ("question_bank", "adapter_url"), ("question_bank", "go_authorization"),
                ("ai", "endpoint"), ("ai", "key"), ("ai", "model"),
                ("notification", "url"), ("notification", "tg_chat_id")]:
        widget = window.fields[key]
        assert widget.isEnabled()
        widget.setFocus()
        QTest.keyClicks(widget, "EDITABLE")
        assert widget.text() == "EDITABLE", key
        widget.clear()
    assert window.ai_check_button.isEnabled()
    assert not window.fields[("desktop", "random_fallback")].isChecked()
    window.load_demo()
    assert not window.fields[("ai", "key")].isEnabled()
    assert not window.ai_check_button.isEnabled()
    wait_until(lambda: not window.controller.active)
    assert window.fields[("ai", "key")].isEnabled()
    assert len(window.courses) == 3
    window.check_courses(True)
    window.start_tasks()
    wait_until(lambda: not window.controller.active)
    assert window.metrics["success"].text() == "9"
    assert "演示结束" in window.run_status.text()
    screenshots = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "plans/screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(screenshots / "任务与日志.png"))
    window.nav.setCurrentRow(0)
    app.processEvents()
    window.grab().save(str(screenshots / "课程与账号.png"))
    # Verify an in-flight task can be stopped and started again.
    window.start_tasks()
    wait_until(lambda: bool(window.task_rows))
    window.controller.stop()
    wait_until(lambda: not window.controller.active)
    assert "已停止" in window.run_status.text()
    assert all(s not in ("running", "waiting", "retry") for s in window.task_states.values())
    window.fields[("common", "password")].setText("SHOULD_NOT_PERSIST")
    window.fields[("desktop", "random_fallback")].setChecked(True)
    window.save_settings()
    assert "SHOULD_NOT_PERSIST" not in (Path(directory) / "settings.ini").read_text(encoding="utf-8")
    from chaoxing_desktop.config import parse_text
    assert parse_text((Path(directory) / "settings.ini").read_text(encoding="utf-8"))["desktop"]["random_fallback"] == "true"
    # Every advanced setting is a form field and survives navigation.
    window.nav.setCurrentRow(3)
    assert not hasattr(window, "editor")
    window.fields[("ai", "timeout")].setValue(90)
    window.nav.setCurrentRow(0)
    window.nav.setCurrentRow(3)
    assert window.current_config()["ai"]["timeout"] == "90"
    window.grab().save(str(screenshots / "高级设置.png"))
    window.nav.setCurrentRow(2)
    for width, height in ((980, 700), (1200, 840), (1600, 900)):
        window.resize(width, height)
        app.processEvents()
        assert window.grab().save(str(screenshots / f"services-{width}.png"))
    window.resize(1200, 840)
    window.fields[("question_bank", "providers")].setText(" TikuGo, TikuYanxi ")
    assert window.fields[("question_bank", "providers")].text() == "TikuGo,TikuYanxi"
    window.update_services()
    assert window.fields[("question_bank", "yanxi_tokens")].isEnabled()
    assert window.fields[("question_bank", "like_tokens")].isEnabled()
    window.fields[("ai", "enabled")].setChecked(True)
    assert window.fields[("ai", "endpoint")].isEnabled()
    app.processEvents()
    window.grab().save(str(screenshots / "随机补全设置.png"))
    window.resize(1600, 1100)
    window.stack.currentWidget().verticalScrollBar().setValue(0)
    app.processEvents()
    window.grab().save(str(screenshots / "题库与AI.png"))
    # Manual answering carries the question and selectable options in the dialog.
    window.controller.stopping = False
    window.request_input({"kind": "question", "question": {"title": "测试题", "type": "single", "options": "A 第一项\nB 第二项"}})
    dialog = window.input_dialog
    assert len(dialog.inputs) == 2
    dialog.inputs[0][0].setChecked(True)
    dialog.inputs[1][0].setChecked(True)
    assert not dialog.inputs[0][0].isChecked()
    app.processEvents()
    assert dialog.grab().save(str(screenshots / "人工补全.png"))
    dialog.submit_answer()
    assert dialog.answer == "B"
    window.close()
    print("GUI smoke passed: demo, stop, secret persistence, graphical settings, separate credentials, manual choices, screenshots.")
