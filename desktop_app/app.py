"""Native Windows media archive manager. No local HTTP server required."""
import argparse
import hashlib
import codecs
import json
import os
import sys
import sqlite3
import math
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / 'vendor'), r'D:\gallery-dl\资料库\vendor',
                str(HERE.parent / 'tools'), str(HERE.parent / 'local_archive/tools')]
from PySide6.QtCore import Qt, QSize, QUrl, QTimer, QProcess, QObject, Signal, QRunnable, QThreadPool, QLockFile, QRect, QEvent, QPointF
from PySide6.QtGui import QPixmap, QImage, QImageReader, QIcon, QDesktopServices, QColor, QPainter, QFont, QPalette, QIntValidator, QTextLayout, QTextOption, QFontMetrics, QPen, QPolygonF
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem, QSplitter, QComboBox,
    QTextBrowser, QScrollArea, QFrame, QDialog, QFormLayout, QDialogButtonBox, QMessageBox,
    QStackedWidget, QSlider, QCheckBox, QPlainTextEdit, QInputDialog, QGridLayout, QSpinBox,
    QButtonGroup, QListView, QMenu, QStyledItemDelegate, QStyle, QSizePolicy, QToolButton, QFileDialog, QProgressDialog)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from library import Library, initialize_library, import_login_file, source_tweet_url
from video_posters import poster_file
from translation_engine import load_config, read_json, PROVIDERS, TranslationError
from translation_settings import TranslationSettings
from storage import resolve_library, select_library, validate_library, empty_destination, copy_library
from storage_settings import StorageSettings, HistorySettings
from settings_dialog import SettingsDialog
from media_viewer import MediaViewer, ClickableVideoWidget
from version import VERSION
from adaptive_cards import AdaptiveCards, masonry_frames
from text_presentation import readable_text
POST_TYPES = ['', 'original', 'quote', 'retweet', 'reference']
TYPE_LABELS = dict(original='原创', quote='引用', retweet='转推', reference='关联来源')
TYPE_COLORS = dict(original='#78dfbd', quote='#9fc2ff', retweet='#f1c17c', reference='#c8b2e9')

STYLE = '''
* { font-family:"Microsoft YaHei UI"; font-size:13px; }
QMainWindow,QDialog { background:#10151e; color:#e7edf5; }
QWidget { color:#dfe7f2; }
QWidget#topbar { background:#141b26; border-bottom:1px solid #242e3e; }
QWidget#sidebar { background:#141b26; border-right:1px solid #242e3e; }
QWidget#feedContent { background:#10151e; }
QFrame#detail { background:#171f2b; border-left:1px solid #2c384a; }
QLabel#brand { font-size:23px; font-weight:700; color:#f3f8f8; }
QLabel#heading { font-size:23px; font-weight:700; }
QLabel#muted { color:#99a9be; font-size:12px; }
QLabel#section { color:#8193ab; font-size:11px; padding:12px 2px 4px; }
QLabel#sidebarSection { color:#cfdeee; font-size:15px; font-weight:700; padding:13px 2px 8px; }
QCheckBox { spacing:9px; }
QCheckBox::indicator { width:19px; height:19px; border:2px solid #74879e; border-radius:4px; background:#1a2432; }
QCheckBox::indicator:checked { background:#79e4bf; border-color:#a5f5d9; image:url("__CHECK_ICON__"); }
QCheckBox::indicator:unchecked:hover { border-color:#a5f5d9; background:#273c49; }
QCheckBox::indicator:disabled { border-color:#526175; background:#26313f; }
QCheckBox::indicator:checked:disabled { background:#73aa98; }
QWidget#updateNotice { background:#1c3535; border:1px solid #416761; border-radius:7px; }
QWidget#updateNotice QLabel { color:#d8f3e8; border:0; }
QPushButton,QToolButton { background:#202b3a; border:1px solid #324155; border-radius:7px; padding:8px 12px; }
QPushButton:hover,QToolButton:hover { background:#2a3a4e; border-color:#566c85; }
QPushButton:disabled,QToolButton:disabled { color:#71829a; }
QPushButton#primary,QToolButton#primary { background:#75dfc0; color:#112b26; border:0; font-weight:700; }
QToolButton::menu-button { border-left:1px solid #458e7b; width:18px; }
QToolButton#primary { padding-right:26px; }
QPushButton#ghost { background:transparent; border:0; color:#b6c5d8; }
QPushButton#ghost:hover { background:#243244; }
QPushButton#ghost:disabled { color:#66758b; }
QPushButton#favorite { background:transparent; border:1px solid transparent; color:#b6c5d8; }
QPushButton#favorite:hover { background:#293442; }
QPushButton#favorite:checked { background:#3a3020; border-color:#826b32; color:#ffda73; font-weight:600; }
QPushButton#favorite:checked:hover { background:#493b24; }
QToolButton#compactIcon { background:transparent; border:0; padding:0; border-radius:6px; }
QToolButton#compactIcon:hover { background:#28384b; }
QToolButton#compactIcon:checked { background:#2a443f; }
QToolButton#backToTop { background:#253d3c; border:1px solid #77cfb8; border-radius:19px; padding:0; }
QToolButton#backToTop:hover { background:#36574e; border-color:#a0f0d8; }
QFrame#accountSearchPopup { background:#1a2432; border:1px solid #41546b; border-radius:8px; }
QListWidget#settingsNav { background:#141b26; padding:14px 8px; border-right:1px solid #2c384a; }
QListWidget#settingsNav::item { padding:13px 10px; margin:3px 0; border-radius:6px; color:#adbed2; }
QListWidget#settingsNav::item:selected { background:#243e3a; color:#8ce7ce; }
QPushButton#choice { background:transparent; border:0; padding:7px 10px; color:#adbed2; }
QPushButton#choice:checked { background:#2a443f; color:#93ebd1; font-weight:600; }
QPushButton#nav { text-align:left; border:0; background:transparent; padding:11px 12px; }
QPushButton#nav:checked { background:#243e3a; color:#8ce7ce; }
QLineEdit,QComboBox,QPlainTextEdit,QSpinBox { background:#1a2432; border:1px solid #2c3a4e; border-radius:7px; padding:8px; selection-background-color:#367b70; }
QSpinBox QLineEdit { background:transparent; color:#edf5f5; border:0; padding:0; }
QComboBox QAbstractItemView { background:#1a2432; color:#edf5f5; selection-background-color:#67d6bd; selection-color:#102b28; border:1px solid #537279; outline:0; padding:3px; }
QComboBox QAbstractItemView::item { min-height:30px; padding:5px 10px; background:#1a2432; color:#edf5f5; }
QComboBox QAbstractItemView::item:selected { background:#67d6bd; color:#102b28; }
QListWidget { background:#10151e; border:0; outline:0; }
QListWidget::item { background:transparent; border:0; padding:0; }
QTextBrowser { border:0; background:transparent; font-size:14px; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { background:transparent; width:7px; }
QScrollBar::handle:vertical { background:#41546b; min-height:30px; border-radius:3px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QSlider::groove:horizontal { height:4px; background:#35505a; border-radius:2px; }
QSlider::handle:horizontal { background:#77dfc3; width:12px; margin:-5px 0; border-radius:6px; }
QToolTip { background:#28433f; color:#e7f5f0; border:1px solid #679d8b; padding:5px; }
QMenu { background:#1a2432; color:#edf5f5; border:1px solid #537279; padding:6px; }
QMenu::item { padding:9px 22px; border-radius:4px; }
QMenu::item:selected { background:#367b70; }
QMenu::item:disabled { color:#62767e; }
QMenu::separator { height:1px; background:#30434b; margin:5px 8px; }
'''.replace('__CHECK_ICON__',(HERE/'icons/check.svg').as_posix())


def label(text='', name=''):
    obj = QLabel(text)
    if name:
        obj.setObjectName(name)
    return obj


def star_polygon(rect):
    center=rect.center();radius=min(rect.width(),rect.height())/2
    return QPolygonF([QPointF(center.x()+radius*(1 if i%2==0 else .44)*math.cos(-math.pi/2+i*math.pi/5),
                             center.y()+radius*(1 if i%2==0 else .44)*math.sin(-math.pi/2+i*math.pi/5)) for i in range(10)])


def star_icon(saved):
    pix=QPixmap(40,40);pix.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pix);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('#ffd35e' if saved else '#b6c5d8'),2))
    painter.setBrush(QColor('#ffd35e') if saved else Qt.BrushStyle.NoBrush)
    painter.drawPolygon(star_polygon(QRect(3,3,34,34)));painter.end();pix.setDevicePixelRatio(2)
    return QIcon(pix)


def compact_icon(kind, title, callback):
    """Draw crisp small icons without depending on symbol-font coverage."""
    pix=QPixmap(40,40); pix.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pix); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2,2); painter.setPen(QPen(QColor('#b6cbdc'),1.5))
    if kind=='search':
        painter.drawEllipse(QPointF(8.5,8.5),5,5); painter.drawLine(QPointF(12.3,12.3),QPointF(17,17))
    elif kind=='folder':
        painter.drawPolyline(QPolygonF([QPointF(2,7),QPointF(2,4),QPointF(8,4),QPointF(10,6),QPointF(18,6),QPointF(18,16),QPointF(2,16),QPointF(2,7)]))
        painter.drawLine(10,9,10,14); painter.drawLine(7,11,13,11)
    elif kind=='account':
        painter.drawEllipse(QPointF(7,6),3,3); painter.drawArc(2,11,10,8,0,180*16)
        painter.drawLine(16,10,16,16); painter.drawLine(13,13,19,13)
    elif kind=='up':
        painter.setPen(QPen(QColor('#9ce8d3'),1.8))
        painter.drawPolyline(QPolygonF([QPointF(4,10),QPointF(10,4),QPointF(16,10)]))
        painter.drawLine(10,4,10,17)
    elif kind=='close':
        painter.drawLine(5,5,15,15);painter.drawLine(15,5,5,15)
    else:
        points=[]
        for i in range(32):
            angle=math.tau*i/32; radius=8 if i%4 in (1,2) else 6.2
            points.append(QPointF(10+radius*math.cos(angle),10+radius*math.sin(angle)))
        painter.drawPolygon(QPolygonF(points)); painter.drawEllipse(QPointF(10,10),2.6,2.6)
    painter.end(); pix.setDevicePixelRatio(2)
    tool=QToolButton(); tool.setObjectName('compactIcon'); tool.setFixedSize(30,30)
    tool.setIcon(QIcon(pix)); tool.setIconSize(QSize(20,20)); tool.setToolTip(title)
    tool.setAccessibleName(title); tool.clicked.connect(callback)
    return tool


def button(text, callback=None, primary=False):
    obj = QPushButton(text)
    obj.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        obj.setObjectName('primary')
    if callback:
        obj.clicked.connect(callback)
    return obj


class ReadableComboBox(QComboBox):
    """Keep popup colors independent of the Windows light menu palette."""
    def __init__(self):
        super().__init__()
        view = QListView()
        view.setUniformItemSizes(True)
        palette = view.palette()
        for role, color in [(QPalette.ColorRole.Base, '#17262c'),
                            (QPalette.ColorRole.Window, '#17262c'),
                            (QPalette.ColorRole.Text, '#edf5f5'),
                            (QPalette.ColorRole.WindowText, '#edf5f5'),
                            (QPalette.ColorRole.Highlight, '#67d6bd'),
                            (QPalette.ColorRole.HighlightedText, '#102b28')]:
            palette.setColor(role, QColor(color))
        view.setPalette(palette)
        self.setView(view)


class ChoiceButtons(QWidget):
    """Visible, exclusive choices with the same index signals as the old selector."""
    currentIndexChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.buttons = []
        self.index = -1
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(3)
        self.group.idClicked.connect(self.setCurrentIndex)

    def addItems(self, titles):
        for title in titles:
            b = button(title)
            b.setObjectName('choice')
            b.setCheckable(True)
            self.group.addButton(b, len(self.buttons))
            self.buttons.append(b)
            self.row.addWidget(b)
        if self.index < 0 and self.buttons:
            self.setCurrentIndex(0)

    def count(self):
        return len(self.buttons)

    def currentIndex(self):
        return self.index

    def setCurrentIndex(self, index):
        if 0 <= index < len(self.buttons):
            changed = index != self.index
            self.index = index
            self.buttons[index].setChecked(True)
            if changed:
                self.currentIndexChanged.emit(index)


class TypeChoices(ChoiceButtons):
    """OR-combined type choices, with backward-compatible single-index restore."""
    def __init__(self):
        super().__init__()
        self.selected_types=set(POST_TYPES[1:])
        self.group.setExclusive(False)
        self.group.idClicked.disconnect()
        self.group.idClicked.connect(self.toggle_type)

    def types(self):
        return set(self.selected_types)

    def setTypes(self, values):
        values=set(values)&set(POST_TYPES[1:])
        if not values: values=set(POST_TYPES[1:])
        changed=values!=self.selected_types
        self.selected_types=values
        self.index=POST_TYPES.index(next(iter(values))) if len(values)==1 else 0
        for index,b in enumerate(self.buttons):
            active=len(values)==4 if index==0 else POST_TYPES[index] in values
            b.setChecked(active)
            b.setText(('✓ ' if active and index else '')+(['全部','原创','引用','转推','关联来源'][index]))
        if changed:self.currentIndexChanged.emit(self.index)

    def setCurrentIndex(self, index):
        if 0 <= index < 5:self.setTypes(POST_TYPES[1:] if index==0 else [POST_TYPES[index]])

    def toggle_type(self, index):
        values=self.types()
        if index==0:values=set(POST_TYPES[1:])
        elif POST_TYPES[index] in values:
            if len(values)>1:values.remove(POST_TYPES[index])
        else:values.add(POST_TYPES[index])
        self.setTypes(values)


class PageInput(QLineEdit):
    def __init__(self):
        super().__init__('1')
        self.bounds = QIntValidator(1, 1, self)
        self.setValidator(self.bounds)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setPlaceholderText('页码')
        self.setAccessibleName('跳转页码')

    def setRange(self, low, high):
        self.bounds.setRange(low, high)

    def setValue(self, value):
        self.setText(str(value))

    def value(self):
        try:
            value = int(self.text())
        except ValueError:
            value = self.bounds.bottom()
        return min(self.bounds.top(), max(self.bounds.bottom(), value))


class TweetList(QListWidget):
    def __init__(self, window):
        super().__init__()
        self.owner = window
        self.adaptive = False
        self.card_frames = []

    def clear(self):
        self.card_frames = []
        super().clear()

    def doItemsLayout(self):
        super().doItemsLayout()
        if self.adaptive:
            for row,rect in enumerate(self.card_frames[:self.count()]):
                self.setPositionForIndex(rect.topLeft(),self.model().index(row,0))
            self.verticalScrollBar().setRange(0,0)
            self.horizontalScrollBar().setRange(0,0)

    def updateGeometries(self):
        super().updateGeometries()
        if getattr(self,'adaptive',False):
            self.verticalScrollBar().setRange(0,0)
            self.horizontalScrollBar().setRange(0,0)

    def mouseMoveEvent(self,event):
        # Free positioning is required by Qt for masonry, but cards cannot be dragged.
        if self.adaptive and event.buttons() & Qt.MouseButton.LeftButton:
            event.accept();return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        index=self.indexAt(event.position().toPoint())
        link=''
        if self.adaptive and event.button()==Qt.MouseButton.LeftButton and index.isValid():
            doc=index.data(Qt.ItemDataRole.UserRole) or {}
            plan=self.owner.adaptive_renderer.plan(doc,self.visualRect(index).width(),index.data(Qt.ItemDataRole.UserRole+5) or ())
            local=event.position().toPoint()-self.visualRect(index).topLeft()
            if plan['quote_link'].contains(local):link=source_tweet_url(doc)
        super().mouseReleaseEvent(event)
        if link:QDesktopServices.openUrl(QUrl(link))

    def wheelEvent(self, event):
        self.owner.feed_scroll.wheelEvent(event)

    def keyPressEvent(self, event):
        if self.adaptive and self.count():
            key=event.key();row=max(0,self.currentRow());step=max(1,self.owner.feed_scroll.viewport().height()//160)
            target={Qt.Key.Key_Up:row-1,Qt.Key.Key_Left:row-1,Qt.Key.Key_Down:row+1,Qt.Key.Key_Right:row+1,
                    Qt.Key.Key_Home:0,Qt.Key.Key_End:self.count()-1,Qt.Key.Key_PageUp:row-step,Qt.Key.Key_PageDown:row+step}.get(key)
            if target is not None:
                self.setCurrentRow(min(self.count()-1,max(0,target)));self.owner.reveal_card(self.currentRow());event.accept();return
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
                           Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End):
            self.owner.reveal_card(self.currentRow())


class TweetDelegate(QStyledItemDelegate):
    """Draw responsive cards without creating a widget for every tweet."""
    def __init__(self, window):
        super().__init__(window.cards)
        self.window = window

    @staticmethod
    def wrapped(painter, rect, value, lines=3):
        text = QTextLayout(value, painter.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        text.setTextOption(option)
        text.beginLayout()
        y = 0
        for _ in range(lines):
            line = text.createLine()
            if not line.isValid():
                break
            line.setLineWidth(rect.width())
            line.setPosition(QPointF(0, y))
            y += line.height() + 3
        text.endLayout()
        painter.save()
        painter.setClipRect(rect)
        text.draw(painter, QPointF(rect.topLeft()))
        painter.restore()

    def paint(self, painter, option, index):
        doc = index.data(Qt.ItemDataRole.UserRole) or {}
        if not doc:
            return
        if self.window.cards.adaptive:
            self.window.adaptive_renderer.paint(painter,option,index)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setPen(QColor('#78dfc3' if selected else '#3c506a' if hovered else '#2a374a'))
        painter.setBrush(QColor('#192b32' if selected else '#1e2b3c' if hovered else '#192230'))
        painter.drawRoundedRect(rect, 10, 10)
        content = rect.adjusted(12, 12, -12, -12)
        grid = self.window.view.currentIndex() == 0
        kind = doc.get('post_type', 'original') if doc.get('status') == 'archived' else None
        badge = TYPE_LABELS.get(kind, '待核对')
        painter.setFont(QFont('Microsoft YaHei UI', 9))
        badge_width = painter.fontMetrics().horizontalAdvance(badge) + 14
        badge_rect = QRect(content.right() - badge_width, content.top(), badge_width, 24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#29394a'))
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(QColor(TYPE_COLORS.get(kind, '#b4bfcd')))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge)
        author = doc.get('author') or doc.get('handle') or '未知作者'
        avatar = QRect(content.left(), content.top(), 33, 33)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#2b3d49'))
        painter.drawEllipse(avatar)
        painter.setPen(QColor('#a7edda'))
        painter.setFont(QFont('Microsoft YaHei UI', 11))
        painter.drawText(avatar, Qt.AlignmentFlag.AlignCenter, author[0])
        painter.setFont(QFont('Microsoft YaHei UI', 10))
        author_rect = QRect(content.left()+43, content.top(), max(1, content.width()-badge_width-55), 21)
        if doc.get('favorite'):
            star=QRect(author_rect.right()-19,content.top()+1,19,19)
            painter.setPen(QPen(QColor('#ffe08a'),1));painter.setBrush(QColor('#ffd35e'))
            painter.drawPolygon(star_polygon(star));author_rect.adjust(0,0,-25,0)
        painter.setPen(QColor('#ecf2f9'))
        painter.drawText(author_rect, Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(author, Qt.TextElideMode.ElideRight, author_rect.width()))
        painter.setFont(QFont('Microsoft YaHei UI', 9))
        painter.setPen(QColor('#99a9be'))
        date = (doc.get('date_beijing') or '')[:10]
        media = f"{len(doc.get('images', []))} 图" if doc.get('images') else ''
        if doc.get('videos'):
            media += f"  ▷ {len(doc['videos'])} 视频"
        if not media:media='文 · 纯文字' if doc.get('media_state')=='text' else '媒体信息待核对' if doc.get('media_state')=='unknown' else '媒体待下载 / 缺失'
        painter.drawText(QRect(content.left()+43, content.top()+24, content.width()-43, 18), date+'  ·  '+media)
        if not doc.get('images') and not doc.get('videos'):
            painter.setFont(QFont('Microsoft YaHei UI', 10))
            painter.setPen(QColor('#dfe7f2'))
            body_rect=QRect(content.left(),content.top()+53,content.width(),max(40,content.height()-77))
            excerpt=(doc.get('content') if self.window.language.currentIndex()==2 else doc.get('translation_zh') or doc.get('content')) or ('正文待补全' if doc.get('status')=='pending' else '原推无文字正文')
            self.wrapped(painter,body_rect,excerpt.replace('\n',' '),lines=7 if grid else 3)
            painter.setFont(QFont('Microsoft YaHei UI',9));painter.setPen(QColor('#99a9be'))
            suffix=' · 待译' if doc.get('content') and not doc.get('translation_zh') else ''
            painter.drawText(QRect(content.left(),content.bottom()-18,content.width(),20),Qt.AlignmentFlag.AlignLeft,media+suffix)
            painter.restore();return
        if grid:
            image_rect = QRect(content.left(), content.top()+50, content.width(), self.window.card_image_height)
            text_rect = QRect(content.left(), image_rect.bottom()+10, content.width(), 63)
        else:
            image_rect = QRect(content.left(), content.top()+49, 125, 90)
            text_rect = QRect(image_rect.right()+14, image_rect.top(), max(1, content.width()-139), 80)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#0d131c'))
        painter.drawRoundedRect(image_rect, 6, 6)
        source = index.data(Qt.ItemDataRole.UserRole+1)
        if isinstance(source, QPixmap) and not source.isNull():
            fitted = source.scaled(image_rect.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(image_rect.center().x()-fitted.width()//2,
                               image_rect.center().y()-fitted.height()//2, fitted)
        if doc.get('videos') and (self.window.mode == 'videos' or not doc.get('images')):
            painter.setFont(QFont('Microsoft YaHei UI', 9))
            painter.setPen(QColor('#e5fff7'))
            seconds = int(index.data(Qt.ItemDataRole.UserRole+2) or 0) // 1000
            badge = f'▷ {seconds//60:02}:{seconds%60:02}' if seconds else '▷ 视频'
            painter.fillRect(QRect(image_rect.right()-82, image_rect.bottom()-25, 81, 24), QColor('#16352f'))
            painter.drawText(image_rect.adjusted(3, 3, -6, -4), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, badge)
        painter.setFont(QFont('Microsoft YaHei UI', 10))
        painter.setPen(QColor('#dfe7f2'))
        excerpt = ((doc.get('content') if self.window.language.currentIndex()==2 else doc.get('translation_zh') or doc.get('content')) or '无文字正文').replace('\n', ' ')
        if doc.get('status') == 'pending':
            excerpt = '正文待补全 · 点击补充核对'
        self.wrapped(painter, text_rect, excerpt)
        painter.restore()


def fitted_thumbnail(source, size, video=False, duration=0, kind=None):
    """Use a fixed canvas so Qt's icon decoration cannot change media proportions."""
    canvas = QPixmap(size)
    canvas.fill(QColor('#0e171b'))
    painter = QPainter(canvas)
    image = QPixmap.fromImage(source) if isinstance(source, QImage) else source
    if image and not image.isNull():
        fitted = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap((size.width() - fitted.width()) // 2,
                           (size.height() - fitted.height()) // 2, fitted)
    else:
        painter.setPen(QColor('#79d9c2'))
        painter.drawText(canvas.rect(), Qt.AlignmentFlag.AlignCenter, '视频' if video else '图片')
    if video:
        seconds = max(0, int(duration)) // 1000
        badge = f'▷ {seconds // 60:02}:{seconds % 60:02}' if seconds else '▷ 视频'
        painter.setFont(QFont('Microsoft YaHei UI', 10))
        width = painter.fontMetrics().horizontalAdvance(badge) + 16
        x, y = max(0, size.width() - width - 6), max(0, size.height() - 30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 21, 24, 220))
        painter.drawRoundedRect(x, y, width, 24, 5, 5)
        painter.setPen(QColor('#ddfff2'))
        painter.drawText(x, y, width, 24, Qt.AlignmentFlag.AlignCenter, badge)
    if kind in TYPE_LABELS:
        badge = TYPE_LABELS[kind]
        painter.setFont(QFont('Microsoft YaHei UI', 9))
        width = painter.fontMetrics().horizontalAdvance(badge) + 14
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(TYPE_COLORS[kind]))
        painter.drawRoundedRect(5, 5, width, 22, 4, 4)
        painter.setPen(QColor('#12252b'))
        painter.drawText(5, 5, width, 22, Qt.AlignmentFlag.AlignCenter, badge)
    painter.end()
    return canvas


class FitLabel(QLabel):
    wheel_step = Signal(int)
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.source = QPixmap()
        self.wheel_enabled = False
        self.wheel_remainder = 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and not self.source.isNull():
            self.clicked.emit();event.accept()
        else:super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if not self.wheel_enabled:
            event.ignore()
            return
        delta = event.angleDelta().y()
        threshold = 120
        if not delta:
            delta = event.pixelDelta().y()
            threshold = 60
        if not delta:
            event.ignore()
            return
        self.wheel_remainder += delta
        steps = int(self.wheel_remainder / threshold)
        self.wheel_remainder -= steps * threshold
        if steps:
            self.wheel_step.emit(-steps)
        event.accept()

    def set_source(self, pixmap):
        self.source = pixmap
        self.fit()

    def fit(self):
        if not self.source.isNull():
            self.setPixmap(self.source.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    def clear(self):
        self.source = QPixmap()
        self.wheel_enabled = False
        self.wheel_remainder = 0
        super().clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()


class TimePicker(QDialog):
    chosen = Signal(str)
    locate = Signal(bool)

    def __init__(self, counts, selected='', parent=None):
        super().__init__(parent)
        self.setWindowTitle('按年月浏览')
        self.resize(500, 390)
        self.counts = counts
        layout = QVBoxLayout(self)
        layout.addWidget(label('直接选择年份或月份，数字为当前筛选下的推文数量。', 'muted'))
        self.year = ReadableComboBox()
        for year in sorted({month[:4] for month in counts}, reverse=True):
            total = sum(n for m, n in counts.items() if m.startswith(year))
            self.year.addItem(f'{year}年 · {total}条', year)
        if selected:
            self.year.setCurrentIndex(max(0, self.year.findData(selected[:4])))
        layout.addWidget(self.year)
        self.whole_year = button('查看整年', self.choose_year, True)
        layout.addWidget(self.whole_year)
        grid = QGridLayout()
        self.months = []
        for month in range(1, 13):
            b = button('', lambda checked=False, m=month: self.choose_month(m))
            b.setMinimumHeight(57)
            b.setCheckable(True)
            grid.addWidget(b, (month - 1) // 4, (month - 1) % 4)
            self.months.append(b)
        layout.addLayout(grid)
        layout.addWidget(button('全部时间', lambda: self.choose('')))
        layout.addWidget(label('快速定位 · 全部时间', 'section'))
        layout.addWidget(label('清除年月范围，保留账号、内容类型、搜索和排序。', 'muted'))
        quick = QHBoxLayout()
        self.locate_latest = button('定位到最新一条', lambda: self.jump(False))
        self.locate_oldest = button('定位到最早一条', lambda: self.jump(True))
        self.locate_latest.setEnabled(bool(counts))
        self.locate_oldest.setEnabled(bool(counts))
        quick.addWidget(self.locate_latest)
        quick.addWidget(self.locate_oldest)
        layout.addLayout(quick)
        self.selected = selected
        self.year.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        year = self.year.currentData() or ''
        self.whole_year.setText(f'查看 {year} 全年' if year else '暂无可选年份')
        self.whole_year.setEnabled(bool(year))
        for month, b in enumerate(self.months, 1):
            period = f'{year}-{month:02}'
            count = self.counts.get(period, 0)
            b.setText(f'{month:02}月\n{count}条')
            b.setEnabled(count > 0)
            b.setChecked(period == self.selected)

    def choose(self, period):
        self.chosen.emit(period)
        self.accept()

    def jump(self, oldest):
        self.locate.emit(oldest)
        self.accept()

    def choose_year(self):
        if self.year.currentData():
            self.choose(self.year.currentData())

    def choose_month(self, month):
        period = f'{self.year.currentData()}-{month:02}'
        if self.counts.get(period):
            self.choose(period)


class ThumbSignals(QObject):
    ready = Signal(str, QImage)


class Thumbnail(QRunnable):
    def __init__(self, path, cache, signals):
        super().__init__()
        self.path, self.cache, self.signals = path, cache, signals

    def run(self):
        try:
            from PIL import Image, ImageOps
            stat = self.path.stat()
            key = hashlib.sha256(f'{self.path}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()
            target = self.cache / (key + '.jpg')
            if not target.exists():
                with Image.open(self.path) as original:
                    image = ImageOps.exif_transpose(original).convert('RGB')
                    image.thumbnail((600, 440))
                    image.save(target, quality=82)
            result = QImage(str(target))
            if not result.isNull():
                self.signals.ready.emit(str(self.path), result)
        except (OSError, ValueError):
            pass


class TaskQueue(QObject):
    changed = Signal()
    completed = Signal()

    def __init__(self, library, program_root=None):
        super().__init__()
        self.library = library
        self.program_root=Path(program_root or library.root).resolve()
        self.waiting = []
        self.current = None
        self.last_finished = None
        self.paused=False
        self.stopping=False
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.error)
        self.process.started.connect(self.started)
        self.restore()

    def persist(self):
        tasks=([self.current] if self.current else [])+self.waiting
        self.library.set_preference('task_queue_v1',dict(
            paused=self.paused,program_root=str(self.program_root),data_root=str(self.library.root),
            tasks=[dict(id=t[0],title=t[1],program=t[2],args=t[3],context=t[4]) for t in tasks]))

    def bind_account(self, task):
        for flag in ('-Index','--index'):
            if flag not in task[3] or task[3].index(flag)+1>=len(task[3]):continue
            try:index=int(task[3][task[3].index(flag)+1])
            except ValueError:continue
            if index>0:
                task[4]['indexed_account']=True
                if 'account' not in task[4] and index<=len(self.library.accounts):
                    task[4]['account']=self.library.accounts[index-1]['key']
        return task

    def discard_account(self,key):
        if self.current:raise ValueError('请先暂停任务，等进程停止后再删除账号。')
        removed=[t for t in self.waiting if t[4].get('account')==key]
        self.waiting=[t for t in self.waiting if t[4].get('account')!=key]
        with self.library.state:
            for task in removed:self.library.state.execute(
                "UPDATE tasks SET status='已取消',log=log||? WHERE id=?",('\n账号已从资料库列表删除，本任务取消；已保存内容保留。\n',task[0]))
        if not self.waiting:self.paused=False
        self.persist();self.changed.emit();return len(removed)

    def restore(self):
        self.waiting=[]
        saved=self.library.preference('task_queue_v1',{})
        if not isinstance(saved,dict):saved={}
        plans=saved.get('tasks',[])
        if not isinstance(plans,list):plans=[]
        seen=set()
        def relocate(value):
            for old,new in [(saved.get('program_root'),str(self.program_root)),(saved.get('data_root'),str(self.library.root))]:
                if isinstance(old,str) and old and (value==old or value.startswith(old+'\\') or value.startswith(old+'/')):
                    return new+value[len(old):]
            return value
        for plan in plans:
            if not isinstance(plan,dict):continue
            tid=plan.get('id');program=plan.get('program');args=plan.get('args');context=plan.get('context',{})
            if (type(tid) is not int or tid in seen or not isinstance(program,str) or not program or '\0' in program
                or not isinstance(args,list) or not all(isinstance(arg,str) and '\0' not in arg for arg in args)
                or not isinstance(context,dict)):continue
            row=self.library.state.execute('SELECT title,status FROM tasks WHERE id=?',(tid,)).fetchone()
            if not row or row[1] not in ('等待中','进行中','正在暂停','已暂停'):continue
            self.waiting.append(self.bind_account((tid,row[0],relocate(program),[relocate(arg) for arg in args],context)));seen.add(tid)
        with self.library.state:
            for task in self.waiting:
                self.library.state.execute("UPDATE tasks SET status='已暂停' WHERE id=?",(task[0],))
            # Legacy versions recorded history without runnable plans. Never auto-run it.
            rows=self.library.state.execute("SELECT id FROM tasks WHERE status IN ('等待中','进行中','正在暂停')").fetchall()
            for tid, in rows:
                if tid not in seen:self.library.state.execute(
                    "UPDATE tasks SET status='已中断',log=log||? WHERE id=?",
                    ('\n上次任务未正常结束，未保存可恢复参数；请重新补充或补译，已有内容保留。\n',tid))
        self.paused=bool(self.waiting)
        self.persist()

    def enqueue(self, title, program, args, context=None):
        if self.paused:
            duplicate=next((task for task in self.waiting if task[2]==program and task[3]==args),None)
            if duplicate:return duplicate[0]
        with self.library.state:
            cursor = self.library.state.execute("INSERT INTO tasks(title,status,log) VALUES (?,?,'')", (title,'已暂停' if self.paused else '等待中'))
        self.waiting.append(self.bind_account((cursor.lastrowid, title, program, list(args), dict(context or {}))))
        self.persist()
        self.changed.emit()
        self.start()
        return cursor.lastrowid

    def start(self):
        if self.current or not self.waiting or self.paused:
            return
        self.current = self.waiting.pop(0)
        self.persist()
        if self.current[4].get('kind')=='sync' or self.current[4].get('indexed_account'):
            # Re-resolve the stable account key, including after a restart.
            account=self.current[4].get('account','')
            if self.current[4].get('indexed_account') and not account:
                self.finish_task(False,addition='\n无法确定任务所属账号，请重新补充或补译；未执行此任务。\n');return
            if account:
                index=next((i+1 for i,a in enumerate(self.library.accounts) if a['key']==account),None)
                if index is None:
                    self.finish_task(False,addition='\n账号已不存在，未执行抓取。\n');return
                args=self.current[3]
                for flag in ('-Index','--index'):
                    if flag in args and args.index(flag)+1<len(args):args[args.index(flag)+1]=str(index)
        if self.current[4].get('kind') == 'sync':
            self.current[4].setdefault('account','');self.current[4].setdefault('name','全部账号')
            self.current[4]['before'] = self.library.archive_counts(self.current[4]['account'])
            self.library.reload()
            self.current[4]['before_types'] = self.library.content_counts(self.current[4]['account'])
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.update('进行中')
        from PySide6.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONIOENCODING', 'utf-8')
        env.insert('PYTHONUTF8', '1')
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(self.library.root))
        # The private Windows job in the wrapper owns PowerShell and all children.
        self.process.start(sys.executable,['-u',str(HERE/'task_runner.py'),'--',self.current[2],*self.current[3]])

    def started(self):
        if self.stopping:self.process.kill()

    def pause(self):
        if self.paused or not (self.current or self.waiting):return False
        self.paused=True
        self.stopping=bool(self.current and self.process.state()!=QProcess.ProcessState.NotRunning)
        with self.library.state:
            for task in self.waiting:self.library.state.execute("UPDATE tasks SET status='已暂停' WHERE id=?",(task[0],))
        self.persist()
        if self.current:
            if self.stopping:
                self.update('正在暂停','\n用户暂停：正在停止本任务及其下载子进程；已保存内容保留。\n')
                self.process.kill()
            else:
                # The normal finished signal may already be queued.
                QTimer.singleShot(0,lambda:self.finished(self.process.exitCode(),self.process.exitStatus()) if self.current else None)
        self.changed.emit()
        return True

    def resume(self):
        if not self.paused or self.stopping:return False
        self.paused=False
        with self.library.state:
            for task in self.waiting:self.library.state.execute(
                "UPDATE tasks SET status='等待中',log=log||? WHERE id=?",
                ('\n用户继续：重新检查已保存内容并继续，已完成的媒体按下载记录跳过。\n',task[0]))
        self.persist();self.changed.emit();self.start();return True

    def update(self, status, addition=''):
        if not self.current:
            return
        with self.library.state:
            self.library.state.execute('UPDATE tasks SET status=?,log=log||? WHERE id=?', (status, addition, self.current[0]))
        self.changed.emit()

    def output(self):
        data = bytes(self.process.readAllStandardOutput())
        value = self.decoder.decode(data) if data else ''
        self.update('正在暂停' if self.stopping else '进行中', value)

    def error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.finish_task(False,addition='\n无法启动任务：'+self.process.errorString())

    def finished(self, code, status):
        if not self.current:return
        self.output()
        normal = status==QProcess.ExitStatus.NormalExit
        partial = normal and code==10 and any(Path(str(arg)).name in ('tweet_archive.py','latest_tweets.py','update.ps1') for arg in self.current[3])
        self.finish_task(code==0 and normal, partial=partial)

    def finish_task(self,success,addition='',partial=False):
        if not self.current:return
        paused=self.stopping
        self.update('已暂停' if paused else '部分完成' if partial else '完成' if success else '失败',addition)
        self.last_finished = dict(id=self.current[0], title=self.current[1], context=self.current[4],
                                  success=success and not paused,paused=paused,partial=partial and not paused)
        if paused:self.waiting.insert(0,self.current)
        self.current = None
        self.stopping=False
        if not self.waiting:self.paused=False
        self.persist()
        self.changed.emit()
        self.completed.emit()
        QTimer.singleShot(0, self.start)


class Window(QMainWindow):
    def __init__(self, root, remember=True, program_root=None, data_lock=None):
        super().__init__()
        self.program_root=Path(program_root or root).resolve()
        self.data_lock=data_lock
        self.storage_busy=False
        self.library = Library(root)
        self.remember = remember
        self.closed = False
        self.loaded = False
        self.render_generation = 0
        session = self.library.preference('browse_v2', {}) if remember else {}
        self.session = session if isinstance(session, dict) else {}
        sizes = self.session.get('layout_sizes', {})
        self.layout_sizes = sizes if isinstance(sizes, dict) else {}
        scopes = self.session.get('scopes', {})
        self.scope_states = scopes if isinstance(scopes, dict) else {}
        self._close_when_paused=False
        self.queue = TaskQueue(self.library,self.program_root)
        self.queue.changed.connect(self.task_status)
        self.queue.completed.connect(self.task_completed)
        self.account = ''
        self.mode = 'all'
        active = self.session.get('active', {})
        if isinstance(active, dict):
            if active.get('mode') in ('all', 'images', 'videos', 'text', 'favorites', 'untranslated', 'pending'):
                self.mode = active['mode']
            if active.get('account') in {a['key'] for a in self.library.accounts}:
                self.account = active['account']
        self.period = ''
        self.page = 0
        self.page_size = 48
        self.current = None
        self.results = []
        self.thumb_items = {}
        self.thumb_cache = self.library.root / '_推文归档/预览缓存'
        self.thumb_cache.mkdir(exist_ok=True)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.signals = ThumbSignals()
        self.signals.ready.connect(self.thumbnail_ready)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.65)
        self.player.setAudioOutput(self.audio)
        self.setWindowTitle('TweetArchive '+VERSION+' · 本地归档')
        self.resize(1600, 960)
        self.setMinimumSize(1180, 740)
        self.build()
        self.restore_display_settings()
        self.restore_reading_sizes()
        self.account_search.setText(str(self.session.get('account_search', '')))
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save_session)
        self.feed_scroll.verticalScrollBar().valueChanged.connect(self.schedule_save)
        self.feed_scroll.verticalScrollBar().valueChanged.connect(self.update_back_to_top)
        self.feed_scroll.verticalScrollBar().rangeChanged.connect(self.update_back_to_top)
        self.body.verticalScrollBar().valueChanged.connect(self.schedule_save)
        self.language.currentIndexChanged.connect(self.schedule_save)
        self.language.currentIndexChanged.connect(self.layout_cards)
        self.reload()
        self.task_status()
        if self.queue.paused:
            self.notice_text.setText('有上次暂停或中断的任务。点击右上角“继续”恢复；已下载内容会保留并重新检查。')
            self.update_notice.show()

    def build(self):
        outer = QWidget()
        self.setCentralWidget(outer)
        main = QVBoxLayout(outer)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        topbar = QWidget()
        topbar.setObjectName('topbar')
        self.topbar=topbar
        top = QGridLayout(topbar)
        top.setContentsMargins(22, 16, 22, 16);top.setHorizontalSpacing(22)
        brand=label('◈  TweetArchive', 'brand');top.addWidget(brand,0,0,Qt.AlignmentFlag.AlignLeft)
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索原文、中文、标签或推文 ID…')
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(600)
        self.search.setMinimumWidth(300)
        top.addWidget(self.search,0,1)
        self.task_tools=QWidget();task_tools_layout=QHBoxLayout(self.task_tools)
        task_tools_layout.setContentsMargins(0,0,0,0);task_tools_layout.setSpacing(6)
        self.pause_tasks_button=button('暂停',self.toggle_tasks_pause)
        self.pause_tasks_button.setToolTip('暂停当前及排队任务，保留已下载内容；之后可继续或关闭软件')
        self.pause_tasks_button.setAccessibleName('暂停或继续任务')
        task_tools_layout.addWidget(self.pause_tasks_button)
        self.tasks_button = button('任务队列', self.show_tasks)
        self.tasks_button.setObjectName('ghost')
        task_tools_layout.addWidget(self.tasks_button)
        top.addWidget(self.task_tools,0,2,Qt.AlignmentFlag.AlignRight)
        self.topbar_brand=brand
        side_width=max(brand.sizeHint().width(),self.task_tools.sizeHint().width())
        for column in (0,2):top.setColumnMinimumWidth(column,side_width);top.setColumnStretch(column,1)
        top.setColumnStretch(1,2)
        main.addWidget(topbar)
        splitter = self.splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.splitterMoved.connect(self.schedule_save)
        main.addWidget(splitter, 1)
        side = QWidget()
        side.setObjectName('sidebar')
        side.setMinimumWidth(190)
        side.setMaximumWidth(260)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(15, 10, 15, 18)
        side_layout.addWidget(label('资料库', 'sidebarSection'))
        self.nav = {}
        for key, title in [('all', '▦   全部推文'), ('favorites', '☆   我的收藏'), ('images', '▧   图片图库'), ('videos', '▷   视频库'), ('text', '文   纯文字'), ('untranslated', '文   待翻译'), ('pending', '◷   正文待补全')]:
            b = button(title, lambda checked=False, k=key: self.set_mode(k))
            b.setObjectName('nav')
            b.setCheckable(True)
            self.nav[key] = b
            side_layout.addWidget(b)
        self.nav['all'].setChecked(True)
        accounts_heading = QHBoxLayout()
        self.nav['favorites'].setIcon(star_icon(True));self.nav['favorites'].setText('我的收藏')
        accounts_heading.addWidget(label('归档账号', 'sidebarSection'))
        accounts_heading.addStretch()
        self.new_group_button=compact_icon('folder','新建分组',lambda:self.new_account_group())
        accounts_heading.addWidget(self.new_group_button)
        self.add_account_button=compact_icon('account','添加归档账号',self.add_account)
        accounts_heading.addWidget(self.add_account_button)
        side_layout.addLayout(accounts_heading)
        self.all_accounts_button = button('全部账号', lambda: self.set_account(''))
        self.all_accounts_button.setObjectName('nav')
        self.all_accounts_button.setCheckable(True)
        accounts_row=QHBoxLayout(); accounts_row.setSpacing(4)
        accounts_row.addWidget(self.all_accounts_button,1)
        self.account_search_button=compact_icon('search','搜索归档账号',self.toggle_account_search)
        self.account_search_button.setCheckable(True); accounts_row.addWidget(self.account_search_button)
        side_layout.addLayout(accounts_row)
        self.account_search_popup=QFrame(self,Qt.WindowType.Popup)
        self.account_search_popup.setObjectName('accountSearchPopup')
        self.account_search_popup.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        self.account_search_popup.installEventFilter(self)
        popup_layout=QVBoxLayout(self.account_search_popup); popup_layout.setContentsMargins(8,8,8,8)
        self.account_search = QLineEdit()
        self.account_search.setPlaceholderText('搜索姓名或 @用户名')
        self.account_search.setClearButtonEnabled(True)
        self.account_search.setAccessibleName('搜索归档账号')
        self.account_search.installEventFilter(self)
        self.account_search.textChanged.connect(self.filter_accounts)
        self.account_search.textChanged.connect(self.schedule_save)
        self.account_search.returnPressed.connect(self.account_search_popup.hide)
        popup_layout.addWidget(self.account_search); self.account_search_popup.setFixedWidth(270)
        account_scroll = QScrollArea()
        account_scroll.setWidgetResizable(True)
        account_scroll.setMinimumHeight(95)
        account_content = QWidget()
        account_content.setStyleSheet('background:transparent')
        account_content.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        account_content.customContextMenuRequested.connect(lambda point:self.groups_menu(account_content.mapToGlobal(point)))
        account_layout = QVBoxLayout(account_content)
        account_layout.setContentsMargins(0, 0, 0, 0)
        self.account_box = QVBoxLayout()
        account_layout.addLayout(self.account_box)
        self.account_empty = label('未找到匹配账号', 'muted')
        account_layout.addWidget(self.account_empty)
        account_layout.addStretch()
        account_scroll.setWidget(account_content)
        side_layout.addWidget(account_scroll, 1)
        status_row=QHBoxLayout(); status_row.setSpacing(6)
        self.settings_button=compact_icon('settings','设置：存储、翻译模型与 X 登录',lambda:self.settings())
        status_row.addWidget(self.settings_button)
        self.connection = label('', 'muted')
        self.connection.setWordWrap(True)
        status_row.addWidget(self.connection,1); side_layout.addLayout(status_row)
        splitter.addWidget(side)
        center = self.center = QWidget()
        center_outer = QVBoxLayout(center)
        center_outer.setContentsMargins(0, 0, 0, 0)
        self.feed_scroll = QScrollArea()
        self.feed_scroll.setWidgetResizable(True)
        self.feed_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.feed_scroll.viewport().installEventFilter(self)
        self.feed_content = QWidget()
        self.feed_content.setObjectName('feedContent')
        self.feed_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        center_layout = QVBoxLayout(self.feed_content)
        center_layout.setContentsMargins(22, 20, 22, 10)
        center_layout.setSpacing(12)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.feed_scroll.setWidget(self.feed_content)
        self.back_to_top=compact_icon('up','返回中间内容顶部',self.scroll_to_top)
        self.back_to_top.setParent(self.feed_scroll.viewport())
        self.back_to_top.setObjectName('backToTop')
        self.back_to_top.setFixedSize(38,38)
        self.back_to_top.setAccessibleName('返回顶部')
        self.back_to_top.hide()
        center_outer.addWidget(self.feed_scroll, 1)
        row = QHBoxLayout()
        self.heading = label('全部推文', 'heading')
        self.heading.setWordWrap(True)
        row.addWidget(self.heading)
        row.addStretch()
        self.sync_button = QToolButton()
        self.sync_button.setObjectName('primary')
        self.sync_button.setText('补充全部最新推文')
        self.sync_button.setAccessibleName('补充最新推文')
        self.sync_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.sync_button.clicked.connect(self.sync)
        sync_menu = QMenu(self.sync_button)
        self.current_sync_action = sync_menu.addAction('补充当前账号最新推文', self.sync)
        sync_menu.addAction('补充全部账号最新推文', lambda: self.sync(all_accounts=True))
        sync_menu.addSeparator()
        sync_menu.addAction('补历史正文…', self.history)
        self.sync_button.setMenu(sync_menu)
        row.addWidget(self.sync_button)
        self.complete_pending_button = button('补全推文', self.complete_pending_tweets)
        self.complete_pending_button.setObjectName('primary')
        self.complete_pending_button.setAccessibleName('按原推 ID 补全待补全推文')
        row.addWidget(self.complete_pending_button)
        self.translate_button = button('补译中文', self.translate)
        self.translate_button.setObjectName('ghost')
        row.addWidget(self.translate_button)
        center_layout.addLayout(row)
        self.summary = label('', 'muted')
        center_layout.addWidget(self.summary)
        filters = QHBoxLayout()
        self.time_button = button('全部时间 ▾', self.pick_time)
        self.time_button.setToolTip('选择年月范围，或定位到最新 / 最早记录')
        self.sort = ChoiceButtons()
        self.sort.setAccessibleName('排序方式')
        self.sort.addItems(['新 → 旧', '旧 → 新'])
        self.sort.setToolTip('仅调整当前筛选结果的排列顺序')
        self.view = ChoiceButtons()
        self.view.setAccessibleName('显示方式')
        self.view.addItems(['网格', '列表'])
        filters.addWidget(self.time_button)
        filters.addSpacing(10)
        filters.addWidget(label('排序', 'muted'))
        filters.addWidget(self.sort)
        filters.addStretch()
        filters.addWidget(self.view)
        center_layout.addLayout(filters)
        type_row = QHBoxLayout()
        type_row.addWidget(label('内容类型', 'muted'))
        self.kind = TypeChoices()
        self.kind.setAccessibleName('内容类型，可多选')
        self.kind.setToolTip('可多选，显示所选类型的合集；全部为一键全选。至少保留一种类型。')
        self.kind.addItems(['全部', '原创', '引用', '转推', '关联来源'])
        self.kind.currentIndexChanged.connect(self.filter)
        type_row.addWidget(self.kind)
        type_row.addStretch()
        center_layout.addLayout(type_row)
        self.summary.setWordWrap(True)
        self.update_notice = QWidget()
        self.update_notice.setObjectName('updateNotice')
        notice_layout = QHBoxLayout(self.update_notice)
        notice_layout.setContentsMargins(10, 7, 10, 7)
        self.notice_text = label()
        self.notice_text.setWordWrap(True)
        notice_layout.addWidget(self.notice_text, 1)
        notice_layout.addWidget(button('查看任务日志', self.show_tasks))
        notice_layout.addWidget(button('查看最新', self.show_updated_latest))
        self.notice_close=compact_icon('close','关闭本次提示',self.update_notice.hide)
        notice_layout.addWidget(self.notice_close)
        self.update_notice.hide()
        center_layout.addWidget(self.update_notice)
        self.cards = TweetList(self)
        self.card_sources = {}
        self.adaptive_renderer = AdaptiveCards(self,TYPE_LABELS,TYPE_COLORS,star_polygon)
        self.cards.setItemDelegate(TweetDelegate(self))
        self.cards.setViewMode(QListWidget.ViewMode.IconMode)
        self.cards.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.cards.setMovement(QListWidget.Movement.Static)
        self.cards.setIconSize(QSize(238, 176))
        self.cards.setSpacing(5)
        self.cards.setMouseTracking(True)
        self.cards.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.card_image_height = 176
        self.reflow_timer = QTimer(self)
        self.reflow_timer.setSingleShot(True)
        self.reflow_timer.setInterval(35)
        self.reflow_timer.timeout.connect(self.layout_cards)
        self.cards.setWordWrap(True)
        self.cards.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.cards.currentItemChanged.connect(self.selected)
        center_layout.addWidget(self.cards)
        self.empty = label('没有符合条件的推文', 'muted')
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.empty)
        pager = QHBoxLayout()
        self.first = button('首页', lambda: self.go_to_page(0))
        self.previous = button('上一页', lambda: self.change_page(-1))
        self.next = button('下一页', lambda: self.change_page(1))
        self.last = button('末页', lambda: self.go_to_page(self.page_count() - 1))
        self.page_label = label('', 'muted')
        pager.addWidget(self.first)
        pager.addWidget(self.previous)
        self.page_numbers = QHBoxLayout()
        self.page_numbers.setSpacing(3)
        pager.addLayout(self.page_numbers)
        pager.addWidget(self.next)
        pager.addWidget(self.last)
        self.jump_tools = QWidget()
        jump_row = QHBoxLayout(self.jump_tools)
        jump_row.setContentsMargins(0, 0, 0, 0)
        jump_row.addWidget(label('跳到', 'muted'))
        self.page_jump = PageInput()
        self.page_jump.setFixedWidth(60)
        self.page_jump.returnPressed.connect(lambda: self.go_to_page(self.page_jump.value() - 1))
        jump_row.addWidget(self.page_jump)
        jump_row.addWidget(label('页', 'muted'))
        jump_row.addWidget(button('跳转', lambda: self.go_to_page(self.page_jump.value() - 1)))
        pager.addWidget(self.jump_tools)
        pager.addStretch()
        pager.addWidget(self.page_label)
        self.pager = pager
        pager_widget = QWidget()
        pager_widget.setLayout(pager)
        pager.setContentsMargins(22, 6, 22, 12)
        self.footer_layout = QVBoxLayout()
        self.footer_layout.setContentsMargins(0, 0, 0, 0)
        self.footer_layout.setSpacing(0)
        self.footer_layout.addWidget(pager_widget)
        center_outer.addLayout(self.footer_layout)
        splitter.addWidget(center)
        detail = QFrame()
        self.detail = detail
        detail.setObjectName('detail')
        detail.setMinimumWidth(420)
        detail.setMaximumWidth(900)
        layout = QVBoxLayout(detail)
        self.detail_layout = layout
        layout.setContentsMargins(20, 18, 20, 18)
        self.detail_title = label('推文详情')
        self.detail_title.setStyleSheet('font-size:20px;font-weight:600')
        self.detail_title.setWordWrap(True)
        layout.addWidget(self.detail_title)
        self.detail_date = label('', 'muted')
        layout.addWidget(self.detail_date)
        self.detail_type = label('')
        self.detail_type.setWordWrap(True)
        layout.addWidget(self.detail_type)
        self.reading_tools = QWidget()
        self.reading_row = QHBoxLayout(self.reading_tools)
        self.reading_row.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.reading_tools)
        self.media = ReadableComboBox()
        self.media.currentIndexChanged.connect(self.media_selected)
        layout.addWidget(self.media)
        self.preview = QStackedWidget()
        self.preview.setMinimumHeight(220)
        self.photo = FitLabel()
        self.photo.clicked.connect(self.open_media_preview)
        self.photo.wheel_step.connect(self.switch_image)
        self.photo.setText('选择一条推文查看内容')
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setStyleSheet('background:#0d131c;border-radius:8px')
        self.photo.setMinimumSize(1, 1)
        self.video = ClickableVideoWidget()
        self.video.clicked.connect(self.open_media_preview)
        self.video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.video.setToolTip('点击在软件内放大播放')
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.preview.addWidget(self.photo)
        self.preview.addWidget(self.video)
        self.player.setVideoOutput(self.video)
        layout.addWidget(self.preview, 3)
        controls = QHBoxLayout()
        self.play = button('播放', self.toggle_play)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.clock = label('00:00', 'muted')
        controls.addWidget(self.play)
        controls.addWidget(self.seek, 1)
        controls.addWidget(self.clock)
        self.video_controls = QWidget()
        self.video_controls.setLayout(controls)
        layout.addWidget(self.video_controls)
        self.player.durationChanged.connect(lambda n: self.seek.setRange(0, max(0, n)))
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(lambda s: self.play.setText('暂停' if s == QMediaPlayer.PlaybackState.PlayingState else '播放'))
        self.player.errorOccurred.connect(lambda *args: self.detail_date.setText('视频播放失败，可用“打开媒体”交给系统播放器：' + self.player.errorString()))
        self.language = ChoiceButtons()
        self.language.setAccessibleName('阅读语言')
        self.language.addItems(['双语', '中文', '原文'])
        self.language.currentIndexChanged.connect(self.show_text)
        language_row = QHBoxLayout()
        language_row.addWidget(self.language)
        language_row.addStretch()
        layout.insertLayout(layout.indexOf(self.media), language_row)
        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(False)
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(self.open_body_link)
        layout.addWidget(self.body, 5)
        self.tags = QLineEdit(detail)
        self.tags.setPlaceholderText('添加标签，空格分隔；按回车保存')
        self.tags.editingFinished.connect(self.save_tags)
        self.tags.hide()
        self.favorite = button('收藏', self.toggle_favorite)
        self.favorite.setObjectName('favorite');self.favorite.setCheckable(True)
        self.favorite.setIcon(star_icon(False));self.favorite.setIconSize(QSize(20,20))
        self.reading_row.addWidget(self.favorite)
        self.more_button = button('更多 ···')
        self.more_button.setObjectName('ghost')
        self.more_button.setAccessibleName('推文更多操作')
        self.more_menu = QMenu(self)
        self.more_menu.aboutToShow.connect(self.update_more_actions)
        self.more_menu.addAction('打开原推', self.open_tweet)
        self.source_action = self.more_menu.addAction('打开来源推文', self.open_source)
        self.more_menu.addSeparator()
        self.more_menu.addAction('打开媒体 / 系统播放器', self.open_media)
        self.more_menu.addAction('打开所在文件夹', self.open_folder)
        self.more_menu.addSeparator()
        self.tags_action = self.more_menu.addAction('编辑标签…', self.edit_tags)
        self.more_button.setMenu(self.more_menu)
        self.reading_row.addWidget(self.more_button)
        layout.removeWidget(self.detail_title)
        self.reading_row.insertWidget(0, self.detail_title, 1)
        layout.removeWidget(self.reading_tools)
        layout.insertWidget(0, self.reading_tools)
        layout.removeWidget(self.media)
        self.media_tools = QWidget()
        media_row = QHBoxLayout(self.media_tools)
        media_row.setContentsMargins(0, 0, 0, 0)
        media_row.addWidget(self.media, 1)
        self.media_previous = button('‹', lambda: self.media.setCurrentIndex(max(0, self.media.currentIndex()-1)))
        self.media_next = button('›', lambda: self.media.setCurrentIndex(min(self.media.count()-1, self.media.currentIndex()+1)))
        for arrow, title in [(self.media_previous, '上一项媒体'), (self.media_next, '下一项媒体')]:
            arrow.setObjectName('ghost')
            arrow.setAccessibleName(title)
            arrow.setToolTip(title)
            media_row.addWidget(arrow)
        layout.insertWidget(layout.indexOf(self.preview)+1, self.media_tools)
        splitter.addWidget(detail)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(20, 8, 20, 8)
        self.location = label(str(self.library.root) + '  ·  本地存储', 'muted')
        self.status = label('就绪', 'muted')
        bottom.addWidget(self.location)
        bottom.addStretch()
        bottom.addWidget(self.status)
        main.addLayout(bottom)
        self.search_delay = QTimer(self)
        self.search_delay.setSingleShot(True)
        self.search_delay.setInterval(220)
        self.search.textChanged.connect(lambda: self.search_delay.start())
        self.search_delay.timeout.connect(self.filter)
        self.sort.currentIndexChanged.connect(self.filter)
        self.view.currentIndexChanged.connect(self.filter)

    def restore_reading_sizes(self):
        for widget, compact, full in [(self.first, '«', '首页'), (self.previous, '‹', '上一页'),
                                      (self.next, '›', '下一页'), (self.last, '»', '末页')]:
            widget.setText(compact)
            widget.setToolTip(full)
            widget.setAccessibleName(full)
        sizes = self.layout_sizes.get('reading')
        if not (isinstance(sizes, list) and len(sizes) == 3 and
                all(isinstance(n, int) and n > 0 for n in sizes)):
            sizes = [205, 755, 620]
        self.splitter.setSizes(sizes)

    def eventFilter(self, obj, event):
        if event.type()==QEvent.Type.KeyPress and obj is getattr(self,'account_search',None) and event.key()==Qt.Key.Key_Escape:
            self.account_search_popup.hide();return True
        if event.type() in (QEvent.Type.Show,QEvent.Type.Hide) and obj is getattr(self,'account_search_popup',None):
            self.account_search_button.setChecked(bool(self.account_search.text().strip()) or event.type()==QEvent.Type.Show)
        if event.type() == QEvent.Type.Resize and hasattr(self, 'feed_scroll') and obj is self.feed_scroll.viewport():
            self.update_back_to_top()
            if hasattr(self, 'reflow_timer'):
                self.reflow_timer.start()
        return super().eventFilter(obj, event)

    def update_back_to_top(self,*args):
        if not hasattr(self,'back_to_top'):return
        viewport=self.feed_scroll.viewport()
        self.back_to_top.move(max(0,viewport.width()-self.back_to_top.width()-14),
                              max(0,viewport.height()-self.back_to_top.height()-14))
        self.back_to_top.setVisible(self.feed_scroll.verticalScrollBar().value()>120)
        self.back_to_top.raise_()

    def scroll_to_top(self):
        self.feed_scroll.verticalScrollBar().setValue(0)
        self.update_back_to_top()

    def layout_cards(self):
        if self.closed or not hasattr(self, 'cards'):
            return
        grid = self.view.currentIndex() == 0
        available = max(240, self.feed_scroll.viewport().width()-44)
        adaptive = self.mode=='all' and grid
        anchor = None
        scroll=self.feed_scroll.verticalScrollBar()
        if self.cards.adaptive and self.cards.card_frames:
            top=scroll.value()-self.cards.y()
            for row,rect in enumerate(self.cards.card_frames):
                if rect.top()<=top<=rect.bottom():
                    anchor=(row,rect.top()-top);break
        if self.cards.adaptive != adaptive:
            self.cards.adaptive=adaptive
            self.cards.card_frames=[]
            self.cards.setMovement(QListWidget.Movement.Free if adaptive else QListWidget.Movement.Static)
            self.cards.setResizeMode(QListWidget.ResizeMode.Fixed if adaptive else QListWidget.ResizeMode.Adjust)
            self.cards.setDragEnabled(False)
            self.cards.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)
        if adaptive:
            available=max(1,min(available,self.cards.viewport().width())-4)
            columns=2 if available>=680 else 1
            width=(available-12*(columns-1))//columns
            heights=[]
            for i in range(self.cards.count()):
                item=self.cards.item(i)
                height=self.adaptive_renderer.plan(item.data(Qt.ItemDataRole.UserRole),width,item.data(Qt.ItemDataRole.UserRole+5) or ())['height']
                heights.append(height);item.setSizeHint(QSize(width,height))
            frames,height=masonry_frames(heights,available,columns)
            self.cards.card_frames=frames
            self.cards.setSpacing(0)
            self.cards.setGridSize(QSize())
            self.cards.setFixedHeight(max(1,height+8))
        else:
            self.cards.setSpacing(5)
            self.layout_uniform_cards(available,grid)
        self.cards.doItemsLayout()
        self.feed_content.setMinimumHeight(0)
        self.feed_content.layout().activate()
        self.feed_content.setMinimumHeight(self.feed_content.sizeHint().height())
        if adaptive and anchor and anchor[0]<len(self.cards.card_frames):
            scroll.setValue(self.cards.y()+self.cards.card_frames[anchor[0]].top()-anchor[1])
        compact = self.center.width() < 700
        if compact and self.jump_tools.parent() is not self.center:
            self.footer_layout.addWidget(self.jump_tools, 0, Qt.AlignmentFlag.AlignLeft)
            self.jump_tools.setContentsMargins(22, 0, 0, 10)
        elif not compact and self.pager.indexOf(self.jump_tools) < 0:
            self.jump_tools.setContentsMargins(0, 0, 0, 0)
            self.pager.insertWidget(self.pager.count()-2, self.jump_tools)
        self.cards.viewport().update()

    def layout_uniform_cards(self,available,grid):
        columns = max(1, available // 290) if grid else 1
        width = max(200, (available-12) // columns-10)
        self.card_image_height = min(236, max(156, int((width-30)*.58)))
        height = self.card_image_height+154 if grid else 169
        if grid and self.cards.count() and all(not self.cards.item(i).data(Qt.ItemDataRole.UserRole).get('images') and
                                               not self.cards.item(i).data(Qt.ItemDataRole.UserRole).get('videos') for i in range(self.cards.count())):
            height=min(height,286)
        size = QSize(width, height)
        self.cards.setGridSize(QSize(width+10, height+10))
        for i in range(self.cards.count()):
            self.cards.item(i).setSizeHint(size)
        self.cards.setFixedHeight(max(1, ((self.cards.count()+columns-1)//columns)*(height+10)+12))

    def reveal_card(self, row):
        if not 0 <= row < self.cards.count():
            return
        self.layout_cards()
        rect = self.cards.visualItemRect(self.cards.item(row))
        y = self.cards.y()+rect.center().y()
        self.feed_scroll.verticalScrollBar().setValue(y-self.feed_scroll.viewport().height()//2)

    def update_more_actions(self):
        for action in self.more_menu.actions():
            if not action.isSeparator():
                action.setEnabled(bool(self.current))
        self.source_action.setVisible(bool(self.current and source_tweet_url(self.current)))
        self.tags_action.setText('编辑标签…' + ('（已添加）' if self.current and self.current.get('tags') else ''))

    def edit_tags(self):
        if not self.current:
            return
        text, ok = QInputDialog.getText(self, '编辑标签', '标签用空格分隔：', text=self.tags.text())
        if ok:
            self.tags.setText(text)
            self.save_tags()

    def reload(self):
        self.save_tags()
        restore = self.capture_browse() if self.loaded else self.scope_states.get(self.scope_key(), {})
        try:
            self.library.reload()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '读取资料库失败', str(exc))
            return
        self.rebuild_accounts()
        for key, b in self.nav.items():
            b.setChecked(key == self.mode)
        try:
            cfg = load_config(self.program_root)
            engine = cfg['engine']
            profile = read_json(self.program_root / 'tools/deepl.local.json') if engine=='deepl' else cfg['profiles'][engine]
            configured = bool(profile.get('api_key'))
            name = PROVIDERS[engine]['name']
            self.connection.setText(f'● {name} 已配置' if configured else f'○ {name} 尚未配置')
            if not cfg['enabled']:
                self.connection.setText(f'○ {name} 自动补译已关闭')
        except TranslationError:
            self.connection.setText('○ 翻译配置需检查')
        self.loaded = True
        self.restore_scope(restore,restore_display=False)

    def toggle_account_search(self):
        popup=self.account_search_popup
        if popup.isVisible():popup.hide();return
        point=self.account_search_button.mapToGlobal(self.account_search_button.rect().bottomRight())
        bounds=self.account_search_button.screen().availableGeometry()
        popup.adjustSize()
        x=max(bounds.left(),min(point.x()-popup.width(),bounds.right()-popup.width()))
        y=max(bounds.top(),min(point.y()+5,bounds.bottom()-popup.height()))
        popup.move(x,y);popup.show();self.account_search.setFocus();self.account_search.selectAll()

    def filter_accounts(self, *args):
        if not hasattr(self, 'account_empty'):
            return
        words = self.account_search.text().casefold().split()
        self.account_search_button.setChecked(bool(words) or self.account_search_popup.isVisible())
        self.account_search_button.setToolTip('搜索归档账号：'+self.account_search.text() if words else '搜索归档账号')
        matched=0;group_matches={}
        grouping=self.library.account_groups()
        for i in range(self.account_box.count()):
            b = self.account_box.itemAt(i).widget()
            if b.property('account') is None:continue
            match = all(word in (b.property('search_text') or '') for word in words)
            group=b.property('group_id') or ''
            b.setVisible(match and (bool(words) or group not in grouping['collapsed']))
            matched+=int(match)
            group_matches[group]=group_matches.get(group,0)+int(match)
        for i in range(self.account_box.count()):
            b=self.account_box.itemAt(i).widget()
            if b.property('group_header') is not None:
                group_id=b.property('group_header')
                b.setVisible(not words or bool(group_matches.get(group_id,0)))
                prefix='▾' if words or group_id not in grouping['collapsed'] else '▸'
                b.setText(f"{prefix} {b.property('group_name')}  ({b.property('group_count')})")
        self.account_empty.setVisible(matched == 0)

    def rebuild_accounts(self):
        while self.account_box.count():
            widget=self.account_box.takeAt(0).widget()
            if widget:widget.hide();widget.deleteLater()
        grouping=self.library.account_groups();members=grouping['memberships']
        groups=grouping['groups']+[dict(id='',name='未分组')]
        counts=Counter(d['account'] for d in self.library.docs if d['status']=='archived')
        for group in groups:
            accounts=[a for a in self.library.accounts if members.get(a['key'],'')==group['id']]
            if group['id'] or (grouping['groups'] and accounts):
                prefix='▸' if group['id'] in grouping['collapsed'] else '▾'
                header=button(f"{prefix} {group['name']}  ({len(accounts)})",lambda checked=False,key=group['id']:self.toggle_account_group(key))
                header.setObjectName('ghost');header.setProperty('group_header',group['id'])
                header.setProperty('group_name',group['name']);header.setProperty('group_count',len(accounts))
                header.setStyleSheet('text-align:left;padding:6px 8px;color:#9eafc2')
                header.setToolTip(group['name']+' · 右键可管理分组')
                header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                header.customContextMenuRequested.connect(lambda point,key=group['id'],w=header:self.group_menu(key,w.mapToGlobal(point)))
                self.account_box.addWidget(header)
            for account in accounts:
                count=counts[account['key']]
                name=account['name']
                b=button('',lambda checked=False,key=account['key']:self.set_account(key))
                shown=b.fontMetrics().elidedText(name,Qt.TextElideMode.ElideRight,145)
                b.setText(('  ' if grouping['groups'] else '')+shown+f'   {count}')
                b.setObjectName('nav');b.setCheckable(True);b.setChecked(self.account==account['key'])
                b.setToolTip(f"{name}\n{account['handle']}\n右键：重命名、移动分组")
                b.setProperty('account',account['key']);b.setProperty('group_id',group['id'])
                b.setProperty('search_text',(' '.join(str(account.get(k) or '') for k in ('name','handle','key','folder'))+' '+group['name']).casefold())
                b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(lambda point,key=account['key'],w=b:self.account_menu(key,w.mapToGlobal(point)))
                self.account_box.addWidget(b)
        self.filter_accounts()

    def toggle_account_group(self,group_id):
        if not group_id:return
        self.library.toggle_group(group_id);self.rebuild_accounts()

    def groups_menu(self,position=None):
        menu=QMenu(self)
        menu.addAction('新建分组…',lambda:self.new_account_group())
        menu.exec(position if position is not None else self.all_accounts_button.mapToGlobal(self.all_accounts_button.rect().topRight()))

    def build_account_menu(self,key):
        account=next((a for a in self.library.accounts if a['key']==key),None)
        if account is None:return None
        menu=QMenu(self);info=menu.addAction(account['name']+'  '+account['handle']);info.setEnabled(False)
        menu.addAction('重命名账号…',lambda:self.rename_archive_account(key))
        move=menu.addMenu('移到分组')
        grouping=self.library.account_groups();current=grouping['memberships'].get(key)
        for group in [dict(id=None,name='未分组')]+grouping['groups']:
            action=move.addAction(group['name'],lambda checked=False,g=group['id']:self.move_archive_account(key,g))
            action.setCheckable(True);action.setChecked(current==group['id'])
        move.addSeparator();move.addAction('新建分组并移入…',lambda:self.new_account_group(key))
        menu.addAction('新建分组…',lambda:self.new_account_group())
        menu.addSeparator()
        menu.addAction('删除账号…',lambda:self.remove_archive_account(key))
        return menu

    def account_menu(self,key,position):
        menu=self.build_account_menu(key)
        if menu:menu.exec(position)

    def group_menu(self,key,position):
        menu=QMenu(self);menu.addAction('新建分组…',lambda:self.new_account_group())
        if key:
            menu.addAction('重命名分组…',lambda:self.rename_account_group(key))
            menu.addAction('解散分组（账号移至未分组）',lambda:self.dissolve_account_group(key))
        menu.exec(position)

    def new_account_group(self,account_key=None):
        name,ok=QInputDialog.getText(self,'新建分组','分组名称：')
        if not ok:return
        try:
            group=self.library.create_group(name)
            if account_key:self.library.move_account(account_key,group['id'])
            self.rebuild_accounts()
        except (ValueError,OSError,sqlite3.Error) as exc:QMessageBox.warning(self,'无法新建分组',str(exc))

    def rename_archive_account(self,key):
        account=next((a for a in self.library.accounts if a['key']==key),None)
        if not account:return
        name,ok=QInputDialog.getText(self,'重命名归档账号','新的显示名称：',text=account['name'])
        if not ok:return
        try:self.library.rename_account(key,name);self.reload()
        except (ValueError,OSError) as exc:QMessageBox.warning(self,'无法改名',str(exc))

    def move_archive_account(self,key,group):
        try:self.library.move_account(key,group);self.rebuild_accounts()
        except (ValueError,sqlite3.Error) as exc:QMessageBox.warning(self,'无法移动分组',str(exc))

    def remove_archive_account(self,key):
        account=next((a for a in self.library.accounts if a['key']==key),None)
        if account is None:return
        def busy():return self.storage_busy or self.queue.current or self.queue.stopping or (self.queue.waiting and not self.queue.paused)
        if busy():
            QMessageBox.information(self,'请先暂停任务','请先暂停任务，等显示“已暂停”后再删除账号。');return
        answer=QMessageBox.question(self,'删除归档账号',
            f'从资料库列表中删除“{account["name"]}” {account["handle"]}？\n\n'
            '该账号会从列表及“全部推文”中移除，属于该账号的暂停任务会取消。\n'
            '本地图片、视频、正文、译文及收藏保留；重新添加同一用户名可恢复。',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        if busy():
            QMessageBox.information(self,'请先暂停任务','任务状态已变化，请先暂停再删除账号。');return
        try:
            self.save_tags()
            self.library.remove_account(key)
            cancelled=self.queue.discard_account(key)
            if self.account==key:self.account='';self.page=0;self.account_search.clear()
            self.scope_states={scope:value for scope,value in self.scope_states.items() if scope.partition('|')[2]!=key}
            if getattr(self,'last_synced_account',None)==key:self.last_synced_account=''
            self.clear_detail();self.reload();self.save_session();self.update_notice.hide()
            self.status.setText(f'已删除账号 {account["name"]}；本地资料保留，已取消 {cancelled} 个任务')
        except (ValueError,OSError,sqlite3.Error) as exc:QMessageBox.warning(self,'删除未完成',str(exc))

    def rename_account_group(self,key):
        group=next((g for g in self.library.account_groups()['groups'] if g['id']==key),None)
        if not group:return
        name,ok=QInputDialog.getText(self,'重命名分组','新的分组名称：',text=group['name'])
        if not ok:return
        try:self.library.rename_group(key,name);self.rebuild_accounts()
        except (ValueError,sqlite3.Error) as exc:QMessageBox.warning(self,'无法改名',str(exc))

    def dissolve_account_group(self,key):
        answer=QMessageBox.question(self,'解散分组','将该组账号移至未分组？推文、媒体与收藏保留。')
        if answer!=QMessageBox.StandardButton.Yes:return
        self.library.dissolve_group(key);self.rebuild_accounts()

    def scope_key(self):
        return f'{self.mode}|{self.account}'

    def capture_browse(self):
        scroll = self.feed_scroll.verticalScrollBar()
        return dict(period=self.period, search=self.search.text(), sort=self.sort.currentIndex(),
                    view=self.view.currentIndex(), kind=self.kind.currentIndex(), types=sorted(self.kind.types()), language=self.language.currentIndex(), page=self.page,
                    scroll=scroll.value(), selected=(self.current or {}).get('tweet_id'),
                    selected_account=(self.current or {}).get('account'), media=self.media.currentIndex(),
                    text_scroll=self.body.verticalScrollBar().value())

    @staticmethod
    def normalized_display(state):
        state=state if isinstance(state,dict) else {}
        def choice(key):
            value=state.get(key,0)
            return value if type(value) is int and value in (0,1) else 0
        kind=state.get('kind',0)
        values=state.get('types')
        if isinstance(values,list):
            types={value for value in values if isinstance(value,str) and value in POST_TYPES[1:]}
        else:types={POST_TYPES[kind]} if type(kind) is int and 1<=kind<=4 else set(POST_TYPES[1:])
        if not types:types=set(POST_TYPES[1:])
        return dict(sort=choice('sort'),view=choice('view'),types=sorted(types))

    def capture_display(self):
        return dict(sort=self.sort.currentIndex(),view=self.view.currentIndex(),types=sorted(self.kind.types()))

    def apply_display(self,state):
        state=self.normalized_display(state)
        for widget,key in ((self.sort,'sort'),(self.view,'view')):
            widget.blockSignals(True);widget.setCurrentIndex(state[key]);widget.blockSignals(False)
        self.kind.blockSignals(True);self.kind.setTypes(state['types']);self.kind.blockSignals(False)

    def restore_display_settings(self):
        # Upgrade legacy per-account settings using the last active account once.
        state=self.session.get('display')
        if not isinstance(state,dict):state=self.scope_states.get(self.scope_key(),{})
        self.apply_display(state)

    def schedule_save(self, *args):
        if self.remember and not self.closed and hasattr(self, 'save_timer'):
            self.save_timer.start()

    def save_session(self):
        if self.remember and not self.closed:
            self.scope_states[self.scope_key()] = self.capture_browse()
            self.layout_sizes['reading'] = self.splitter.sizes()
            self.library.set_preference('browse_v2', dict(active=dict(mode=self.mode, account=self.account),
                                                        scopes=self.scope_states, account_search=self.account_search.text(),
                                                        layout='reading', layout_sizes=self.layout_sizes,display=self.capture_display()))

    def remember_scope(self):
        self.save_tags()
        self.scope_states[self.scope_key()] = self.capture_browse()

    def restore_scope(self, state=None, *, restore_display=True):
        if state is None:
            state = self.scope_states.get(self.scope_key(), {})
        if not isinstance(state, dict):
            state = {}
        state=dict(state)
        if restore_display:
            self.apply_display(state)
        else:
            old=self.normalized_display(state)
            current=self.capture_display()
            if old['sort']!=current['sort'] or old['types']!=current['types']:
                state.update(page=0,scroll=0,selected=None,selected_account=None,media=0,text_scroll=0)
            elif old['view']!=current['view']:
                state.update(scroll=0,reveal_selected=True)
        period = str(state.get('period', ''))
        import re
        self.period = period if re.fullmatch(r'\d{4}(?:-\d{2})?', period) else ''
        for widget, field, default in [(self.search, 'search', ''), (self.language, 'language', 0)]:
            widget.blockSignals(True)
            value = state.get(field, default)
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            else:
                widget.setCurrentIndex(min(widget.count() - 1, max(0, value if isinstance(value, int) else 0)))
            widget.blockSignals(False)
        self.search_delay.stop()
        self.filter(restore=state)

    def time_counts(self):
        return Counter((d.get('date_beijing') or '')[:7] for d in
                       self.library.query(self.account, self.mode, self.search.text(), post_types=self.kind.types())
                       if len(d.get('date_beijing') or '') >= 7)

    def pick_time(self):
        dialog = TimePicker(self.time_counts(), self.period, self)
        dialog.chosen.connect(self.set_period)
        dialog.locate.connect(self.jump_edge)
        dialog.exec()

    def set_period(self, period):
        self.period = period
        self.filter()

    def jump_edge(self, oldest):
        self.period = ''
        self.filter()
        if not self.results:
            return
        ascending = self.sort.currentIndex() == 1
        index = 0 if bool(oldest) == ascending else len(self.results) - 1
        page, row = divmod(index, self.page_size)
        if self.page != page:
            self.go_to_page(page)
        self.cards.setCurrentRow(row)
        self.reveal_card(row)
        self.schedule_save()

    def set_mode(self, mode):
        self.remember_scope()
        fallback = self.capture_browse()
        fallback.update(page=0, scroll=0, selected=None, media=0, text_scroll=0)
        self.mode = mode
        for key, b in self.nav.items():
            b.setChecked(key == mode)
        self.restore_scope(self.scope_states.get(self.scope_key(), fallback),restore_display=False)

    def set_account(self, account):
        self.remember_scope()
        fallback = self.capture_browse()
        fallback.update(page=0, scroll=0, selected=None, media=0, text_scroll=0)
        self.account = account
        for i in range(self.account_box.count()):
            b = self.account_box.itemAt(i).widget()
            b.setChecked(b.property('account') == account)
        self.restore_scope(self.scope_states.get(self.scope_key(), fallback),restore_display=False)

    def filter(self, *args, restore=None):
        self.save_tags()
        self.page = 0
        self.results = self.library.query(self.account, self.mode, self.search.text(), self.period, self.sort.currentIndex() == 1,
                                          post_types=self.kind.types())
        if restore and isinstance(restore.get('page'), int):
            self.page = min(max(0, restore['page']), self.page_count() - 1)
        period_label = (self.period.replace('-', '年 ') + '月') if len(self.period) == 7 else (self.period + '年' if self.period else '全部时间')
        self.time_button.setText(period_label + ' ▾')
        names = dict(all='全部推文', images='图片图库', videos='视频库', text='纯文字', favorites='我的收藏', untranslated='待翻译', pending='正文待补全')
        account = next((a['name'] for a in self.library.accounts if a['key'] == self.account), '')
        self.heading.setText((account + ' · ' if account else '') + names[self.mode])
        self.sync_button.setText('补充当前账号最新推文' if self.account else '补充全部最新推文')
        self.sync_button.setToolTip('按已完成补充的时间检查点增量获取，并重叠回扫三天；图片、视频和正文共用时间线结果。旧资料缺口请使用“补历史正文”。')
        self.all_accounts_button.setChecked(not self.account)
        self.current_sync_action.setEnabled(bool(self.account))
        is_pending = self.mode == 'pending'
        self.sync_button.setVisible(not is_pending)
        self.complete_pending_button.setVisible(is_pending)
        self.complete_pending_button.setEnabled(is_pending and bool(self.library.archive_counts(self.account)['pending']))
        self.complete_pending_button.setToolTip('按原推 ID 补全' + ('当前账号' if self.account else '全部账号') + '的所有待补记录；不限年代，不受搜索、日期或内容类型筛选影响。不下载媒体、不自动翻译，可在任务队列暂停。')
        self.kind.setEnabled(not is_pending)
        images = sum(len(d['images']) for d in self.results)
        videos = sum(len(d['videos']) for d in self.results)
        kinds = Counter(d.get('post_type', 'original') for d in self.results if d['status']=='archived')
        details = '  ·  '.join(f'{TYPE_LABELS[k]} {kinds[k]}' for k in TYPE_LABELS if kinds[k])
        self.summary.setText(f'{len(self.results):,} 条推文  /  {images:,} 张图片  /  {videos:,} 个视频')
        self.summary.setToolTip(details)
        if self.mode == 'pending':
            self.summary.setText(f'{len(self.results)} 条记录等待核对正文  ·  点击“补全推文”按原推 ID 获取，不限年代；确认无文字也会正常归档')
        self.render(restore=restore)

    def render(self, restore=None):
        self.render_generation += 1
        generation = self.render_generation
        self.cards.blockSignals(True)
        self.cards.clear()
        self.thumb_items.clear()
        self.card_sources={(doc['account'],doc['tweet_id']):doc for doc in self.library.docs}
        grid = self.view.currentIndex() == 0
        self.cards.setViewMode(QListWidget.ViewMode.IconMode if grid else QListWidget.ViewMode.ListMode)
        self.cards.setIconSize(QSize(238, 176) if grid else QSize(120, 90))
        for d in self.results[self.page * self.page_size:(self.page + 1) * self.page_size]:
            media = f"{len(d['images'])} 图" if d['images'] else ''
            if d['videos']:
                media += f"  ▷ {len(d['videos'])} 视频"
            date = (d.get('date_beijing') or '')[:10]
            title = (d.get('translation_zh') or d.get('content') or '无文字正文').replace('\n', ' ')
            if d['status'] == 'pending':
                title = '正文待补全 · 点击补充核对'
            kind = d.get('post_type', 'original') if d['status']=='archived' else None
            text = f"【{TYPE_LABELS.get(kind, '待核对')}】{d.get('author') or d.get('handle', '')}  {'★' if d['favorite'] else ''}\n{date}  ·  {media}\n{title[:55]}"
            item = QListWidgetItem(text)
            item.setToolTip(f"{TYPE_LABELS.get(kind, '待核对')} · 归档账号：{d.get('account_name') or d['account']}\n作者：{d.get('author') or d.get('handle')}")
            item.setData(Qt.ItemDataRole.UserRole, d)
            item.setSizeHint(QSize(266, 318) if grid else QSize(400, 169))
            pix = fitted_thumbnail(QPixmap(), self.cards.iconSize(), bool(d['videos']), kind=kind)
            item.setIcon(QIcon(pix))
            self.cards.addItem(item)
            if self.mode=='all' and grid and d['images']:
                paths=[self.library.safe_path(relative) for relative in d['images'][:4]]
                dimensions=[]
                for path in paths:
                    size=QImageReader(str(path)).size()
                    dimensions.append((size.width(),size.height()) if size.isValid() else (16,9))
                item.setData(Qt.ItemDataRole.UserRole+3,{})
                item.setData(Qt.ItemDataRole.UserRole+4,[str(path) for path in paths])
                item.setData(Qt.ItemDataRole.UserRole+5,dimensions)
                for path in paths:
                    key=str(path)
                    first=key not in self.thumb_items
                    self.thumb_items.setdefault(key,[]).append(item)
                    if first:self.pool.start(Thumbnail(path,self.thumb_cache,self.signals))
                continue
            if d['videos'] and (self.mode == 'videos' or not d['images']):
                poster = poster_file(self.library.safe_path(d['videos'][0]), self.thumb_cache)
                if poster.is_file():
                    try:
                        duration = json.loads(poster.with_suffix('.json').read_text(encoding='utf-8')).get('duration_ms', 0)
                    except (OSError, ValueError, TypeError):
                        duration = 0
                    item.setIcon(QIcon(fitted_thumbnail(QPixmap(str(poster)), self.cards.iconSize(), True, duration, kind)))
                    item.setData(Qt.ItemDataRole.UserRole+1, QPixmap(str(poster)))
                    item.setData(Qt.ItemDataRole.UserRole+2, duration)
            elif d['images']:
                path = self.library.safe_path(d['images'][0])
                self.thumb_items.setdefault(str(path), []).append(item)
                self.pool.start(Thumbnail(path, self.thumb_cache, self.signals))
        self.cards.blockSignals(False)
        pages = self.page_count()
        self.page_label.setText(f'{self.page + 1} / {pages} 页')
        self.previous.setEnabled(self.page > 0)
        self.first.setEnabled(self.page > 0)
        self.next.setEnabled(self.page + 1 < pages)
        self.last.setEnabled(self.page + 1 < pages)
        self.page_jump.setRange(1, pages)
        self.page_jump.setValue(self.page + 1)
        self.render_page_numbers(pages)
        self.empty.setVisible(not self.results)
        self.empty.setText('还没有归档账号。点击“归档账号”旁的添加账号图标，再通过左下角齿轮 → “X 登录”导入登录文件，然后点击补充。' if not self.library.accounts else '没有符合条件的推文')
        self.layout_cards()
        if not restore:
            self.feed_scroll.verticalScrollBar().setValue(0)
        if self.cards.count():
            index = 0
            if restore:
                for i in range(self.cards.count()):
                    doc = self.cards.item(i).data(Qt.ItemDataRole.UserRole)
                    if doc['tweet_id'] == restore.get('selected') and doc['account'] == restore.get('selected_account'):
                        index = i
                        break
            self.cards.setCurrentRow(index)
        else:
            self.clear_detail()
        if restore:
            def restore_position():
                if self.closed or generation != self.render_generation:
                    return
                index = restore.get('media', 0)
                same_selection = self.current and self.current['tweet_id'] == restore.get('selected') and self.current['account'] == restore.get('selected_account')
                if same_selection and isinstance(index, int) and 0 <= index < self.media.count():
                    self.media.setCurrentIndex(index)
                self.cards.doItemsLayout()
                self.layout_cards()
                self.feed_scroll.verticalScrollBar().setValue(restore.get('scroll', 0))
                if restore.get('reveal_selected') and same_selection:self.reveal_card(self.cards.currentRow())
                self.body.verticalScrollBar().setValue(restore.get('text_scroll', 0) if same_selection else 0)
                self.schedule_save()
            QTimer.singleShot(0, restore_position)
        self.schedule_save()

    def page_count(self):
        return max(1, (len(self.results) + self.page_size - 1) // self.page_size)

    def render_page_numbers(self, pages):
        while self.page_numbers.count():
            widget = self.page_numbers.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        indexes = sorted({0, pages - 1, *range(max(0, self.page - 1), min(pages, self.page + 2))})
        previous = -1
        for index in indexes:
            if previous >= 0 and index - previous > 1:
                self.page_numbers.addWidget(label('…', 'muted'))
            b = button(str(index + 1), lambda checked=False, p=index: self.go_to_page(p), index == self.page)
            b.setStyleSheet('padding:6px 8px;min-width:20px')
            self.page_numbers.addWidget(b)
            previous = index

    def thumbnail_ready(self, path, image):
        for item in self.thumb_items.get(path, []):
            doc = item.data(Qt.ItemDataRole.UserRole)
            kind = doc.get('post_type', 'original') if doc['status']=='archived' else None
            paths=item.data(Qt.ItemDataRole.UserRole+4) or []
            if paths:
                pixmaps=item.data(Qt.ItemDataRole.UserRole+3) or {}
                pixmaps[path]=QPixmap.fromImage(image)
                item.setData(Qt.ItemDataRole.UserRole+3,pixmaps)
            if not paths or path==paths[0]:
                item.setIcon(QIcon(fitted_thumbnail(image, self.cards.iconSize(), kind=kind)))
                item.setData(Qt.ItemDataRole.UserRole+1, QPixmap.fromImage(image))

    def change_page(self, delta):
        self.go_to_page(self.page + delta)

    def go_to_page(self, page):
        self.save_tags()
        self.page = min(max(0, page), self.page_count() - 1)
        self.render()

    def clear_detail(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.current = None
        self.update_favorite_button()
        self.media.clear()
        self.media_previous.setEnabled(False)
        self.media_next.setEnabled(False)
        self.photo.clear()
        self.body.clear()
        self.tags.clear()
        self.detail_title.setText('选择一条推文查看内容')
        self.detail_date.clear()
        self.detail_type.clear()
        self.video_controls.hide()
        self.preview.show();self.media_tools.show()
        self.preview.setCurrentIndex(0)

    def selected(self, item, previous=None):
        self.save_tags()
        if item is None:
            return
        self.current = item.data(Qt.ItemDataRole.UserRole)
        d = self.current
        self.photo.wheel_enabled = len(d['images']) > 1
        self.photo.wheel_remainder = 0
        self.photo.setToolTip('点击查看大图；滚轮向下：下一张，向上：上一张' if self.photo.wheel_enabled else '点击在软件内查看大图')
        self.detail_title.setText(f"{d.get('author') or ''}  {d.get('handle') or ''}")
        self.detail_date.setText((d.get('date_beijing') or '').replace('T', ' ')[:19] + '  北京时间')
        kind = d.get('post_type', 'original') if d['status']=='archived' else None
        owner = d.get('account_name') or next((a['name'] for a in self.library.accounts if a['key']==d['account']), d['account'])
        text = f"{TYPE_LABELS.get(kind, '待核对')} · 归档账号：{owner}"
        if kind == 'retweet':
            text += f" · 原作者：{d.get('author') or d.get('handle')}"
        if kind == 'reference':
            text += ' · 保留原作者，不作为本账号原创'
        if d.get('media_state')=='text':text+=' · 纯文字'
        elif d.get('media_state')=='missing':text+=' · 媒体待下载 / 缺失'
        elif d.get('media_state')=='unknown':text+=' · 媒体信息待核对'
        self.detail_type.setText(text)
        self.detail_type.setStyleSheet(f"color:{TYPE_COLORS.get(kind, '#a4b6bf')};font-size:12px;padding:6px 0")
        self.update_favorite_button()
        self.tags.setText(d['tags'])
        self.media.blockSignals(True)
        self.media.clear()
        for i, path in enumerate(d['images'], 1):
            self.media.addItem(f'图片 {i} / {len(d["images"])}', ('image', path))
        for i, path in enumerate(d['videos'], 1):
            self.media.addItem(f'▷ 视频 {i} / {len(d["videos"])}', ('video', path))
        if self.mode == 'videos' and d['videos']:
            self.media.setCurrentIndex(len(d['images']))
        self.media.blockSignals(False)
        has_media=self.media.count()>0
        self.preview.setVisible(has_media)
        self.media_tools.setVisible(has_media)
        self.video_controls.hide()
        self.media_selected()
        self.show_text()

    def switch_image(self, steps):
        if not self.current:
            return
        count = len(self.current['images'])
        index = self.media.currentIndex()
        if count > 1 and 0 <= index < count:
            self.media.setCurrentIndex(min(count - 1, max(0, index + steps)))

    def media_selected(self, *args):
        self.media_previous.setEnabled(self.media.currentIndex() > 0)
        self.media_next.setEnabled(0 <= self.media.currentIndex() < self.media.count()-1)
        self.player.stop()
        self.player.setSource(QUrl())
        data = self.media.currentData()
        if not data:
            return
        kind, relative = data
        path = self.library.safe_path(relative)
        if not path:
            return
        video = kind == 'video'
        self.video_controls.setVisible(video)
        self.preview.setCurrentIndex(1 if video else 0)
        if video:
            self.player.setSource(QUrl.fromLocalFile(str(path)))
        else:
            self.original_photo = QPixmap(str(path))
            self.photo.set_source(self.original_photo)
            self.resize_photo()
        self.schedule_save()

    def resize_photo(self):
        if hasattr(self, 'photo'):
            self.photo.fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.resize_photo)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def position_changed(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        seconds = position // 1000
        self.clock.setText(f'{seconds // 60:02}:{seconds % 60:02}')

    def show_text(self, *args):
        if not self.current:
            return
        import html
        d = self.current
        def escaped(text):
            return html.escape(readable_text(text,d.get('post_type',''))).replace('\n','<br>')
        original = d.get('content') if (d.get('content') or '').strip() else ('正文待补全；完成核对前不作为原创归档。' if d['status'] == 'pending' else '已确认原推无文字正文')
        if d['status'] == 'pending' and isinstance(d.get('completion_error'), dict):
            original += '\n上次补全：' + str(d['completion_error'].get('reason') or '未取得正文，请查看任务日志。')
        translated = ('正文尚未取得，取得原文后才能翻译。' if d['status']=='pending' else
                      d.get('translation_zh') or ('待翻译，可点击“补译中文”' if d.get('content','').strip() else '已确认原推无文字正文，无需翻译'))
        blocks = []
        if self.language.currentIndex() != 1:
            blocks.append('<p style="color:#95aab2">原文</p><p>' + escaped(original) + '</p>')
        if self.language.currentIndex() != 2:
            blocks.append('<p style="color:#75d9ba">中文翻译</p><p style="color:#b3e7d5">' + escaped(translated) + '</p>')
        if d.get('post_type')=='quote' or d.get('quote_summary'):
            source=source_tweet_url(d)
            link=(' <a style="color:#9fd5ff;text-decoration:underline;font-weight:600" href="'+html.escape(source,quote=True)+'">查看来源推文 ↗</a>') if source else ' · 来源链接暂缺'
            blocks.append('<p style="color:#95aab2">引用来源'+link+'</p>')
            if d.get('quote_summary'):
                summary=self.adaptive_renderer.quote(d) or d['quote_summary']
                blocks.append('<div style="margin:0;padding:0"><p style="margin:6px 0">'+escaped(summary)+'</p></div>')
        self.body.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.document().setDocumentMargin(4)
        self.body.document().setDefaultStyleSheet('p { margin-top:0px; margin-bottom:10px; }')
        self.body.setHtml('<body style="font-size:16px;line-height:1.6;margin:0;padding:0">' + ''.join(blocks) + '</body>')

    def save_tags(self):
        if self.current and hasattr(self, 'tags') and self.tags.text().strip() != self.current['tags']:
            self.library.annotate(self.current, tags=self.tags.text())
            for doc in self.library.docs:
                if (doc['account'], doc['tweet_id']) == (self.current['account'], self.current['tweet_id']):
                    doc['tags'] = self.current['tags']
            self.refresh_annotation()

    def refresh_annotation(self):
        if not self.current:
            return
        for i in range(self.cards.count()):
            item = self.cards.item(i)
            doc = item.data(Qt.ItemDataRole.UserRole)
            if (doc['account'], doc['tweet_id']) == (self.current['account'], self.current['tweet_id']):
                doc.update(favorite=self.current['favorite'], tags=self.current['tags'])
                item.setData(Qt.ItemDataRole.UserRole, doc)

    def update_favorite_button(self):
        saved=bool(self.current and self.current.get('favorite'))
        self.favorite.setChecked(saved);self.favorite.setIcon(star_icon(saved))
        self.favorite.setText('已收藏' if saved else '收藏');self.favorite.setEnabled(bool(self.current))
        self.favorite.setToolTip('取消收藏' if saved else '收藏这条推文')

    def toggle_favorite(self):
        if self.current:
            self.library.annotate(self.current, favorite=not self.current['favorite'])
            self.update_favorite_button()
            # Qt stores a copy of dictionary item data; refresh the library document too.
            for d in self.library.docs:
                if (d['account'], d['tweet_id']) == (self.current['account'], self.current['tweet_id']):
                    d.update(favorite=self.current['favorite'])
            self.refresh_annotation()
            if self.mode == 'favorites':
                self.filter()

    def open_tweet(self):
        if self.current:
            url = self.current.get('url') or ''
            if url.startswith('https://x.com/') or url.startswith('https://twitter.com/'):
                QDesktopServices.openUrl(QUrl(url))

    def open_source(self):
        url=source_tweet_url(self.current or {})
        if url:QDesktopServices.openUrl(QUrl(url))

    def open_body_link(self,url):
        expected=source_tweet_url(self.current or {})
        if expected and url.toString()==expected:QDesktopServices.openUrl(QUrl(expected))

    def open_media(self):
        data = self.media.currentData()
        if data and (path := self.library.safe_path(data[1])):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_media_preview(self):
        data=self.media.currentData()
        if not self.current or not data:return
        selected=self.library.safe_path(data[1])
        if selected is None or not selected.is_file():
            QMessageBox.information(self,'媒体文件不可用','本地文件不存在，请重新下载或检查存储位置。');return
        existing=getattr(self,'media_viewer',None)
        if existing is not None and existing.isVisible():existing.raise_();existing.activateWindow();return
        entries=[]
        for kind,paths in [('image',self.current['images']),('video',self.current['videos'])]:
            for relative in paths:
                path=self.library.safe_path(relative)
                if path is not None and path.is_file():entries.append((kind,path))
        index=next((i for i,entry in enumerate(entries) if entry==(data[0],selected)),None)
        if index is None:return
        position=self.player.position() if data[0]=='video' else 0
        self.player.pause()
        viewer=MediaViewer(entries,index,self,position);self.media_viewer=viewer
        def finished(*args):
            if self.media_viewer is viewer:self.media_viewer=None
            viewer.deleteLater()
        viewer.finished.connect(finished);viewer.open()

    def open_folder(self):
        data = self.media.currentData()
        if data and (path := self.library.safe_path(data[1])):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        elif self.current:
            account=next((a for a in self.library.accounts if a['key']==self.current['account']),None)
            if account and (path:=self.library.safe_path(account['folder'])):
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def python_task(self, title, script, args):
        if script=='tweet_archive.py':args=['--runtime-root',str(self.program_root)]+args
        self.queue.enqueue(title, str(self.program_root / 'python/python.exe'), ['-u', str(self.program_root / 'tools' / script), '--root', str(self.library.root if script=='tweet_archive.py' else self.program_root)] + args)

    def sync(self, checked=False, all_accounts=False):
        if not self.library.accounts:
            QMessageBox.information(self, '请先添加账号', '点击左侧“归档账号”旁的“＋”添加一个 X 用户名，然后补充。')
            return
        selected = [a for a in self.library.accounts if all_accounts or not self.account or a['key'] == self.account]
        for account in selected:
            index = next(i + 1 for i, a in enumerate(self.library.accounts) if a['key'] == account['key'])
            self.queue.enqueue('补充最新推文 · ' + account['name'], 'powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(self.program_root / 'tools/update.ps1'), '-Index', str(index), '-DataRoot', str(self.library.root), '-RuntimeRoot',str(self.program_root)],
                               context=dict(kind='sync', account=account['key'], name=account['name']))
        self.refresh_posters()
        self.status.setText('任务处于暂停状态，点击右上角“继续”开始' if self.queue.paused else '补充已加入任务队列')

    def complete_pending_tweets(self):
        selected = [a for a in self.library.accounts if not self.account or a['key'] == self.account]
        added = 0
        for account in selected:
            if not self.library.archive_counts(account['key'])['pending']:
                continue
            index = next(i + 1 for i, a in enumerate(self.library.accounts) if a['key'] == account['key'])
            args = ['-u', str(self.program_root / 'tools/tweet_archive.py'), '--root', str(self.library.root),
                    '--runtime-root', str(self.program_root), '--index', str(index), '--complete-pending', '--no-translate']
            self.queue.enqueue('补全推文 · ' + account['name'], str(self.program_root / 'python/python.exe'), args,
                               context=dict(kind='sync', account=account['key'], name=account['name'], complete_pending=True))
            added += 1
        if added:
            self.show_tasks()
        else:
            QMessageBox.information(self, '无需补全', '当前账号范围内没有正文待补全的记录。')

    def refresh_posters(self):
        self.queue.enqueue('更新视频封面', str(self.program_root / 'python/python.exe'), ['-u', str(HERE / 'video_posters.py'), '--root', str(self.library.root)])

    def translate(self):
        index = next((i + 1 for i, a in enumerate(self.library.accounts) if a['key'] == self.account), 0)
        args = ['--translate-only', '--index', str(index)]
        for kind in sorted(self.kind.types()):args += ['--translation-type', kind]
        self.translate_button.setToolTip('补译当前账号与所选类型的全部待译正文；不局限当前页、搜索或年月。')
        self.python_task('补译中文', 'tweet_archive.py', args)

    def add_account(self):
        handle, ok = QInputDialog.getText(self, '添加账号', 'X 用户名（不含链接，可带 @）：')
        if not ok:
            return
        name, ok = QInputDialog.getText(self, '添加账号', '显示名称（可留空）：')
        if not ok:
            return
        try:
            self.library.add_account(handle, name)
            self.reload()
            self.status.setText('账号已添加，点击补充开始下载和归档')
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, '添加失败', str(exc))

    def task_status(self):
        if self.closed:return
        count = len(self.queue.waiting) + bool(self.queue.current)
        self.tasks_button.setText(f'任务队列  {count}' if count else '任务队列')
        state='正在暂停…' if self.queue.stopping else '任务已暂停，可继续或关闭软件' if self.queue.paused else (self.queue.current[1]+' · 进行中') if self.queue.current else ('任务等待执行' if self.queue.waiting else '就绪')
        self.status.setText(state)
        self.pause_tasks_button.setText('正在暂停…' if self.queue.stopping else '继续' if self.queue.paused else '暂停')
        self.pause_tasks_button.setEnabled(bool(count) and not self.queue.stopping)
        side_width=max(self.topbar_brand.sizeHint().width(),self.task_tools.sizeHint().width())
        for column in (0,2):self.topbar.layout().setColumnMinimumWidth(column,side_width)
        if hasattr(self, 'task_dialog') and self.task_dialog.isVisible():
            self.refresh_tasks()
        if self._close_when_paused and not self.queue.current and not self.queue.stopping:
            QTimer.singleShot(0,self.close)

    def toggle_tasks_pause(self):
        if self.queue.paused:self.queue.resume()
        else:self.queue.pause()

    def pause_tasks(self):
        self.queue.pause()

    def resume_tasks(self):
        self.queue.resume()

    def task_completed(self):
        if self.closed:return
        self.reload()
        result = self.queue.last_finished or {}
        context = result.get('context', {})
        if result.get('paused'):
            self.notice_text.setText('任务已暂停，已保存的正文和下载文件保留。点击右上角“继续”可重新检查并继续，也可以关闭软件。')
            self.update_notice.show()
            self.status.setText('已暂停；当前和排队任务均已保存')
            return
        if context.get('kind') != 'sync':
            if result.get('partial'):
                self.status.setText('翻译部分完成；失败条目保留待译，原因见任务日志')
            return
        self.last_synced_account = context['account']
        after = self.library.archive_counts(context['account'])
        types = self.library.content_counts(context['account'])
        before_types = context.get('before_types', {})
        before = context.get('before', {})
        new_originals = max(0, after['archived'] - before.get('archived', 0))
        new_excluded = max(0, after['excluded'] - before.get('excluded', 0))
        outcome = '补充完成' if result.get('success') else '补充未全部完成，请查看日志'
        if context.get('complete_pending'):
            resolved = max(0, before.get('pending', 0) - after['pending'])
            outcome = '补全完成' if result.get('success') else '部分完成，剩余记录的原因请查看任务日志' if result.get('partial') else '补全未完成，请查看任务日志'
            self.notice_text.setText(f"{context['name']}：{outcome}。本次补全 {resolved} 条；仍待补全 {after['pending']} 条。确认没有文字的原推已正常归档，需要翻译时再点击“补译中文”。")
            self.update_notice.show()
            self.status.setText(f"{context['name']}：补全 {resolved} 条，仍待补全 {after['pending']} 条")
            with self.library.state:
                self.library.state.execute('UPDATE tasks SET log=log||? WHERE id=?',
                                           ('\n[正文补全结果] ' + self.notice_text.text() + '\n', result['id']))
            return
        additions = '、'.join(f'{TYPE_LABELS[k]} {max(0, types[k]-before_types.get(k,0))}' for k in TYPE_LABELS)
        self.notice_text.setText(f"{context['name']}：{outcome}。本次新增：{additions}；正文待补全 {after['pending']} 条。原创与转推、引用分别标识，可按内容类型筛选。")
        self.update_notice.show()
        self.status.setText(f"{context['name']}：新增 {new_originals} 条，待补全 {after['pending']}")
        with self.library.state:
            self.library.state.execute('UPDATE tasks SET log=log||? WHERE id=?',
                                       ('\n[资料库显示结果] ' + self.notice_text.text() + '\n', result['id']))

    def show_updated_latest(self):
        self.set_mode('all')
        self.set_account(getattr(self, 'last_synced_account', self.account))
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.search_delay.stop()
        self.kind.blockSignals(True)
        self.kind.setCurrentIndex(0)
        self.kind.blockSignals(False)
        self.jump_edge(False)

    def show_tasks(self):
        if hasattr(self,'task_dialog') and self.task_dialog.isVisible():
            self.refresh_tasks();self.task_dialog.raise_();self.task_dialog.activateWindow();return
        self.task_dialog = QDialog(self)
        self.task_dialog.setWindowTitle('任务队列')
        self.task_dialog.resize(850, 620)
        layout = QVBoxLayout(self.task_dialog)
        self.task_hint=label('下载、抓取、翻译依次执行。暂停后可关闭软件；重新打开后点击“继续”恢复。')
        self.task_hint.setWordWrap(True);layout.addWidget(self.task_hint)
        self.task_list = QListWidget()
        self.task_list.setStyleSheet('QListWidget::item { padding:7px 9px; border-radius:5px; } QListWidget::item:selected { background:#2b4544; color:#f5f9ff; }')
        self.task_list.setMaximumHeight(190)
        self.task_log = QPlainTextEdit()
        self.task_log.setReadOnly(True)
        self.task_list.currentItemChanged.connect(self.select_task)
        layout.addWidget(self.task_list)
        layout.addWidget(self.task_log, 1)
        actions = QHBoxLayout()
        self.task_pause_button=button('暂停任务',self.pause_tasks)
        self.task_resume_button=button('继续任务',self.resume_tasks)
        actions.addWidget(self.task_pause_button);actions.addWidget(self.task_resume_button)
        actions.addWidget(button('重新补充', self.sync))
        actions.addWidget(button('重试补译', self.translate))
        actions.addStretch()
        actions.addWidget(button('关闭', self.task_dialog.close))
        layout.addLayout(actions)
        self.refresh_tasks()
        self.task_dialog.show()

    def refresh_tasks(self):
        self.task_pause_button.setEnabled(bool(self.queue.current or self.queue.waiting) and not self.queue.paused)
        self.task_resume_button.setEnabled(self.queue.paused and bool(self.queue.waiting) and not self.queue.stopping)
        if self.queue.stopping:self.task_hint.setText('正在暂停下载及其子进程，请稍候。')
        elif self.queue.paused:self.task_hint.setText('已暂停：已保存内容保留。继续时重新检查并跳过已完成下载；关闭此窗口不会恢复任务。')
        else:self.task_hint.setText('下载、抓取、翻译依次执行。关闭此任务窗口会继续；主窗口退出时可选择暂停并退出。')
        selected = self.task_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.task_list.currentItem() else None
        if selected is None:
            if self.queue.current:selected=self.queue.current[0]
            elif self.queue.waiting:selected=self.queue.waiting[0][0]
        self.task_list.clear()
        for tid, title, status, created in self.library.state.execute('SELECT id,title,status,created FROM tasks ORDER BY id DESC LIMIT 100'):
            item = QListWidgetItem(f'{status}   {title}   ·   {created} UTC')
            item.setForeground(QColor({'已暂停':'#f1c17c','正在暂停':'#f1c17c','部分完成':'#f1c17c','进行中':'#8ce7ce','失败':'#f2a29a'}.get(status,'#dfe7f2')))
            item.setData(Qt.ItemDataRole.UserRole, tid)
            self.task_list.addItem(item)
            if tid == selected:
                self.task_list.setCurrentItem(item)
        if not self.task_list.currentItem() and self.task_list.count():
            self.task_list.setCurrentRow(0)

    def select_task(self, item, previous=None):
        if item:
            row = self.library.state.execute('SELECT log FROM tasks WHERE id=?', (item.data(Qt.ItemDataRole.UserRole),)).fetchone()
            self.task_log.setPlainText(row[0] or '等待执行…')
            self.task_log.verticalScrollBar().setValue(self.task_log.verticalScrollBar().maximum())

    def stop_history(self):
        if self.queue.current and self.queue.current[4].get('history'):
            self.queue.pause()
        else:QMessageBox.information(self,'没有历史任务','当前运行的任务不是历史补录。')

    def settings(self,page=0):
        try:
            dialog = SettingsDialog(self.library.root,self.program_root,self,ReadableComboBox,page,
                                    busy=bool(self.storage_busy or self.queue.current or self.queue.waiting))
        except (TranslationError,OSError,ValueError) as exc:
            QMessageBox.warning(self, '读取设置失败', str(exc))
            return
        self.settings_dialog = dialog
        def test_provider():
            dialog.accept()
            self.python_task('翻译引擎固定样例试译', 'translation_engine.py', [])
            self.show_tasks()
        dialog.test_requested.connect(test_provider)
        dialog.refresh_requested.connect(lambda: (self.reload(), self.refresh_posters()))
        def import_settings_login():
            self.import_login();dialog.refresh_login_status()
        dialog.login_requested.connect(import_settings_login)
        dialog.exec()
        if dialog.selection:self.change_storage(*dialog.selection)
        else:self.reload()

    def history(self):
        if not self.library.accounts:
            QMessageBox.information(self,'请先添加账号','先添加一个归档账号。');return
        name=next((a['name'] for a in self.library.accounts if a['key']==self.account),'全部账号')
        dialog=HistorySettings(name,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        index=next((i+1 for i,a in enumerate(self.library.accounts) if a['key']==self.account),0)
        args=['-u',str(self.program_root/'tools/tweet_archive.py'),'--root',str(self.library.root),
              '--runtime-root',str(self.program_root),'--index',str(index),'--history',
              '--scan-limit',str(dialog.limit.value())]
        if dialog.since.text().strip():args+=['--since',dialog.since.text().strip()]
        if not dialog.resume.isChecked():args+=['--restart-history']
        if not dialog.translate.isChecked():args+=['--no-translate']
        self.queue.enqueue('补历史正文 · '+name,str(self.program_root/'python/python.exe'),args,context=dict(kind='sync',account=self.account,name=name,history=True))
        self.show_tasks()

    def storage_settings(self):
        self.settings(page=0)

    def change_storage(self,mode,target):
        if self.storage_busy or self.queue.current or self.queue.waiting:return
        target=Path(target).resolve()
        if target==self.library.root:
            QMessageBox.information(self,'位置未变','这就是当前资料库。');return
        lock=None;new_library=None;progress=None
        self.storage_busy=True
        try:
            if mode=='open':validate_library(target)
            else:empty_destination(self.library.root,target)
            self.save_tags();self.save_session();self.save_timer.stop();self.search_delay.stop()
            self.pool.waitForDone()
            if mode=='copy':
                progress=QProgressDialog('正在复制资料并校验，原目录将保留…','',0,100,self)
                progress.setCancelButton(None);progress.setWindowModality(Qt.WindowModality.ApplicationModal)
                progress.setMinimumDuration(0)
                def advance(done,total,path):
                    progress.setLabelText('正在复制并校验：'+path)
                    progress.setValue(int(done*100/max(total,1)));QApplication.processEvents()
                copy_library(self.library.root,target,advance)
            elif mode=='new':
                target.mkdir(parents=True,exist_ok=True);initialize_library(target)
            validate_library(target)
            lock=QLockFile(str(target/'_推文归档/manager.lock'));lock.setStaleLockTime(0)
            if not lock.tryLock(0):raise ValueError('目标资料库正在被另一个窗口使用。')
            new_library=Library(target)
            select_library(self.program_root,target)
            self.clear_detail()
            self.library.state.close()
            if self.data_lock:self.data_lock.unlock()
            self.data_lock=lock;lock=None
            self.library=new_library;new_library=None;self.queue.library=self.library;self.queue.restore()
            self.loaded=False;self.mode='all';self.account=''
            session=self.library.preference('browse_v2',{})
            self.session=session if isinstance(session,dict) else {}
            self.scope_states=self.session.get('scopes',{})
            if not isinstance(self.scope_states,dict):self.scope_states={}
            active=self.session.get('active',{})
            if isinstance(active,dict):
                if active.get('mode') in self.nav:self.mode=active['mode']
                if active.get('account') in {a['key'] for a in self.library.accounts}:self.account=active['account']
            self.account_search.setText(str(self.session.get('account_search','')))
            if hasattr(self,'task_dialog'):self.task_dialog.close()
            self.thumb_items={};self.thumb_cache=target/'_推文归档/预览缓存';self.thumb_cache.mkdir(exist_ok=True)
            self.location.setText(str(target)+'  ·  本地存储')
            self.reload()
            self.task_status()
            QMessageBox.information(self,'资料库已切换','当前资料库：'+str(target)+'\n原位置的资料保留。登录文件与翻译密钥仍位于程序目录。')
        except (OSError,ValueError,KeyError, sqlite3.Error) as exc:
            QMessageBox.warning(self,'切换未完成',str(exc)+'\n未完成的复制目录请勿作为完整资料库使用。')
        finally:
            if progress:progress.close()
            if new_library:new_library.state.close()
            if lock:lock.unlock()
            self.storage_busy=False

    def import_login(self):
        source,_=QFileDialog.getOpenFileName(self,'导入本人的 X 登录文件','','Cookies 文件 (*.txt);;所有文件 (*)')
        if not source:
            return
        try:
            import_login_file(self.program_root,source)
            QMessageBox.information(self,'登录文件已导入','已保存 X 登录信息，可添加账号并点击补充。')
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,'导入失败',str(exc))

    def closeEvent(self, event):
        if self.closed:event.accept();return
        if self.storage_busy:
            QMessageBox.information(self,'正在迁移资料库','请等待资料库复制或切换完成后再关闭软件。');event.ignore();return
        if self.queue.current or (self.queue.waiting and not self.queue.paused):
            if not self.queue.paused:
                answer=QMessageBox.question(self,'暂停任务并退出？',
                    '还有下载或排队任务。是否暂停任务并退出？\n已保存内容保留，下次启动后可点击“继续”；不会自动下载。',
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                if answer!=QMessageBox.StandardButton.Yes:event.ignore();return
            self._close_when_paused=True
            self.queue.pause()
            if not self.queue.current:QTimer.singleShot(0,self.close)
            event.ignore();return
        self.queue.persist()
        self.save_tags()
        self.save_session()
        self.save_timer.stop()
        self.account_search_popup.hide()
        if hasattr(self,'task_dialog'):self.task_dialog.close()
        if getattr(self,'media_viewer',None) is not None:self.media_viewer.close()
        self.search_delay.stop()
        self.closed = True
        self.player.stop()
        self.pool.waitForDone()
        self.library.state.close()
        if self.data_lock:self.data_lock.unlock()
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=HERE.parent)
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--video-smoke', type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('TweetArchive')
    app.setApplicationDisplayName('TweetArchive')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    try:root=resolve_library(args.root)
    except ValueError as exc:
        QMessageBox.warning(None,'资料库位置不可用',str(exc))
        folder=QFileDialog.getExistingDirectory(None,'选择已有的完整资料库')
        if not folder:return 1
        try:select_library(args.root,Path(folder));root=Path(folder).resolve()
        except (OSError,ValueError,sqlite3.Error) as problem:
            QMessageBox.warning(None,'无法打开资料库',str(problem));return 1
    initialize_library(root)
    if (HERE / 'archive.ico').is_file():
        app.setWindowIcon(QIcon(str(HERE / 'archive.ico')))
    lock = QLockFile(str(root / '_推文归档/manager.lock'))
    lock.setStaleLockTime(0)
    if not args.screenshot and not args.video_smoke and not lock.tryLock(0):
        QMessageBox.information(None, 'TweetArchive', '资料库已在运行，请切换到已经打开的窗口。')
        return 0
    window = Window(root, program_root=args.root, data_lock=lock, remember=not (args.screenshot or args.video_smoke))
    window.show()
    if args.screenshot:
        def capture():
            window.grab().save(str(args.screenshot))
            window.close()
            app.quit()
        QTimer.singleShot(3200, capture)
    if args.video_smoke:
        window.set_mode('videos')
        def finish_video():
            report = dict(duration=window.player.duration(), position=window.player.position(),
                          status=str(window.player.mediaStatus()), error=window.player.errorString(),
                          has_video=window.player.hasVideo(), count=len(window.results))
            args.video_smoke.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            window.grab().save(str(args.video_smoke.with_suffix('.png')))
            window.close()
            app.quit()
        QTimer.singleShot(1800, window.player.play)
        QTimer.singleShot(6500, finish_video)
    return app.exec()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log = HERE / '启动错误.log'
        log.write_text(traceback.format_exc(), encoding='utf-8')
        raise
