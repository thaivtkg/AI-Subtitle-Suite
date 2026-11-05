import os
from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QSlider, QStyle, QApplication, QFrame
)

def format_time_ms(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

class PiPPlayerWindow(QWidget):
    play_pause_requested = Signal()
    seek_requested = Signal(int)
    dock_requested = Signal()
    pin_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.is_always_on_top = False
        self._duration_ms = 0
        self._position_ms = 0
        self._is_playing = False

        # Ràng buộc 2: Top-Level OS Window chuẩn, có min/max/close, hỗ trợ Windows Snap
        self.setWindowFlags(
            Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | 
            Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
        )
        self.setWindowTitle("AI Subtitle Suite - Video Player (PiP)")
        self.resize(640, 390)
        self.setMinimumSize(320, 200)

        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0B1120;
                color: #F8FAFC;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Video Viewport
        self.video_widget = QVideoWidget()
        self.video_widget.setAspectRatioMode(Qt.KeepAspectRatio)
        self.video_widget.setStyleSheet("background-color: #000000;")
        layout.addWidget(self.video_widget, stretch=1)

        # 2. Controls Panel
        controls_container = QWidget()
        controls_container.setStyleSheet("background-color: #0F172A; border-top: 1px solid #1E293B;")
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(10, 6, 10, 8)
        controls_layout.setSpacing(6)

        # 2a. Seek Slider
        self.slider_seek = QSlider(Qt.Horizontal)
        self.slider_seek.setRange(0, 0)
        self.slider_seek.setStyleSheet("""
            QSlider::groove:horizontal { 
                background: #1E293B; height: 4px; border-radius: 2px; 
            }
            QSlider::sub-page:horizontal { 
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #38BDF8, stop: 1 #818CF8); 
                border-radius: 2px; 
            }
            QSlider::handle:horizontal { 
                background: #F8FAFC; width: 12px; margin: -4px 0; border-radius: 6px; 
            }
            QSlider::handle:horizontal:hover { background: #38BDF8; }
        """)
        self.slider_seek.sliderMoved.connect(self._on_slider_moved)
        controls_layout.addWidget(self.slider_seek)

        # 2b. Buttons & Indicators Bar
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 0, 0, 0)
        btn_bar.setSpacing(8)

        # Play/Pause
        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.btn_play.setFixedSize(28, 28)
        self.btn_play.setStyleSheet("""
            QPushButton { 
                background: #1E293B; 
                border: 1px solid #334155; 
                border-radius: 14px; 
            }
            QPushButton:hover { background: #334155; }
            QPushButton:pressed { background: #38BDF8; }
        """)
        self.btn_play.clicked.connect(self.play_pause_requested.emit)
        btn_bar.addWidget(self.btn_play)

        # Timecode
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 500;")
        btn_bar.addWidget(self.lbl_time)

        btn_bar.addStretch()

        # Always on top toggle
        self.btn_pin = QPushButton("📌 Luôn nổi")
        self.btn_pin.setToolTip("Bật/Tắt chế độ ghim cửa sổ luôn nổi lên trên các ứng dụng khác")
        self.btn_pin.setStyleSheet("background: #1E293B; color: #94A3B8; border: 1px solid #334155; border-radius: 4px; font-size: 11px; padding: 4px 8px;")
        self.btn_pin.clicked.connect(lambda: self.toggle_always_on_top())
        btn_bar.addWidget(self.btn_pin)

        # Dock back to app
        self.btn_dock = QPushButton("🗗 Gắn lại vào App")
        self.btn_dock.setToolTip("Thu cửa sổ video trở lại khung làm việc chính của AI Subtitle Suite (Ctrl + P)")
        self.btn_dock.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #0284C7, stop: 1 #2563EB);
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
            }
            QPushButton:hover { background: #0284C7; }
        """)
        self.btn_dock.clicked.connect(self.dock_requested.emit)
        btn_bar.addWidget(self.btn_dock)

        controls_layout.addLayout(btn_bar)
        layout.addWidget(controls_container)

    def set_video_frame(self, frame: QVideoFrame):
        """Nhận và hiển thị video frame chuyển tiếp từ player chính (Zero Dual-Decode)."""
        if hasattr(self, "video_widget") and self.video_widget:
            sink = self.video_widget.videoSink()
            if sink and frame.isValid():
                sink.setVideoFrame(frame)

    def set_position(self, pos_ms: int):
        self._position_ms = max(0, pos_ms)
        if not self.slider_seek.isSliderDown():
            self.slider_seek.setValue(self._position_ms)
        self._update_time_label()

    def set_duration(self, dur_ms: int):
        self._duration_ms = max(0, dur_ms)
        self.slider_seek.setRange(0, self._duration_ms)
        self._update_time_label()

    def set_playing(self, is_playing: bool):
        self._is_playing = bool(is_playing)
        icon_type = QStyle.SP_MediaPause if self._is_playing else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icon_type))

    def _on_slider_moved(self, pos: int):
        self._position_ms = pos
        self._update_time_label()
        self.seek_requested.emit(pos)

    def _update_time_label(self):
        cur_str = format_time_ms(self._position_ms)
        dur_str = format_time_ms(self._duration_ms)
        self.lbl_time.setText(f"{cur_str} / {dur_str}")

    def toggle_always_on_top(self, enabled: bool = None):
        if enabled is None:
            self.is_always_on_top = not self.is_always_on_top
        else:
            self.is_always_on_top = bool(enabled)

        flags = (
            Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | 
            Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
        )
        if self.is_always_on_top:
            flags |= Qt.WindowStaysOnTopHint
            self.btn_pin.setText("📌 Đang nổi")
            self.btn_pin.setStyleSheet("background: #0284C7; color: #FFFFFF; border: 1px solid #38BDF8; border-radius: 4px; font-size: 11px; padding: 4px 8px; font-weight: bold;")
        else:
            self.btn_pin.setText("📌 Luôn nổi")
            self.btn_pin.setStyleSheet("background: #1E293B; color: #94A3B8; border: 1px solid #334155; border-radius: 4px; font-size: 11px; padding: 4px 8px;")

        was_visible = self.isVisible()
        geo = self.geometry()
        self.setWindowFlags(flags)
        self.setGeometry(geo)
        if was_visible:
            self.show()
        self.pin_toggled.emit(self.is_always_on_top)

    def closeEvent(self, event):
        """Khi bấm X trên cửa sổ, thực hiện Dock lại vào App thay vì hủy đối tượng."""
        event.ignore()
        self.dock_requested.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.play_pause_requested.emit()
            event.accept()
            return
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_P:
            self.dock_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PiPWorkspacePlaceholderWidget(QFrame):
    """
    Placeholder widget hiển thị trong không gian làm việc video khi PiP Player tách ra độc lập (FR-07).
    Bảo toàn 100% kích thước và tỷ lệ phân chia của Splitter, ngăn chặn co giật giao diện
    và duy trì tính ổn định hình học khi chuyển đổi qua lại giữa các tab (FINDING-PHASE3-001).
    """
    dock_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pip_workspace_placeholder")
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QFrame#pip_workspace_placeholder {
                background-color: #0F172A;
                border: 1.5px dashed #334155;
                border-radius: 10px;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # 1. Biểu tượng Video PiP
        self.lbl_icon = QLabel("📺")
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        self.lbl_icon.setStyleSheet("font-size: 40px; border: none; background: transparent;")
        layout.addWidget(self.lbl_icon)

        # 2. Tiêu đề trạng thái
        self.lbl_title = QLabel("CỬA SỔ XEM TRƯỚC VIDEO ĐANG TÁCH RỜI (PiP ACTIVE)")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: 700; letter-spacing: 0.5px; border: none; background: transparent;")
        layout.addWidget(self.lbl_title)

        # 3. Hướng dẫn & Lưu ý bố cục
        self.lbl_desc = QLabel(
            "Video đang phát ở cửa sổ độc lập. Bạn có thể kéo thả tự do hoặc dùng Windows Snap (Win + Phím Mũi Tên) để chia đôi màn hình.\n"
            "Vùng xem trước này được bảo lưu tỷ lệ để giữ nguyên vẹn bố cục ứng dụng mà không gây co giật khi chuyển tab."
        )
        self.lbl_desc.setAlignment(Qt.AlignCenter)
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.5; border: none; background: transparent; max-width: 480px;")
        layout.addWidget(self.lbl_desc)

        # 4. Nút bấm 1-click thu hồi video về App
        self.btn_dock = QPushButton("🗗 Gắn video trở lại đây (Ctrl + P)")
        self.btn_dock.setObjectName("btn_dock_from_placeholder")
        self.btn_dock.setCursor(Qt.PointingHandCursor)
        self.btn_dock.setToolTip("Thu cửa sổ video trở lại khung làm việc chính (Ctrl + P)")
        self.btn_dock.setStyleSheet("""
            QPushButton#btn_dock_from_placeholder {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #0284C7, stop: 1 #2563EB);
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 20px;
            }
            QPushButton#btn_dock_from_placeholder:hover {
                background: #0284C7;
            }
            QPushButton#btn_dock_from_placeholder:pressed {
                background: #0369A1;
            }
        """)
        self.btn_dock.clicked.connect(self.dock_requested.emit)
        layout.addWidget(self.btn_dock, alignment=Qt.AlignCenter)

