"""Real rendered button/feedback checks, synthetic profile and zero network."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QSG_RHI_BACKEND', 'software')
from PySide6.QtCore import QObject, QMetaObject, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from chaoxing_desktop.qml_app import configure_app, create_engine
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.draft_copies import DraftCopies
from test_workbench_continuation import discussion_record


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    configure_app(app)
    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, CHAOXING_DESKTOP_DATA=folder), patch(
            'requests.sessions.Session.request', side_effect=AssertionError('offline UI only')):
        b = Backend()
        engine = create_engine(b)
        assert engine.rootObjects(), engine.load_warnings
        window = engine.rootObjects()[0]
        window.setWidth(980); window.setHeight(700); QTest.qWait(180)

        def find(name):
            return window.findChild(QObject, name)

        def click(name):
            item = find(name)
            assert item is not None and item.isVisible() and item.isEnabled(), name
            point = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
            assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), (name, point)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point); QTest.qWait(120)

        def shot(name):
            QTest.qWait(150)
            assert window.grabWindow().save(str(output / (name + '.png')))

        def close(name):
            QMetaObject.invokeMethod(find(name), 'reject'); QTest.qWait(240)

        window.setProperty('pageIndex', 4); QTest.qWait(100)
        click('saved_drafts_button')
        assert not find('savedDraftsDialog_primary').isEnabled()
        assert find('savedDraftsDialog_primary').property('text') == '打开所选副本'
        shot('01-empty-copies'); close('savedDraftsDialog')
        click('recovery_button')
        assert not find('recoveryDialog_primary').isEnabled()
        shot('02-empty-recovery'); close('recoveryDialog')

        window.setProperty('pageIndex', 2)
        find('servicesPage').setProperty('serviceArea', 'ai'); QTest.qWait(120)
        click('ai_profiles_button')
        click('aiProfileName'); QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier); QTest.keyClick(window, Qt.Key_Backspace)
        click('saveAiProfile')
        assert find('aiProfilesDialog').property('opened')
        assert find('profilesNotice').isVisible() and find('profilesNotice').property('tone') == 'danger'
        shot('03-profile-error-visible')
        click('aiProfileName')
        for char in 'synthetic profile': QTest.keyClick(window, char)
        click('saveAiProfile')
        assert len(b.listAiProfiles()) == 1
        assert find('profilesNotice').property('tone') == 'success'
        assert find('saveAiProfile').property('tone') == 'save'
        assert find('loadAiProfile').property('tone') == 'connect'
        click('deleteAiProfile'); QTest.qWait(200)
        assert find('deleteAiProfileDialog_primary').property('tone') == 'danger'
        assert find('deleteAiProfileDialog_cancel').hasActiveFocus()
        shot('04-danger-confirmation')
        click('deleteAiProfileDialog_cancel'); assert len(b.listAiProfiles()) == 1
        close('aiProfilesDialog')

        b.demo_mode = True
        source = discussion_record(); b._discussion_model.upsert(source)
        b.openDraftCopy('discussion', source['id']); QTest.qWait(260)
        click('draftDiscussionText'); QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for char in 'synthetic manual edit': QTest.keyClick(window, char)
        click('closeDraftEditor'); QTest.qWait(180)
        assert find('discardDraftEdits').property('opened') and find('draftEditor').property('opened')
        shot('05-unsaved-warning'); click('discardDraftEdits_cancel')
        assert b._draft['content'] == 'synthetic manual edit'
        with patch('chaoxing_desktop.qml_backend.DraftCopies.save', side_effect=OSError('synthetic disk full')):
            click('saveDraftCopy')
        assert find('draftEditor').property('opened') and b.draftDirty
        assert find('draftOperationNotice').isVisible()
        assert 'disk full' in find('draftOperationNotice').property('message')
        shot('06-save-failure-visible')
        click('saveDraftCopy'); assert not b.draftDirty
        assert find('draftOperationNotice').property('tone') == 'success'
        shot('07-save-success'); click('closeDraftEditor'); QTest.qWait(220)

        window.setProperty('pageIndex', 4); QTest.qWait(100)
        click('saved_drafts_button')
        assert find('savedDraftsDialog_primary').isEnabled()
        assert find('savedDraftsDialog_primary').property('tone') == 'connect'
        shot('08-selected-copy-primary')
        click('deleteSavedDraft'); QTest.qWait(180)
        shot('09-copy-delete-danger'); click('deleteDraftDialog_cancel')
        close('savedDraftsDialog')
        store = DraftCopies(folder, 'offline-demo')
        store.path.write_bytes(b'{synthetic corrupt')
        click('saved_drafts_button')
        assert not find('savedDraftsDialog_primary').isEnabled()
        assert find('savedDraftsNotice').property('tone') == 'danger'
        shot('10-corrupt-is-not-empty'); close('savedDraftsDialog')
        click('release_info_button'); click('copy_verification_info')
        assert find('releaseNotice').isVisible() and find('releaseNotice').property('tone') == 'success'
        shot('11-copy-feedback-visible'); close('releaseInfoDialog')
        window.setWidth(1280); window.setHeight(860); QTest.qWait(120)
        click('saved_drafts_button'); shot('12-wide-corrupt-message'); close('savedDraftsDialog')

        assert not engine.load_warnings, engine.load_warnings
        b.discardAndClose(); delete(engine); b.deleteLater(); app.processEvents()
    result = dict(success=True, screenshots=len(list(output.glob('*.png'))), qml_warnings=[],
                  scale=os.environ.get('QT_SCALE_FACTOR', '1'))
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
