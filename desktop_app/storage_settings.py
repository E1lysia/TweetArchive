"""Storage selection and capture preferences, separate from translation credentials."""
from pathlib import Path
from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QCheckBox,QDialogButtonBox,QFileDialog,QLineEdit,QSpinBox,QFormLayout,QMessageBox)
from storage import archive_options,save_archive_options,TYPES


class StorageSettings(QDialog):
    selection_requested=Signal()

    def __init__(self, root, parent=None, embedded=False):
        super().__init__(parent); self.root=root; self.selection=None
        self.embedded=embedded
        if embedded:self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle('存储位置与归档'); self.resize(650,550)
        layout=QVBoxLayout(self)
        if embedded:layout.setContentsMargins(0,0,0,0)
        layout.addWidget(QLabel('当前资料库位置'))
        location=QLineEdit(str(root)); location.setReadOnly(True); layout.addWidget(location)
        reveal=QPushButton('打开所在文件夹'); reveal.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(root))))
        layout.addWidget(reveal)
        note=QLabel('更改位置时可复制现有资料，或新建空资料库用于教学演示。原目录保留。登录文件和翻译密钥保留在程序目录，不随归档复制。')
        note.setWordWrap(True); layout.addWidget(note)
        for title,mode in [('复制现有资料并切换位置…','copy'),('在新位置创建空资料库…','new'),('打开已有资料库…','open')]:
            button=QPushButton(title); button.clicked.connect(lambda checked=False,m=mode:self.choose(m)); layout.addWidget(button)
        layout.addSpacing(16); layout.addWidget(QLabel('账号补新范围（与页面筛选独立）'))
        options=archive_options(root)
        self.text=QCheckBox('同步纯文字推文'); self.text.setChecked(bool(options['sync_text'])); layout.addWidget(self.text)
        self.replies=QCheckBox('包含回复'); self.replies.setChecked(bool(options['include_replies'])); layout.addWidget(self.replies)
        self.types={}; row=QHBoxLayout()
        for key,title in zip(TYPES,['原创','引用','转推','关联来源']):
            box=QCheckBox(title); box.setChecked(key in options['post_types']); self.types[key]=box; row.addWidget(box)
        layout.addLayout(row)
        info=QLabel('日常补新扫描最新正文；旧的纯文字使用中栏补新菜单中的“补历史正文”。迁移或切换前，请先等待所有任务结束。')
        info.setWordWrap(True); layout.addWidget(info)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存归档设置')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('关闭')
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        if embedded:buttons.hide()

    def options(self):
        types=[key for key,box in self.types.items() if box.isChecked()]
        if not types: raise ValueError('至少选择一种内容类型。')
        return dict(sync_text=self.text.isChecked(),include_replies=self.replies.isChecked(),post_types=types)

    def save_settings(self):
        try: save_archive_options(self.root,self.options())
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,'无法保存',str(exc)); return False
        return True

    def save(self):
        if self.save_settings():self.accept()

    def choose(self, mode):
        folder=QFileDialog.getExistingDirectory(self,'选择完整资料库' if mode=='open' else '选择新的空目录',str(self.root.parent))
        if not folder:return
        self.selection=(mode,Path(folder))
        if self.embedded:self.selection_requested.emit()
        else:self.accept()


class HistorySettings(QDialog):
    def __init__(self, account_name, parent=None):
        super().__init__(parent); self.setWindowTitle('补历史正文'); self.resize(520,330)
        form=QFormLayout(self)
        intro=QLabel(f'范围：{account_name}\n保存原文，不下载媒体；不会清空已有内容。可获取范围以 X 返回为准。')
        intro.setWordWrap(True); form.addRow(intro)
        self.since=QLineEdit(); self.since.setPlaceholderText('YYYY-MM-DD，留空不限制起始日期'); form.addRow('最早日期',self.since)
        self.limit=QSpinBox(); self.limit.setRange(100,10000); self.limit.setValue(500); form.addRow('单次扫描上限',self.limit)
        self.resume=QCheckBox('从上次未完成的位置继续（相同日期和归档设置）'); self.resume.setChecked(True); form.addRow(self.resume)
        self.translate=QCheckBox('本次完成后补译中文（使用当前引擎与字符上限）'); form.addRow(self.translate)
        note=QLabel('历史正文与页面上的搜索、月份、类型筛选无关，采用“存储与归档”中的账号归档范围。达到上限后可再次运行。')
        note.setWordWrap(True); form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('开始归档')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.check); buttons.rejected.connect(self.reject); form.addRow(buttons)

    def check(self):
        import datetime
        try:
            if self.since.text().strip(): datetime.date.fromisoformat(self.since.text().strip())
        except ValueError:
            QMessageBox.warning(self,'日期不正确','请输入 YYYY-MM-DD 格式的日期。'); return
        self.accept()
