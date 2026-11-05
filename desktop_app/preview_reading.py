"""Capture both interface variants with the real library, without changing preferences."""
import json
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app as manager

qt = manager.QApplication([])
qt.setStyle('Fusion')
qt.setStyleSheet(manager.STYLE)
window = manager.Window(Path(r'D:\gallery-dl'), remember=False)
window.show()
out = HERE.parent / 'design'
metrics = {}

def capture_reading():
    window.grab().save(str(out / 'desktop-reading.png'))
    metrics['reading'] = dict(panes=window.splitter.sizes(), body=[window.body.width(), window.body.height()],
                              window=[window.width(), window.height()])
    window.layout_choice.setCurrentIndex(1)
    manager.QTimer.singleShot(500, capture_classic)

def capture_classic():
    window.grab().save(str(out / 'desktop-classic.png'))
    metrics['classic'] = dict(panes=window.splitter.sizes(), body=[window.body.width(), window.body.height()])
    window.layout_choice.setCurrentIndex(0)
    window.resize(1180, 740)
    manager.QTimer.singleShot(500, finish)

def finish():
    window.grab().save(str(out / 'desktop-reading-small.png'))
    metrics['small'] = dict(window=[window.width(), window.height()], panes=window.splitter.sizes())
    print(json.dumps(metrics))
    window.close()
    qt.quit()

manager.QTimer.singleShot(2000, capture_reading)
qt.exec()
