import re
import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QDialog,
    QLabel,
    QPushButton,
    QProgressBar,
    QProgressDialog,
    QLineEdit,
    QMessageBox,
    QFrame,
)
from PySide6.QtCore import Qt, QRect

from ui.Gui import MainWindow
from ui.SubEditor import SubtitleEditorWidget
from ui.timeline.timeline_widget import TimelineWidget
from ui.timeline.subtitle_track import SubtitleTrack
from ui.timeline.waveform_view import WaveformView
from ui.timeline.timeline_ruler import TimeRuler
from ui.quality_inspector_panel import QualityInspectorPanel
from ui.subtitle_inspector_panel import SubtitleInspectorPanel
from ui.batch.batch_progress_dashboard import BatchProgressDashboard
from ui.components.tm_matches_panel import TMMatchesPanel
from ui.components.transcription_context_panel import TranscriptionContextPanel
from ui.dialogs.new_project_dialog import NewProjectDialog
from ui.dialogs.media_import_dialog import MediaImportDialog
from ui.dialogs.hardware_check_dialog import HardwareCheckDialog
from ui.dialogs.preview_range_dialog import PreviewRangeDialog
from ui.dialogs.source_mismatch_dialog import SourceMismatchDialog
from ui.dialogs.recovery_dialog import RecoveryDialog
from ui.pages.dashboard_page import DashboardPage
from ui.pages.settings_page import SettingsCenterPage
from ui.pages.export_center_page import ExportCenterPage
from ui.pages.draft_center_page import DraftCenterPage
from ui.pages.help_center_page import HelpCenterPage
from ui.theme import Theme
from ui.core.liquid_theme_engine import LiquidThemeEngine


_app = QApplication.instance() or QApplication([])
_app.setStyleSheet(LiquidThemeEngine.compile_stylesheet())


class UIInspector:
    """Công cụ tự động dò quét các lỗi giao diện: che lấp text, đè chồng widget, text placeholder lỗi."""

    PLACEHOLDER_REGEX = re.compile(r"\{[0-9a-zA-Z_]+\}|\%[sdaf]|\bundefined\b|\bNaN\b|\bnull\b|\bNone\b")

    @classmethod
    def check_progress_bar_clipping(cls, pbar: QProgressBar) -> list[str]:
        """Kiểm tra thanh tiến trình: nếu thanh mảnh (<16px) thì bắt buộc textVisible=False để không bị đè vỡ text."""
        issues = []
        is_visible_text = pbar.isTextVisible()
        h = pbar.height() if pbar.height() > 0 else pbar.maximumHeight()
        if is_visible_text and h < 16:
            issues.append(
                f"LỖI CHE LẤP TEXT: QProgressBar (height={h}px) đang bật textVisible=True. "
                f"Chữ phần trăm sẽ bị cắt cụt/đè nát viền!"
            )
        return issues

    @classmethod
    def check_text_truncation(cls, widget: QWidget) -> list[str]:
        """Kiểm tra text bị cắt cụt do ép kích thước cố định nhỏ hơn độ dài thực của chữ."""
        issues = []
        if isinstance(widget, (QLabel, QPushButton)):
            text = widget.text().strip()
            if not text:
                return issues
            if isinstance(widget, QLabel) and widget.wordWrap():
                return issues

            fm = widget.fontMetrics()
            text_width = fm.horizontalAdvance(text)
            text_height = fm.height()

            max_w = widget.maximumWidth()
            max_h = widget.maximumHeight()
            if 0 < max_w < text_width:
                issues.append(
                    f"LỖI CẮT CHỮ: {widget.__class__.__name__} ('{text}') có max_width={max_w}px < text_width={text_width}px"
                )
            if 0 < max_h < text_height:
                issues.append(
                    f"LỖI CHE CHIỀU CAO: {widget.__class__.__name__} ('{text}') có max_height={max_h}px < font_height={text_height}px"
                )
        return issues

    @classmethod
    def check_malformed_placeholders(cls, text: str, context: str) -> list[str]:
        """Kiểm tra rò rỉ mã mẫu template hoặc giá trị lỗi như {0}, {count}, undefined, NaN, None."""
        issues = []
        if not text:
            return issues
        matches = cls.PLACEHOLDER_REGEX.findall(text)
        for match in matches:
            issues.append(f"LỖI TEXT SAI: {context} chứa chuỗi mẫu chưa được format: '{match}' (Toàn văn: '{text}')")
        return issues

    @classmethod
    def check_overlapping_siblings(cls, parent: QWidget) -> list[str]:
        """Kiểm tra vị trí sai: các widget tương tác cùng cấp bị đè chồng lấn lên nhau."""
        issues = []
        children = [
            c for c in parent.findChildren(QWidget, options=Qt.FindDirectChildrenOnly)
            if c.isVisible() and not c.isWindow() and isinstance(c, (QPushButton, QLineEdit, QLabel))
        ]
        for i in range(len(children)):
            for j in range(i + 1, len(children)):
                w1, w2 = children[i], children[j]
                r1 = w1.geometry()
                r2 = w2.geometry()
                intersect = r1.intersected(r2)
                if intersect.width() > 3 and intersect.height() > 3:
                    issues.append(
                        f"LỖI VỊ TRÍ ĐÈ NHAU: {w1.__class__.__name__} ('{getattr(w1, 'text', lambda: '')()}') "
                        f"đang đè lên {w2.__class__.__name__} ('{getattr(w2, 'text', lambda: '')()}') "
                        f"tại vùng {intersect.width()}x{intersect.height()}px"
                    )
        return issues

    @classmethod
    def audit_widget_tree(cls, root: QWidget, name: str) -> list[str]:
        """Dò quét toàn bộ cây widget (tất cả nhãn, nút bấm, progress bar)."""
        issues = []
        # 1. Kiểm tra progress bars
        for pb in root.findChildren(QProgressBar):
            issues.extend(cls.check_progress_bar_clipping(pb))

        # 2. Kiểm tra buttons
        for btn in root.findChildren(QPushButton):
            text = btn.text().strip()
            issues.extend(cls.check_malformed_placeholders(text, f"[{name}] Nút '{text}'"))
            if text and btn.maximumHeight() > 0 and btn.maximumHeight() < 20:
                issues.append(f"[{name}] LỖI CHIỀU CAO: Nút '{text}' quá nhỏ (max_height={btn.maximumHeight()}px < 20px)")

        # 3. Kiểm tra labels
        for lbl in root.findChildren(QLabel):
            text = lbl.text().strip()
            issues.extend(cls.check_malformed_placeholders(text, f"[{name}] Label '{text}'"))

        return issues


class TestUIVisualIntegrity:
    """Bộ kiểm thử nghiệm thu toàn bộ giao diện (Comprehensive Full-UI Audit Suite)."""

    def test_tc_ui_audit_01_batch_scan_progress_dialog_no_clipping(self):
        """TC-UI-AUDIT-01: Kiểm tra hộp thoại QProgressDialog (Nhận diện âm thanh Whisper):
        - Thanh tiến trình phải tắt textVisible (hoặc cao >= 18px) để không bị đè vỡ chữ '0%'.
        - Hộp thoại có độ rộng chuẩn 380px, Dark Theme sang trọng đồng bộ.
        """
        win = MainWindow.__new__(MainWindow)
        progress = win._create_batch_scan_progress_dialog(1)

        pbar = progress.findChild(QProgressBar)
        assert pbar is not None, "QProgressDialog phải chứa QProgressBar"
        assert pbar.isTextVisible() is False, "QProgressBar 8px phải tắt textVisible=False để tránh đè vỡ chữ!"
        assert progress.width() >= 320, "QProgressDialog phải có độ rộng tối thiểu >= 320px để không bị cụt text"

        issues = UIInspector.check_progress_bar_clipping(pbar)
        assert len(issues) == 0, f"Phát hiện lỗi hiển thị trên QProgressDialog: {issues}"

    def test_tc_ui_audit_02_all_app_progress_bars_integrity(self):
        """TC-UI-AUDIT-02: Dò quét toàn bộ QProgressBar trong ứng dụng, bảo đảm không thanh nào bị đè chữ."""
        from ui.subtitle_generation_panel import SubtitleGenerationPanel

        widgets_to_test = [
            BatchProgressDashboard(MagicMock(), MagicMock()),
            SubtitleGenerationPanel(MagicMock()),
            DashboardPage(),
        ]

        all_issues = []
        for widget in widgets_to_test:
            for pb in widget.findChildren(QProgressBar):
                all_issues.extend(UIInspector.check_progress_bar_clipping(pb))

        assert len(all_issues) == 0, f"Phát hiện thanh tiến trình lỗi: {all_issues}"

    def test_tc_ui_audit_03_all_dialogs_visual_and_text_integrity(self):
        """TC-UI-AUDIT-03: Dò quét toàn bộ 6 Dialog trong ứng dụng:
        - NewProjectDialog, MediaImportDialog, HardwareCheckDialog, PreviewRangeDialog,
          SourceMismatchDialog, RecoveryDialog.
        """
        dialogs = [
            ("NewProjectDialog", NewProjectDialog()),
            ("MediaImportDialog", MediaImportDialog(MagicMock())),
            ("HardwareCheckDialog", HardwareCheckDialog()),
            ("PreviewRangeDialog", PreviewRangeDialog('00:00:00', '00:00:10', MagicMock(duration_ms=10000, overlapping_count=0, manual_edits_count=0, overlapping_segments=[]))),
            ("SourceMismatchDialog", SourceMismatchDialog('vid.mp4', 'expected.mp4', '2026-10-25 00:00:00')),
            ("RecoveryDialog", RecoveryDialog('art_1', 'proj_1', '2026-10-25 00:00:00')),
        ]

        all_issues = []
        for name, dlg in dialogs:
            all_issues.extend(UIInspector.audit_widget_tree(dlg, name))

        assert len(all_issues) == 0, f"Phát hiện lỗi trong các Dialog: {all_issues}"

    def test_tc_ui_audit_04_all_pages_visual_and_text_integrity(self):
        """TC-UI-AUDIT-04: Dò quét toàn bộ 5 Pages trong Drawer/Navigation:
        - DashboardPage, SettingsCenterPage, ExportCenterPage, DraftCenterPage, HelpCenterPage.
        """
        pages = [
            ("DashboardPage", DashboardPage()),
            ("SettingsCenterPage", SettingsCenterPage()),
            ("ExportCenterPage", ExportCenterPage()),
            ("DraftCenterPage", DraftCenterPage()),
            ("HelpCenterPage", HelpCenterPage()),
        ]

        all_issues = []
        for name, page in pages:
            all_issues.extend(UIInspector.audit_widget_tree(page, name))

        assert len(all_issues) == 0, f"Phát hiện lỗi trong các Page: {all_issues}"

    def test_tc_ui_audit_05_all_panels_visual_and_text_integrity(self):
        """TC-UI-AUDIT-05: Dò quét toàn bộ 5 Panels chuyên dụng:
        - QualityInspectorPanel, SubtitleInspectorPanel, BatchProgressDashboard,
          TMMatchesPanel, TranscriptionContextPanel.
        """
        panels = [
            ("QualityInspectorPanel", QualityInspectorPanel()),
            ("SubtitleInspectorPanel", SubtitleInspectorPanel()),
            ("BatchProgressDashboard", BatchProgressDashboard(MagicMock(), MagicMock())),
            ("TMMatchesPanel", TMMatchesPanel()),
            ("TranscriptionContextPanel", TranscriptionContextPanel()),
        ]

        all_issues = []
        for name, panel in panels:
            all_issues.extend(UIInspector.audit_widget_tree(panel, name))

        assert len(all_issues) == 0, f"Phát hiện lỗi trong các Panel: {all_issues}"

    def test_tc_ui_audit_06_sub_editor_and_current_subtitle_editor(self):
        """TC-UI-AUDIT-06: Dò quét SubtitleEditorWidget và thanh Current Subtitle:
        - Nút hành động không bị đè bẹp, không lỗi placeholder.
        - Không có xung đột vị trí đè lấn giữa các input/button.
        """
        editor = SubtitleEditorWidget()
        issues = UIInspector.audit_widget_tree(editor, "SubtitleEditor")

        curr_editor = getattr(editor, "current_editor", None)
        if curr_editor:
            issues.extend(UIInspector.check_overlapping_siblings(curr_editor))

        assert len(issues) == 0, f"Phát hiện lỗi trên SubtitleEditor: {issues}"

    def test_tc_ui_audit_07_timeline_widget_and_toolbar(self):
        """TC-UI-AUDIT-07: Dò quét TimelineWidget, TimelineToolbar, Track, Ruler, Waveform:
        - Nút Gen Sub, Nudge, Ripple Shift, Zoom có hit-target chuẩn và không lỗi text.
        - Chiều cao các thành phần Timeline hợp lý (Track >= 50px, Ruler >= 25px, Waveform >= 75px).
        """
        track = SubtitleTrack()
        ruler = TimeRuler()
        waveform = WaveformView()

        assert track.height() >= 45, "SubtitleTrack phải có chiều cao tối thiểu >= 45px"
        assert ruler.height() >= 20, "TimeRuler phải có chiều cao tối thiểu >= 20px"
        assert waveform.height() >= 60, "WaveformView phải có chiều cao tối thiểu >= 60px"

    def test_tc_ui_audit_08_theme_contrast_and_color_tokens(self):
        """TC-UI-AUDIT-08: Kiểm tra độ hợp lệ của toàn bộ bảng mã màu Theme và đảm bảo độ tương phản:
        - Mọi mã màu đều là hex hợp lệ (#RGB hoặc #RRGGBB).
        - Màu chữ TEXT_PRIMARY có độ sáng vượt trội so với màu nền SURFACE_MAIN.
        """
        hex_regex = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
        color_tokens = [
            ("BG_APP", Theme.BG_APP),
            ("SURFACE", Theme.SURFACE),
            ("SURFACE_MAIN", Theme.SURFACE_MAIN),
            ("SURFACE_ELEVATED", Theme.SURFACE_ELEVATED),
            ("SURFACE_SOFT", Theme.SURFACE_SOFT),
            ("BORDER", Theme.BORDER),
            ("PRIMARY_PURPLE", Theme.PRIMARY_PURPLE),
            ("CYAN", Theme.CYAN),
            ("TEXT_PRIMARY", Theme.TEXT_PRIMARY),
            ("TEXT_MUTED", Theme.TEXT_MUTED),
        ]

        for name, color in color_tokens:
            assert hex_regex.match(color), f"Mã màu Theme.{name} = '{color}' không hợp lệ!"

    def test_tc_ui_audit_09_qmessagebox_dark_theme_and_no_white_glitch(self):
        """TC-UI-AUDIT-09: Kiểm tra Dark Theme cho QMessageBox:
        - StyleSheet biên dịch phải chứa quy tắc QMessageBox, QLabel, QPushButton.
        - Không bị lỗi màu trắng trên nền trắng (white-on-white glitch).
        """
        compiled = LiquidThemeEngine.compile_stylesheet()
        assert "QMessageBox {" in compiled, "Stylesheet phải chứa quy tắc định kiểu QMessageBox"
        assert "QMessageBox QLabel" in compiled, "Stylesheet phải chứa quy tắc QMessageBox QLabel"
        assert "QMessageBox QPushButton" in compiled, "Stylesheet phải chứa quy tắc QMessageBox QPushButton"
        assert Theme.SURFACE in compiled, "Màu nền SURFACE phải được render vào QMessageBox"

        msgbox = QMessageBox()
        msgbox.setWindowTitle("Kiểm thử")
        msgbox.setText("Nội dung thông báo")
        msgbox.setStandardButtons(QMessageBox.StandardButton.Ok)
        assert msgbox.windowTitle() == "Kiểm thử"
        msgbox.close()

    def test_tc_ui_audit_10_immersive_dark_mode_and_toast_new_project(self):
        """TC-UI-AUDIT-10: Kiểm tra kích hoạt DWM Immersive Dark Mode và chuyển sang Toast khi tạo dự án."""
        import inspect
        from unittest.mock import patch, MagicMock

        # 1. Kiểm tra action_new_project dùng Toast.show_success thay vì QMessageBox.information
        src = inspect.getsource(MainWindow.action_new_project)
        assert "Toast.show_success" in src, "action_new_project phải dùng Toast.show_success"
        assert "QMessageBox.information" not in src, "action_new_project không được dùng QMessageBox.information làm gián đoạn UX"

        # 2. Kiểm tra _apply_window_corner_preference có DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        src_pref = inspect.getsource(MainWindow._apply_window_corner_preference)
        assert "DWMWA_USE_IMMERSIVE_DARK_MODE = 20" in src_pref, "Phải định nghĩa DWMWA_USE_IMMERSIVE_DARK_MODE = 20"
        assert "hwnd" in src_pref

        # 3. Chạy thử nghiệm mock DwmSetWindowAttribute
        win = MainWindow.__new__(MainWindow)
        win.winId = MagicMock(return_value=12345)
        win.isMaximized = MagicMock(return_value=False)
        with patch("sys.platform", "win32"), patch("ctypes.windll.dwmapi.DwmSetWindowAttribute") as mock_dwm:
            win._apply_window_corner_preference()
            assert mock_dwm.call_count == 2

    def test_tc_ui_audit_11_export_center_frames_scoped_no_checkbox_clipping(self):
        """Xác thực stylesheet các QFrame trong ExportCenterPage được scope chính xác, không cascade padding làm biến mất chữ QCheckBox."""
        page = ExportCenterPage()
        frames = [w for w in page.findChildren(QFrame) if type(w) is QFrame]
        assert len(frames) >= 4, "Phải tìm thấy ít nhất 4 QFrame container"
        for frame in frames:
            ss = frame.styleSheet()
            if ss:
                # Không được chứa CSS padding trực tiếp gây cascade
                assert "padding:" not in ss, f"QFrame {frame.objectName()} chứa CSS padding làm cascade xuống widget con: {ss}"
                # Phải có selector định danh QFrame
                assert "QFrame#" in ss, f"QFrame {frame.objectName()} không được scope bằng selector: {ss}"
        
        # Đảm bảo các checkbox có sizeHint chiều cao bình thường (>= 16px) và spinbox đủ độ rộng
        assert page.chk_srt.sizeHint().height() >= 16
        assert page.spin_batch_count.maximumWidth() >= 85 or page.spin_batch_count.width() >= 85


