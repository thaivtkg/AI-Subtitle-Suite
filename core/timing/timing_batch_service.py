import os
import json
import uuid
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot
from dataclasses import asdict

from core.services.project_service import ProjectService
from core.artifacts.artifact import Artifact
from core.artifacts.artifact_types import ArtifactType, ArtifactStatus
from core.timing.timing_checkpoint import TimingCheckpoint
from core.timing.timing_batch import TimingBatch, BatchStatus
from core.timing.timing_run_request import TimingRunRequest
from core.project.project_state import TimingState
from workers.TimingBatchWorker import TimingBatchWorker

class TimingBatchService(QObject):
    progress_signal = Signal(int, str)
    log_signal = Signal(str)
    batch_completed_signal = Signal(int, int)
    timing_finished_signal = Signal()
    error_signal = Signal(str)
    state_changed_signal = Signal(str, str)
    effective_compute_signal = Signal(str, str)

    def __init__(self, project_service: ProjectService, history_service=None):
        super().__init__()
        self.project_service = project_service
        self.history_service = history_service
        self.worker = None
        self._current_settings = None
        self._last_timing_diagnostics = []
        self._pending_draft_lines = None
        self._pending_terminal_state = None
        self._connected_finished_worker = None

    def _clear_timing_diagnostics(self):
        self._last_timing_diagnostics = []

    @staticmethod
    def _settings_from_checkpoint(checkpoint):
        required = (
            "model_size", "compute_type", "use_vad", "min_silence_ms",
            "fix_overlap", "overlap_gap_ms", "overlap_ms", "max_window_ms",
        )
        if any(getattr(checkpoint, name, None) is None for name in required):
            raise ValueError(
                "This checkpoint was created before model settings were stored. "
                "Resume cannot safely determine the original model configuration. "
                "Start a new Timing generation run."
            )
        settings = {name: getattr(checkpoint, name) for name in required}
        if getattr(checkpoint, "music_mode", None) is not None:
            settings["music_mode"] = checkpoint.music_mode
        if getattr(checkpoint, "language", None) is not None:
            settings["language"] = checkpoint.language
        if getattr(checkpoint, "specialized_model", None) is not None:
            settings["specialized_model"] = checkpoint.specialized_model
        for vad_field in (
            "vad_preset", "vad_threshold", "vad_speech_pad_ms",
            "vad_max_speech_duration_s", "min_speech_duration_ms",
            "condition_on_previous_text",
        ):
            if getattr(checkpoint, vad_field, None) is not None:
                settings[vad_field] = getattr(checkpoint, vad_field)
        return TimingBatchService._validate_settings(settings)

    @staticmethod
    def _validate_settings(settings: dict | None, defaults: TimingState | None = None) -> dict:
        defaults = defaults or TimingState()
        settings = settings or {}
        result = {
            name: settings.get(name, getattr(defaults, name))
            for name in (
                "model_size", "compute_type", "use_vad", "min_silence_ms",
                "fix_overlap", "overlap_gap_ms", "overlap_ms", "max_window_ms",
            )
        }
        if "music_mode" in settings:
            result["music_mode"] = bool(settings["music_mode"])
        elif getattr(defaults, "music_mode", False):
            result["music_mode"] = True
        if "language" in settings:
            result["language"] = settings["language"]
        if "specialized_model" in settings:
            result["specialized_model"] = str(settings.get("specialized_model") or "")
        for vad_field in (
            "vad_preset", "vad_threshold", "vad_speech_pad_ms",
            "vad_max_speech_duration_s", "min_speech_duration_ms",
            "patience", "hallucination_silence_threshold", "tail_pad_ms",
        ):
            if vad_field in settings:
                result[vad_field] = settings[vad_field]
        for extra_text_field in ("initial_prompt", "hotwords"):
            if extra_text_field in settings:
                result[extra_text_field] = str(settings.get(extra_text_field) or "")
        if "speech_filter" in settings:
            result["speech_filter"] = bool(settings["speech_filter"])
        if "condition_on_previous_text" in settings and settings["condition_on_previous_text"] is not None:
            result["condition_on_previous_text"] = bool(settings["condition_on_previous_text"])
        elif hasattr(defaults, "condition_on_previous_text"):
            result["condition_on_previous_text"] = bool(getattr(defaults, "condition_on_previous_text", True))
        if result.get("vad_preset") is not None:
            from core.project.project_state import normalize_vad_preset_key
            result["vad_preset"] = normalize_vad_preset_key(str(result["vad_preset"]))
        if result.get("vad_threshold") is not None:
            result["vad_threshold"] = float(result["vad_threshold"])
        if result.get("vad_speech_pad_ms") is not None:
            result["vad_speech_pad_ms"] = int(result["vad_speech_pad_ms"])
        if result.get("vad_max_speech_duration_s") is not None:
            result["vad_max_speech_duration_s"] = float(result["vad_max_speech_duration_s"])
        if result.get("min_speech_duration_ms") is not None:
            result["min_speech_duration_ms"] = int(result["min_speech_duration_ms"])
        if result.get("patience") is not None:
            result["patience"] = float(result["patience"])
        if result.get("hallucination_silence_threshold") is not None:
            result["hallucination_silence_threshold"] = float(result["hallucination_silence_threshold"])
        if result.get("tail_pad_ms") is not None:
            result["tail_pad_ms"] = max(0, int(result["tail_pad_ms"]))
        result["min_silence_ms"] = int(result["min_silence_ms"])
        result["overlap_gap_ms"] = int(result["overlap_gap_ms"])
        result["overlap_ms"] = int(result["overlap_ms"])
        result["max_window_ms"] = int(result["max_window_ms"])
        if result["use_vad"] is not True:
            raise ValueError("Timing generation requires VAD to be enabled.")
        if not 1 <= result["overlap_gap_ms"] <= 500:
            raise ValueError("Overlap gap must be between 1 and 500 ms.")
        if result["overlap_ms"] < 0 or result["max_window_ms"] <= 0:
            raise ValueError("Timing window settings are invalid.")
        return result

    @staticmethod
    def normalize_segments(
        segments: list[dict],
        *,
        fix_overlap: bool = True,
        overlap_gap_ms: int = 50,
        diagnostics: list | None = None,
    ) -> list[dict]:
        if not 1 <= int(overlap_gap_ms) <= 500:
            raise ValueError("Overlap gap must be between 1 and 500 ms.")
        normalized = [dict(segment) for segment in segments]
        if not fix_overlap:
            return normalized
        diagnostics = diagnostics if diagnostics is not None else []
        gap = int(overlap_gap_ms)
        for index in range(len(normalized) - 1):
            current = normalized[index]
            following = normalized[index + 1]
            desired_end = int(following["start_ms"]) - gap
            if int(current["end_ms"]) < desired_end:
                continue
            if desired_end > int(current["start_ms"]):
                current["end_ms"] = desired_end
            else:
                diagnostics.append({
                    "type": "UNRESOLVED_OVERLAP",
                    "index": index,
                    "next_index": index + 1,
                    "start_ms": int(current["start_ms"]),
                    "end_ms": int(current["end_ms"]),
                    "next_start_ms": int(following["start_ms"]),
                })
        return normalized

    def _validate_source_and_state(self):
        project = self.project_service.current_project
        if not project:
            raise ValueError("Không có dự án nào đang mở.")
        video_path = project.source.path
        if not os.path.exists(video_path):
            raise FileNotFoundError("Không tìm thấy video gốc.")
        current_fp = self.project_service._generate_fingerprint(video_path)
        if current_fp.fingerprint != project.source.fingerprint:
            raise ValueError("Video gốc đã bị thay đổi (Sai lệch mã Hash).")

    def _validate_checkpoint_identity(self, checkpoint: TimingCheckpoint):
        project = self.project_service.current_project
        if not project:
            raise ValueError("Không có dự án nào đang mở.")
        if checkpoint.project_id != project.project_id:
            raise ValueError("Checkpoint không thuộc về Dự án hiện tại.")
        if checkpoint.source_fingerprint != project.source.fingerprint:
            # Checkpoint thuộc dự án nhưng video đã được relink hoặc thay đổi vân tay:
            # Tự động đồng bộ vân tay để bảo toàn tiến trình Timing mà không làm gián đoạn người dùng.
            self.log_signal.emit(
                f"[Recovery] Vân tay video trong Checkpoint đã được tự động đồng bộ theo video hiện tại ({project.source.fingerprint[:12]}...)."
            )
            checkpoint.source_fingerprint = project.source.fingerprint
            self.project_service.save_timing_checkpoint(checkpoint)
        if checkpoint.timing_artifact_id and checkpoint.timing_artifact_id != project.state.timing.timing_artifact_id:
            if self.project_service.artifact_store.get(checkpoint.timing_artifact_id):
                project.state.timing.timing_artifact_id = checkpoint.timing_artifact_id
            else:
                raise ValueError("ID của Timing Artifact không khớp với Checkpoint.")

    def start_timing(self, batch_size: int, settings: dict, existing_segments: list | None = None):
        self._clear_timing_diagnostics()
        self._pending_draft_lines = None
        self._validate_source_and_state()
        project = self.project_service.current_project
        timing_state = project.state.timing
        settings = self._validate_settings(settings, timing_state)
        for name, value in settings.items():
            setattr(timing_state, name, value)

        normalized_segments = self._normalize_editor_segments(existing_segments) if existing_segments else []
        if normalized_segments:
            start_idx = len(normalized_segments) + 1
            start_ms = max(s["end_ms"] for s in normalized_segments)
            self._pending_draft_lines = self._build_draft_lines(normalized_segments)
            self.log_signal.emit(
                f"[Timing] Tiếp tục sau câu sub cuối cùng #{len(normalized_segments)} "
                f"(mốc {self._ms_to_time_str(start_ms)}) -> Bắt đầu câu #{start_idx}."
            )
        else:
            start_idx = 1
            start_ms = 0

        timing_state.batch_size = batch_size
        timing_state.next_segment_index = start_idx
        timing_state.completed_until = start_idx - 1
        timing_state.timing_artifact_id = None
        timing_state.checkpoint_id = None
        timing_state.status = "RUNNING"

        # [S7.1-FIX-05] Khởi tạo và Lưu ngay Active Batch trước khi Worker chạy
        new_batch = TimingBatch(
            batch_id=f"batch_{uuid.uuid4().hex[:8]}",
            start_segment=start_idx,
            end_segment=start_idx + batch_size - 1,
            start_ms=start_ms,
            end_ms=start_ms,
            status=BatchStatus.RUNNING.value,
            revision=1,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        self.active_batch_data = asdict(new_batch)

        checkpoint_settings = {
            k: v for k, v in settings.items() if k in TimingCheckpoint.__dataclass_fields__
        }
        checkpoint = TimingCheckpoint(
            project_id=project.project_id,
            source_fingerprint=project.source.fingerprint,
            timing_artifact_id="",
            timing_revision=1,
            batch_size=batch_size,
            active_batch=self.active_batch_data,
            next_segment_index=start_idx,
            last_completed_end_ms=start_ms,
            completed_batches=[],
            **checkpoint_settings,
        )
        self.project_service.save_timing_checkpoint(checkpoint)

        self.project_service.mark_dirty()
        init_prefix = f"Đang tiếp tục từ câu {start_idx}" if start_idx > 1 else "Đang khởi tạo Timing"
        self.state_changed_signal.emit(
            "RUNNING",
            f"{init_prefix} · Đã gen 0/{batch_size} câu (0%)",
        )
        self._execute_run(start_ms=start_ms, target_count=batch_size, settings=settings)

    def continue_timing(
        self,
        batch_size: int,
        settings: dict,
        existing_segments: list | None = None,
        current_index: int | None = None,
    ):
        self._clear_timing_diagnostics()
        self._pending_draft_lines = None
        self._validate_source_and_state()
        project = self.project_service.current_project
        timing_state = project.state.timing
        checkpoint = self.project_service.load_timing_checkpoint()
        if not checkpoint:
            raise ValueError("Không tìm thấy dữ liệu Checkpoint.")

        caller_settings = settings or {}
        default_state = TimingState()
        settings = self._settings_from_checkpoint(checkpoint)
        override_keys = (
            "language",
            "music_mode",
            "specialized_model",
            "vad_preset",
            "vad_threshold",
            "vad_speech_pad_ms",
            "vad_max_speech_duration_s",
            "min_speech_duration_ms",
            "condition_on_previous_text",
        )
        for key in override_keys:
            if key in caller_settings and caller_settings[key] is not None:
                settings[key] = caller_settings[key]
            else:
                state_val = getattr(timing_state, key, None)
                default_val = getattr(default_state, key, None)
                if state_val not in (None, "Auto Detect", "") and state_val != default_val:
                    settings[key] = state_val
        if (
            caller_settings.get("vad_preset") not in (None, "", "standard")
            or getattr(timing_state, "vad_preset", "standard") not in (None, "", "standard")
            or (
                caller_settings.get("min_silence_ms") is not None
                and int(caller_settings["min_silence_ms"]) != default_state.min_silence_ms
            )
        ):
            if "min_silence_ms" in caller_settings and (
                caller_settings.get("vad_preset") not in (None, "", "standard")
                or int(caller_settings["min_silence_ms"]) != default_state.min_silence_ms
            ):
                settings["min_silence_ms"] = int(caller_settings["min_silence_ms"])
            elif getattr(timing_state, "min_silence_ms", 500) != default_state.min_silence_ms:
                settings["min_silence_ms"] = int(timing_state.min_silence_ms)
        settings = self._validate_settings(settings)

        if checkpoint.active_batch:
            batch_size = checkpoint.batch_size
        timing_state.batch_size = batch_size
            
        self._validate_checkpoint_identity(checkpoint)
            
        artifact = self.project_service.artifact_store.get(checkpoint.timing_artifact_id)
        recovered_artifact = None
        if artifact and artifact.artifact_type != ArtifactType.TIMING:
            timing_dir = os.path.join(self.project_service.project_dir, "artifacts", "timing")
            timing_files = [
                os.path.join(timing_dir, name) for name in os.listdir(timing_dir)
                if name.lower().endswith(".srt")
            ] if os.path.isdir(timing_dir) else []
            if len(timing_files) != 1:
                raise ValueError("ID Artifact Timing bị trùng và không xác định được file Timing SRT.")
            timing_id = str(uuid.uuid4())
            recovered_artifact = Artifact(
                artifact_id=timing_id, artifact_type=ArtifactType.TIMING,
                path=timing_files[0], created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(), source_project_id=project.project_id,
                status=ArtifactStatus.READY, revision=checkpoint.timing_revision,
                metadata={},
            )
            artifact = recovered_artifact
        if not artifact or not os.path.exists(artifact.path):
            raise ValueError("Không tìm thấy file Artifact Timing.")
        if existing_segments is not None:
            draft_count = len(self._parse_draft_segments(artifact.path))
            if len(existing_segments) > draft_count:
                raise ValueError("Editor có nhiều câu hơn Timing SRT; cần đồng bộ phụ đề trước khi Resume.")
        if recovered_artifact:
            # A legacy manifest can contain the same ID for Timing and Subtitle.
            self.project_service.artifact_store.register(recovered_artifact)
            checkpoint.timing_artifact_id = recovered_artifact.artifact_id
            timing_state.timing_artifact_id = recovered_artifact.artifact_id
            
        # Tự động phục hồi nếu phát hiện Crash giữa giao dịch file hoặc có chỉnh sửa sau khi tạo draft
        if artifact.revision != checkpoint.timing_revision:
            if artifact.revision > checkpoint.timing_revision:
                self.log_signal.emit(
                    f"[Recovery] Phát hiện chỉnh sửa phụ đề (Artifact Rev {artifact.revision} > Checkpoint Rev {checkpoint.timing_revision}). Đang tự động đồng bộ..."
                )
                checkpoint.timing_revision = artifact.revision
                self.project_service.save_timing_checkpoint(checkpoint)
            elif checkpoint.timing_revision == artifact.revision + 1:
                self.log_signal.emit("[Recovery] Phát hiện Crash khi đang Commit. Đang đồng bộ lại Revision...")
                artifact.revision = checkpoint.timing_revision
            else:
                raise ValueError(f"Dữ liệu Checkpoint không hợp lệ (Rev {checkpoint.timing_revision} vs {artifact.revision}).")

        for key in (*override_keys, "min_silence_ms"):
            if key in settings:
                setattr(checkpoint, key, settings[key])
                if hasattr(timing_state, key) and (
                    key != "min_silence_ms" or settings.get("vad_preset") not in (None, "", "standard")
                ):
                    setattr(timing_state, key, settings[key])

        # Đồng bộ câu bắt đầu và mốc thời gian theo phụ đề hiện tại / câu sub đang chọn
        start_idx, start_ms = self._reconcile_timing_checkpoint_with_subtitles(
            checkpoint,
            existing_segments=existing_segments,
            current_index=current_index,
            artifact_path=artifact.path if artifact else None,
        )
        
        # [S7.1-FIX-05] Cập nhật Checkpoint với Batch tiếp theo trước khi chạy
        new_batch = TimingBatch(
            batch_id=f"batch_{uuid.uuid4().hex[:8]}",
            start_segment=start_idx,
            end_segment=start_idx + batch_size - 1,
            start_ms=start_ms,
            end_ms=0,
            status=BatchStatus.RUNNING.value,
            revision=artifact.revision,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        self.active_batch_data = asdict(new_batch)
        
        checkpoint.active_batch = self.active_batch_data
        checkpoint.batch_size = batch_size
        self.project_service.save_timing_checkpoint(checkpoint)

        timing_state.status = "RUNNING"
        self.project_service.mark_dirty()
        
        self.state_changed_signal.emit(
            "RUNNING",
            f"Đang tiếp tục từ câu {start_idx} · Đã gen 0/{batch_size} câu (0%)",
        )
        self._execute_run(start_ms=start_ms, target_count=batch_size, settings=settings)

    # [S7.1-FIX-04] Dọn dẹp chỉ giữ một hàm Retry duy nhất
    def retry_timing(self, batch_size: int, settings: dict):
        self._clear_timing_diagnostics()
        self._validate_source_and_state()
        checkpoint = self.project_service.load_timing_checkpoint()
        
        if not checkpoint or not checkpoint.active_batch:
            raise ValueError("Không có Batch nào đang ở trạng thái lỗi để Retry.")
            
        self._validate_checkpoint_identity(checkpoint)
        settings = self._settings_from_checkpoint(checkpoint)
        
        # Cho phép sửa Batch Size khi Retry
        checkpoint.active_batch["status"] = "RUNNING"
        checkpoint.active_batch["end_segment"] = checkpoint.active_batch["start_segment"] + batch_size - 1
        self.active_batch_data = checkpoint.active_batch
        
        self.project_service.save_timing_checkpoint(checkpoint)
        
        project = self.project_service.current_project
        project.state.timing.batch_size = batch_size
        project.state.timing.status = "RUNNING"
        
        self.state_changed_signal.emit(
            "RUNNING",
            f"Đang thử lại từ câu {checkpoint.active_batch['start_segment']} · Đã gen 0/{batch_size} câu (0%)",
        )
        self._execute_run(start_ms=checkpoint.active_batch["start_ms"], target_count=batch_size, settings=settings)

    @property
    def is_running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def cancel_timing(self):
        self._clear_timing_diagnostics()
        self._pending_terminal_state = None
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            project = self.project_service.current_project
            if project:
                project.state.timing.status = "IDLE"
                
                # Đánh dấu Cancelled vào checkpoint
                checkpoint = self.project_service.load_timing_checkpoint()
                if checkpoint and checkpoint.active_batch:
                    checkpoint.active_batch["status"] = "CANCELLED"
                    self.project_service.save_timing_checkpoint(checkpoint)
                    
                self.project_service.mark_dirty()

            worker = self.worker

            def _on_worker_finished():
                try:
                    worker.finished.disconnect(_on_worker_finished)
                except (RuntimeError, TypeError):
                    pass
                if self.worker is worker:
                    self.worker = None
                self.state_changed_signal.emit("READY", "Đã hủy tiến trình.")

            if not worker.isRunning():
                self.worker = None
                self.state_changed_signal.emit("READY", "Đã hủy tiến trình.")
            else:
                worker.finished.connect(_on_worker_finished)
        else:
            self.worker = None
            self.state_changed_signal.emit("READY", "Đã hủy tiến trình.")

    def _emit_terminal_state(self, status: str, message: str) -> None:
        # Delay READY/COMPLETED/FAILED until QThread.finished so UI unlock checks see is_running == False.
        worker = self.worker
        if worker and worker.isRunning():
            self._pending_terminal_state = (status, message)
            if hasattr(worker, "finished") and self._connected_finished_worker is not worker:
                worker.finished.connect(self._on_worker_qthread_finished)
                self._connected_finished_worker = worker
            return
        self._pending_terminal_state = None
        if worker is not None:
            self.worker = None
        self.state_changed_signal.emit(status, message)

    @Slot()
    def _on_worker_qthread_finished(self) -> None:
        worker = self.sender()
        if worker is not None and worker is not self.worker:
            return
        self.worker = None
        self._connected_finished_worker = None
        pending = self._pending_terminal_state
        self._pending_terminal_state = None
        if pending is not None:
            self.state_changed_signal.emit(pending[0], pending[1])

    def _execute_run(self, start_ms: int, target_count: int, settings: dict):
        project = self.project_service.current_project
        settings = self._validate_settings(settings, project.state.timing)
        self._current_settings = settings
        self._pending_terminal_state = None
        active_batch = getattr(self, "active_batch_data", None)
        start_segment_index = (
            active_batch.get("start_segment")
            if isinstance(active_batch, dict)
            else None
        )
        if not isinstance(start_segment_index, int):
            raw_next_idx = getattr(project.state.timing, "next_segment_index", 1)
            start_segment_index = raw_next_idx if isinstance(raw_next_idx, int) else 1
        start_segment_index = max(1, int(start_segment_index))
        from core.services.model_manager import ModelManager

        effective_model = str(settings.get("specialized_model") or "").strip() or settings["model_size"]
        spec_info = ModelManager.get_specialized_info(effective_model)
        eff_lang = settings.get("language", None) or (spec_info["language"] if spec_info else None)
        req_initial_prompt = ""
        req_hotwords = ""

        request = TimingRunRequest(
            video_path=project.source.path,
            start_ms=start_ms,
            target_segment_count=target_count,
            overlap_ms=settings["overlap_ms"],
            max_window_ms=settings["max_window_ms"],
            model_size=effective_model,
            compute_type=settings["compute_type"],
            use_vad=settings["use_vad"],
            min_silence_ms=settings["min_silence_ms"],
            fix_overlap=settings["fix_overlap"],
            overlap_gap_ms=settings["overlap_gap_ms"],
            music_mode=settings.get("music_mode", False),
            language=eff_lang,
            vad_preset=settings.get("vad_preset", None),
            vad_threshold=settings.get("vad_threshold", None),
            vad_speech_pad_ms=settings.get("vad_speech_pad_ms", None),
            vad_max_speech_duration_s=settings.get("vad_max_speech_duration_s", None),
            min_speech_duration_ms=settings.get("min_speech_duration_ms", None) or 120,
            start_segment_index=start_segment_index,
            speech_filter=bool(settings.get("speech_filter", True)),
            initial_prompt=req_initial_prompt,
            hotwords=req_hotwords,
            patience=settings.get("patience", 1.5),
            hallucination_silence_threshold=settings.get("hallucination_silence_threshold", 2.5),
            tail_pad_ms=int(settings.get("tail_pad_ms", 180) if settings.get("tail_pad_ms") is not None else 180),
            condition_on_previous_text=bool(settings.get("condition_on_previous_text", True)),
        )
        self.worker = TimingBatchWorker(request)
        self.worker.progress_signal.connect(self.progress_signal.emit)
        self.worker.log_signal.connect(self.log_signal.emit)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.error_signal.connect(self._on_worker_error)
        self.worker.effective_compute_signal.connect(
            lambda effective: self.effective_compute_signal.emit(
                request.compute_type, effective
            )
        )
        if hasattr(self.worker, "finished"):
            self.worker.finished.connect(self._on_worker_qthread_finished)
            self._connected_finished_worker = self.worker
        self.worker.start()

    def _on_worker_error(self, err: str):
        self._clear_timing_diagnostics()
        if hasattr(self, 'active_batch_data') and self.active_batch_data:
            self.active_batch_data["status"] = "FAILED"
            checkpoint = self.project_service.load_timing_checkpoint()
            if checkpoint:
                checkpoint.active_batch = self.active_batch_data
                self.project_service.save_timing_checkpoint(checkpoint)
                
        project = self.project_service.current_project
        if project:
            project.state.timing.status = "FAILED"
            self.project_service.save_project()
        self.error_signal.emit(err)
        self._emit_terminal_state("FAILED", "Lỗi xử lý AI. Vui lòng Retry Batch.")

    def _on_worker_finished(self, new_segments: list, is_end_of_source: bool):
        project = self.project_service.current_project
        timing_state = project.state.timing
        settings = self._current_settings or self._validate_settings({}, timing_state)
        self._last_timing_diagnostics = []
        new_segments = self.normalize_segments(
            new_segments,
            fix_overlap=settings["fix_overlap"],
            overlap_gap_ms=settings["overlap_gap_ms"],
            diagnostics=self._last_timing_diagnostics,
        )
        for diagnostic in self._last_timing_diagnostics:
            self.log_signal.emit(
                "[Timing] Unresolved subtitle overlap "
                f"between rows {diagnostic['index'] + 1} and "
                f"{diagnostic['next_index'] + 1}; timestamps preserved."
            )

        # A first Timing batch that finds no speech must not create an empty
        # artifact and advertise it as completed. That state makes Segment
        # mode fail later and leaves the Editor empty without an explanation.
        if not new_segments and not timing_state.timing_artifact_id and not self._pending_draft_lines:
            timing_state.status = "FAILED"
            project.state.timing_status = "EMPTY"
            checkpoint = self.project_service.load_timing_checkpoint()
            if checkpoint and checkpoint.active_batch:
                checkpoint.active_batch["status"] = "FAILED"
                self.project_service.save_timing_checkpoint(checkpoint)
            self.project_service.save_project()
            message = (
                "VAD không tìm thấy đoạn thoại sau 2 lần phân tích. "
                "Mở Live Log để xem thông tin FFmpeg, thời lượng speech và threshold."
            )
            self.error_signal.emit(message)
            self._emit_terminal_state("FAILED", message)
            return

        if not new_segments and not is_end_of_source:
            self._pending_draft_lines = None
            self._emit_terminal_state("READY", "Không có dữ liệu mới.")
            return

        existing_lines = []
        artifact_path = ""
        current_revision = 0
        
        if timing_state.timing_artifact_id:
            old_art = self.project_service.artifact_store.get(timing_state.timing_artifact_id)
            if old_art and os.path.exists(old_art.path):
                artifact_path = old_art.path
                current_revision = old_art.revision
                existing_lines = self._read_draft_lines(artifact_path)

        if self._pending_draft_lines is not None:
            existing_lines = list(self._pending_draft_lines)

        if not artifact_path:
            safe_name = "".join(c if c.isalnum() else "_" for c in project.name)
            artifacts_dir = os.path.join(self.project_service.project_dir, "artifacts", "timing")
            os.makedirs(artifacts_dir, exist_ok=True)
            artifact_path = os.path.join(artifacts_dir, f"{safe_name}_timing.srt")

        start_index = timing_state.next_segment_index
        checkpoint = self.project_service.load_timing_checkpoint()
        last_end_ms = checkpoint.last_completed_end_ms if checkpoint else 0

        if self.history_service is not None and new_segments:
            from core.export.subtitle_parser import parse_srt_content
            history_before = parse_srt_content("\n".join(existing_lines))

        if existing_lines and existing_lines[-1].strip() != "":
            existing_lines.append("")

        added_count = 0
        for seg in new_segments:
            stt = start_index + added_count
            start_time_str = self._ms_to_time_str(seg["start_ms"])
            end_time_str = self._ms_to_time_str(seg["end_ms"])
            
            existing_lines.append(f"{stt}")
            existing_lines.append(f"{start_time_str} --> {end_time_str}")
            existing_lines.append("[ Chưa có nội dung ]")
            existing_lines.append("")
            
            last_end_ms = seg["end_ms"]
            added_count += 1

        if added_count == 0 and not is_end_of_source:
            self._emit_terminal_state("READY", "Sẵn sàng.")
            return

        new_revision = current_revision + 1
        
        if hasattr(self, 'active_batch_data') and self.active_batch_data:
            self.active_batch_data["status"] = "COMPLETED"
            self.active_batch_data["end_ms"] = last_end_ms
            
        checkpoint_settings = {
            k: v for k, v in settings.items() if k in TimingCheckpoint.__dataclass_fields__
        }
        new_checkpoint = TimingCheckpoint(
            project_id=project.project_id,
            source_fingerprint=project.source.fingerprint,
            timing_artifact_id=timing_state.timing_artifact_id or "WILL_BE_SET",
            timing_revision=new_revision,
            batch_size=timing_state.batch_size,
            active_batch=None, # Xóa active batch vì đã hoàn tất an toàn
            next_segment_index=start_index + added_count,
            last_completed_end_ms=last_end_ms,
            completed_batches=checkpoint.completed_batches if checkpoint else [],
            updated_at=datetime.now().isoformat(),
            **checkpoint_settings,
        )
        if added_count > 0 and hasattr(self, 'active_batch_data'):
            new_checkpoint.completed_batches.append(self.active_batch_data["batch_id"])

        # Cập nhật Memory State
        artifact_metadata = {
            "batch_size": timing_state.batch_size,
            "completed_until": start_index + added_count - 1,
            "last_completed_end_ms": last_end_ms
        }

        if not timing_state.timing_artifact_id:
            new_art_id = str(uuid.uuid4())
            art = Artifact(
                artifact_id=new_art_id, artifact_type=ArtifactType.TIMING, path=artifact_path,
                created_at=datetime.now().isoformat(), updated_at=datetime.now().isoformat(),
                source_project_id=project.project_id, status=ArtifactStatus.READY,
                revision=new_revision, metadata=artifact_metadata
            )
            self.project_service.artifact_store.register(art)
            timing_state.timing_artifact_id = new_art_id
            new_checkpoint.timing_artifact_id = new_art_id
        else:
            art = self.project_service.artifact_store.get(timing_state.timing_artifact_id)
            art.revision = new_revision
            art.metadata.update(artifact_metadata)
            
        project.state.active_artifact_id = timing_state.timing_artifact_id
        timing_state.completed_until = start_index + added_count - 1
        timing_state.next_segment_index = start_index + added_count
        timing_state.checkpoint_id = "checkpoint.json"
        
        if is_end_of_source:
            timing_state.status = "COMPLETED"
            project.state.timing_status = "READY"
        else:
            timing_state.status = "IDLE"
            project.state.timing_status = "DRAFT"

        # [S7.1-FIX-06] THỰC THI ATOMIC MULTI-FILE TRANSACTION CỰC KỲ AN TOÀN
        try:
            srt_content = "\n".join(existing_lines)
            self._commit_transaction(artifact_path, srt_content, new_checkpoint)
        except Exception as e:
            self.error_signal.emit(f"Lỗi khi Commit Batch (Disk Error): {str(e)}")
            self._emit_terminal_state("FAILED", "Lỗi lưu đĩa. Dữ liệu cũ vẫn an toàn.")
            return

        self._pending_draft_lines = None
        if added_count > 0:
            if self.history_service is not None:
                try:
                    self.history_service.create_history_checkpoint(history_before, is_initial=True)
                    self.history_service.create_history_checkpoint(
                        parse_srt_content(srt_content), is_timing=True
                    )
                except (OSError, ValueError, TypeError) as exc:
                    self.error_signal.emit(f"Timing đã lưu nhưng không ghi được Generation History: {exc}")
            self.batch_completed_signal.emit(added_count, timing_state.batch_size)
        if is_end_of_source:
            self.timing_finished_signal.emit()
            self._emit_terminal_state("COMPLETED", "Đã hoàn tất Timing toàn bộ Video!")
        else:
            self._emit_terminal_state("READY", f"Đã lưu Checkpoint (Đến câu {timing_state.completed_until}).")

    def _commit_transaction(self, srt_path, srt_content, checkpoint_obj):
        """[S7.1-FIX-06] Giao dịch 2 pha (Two-Phase Commit) cho 4 file cốt lõi"""
        project = self.project_service.current_project
        proj_dir = self.project_service.project_dir

        chk_path = os.path.join(proj_dir, "artifacts", "timing", "checkpoint.json")
        man_path = os.path.join(proj_dir, "artifacts", "manifest.json")
        state_path = os.path.join(proj_dir, "state.json")

        chk_data = json.dumps(asdict(checkpoint_obj), ensure_ascii=False, indent=2)
        man_data = json.dumps(self.project_service.artifact_store.to_dict(proj_dir), ensure_ascii=False, indent=2)
        state_dict = ProjectService.serialize_project_state(project.state)
        state_data = json.dumps(state_dict, ensure_ascii=False, indent=2)

        # Lưu trạng thái và artifacts nguyên tử (Atomic Write) bảo đảm an toàn dữ liệu
        from core.utils.file_utils import atomic_save_text
        atomic_save_text(srt_path, srt_content)
        atomic_save_text(chk_path, chk_data)
        atomic_save_text(man_path, man_data)
        atomic_save_text(state_path, state_data)

        project.state.dirty = False

    def _write_tmp_fsync(self, path, content):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

    def _read_draft_lines(self, path):
        if not os.path.exists(path): return []
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().splitlines()

    def _ms_to_time_str(self, ms: int) -> str:
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def _time_str_to_ms(self, time_str: str) -> int:
        clean = time_str.strip().replace(",", ".")
        parts = clean.split(":")
        try:
            if len(parts) == 3:
                h = int(parts[0])
                m = int(parts[1])
                sec_parts = parts[2].split(".")
                sec = int(sec_parts[0])
                ms = int(sec_parts[1].ljust(3, "0")[:3]) if len(sec_parts) > 1 else 0
                return h * 3600000 + m * 60000 + sec * 1000 + ms
            elif len(parts) == 2:
                m = int(parts[0])
                sec_parts = parts[1].split(".")
                sec = int(sec_parts[0])
                ms = int(sec_parts[1].ljust(3, "0")[:3]) if len(sec_parts) > 1 else 0
                return m * 60000 + sec * 1000 + ms
        except Exception:
            pass
        return 0

    def _parse_draft_segments(self, path: str) -> list[dict]:
        """Đọc và trích xuất danh sách segment (start_ms, end_ms) từ file SRT draft."""
        if not path or not os.path.exists(path):
            return []
        segments = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "-->" in line:
                        parts = line.split("-->", 1)
                        try:
                            s_ms = self._time_str_to_ms(parts[0].strip())
                            e_ms = self._time_str_to_ms(parts[1].strip())
                            if e_ms > s_ms:
                                segments.append({"start_ms": s_ms, "end_ms": e_ms})
                        except Exception:
                            continue
        except Exception as e:
            print(f"[TimingBatchService] Warning: Không thể đọc file draft SRT: {e}")
        return segments

    def _normalize_editor_segments(self, existing_segments: list) -> list[dict]:
        """Validate and normalize editor segment start/end times to millisecond ints."""
        segments = []
        for s in existing_segments:
            start_ms = s.get("start_ms")
            end_ms = s.get("end_ms")
            if start_ms is None and "start" in s:
                start_ms = s["start"] if isinstance(s["start"], (int, float)) else self._time_str_to_ms(str(s["start"]))
            if end_ms is None and "end" in s:
                end_ms = s["end"] if isinstance(s["end"], (int, float)) else self._time_str_to_ms(str(s["end"]))
            if start_ms is None or end_ms is None or start_ms < 0 or end_ms <= start_ms:
                raise ValueError("Timing trong Editor không hợp lệ; chưa thể tạo tiếp Draft.")
            segments.append({**s, "start_ms": int(start_ms), "end_ms": int(end_ms)})
        return segments

    def _build_draft_lines(self, segments: list[dict]) -> list[str]:
        """Serialize normalized segments into SRT draft lines."""
        lines = []
        for index, segment in enumerate(segments, 1):
            lines.extend([
                str(index),
                f"{self._ms_to_time_str(segment['start_ms'])} --> {self._ms_to_time_str(segment['end_ms'])}",
                segment.get("text", ""),
                "",
            ])
        return lines

    def _reconcile_timing_checkpoint_with_subtitles(
        self,
        checkpoint: TimingCheckpoint,
        existing_segments: list | None = None,
        current_index: int | None = None,
        artifact_path: str | None = None,
    ) -> tuple[int, int]:
        """
        Đồng bộ next_segment_index và last_completed_end_ms với phụ đề thực tế và vị trí câu sub hiện tại.
        Trả về (start_idx, start_ms) chính xác.
        """
        segments = []
        if existing_segments is not None:
            segments = self._normalize_editor_segments(existing_segments)
        elif artifact_path and os.path.exists(artifact_path):
            segments = self._parse_draft_segments(artifact_path)

        if segments or existing_segments is not None:
            # 1. Nếu người dùng đang chọn một câu sub cụ thể (current_index)
            if not segments:
                target_start_ms = 0
                target_next_index = 1
            elif current_index is not None and 0 <= current_index < len(segments):
                cur_seg = segments[current_index]
                target_start_ms = cur_seg["end_ms"]
                target_next_index = current_index + 2
                self.log_signal.emit(
                    f"[Timing] Tiếp tục sau câu sub hiện tại #{current_index + 1} "
                    f"(mốc {self._ms_to_time_str(target_start_ms)}) -> Bắt đầu câu #{target_next_index}."
                )
            else:
                # 2. Mặc định tiếp tục sau câu sub cuối cùng hiện có
                actual_count = len(segments)
                max_end_ms = max(s["end_ms"] for s in segments)
                target_next_index = actual_count + 1
                target_start_ms = max_end_ms
                self.log_signal.emit(
                    f"[Timing] Tiếp tục sau câu sub cuối cùng #{actual_count} "
                    f"(mốc {self._ms_to_time_str(max_end_ms)}) -> Bắt đầu câu #{target_next_index}."
                )

            checkpoint.next_segment_index = target_next_index
            checkpoint.last_completed_end_ms = target_start_ms
            checkpoint.completed_until = target_next_index - 1
            self.project_service.save_timing_checkpoint(checkpoint)

            project = self.project_service.current_project
            if project and hasattr(project, "state") and hasattr(project.state, "timing"):
                project.state.timing.next_segment_index = target_next_index
                project.state.timing.completed_until = target_next_index - 1

        if existing_segments is not None:
            # Commit the edited prefix with new rows so deleted rows stay deleted.
            self._pending_draft_lines = self._build_draft_lines(segments)

        return checkpoint.next_segment_index, checkpoint.last_completed_end_ms
