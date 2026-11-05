"""Local in-app image viewer and video player; no external URLs are loaded."""
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QEvent
from PySide6.QtGui import QPixmap, QPainter, QDesktopServices, QShortcut, QKeySequence, QCursor
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QGraphicsView, QGraphicsScene, QSlider, QApplication)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget


class ClickableVideoWidget(QVideoWidget):
    clicked=Signal()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.clicked.emit();event.accept()
        else:super().mouseReleaseEvent(event)


class ImageView(QGraphicsView):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self));self.item=None;self.fit_mode=True
        self.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet('background:#0b1018;border:0')
        self.setAccessibleName('大图：滚轮缩放，按住鼠标拖动')

    def load(self,path):
        self.scene().clear();self.item=None
        image=QPixmap(str(path))
        if image.isNull():return False
        self.item=self.scene().addPixmap(image);self.setSceneRect(self.item.boundingRect())
        self.fit_image();return True

    def fit_image(self):
        self.fit_mode=True
        if self.item:
            self.resetTransform();self.fitInView(self.item,Qt.AspectRatioMode.KeepAspectRatio)

    def actual_size(self):
        self.fit_mode=False;self.resetTransform()
        if self.item:self.centerOn(self.item)

    def wheelEvent(self,event):
        if not self.item:event.ignore();return
        delta=event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            factor=1.2 if delta>0 else 1/1.2
            if .01<=self.transform().m11()*factor<=40:
                self.fit_mode=False;self.scale(factor,factor)
            event.accept()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.fit_mode:self.fit_image()


class MediaViewer(QDialog):
    def __init__(self,entries,index=0,parent=None,position=0):
        super().__init__(parent)
        self.entries=[(kind,Path(path)) for kind,path in entries];self.index=index
        self.initial_position=position;self.pending_position=0;self.closed=False
        self.controls_hidden=False;self.pointer_over_media=False;self.last_pointer=None
        self.hide_timer=QTimer(self);self.hide_timer.setSingleShot(True);self.hide_timer.setInterval(2000)
        self.hide_timer.timeout.connect(self.hide_fullscreen_controls)
        self.setWindowTitle('媒体查看');self.resize(1100,780);self.setMinimumSize(760,520)
        self.setWindowFlags(self.windowFlags()|Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        layout=QVBoxLayout(self);layout.setContentsMargins(16,12,16,14);self.main_layout=layout
        self.top_bar=QWidget();top=QHBoxLayout(self.top_bar);top.setContentsMargins(0,0,0,0)
        self.title=QLabel();self.title.setWordWrap(True)
        self.title.setStyleSheet('font-weight:600');top.addWidget(self.title,1)
        self.system_button=QPushButton('系统打开');self.system_button.clicked.connect(self.system_open);top.addWidget(self.system_button)
        self.fullscreen_button=QPushButton('全屏');self.fullscreen_button.clicked.connect(self.toggle_fullscreen);top.addWidget(self.fullscreen_button)
        close=QPushButton('关闭 · Esc');close.clicked.connect(self.reject);top.addWidget(close);layout.addWidget(self.top_bar)
        self.stack=QStackedWidget();self.image=ImageView();self.video=QVideoWidget()
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.stack.addWidget(self.image);self.stack.addWidget(self.video);layout.addWidget(self.stack,1)
        self.bottom_bar=QWidget();bottom=QVBoxLayout(self.bottom_bar);bottom.setContentsMargins(0,0,0,0)
        layout.addWidget(self.bottom_bar)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('color:#f1c17c');self.error.hide();bottom.addWidget(self.error)
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.audio.setVolume(.65)
        self.player.setAudioOutput(self.audio);self.player.setVideoOutput(self.video)
        self.video_controls=QWidget();controls=QHBoxLayout(self.video_controls);controls.setContentsMargins(0,0,0,0)
        self.play=QPushButton('暂停');self.play.clicked.connect(self.toggle_play);controls.addWidget(self.play)
        self.seek=QSlider(Qt.Orientation.Horizontal);self.seek.sliderMoved.connect(self.player.setPosition);controls.addWidget(self.seek,1)
        self.clock=QLabel('00:00 / 00:00');controls.addWidget(self.clock)
        controls.addWidget(QLabel('音量'));self.volume=QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0,100);self.volume.setValue(65);self.volume.setFixedWidth(90)
        self.volume.setAccessibleName('播放音量');self.volume.valueChanged.connect(lambda n:self.audio.setVolume(n/100))
        controls.addWidget(self.volume);bottom.addWidget(self.video_controls)
        row=QHBoxLayout();self.previous=QPushButton('‹ 上一项');self.next=QPushButton('下一项 ›')
        self.previous.clicked.connect(lambda:self.move(-1));self.next.clicked.connect(lambda:self.move(1))
        row.addWidget(self.previous);self.counter=QLabel();row.addWidget(self.counter);row.addWidget(self.next);row.addStretch()
        self.image_tools=QWidget();tools=QHBoxLayout(self.image_tools);tools.setContentsMargins(0,0,0,0)
        fit=QPushButton('适应窗口');fit.clicked.connect(self.image.fit_image);tools.addWidget(fit)
        actual=QPushButton('100%');actual.clicked.connect(self.image.actual_size);tools.addWidget(actual)
        row.addWidget(self.image_tools);bottom.addLayout(row)
        self.hint=QLabel('图片滚轮缩放、拖动查看；← → 切换媒体，F11 全屏。');self.hint.setObjectName('muted');bottom.addWidget(self.hint)
        self.player.durationChanged.connect(lambda n:(self.seek.setRange(0,max(0,n)),self.update_clock()))
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(lambda state:self.play.setText('暂停' if state==QMediaPlayer.PlaybackState.PlayingState else '播放'))
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.errorOccurred.connect(self.playback_error)
        self.shortcuts=[]
        for key,callback in [('Left',lambda:self.move(-1)),('Right',lambda:self.move(1)),('Space',self.toggle_play),('F11',self.toggle_fullscreen)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(callback);self.shortcuts.append(shortcut)
        self.load_current(position)
        for widget in [self,*self.findChildren(QWidget)]:widget.setMouseTracking(True)
        QApplication.instance().installEventFilter(self)

    @property
    def current(self):return self.entries[self.index]

    def load_current(self,position=0):
        self.player.stop();self.player.setSource(QUrl());self.error.hide()
        kind,path=self.current;self.pending_position=position
        self.title.setText(('视频' if kind=='video' else '图片')+' · '+path.name)
        self.counter.setText(f'{self.index+1} / {len(self.entries)}')
        self.previous.setEnabled(self.index>0);self.next.setEnabled(self.index+1<len(self.entries))
        video=kind=='video';self.video_controls.setVisible(video);self.image_tools.setVisible(not video)
        self.stack.setCurrentWidget(self.video if video else self.image)
        if not path.is_file():
            self.error.setText('本地文件不存在，请重新下载或检查存储位置。');self.error.show();return
        if video:
            self.image.scene().clear();self.image.item=None
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            QTimer.singleShot(0,self.start_video)
        elif not self.image.load(path):
            self.error.setText('内置查看器无法读取此图片，可点击“系统打开”。');self.error.show()
        if hasattr(self,'top_bar'):
            if kind=='video' or not self.error.isHidden():self.show_controls()
            elif self.isFullScreen() and not self.controls_hidden:self.arm_hide_timer()

    def start_video(self):
        if not self.closed and self.isVisible() and self.current[0]=='video':self.player.play()

    def showEvent(self,event):
        super().showEvent(event)
        if self.current[0]=='video':QTimer.singleShot(0,self.start_video)
        else:QTimer.singleShot(0,self.image.fit_image)

    def media_status(self,status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia,QMediaPlayer.MediaStatus.BufferedMedia) and self.pending_position:
            position=self.pending_position;self.pending_position=0;self.player.setPosition(position)

    def position_changed(self,n):
        if not self.seek.isSliderDown():self.seek.setValue(n)
        self.update_clock()

    def update_clock(self):
        def clock(n):
            seconds=max(0,n)//1000;return f'{seconds//60:02}:{seconds%60:02}'
        self.clock.setText(clock(self.player.position())+' / '+clock(self.player.duration()))

    def playback_error(self,*args):
        self.error.setText('内置播放失败，可点击“系统打开”使用默认播放器。\n'+self.player.errorString())
        self.error.show()

    def toggle_play(self):
        if self.current[0]!='video':return
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
        else:self.player.play()

    def move(self,delta):
        index=self.index+delta
        if 0<=index<len(self.entries):self.index=index;self.load_current()

    def system_open(self):
        if self.current[1].is_file():
            self.player.pause();QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current[1])))

    def toggle_fullscreen(self):
        if self.isFullScreen():
            if getattr(self,'was_maximized',False):self.showMaximized()
            else:self.showNormal()
        else:
            self.was_maximized=self.isMaximized();self.showFullScreen()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.WindowStateChange and hasattr(self,'fullscreen_button'):
            fullscreen=self.isFullScreen()
            self.fullscreen_button.setText('退出全屏' if fullscreen else '全屏')
            self.show_controls()
            self.main_layout.setContentsMargins(0,0,0,0) if fullscreen else self.main_layout.setContentsMargins(16,12,16,14)
            QTimer.singleShot(0,self.arm_hide_timer)

    def show_controls(self):
        was_hidden=self.controls_hidden
        self.hide_timer.stop();self.controls_hidden=False
        self.top_bar.show();self.bottom_bar.show()
        if was_hidden:
            self.stack.setCursor(self.saved_stack_cursor);self.image.viewport().setCursor(self.saved_image_cursor)
            self.main_layout.activate()

    def arm_hide_timer(self):
        if self.closed or not self.isVisible():return
        position=self.last_pointer if self.last_pointer is not None else QCursor.pos()
        self.pointer_over_media=self.stack.rect().contains(self.stack.mapFromGlobal(position))
        if (self.isFullScreen() and self.current[0]=='image' and self.pointer_over_media and
                self.error.isHidden() and not QApplication.mouseButtons()):
            self.hide_timer.start()
        else:self.hide_timer.stop()

    def hide_fullscreen_controls(self):
        if (self.closed or not self.isFullScreen() or self.current[0]!='image' or
                not self.pointer_over_media or not self.error.isHidden() or QApplication.mouseButtons()):return
        if self.controls_hidden:return
        self.saved_stack_cursor=self.stack.cursor();self.saved_image_cursor=self.image.viewport().cursor()
        self.controls_hidden=True;self.top_bar.hide();self.bottom_bar.hide()
        self.stack.setCursor(Qt.CursorShape.BlankCursor);self.image.viewport().setCursor(Qt.CursorShape.BlankCursor)

    def eventFilter(self,watched,event):
        if not self.closed and isinstance(watched,QWidget) and (watched is self or self.isAncestorOf(watched)):
            kind=event.type()
            if kind in (QEvent.Type.MouseMove,QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease,QEvent.Type.Wheel):
                position=event.globalPosition().toPoint()
                moved=self.last_pointer is None or position!=self.last_pointer
                if moved or kind!=QEvent.Type.MouseMove:
                    self.last_pointer=position;self.show_controls()
                    if kind!=QEvent.Type.MouseButtonPress and not event.buttons():self.arm_hide_timer()
            elif (watched is self and kind in (QEvent.Type.Leave,QEvent.Type.WindowDeactivate)):
                self.pointer_over_media=False;self.show_controls()
        return super().eventFilter(watched,event)

    def done(self,result):
        self.closed=True;self.hide_timer.stop();QApplication.instance().removeEventFilter(self)
        self.player.stop();self.player.setSource(QUrl())
        super().done(result)
