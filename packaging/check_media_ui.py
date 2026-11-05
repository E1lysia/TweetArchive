"""Visual and real MP4 playback checks using generated, non-personal data."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True);parser.add_argument('--source',action='store_true')
args=parser.parse_args();root=args.root.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
work=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent))
if args.source:sys.path.insert(0,str(work/'desktop_app'))
else:sys.path[:0]=[str(root/'资料库'),str(root/'资料库/vendor'),str(root/'tools')]
import app as manager
import media_viewer
from settings_dialog import SettingsDialog
from generate_preview_fixture import make_video
from PySide6.QtCore import QPoint,QPointF,QEvent,QEventLoop,QTimer
from PySide6.QtGui import QMouseEvent

def wait(milliseconds):
    loop=QEventLoop();QTimer.singleShot(milliseconds,loop.quit);loop.exec()

def click(widget):
    point=widget.rect().center();local=QPointF(point);global_point=QPointF(widget.mapToGlobal(point))
    for kind,buttons in [(QEvent.Type.MouseButtonPress,manager.Qt.MouseButton.LeftButton),
                         (QEvent.Type.MouseButtonRelease,manager.Qt.MouseButton.NoButton)]:
        event=QMouseEvent(kind,local,global_point,manager.Qt.MouseButton.LeftButton,buttons,manager.Qt.KeyboardModifier.NoModifier)
        manager.QApplication.sendEvent(widget,event)
if not args.source:
    assert all(Path(m.__file__).resolve().is_relative_to(root) for m in [manager,media_viewer])
qt=manager.QApplication([]);qt.setStyle('Fusion');qt.setStyleSheet(manager.STYLE)
manager.initialize_library(root)
assert json.loads((root/'tools/accounts.json').read_text(encoding='utf-8'))==[]
fixture=root/'_qa-generated';fixture.mkdir(exist_ok=True)
for name,size in [('portrait.png',(800,1200)),('landscape.png',(1200,700))]:
    image=manager.QImage(*size,manager.QImage.Format.Format_RGB32);image.fill(manager.QColor('#203c4c'))
    p=manager.QPainter(image);p.setPen(manager.Qt.PenStyle.NoPen)
    p.setBrush(manager.QColor('#73d8ba'));p.drawEllipse(size[0]//5,size[1]//5,size[0]*3//5,size[0]*3//5)
    p.fillRect(size[0]//4,size[1]*2//3,size[0]//2,30,manager.QColor('#f4d373'))
    p.setPen(manager.QColor('#e8f4f9'));p.setFont(manager.QFont('Arial',28));p.drawText(40,70,'LOCAL ARCHIVE');p.end()
    assert image.save(str(fixture/name))
video=fixture/'synthetic.mp4';make_video(video)
cache=root/'_推文归档/预览缓存';cache.mkdir(exist_ok=True)
poster=manager.poster_file(video,cache)
manager.QImage(str(fixture/'landscape.png')).save(str(poster),'JPG')
poster.with_suffix('.json').write_text('{"duration_ms":4000}',encoding='utf-8')
w=manager.Window(root,program_root=root,remember=False)
w.setAttribute(manager.Qt.WidgetAttribute.WA_DontShowOnScreen)
account=w.library.add_account('example_user','示例作者');key=account['key']
group=w.library.create_group('音乐与生活');w.library.move_account(key,group['id'])
db=sqlite3.connect(root/'_推文归档/tweets.sqlite')
for tid,content in [('100','本地归档中的图片与视频，可以直接点击右侧预览，在软件内放大查看。'),('99','纯文字同样可以归档，按账号、日期和类型快速浏览。')]:
    doc=dict(tweet_id=tid,status='archived',author='示例作者',handle='@example_user',post_type='original',
             content=content,translation_zh=None,source_media_count=3 if tid=='100' else 0,
             date_beijing='2026-11-04T18:30:00+08:00',images=['_qa-generated/portrait.png','_qa-generated/landscape.png'] if tid=='100' else [],
             videos=['_qa-generated/synthetic.mp4'] if tid=='100' else [],url='https://x.com/example_user/status/'+tid)
    db.execute('INSERT INTO tweets VALUES(?,?,?,?)',(key,tid,'archived',json.dumps(doc,ensure_ascii=False)))
db.commit();db.close();w.reload();w.set_account(key);w.show();wait(200)
w.favorite.click();assert w.current['favorite'] and w.favorite.isChecked()
assert w.cards.item(0).data(manager.Qt.ItemDataRole.UserRole)['favorite']
centers={}
for width,height in [(1600,960),(1180,740)]:
    w.resize(width,height);wait(120)
    center=w.search.mapTo(w.topbar,QPoint(0,0)).x()+w.search.width()/2
    centers[str(width)]=dict(search=center,window=w.topbar.width()/2,width=w.search.width())
    assert abs(center-w.topbar.width()/2)<=2,centers
    w.grab().save(str(out/f'主界面-{width}.png'))
w.resize(1600,960);wait(100)
d=SettingsDialog(root,root,w,manager.ReadableComboBox);d.setAttribute(manager.Qt.WidgetAttribute.WA_DontShowOnScreen)
d.show();wait(100);d.grab().save(str(out/'清晰复选框.png'));d.reject()
click(w.photo);wait(150)
viewer=w.media_viewer;assert isinstance(viewer,media_viewer.MediaViewer) and viewer.isVisible()
assert viewer.current[0]=='image' and viewer.image.item.pixmap().size()==manager.QSize(800,1200)
assert abs(viewer.image.transform().m11()-viewer.image.transform().m22())<.001
viewer.grab().save(str(out/'软件内大图.png'));viewer.move(1);assert viewer.index==1
frames=[]
def decoded(frame):
    if frame.isValid():
        frames.append((frame.width(),frame.height()))
        if len(frames)==1:frame.toImage().save(str(out/'视频解码帧.png'))
viewer.video.videoSink().videoFrameChanged.connect(decoded);viewer.move(1)
start=time.monotonic()
while time.monotonic()-start<8 and not (frames and viewer.player.position()>350):wait(50)
playback=dict(frames=len(frames),size=frames[-1] if frames else None,duration=viewer.player.duration(),position=viewer.player.position(),error=viewer.player.errorString())
assert playback['frames']>0 and playback['duration']>=3900 and playback['position']>350,playback
viewer.player.pause();viewer.player.setPosition(1500);wait(150)
assert abs(viewer.player.position()-1500)<250
viewer.reject();assert viewer.player.source().isEmpty() and w.media_viewer is None
w.media.setCurrentIndex(2);wait(100)
click(w.video);wait(200)
assert w.media_viewer and w.media_viewer.current[0]=='video'
w.media_viewer.reject();w.close();wait(80)
report=dict(version=manager.VERSION,independent_runtime=not args.source,centered_search=centers,
            favorite_synced=True,image_viewer=True,video_click=True,playback=playback,closed_player_released=True,screenshots=str(out))
(out/'界面验证.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
