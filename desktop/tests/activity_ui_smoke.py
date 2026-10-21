"""Render activity settings, native local preview and bounded result details."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QSG_RHI_BACKEND', 'software')
from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.qml_app import configure_app, create_engine
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.activity import ActivityGenerator, preview_context
from chaoxing_desktop.activity_model import safe_record
from chaoxing_desktop.answers import AnswerRouter
from chaoxing_desktop.config import to_payload


def main():
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else 'build/activity-ui-smoke').resolve()
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    configure_app(app)
    with tempfile.TemporaryDirectory() as directory:
        os.environ['CHAOXING_DESKTOP_DATA'] = directory
        b = Backend(); engine = create_engine(b)
        assert engine.rootObjects(), engine.load_warnings
        window = engine.rootObjects()[0]
        def find(name, item=None):
            item = item or window.contentItem()
            if item.objectName() == name:
                return item
            for child in item.childItems():
                found = find(name, child)
                if found is not None:
                    return found
            return None
        window.setProperty('pageIndex', 2)
        find('serviceTabs').setProperty('currentIndex', 4)
        b.setValue('activity', 'choice_strategy', 'random')
        b.setValue('activity', 'text_strategy', 'fixed_good')
        with (patch.object(b.controller, 'start', side_effect=AssertionError('local preview started worker')),
              patch('chaoxing_desktop.answers.AIClient', side_effect=AssertionError('local preview initialized AI'))):
            b.previewActivity('示例题干')
        assert '好' in b.activityPreview['content'] and '随机选择' in b.activityPreview['content']
        assert b.summary['activityCount'] == 0
        QTest.qWait(150)
        assert not find('choice_activity_reply_level').isEnabled()
        for width, height in ((1440, 900), (980, 700)):
            window.setWidth(width); window.setHeight(height); QTest.qWait(150)
            assert window.grabWindow().save(str(destination / f'settings-{width}.png'))
        b.controller.active = True; b.changed.emit()
        assert not find('activityPreviewButton').isEnabled()
        b.controller.active = False; b.changed.emit()
        ctx = preview_context('文本固定好')
        answers = ActivityGenerator(AnswerRouter(to_payload(b.config), SimpleNamespace(control=None))).generate(ctx, b.config['activity'])
        record = safe_record(dict(id='activity-ui', run_id=b.controller.run_id, task_id='task', course='CourseA', chapter='章节',
            title='投票与混合问卷', kind='survey', stage='draft', submit_status='draft', task_status='pending',
            reason='离线界面验收，不访问平台。', elapsed_ms=12, questions=ctx.questions, answers=answers), lambda text: text)
        b.on_event(dict(type='activity_result', record=record)); b.changed.emit()
        window.setProperty('pageIndex', 4); find('resultTabs').setProperty('currentIndex', 3)
        window.setWidth(1280); window.setHeight(860); QTest.qWait(150)
        assert b.summary['activityCount'] == 1 and b.activityModel.rowCount() == 1
        b.filterActivities('missing', ''); assert b.activityModel.rowCount() == 0
        b.filterActivities('CourseA', 'draft'); assert b.activityModel.rowCount() == 1
        assert '好' in b.activityDetail('activity-ui')['detailText']
        assert window.grabWindow().save(str(destination / 'records.png'))
        view = find('activityResults')
        position = view.mapToScene(QPointF(view.width()/2, 45)).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position)
        QTest.qWait(100)
        dialog = window.findChild(QObject, 'activityDetail')
        assert dialog is not None and dialog.property('visible')
        assert dialog.property('background').property('color').name() == '#ffffff', 'Detail dialog must have an opaque background'
        assert window.grabWindow().save(str(destination / 'detail.png'))
        b.reset_account_view(); assert b.summary['activityCount'] == 0
        assert not engine.load_warnings, engine.load_warnings
        b.close(); delete(engine)
    print('Activity QML passed: local preview zero AI/worker, reply-level disable, running locks, narrow layout, source counts, filtering and account isolation.')


if __name__ == '__main__':
    main()
