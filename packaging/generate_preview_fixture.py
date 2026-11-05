"""Create a synthetic MP4 for local playback checks, without personal media."""
from pathlib import Path


def make_video(target):
    from PySide6.QtCore import QEventLoop,QTimer,QUrl
    from PySide6.QtGui import QImage,QColor,QPainter,QFont
    from PySide6.QtMultimedia import (QMediaCaptureSession,QMediaRecorder,QMediaFormat,
        QVideoFrameInput,QVideoFrame)
    session=QMediaCaptureSession();recorder=QMediaRecorder();source=QVideoFrameInput()
    session.setRecorder(recorder);session.setVideoFrameInput(source)
    fmt=QMediaFormat(QMediaFormat.FileFormat.MPEG4);fmt.setVideoCodec(QMediaFormat.VideoCodec.MPEG4)
    recorder.setMediaFormat(fmt);recorder.setVideoResolution(480,270);recorder.setVideoFrameRate(30)
    recorder.setAutoStop(True);recorder.setOutputLocation(QUrl.fromLocalFile(str(Path(target).resolve())))
    loop=QEventLoop();state=dict(index=0,ended=False,started=False,error='')
    def feed():
        if state['ended']:return
        if state['index']<120:
            n=state['index'];image=QImage(480,270,QImage.Format.Format_RGB32);image.fill(QColor('#142d3c'))
            p=QPainter(image);p.setPen(QColor('#f4d373'));p.setFont(QFont('Arial',24))
            p.drawText(30,65,'LOCAL VIDEO PREVIEW');p.fillRect(30+n*3%360,120,60,75,QColor('#75dfc0'));p.end()
            frame=QVideoFrame(image);frame.setStartTime(n*1000000//30);frame.setEndTime((n+1)*1000000//30)
            if not source.sendVideoFrame(frame):return
            state['index']+=1
        elif source.sendVideoFrame(QVideoFrame()):state['ended']=True
    def changed(value):
        if value==QMediaRecorder.RecorderState.RecordingState:state['started']=True;feed_timer.start()
        if value==QMediaRecorder.RecorderState.StoppedState and state['started']:loop.quit()
    def error(*args):state['error']=recorder.errorString();loop.quit()
    feed_timer=QTimer();feed_timer.setInterval(33);feed_timer.timeout.connect(feed)
    recorder.recorderStateChanged.connect(changed);recorder.errorOccurred.connect(error)
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit);timer.start(20000)
    recorder.record();loop.exec();feed_timer.stop();recorder.stop()
    assert not state['error'],state['error']
    assert state['ended'] and state['index']==120 and Path(target).stat().st_size>1000,state
    return dict(frames=120,seconds=4)


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop_app'))
    import app
    qt=app.QApplication([])
    print(make_video(Path(sys.argv[1])))
