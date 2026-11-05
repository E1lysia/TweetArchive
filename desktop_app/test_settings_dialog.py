import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import app as manager
from settings_dialog import SettingsDialog
from storage import archive_options
from translation_engine import load_config, CONFIG_FILE

qt=manager.QApplication.instance() or manager.QApplication([])


class UnifiedSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.data=self.base/'资料';self.runtime=self.base/'程序'
        manager.initialize_library(self.data);self.runtime.mkdir()
        self.d=SettingsDialog(self.data,self.runtime,combo_class=manager.ReadableComboBox)
        self.d.setAttribute(manager.Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.d.show();qt.processEvents()

    def tearDown(self):
        self.d.close();qt.processEvents();self.temp.cleanup()

    def test_switch_keeps_draft_and_save_only_changes_current_page(self):
        self.d.storage.replies.setChecked(True)
        self.d.navigation.setCurrentRow(1)
        self.d.translation.engine.setCurrentIndex(self.d.translation.engine.findData('deepseek'))
        self.d.translation.key.setText('test-provider-key')
        self.d.save_current()
        self.assertFalse(archive_options(self.data)['include_replies'])
        self.assertEqual(load_config(self.runtime)['profiles']['deepseek']['api_key'],'test-provider-key')
        self.assertFalse((self.data/'tools'/CONFIG_FILE).exists())
        self.d.navigation.setCurrentRow(0);self.d.save_current()
        self.assertTrue(archive_options(self.data)['include_replies'])
        self.assertTrue(self.d.isVisible())

    def test_login_is_separate_and_inspection_does_not_create_credentials(self):
        self.d.navigation.setCurrentRow(2)
        self.assertFalse(self.d.save_button.isVisible())
        self.assertIn('尚未导入',self.d.login_status.text())
        self.assertFalse((self.runtime/'cookies.txt').exists())
        (self.runtime/'cookies.txt').write_text('fixture',encoding='utf-8')
        self.d.refresh_login_status();self.assertIn('已导入',self.d.login_status.text())
        self.assertFalse((self.runtime/'tools'/CONFIG_FILE).exists())
        self.assertFalse(any('导入' in b.text() for b in self.d.translation.findChildren(manager.QPushButton)))

    def test_storage_selection_uses_shared_dialog_and_busy_disables_changes(self):
        target=self.base/'新位置'
        with patch('storage_settings.QFileDialog.getExistingDirectory',return_value=str(target)):
            self.d.storage.choose('copy')
        self.assertEqual(self.d.selection,('copy',target))
        self.assertEqual(self.d.result(),manager.QDialog.DialogCode.Accepted)
        other=SettingsDialog(self.data,self.runtime,busy=True)
        self.assertFalse(other.storage.isEnabled());self.assertFalse(other.save_button.isEnabled())
        other.navigation.setCurrentRow(1);self.assertTrue(other.save_button.isEnabled());other.close()

    def test_try_translation_emits_once_and_preserves_config(self):
        called=[];self.d.test_requested.connect(lambda:called.append(True))
        self.d.navigation.setCurrentRow(1);self.d.translation.test.click()
        self.assertEqual(called,[True]);self.assertTrue((self.runtime/'tools'/CONFIG_FILE).exists())


if __name__=='__main__':unittest.main()
