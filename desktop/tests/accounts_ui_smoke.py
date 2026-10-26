"""Rendered multi-account controls with synthetic, isolated sessions."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QSG_RHI_BACKEND', 'software')
from PySide6.QtCore import QPoint, QPointF, Qt, qInstallMessageHandler
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.accounts import AccountStore, write_cookie
from chaoxing_desktop.qml_app import configure_app, create_engine
from chaoxing_desktop.qml_backend import Backend

app = QApplication([])
configure_app(app)
warnings = []
previous = qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
destination = Path(__file__).resolve().parents[1] / 'build/multi-account-smoke'
destination.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
    os.environ['CHAOXING_DESKTOP_DATA'] = directory
    store = AccountStore(Path(directory))
    first = store.add('demo-student-a', '学习账号 A')
    second = store.add('demo-student-b', '学习账号 B')
    for row in (first, second):
        write_cookie(store.cookie_path(row['id']), {'_uid': row['username'], 'session': 'synthetic'})
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

    def click(name):
        item = find(name)
        assert item and item.isEnabled() and item.isVisible(), name
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(80)

    QTest.qWait(150)
    assert find('account_selector').property('currentIndex') == 1
    assert find('account_username').property('readOnly')
    selector = find('account_selector')
    selector.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_Home)
    QTest.qWait(80)
    assert b.summary['activeAccount'] == first['id'], b.summary
    assert find('account_username').property('text') == 'demo-student-a'
    with patch.object(b.controller, 'start') as start:
        click('account_login')
    assert start.call_args.args[0]['account_id'] == first['id']
    window.setWidth(980)
    window.setHeight(700)
    QTest.qWait(120)
    assert window.grabWindow().save(str(destination / '账号展开-980.png'))
    b.on_event(dict(type='courses', demo=False, courses=[dict(courseId='101', clazzId='01', title='账号 A 的示例课程')]))
    b.selectVisible(True)
    for width, height in [(1440, 900), (980, 700)]:
        window.setWidth(width)
        window.setHeight(height)
        QTest.qWait(120)
        assert window.grabWindow().save(str(destination / f'多账号-{width}.png'))
        for name in ['account_selector', 'account_add', 'account_delete', 'account_login']:
            item = find(name)
            if not item.isVisible():
                continue
            point = item.mapToScene(QPointF(item.width(), item.height()))
            assert point.x() <= window.width() and point.y() <= window.height(), (name, point)
    selector.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_End)
    QTest.qWait(80)
    assert b.summary['activeAccount'] == second['id']
    assert not b.courses and not b.selected

    # The selected row must stay readable while another row is highlighted.
    click('account_selector')
    QTest.keyClick(window, Qt.Key_Home)
    QTest.qWait(80)
    selected_option = find('account_selector_option_1')
    assert selected_option is not None and selected_option.property('selected')
    assert find('account_selector_option_0').property('highlighted')

    def luminance(color):
        def linear(value):
            return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
        return sum(weight * linear(value) for weight, value in
                   zip((.2126, .7152, .0722), (color.redF(), color.greenF(), color.blueF())))

    for index in (0, 1):
        option = find(f'account_selector_option_{index}')
        foreground = luminance(option.property('contentItem').property('color'))
        background = luminance(option.property('background').property('color'))
        assert (max(foreground, background) + .05) / (min(foreground, background) + .05) >= 4.5
    assert window.grabWindow().save(str(destination / '账号下拉选中.png'))
    QTest.keyClick(window, Qt.Key_Escape)
    assert b.summary['activeAccount'] == second['id'], 'Dismissal changed the account'
    click('account_selector')
    click('account_selector_option_0')
    assert b.summary['activeAccount'] == first['id'], 'Popup click did not switch accounts'
    selector.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_End)
    QTest.qWait(80)

    # Send real wheel events over cards, including a checkbox, at both sizes.
    b.on_event(dict(type='courses', demo=False, courses=[
        dict(courseId=str(index), clazzId='01', title=f'离线滚动课程 {index + 1}')
        for index in range(30)]))
    course_list = find('courseList')

    def wheel(item, angle=0, pixels=0, x=100):
        position = item.mapToScene(QPointF(x, item.height() / 2))
        event = QWheelEvent(position, QPointF(window.mapToGlobal(position.toPoint())),
                            QPoint(0, pixels), QPoint(0, angle), Qt.NoButton,
                            Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(window, event)
        QTest.qWait(40)

    for width, height in [(1440, 900), (980, 700)]:
        window.setWidth(width)
        window.setHeight(height)
        QTest.qWait(100)
        course_list.setProperty('contentY', course_list.property('originY'))
        wheel(course_list, angle=-120)
        assert abs(course_list.property('contentY') - course_list.property('originY') - 136) < 1
        before = course_list.property('contentY')
        wheel(course_list, pixels=-23)
        assert abs(course_list.property('contentY') - before - 23) < 1
        wheel(course_list, angle=120000, x=30)
        assert abs(course_list.property('contentY') - course_list.property('originY')) < 1
        wheel(course_list, angle=-120000)
        bottom = (course_list.property('originY') + course_list.property('contentHeight')
                  - course_list.height())
        assert abs(course_list.property('contentY') - bottom) < 1
        wheel(course_list, angle=-120)
        assert abs(course_list.property('contentY') - bottom) < 1
        wheel(course_list, angle=120000)

        click('courses_select_all')
        assert b.summary['selectedCount'] == 30
        click('courses_show_ids')
        assert find('courses_show_ids').property('checked')
        assert find('courses_show_ids').property('text') == '隐藏 ID'
        assert window.grabWindow().save(str(destination / f'课程按钮与ID-{width}.png'))
        click('courses_show_ids')
        assert not find('courses_show_ids').property('checked')
        click('courses_clear_selection')
        assert b.summary['selectedCount'] == 0

    b.controller.active = True; b.controller.busy_changed.emit(True)
    b.changed.emit()
    QTest.qWait(60)
    assert not selector.isEnabled()
    assert not find('account_add').isEnabled()
    assert not find('account_delete').isEnabled()
    b.controller.active = False; b.controller.busy_changed.emit(False)
    b.changed.emit()
    click('account_add')
    assert not b.summary['activeAccount']
    assert not find('account_username').property('readOnly')
    assert find('account_selector').property('currentIndex') == -1
    assert len(b.accountRows) == 2
    window.close()
    delete(engine)
    b.close()
qInstallMessageHandler(previous)
meaningful = [message for message in warnings if not message.startswith('QFontDatabase:')]
assert not meaningful, '\n'.join(meaningful)
print('Multi-account UI passed: account switching/isolation, readable popup selection, mouse and pixel wheel scrolling/bounds, selection and ID buttons, busy lock, narrow/wide screenshots; no QML warnings.')
