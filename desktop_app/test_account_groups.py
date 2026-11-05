import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import app as manager
import test_archive_ui as fixtures


class AccountGroupUiTests(unittest.TestCase):
    setUp=fixtures.ArchiveUiTests.setUp
    tearDown=fixtures.ArchiveUiTests.tearDown
    def rows(self):
        return [self.w.account_box.itemAt(i).widget() for i in range(self.w.account_box.count())]

    def test_account_context_menu_renames_initial_name_and_preserves_data(self):
        original=dict(self.w.library.accounts[0]);doc=self.w.library.docs[0]
        self.w.library.annotate(doc,favorite=True,tags='保留')
        menu=self.w.build_account_menu('a')
        self.assertIn('重命名账号…',[action.text() for action in menu.actions()])
        action=next(action for action in menu.actions() if action.text()=='重命名账号…')
        with patch.object(manager.QInputDialog,'getText',return_value=('重新命名的账号',True)):
            action.trigger()
        account=self.w.library.accounts[0]
        self.assertEqual(account['name'],'重新命名的账号')
        for key in ['key','handle','folder']:self.assertEqual(account[key],original[key])
        self.assertEqual(len(self.w.library.docs),3)
        self.assertTrue(self.w.library.query(mode='favorites')[0]['favorite'])
        self.assertTrue(all(d['account_name']=='重新命名的账号' for d in self.w.library.docs))
        self.assertEqual(len(self.w.library.query(search='重新命名的账号')),3)

    def test_group_move_collapse_search_and_dissolve_keep_account_selection(self):
        group=self.w.library.create_group('音乐与演出')
        self.w.move_archive_account('a',group['id']);self.w.set_account('a')
        header=next(row for row in self.rows() if row.property('group_header')==group['id'])
        header.click()
        row=next(row for row in self.rows() if row.property('account')=='a')
        self.assertTrue(row.isHidden())
        self.assertEqual(self.w.account,'a')
        self.w.account_search.setText('音乐')
        self.assertFalse(row.isHidden())
        self.w.account_search.clear();self.assertTrue(row.isHidden())
        self.w.library.rename_group(group['id'],'演员');self.w.rebuild_accounts()
        self.assertTrue(any('演员' in row.text() for row in self.rows()))
        with patch.object(manager.QMessageBox,'question',return_value=manager.QMessageBox.StandardButton.Yes):
            self.w.dissolve_account_group(group['id'])
        self.assertEqual(self.w.library.account_groups()['groups'],[])
        self.assertEqual(self.w.account,'a');self.assertEqual(len(self.w.results),3)

    def test_group_metadata_roundtrip_and_rename_validation(self):
        group=self.w.library.create_group('收藏作者');self.w.library.move_account('a',group['id'])
        self.w.library.toggle_group(group['id'])
        other=manager.Library(self.root)
        try:
            state=other.account_groups();self.assertEqual(state['memberships']['a'],group['id'])
            self.assertIn(group['id'],state['collapsed'])
            for bad in ['', 'bad\nname','a'*81]:
                with self.assertRaises(ValueError):other.rename_account('a',bad)
            with self.assertRaises(ValueError):other.create_group('收藏作者')
            with self.assertRaises(ValueError):other.move_account('a','unknown')
        finally:other.state.close()

    def test_compact_settings_opens_unified_window_and_middle_menu_stays_clean(self):
        self.assertIsNone(self.w.settings_button.menu())
        self.assertEqual(self.w.settings_button.text(),'')
        self.assertEqual(self.w.settings_button.parent(),self.w.connection.parent())
        self.assertLess(self.w.settings_button.x(),self.w.connection.x())
        self.assertNotIn('存储与归档…',[action.text() for action in self.w.sync_button.menu().actions()])
        with patch.object(manager.SettingsDialog,'exec',return_value=manager.QDialog.DialogCode.Rejected):
            self.w.settings_button.click()
        self.assertEqual(self.w.settings_dialog.navigation.count(),3)

    def test_group_button_only_creates_group_and_add_account_stays_separate(self):
        with patch.object(manager.QInputDialog,'getText',return_value=('新组',True)),patch.object(self.w.library,'add_account') as add:
            self.w.new_group_button.click()
        self.assertEqual(self.w.library.account_groups()['groups'][0]['name'],'新组')
        add.assert_not_called()
        self.assertNotEqual(self.w.new_group_button.toolTip(),self.w.add_account_button.toolTip())

    def test_popup_search_keeps_filter_until_cleared(self):
        self.assertFalse(self.w.account_search.isVisible())
        self.assertEqual(self.w.all_accounts_button.parent(),self.w.account_search_button.parent())
        self.w.toggle_account_search();fixtures.qt.processEvents()
        self.assertTrue(self.w.account_search_popup.isVisible())
        self.w.account_search.setText('没有这个作者')
        self.assertTrue(self.w.account_empty.isVisible())
        from PySide6.QtTest import QTest
        QTest.keyClick(self.w.account_search,manager.Qt.Key.Key_Escape);fixtures.qt.processEvents()
        self.assertFalse(self.w.account_search_popup.isVisible())
        self.assertEqual(self.w.account_search.text(),'没有这个作者')
        self.assertTrue(self.w.account_search_button.isChecked())
        self.w.toggle_account_search();self.w.account_search.clear()
        self.w.account_search_popup.hide();fixtures.qt.processEvents()
        self.assertFalse(self.w.account_search_button.isChecked())
        self.assertFalse(self.w.account_empty.isVisible())


if __name__=='__main__':unittest.main()
