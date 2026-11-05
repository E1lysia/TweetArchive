"""One settings window with independent storage, translation and login pages."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QListWidget, QStackedWidget, QScrollArea, QPushButton)
from storage_settings import StorageSettings
from translation_settings import TranslationSettings


class SettingsDialog(QDialog):
    test_requested=Signal()
    refresh_requested=Signal()
    login_requested=Signal()

    def __init__(self, data_root, program_root, parent=None, combo_class=None, page=0, busy=False):
        super().__init__(parent)
        self.setWindowTitle('设置'); self.resize(920,740); self.setMinimumSize(780,600)
        self.selection=None
        self.program_root=program_root
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        body=QHBoxLayout(); body.setSpacing(0); outer.addLayout(body,1)
        self.navigation=QListWidget(); self.navigation.setObjectName('settingsNav')
        self.navigation.setAccessibleName('设置分类'); self.navigation.setFixedWidth(160)
        self.navigation.addItems(['存储与归档','翻译模型','X 登录'])
        body.addWidget(self.navigation)
        content=QWidget(); right=QVBoxLayout(content); right.setContentsMargins(24,22,24,18)
        self.title=QLabel(); self.title.setObjectName('heading'); right.addWidget(self.title)
        self.pages=QStackedWidget(); right.addWidget(self.pages,1); body.addWidget(content,1)
        self.storage=StorageSettings(data_root,self,embedded=True)
        self.translation=TranslationSettings(program_root,self,**({'combo_class':combo_class} if combo_class else {}),embedded=True)
        self.storage.selection_requested.connect(self.select_storage)
        self.storage.setEnabled(not busy)
        for panel in [self.storage,self.translation]:
            scroller=QScrollArea(); scroller.setWidgetResizable(True)
            scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroller.setWidget(panel); self.pages.addWidget(scroller)
        self.login_page=QWidget(); login=QVBoxLayout(self.login_page); login.setContentsMargins(0,0,0,0)
        intro=QLabel('为抓取配置本人的 X 登录信息。登录文件与翻译密钥分开管理，保存在程序目录。')
        intro.setWordWrap(True); login.addWidget(intro)
        self.login_status=QLabel(); self.login_status.setWordWrap(True); login.addWidget(self.login_status)
        folder=QLabel('登录文件位置：\n'+str(program_root/'cookies.txt'))
        folder.setWordWrap(True); folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder.setObjectName('muted'); login.addWidget(folder)
        self.import_button=QPushButton('导入本人的 X 登录文件（cookies.txt）')
        self.import_button.clicked.connect(self.login_requested.emit); login.addWidget(self.import_button)
        note=QLabel('需要重新获取时，运行程序目录中的“刷新登录态.cmd”，按提示操作后重新检查。这里只检查文件是否存在，是否有效需以实际补新结果为准。')
        note.setWordWrap(True); note.setObjectName('muted'); login.addWidget(note)
        check=QPushButton('重新检查登录文件'); check.clicked.connect(self.refresh_login_status); login.addWidget(check)
        login.addStretch(); self.pages.addWidget(self.login_page)
        self.status=QLabel(); self.status.setWordWrap(True); self.status.setObjectName('muted'); right.addWidget(self.status)
        footer=QHBoxLayout(); self.refresh=QPushButton('刷新资料库与视频封面')
        self.refresh.clicked.connect(self.refresh_requested.emit); footer.addWidget(self.refresh); footer.addStretch()
        self.save_button=QPushButton('保存当前页'); self.save_button.setObjectName('primary')
        self.save_button.clicked.connect(self.save_current); footer.addWidget(self.save_button)
        close=QPushButton('关闭'); close.clicked.connect(self.reject); footer.addWidget(close); right.addLayout(footer)
        self.translation.test_requested.connect(self.test_requested.emit)
        self.navigation.currentRowChanged.connect(self.show_page)
        self.navigation.setCurrentRow(page if page in (0,1,2) else 0)
        self.refresh_login_status()
        if busy:self.status.setText('任务进行中，结束后可修改存储与归档。')

    def show_page(self,index):
        self.pages.setCurrentIndex(index); self.title.setText(self.navigation.item(index).text())
        self.save_button.setVisible(index!=2)
        self.save_button.setEnabled(index!=0 or self.storage.isEnabled())
        self.refresh.setVisible(index==0); self.refresh.setEnabled(self.storage.isEnabled())
        self.status.clear()

    def save_current(self):
        panel=self.storage if self.pages.currentIndex()==0 else self.translation
        if panel.save_settings():self.status.setText('当前页设置已保存。')

    def select_storage(self):
        self.selection=self.storage.selection
        self.accept()

    def refresh_login_status(self):
        exists=(self.program_root/'cookies.txt').is_file()
        self.login_status.setText('● 已导入登录文件' if exists else '○ 尚未导入登录文件')
