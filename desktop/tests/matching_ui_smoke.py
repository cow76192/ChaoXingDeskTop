"""Verify the configurable matcher in the rendered QML form, without queries."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QSG_RHI_BACKEND', 'software')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.qml_app import configure_app, create_engine
from chaoxing_desktop.qml_backend import Backend


def main():
    destination = Path(sys.argv[1]).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    configure_app(app)
    with tempfile.TemporaryDirectory() as directory:
        os.environ['CHAOXING_DESKTOP_DATA'] = directory
        b = Backend()
        engine = create_engine(b)
        window = engine.rootObjects()[0]
        def items(root=None):
            root = root or window.contentItem()
            yield root
            for child in root.childItems():
                yield from items(child)
        def find(name):
            return next(item for item in items() if item.objectName() == name)
        window.setProperty('pageIndex', 2)
        QTest.qWait(100)
        find('serviceTabs').setProperty('currentIndex', 1)
        QTest.qWait(150)
        review = find('choice_matching_bank_review_policy')
        review.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.qWait(100)
        assert b.config['matching']['bank_review_policy'] == 'ai_dependent'
        assert review.property('currentIndex') == 1
        assert b.save(), b.message
        reopened = Backend()
        assert reopened.config['matching']['bank_review_policy'] == 'ai_dependent'
        reopened.close()
        for width, height in [(1280, 860), (980, 700)]:
            window.setWidth(width); window.setHeight(height)
            QTest.qWait(150)
            assert window.grabWindow().save(str(destination / f'review-policy-{width}.png'))
        threshold = find('field_matching_min_similarity')
        threshold.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        for char in '0.95':
            QTest.keyClick(window, char)
        assert b.config['matching']['min_similarity'] == '0.95'
        for width, height in [(1280, 860), (980, 700)]:
            window.setWidth(width); window.setHeight(height)
            QTest.qWait(150)
            for item in items():
                content = item.property('contentHeight')
                offset = item.property('contentY')
                if content is not None and offset is not None and item.isVisible():
                    item.setProperty('contentY', max(0, float(content) - item.height()))
            QTest.qWait(150)
            assert window.grabWindow().save(str(destination / f'matching-{width}.png'))
        b.controller.active = True; b.controller.busy_changed.emit(True)
        b.changed.emit()
        assert not threshold.isEnabled()
        assert not review.isEnabled()
        b.controller.active = False; b.controller.busy_changed.emit(False)
        b.changed.emit()
        assert b.save(), b.message
        assert not engine.load_warnings, engine.load_warnings
        window.close()
        delete(engine)
        b.close()
    print('Matching UI passed: keyboard threshold edit, wide/narrow form, run lock, save, no QML warnings.')


if __name__ == '__main__':
    main()
