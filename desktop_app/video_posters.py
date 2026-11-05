"""Extract local video cover frames using the same Qt video backend as the app."""
import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / 'vendor'), r'D:\gallery-dl\资料库\vendor']
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink


def poster_file(path, cache):
    stat = path.stat()
    key = hashlib.sha256(f'{path}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()
    return cache / ('video-' + key + '.jpg')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    cache = root / '_推文归档/预览缓存'
    cache.mkdir(exist_ok=True)
    files = []
    with closing(sqlite3.connect(f'{(root / "_推文归档/tweets.sqlite").as_uri()}?mode=ro', uri=True)) as db:
        for raw, in db.execute("SELECT document FROM tweets WHERE status='archived'"):
            for relative in json.loads(raw).get('videos', []):
                path = (root / relative).resolve()
                if (path.is_relative_to(root) and path.is_file() and
                        (not poster_file(path, cache).exists() or not poster_file(path, cache).with_suffix('.json').exists())):
                    files.append(path)
    app = QApplication(sys.argv[:1])
    player = QMediaPlayer()
    sink = QVideoSink()
    player.setVideoSink(sink)
    timeout = QTimer()
    timeout.setSingleShot(True)
    remaining = iter(files)
    current = [None]
    captured = [0]
    busy = [False]

    def advance():
        timeout.stop()
        busy[0] = False
        player.stop()
        player.setSource(QUrl())
        current[0] = next(remaining, None)
        if current[0] is None:
            print(f'视频封面完成：新生成 {captured[0]} 个。', flush=True)
            app.quit()
            return
        busy[0] = True
        player.setSource(QUrl.fromLocalFile(str(current[0])))
        timeout.start(12000)
        player.play()

    def frame_ready(frame):
        if not busy[0] or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        busy[0] = False
        from PySide6.QtCore import Qt
        image = image.scaled(600, 440, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        target = poster_file(current[0], cache)
        if image.save(str(target), 'JPG', 85):
            target.with_suffix('.json').write_text(json.dumps({'duration_ms': player.duration()}, ensure_ascii=False), encoding='utf-8')
            captured[0] += 1
        QTimer.singleShot(0, advance)

    sink.videoFrameChanged.connect(frame_ready)
    timeout.timeout.connect(advance)
    QTimer.singleShot(0, advance)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
