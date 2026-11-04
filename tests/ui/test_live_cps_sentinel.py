# -*- coding: utf-8 -*-
"""
Kiểm thử TDD cho Live CPS Sentinel HUD & Smart Natural Split (FR-01 / Phase 1)
Thuộc Kế hoạch: DEV-SPEC-PHASE1-HUD-001
"""
import io
import unittest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.SubEditor import CurrentSubtitleEditor, SubtitleEditorWidget, ms_to_time_str, time_str_to_ms


class TestLiveCPSSentinel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = CurrentSubtitleEditor()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()

    # --- 1. KIỂM THỬ CÔNG THỨC CPS & AN TOÀN CHIA CHO 0 ---

    def test_calculate_cps_normal(self):
        """Thời lượng 2.0s (2000ms), 50 ký tự -> CPS = 25.0."""
        cps = CurrentSubtitleEditor.calculate_cps("A" * 50, 1000, 3000)
        self.assertEqual(cps, 25.0)

    def test_calculate_cps_low(self):
        """Thời lượng 3.0s (3000ms), 30 ký tự -> CPS = 10.0."""
        cps = CurrentSubtitleEditor.calculate_cps("A" * 30, 0, 3000)
        self.assertEqual(cps, 10.0)

    def test_calculate_cps_zero_and_inverted_duration_protection(self):
        """Bảo vệ chia cho 0 khi start_ms >= end_ms; không crash ZeroDivisionError."""
        # start == end (0ms) -> duration kẹp max(0.1, 0) = 0.1s
        cps_zero = CurrentSubtitleEditor.calculate_cps("Hello World", 5000, 5000)
        self.assertGreater(cps_zero, 0.0)

        # start > end (-1000ms) -> duration kẹp max(0.1, -1.0) = 0.1s
        cps_inverted = CurrentSubtitleEditor.calculate_cps("Hello World", 5000, 4000)
        self.assertGreater(cps_inverted, 0.0)

    def test_calculate_cps_empty_or_placeholder_text(self):
        """Văn bản rỗng hoặc placeholder trả về 0.0 CPS."""
        self.assertEqual(CurrentSubtitleEditor.calculate_cps("", 1000, 3000), 0.0)
        self.assertEqual(CurrentSubtitleEditor.calculate_cps("   ", 1000, 3000), 0.0)
        self.assertEqual(CurrentSubtitleEditor.calculate_cps("[ Chưa có nội dung ]", 1000, 3000), 0.0)

    # --- 2. KIỂM THỬ THUẬT TOÁN NGẮT CÂU TỰ NHIÊN (NATURAL BOUNDARY SPLITTING) ---

    def test_split_primary_punctuation(self):
        """Ưu tiên dấu ngắt câu chính (. ! ? … 。 ！ ？ \n) gần giữa câu nhất."""
        text = "Hôm nay thời tiết rất đẹp. Chúng ta hãy cùng đi dạo nhé!"
        idx, part1, part2 = CurrentSubtitleEditor.split_text_at_natural_boundary(text)
        self.assertTrue(part1.endswith("."))
        self.assertEqual(part1, "Hôm nay thời tiết rất đẹp.")
        self.assertEqual(part2, "Chúng ta hãy cùng đi dạo nhé!")

    def test_split_primary_cjk_punctuation(self):
        """Ưu tiên dấu ngắt câu CJK (。) thay vì cắt giữa từ."""
        text = "今日はいい天気ですね。散歩に行きましょう。"
        idx, part1, part2 = CurrentSubtitleEditor.split_text_at_natural_boundary(text)
        self.assertTrue(part1.endswith("。"))
        self.assertEqual(part1, "今日はいい天気ですね。")
        self.assertEqual(part2, "散歩に行きましょう。")

    def test_split_secondary_punctuation(self):
        """Không có dấu chấm thì ưu tiên dấu phẩy / chấm phẩy (, ; 、 ，)."""
        text = "Tôi muốn ăn phở, nhưng bạn tôi lại thích ăn bún chả"
        idx, part1, part2 = CurrentSubtitleEditor.split_text_at_natural_boundary(text)
        self.assertTrue(part1.endswith(","))
        self.assertEqual(part1, "Tôi muốn ăn phở,")
        self.assertEqual(part2, "nhưng bạn tôi lại thích ăn bún chả")

    def test_split_whitespace_when_no_punctuation(self):
        """Không có dấu câu thì tách tại khoảng trắng gần giữa câu nhất."""
        text = "Một hai ba bốn năm sáu bảy tám chín mười"
        idx, part1, part2 = CurrentSubtitleEditor.split_text_at_natural_boundary(text)
        self.assertTrue(len(part1) > 0 and len(part2) > 0)
        self.assertEqual(f"{part1} {part2}", text)

    def test_split_cjk_unspaced_fallback_midpoint(self):
        """Chuỗi tiếng Nhật/Trung không có dấu cách hay dấu câu: Fallback cắt tại Midpoint, không crash."""
        text = "昨日友達と一緒に映画を見に行きました"
        idx, part1, part2 = CurrentSubtitleEditor.split_text_at_natural_boundary(text)
        midpoint = len(text) // 2
        self.assertEqual(idx, midpoint)
        self.assertEqual(part1, text[:midpoint])
        self.assertEqual(part2, text[midpoint:])

    # --- 3. KIỂM THỬ HIỂN THỊ HUY HIỆU LIVE CPS & NÚT TÁCH TRÊN CURRENT EDITOR ---

    def test_cps_badge_and_button_visibility_low_cps(self):
        """Khi CPS <= 20.0: Huy hiệu và nút tách đều bị ẩn."""
        # 10 ký tự trong 2.0s -> CPS = 5.0
        self.editor.set_values(1000, 3000, "Xin chào bạn")
        self.assertTrue(self.editor.lbl_cps.isHidden())
        self.assertTrue(self.editor.btn_smart_split.isHidden())

    def test_cps_badge_and_button_visibility_high_cps(self):
        """Khi CPS > 20.0: Huy hiệu hiển thị ⚠️ và nút ⚡ Tách câu xuất hiện."""
        # 60 ký tự trong 2.0s -> CPS = 30.0
        high_cps_text = "Đây là một câu phụ đề rất dài vượt quá giới hạn hai mươi ký tự mỗi giây."
        self.editor.set_values(1000, 3000, high_cps_text)
        self.assertFalse(self.editor.lbl_cps.isHidden())
        self.assertFalse(self.editor.btn_smart_split.isHidden())
        self.assertIn("⚠️", self.editor.lbl_cps.text())
        self.assertIn("CPS", self.editor.lbl_cps.text())

    def test_cps_badge_updates_dynamically_on_text_change(self):
        """Gõ thêm ký tự vào text_edit vượt ngưỡng 20 tự động kích hoạt huy hiệu."""
        self.editor.set_values(1000, 3000, "Ngắn")
        self.assertTrue(self.editor.lbl_cps.isHidden())

        # Gõ thêm text làm CPS tăng vọt
        self.editor.text_edit.setPlainText("Câu này được gõ thêm vào rất nhiều chữ để CPS vượt quá 20 ký tự một giây")
        self.assertFalse(self.editor.lbl_cps.isHidden())
        self.assertFalse(self.editor.btn_smart_split.isHidden())

    # --- 4. KIỂM THỬ TÍN HIỆU SMART SPLIT & THỜI ĐIỂM CẮT ---

    def test_smart_split_signal_emits_valid_split_time(self):
        """Bấm nút ⚡ Tách câu phát tín hiệu smart_split_requested với split_time_ms hợp lệ."""
        text = "Hôm nay trời rất đẹp. Chúng ta hãy cùng đi dạo trong công viên nhé!"
        start_ms, end_ms = 10000, 14000  # 4s
        self.editor.set_values(start_ms, end_ms, text)

        emitted_splits = []
        self.editor.smart_split_requested.connect(lambda t: emitted_splits.append(t))

        self.editor.btn_smart_split.click()
        self.assertEqual(len(emitted_splits), 1)
        split_time = emitted_splits[0]
        # Thời điểm cắt phải nằm trong [start + 200, end - 200]
        self.assertGreaterEqual(split_time, start_ms + 200)
        self.assertLessEqual(split_time, end_ms - 200)

    # --- 5. BẢO ĐẢM SOFT WARNING ONLY (KHÔNG CHẶN XUẤT FILE) ---

    def test_high_cps_does_not_block_export(self):
        """Phụ đề CPS cao (> 30 CPS) vẫn xuất ra SRT bình thường mà không bị cản trở."""
        import tempfile
        from pathlib import Path
        from core.subtitle_exporter import SubtitleExportService

        high_cps_subs = [
            (1000, 2000, "Chuỗi ký tự dài bất thường gây CPS cực cao trong khoảng thời gian một giây")
        ]
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            SubtitleExportService.export_srt(high_cps_subs, tmp_path)
            content = Path(tmp_path).read_text(encoding="utf-8")
            self.assertIn("Chuỗi ký tự dài", content)
            self.assertIn("00:00:01,000 --> 00:00:02,000", content)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
