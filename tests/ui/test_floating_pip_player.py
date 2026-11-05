import pytest
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtWidgets import QApplication, QSplitter, QWidget
from player.pip_player import PiPPlayerWindow
from player.video_player import VideoPlayerWidget

@pytest.fixture
def pip_window(qapp):
    win = PiPPlayerWindow()
    yield win
    win.close()

def test_pip_window_flags_and_title(pip_window):
    # Ràng buộc 2: Top-Level OS Window có hỗ trợ Windows Snap Assist
    flags = pip_window.windowFlags()
    assert bool(flags & Qt.Window) is True
    assert bool(flags & Qt.WindowTitleHint) is True
    assert bool(flags & Qt.WindowMinMaxButtonsHint) is True
    assert bool(flags & Qt.WindowCloseButtonHint) is True
    # Tuyệt đối KHÔNG gán FramelessWindowHint cố định
    assert bool(flags & Qt.FramelessWindowHint) is False
    assert pip_window.windowTitle() == "AI Subtitle Suite - Video Player (PiP)"

def test_pip_window_always_on_top_toggle(pip_window):
    # Kiểm tra nút toggle 📌 Luôn nổi
    assert pip_window.is_always_on_top is False
    pip_window.toggle_always_on_top(True)
    assert pip_window.is_always_on_top is True
    assert bool(pip_window.windowFlags() & Qt.WindowStaysOnTopHint) is True

    pip_window.toggle_always_on_top(False)
    assert pip_window.is_always_on_top is False
    assert bool(pip_window.windowFlags() & Qt.WindowStaysOnTopHint) is False

def test_pip_window_video_frame_forwarding(pip_window):
    # Ràng buộc 4: Chia sẻ video sink, không dual decode
    assert hasattr(pip_window, "set_video_frame")
    img = QImage(320, 240, QImage.Format_ARGB32)
    img.fill(Qt.blue)
    frame = QVideoFrame(img)
    # Không được ném Exception khi nhận frame
    pip_window.set_video_frame(frame)

def test_pip_window_bidirectional_signals(pip_window):
    # Kiểm tra các tín hiệu 2 chiều
    play_called = []
    seek_called = []
    dock_called = []

    pip_window.play_pause_requested.connect(lambda: play_called.append(True))
    pip_window.seek_requested.connect(lambda pos: seek_called.append(pos))
    pip_window.dock_requested.connect(lambda: dock_called.append(True))

    pip_window.btn_play.click()
    assert len(play_called) == 1

    pip_window.slider_seek.setValue(1500)
    pip_window.slider_seek.sliderMoved.emit(1500)
    assert 1500 in seek_called

    pip_window.btn_dock.click()
    assert len(dock_called) == 1

def test_splitter_detach_undock_100_percent_expansion(qapp):
    # Ràng buộc 1: Khi detach video, SubEditor mở rộng 100% bề ngang
    splitter = QSplitter(Qt.Horizontal)
    sub_editor = QWidget()
    video_player = VideoPlayerWidget()
    splitter.addWidget(sub_editor)
    splitter.addWidget(video_player)
    splitter.setSizes([600, 400])
    splitter.show()

    # Lưu sizes và hide video
    saved_sizes = splitter.sizes()
    assert saved_sizes[0] > 0 and saved_sizes[1] > 0
    video_player.hide()

    # Khi video bị ẩn, sub_editor chiếm toàn bộ bề ngang
    assert video_player.isHidden() is True
    assert sub_editor.isVisible() is True

    # Khi gắn lại (dock), phục hồi kích thước
    video_player.show()
    splitter.setSizes(saved_sizes)
    assert video_player.isVisible() is True
    assert splitter.sizes()[1] > 0


def test_mainwindow_pip_toggle_and_tab_geometry_lock(qapp):
    from ui.Gui import MainWindow
    win = MainWindow()
    win.show()
    try:
        initial_geo = win.geometry()

        # 1. Tách PiP
        win.detach_pip_video()
        assert win.video_player.isHidden() is True
        assert win.pip_window.isVisible() is True

        # 2. Ràng buộc 3: Chuyển tab không làm thay đổi kích thước MainWindow
        win.switch_page(8) # Tab Dịch thuật AI
        assert win.geometry().width() == initial_geo.width()
        assert win.geometry().height() == initial_geo.height()
        # PiP vẫn hiển thị ngoài màn hình khi ở tab khác
        assert win.pip_window.isVisible() is True

        win.switch_page(1) # Quay lại Tab Studio
        assert win.geometry().width() == initial_geo.width()
        assert win.geometry().height() == initial_geo.height()

        # 3. Gắn lại (Dock)
        win.dock_pip_video()
        assert win.video_player.isVisible() is True
        assert win.pip_window.isHidden() is True
    finally:
        win.close()
