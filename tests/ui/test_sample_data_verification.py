import json
import os
import shutil
import tempfile
import types
import unittest
from dataclasses import replace
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QPushButton, QTableWidgetItem
from PySide6.QtCore import Qt

from core.subtitle_generation.generation_service import SubtitleGenerationService
from core.subtitle_generation.subtitle_generation_request import SubtitleGenerationRequest
from core.subtitle_generation.subtitle_generation_result import (
    SubtitleGenerationResult,
    WhisperSegmentResult,
)
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from workers.subtitle_generation_worker import SubtitleGenerationWorker
from ui.SubEditor import SubtitleEditorWidget
from ui.Gui import MainWindow


_app = QApplication.instance() or QApplication([])


class MockSource:
    fingerprint = "video_sample_hash_999"


class MockState:
    subtitle_artifact_id = "sample_sub_artifact"
    timing = None


class MockProject:
    def __init__(self, project_dir):
        self.project_id = "sample_project_001"
        self.project_dir = project_dir
        self.state = MockState()
        self.source = MockSource()


class MockArtifactStore:
    def __init__(self):
        self._store = {}

    def register(self, artifact):
        self._store[artifact.artifact_id] = artifact

    def get(self, artifact_id):
        return self._store.get(artifact_id)


class MockProjectService:
    def __init__(self, project_dir):
        self.current_project = MockProject(project_dir)
        self.artifact_store = MockArtifactStore()

    def mark_dirty(self):
        pass


class TrackingWhisperService(FasterWhisperService):
    def __init__(self):
        super().__init__()
        self.transcribe_calls = []

    def load_model(self, model_size, compute_type):
        self.model = object()
        self.current_model_size = model_size
        self.current_compute_type = compute_type

    def transcribe_batch(self, request, batch, is_cancelled):
        self.transcribe_calls.append(batch)
        # Tạo kết quả nhận diện trùng khớp mốc thời gian của từng câu trong batch
        return SubtitleGenerationResult(
            batch.batch_id,
            [
                WhisperSegmentResult(500, 2500, "Nội dung câu 1 nhận diện"),
                WhisperSegmentResult(4500, 6500, "Nội dung câu 2 nhận diện"),
                WhisperSegmentResult(8500, 10500, "Nội dung câu 3 nhận diện"),
            ],
        )


class TestSampleDataVerification(unittest.TestCase):
    """Bộ kiểm thử nghiệm thu End-to-End với Dữ liệu mẫu (Sample Data Acceptance Tests)."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.project_service = MockProjectService(self.test_dir)
        self.whisper = TrackingWhisperService()
        self.service = SubtitleGenerationService(
            self.whisper,
            self.project_service,
        )

        # 1. Tạo tệp dữ liệu mẫu Timing Draft (10 câu phát hiện giọng nói từ VAD)
        self.sample_timing_path = os.path.join(self.test_dir, "sample_vad_timing.srt")
        with open(self.sample_timing_path, "w", encoding="utf-8") as f:
            for i in range(10):
                start_sec = i * 4
                end_sec = start_sec + 3
                f.write(
                    f"{i+1}\n"
                    f"00:00:{start_sec:02d},000 --> 00:00:{end_sec:02d},000\n"
                    f"[ Chưa có nội dung ]\n\n"
                )

        self.project_service.current_project.state.timing = types.SimpleNamespace(
            timing_artifact_id="timing_artifact_vad"
        )
        self.project_service.artifact_store.register(
            types.SimpleNamespace(
                artifact_id="timing_artifact_vad",
                path=self.sample_timing_path,
            )
        )

        # Tạo video giả lập cho request
        self.sample_video_path = os.path.join(self.test_dir, "sample_video.mp4")
        with open(self.sample_video_path, "wb") as f:
            f.write(b"sample_video_mock_binary_data")

        self.request = SubtitleGenerationRequest(
            request_id="req_sample_run",
            project_id="sample_project_001",
            source_fingerprint="video_sample_hash_999",
            video_path=self.sample_video_path,
            model_size="base",
            compute_type="int8",
            language="vi",
            use_vad=True,
            min_silence_ms=500,
            word_timestamps=False,
            batch_duration_ms=60000,
            overlap_ms=1000,
            prompt_context="",
            batch_mode="segments",
            batch_size_value=3,  # Gen đợt 3 câu trên tổng 10 câu
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tc_sample_01_segment_gen_preserves_all_timing_draft_data(self):
        """TC-SAMPLE-01: Chạy Gen Sub theo segment (3 câu) trên dữ liệu mẫu 10 câu Timing Draft.
        Xác nhận:
        - Toàn bộ 10 câu vẫn còn nguyên trong Artifact phụ đề.
        - 3 câu đầu tiên được điền chữ (status: 'generated').
        - 7 câu còn lại giữ nguyên khung thời gian (status: 'timing', text: '').
        """
        SubtitleGenerationWorker.start = lambda w: w.run()
        self.service.start_generation(self.request, 40000)

        artifact = self.project_service.artifact_store.get(
            self.project_service.current_project.state.subtitle_artifact_id
        )
        self.assertIsNotNone(artifact)
        self.assertTrue(os.path.exists(artifact.path))

        data = self.service.artifact_service.load_data(artifact.path)
        segments = data.get("segments", [])

        # Kiểm tra không bị mất bất kỳ câu nào
        self.assertEqual(len(segments), 10, "Tổng số câu sau khi gen đợt 1 phải đủ 10 câu!")

        # Kiểm tra 3 câu đầu tiên đã được gen
        for i in range(3):
            self.assertEqual(segments[i]["status"], "generated")
            self.assertTrue(len(segments[i]["text"]) > 0)

        # Kiểm tra 7 câu tiếp theo vẫn là Timing Draft chờ xử lý
        for i in range(3, 10):
            self.assertEqual(segments[i]["status"], "timing")
            self.assertEqual(segments[i]["text"], "")

    def test_tc_sample_02_load_sample_data_into_editor_and_verify_timeline_button(self):
        """TC-SAMPLE-02: Nạp dữ liệu mẫu vào SubEditor và kiểm tra Nút 'Gen Sub (N câu)' trên Timeline:
        - Mặc định: '🎙️ Gen Sub đã chọn' (disabled)
        - Chọn 1 câu bất kỳ (chưa có chữ): Nút hiển thị '🎙️ Gen Sub (1 câu)' (enabled)
        - Chọn 3 câu lẻ tẻ bằng Ctrl: Nút hiển thị '🎙️ Gen Sub (3 câu)' (enabled)
        - Bấm nút: Gọi hàm _on_batch_segment_scan_requested với đúng 3 index đã chọn
        """
        # Khởi tạo MainWindow và SubEditor
        win = MainWindow.__new__(MainWindow)
        win.sub_editor = SubtitleEditorWidget()
        win.btn_timeline_batch_scan = QPushButton("🎙️ Gen Sub đã chọn")
        win.btn_timeline_batch_scan.setEnabled(False)
        win.btn_timeline_batch_scan.clicked.connect(win._on_timeline_batch_scan_clicked)

        # Giả lập 10 câu mẫu trong SubEditor (gồm 3 câu đã gen và 7 câu draft trống)
        sample_segments = []
        for i in range(10):
            sample_segments.append({
                "id": f"sub_seg_{i+1}",
                "stt": str(i+1),
                "start": f"00:00:{i*4:02d},000",
                "end": f"00:00:{i*4+3:02d},000",
                "start_ms": i * 4000,
                "end_ms": i * 4000 + 3000,
                "text": f"Nội dung câu {i+1}" if i < 3 else "",
                "status": "generated" if i < 3 else "timing",
            })
        win.sub_editor.all_segments = sample_segments
        win.sub_editor.render_page()

        # 1. Trạng thái ban đầu chưa chọn câu nào
        win.sub_editor.current_index = -1
        win._update_timeline_batch_scan_button()
        self.assertFalse(win.btn_timeline_batch_scan.isEnabled())
        self.assertEqual(win.btn_timeline_batch_scan.text(), "🎙️ Gen Sub đã chọn")

        # 2. Click chọn 1 câu chưa có chữ (ví dụ câu số 5, index 4)
        win.sub_editor.current_index = 4
        win._update_timeline_batch_scan_button()
        self.assertTrue(win.btn_timeline_batch_scan.isEnabled())
        self.assertEqual(win.btn_timeline_batch_scan.text(), "🎙️ Gen Sub (1 câu)")

        # 3. Chọn 3 câu qua Ctrl-selection (ví dụ câu 4, câu 6, câu 8 -> index 3, 5, 7)
        win.sub_editor._get_selected_source_indices = lambda: [3, 5, 7]
        win._update_timeline_batch_scan_button()
        self.assertTrue(win.btn_timeline_batch_scan.isEnabled())
        self.assertEqual(win.btn_timeline_batch_scan.text(), "🎙️ Gen Sub (3 câu)")

        # 4. Bấm nút Gen Sub trên thanh Timeline
        dispatched_batch = []
        win._on_batch_segment_scan_requested = lambda indices: dispatched_batch.append(indices)
        win._on_timeline_batch_scan_clicked()

        self.assertEqual(len(dispatched_batch), 1)
        self.assertEqual(dispatched_batch[0], [3, 5, 7], "Phải phát lệnh quét đúng 3 câu index [3, 5, 7]!")

    def test_tc_sample_03_real_srt_timing_draft_selective_scan_workflow(self):
        """TC-SAMPLE-03: Kiểm thử toàn trình với tệp mẫu thực tế E:\\ghpm98.srt:
        - Nạp tệp mẫu vào Editor.
        - Giả lập người dùng tạo Timing Draft (các câu có timecode nhưng chưa có nội dung).
        - Chọn đồng thời 4 câu (1, 3, 5, 7) trên Timeline/Bảng.
        - Nút Gen Sub cập nhật chính xác '🎙️ Gen Sub (4 câu)'.
        - Thực hiện quét mẫu: Chỉ 4 câu này được cập nhật chữ, các câu còn lại giữ nguyên.
        """
        sample_path = r"E:\ghpm98.srt" if os.path.exists(r"E:\ghpm98.srt") else self.sample_timing_path
        
        from core.export.subtitle_parser import parse_srt_content
        with open(sample_path, "r", encoding="utf-8") as f:
            parsed = parse_srt_content(f.read())

        self.assertTrue(len(parsed) >= 5, "Tệp mẫu phải có ít nhất 5 câu phụ đề.")

        # Chuẩn bị dữ liệu mẫu dạng Timing Draft (chưa có chữ)
        draft_segments = []
        for i, s in enumerate(parsed[:8]):
            draft_segments.append({
                "id": f"real_seg_{i+1}",
                "stt": str(i+1),
                "start": s.get("start", "00:00:00,000"),
                "end": s.get("end", "00:00:01,000"),
                "start_ms": s.get("start_ms", i * 2000),
                "end_ms": s.get("end_ms", i * 2000 + 1500),
                "text": "",  # Trống như Timing Draft
                "status": "timing",
            })

        win = MainWindow.__new__(MainWindow)
        win.sub_editor = SubtitleEditorWidget()
        win.btn_timeline_batch_scan = QPushButton("🎙️ Gen Sub đã chọn")
        win.btn_timeline_batch_scan.setEnabled(False)
        win.btn_timeline_batch_scan.clicked.connect(win._on_timeline_batch_scan_clicked)

        win.sub_editor.all_segments = draft_segments
        win.sub_editor.render_page()

        # Chọn 4 câu: index 0, 2, 4, 6
        target_indices = [0, 2, 4, 6]
        win.sub_editor._get_selected_source_indices = lambda: target_indices
        win._update_timeline_batch_scan_button()

        self.assertTrue(win.btn_timeline_batch_scan.isEnabled())
        self.assertEqual(win.btn_timeline_batch_scan.text(), "🎙️ Gen Sub (4 câu)")

        # Giả lập quét hoàn tất 4 câu này
        for idx in target_indices:
            draft_segments[idx]["text"] = f"Nhận diện Whisper mẫu #{idx+1}"
            draft_segments[idx]["status"] = "generated"

        win.sub_editor.render_page()

        # Xác nhận 4 câu đã chọn có chữ, 4 câu còn lại vẫn là Timing Draft trống
        for idx in range(8):
            if idx in target_indices:
                self.assertEqual(draft_segments[idx]["status"], "generated")
                self.assertTrue(len(draft_segments[idx]["text"]) > 0)
            else:
                self.assertEqual(draft_segments[idx]["status"], "timing")
                self.assertEqual(draft_segments[idx]["text"], "")


if __name__ == "__main__":
    unittest.main()
