"""Render this app's paging controls and popup for visual verification."""
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
window.resize(1280, 800)
window.show()
out = HERE.parent / 'design'

def capture():
    window.go_to_page(5)
    def capture_page():
        window.grab().save(str(out / 'desktop-v3-compact.png'))
        assert window.page_jump.text() == '6'
        assert window.page_jump.width() >= 35
        assert window.page_jump.geometry().right() < window.page_label.geometry().left()
        window.language.showPopup()
        def capture_popup():
            window.language.view().window().grab().save(str(out / 'desktop-v3-popup.png'))
            window.language.hidePopup()
            window.close()
            qt.quit()
        manager.QTimer.singleShot(300, capture_popup)
    manager.QTimer.singleShot(500, capture_page)

manager.QTimer.singleShot(1800, capture)
qt.exec()
