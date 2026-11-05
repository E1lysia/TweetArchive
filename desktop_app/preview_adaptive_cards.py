"""Capture the native layout with generated fixtures; never open a personal library."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from test_adaptive_cards import AdaptiveCardTests,qt,manager

qt.setStyle('Fusion');qt.setStyleSheet(manager.STYLE)
case=AdaptiveCardTests('test_short_text_shrinks_and_geometry_stays_stable_after_async_thumbnails')
case.setUp()
output=Path(__file__).resolve().parents[1]/'packaging/qa/adaptive-cards'
output.mkdir(parents=True,exist_ok=True)
try:
    case.w.resize(1920,1080);case.w.splitter.setSizes([210,1150,550]);case.settle()
    case.w.pool.waitForDone();case.settle();case.w.cards.setCurrentRow(1)
    qt.sendPostedEvents(None,manager.QEvent.Type.DeferredDelete);qt.processEvents()
    assert case.w.grab().save(str(output/'全部推文-双列.png'))
    case.w.feed_scroll.verticalScrollBar().setValue(350);case.settle()
    assert case.w.back_to_top.isVisible()
    assert case.w.grab().save(str(output/'全部推文-返回顶部.png'))
    assert case.w.back_to_top.grab().save(str(output/'返回顶部按钮.png'))
    case.w.back_to_top.click();case.settle()
    case.w.resize(1280,850);case.w.splitter.setSizes([190,540,540]);case.settle()
    qt.sendPostedEvents(None,manager.QEvent.Type.DeferredDelete);qt.processEvents()
    assert case.w.grab().save(str(output/'全部推文-窄窗口.png'))
    print(str(output))
finally:
    case.tearDown()
