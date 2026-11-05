"""Real-library visual checks without changing saved browsing preferences."""
import json
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import app as manager

qt=manager.QApplication([])
qt.setStyle('Fusion'); qt.setStyleSheet(manager.STYLE)
window=manager.Window(Path(r'D:\gallery-dl'),remember=False)
window.show()
out=HERE.parent/'design'
metrics={}

def top():
    window.layout_cards()
    window.grab().save(str(out/'desktop-polished.png'))
    metrics['normal']=dict(window=[window.width(),window.height()], panes=window.splitter.sizes(),
                           columns=window.cards.viewport().width()//window.cards.gridSize().width(),
                           inner_scroll=window.cards.verticalScrollBar().maximum())
    window.feed_scroll.verticalScrollBar().setValue(260)
    manager.QTimer.singleShot(300,scrolled)

def scrolled():
    window.grab().save(str(out/'desktop-polished-scrolled.png'))
    metrics['scroll']=window.feed_scroll.verticalScrollBar().value()
    window.feed_scroll.verticalScrollBar().setValue(0)
    window.resize(1180,740)
    manager.QTimer.singleShot(500,small)

def small():
    window.layout_cards()
    window.grab().save(str(out/'desktop-polished-small.png'))
    metrics['small']=dict(window=[window.width(),window.height()],panes=window.splitter.sizes())
    window.view.setCurrentIndex(1)
    manager.QTimer.singleShot(300,finish)

def finish():
    window.grab().save(str(out/'desktop-polished-list.png'))
    print(json.dumps(metrics))
    window.close(); qt.quit()

manager.QTimer.singleShot(1600,top)
qt.exec()
