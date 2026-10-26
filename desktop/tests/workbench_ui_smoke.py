"""Rendered offline upgrade acceptance: narrow, long text, focus and safe export."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QSG_RHI_BACKEND', 'software')
from PySide6.QtCore import QObject, QPointF, Qt, QMetaObject, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.qml_app import configure_app, create_engine
from chaoxing_desktop.qml_backend import Backend


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='chaoxing-workbench-'))
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    configure_app(app)
    warnings = []
    previous = qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CHAOXING_DESKTOP_DATA=directory), \
            patch('requests.sessions.Session.request', side_effect=AssertionError('offline acceptance must not use network')):
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
            if item is window.contentItem():
                return window.findChild(QObject, name)

        def click(name):
            item = find(name)
            assert item is not None and item.isVisible() and item.isEnabled(), (name, warnings)
            point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
            assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), (name, point)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(80)

        def shot(name):
            QTest.qWait(100)
            assert window.grabWindow().save(str(output / (name + '.png')))

        QTest.qWait(150)
        window.setWidth(980); window.setHeight(700)
        QTest.qWait(80)
        click('account_username')
        QTest.keyClick(window, Qt.Key_Tab)
        assert window.activeFocusItem().objectName() == 'account_password'
        QTest.keyClick(window, Qt.Key_Backtab)
        assert window.activeFocusItem().objectName() == 'account_username'
        shot('01-login-980')

        long_title = '合成课程与长标题验证' * 12
        b.courses = [dict(courseId='synthetic', clazzId='fixture', title=long_title, teacher='演示教师', desc='合成样例')]
        b.selected = {('synthetic', 'fixture')}
        b.coursesChanged.emit(); b.changed.emit()
        click('strategy_button')
        shot('02-strategy-980')
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(220)
        window.setProperty('pageIndex', 2)
        QTest.qWait(80)
        click('settings_TikuYanxi')
        assert find('servicesPage').property('selectedBank') == 'TikuYanxi', (find('servicesPage').property('selectedBank'), warnings)
        token = find('field_question_bank_yanxi_tokens')
        click('field_question_bank_yanxi_tokens')
        assert window.activeFocusItem() is token, 'service editor must be scrolled into view before typing'
        for char in 'synthetic-token':
            QTest.keyClick(window, char)
            assert find('field_question_bank_yanxi_tokens') is token
        assert token.property('text') == 'synthetic-token', ('before reorder', token.property('text'), warnings)
        b.toggleProvider('TikuGo', True)
        b.moveProvider(1, -1)
        QTest.qWait(80)
        assert find('field_question_bank_yanxi_tokens') is token, 'toggle/reorder rebuilt the active editor'
        assert token.property('text') == 'synthetic-token', ('after reorder', token.property('text'), b.config['question_bank']['yanxi_tokens'], warnings)
        shot('03-services-980')
        click('service_ai_link')
        QTest.qWait(80)
        endpoint = find('field_ai_endpoint')
        assert endpoint.isVisible()
        # Reach service fields with Tab from the direct AI navigation button.
        reached = False
        for _ in range(60):
            QTest.keyClick(window, Qt.Key_Tab)
            if window.activeFocusItem() is endpoint:
                reached = True
                break
        assert reached, 'AI endpoint is not reachable by Tab'
        shot('04-ai-980')

        window.setProperty('pageIndex', 1)
        QTest.qWait(80)
        redo = find('field_common_work_max_retries')
        assert not redo.isEnabled()
        b.setValue('common', 'work_redo_enabled', 'true')
        assert redo.isEnabled()
        b.setValue('common', 'work_redo_enabled', 'false')
        assert not redo.isEnabled() and b.config['common']['work_max_retries'] == '3'
        b.setValue('common', 'speed', '9')
        assert not b.save()
        QTest.qWait(100)
        assert window.activeFocusItem() is find('field_common_speed')
        shot('05-field-error-980')
        b.setValue('common', 'speed', '1.0')

        window.setProperty('pageIndex', 4)
        b.on_event(dict(type='tasks', tasks=[dict(id='fixture', title=long_title, course=long_title)]))
        b.on_event(dict(type='task', id='fixture', status='pending'))
        find('resultTabs').setProperty('currentIndex', 4)
        QTest.qWait(120)
        assert find('attentionList').property('count') == 1
        click('attentionList')
        QTest.keyClick(window, Qt.Key_Home)
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(180)
        assert find('attentionDetail').property('opened'), 'reason detail must open from the keyboard'
        shot('06-attention-detail-980')
        QTest.keyClick(window, Qt.Key_Escape)
        shot('07-attention-980')

        b.controller.active = True; b.controller.busy_changed.emit(True)
        b.on_event(dict(type='input', question=dict(type='text', title='长题干' * 400)))
        QTest.qWait(120)
        answer = find('manual_answer')
        assert window.activeFocusItem() is answer, 'manual input should focus the answer automatically'
        answer_point = answer.mapToScene(QPointF(10, 10))
        assert 100 < answer_point.y() < 540, ('manual answer must scroll into view', answer_point)
        for char in 'synthetic answer':
            QTest.keyClick(window, char)
        assert answer.property('text') == 'synthetic answer'
        shot('08-manual-long-980')
        b.clear_input(); b.controller.active = False; b.controller.busy_changed.emit(False); b.changed.emit()

        path = output / 'diagnostics.ini'
        window.setProperty('pageIndex', 3)
        QTest.qWait(100)
        scroll = find('advancedScroll').property('contentItem')
        scroll.setProperty('contentY', max(0, scroll.property('contentHeight') - scroll.height()))
        QTest.qWait(100)
        with patch('chaoxing_desktop.qml_backend.QFileDialog.getSaveFileName', return_value=(str(path), '')):
            click('export_diagnostics')
        assert 'synthetic-token' not in path.read_text(encoding='utf-8')
        shot('10-export-980')
        click('data_explanation')
        assert find('dataInfoDialog').property('opened')
        shot('11-data-explanation-980')
        QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(220)
        b.demo_mode = True
        b._history_account = 'offline-demo'; b._history_run = 'synthetic-run'
        b._history_time = '2026-10-24T00:00:00+08:00'
        assert b.save_run_summary('离线合成摘要')
        b._history_run = ''
        window.setProperty('pageIndex', 4)
        QTest.qWait(100)
        click('history_button')
        assert find('historyDialog').property('opened')
        shot('12-history-980')
        QTest.keyClick(window, Qt.Key_Escape); QTest.qWait(220)
        for page in (0, 1, 2, 3, 4):
            window.setWidth(1280); window.setHeight(860); window.setProperty('pageIndex', page)
            shot('09-page-' + str(page) + '-1280')

        # Continuation: all actions below remain under the network-failure sentinel.
        from test_workbench_continuation import discussion_record, activity_record
        from chaoxing_desktop.declarative import TEMPLATE
        window.setWidth(980); window.setHeight(700); window.setProperty('pageIndex', 2)
        template = output / 'synthetic-template.json'; template.write_text(json.dumps(TEMPLATE), encoding='utf-8')
        with patch('chaoxing_desktop.qml_backend.QFileDialog.getOpenFileName', return_value=(str(template), '')):
            b.definitionAction('import')
        QTest.qWait(100)
        assert find('definitionPreview').property('opened')
        shot('13-template-preview-980')
        QMetaObject.invokeMethod(find('definitionPreview'), 'accept'); QTest.qWait(150)
        assert json.loads(b.config['question_bank']['declarative_definition']) == TEMPLATE
        template.write_text(json.dumps(dict(TEMPLATE, handler='synthetic rejected code')), encoding='utf-8')
        with patch('chaoxing_desktop.qml_backend.QFileDialog.getOpenFileName', return_value=(str(template), '')):
            b.definitionAction('import')
        shot('14-template-rejected-980')
        QMetaObject.invokeMethod(find('definitionPreview'), 'reject'); QTest.qWait(180)

        b.config['discussion']['reply_level'] = 'invalid'; assert not b.save(); QTest.qWait(100)
        assert find('serviceTabs').property('currentIndex') == 3
        assert find('choice_discussion_reply_level').hasActiveFocus()
        shot('15-choice-error-980')
        b.setValue('discussion', 'reply_level', 'medium')
        find('serviceTabs').setProperty('currentIndex', 0)
        find('servicesPage').setProperty('serviceArea', 'ai')
        find('servicesScroll').property('contentItem').setProperty('contentY', 0); QTest.qWait(120)
        click('ai_profiles_button'); shot('16-ai-profiles-980')
        click('saveAiProfile'); assert len(b.listAiProfiles()) == 1
        QMetaObject.invokeMethod(find('aiProfilesDialog'), 'close'); QTest.qWait(150)

        window.setProperty('pageIndex', 4)
        record = discussion_record(); b._discussion_model.upsert(record); b.changed.emit()
        b.openDraftCopy('discussion', record['id']); QTest.qWait(120)
        assert find('draftEditor').property('opened') and b.draftEditable
        click('draftDiscussionText'); QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for char in 'manual edited copy': QTest.keyClick(window, char)
        assert b._draft['content'] == 'manual edited copy'
        click('saveDraftCopy'); assert b._draft['version'] == 1
        assert b._discussion_model.rows[0]['content'] == record['content']
        shot('17-discussion-edit-980')
        click('closeDraftEditor')

        record = activity_record(); b._activity_model.upsert(record); b.changed.emit()
        b.openDraftCopy('activity', record['id']); QTest.qWait(120)
        first = record['questions'][0]
        option = first['options'][1]['id']
        click('draftOption_' + first['id'] + '_' + option)
        assert b.draftAnswer(first['id'])['option_ids'] == [option]
        shot('18-activity-edit-980')
        QMetaObject.invokeMethod(find('draftQuestions'), 'positionViewAtEnd'); QTest.qWait(120)
        text_q = next(q for q in record['questions'] if q['type'] == 'text')
        click('draftText_' + text_q['id']); QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for char in 'my own suggestion': QTest.keyClick(window, char)
        assert b.draftAnswer(text_q['id'])['text'] == 'my own suggestion'
        click('saveDraftCopy'); shot('19-activity-text-980')
        click('closeDraftEditor')

        extreme = activity_record(); extreme['id'] = 'synthetic-extreme'
        question = extreme['questions'][0]
        extreme['questions'] = [dict(question, id='extreme-'+str(i), title='第 '+str(i+1)+' 题：100 选项合成极限样本',
                                    options=[dict(id='option-'+str(j), text='选项 '+str(j+1)) for j in range(100)]) for i in range(100)]
        extreme['answers'] = [dict(question_id=q['id'], option_ids=['option-0'], source='random', valid=True, reason='') for q in extreme['questions']]
        assert b._activity_model.upsert(extreme), 'extreme fixture must stay within the 512 KiB event contract'
        b.changed.emit(); b.openDraftCopy('activity', extreme['id'])
        QTest.qWait(150); shot('20-extreme-first-980')
        QMetaObject.invokeMethod(find('draftQuestions'), 'positionViewAtEnd'); QTest.qWait(250)
        shot('21-extreme-last-980')
        last = find('draftOption_extreme-99_option-99'); assert last is not None and last.isVisible()
        point = last.mapToScene(QPointF(20, last.height()/2)).toPoint()
        assert 0 < point.y() < window.height() - 100, point
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point); QTest.qWait(100)
        assert b.draftAnswer('extreme-99')['option_ids'] == ['option-99']
        click('closeDraftEditor')
        assert find('discardDraftEdits').property('opened'), 'unsaved changes must be explicit'
        click('discardDraftEdits_cancel'); assert find('draftEditor').property('opened')
        assert b.draftAnswer('extreme-99')['option_ids'] == ['option-99']
        click('closeDraftEditor'); click('discardDraftEdits_primary'); QTest.qWait(240)

        b._discussion_model.upsert(discussion_record(stage='publish_unknown')); b.changed.emit()
        saved = next(r for r in b.listDraftCopies() if r['title'] == '合成讨论')
        b.openSavedDraft(saved['id']); QTest.qWait(100)
        assert not b.draftEditable and not find('saveDraftCopy').isEnabled()
        shot('22-saved-copy-readonly-980'); click('closeDraftEditor')
        click('saved_drafts_button'); assert find('savedDraftsDialog').property('opened'); shot('27-saved-copies-980')
        before_delete = len(b.listDraftCopies())
        click('deleteSavedDraft'); assert find('deleteDraftDialog').property('opened'); shot('28-delete-copy-confirm-980')
        QMetaObject.invokeMethod(find('deleteDraftDialog'), 'reject'); QTest.qWait(240)
        assert len(b.listDraftCopies()) == before_delete
        QMetaObject.invokeMethod(find('savedDraftsDialog'), 'reject'); QTest.qWait(240)
        click('recovery_button'); shot('23-recovery-980')
        assert find('recoveryDialog').property('opened')
        QMetaObject.invokeMethod(find('recoveryDialog'), 'reject'); QTest.qWait(240)
        click('capacity_button'); assert find('capacityDialog').property('opened'); shot('24-capacity-980')
        QMetaObject.invokeMethod(find('capacityDialog'), 'close'); QTest.qWait(240)
        click('release_info_button'); shot('25-release-980'); click('copy_verification_info')
        assert '当前数据 profile' not in app.clipboard().text()
        QMetaObject.invokeMethod(find('releaseInfoDialog'), 'close'); QTest.qWait(120)
        window.setWidth(1280); window.setHeight(860)
        b.openDraftCopy('activity', record['id']); shot('26-activity-edit-1280'); click('closeDraftEditor')
        assert not engine.load_warnings, engine.load_warnings
        assert not [w for w in warnings if not w.startswith('QFontDatabase: Cannot find font directory')], warnings
        b.discardAndClose()
        window.setProperty('discardedClose', True)
        window.close()
        delete(engine)
        b.deleteLater(); app.processEvents()
    qInstallMessageHandler(previous)
    report = dict(success=True, screenshots=len(list(output.glob('*.png'))), qml_warnings=[], warnings=warnings,
                  scale=os.environ.get('QT_SCALE_FACTOR', '1'), output=str(output))
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
