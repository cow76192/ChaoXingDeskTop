"""Rendered regression for multi-blank input, filter reset and log reading."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QSG_RHI_BACKEND','software')
from PySide6.QtCore import QPointF,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.qml_app import configure_app,create_engine
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.completion import completion_parts


def main():
    output=Path('build/audit-repair-2026-10-17/ui').resolve();output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);configure_app(app)
    with tempfile.TemporaryDirectory() as folder:
        os.environ['CHAOXING_DESKTOP_DATA']=folder
        b=Backend();engine=create_engine(b);assert engine.rootObjects(),engine.load_warnings
        window=engine.rootObjects()[0]
        def find(name,item=None):
            item=item or window.contentItem()
            if item.objectName()==name:return item
            for child in item.childItems():
                found=find(name,child)
                if found is not None:return found
        def property_item(name,item=None):
            item=item or window.contentItem()
            if item.metaObject().indexOfProperty(name)>=0:return item
            for child in item.childItems():
                found=property_item(name,child)
                if found is not None:return found
        def click(name):
            item=find(name);assert item is not None and item.isVisible(),name
            point=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(40)
        try:
            QTest.qWait(150)
            window.setWidth(980);window.setHeight(700);QTest.qWait(160)
            assert find('courseList').height()>=100
            assert window.grabWindow().save(str(output/'courses-980.png'))
            b.controller.active=True;b.changed.emit()
            with patch.object(b.controller,'reply') as reply:
                b.on_event(dict(type='input',kind='question',question=dict(type='completion',title='Synthetic two-blank question',blank_count=2)))
                QTest.qWait(100)
                for index,text in enumerate(('first;part','second')):
                    find('manual_blank_'+str(index)).forceActiveFocus()
                    for character in text:QTest.keyClick(window,character)
                click('manual_send')
                answer=reply.call_args.args[0]
                assert completion_parts(answer,2)==['first;part','second']
                b.on_event(dict(type='input',kind='question',question=dict(type='completion',title='Next two-blank question',blank_count=2)))
                QTest.qWait(100)
                assert find('manual_blank_0').property('text')==''
                assert window.grabWindow().save(str(output/'multi-blank.png'))
                click('manual_skip')
            b.controller.active=False;b.changed.emit()
            window.setProperty('pageIndex',4);QTest.qWait(100)
            pane=property_item('taskId');pane.setProperty('taskId','old-chapter')
            find('questionPending').setProperty('checked',True)
            b.filterQuestions(True,'old-chapter')
            b.reset_account_view();QTest.qWait(60)
            assert pane.property('taskId')==''
            assert not find('questionPending').property('checked')
            assert not b._question_filter.task and not b._question_filter.pending_only
            for i in range(500):b.append_log('Synthetic log '+str(i))
            b._log_model.flush();QTest.qWait(180)
            monitor=property_item('followLogs');monitor.setProperty('followLogs',False)
            log_list=find('logList');log_list.positionViewAtBeginning();QTest.qWait(80)
            y=log_list.property('contentY')
            for i in range(20):b.append_log('New log '+str(i))
            b._log_model.flush();QTest.qWait(140)
            assert abs(log_list.property('contentY')-y)<2
            b.append_log('Error for filter','ERROR');b._log_model.flush()
            b.filterLogs('ERROR','filter');QTest.qWait(80)
            assert b.logModel.rowCount()==1
            b.filterLogs('','');QTest.qWait(80)
            assert window.grabWindow().save(str(output/'monitor-980.png'))
            assert b.log_store.flush()
            assert not engine.load_warnings,engine.load_warnings
            print('Audit UI passed: two blanks/reset, account filters, narrow list, log scroll/filter; no QML warnings.')
        finally:
            b.controller.active=False;b.discardAndClose();delete(engine);delete(b);app.processEvents()


if __name__=='__main__':main()
