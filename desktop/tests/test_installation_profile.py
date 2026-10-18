"""Installed releases must start with independent data, preserving old settings."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from chaoxing_desktop.config import data_dir


class InstallationProfileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.application = self.root / "app"
        self.application.mkdir()
        self.local = self.root / "local"
        self.environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        # Honor caller environments after the test; clear only inside this patch.
        os.environ.pop("CHAOXING_DESKTOP_DATA", None)
        frozen = patch.object(sys, "frozen", True, create=True)
        frozen.start()
        self.addCleanup(frozen.stop)
        executable = patch.object(sys, "executable", str(self.application / "ChaoxingDesktop.exe"))
        executable.start()
        self.addCleanup(executable.stop)

    def write_marker(self, profile):
        (self.application / "installation.json").write_text(json.dumps({"profile": profile}), encoding="utf-8")

    def test_installed_profile_is_empty_and_old_config_untouched(self):
        previous = self.local / "ChaoxingDesktop"
        previous.mkdir(parents=True)
        old_settings = previous / "settings.ini"
        old_settings.write_text("existing private settings", encoding="utf-8")
        self.write_marker("installer-0_2_11-fresh")
        fresh = data_dir()
        self.assertEqual(fresh, previous / "profiles/installer-0_2_11-fresh")
        self.assertEqual(list(fresh.iterdir()), [])
        self.assertEqual(old_settings.read_text(encoding="utf-8"), "existing private settings")

    def test_explicit_test_data_override_takes_priority(self):
        self.write_marker("installer-0_2_11-fresh")
        override = self.root / "isolated-test"
        os.environ["CHAOXING_DESKTOP_DATA"] = str(override)
        self.assertEqual(data_dir(), override)

    def test_portable_release_keeps_original_location(self):
        self.assertEqual(data_dir(), self.local / "ChaoxingDesktop")

    def test_profile_cannot_escape_user_data_directory(self):
        for value in ("../../old", "C:/private", "", None):
            with self.subTest(profile=value):
                self.write_marker(value)
                with self.assertRaises(ValueError):
                    data_dir()


if __name__ == "__main__":
    unittest.main()
