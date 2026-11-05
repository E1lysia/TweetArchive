# 推文资料库桌面程序

原生 PySide6/Qt Windows 程序；复用 gallery-dl 的 SQLite 原文库、DeepL 翻译适配器和现有媒体目录。收藏、标签、任务历史分别保存在 `manager.sqlite`，不写入原始推文内容。

安装位置：`D:\gallery-dl\资料库`。启动入口：`D:\gallery-dl\推文资料库.exe`，备用入口为同目录 `推文资料库.cmd`。

## 开发与安装

嵌入式 Python 缺省不搜索脚本目录，入口显式加入自身目录和 vendor。Qt 依赖已独立安装在 `D:\gallery-dl\资料库\vendor`，不替换 gallery-dl 的运行依赖。

1. 安装 PySide6 到 vendor：`python -m pip install --target D:\gallery-dl\资料库\vendor PySide6==6.12.0`。
2. 使用 portable Python 运行 `make_icon.py`。
3. 用 .NET 8 SDK 构建 `launcher/Launcher.csproj`，Release 输出至 `launcher/dist`。
4. 首次运行 `install.py` 备份数据库和旧脚本；后续运行 `finish_install.py` 更新界面及启动入口。

## 验证

- `python -m unittest discover -s local_archive -p test_*.py`：原文、翻译和视频导出回归。
- `python -m unittest discover -s desktop_app -p test_*.py`：搜索、过滤、路径、收藏、标签、账号唯一性。
- `python desktop_app/smoke_ui.py`：临时资料库上测试 Qt 界面状态和异步任务成功/失败日志。
- `python desktop_app/app.py --video-smoke output.json`：真实本地视频解码、播放进度和错误报告，自动退出。
- `python desktop_app/verify_migration.py`：核对迁移前所有记录的原文、译文、状态和图片路径未变。

Qt 硬件视频画面不包含在 QWidget.grab 的截图中；最终已用实际 Windows 窗口确认播放画面。测试截图只用于查看布局。
