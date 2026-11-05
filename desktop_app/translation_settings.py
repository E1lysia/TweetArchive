"""Translation provider editor; saved credentials are never put into visible fields."""
import copy
from PySide6.QtCore import Signal, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QFormLayout,QLabel,QLineEdit,QComboBox,QCheckBox,QPushButton,QDialogButtonBox,QHBoxLayout
from translation_engine import PROVIDERS,TranslationError,load_config,read_json,save_config


class TranslationSettings(QDialog):
    test_requested=Signal()
    refresh_requested=Signal()
    login_requested=Signal()

    def __init__(self,root,parent=None,combo_class=QComboBox,embedded=False):
        super().__init__(parent)
        self.embedded=embedded
        if embedded:self.setWindowFlags(Qt.WindowType.Widget)
        self.root=root
        self.config=copy.deepcopy(load_config(root))
        self.legacy=read_json(root/'tools/deepl.local.json')
        self.previous=None
        self.deepl_key=''
        self.setWindowTitle('设置与翻译')
        self.resize(700,650)
        if not embedded:self.setMinimumWidth(620)
        form=QFormLayout(self)
        form.setContentsMargins(0,0,0,0) if embedded else form.setContentsMargins(22,20,22,20)
        form.setVerticalSpacing(12)
        location=QLabel(str(root)); location.setObjectName('muted')
        if not embedded:form.addRow('程序 / 登录配置位置',location)
        login=QPushButton('导入本人的 X 登录文件（cookies.txt）')
        login.clicked.connect(self.import_login)
        if not embedded:form.addRow(login)
        self.engine=combo_class()
        for name,preset in PROVIDERS.items():
            self.engine.addItem(preset['name'],name)
        form.addRow('翻译引擎',self.engine)
        self.hint=QLabel(); self.hint.setWordWrap(True); self.hint.setObjectName('muted')
        form.addRow(self.hint)
        self.key=QLineEdit(); self.key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('API 密钥',self.key)
        self.base=QLineEdit(); self.base.setPlaceholderText('https://服务地址/v1')
        self.base_label=QLabel('接口地址')
        form.addRow(self.base_label,self.base)
        self.model=QLineEdit(); self.model.setPlaceholderText('填写服务商提供的模型名称')
        self.model_label=QLabel('模型名称')
        form.addRow(self.model_label,self.model)
        self.workers=combo_class(); self.workers.addItems(['1','2','3','4','5'])
        self.workers.setCurrentText(str(self.config['workers']))
        form.addRow('并发请求数',self.workers)
        self.budget=QLineEdit(str(self.config['max_characters_per_run']))
        form.addRow('单次原文字符上限',self.budget)
        self.timeout=combo_class(); self.timeout.addItems(['30','60','90','120','180'])
        if str(self.config['timeout_seconds']) not in [self.timeout.itemText(i) for i in range(self.timeout.count())]:
            self.timeout.addItem(str(self.config['timeout_seconds']))
        self.timeout.setCurrentText(str(self.config['timeout_seconds']))
        form.addRow('请求超时（秒）',self.timeout)
        self.auto=QCheckBox('补新完成后自动补译'); self.auto.setChecked(self.config['enabled'])
        form.addRow(self.auto)
        note=QLabel('已有译文保留；相同原文优先复用本地缓存。大模型服务通常按 token 计费，字符上限不等于费用上限。密钥仅保存到本机，留空保留所选服务的密钥。')
        note.setObjectName('muted'); note.setWordWrap(True); form.addRow(note)
        self.status=QLabel(''); self.status.setWordWrap(True); form.addRow(self.status)
        row=QHBoxLayout()
        self.portal=QPushButton('打开所选服务平台'); self.portal.clicked.connect(self.open_portal)
        row.addWidget(self.portal)
        self.test=QPushButton('保存并试译固定样例'); self.test.clicked.connect(self.test_saved)
        row.addWidget(self.test); form.addRow(row)
        refresh=QPushButton('刷新资料库与视频封面')
        refresh.clicked.connect(self.refresh_library)
        if not embedded:form.addRow(refresh)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.save_and_close); buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        if embedded:buttons.hide()
        self.engine.currentIndexChanged.connect(self.switch_engine)
        self.engine.setCurrentIndex(self.engine.findData(self.config['engine']))
        if self.previous is None:
            self.switch_engine()

    def capture_profile(self):
        if self.previous is None:
            return
        profile=self.config['profiles'][self.previous]
        if self.previous!='deepl':
            profile.update(base_url=self.base.text().strip(),model=self.model.text().strip())
        if self.key.text().strip():
            if self.previous=='deepl':
                self.deepl_key=self.key.text().strip()
            else:
                profile['api_key']=self.key.text().strip()

    def switch_engine(self,*args):
        self.capture_profile()
        engine=self.engine.currentData()
        self.previous=engine
        profile=self.config['profiles'][engine]
        self.base.setText(profile['base_url']); self.model.setText(profile['model'])
        self.key.clear()
        saved=bool(self.deepl_key or self.legacy.get('api_key')) if engine=='deepl' else bool(profile.get('api_key'))
        self.key.setPlaceholderText('已保存此服务密钥；留空保留' if saved else '填写所选服务的 API 密钥，不会使用其他服务密钥')
        for widget in (self.base,self.base_label,self.model,self.model_label):
            widget.setVisible(engine!='deepl')
        hints={
            'deepl':'使用已有 DeepL 配置。切换到大模型不会修改 DeepL 密钥。',
            'deepseek':'使用 DeepSeek API，默认关闭深度思考以减少翻译等待。可修改模型名称。',
            'qwen':'预设为百炼北京地域；其他地域请使用对应的地址和密钥。模型名称可修改。',
            'kimi':'使用 Kimi 开放平台 API。请填写开放平台密钥，模型按账户权限选择。',
            'custom':'支持 Chat Completions 兼容服务；可填基础地址或完整接口地址。HTTPS 云服务需要对应密钥。',
        }
        self.hint.setText(hints[engine]); self.portal.setEnabled(bool(PROVIDERS[engine]['url']))
        self.status.clear()

    def open_portal(self):
        url=PROVIDERS[self.engine.currentData()]['url']
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def save_settings(self):
        try:
            self.capture_profile()
            self.config.update(engine=self.engine.currentData(),enabled=self.auto.isChecked(),
                               workers=int(self.workers.currentText()),max_characters_per_run=int(self.budget.text()),
                               timeout_seconds=int(self.timeout.currentText()))
            save_config(self.root,self.config,self.deepl_key)
            return True
        except (TranslationError,ValueError,OSError):
            self.status.setText('保存失败：请检查接口地址、模型名称及字符上限（1～1000000），并确认配置目录可写。')
            return False

    def save_and_close(self):
        if self.save_settings():
            self.accept()

    def test_saved(self):
        if self.save_settings():
            if not self.embedded:self.accept()
            self.test_requested.emit()

    def refresh_library(self):
        self.reject()
        self.refresh_requested.emit()

    def import_login(self):
        self.reject()
        self.login_requested.emit()
