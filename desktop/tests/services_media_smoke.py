"""Render and inspect independent bank controls and concurrent media bars."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QSG_RHI_BACKEND', 'software')
from PySide6.QtTest import QTest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
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
        def screenshot(name):
            QTest.qWait(150)
            assert window.grabWindow().save(str(destination / name))
        window.setProperty('pageIndex', 2)
        QTest.qWait(150)
        services = find('servicesScroll')
        scroll = services.property('contentItem')
        find('settings_TikuGo').clicked.emit()
        QTest.qWait(80)
        def wheel(item, angle=0, pixels=0):
            point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
            event = QWheelEvent(point, QPointF(window.mapToGlobal(point.toPoint())),
                                QPoint(0, pixels), QPoint(0, angle), Qt.NoButton,
                                Qt.NoModifier, Qt.NoScrollPhase, False)
            QApplication.sendEvent(window, event)
            QTest.qWait(40)
        for width, height in ((1440, 900), (980, 700)):
            window.setWidth(width); window.setHeight(height)
            QTest.qWait(100)
            top = scroll.property('originY')
            scroll.setProperty('contentY', top)
            token = find('field_question_bank_go_authorization')
            before = token.property('text')
            wheel(token, angle=-120)
            assert abs(scroll.property('contentY') - top - 136) < 1, (width, scroll.property('contentY'))
            assert token.property('text') == before
            wheel(services, pixels=-23)
            assert abs(scroll.property('contentY') - top - 159) < 1
            wheel(services, angle=120000)
            assert abs(scroll.property('contentY') - top) < 1
            wheel(services, angle=-120000)
            bottom = top + max(0, scroll.property('contentHeight') - scroll.height())
            assert abs(scroll.property('contentY') - bottom) < 1
            wheel(services, angle=-120)
            assert abs(scroll.property('contentY') - bottom) < 1
            wheel(services, angle=120000)
            if width == 1440:
                choice = find('choice_ai_provider')
                selected = choice.property('currentIndex')
                wheel(choice, angle=-120)
                assert abs(scroll.property('contentY') - top - 136) < 1
                assert choice.property('currentIndex') == selected
                scroll.setProperty('contentY', top)
        for index, name in ((1, 'answersScroll'), (2, 'notificationScroll')):
            find('serviceTabs').setProperty('currentIndex', index)
            QTest.qWait(100)
            view = find(name)
            target = view.property('contentItem')
            top = target.property('originY')
            target.setProperty('contentY', top)
            bottom = top + max(0, target.property('contentHeight') - target.height())
            wheel(view, angle=-120)
            assert abs(target.property('contentY') - min(top + 136, bottom)) < 1
        find('serviceTabs').setProperty('currentIndex', 0)
        window.setWidth(1280); window.setHeight(860)
        QTest.qWait(100)
        find('settings_TikuYanxi').clicked.emit()
        QTest.qWait(150)
        field = find('field_question_bank_yanxi_timeout')
        assert field.isVisible()
        b.setValue('question_bank', 'yanxi_timeout', '42')
        assert field.property('text') == '42'
        assert b.config['question_bank']['like_timeout'] == '300'
        screenshot('独立题库设置.png')
        window.setWidth(980); window.setHeight(700)
        screenshot('独立题库设置-窄窗.png')
        window.setWidth(1280); window.setHeight(860)
        window.setProperty('pageIndex', 3)
        custom = str(Path(directory) / 'custom logs')
        with patch('chaoxing_desktop.qml_backend.QFileDialog.getExistingDirectory', return_value=custom):
            b.chooseLogDirectory()
        assert b.config['logging']['directory'] == custom
        screenshot('日志目录设置.png')
        window.setProperty('pageIndex', 4)
        b.controller.active = True
        b.changed.emit()
        b.on_event(dict(type='tasks', tasks=[dict(id='v', course='演示课程 · 示例', title='第一章 · 视频'), dict(id='a', course='演示课程 · 示例', title='第二章 · 音频')]))
        for key, kind, position in [('v', 'Video', 72), ('a', 'Audio', 165)]:
            b.on_event(dict(type='task', id=key, status='running'))
            b.on_event(dict(type='media', id=key, name='示例视频' if key == 'v' else '示例音频', kind=kind, position=position, duration=240 if key == 'v' else 300))
        b.append_log('示例：题库独立请求参数已加载')
        b.append_log('示例：平台尚未确认章节完成', 'WARNING')
        b.append_log('示例：连接异常，后续服务继续补全', 'ERROR')
        QTest.qWait(200)
        assert abs(find('media_v').property('value') - .3) < .001
        assert abs(find('media_a').property('value') - .55) < .001
        screenshot('视频音频进度.png')
        window.setWidth(980); window.setHeight(700)
        screenshot('视频音频进度-窄窗.png')
        b.on_event(dict(type='media', id='v', name='示例视频', kind='Video', position=240, duration=240, verified=False))
        b.on_event(dict(type='task', id='v', status='pending'))
        b.on_event(dict(type='media', id='a', name='示例音频', kind='Audio', position=300, duration=300, verified=True))
        b.on_event(dict(type='task', id='a', status='pending'))
        QTest.qWait(150)
        assert find('media_status_v').property('text') == '未确认完成'
        assert find('media_status_a').property('text') == '平台已确认'
        assert b.summary['success'] == 0 and b.summary['pending'] == 2
        screenshot('时长到达但章节未完成.png')
        assert not engine.load_warnings, engine.load_warnings
        b.controller.active = False
        window.close()
        delete(engine)
        b.close()
    print('Service/media smoke passed: 136-pixel mouse steps, precise touchpad deltas, scroll bounds, independent fields, concurrent bars, wide/narrow screenshots, no QML warnings.')


if __name__ == '__main__':
    main()
