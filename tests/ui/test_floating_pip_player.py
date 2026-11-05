import pytest
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtWidgets import QApplication, QSplitter, QWidget
from player.pip_player import PiPPlayerWindow, PiPWorkspacePlaceholderWidget
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

def test_pip_workspace_placeholder_widget(qapp):
    # FINDING-PHASE3-001: Kiểm tra cấu trúc và tương tác của Placeholder Widget
    placeholder = PiPWorkspacePlaceholderWidget()
    assert placeholder.objectName() == "pip_workspace_placeholder"
    assert placeholder.lbl_icon.text() == "📺"
    assert "PiP ACTIVE" in placeholder.lbl_title.text()
    assert placeholder.btn_dock.objectName() == "btn_dock_from_placeholder"

    dock_signal_fired = []
    placeholder.dock_requested.connect(lambda: dock_signal_fired.append(True))
    placeholder.btn_dock.click()
    assert len(dock_signal_fired) == 1

def test_splitter_detach_undock_placeholder_preserves_workspace(qapp):
    # Ràng buộc 1 & FINDING-PHASE3-001: Video container dùng QStackedWidget để bảo toàn kích thước Splitter
    from PySide6.QtWidgets import QStackedWidget
    splitter = QSplitter(Qt.Horizontal)
    sub_editor = QWidget()
    video_stack = QStackedWidget()
    video_player = VideoPlayerWidget()
    placeholder = PiPWorkspacePlaceholderWidget()
    video_stack.addWidget(video_player)
    video_stack.addWidget(placeholder)
    
    splitter.addWidget(sub_editor)
    splitter.addWidget(video_stack)
    splitter.setSizes([600, 400])
    splitter.show()

    initial_sizes = splitter.sizes()
    assert initial_sizes[0] > 0 and initial_sizes[1] > 0

    # 1. Khi tách PiP (chuyển sang placeholder): kích thước splitter không đổi
    video_stack.setCurrentIndex(1)
    assert video_player.isHidden() is True
    assert placeholder.isVisible() is True
    assert splitter.sizes() == initial_sizes

    # 2. Khi gắn lại: video_player phục hồi, kích thước splitter tiếp tục bảo toàn
    video_stack.setCurrentIndex(0)
    assert video_player.isVisible() is True
    assert placeholder.isHidden() is True
    assert splitter.sizes() == initial_sizes


def test_mainwindow_pip_toggle_and_tab_geometry_lock(qapp):
    from ui.Gui import MainWindow
    win = MainWindow()
    win.show()
    try:
        # Chuyển sang Tab 1 (Video Workspace) để các widget trong workspace hiển thị
        win.switch_page(1)
        initial_geo = win.geometry()
        assert win.video_stack.currentIndex() == 0
        assert win.video_player.isVisible() is True
        assert win.pip_placeholder.isHidden() is True

        # 1. Tách PiP (FINDING-PHASE3-001: Video workspace được thế chỗ bằng Placeholder)
        win.detach_pip_video()
        assert win.video_stack.currentIndex() == 1
        assert win.video_player.isHidden() is True
        assert win.pip_placeholder.isVisible() is True
        assert win.pip_window.isVisible() is True
        sizes = win.top_horizontal_splitter.sizes()
        assert sizes[0] > 0 and sizes[1] > 0

        # 2. Nút 1-click dock trên Placeholder
        win.pip_placeholder.btn_dock.click()
        assert win.video_stack.currentIndex() == 0
        assert win.video_player.isVisible() is True
        assert win.pip_placeholder.isHidden() is True
        assert win.pip_window.isHidden() is True

        # 3. Tách lại và kiểm tra chuyển tab không làm biến động kích thước (Ràng buộc 3)
        win.detach_pip_video()
        assert win.pip_placeholder.isVisible() is True
        
        win.switch_page(8) # Tab Dịch thuật AI
        assert win.geometry().width() == initial_geo.width()
        assert win.geometry().height() == initial_geo.height()
        assert win.pip_window.isVisible() is True

        win.switch_page(1) # Quay lại Tab Studio
        assert win.geometry().width() == initial_geo.width()
        assert win.geometry().height() == initial_geo.height()
        assert win.pip_placeholder.isVisible() is True

        # 4. Gắn lại (Dock)
        win.dock_pip_video()
        assert win.video_stack.currentIndex() == 0
        assert win.video_player.isVisible() is True
        assert win.pip_placeholder.isHidden() is True
        assert win.pip_window.isHidden() is True
    finally:
        win.close()
