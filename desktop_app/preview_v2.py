"""Capture the app's own preview views for visual QA."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app as manager

qt = manager.QApplication([])
qt.setStyle('Fusion')
qt.setStyleSheet(manager.STYLE)
window = manager.Window(Path(r'D:\gallery-dl'), remember=False)
window.set_mode('videos')
window.set_account('aoki')
window.show()
out = HERE.parent / 'design'

def capture():
    window.grab().save(str(out / 'desktop-v2-video.png'))
    picker = manager.TimePicker(window.time_counts(), '2025', window)
    picker.show()
    def capture_picker():
        picker.grab().save(str(out / 'desktop-v2-time.png'))
        picker.close()
        window.close()
        qt.quit()
    manager.QTimer.singleShot(700, capture_picker)

manager.QTimer.singleShot(2000, capture)
qt.exec()
