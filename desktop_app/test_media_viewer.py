import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import app as manager
import test_archive_ui as fixtures
from media_viewer import MediaViewer
from PySide6.QtTest import QTest
from PySide6.QtCore import QPoint,QPointF
from PySide6.QtGui import QMouseEvent


class MediaPreviewTests(unittest.TestCase):
    setUp=fixtures.ArchiveUiTests.setUp
    tearDown=fixtures.ArchiveUiTests.tearDown

    def prepare_images(self):
        for name,size in [('portrait.png',(240,480)),('landscape.png',(640,320))]:
            image=manager.QImage(*size,manager.QImage.Format.Format_RGB32)
            image.fill(manager.QColor('#72cabb'));image.save(str(self.root/name))
        for doc in self.w.library.docs:
            doc['images']=['portrait.png','landscape.png'];doc['media_state']='local'
        self.w.filter();fixtures.qt.processEvents()

    def test_click_selected_image_opens_in_app_at_current_index(self):
        self.prepare_images();self.w.media.setCurrentIndex(1)
        with patch('media_viewer.QDesktopServices.openUrl') as external:
            QTest.mouseClick(self.w.photo,manager.Qt.MouseButton.LeftButton)
            fixtures.qt.processEvents()
            viewer=self.w.media_viewer
            self.assertIsInstance(viewer,MediaViewer);self.assertEqual(viewer.index,1)
            self.assertEqual(viewer.current[1],self.root/'landscape.png')
            self.assertTrue(viewer.isVisible());external.assert_not_called()
            viewer.reject();self.assertIsNone(self.w.media_viewer)

    def test_zoom_fit_and_navigation_preserve_image_proportions(self):
        self.prepare_images();self.w.open_media_preview();viewer=self.w.media_viewer
        fixtures.qt.processEvents()
        self.assertAlmostEqual(viewer.image.transform().m11(),viewer.image.transform().m22())
        viewer.image.actual_size();self.assertEqual(viewer.image.transform().m11(),1)
        viewer.move(1);self.assertEqual(viewer.index,1)
        self.assertEqual(viewer.image.item.pixmap().size(),manager.QSize(640,320))
        viewer.move(1);self.assertEqual(viewer.index,1)
        viewer.move(-1);self.assertEqual(viewer.image.item.pixmap().size(),manager.QSize(240,480))
        viewer.reject()

    def test_missing_or_outside_media_never_opens_viewer_or_external_app(self):
        self.prepare_images();self.w.media.blockSignals(True)
        self.w.media.setItemData(0,('image','../outside.png'))
        self.w.media.blockSignals(False)
        with patch.object(manager.QMessageBox,'information') as info,patch('media_viewer.QDesktopServices.openUrl') as external:
            self.w.open_media_preview()
            self.assertIsNone(getattr(self.w,'media_viewer',None));info.assert_called_once();external.assert_not_called()

    def test_video_surface_click_opens_selected_video_with_image_navigation(self):
        self.prepare_images();video=self.root/'sample.mp4';video.write_bytes(b'fixture-not-a-video')
        self.w.current['videos']=['sample.mp4']
        self.w.media.blockSignals(True);self.w.media.addItem('视频',('video','sample.mp4'))
        self.w.media.setCurrentIndex(2);self.w.media.blockSignals(False)
        with patch.object(manager,'MediaViewer') as viewer_class:
            QTest.mouseClick(self.w.video,manager.Qt.MouseButton.LeftButton)
            entries,index,parent,position=viewer_class.call_args.args
            self.assertEqual(entries[2],('video',video));self.assertEqual(index,2)
            viewer_class.return_value.open.assert_called_once()
        self.w.media_viewer=None

    def test_system_fallback_is_explicit_and_close_releases_player(self):
        self.prepare_images();viewer=MediaViewer([('image',self.root/'portrait.png')],parent=self.w)
        with patch('media_viewer.QDesktopServices.openUrl',return_value=True) as external:
            viewer.system_open();self.assertEqual(Path(external.call_args.args[0].toLocalFile()),self.root/'portrait.png')
        viewer.reject();self.assertTrue(viewer.closed)
        self.assertEqual(viewer.player.playbackState(),manager.QMediaPlayer.PlaybackState.StoppedState)
        self.assertTrue(viewer.player.source().isEmpty())

    def mouse_move(self,viewer,widget,point):
        event=QMouseEvent(manager.QEvent.Type.MouseMove,QPointF(point),QPointF(widget.mapToGlobal(point)),
                          manager.Qt.MouseButton.NoButton,manager.Qt.MouseButton.NoButton,manager.Qt.KeyboardModifier.NoModifier)
        fixtures.qt.sendEvent(widget,event);fixtures.qt.processEvents()

    def test_fullscreen_idle_image_hides_bars_and_real_mouse_move_restores(self):
        self.prepare_images();self.w.open_media_preview();viewer=self.w.media_viewer
        viewer.toggle_fullscreen();fixtures.qt.processEvents()
        surface=viewer.image.viewport();point=surface.rect().center()
        self.mouse_move(viewer,surface,point)
        self.assertTrue(viewer.hide_timer.isActive());self.assertEqual(viewer.hide_timer.interval(),2000)
        QTest.qWait(2150)
        self.assertTrue(viewer.controls_hidden);self.assertTrue(viewer.top_bar.isHidden());self.assertTrue(viewer.bottom_bar.isHidden())
        self.mouse_move(viewer,surface,surface.rect().center()+QPoint(12,0))
        self.assertFalse(viewer.controls_hidden);self.assertFalse(viewer.top_bar.isHidden());self.assertFalse(viewer.bottom_bar.isHidden())
        self.assertTrue(viewer.hide_timer.isActive());viewer.reject()

    def test_toolbar_hover_windowed_mode_and_fullscreen_exit_keep_controls(self):
        self.prepare_images();self.w.open_media_preview();viewer=self.w.media_viewer
        surface=viewer.image.viewport()
        self.mouse_move(viewer,surface,surface.rect().center())
        self.assertFalse(viewer.hide_timer.isActive())
        viewer.toggle_fullscreen();fixtures.qt.processEvents()
        self.mouse_move(viewer,surface,surface.rect().center())
        self.assertTrue(viewer.hide_timer.isActive())
        self.mouse_move(viewer,viewer.fullscreen_button,viewer.fullscreen_button.rect().center())
        self.assertFalse(viewer.hide_timer.isActive());self.assertFalse(viewer.controls_hidden)
        self.mouse_move(viewer,surface,surface.rect().center())
        viewer.hide_fullscreen_controls();fixtures.qt.processEvents();self.assertTrue(viewer.controls_hidden)
        viewer.toggle_fullscreen();fixtures.qt.processEvents()
        self.assertFalse(viewer.controls_hidden);self.assertFalse(viewer.hide_timer.isActive())
        self.assertFalse(viewer.top_bar.isHidden());self.assertFalse(viewer.bottom_bar.isHidden())
        viewer.reject();self.assertFalse(viewer.hide_timer.isActive())

    def test_notice_close_dismisses_only_banner_and_new_notice_can_show(self):
        self.w.notice_text.setText('任务结果');self.w.update_notice.show();fixtures.qt.processEvents()
        self.assertTrue(self.w.update_notice.isVisible());self.assertEqual(self.w.notice_close.accessibleName(),'关闭本次提示')
        before=self.w.library.state.execute('SELECT count(*) FROM tasks').fetchone()[0]
        self.w.notice_close.click();fixtures.qt.processEvents();self.assertTrue(self.w.update_notice.isHidden())
        self.assertEqual(self.w.library.state.execute('SELECT count(*) FROM tasks').fetchone()[0],before)
        self.w.update_notice.show();fixtures.qt.processEvents();self.assertTrue(self.w.update_notice.isVisible())


if __name__=='__main__':unittest.main()
