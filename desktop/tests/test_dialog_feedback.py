"""Offline operation results: visible context, failure retention and no writes to platform."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from chaoxing_desktop.qml_backend import Backend
from chaoxing_desktop.draft_copies import DraftCopies
from test_workbench_continuation import discussion_record


class DialogFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, CHAOXING_DESKTOP_DATA=self.tmp.name)
        self.env.start()
        self.network = patch('requests.sessions.Session.request', side_effect=AssertionError('offline only'))
        self.network.start()
        self.b = Backend()
        self.b.demo_mode = True

    def tearDown(self):
        self.b.discardAndClose()
        self.b.deleteLater()
        self.app.processEvents()
        self.network.stop()
        self.env.stop()
        self.tmp.cleanup()

    def open_draft(self):
        record = discussion_record()
        self.b._discussion_model.upsert(record)
        self.b.openDraftCopy('discussion', record['id'])
        return record

    def test_failed_save_keeps_edits_dirty_and_reports_in_draft_scope(self):
        self.open_draft()
        self.b.setDraftContent('synthetic manual edit')
        with patch('chaoxing_desktop.qml_backend.DraftCopies.save', side_effect=OSError('synthetic disk full')):
            self.assertFalse(self.b.saveDraftCopy())
        self.assertTrue(self.b.draftDirty)
        self.assertEqual(self.b._draft['content'], 'synthetic manual edit')
        self.assertEqual(self.b.uiFeedback['draft']['tone'], 'danger')
        self.assertIn('disk full', self.b.uiFeedback['draft']['message'])
        self.assertEqual(DraftCopies(self.tmp.name, 'offline-demo').read()[0], [])
        self.assertTrue(self.b.saveDraftCopy())
        self.assertFalse(self.b.draftDirty)
        self.assertEqual(self.b.draftFeedbackTone, 'success')

    def test_corrupt_lists_are_errors_not_successful_empty_results(self):
        for scope, path, load in (
            ('profiles', Path(self.tmp.name) / 'ai_profiles.json', self.b.listAiProfiles),
            ('savedDrafts', DraftCopies(self.tmp.name, 'offline-demo').path, self.b.listDraftCopies),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            original = b'{synthetic corrupt'
            path.write_bytes(original)
            self.assertEqual(load(), [])
            self.assertEqual(self.b.uiFeedback[scope]['tone'], 'danger')
            self.assertEqual(path.read_bytes(), original)

    def test_scoped_messages_are_redacted_and_do_not_replace_other_dialogs(self):
        secret = 'synthetic-ui-secret-1234'
        self.b.config['ai']['key'] = secret
        self.b.feedback('draft', 'failure: ' + secret, 'danger')
        self.assertNotIn(secret, self.b.uiFeedback['draft']['message'])
        self.b.releaseAction('copy')
        self.assertEqual(self.b.uiFeedback['release']['tone'], 'success')
        self.assertEqual(self.b.uiFeedback['draft']['tone'], 'danger')
        self.b.clearUiFeedback('release')
        self.assertNotIn('release', self.b.uiFeedback)

    def test_invalid_profile_load_keeps_current_configuration_and_reports_failure(self):
        before = dict(self.b.config['ai'])
        self.assertFalse(self.b.aiProfileAction('load', 'synthetic-missing'))
        self.assertEqual(dict(self.b.config['ai']), before)
        self.assertEqual(self.b.uiFeedback['profiles']['tone'], 'danger')

    def test_missing_selection_returns_failure_without_opening_or_starting(self):
        self.assertFalse(self.b.openSavedDraft('missing'))
        self.assertEqual(self.b.uiFeedback['savedDrafts']['tone'], 'danger')
        self.assertFalse(self.b.prepareRecovery('missing'))
        self.assertEqual(self.b.uiFeedback['recovery']['tone'], 'danger')
        self.assertFalse(self.b.controller.active)

    def test_invalid_and_saved_draft_statuses_have_distinct_severity(self):
        self.open_draft()
        self.b.setDraftContent('x' * 1001)
        self.assertEqual(self.b.draftFeedbackTone, 'danger')
        self.b.setDraftContent('valid synthetic text')
        self.assertEqual(self.b.draftFeedbackTone, 'warning')
        self.assertTrue(self.b.saveDraftCopy())
        self.assertEqual(self.b.draftFeedbackTone, 'success')


if __name__ == '__main__':
    unittest.main()
