import base64
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage
from chaoxing_desktop.bank_question import ImageEncoder, clean_title, yanxi_environment


class BankQuestionTests(unittest.TestCase):
    def test_metadata_removed_without_removing_math(self):
        self.assertEqual(clean_title('5【单选题】2025年服务业占比（）'), '2025年服务业占比（）')
        self.assertEqual(clean_title('11【多选题】2026年有哪些措施'), '2026年有哪些措施')
        self.assertEqual(clean_title('12.【单选题】1+1=？（2.0分）'), '1+1=？')
        self.assertEqual(clean_title('(多选题, 3分)以下正确的是'), '以下正确的是')
        self.assertEqual(clean_title('1.5+2.5=( )'), '1.5+2.5=( )')
        self.assertEqual(clean_title('化简 (2+3)×4'), '化简 (2+3)×4')

    def test_text_no_images_keeps_suggestion_fields_empty(self):
        encoder = Mock()
        env = yanxi_environment(dict(title=' 1.【单选题】<p>1&lt;2 是否正确</p>（2分）', options='A. 正确\nB. 错误', type='judgement'), encoder)
        self.assertEqual(env['title'], '1<2 是否正确')
        self.assertEqual(env['options'], '正确\n错误')
        self.assertEqual(env['images'], [])
        self.assertEqual(env['suggestion_title'], '')
        self.assertEqual(env['suggestion_options'], '')
        encoder.encode.assert_not_called()

    def test_image_placeholders_follow_title_option_order_and_deduplicate_urls(self):
        encoder = Mock()
        encoder.encode.side_effect = ['data:image/png;base64,AA==', 'data:image/png;base64,BB==']
        env = yanxi_environment(dict(title='公式<img src="//example.test/a.png">', options=['A. <img src="https://example.test/b.png">', 'B. <img src="//example.test/a.png">']), encoder)
        self.assertEqual([c.args[0] for c in encoder.encode.call_args_list], ['https://example.test/a.png', 'https://example.test/b.png'])
        self.assertIn('[图片1]', env['suggestion_title'])
        self.assertIn('[图片2]', env['suggestion_options'].splitlines()[0])
        self.assertIn('[图片1]', env['suggestion_options'].splitlines()[1])
        self.assertIn('https://example.test/a.png', env['title'])

    def test_failed_image_fetch_retains_url_and_does_not_invent_placeholders(self):
        warning = Mock()
        encoder = Mock()
        encoder.encode.side_effect = [ValueError('bad image'), 'data:image/png;base64,AA==']
        env = yanxi_environment(dict(title='<img src="https://example.test/a.png"><img src="https://example.test/b.png">'), encoder, warning)
        self.assertIn('https://example.test/a.png', env['suggestion_title'])
        self.assertIn('[图片1]', env['suggestion_title'])
        self.assertNotIn('[图片2]', env['suggestion_title'])
        warning.assert_called_once()

    def test_encoder_produces_png_and_caches_download(self):
        original = QImage(10, 20, QImage.Format.Format_RGB32)
        original.fill(0xFFFFFF)
        stream = QBuffer()
        stream.open(QIODevice.OpenModeFlag.WriteOnly)
        self.assertTrue(original.save(stream, 'PNG'))
        encoder = ImageEncoder()
        with patch.object(encoder, 'download', return_value=bytes(stream.data())) as download:
            encoded = encoder.encode('https://example.test/q.png')
            self.assertEqual(encoder.encode('https://example.test/q.png'), encoded)
        download.assert_called_once()
        image = QImage.fromData(base64.b64decode(encoded.split(',', 1)[1]))
        self.assertEqual((image.width(), image.height()), (256, 512))

    def test_unreadable_image_is_rejected(self):
        encoder = ImageEncoder()
        with patch.object(encoder, 'download', return_value=b'<html>not an image</html>'):
            with self.assertRaises(ValueError):
                encoder.encode('https://example.test/q.png')


if __name__ == '__main__':
    unittest.main()
