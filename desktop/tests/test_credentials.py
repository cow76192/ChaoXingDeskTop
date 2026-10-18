import base64
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from chaoxing_desktop import credentials
from chaoxing_desktop.config import defaults, parse_text, serialize, to_payload
from chaoxing_desktop.settings import CREDENTIAL_SECTION, restore_credentials, serialize_settings


@unittest.skipUnless(os.name == "nt", "Windows DPAPI")
class CredentialTests(unittest.TestCase):
    def test_dpapi_unicode_and_multiple_tokens_survive_another_process(self):
        value = "KEY_测试, TOKEN_A,TOKEN_B".encode("utf-8")
        encrypted = credentials.protect(value)
        self.assertNotIn(value, encrypted)
        program = ("import base64,sys; from chaoxing_desktop.credentials import unprotect; "
                   "value=unprotect(base64.b64decode(sys.stdin.read())); "
                   "assert value == 'KEY_测试, TOKEN_A,TOKEN_B'.encode('utf-8')")
        result = subprocess.run([sys.executable, "-c", program],
                                input=base64.b64encode(encrypted).decode("ascii"),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_service_secrets_restore_but_password_and_extra_secrets_do_not(self):
        config = defaults()
        config["common"]["password"] = "PASSWORD_SECRET"
        config["ai"]["key"] = "KEY_SECRET"
        config["question_bank"]["yanxi_tokens"] = "TOKEN_A,TOKEN_B"
        config["custom"] = {"unknown_token": "UNKNOWN_SECRET"}
        saved = serialize_settings(config)
        for secret in ("PASSWORD_SECRET", "KEY_SECRET", "TOKEN_A", "TOKEN_B", "UNKNOWN_SECRET"):
            self.assertNotIn(secret, saved)
        restored = parse_text(saved)
        restore_credentials(restored)
        self.assertEqual(restored["ai"]["key"], "KEY_SECRET")
        self.assertEqual(restored["question_bank"]["yanxi_tokens"], "TOKEN_A,TOKEN_B")
        self.assertEqual(restored["common"]["password"], "")
        self.assertEqual(restored["custom"]["unknown_token"], "")
        self.assertNotIn(CREDENTIAL_SECTION, to_payload(restored))
        self.assertNotIn(CREDENTIAL_SECTION, serialize(restored))
        self.assertIn("KEY_SECRET", serialize(restored))

    def test_corrupt_ciphertext_is_rejected(self):
        encrypted = credentials.protect(b"SECRET")
        with self.assertRaises(OSError):
            credentials.unprotect(encrypted[:20])

    def test_invalid_decrypted_structure_never_partially_restores_secrets(self):
        config = defaults()
        config[CREDENTIAL_SECTION] = {"format": "dpapi-v1", "data": "AA=="}
        invalid = {"question_bank": {"yanxi_tokens": "TOKEN"}, "ai": {"key": 123}}
        with patch.object(credentials, "unprotect", return_value=json.dumps(invalid).encode()):
            with self.assertRaisesRegex(ValueError, "无法解密"):
                restore_credentials(config)
        self.assertEqual(config["question_bank"]["yanxi_tokens"], "")

    def test_legacy_file_does_not_require_dpapi(self):
        config = parse_text("[common]\nuse_cookies = \n[ai]\nmodel = previous-model\n")
        with patch.object(credentials, "unprotect", side_effect=AssertionError("not needed")):
            restore_credentials(config)
        self.assertEqual(config["ai"]["model"], "previous-model")


if __name__ == "__main__":
    unittest.main()
