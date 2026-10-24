"""Exercise keyboard input and QML bindings through the rendered window."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")
from PySide6.QtCore import QPointF, Qt, qInstallMessageHandler
from unittest.mock import patch
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.qml_app import configure_app, create_engine
from chaoxing_desktop.qml_backend import Backend

app = QApplication([])
configure_app(app)
warnings = []
previous = qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
with tempfile.TemporaryDirectory() as directory:
    os.environ["CHAOXING_DESKTOP_DATA"] = directory
    b = Backend()
    e = create_engine(b)
    assert e.rootObjects(), e.load_warnings
    window = e.rootObjects()[0]
    QTest.qWait(150)

    def find(name, item=None):
        item = item or window.contentItem()
        if item.objectName() == name:
            return item
        for child in item.childItems():
            found = find(name, child)
            if found is not None:
                return found
        return None

    account = find("account_username")
    account.forceActiveFocus()
    for char in "123456":
        QTest.keyClick(window, char)
    assert b.config["common"]["username"] == "123456"
    window.setProperty("pageIndex", 2)
    QTest.qWait(100)
    find('settings_TikuYanxi').clicked.emit()
    QTest.qWait(50)
    token = find("field_question_bank_yanxi_tokens")
    token.forceActiveFocus()
    for char in "abc123":
        QTest.keyClick(window, char)
        assert find("field_question_bank_yanxi_tokens") is token, "typing rebuilt the provider field"
    assert b.config["question_bank"]["yanxi_tokens"] == "abc123"
    assert token.property("displayText") != "abc123" and token.property("displayText"), "secret is displayed as plain text"
    window.setWidth(980); window.setHeight(700)
    QTest.qWait(100)
    assert token.property("text") == "abc123"
    b.controller.active = True
    b.changed.emit()
    assert not token.isEnabled()
    b.controller.active = False
    b.changed.emit()
    window.setProperty("pageIndex", 1)
    QTest.qWait(100)
    speed = find("field_common_speed")
    speed.forceActiveFocus()
    QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    for char in "1.5":
        QTest.keyClick(window, char)
    assert b.config["common"]["speed"] == "1.5"
    assert b.save(), b.message
    def click(name):
        item = find(name)
        assert item is not None and item.isVisible(), name
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        QTest.qWait(40)

    b.controller.active = True
    b.changed.emit()
    with patch.object(b.controller, "reply") as reply:
        for kind, choices, expected in [("single", ["B"], "B"), ("multiple", ["A", "B"], "AB"), ("judgement", ["正确"], "正确")]:
            b.on_event(dict(type="input", kind="question", question=dict(type=kind, title="Sample", options="A. first\nB. second")))
            QTest.qWait(100)
            for value in choices:
                click(("manual_multi_" if kind == "multiple" else "manual_single_") + value)
            click("manual_send")
            reply.assert_called_with(expected, False)
            assert not b.input
        b.on_event(dict(type="input", kind="question", question=dict(type="completion", title="Fill")))
        QTest.qWait(100)
        find("manual_answer").forceActiveFocus()
        for char in "answer":
            QTest.keyClick(window, char)
        click("manual_send")
        reply.assert_called_with("answer", False)
        b.on_event(dict(type="input", kind="choice", choices=[dict(label="跳过章节", value="continue")]))
        QTest.qWait(100)
        click("manual_choice_continue")
        reply.assert_called_with("continue", False)
        b.on_event(dict(type="input", kind="question", question=dict(type="single", title="Skip")))
        QTest.qWait(100)
        click("manual_skip")
        reply.assert_called_with("", False)
        b.on_event(dict(type="input", kind="question", question=dict(type="single", title="Stop")))
        QTest.qWait(100)
        click("manual_stop")
        reply.assert_called_with("", True)
    b.controller.active = False
    b.changed.emit()
    window.close()
    delete(e)
    b.close()
qInstallMessageHandler(previous)
meaningful = [m for m in warnings if not m.startswith("QFontDatabase:")]
assert not meaningful, "\n".join(meaningful)
print("QML UI smoke passed: real keyboard edits, stable secret field, resize, running lock, save, single/multiple/judgement/text/choice replies, skip and stop; no QML warnings.")
