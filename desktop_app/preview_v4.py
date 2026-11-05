import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app as manager

qt = manager.QApplication([])
qt.setStyle('Fusion')
qt.setStyleSheet(manager.STYLE)
window = manager.Window(Path(r'D:\gallery-dl'), remember=False)
window.set_account('virtual_kaf')
window.account_search.setText('virtual_kaf')
window.show()
def capture():
    assert len(window.current['images']) >= 2
    window.switch_image(1)
    def finish():
        window.grab().save(str(HERE.parent / 'design/desktop-v4.png'))
        window.close()
        qt.quit()
    manager.QTimer.singleShot(400, finish)
manager.QTimer.singleShot(2000, capture)
qt.exec()
