import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import app as manager
qt=manager.QApplication([])
qt.setStyle('Fusion'); qt.setStyleSheet(manager.STYLE)
dialog=manager.TranslationSettings(Path(r'D:\gallery-dl'),combo_class=manager.ReadableComboBox)
dialog.engine.setCurrentIndex(dialog.engine.findData('deepseek'))
dialog.show()
def finish():
    assert not dialog.key.text()
    dialog.grab().save(str(HERE.parent/'design/translation-engines.png'))
    print('Settings preview size:',dialog.width(),dialog.height())
    dialog.reject(); qt.quit()
manager.QTimer.singleShot(600,finish)
qt.exec()
