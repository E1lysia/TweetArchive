import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import app as manager
from translation_engine import load_config,atomic_json,CONFIG_FILE
from translation_settings import TranslationSettings
qt=manager.QApplication.instance() or manager.QApplication([])


class TranslationDialogTests(unittest.TestCase):
    def test_switching_preserves_separate_keys_and_cancel_does_not_save(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'tools').mkdir()
            atomic_json(root/'tools/deepl.local.json',dict(api_key='fake-deepl:fx'))
            dialog=TranslationSettings(root,combo_class=manager.ReadableComboBox)
            dialog.show(); qt.processEvents()
            self.assertEqual(dialog.key.text(),'')
            dialog.engine.setCurrentIndex(dialog.engine.findData('deepseek'))
            dialog.key.setText('fake-deepseek'); dialog.model.setText('test-model')
            dialog.engine.setCurrentIndex(dialog.engine.findData('qwen'))
            self.assertEqual(dialog.key.text(),''); dialog.key.setText('fake-qwen')
            dialog.engine.setCurrentIndex(dialog.engine.findData('deepseek'))
            self.assertEqual(dialog.model.text(),'test-model'); self.assertEqual(dialog.key.text(),'')
            self.assertTrue(dialog.save_settings())
            config=load_config(root)
            self.assertEqual(config['engine'],'deepseek')
            self.assertEqual(config['profiles']['deepseek']['api_key'],'fake-deepseek')
            self.assertEqual(config['profiles']['qwen']['api_key'],'fake-qwen')
            self.assertNotIn('fake-deepl',(root/'tools'/CONFIG_FILE).read_text())
            dialog.close()
            before=(root/'tools'/CONFIG_FILE).read_bytes()
            other=TranslationSettings(root); other.key.setText('not-saved'); other.reject()
            self.assertEqual((root/'tools'/CONFIG_FILE).read_bytes(),before)

    def test_invalid_custom_provider_does_not_save(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'tools').mkdir()
            dialog=TranslationSettings(root)
            dialog.engine.setCurrentIndex(dialog.engine.findData('custom'))
            self.assertFalse(dialog.save_settings())
            self.assertFalse((root/'tools'/CONFIG_FILE).exists())
            dialog.close()


if __name__=='__main__': unittest.main()
