"""Offline release check for the packaged GUI and its actual worker companion."""
import json
import time

from PySide6.QtCore import QTimer


def start_smoke(app, window, destination):
    destination.mkdir(parents=True, exist_ok=True)
    phase = [0]
    started = time.monotonic()
    timer = QTimer(window)
    timer.setInterval(80)

    def finish(success, message):
        timer.stop()
        (destination / "result.json").write_text(json.dumps({"success": success, "message": message}, ensure_ascii=False), encoding="utf-8")
        window.close()
        app.exit(0 if success else 1)

    def tick():
        try:
            if time.monotonic() - started > 45:
                raise RuntimeError("release smoke timed out")
            if phase[0] == 0:
                assert window.fields[("question_bank", "yanxi_tokens")].isEnabled()
                assert window.fields[("ai", "key")].isEnabled()
                assert window.fields[("notification", "url")].isEnabled()
                assert not window.fields[("desktop", "random_fallback")].isChecked()
                phase[0] = 1
                window.load_demo()
            elif phase[0] == 1 and not window.controller.active:
                assert len(window.courses) == 3, window.log.toPlainText()
                window.check_courses(True)
                window.grab().save(str(destination / "课程与账号.png"))
                phase[0] = 2
                window.start_tasks()
            elif phase[0] == 2 and not window.controller.active:
                assert window.metrics["success"].text() == "9", window.log.toPlainText()
                window.grab().save(str(destination / "任务与日志.png"))
                assert not hasattr(window, "editor")
                window.fields[("question_bank", "providers")].setText("TikuGo,TikuYanxi")
                window.fields[("ai", "enabled")].setChecked(True)
                window.fields[("desktop", "random_fallback")].setChecked(True)
                window.update_services()
                assert window.fields[("question_bank", "yanxi_tokens")].isEnabled()
                assert window.fields[("ai", "endpoint")].isEnabled()
                window.nav.setCurrentRow(2)
                window.grab().save(str(destination / "题库与AI.png"))
                window.nav.setCurrentRow(3)
                window.grab().save(str(destination / "高级设置.png"))
                phase[0] = 3
                window.start_tasks()
            elif phase[0] == 3 and window.task_rows:
                phase[0] = 4
                window.controller.stop()
            elif phase[0] == 4 and not window.controller.active:
                assert "已停止" in window.run_status.text()
                finish(True, "Packaged GUI and worker: 3 demo courses, 9 chapters, restart and stop passed.")
        except Exception as exc:
            finish(False, str(exc))
    timer.timeout.connect(tick)
    timer.start()
