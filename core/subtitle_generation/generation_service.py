from core.subtitle_generation.generation_error import GenerationError, GenerationErrorCode
import os
import re
import uuid
import copy
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from core.subtitle_generation.boundary_reconciler import BoundaryReconciler
from core.subtitle_generation.faster_whisper_service import FasterWhisperService
from core.subtitle_generation.generation_checkpoint_manager import (
    SubtitleGenerationCheckpointManager,
)
from core.subtitle_generation.generation_planner import SubtitleGenerationPlanner
from core.subtitle_generation.generation_validator import SubtitleGenerationValidator
from core.subtitle_generation.subtitle_artifact_service import SubtitleArtifactService
from core.subtitle_generation.subtitle_generation_batch import SubtitleGenerationBatch
from core.subtitle_generation.subtitle_generation_checkpoint import (
    SubtitleGenerationCheckpoint,
)
from core.subtitle_generation.subtitle_generation_request import (
    SubtitleGenerationRequest,
)
from core.subtitle_generation.generation_range import (
    GenerationRange,
    GenerationRangeStatus,
    validate_generation_range,
)
from core.subtitle_generation.generation_timing_reconciler import (
    ReconciliationResult,
    ReconciliationStatus,
    reconcile_generated_timing,
)
from core.subtitle_generation.subtitle_generation_result import (
    SubtitleGenerationResult,
    WhisperSegmentResult,
)
from core.transcription.prompt_context_builder import (
    CompiledPromptContext,
    PromptContextBuilder,
)
from core.transcription.token_counter import ApproximateTokenCounter
from core.project.transcription_context import TranscriptionContext
from workers.subtitle_generation_worker import SubtitleGenerationWorker


class SubtitleGenerationService(QObject):
    """Main-thread orchestrator for one-at-a-time, resumable ASR batches."""

    history_changed = Signal()

    def __init__(self, whisper_service: FasterWhisperService, project_service):
        super().__init__()
        self.whisper_service = whisper_service
        self.project_service = project_service
        self.prompt_context_builder = PromptContextBuilder(ApproximateTokenCounter())
        self.checkpoint_manager = SubtitleGenerationCheckpointManager(project_service)
        self.artifact_service = SubtitleArtifactService(project_service)
        self.current_worker: Optional[SubtitleGenerationWorker] = None
        self.current_request: Optional[SubtitleGenerationRequest] = None
        self.current_batches: List[SubtitleGenerationBatch] = []
        self.current_checkpoint: Optional[SubtitleGenerationCheckpoint] = None
        self.current_timing_ranges = []
        self.all_checkpoints = []
        self._is_cancelled = False
        self._pending_dispatch = False
        self._pending_finish = False
        self._pending_error: Optional[str] = None
        self._terminal_notified = False
        self._is_range_generation = False
        self._range_committed = False
        self._range_artifact_id = None
        self._range_state_artifact_id = None
        self._range_artifact_revision = 0
        self._range_artifact_hash = ""
        self._range_duration_ms = 0
        self._range_editor_segments = None
        self.last_range_reconciliation = None
        self.range_segments_provider = None
        self._generated_segments_count: int = 0

        # Optional UI callbacks kept decoupled from the service.
        self.on_progress: Optional[Callable[[int, str], None]] = None
        self.on_batch_complete: Optional[Callable[[SubtitleGenerationBatch, list], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_finish: Optional[Callable[[], None]] = None


    @property
    def checkpoint_history(self):
        project = self.project_service.current_project
        source_id = getattr(project.state, "active_subtitle_source_id", "default") if project else "default"
        return [cp for cp in getattr(self, "all_checkpoints", []) if getattr(cp, "checkpoint_type", "") != "INITIAL" and getattr(cp, "source_id", "default") == source_id]

    @property
    def initial_state(self):
        project = self.project_service.current_project
        source_id = getattr(project.state, "active_subtitle_source_id", "default") if project else "default"
        for cp in getattr(self, "all_checkpoints", []):
            if getattr(cp, "checkpoint_type", "") == "INITIAL" and getattr(cp, "source_id", "default") == source_id:
                return cp
        return None

    def compile_prompt_context(
        self, context: TranscriptionContext
    ) -> CompiledPromptContext:
        return self.prompt_context_builder.build(context)

    @property
    def is_running(self) -> bool:
        """Whether the worker thread is still alive, including cancellation."""
        return bool(self.current_worker and self.current_worker.isRunning())

    def start_generation(
        self, request: SubtitleGenerationRequest, video_duration_ms: int,
        *, existing_segments=None, conflict_strategy=None
    ) -> None:
        from core.subtitle_generation.range_validation import RangeValidator, ConflictStrategy
        self._ensure_idle()
        self._range_conflict_strategy = conflict_strategy

        project = self._require_project()
        self._validate_request_source(request, project)
        if video_duration_ms <= 0:
            raise ValueError("Video duration must be positive.")

        if request.range_start_ms is not None and request.range_end_ms is not None:
            # Phase 2: Range Validation
            result = RangeValidator.preview_range(
                request.range_start_ms, request.range_end_ms, video_duration_ms, existing_segments or [], False
            )
            if not result.is_valid:
                raise GenerationError(GenerationErrorCode.VALIDATION_FAILED, f"{result.message}")
            if result.overlapping_count > 0 and self._range_conflict_strategy == ConflictStrategy.CANCEL:
                raise GenerationError(GenerationErrorCode.RANGE_CONFLICT, f"Range overlaps with {result.overlapping_count} existing subtitles.")
                
        if existing_segments is not None:
            self.create_history_checkpoint(existing_segments, is_initial=True)
        else:
            # We can't snapshot without segments. Maybe load from artifact?
            pass

        if request.range_start_ms is not None or request.range_end_ms is not None:
            self._start_range_generation(
                request, video_duration_ms, existing_segments
            )
            return

        self._is_range_generation = False

        artifact = self.artifact_service.get_or_create_artifact()
        if artifact is None:
            raise RuntimeError("Unable to create subtitle artifact.")

        segment_ranges = None
        timing_segment_cursor = 0
        timing_segment_count = 0
        if request.batch_mode == "segments":
            all_timing_ranges = self._load_timing_segment_ranges(
                project, existing_segments=existing_segments
            )
            # Bảo toàn toàn bộ các mốc Timing Draft / thủ công đã có trước khi chọn slot trống
            self._ensure_timing_rows(
                artifact, all_timing_ranges, existing_segments=existing_segments
            )
            artifact_rows = self.artifact_service.load_data(artifact.path).get("segments", [])
            rows_by_key = {
                (int(r.get("start_ms", -1)), int(r.get("end_ms", -1))): r
                for r in artifact_rows
            }
            unfilled_indices = [
                idx
                for idx, rng in enumerate(all_timing_ranges)
                if (
                    rows_by_key.get((int(rng[0]), int(rng[1]))) is None
                    or (
                        self._is_unfilled_timing_text(
                            rows_by_key[(int(rng[0]), int(rng[1]))].get("text")
                        )
                        and rows_by_key[(int(rng[0]), int(rng[1]))].get("status") != "generated"
                    )
                )
            ]
            selected_indices = unfilled_indices[:request.batch_size_value]
            if not selected_indices:
                raise ValueError("Tất cả Timing segments đã được điền phụ đề.")
            segment_ranges = [all_timing_ranges[i] for i in selected_indices]
            timing_segment_cursor = selected_indices[0]
            timing_segment_count = selected_indices[-1] - selected_indices[0] + 1
        self.current_timing_ranges = list(segment_ranges or [])

        self._is_cancelled = False
        self._pending_dispatch = False
        self._pending_finish = False
        self._pending_error = None
        self._terminal_notified = False
        self._generated_segments_count = 0
        self.current_request = request
        self.current_batches = SubtitleGenerationPlanner.create_plan(
            video_duration_ms,
            request.batch_mode,
            request.batch_size_value,
            request.overlap_ms,
            segment_ranges=segment_ranges,
        )
        artifact_hash = self.artifact_service.content_hash(artifact.path)
        self.current_checkpoint = SubtitleGenerationCheckpoint(
            project_id=project.project_id,
            source_fingerprint=project.source.fingerprint,
            request_id=request.request_id,
            subtitle_artifact_id=artifact.artifact_id,
            artifact_revision=artifact.revision,
            completed_batches=[],
            request_data=asdict(request),
            batches_data=[asdict(batch) for batch in self.current_batches],
            active_batch=None,
            next_start_ms=0,
            detected_language=None,
            updated_at=self._now(),
            artifact_content_hash=artifact_hash,
            timing_segment_cursor=timing_segment_cursor,
            timing_segment_count=timing_segment_count,
        )
        self.checkpoint_manager.save_checkpoint(self.current_checkpoint)
        self._dispatch_next_batch()

    def _start_range_generation(self, request, duration_ms, existing_segments):
        project = self._require_project()
        start_ms, end_ms = request.range_start_ms, request.range_end_ms
        artifact_id = getattr(project.state, "subtitle_artifact_id", None)
        artifact = self.project_service.artifact_store.get(artifact_id) if artifact_id else None
        artifact_segments = (
            self.artifact_service.load_data(artifact.path).get("segments", [])
            if artifact and os.path.exists(artifact.path)
            else []
        )
        from core.subtitle_generation.range_validation import ConflictStrategy

        validation = validate_generation_range(
            start_ms, end_ms, duration_ms,
            self._resolve_range_coverage(artifact_segments, existing_segments),
        )
        strategy = getattr(self, "_range_conflict_strategy", ConflictStrategy.CANCEL)
        if validation.status != GenerationRangeStatus.VALID:
            if not (
                validation.status == GenerationRangeStatus.OVERLAPS_SUBTITLE
                and strategy in (ConflictStrategy.REPLACE_OVERLAP, ConflictStrategy.FILL_GAPS_ONLY)
            ):
                raise ValueError(validation.status.value)

        self._is_range_generation = True
        self._range_committed = False
        self.last_range_reconciliation = None
        self._range_artifact_id = artifact.artifact_id if artifact else None
        self._range_state_artifact_id = artifact_id
        self._range_artifact_revision = artifact.revision if artifact else 0
        self._range_artifact_hash = (
            self.artifact_service.content_hash(artifact.path)
            if artifact and os.path.exists(artifact.path)
            else ""
        )
        self._range_editor_segments = existing_segments
        self._range_duration_ms = duration_ms
        self.current_timing_ranges = []
        self._is_cancelled = False
        self._pending_dispatch = False
        self._pending_finish = False
        self._pending_error = None
        self._terminal_notified = False
        self._generated_segments_count = 0
        self.current_request = request
        batch = SubtitleGenerationBatch(
            batch_id=str(uuid.uuid4()),
            start_ms=start_ms,
            end_ms=end_ms,
            status="PENDING",
            revision=0,
            created_at=self._now(),
            updated_at=self._now(),
        )
        self.current_batches = [batch]
        self.current_checkpoint = SubtitleGenerationCheckpoint(
            project_id=project.project_id,
            source_fingerprint=project.source.fingerprint,
            request_id=request.request_id,
            subtitle_artifact_id=artifact.artifact_id if artifact else (artifact_id or ""),
            artifact_revision=artifact.revision if artifact else 0,
            completed_batches=[],
            request_data=asdict(request),
            batches_data=[asdict(batch)],
            active_batch=None,
            next_start_ms=start_ms,
            detected_language=None,
            updated_at=self._now(),
            artifact_content_hash=self._range_artifact_hash,
        )
        self._dispatch_next_batch()

    def resume_generation(self) -> None:
        self._ensure_idle()
        self._is_range_generation = False
        project = self._require_project()
        checkpoint = self.checkpoint_manager.load_checkpoint()
        if checkpoint is None:
            raise ValueError("No subtitle-generation checkpoint found.")
        self._validate_checkpoint(checkpoint, project)

        artifact = self.artifact_service.get_or_create_artifact()
        if artifact is None or artifact.artifact_id != checkpoint.subtitle_artifact_id:
            raise ValueError("Subtitle artifact does not match checkpoint.")
        if artifact.revision != checkpoint.artifact_revision:
            raise GenerationError(GenerationErrorCode.STALE_SUBTITLE, "subtitle artifact changed externally.")
        if checkpoint.artifact_content_hash:
            current_hash = self.artifact_service.content_hash(artifact.path)
            if current_hash != checkpoint.artifact_content_hash:
                raise RuntimeError(
                    "STALE_SUBTITLE_FILE: subtitle artifact was edited externally."
                )

        self._is_cancelled = False
        self._pending_dispatch = False
        self._pending_finish = False
        self._pending_error = None
        self._terminal_notified = False
        self.current_request = SubtitleGenerationRequest(**checkpoint.request_data)
        self._generated_segments_count = 0
        if self.current_request.batch_mode != "segments":
            try:
                existing_rows = self.artifact_service.load_data(artifact.path).get("segments", [])
                self._generated_segments_count = sum(
                    1
                    for row in existing_rows
                    if not self._is_unfilled_timing_text(row.get("text"))
                )
            except Exception:
                self._generated_segments_count = 0
        self.current_timing_ranges = []
        if self.current_request.batch_mode == "segments":
            all_timing_ranges = self._load_timing_segment_ranges(project)
            count = (
                checkpoint.timing_segment_count
                or self.current_request.batch_size_value
            )
            self.current_timing_ranges = all_timing_ranges[
                checkpoint.timing_segment_cursor : checkpoint.timing_segment_cursor
                + count
            ]
        self.current_batches = [
            SubtitleGenerationBatch(**batch_data)
            for batch_data in checkpoint.batches_data
        ]
        completed = set(checkpoint.completed_batches)
        for batch in self.current_batches:
            if batch.batch_id in completed:
                batch.status = "COMPLETED"
            else:
                # The checkpoint list is authoritative. A crash can leave the
                # serialized batch status ahead of the committed-batch list.
                batch.status = "PENDING"
        self.current_checkpoint = checkpoint
        self.current_checkpoint.status = "RUNNING"
        self.current_checkpoint.active_batch = None
        self.current_checkpoint.updated_at = self._now()
        self.checkpoint_manager.save_checkpoint(self.current_checkpoint)
        self._dispatch_next_batch()

    def cancel_generation(self) -> None:
        self._is_cancelled = True
        self._pending_dispatch = False
        worker = self.current_worker
        if worker and worker.isRunning():
            worker.cancel()
        if self.current_checkpoint:
            self.current_checkpoint.status = "CANCELLED"
            self.current_checkpoint.active_batch = None
            self.current_checkpoint.updated_at = self._now()
            self._save_checkpoint()
        # Do not unload the model or notify the UI while inference is still
        # inside QThread.run(). Resume becomes available only after finished.
        self._pending_finish = True
        self._complete_terminal_if_idle()

    def _dispatch_next_batch(self) -> None:
        if self._is_cancelled or not self.current_checkpoint:
            return
        batch = next(
            (candidate for candidate in self.current_batches if candidate.status != "COMPLETED"),
            None,
        )
        if batch is None:
            self.current_checkpoint.status = "COMPLETED"
            self.current_checkpoint.active_batch = None
            self.current_checkpoint.updated_at = self._now()
            self._save_checkpoint()
            completion_message = "Subtitle generation completed."
            report = self.last_range_reconciliation
            if (
                self._is_range_generation
                and report
                and report.changed_segment_count
            ):
                completion_message = "Đã tạo phụ đề và tự điều chỉnh thời gian."
            elif self.current_request and self.current_request.batch_mode == "segments":
                target_segs = len(self.current_timing_ranges) or self._generated_segments_count
                completion_message = (
                    f"Hoàn tất tạo phụ đề · Đã gen {self._generated_segments_count}/{target_segs} câu (100%)."
                )
            elif self._generated_segments_count > 0:
                completion_message = (
                    f"Hoàn tất tạo phụ đề · Đã gen {self._generated_segments_count} câu (100%)."
                )
            self._notify_progress(100, completion_message)
            self._pending_finish = True
            self._complete_terminal_if_idle()
            return

        self.current_checkpoint.active_batch = asdict(batch)
        self.current_checkpoint.updated_at = self._now()
        self._save_checkpoint()
        completed_count = len(self.current_checkpoint.completed_batches)
        total = len(self.current_batches)
        if self.current_request and self.current_request.batch_mode == "segments":
            target_segs = len(self.current_timing_ranges) or max(
                1, int(getattr(self.current_request, "batch_size_value", 1) or 1)
            )
            start_pct = max(2, int(completed_count * 100 / total)) if total else 2
            self._notify_progress(
                start_pct,
                f"Đang tạo phụ đề: Đã gen {self._generated_segments_count}/{target_segs} câu ({start_pct}%)",
            )
        else:
            base_pct = int(completed_count * 100 / total) if total else 0
            start_pct = max(2, base_pct) if completed_count == 0 else base_pct
            self._notify_progress(
                start_pct,
                f"Đang tạo phụ đề (Batch {completed_count + 1}/{total}: "
                f"{batch.start_ms / 1000:.1f}s–{batch.end_ms / 1000:.1f}s) · "
                f"Đã gen {self._generated_segments_count} câu ({start_pct}%)",
            )

        self.current_worker = SubtitleGenerationWorker(
            self.current_request, batch, self.whisper_service
        )
        worker = self.current_worker
        self.current_worker.batch_success_signal.connect(self._commit_batch)
        if hasattr(self.current_worker, "batch_progress_signal"):
            self.current_worker.batch_progress_signal.connect(
                self._on_worker_batch_progress
            )
        self.current_worker.error_signal.connect(self._handle_worker_error)
        # The real QThread always has `finished`; the guard keeps the service
        # usable with lightweight test doubles as well.
        if hasattr(worker, "finished"):
            # Bound QObject slots give Qt a receiver context, so this cleanup
            # is queued back to the service's Main Thread instead of running
            # inside the worker thread.
            worker.finished.connect(self._on_worker_finished_signal)
        worker.start()

    @Slot(object, object)



    def _ensure_history_loaded(self):
        project = self.project_service.current_project
        if not project:
            self.all_checkpoints = []
            self._history_project_id = None
            return
        if getattr(self, '_history_project_id', None) != project.project_id:
            self.all_checkpoints = []
            self.load_history()
            self._history_project_id = project.project_id

    def _get_history_path(self) -> str:
        from pathlib import Path
        project = self.project_service.current_project
        project_dir = getattr(self.project_service, "project_dir", None) or getattr(
            project, "project_dir", None
        )
        if (
            not project
            or not isinstance(project_dir, (str, Path))
            or not str(project_dir).strip()
        ):
            return None
        import os
        checkpoint_dir = os.path.join(
            project_dir, "artifacts", "subtitle_generation"
        )
        os.makedirs(checkpoint_dir, exist_ok=True)
        return os.path.join(checkpoint_dir, "history.json")

    def _save_history(self):
        path = self._get_history_path()
        if not path:
            return
            
        import json
        import os
        data = {
            "all_checkpoints": [cp.__dict__ for cp in getattr(self, "all_checkpoints", [])],
            "initial_state": self.initial_state.__dict__ if self.initial_state else None,
            "history": [cp.__dict__ for cp in self.checkpoint_history]
        }
        
        temp_path = f"{path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def load_history(self):
        path = self._get_history_path()
        if not path or not __import__("os").path.exists(path):
            return
            
        import json
        from core.subtitle_generation.generation_checkpoint import GenerationCheckpoint
        
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                
            def dict_to_cp(d):
                if not d: return None
                cp = GenerationCheckpoint(
                    checkpoint_id=d.get("checkpoint_id"),
                    project_id=d.get("project_id"),
                    source_fingerprint=d.get("source_fingerprint"),
                    generated_count=d.get("generated_count"),
                    segments_snapshot=d.get("segments_snapshot", []),
                    generation_range=d.get("generation_range"),
                    generation_request_id=d.get("generation_request_id"),
                    checkpoint_type=d.get("checkpoint_type", "BATCH"),
                    model_settings=d.get("model_settings", {}),
                source_id=d.get("source_id", "default")
            )
                cp.created_at = d.get("created_at", __import__("time").time())
                return cp
                
            if "all_checkpoints" in data:
                self.all_checkpoints = [dict_to_cp(d) for d in data.get("all_checkpoints", [])]
            else:
                self.all_checkpoints = []
                initial = dict_to_cp(data.get("initial_state"))
                if initial: self.all_checkpoints.append(initial)
                self.all_checkpoints.extend([dict_to_cp(d) for d in data.get("history", [])])
        except Exception:
            pass

    def create_history_checkpoint(self, segments, is_initial=False, is_range=False, is_timing=False):
        """Creates a snapshot of the generation state and appends to history."""
        self._ensure_history_loaded()
        from core.subtitle_generation.generation_checkpoint import GenerationCheckpoint
        project = self.project_service.current_project
        if not project:
            return
            
        if is_initial:
            c_type = "INITIAL"
        else:
            c_type = "TIMING_BATCH" if is_timing else (
                "RANGE_GENERATION_BATCH" if is_range else "FULL_GENERATION_BATCH"
            )
            
        cp = GenerationCheckpoint(
            checkpoint_id=str(__import__("uuid").uuid4()),
            project_id=project.project_id,
            source_fingerprint=project.source.fingerprint if hasattr(project, "source") else "",
            generated_count=len(segments),
            segments_snapshot=segments,
            checkpoint_type=c_type,
            generation_request_id=self.current_request.request_id if self.current_request else None,
            source_id=getattr(project.state, "active_subtitle_source_id", "default")
        )
        
        if is_initial and self.initial_state:
            return
        self.all_checkpoints.append(cp)
        try:
            self._save_history()
        except Exception:
            self.all_checkpoints.pop()
            raise
        self.history_changed.emit()
            
    def get_rollback_checkpoint(self, target_count=None, checkpoint_id=None):
        """
        Resolves the target rollback checkpoint.
        """
        self._ensure_history_loaded()
        if checkpoint_id:
            if self.initial_state and self.initial_state.checkpoint_id == checkpoint_id:
                return self.initial_state
            for cp in self.checkpoint_history:
                if cp.checkpoint_id == checkpoint_id:
                    return cp
            return None
            
        if target_count == 0:
            return self.initial_state
            
        if target_count is not None:
            # Exact match only
            for cp in reversed(self.checkpoint_history):
                if cp.generated_count == target_count:
                    return cp
                    
        return None


    def execute_rollback(self, target_count, data_provider, undo_manager, checkpoint_id=None):
        """
        Executes a rollback to a specific target_count by pushing a RestoreGenerationCommand
        to the provided undo_manager.
        """
        self._ensure_idle()
        cp = self.get_rollback_checkpoint(target_count, checkpoint_id=checkpoint_id)
        if cp is None:
            raise ValueError(f"No checkpoint found near target count: {target_count}")
            
        from core.subtitle_editing.commands.restore_generation_command import RestoreGenerationCommand
        
        # Check for manual edits (for UI reporting later)
        has_manual = cp.has_manual_edits_compared_to(data_provider)

        rows = copy.deepcopy(cp.segments_snapshot)
        for index, row in enumerate(rows, 1):
            # ASR artifacts store milliseconds; the editor also needs its aliases.
            row.setdefault("start", row.get("start_ms"))
            row.setdefault("end", row.get("end_ms"))
            row.setdefault("id", str(uuid.uuid4()))
            row["stt"] = str(index)
        
        command = RestoreGenerationCommand(
            before_segments=data_provider,
            after_segments=rows,
            data_provider=data_provider
        )
        undo_manager.push(command)
        self.project_service.mark_dirty()
        return has_manual

    def _commit_batch(
        self, batch: SubtitleGenerationBatch, result: SubtitleGenerationResult
    ) -> None:
        if self._is_cancelled or not self.current_checkpoint:
            return
        if self._is_range_generation:
            self._commit_range_batch(batch, result)
            return
        try:
            project = self._require_project()
            self._validate_request_source(self.current_request, project)
            artifact = self.artifact_service.get_or_create_artifact()
            if artifact is None:
                raise RuntimeError("Subtitle artifact is unavailable.")
            if artifact.artifact_id != self.current_checkpoint.subtitle_artifact_id:
                raise GenerationError(GenerationErrorCode.STALE_SUBTITLE, "artifact identity changed.")
            if artifact.revision != self.current_checkpoint.artifact_revision:
                self.current_checkpoint.artifact_revision = artifact.revision
                if os.path.exists(artifact.path):
                    self.current_checkpoint.artifact_content_hash = (
                        self.artifact_service.content_hash(artifact.path)
                    )
            else:
                self._assert_live_artifact_hash(artifact)

            valid = SubtitleGenerationValidator.validate(
                result.segments, batch.start_ms, batch.end_ms
            )
            if self.current_request.batch_mode == "segments":
                valid = self._align_text_to_timing_ranges(
                    valid, self.current_timing_ranges
                )
            data = self.artifact_service.load_data(artifact.path)
            existing = data.get("segments", [])
            if self.current_request.batch_mode == "segments":
                reconciled = self._fill_timing_rows(existing, valid)
            else:
                reconciled = BoundaryReconciler.reconcile(existing, valid)
                existing.extend(
                    {
                        "id": str(uuid.uuid4()),
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        "text": segment.text,
                        "words": segment.words,
                        "status": "generated",
                    }
                    for segment in reconciled
                )
            existing.sort(key=lambda segment: (segment["start_ms"], segment["end_ms"]))
            data["segments"] = existing
            self.artifact_service._save_atomic(artifact.path, data)

            artifact.revision += 1
            artifact.updated_at = self._now()
            batch.status = "COMPLETED"
            batch.updated_at = self._now()
            self.current_checkpoint.completed_batches.append(batch.batch_id)
            self.create_history_checkpoint(existing, is_range=self._is_range_generation)
            self.current_checkpoint.artifact_revision = artifact.revision
            self.current_checkpoint.artifact_content_hash = (
                self.artifact_service.content_hash(artifact.path)
            )
            self.current_checkpoint.active_batch = None
            self.current_checkpoint.next_start_ms = batch.end_ms
            if self.current_request.batch_mode == "segments":
                self.current_checkpoint.timing_segment_cursor += (
                    self.current_checkpoint.timing_segment_count
                )
            self.current_checkpoint.batches_data = [
                asdict(candidate) for candidate in self.current_batches
            ]
            self.current_checkpoint.updated_at = self._now()
            mark_dirty = getattr(self.project_service, "mark_dirty", None)
            if mark_dirty:
                mark_dirty()
            self.checkpoint_manager.save_checkpoint(self.current_checkpoint)
            self._generated_segments_count += len(reconciled)
            if self.on_batch_complete:
                self.on_batch_complete(batch, reconciled)
            # The success signal can be delivered just before QThread.run()
            # returns. Wait for finished so only one worker is alive at a time.
            self._pending_dispatch = True
            self._dispatch_next_batch_if_idle()
        except Exception as exc:
            batch.status = "STALE" if "STALE_SUBTITLE" in str(exc) else "FAILED"
            self._fail(str(exc))

    @Slot(int, int)
    def _on_worker_batch_progress(self, batch_seg_count: int, seg_end_ms: int) -> None:
        if self._is_cancelled or not self.current_checkpoint or not self.current_batches:
            return
        active_id = (self.current_checkpoint.active_batch or {}).get("batch_id")
        batch = next(
            (b for b in self.current_batches if b.batch_id == active_id),
            None,
        ) or next(
            (b for b in self.current_batches if b.status != "COMPLETED"),
            self.current_batches[0],
        )
        if self.current_request and self.current_request.batch_mode == "segments":
            target_segs = len(self.current_timing_ranges) or max(
                1, int(getattr(self.current_request, "batch_size_value", 1) or 1)
            )
            abs_pos_ms = batch.start_ms + max(0, int(seg_end_ms))
            covered_slots = sum(
                1 for s_ms, _e_ms in self.current_timing_ranges if s_ms < abs_pos_ms
            )
            done_segs = min(
                target_segs,
                max(
                    covered_slots,
                    min(int(batch_seg_count), target_segs),
                    1 if batch_seg_count > 0 else 0,
                ),
            )
            seg_pct = int(done_segs * 100 / max(1, target_segs))
            batch_dur = max(1, batch.end_ms - batch.start_ms)
            time_pct = int(min(0.99, max(0.0, seg_end_ms / batch_dur)) * 95)
            bar_pct = min(99, max(5, seg_pct, time_pct))
            self._notify_progress(
                bar_pct,
                f"Đang tạo phụ đề: Đã gen {done_segs}/{target_segs} câu ({bar_pct}%)",
            )
            return

        completed_count = len(self.current_checkpoint.completed_batches)
        total = max(1, len(self.current_batches))
        batch_dur = max(1, batch.end_ms - batch.start_ms)
        in_batch_ratio = min(0.99, max(0.02, seg_end_ms / batch_dur))
        bar_pct = min(
            99, max(2, int(((completed_count + in_batch_ratio) * 100) / total))
        )
        live_total = self._generated_segments_count + max(0, int(batch_seg_count))
        self._notify_progress(
            bar_pct,
            f"Đang tạo phụ đề (Batch {completed_count + 1}/{total}) · "
            f"Đã gen {live_total} câu ({bar_pct}%)",
        )

    @Slot(str)
    def _handle_worker_error(self, message: str) -> None:
        if not self._is_cancelled:
            self._fail(message)

    def _fail(self, message: str) -> None:
        if self._terminal_notified or self._pending_error:
            return
        if self.current_checkpoint:
            self.current_checkpoint.status = "FAILED"
            self.current_checkpoint.updated_at = self._now()
            self._save_checkpoint()
        self._pending_dispatch = False
        self._pending_error = message
        self._complete_terminal_if_idle()

    def _dispatch_next_batch_if_idle(self) -> None:
        if self.is_running:
            return
        if self._pending_dispatch:
            self._pending_dispatch = False
            self._dispatch_next_batch()

    @Slot()
    def _on_worker_finished_signal(self) -> None:
        worker = self.sender()
        if worker is not None:
            self._on_worker_finished(worker)

    def _on_worker_finished(self, worker) -> None:
        if worker is not self.current_worker:
            return
        self.current_worker = None
        self._dispatch_next_batch_if_idle()
        self._complete_terminal_if_idle()

    def _complete_terminal_if_idle(self) -> None:
        if self.is_running or self._terminal_notified:
            return
        if not self._pending_finish and not self._pending_error:
            return

        self._terminal_notified = True
        pending_error = self._pending_error
        self._pending_error = None
        self._pending_finish = False
        self.whisper_service.unload_model()

        if pending_error:
            if self.on_error:
                self.on_error(pending_error)
        elif self.on_finish:
            self.on_finish()

    def _ensure_idle(self) -> None:
        if self.current_worker and self.current_worker.isRunning():
            raise RuntimeError("Subtitle generation is already running.")

    def _save_checkpoint(self):
        if not self._is_range_generation:
            self.checkpoint_manager.save_checkpoint(self.current_checkpoint)

    def _commit_range_batch(self, batch, result):
        if self._is_cancelled or not self.current_checkpoint:
            return
        try:
            if not result.segments:
                raise RuntimeError("No subtitle segments were generated for this range.")
            project = self._require_project()
            self._validate_request_source(self.current_request, project)
            state_artifact_id = getattr(project.state, "subtitle_artifact_id", None)
            artifact = (
                self.project_service.artifact_store.get(state_artifact_id)
                if state_artifact_id else None
            )
            artifact_data = (
                self.artifact_service.load_data(artifact.path)
                if artifact and os.path.exists(artifact.path)
                else {"version": 1, "segments": []}
            )
            artifact_rows = artifact_data.get("segments", [])
            current_subtitles = self._resolve_range_coverage(
                artifact_rows, self._range_editor_segments
            )
            
            # PHASE 2: Apply Conflict Strategy before reconciliation
            from core.subtitle_generation.range_validation import ConflictStrategy

            def _seg_bounds(seg):
                raw_s = seg.get("start_ms", seg.get("start")) if isinstance(seg, dict) else getattr(seg, "start_ms", None)
                raw_e = seg.get("end_ms", seg.get("end")) if isinstance(seg, dict) else getattr(seg, "end_ms", None)
                return self._coerce_segment_ms(raw_s), self._coerce_segment_ms(raw_e)

            def _overlaps_range(seg, r_start, r_end):
                s_start, s_end = _seg_bounds(seg)
                if s_start is None or s_end is None:
                    return False
                return s_start < r_end and s_end > r_start

            strategy = getattr(self, "_range_conflict_strategy", None)
            generated_input = list(result.segments or [])
            reconcile_subtitles = current_subtitles
            if strategy == ConflictStrategy.REPLACE_OVERLAP:
                current_subtitles = [
                    seg for seg in current_subtitles
                    if not _overlaps_range(seg, batch.start_ms, batch.end_ms)
                ]
                reconcile_subtitles = current_subtitles
            elif strategy == ConflictStrategy.FILL_GAPS_ONLY:
                occupied = [
                    bounds for seg in current_subtitles
                    if (bounds := _seg_bounds(seg))[0] is not None and bounds[1] is not None
                ]
                generated_input = [
                    seg for seg in generated_input
                    if (gb := _seg_bounds(seg))[0] is not None and gb[1] is not None
                    and not any(gb[0] < oe and gb[1] > os_ for os_, oe in occupied)
                ]
                reconcile_subtitles = [
                    seg for seg in current_subtitles
                    if not _overlaps_range(seg, batch.start_ms, batch.end_ms)
                ]

            generated_input = SubtitleGenerationValidator.filter_hallucinated_segments(
                generated_input
            )
            if not generated_input:
                self.last_range_reconciliation = ReconciliationResult(
                    status=ReconciliationStatus.EMPTY_RESULT,
                    reason="No subtitle segments were generated for this range.",
                )
                raise RuntimeError("No subtitle segments were generated for this range.")

            reconciled = reconcile_generated_timing(
                GenerationRange(batch.start_ms, batch.end_ms),
                generated_input,
                self._range_duration_ms,
                current_subtitles=reconcile_subtitles,
            )
            self.last_range_reconciliation = reconciled
            if reconciled.status == ReconciliationStatus.STALE_RANGE_CONFLICT:
                raise GenerationError(GenerationErrorCode.STALE_RANGE_CONFLICT, f"{reconciled.reason}")
            if reconciled.status == ReconciliationStatus.EMPTY_RESULT:
                raise RuntimeError(reconciled.reason or "No subtitle segments were generated for this range.")
            if reconciled.status != ReconciliationStatus.SUCCESS:
                raise GenerationError(GenerationErrorCode.RECONCILIATION_UNSAFE, f"{reconciled.reason}")

            if state_artifact_id != self._range_state_artifact_id:
                raise GenerationError(GenerationErrorCode.STALE_SUBTITLE, "artifact identity changed during range generation.")
            if (artifact.artifact_id if artifact else None) != self._range_artifact_id:
                raise GenerationError(GenerationErrorCode.STALE_SUBTITLE, "artifact identity changed during range generation.")
            if artifact and artifact.revision != self._range_artifact_revision:
                raise GenerationError(GenerationErrorCode.STALE_SUBTITLE, "artifact revision changed during range generation.")
            if artifact:
                self._assert_live_artifact_hash(artifact)
            if artifact and self._range_artifact_hash:
                if self.artifact_service.content_hash(artifact.path) != self._range_artifact_hash:
                    raise GenerationError(GenerationErrorCode.STALE_SUBTITLE, "artifact changed during range generation.")

            generated = SubtitleGenerationValidator.validate(
                list(reconciled.segments), batch.start_ms, batch.end_ms
            )
            if len(generated) != len(reconciled.segments):
                raise GenerationError(GenerationErrorCode.RECONCILIATION_UNSAFE, "generated output failed subtitle validation.")
            rows = copy.deepcopy([
                segment.get_raw_dict() if hasattr(segment, "get_raw_dict") else segment
                for segment in current_subtitles
            ])
            rows.extend(
                {
                    "id": str(uuid.uuid4()),
                    "start_ms": int(segment.start_ms),
                    "end_ms": int(segment.end_ms),
                    "text": segment.text,
                    "words": segment.words,
                    "status": "generated",
                }
                for segment in generated
            )
            rows.sort(
                key=lambda row: (
                    self._coerce_segment_ms(row.get("start_ms", row.get("start"))) or 0,
                    self._coerce_segment_ms(row.get("end_ms", row.get("end"))) or 0,
                )
            )
            data = dict(artifact_data)
            data["segments"] = rows

            if artifact:
                self.artifact_service._save_atomic(artifact.path, data)
                artifact.revision += 1
                artifact.updated_at = self._now()
                mark_dirty = getattr(self.project_service, "mark_dirty", None)
                if mark_dirty:
                    mark_dirty()
            else:
                artifact = self.artifact_service.create_artifact_with_data(data)
                if artifact is None:
                    raise RuntimeError("Unable to create subtitle artifact.")

            self._range_committed = True
            self.create_history_checkpoint(rows, is_range=True)
            self.current_checkpoint.status = "COMPLETED"
            self.current_checkpoint.artifact_revision = artifact.revision
            self.current_checkpoint.artifact_content_hash = self.artifact_service.content_hash(artifact.path)
            self.current_checkpoint.completed_batches = [batch.batch_id]
            batch.status = "COMPLETED"
            batch.updated_at = self._now()
            self._generated_segments_count += len(generated)
            if self.on_batch_complete:
                self.on_batch_complete(batch, generated)
            self._pending_dispatch = True
            self._dispatch_next_batch_if_idle()
        except Exception as exc:
            batch.status = "FAILED"
            self._fail(str(exc))

    def _resolve_range_coverage(self, artifact_rows, supplied_segments):
        """Providers/callers supply complete rows for the validated request context.

        None means unavailable; an empty list is authoritative, not a fallback.
        Call again immediately before insertion to observe edits made during ASR.
        """
        current = (
            self.range_segments_provider()
            if callable(self.range_segments_provider)
            else supplied_segments
        )
        return list(artifact_rows if current is None else current)

    def _require_project(self):
        project = self.project_service.current_project
        if not project:
            raise ValueError("No project is currently open.")
        return project

    def _validate_request_source(self, request, project) -> None:
        if request.project_id != project.project_id:
            raise ValueError("Sai Project ID: request belongs to another project.")
        if request.source_fingerprint != project.source.fingerprint:
            request.source_fingerprint = project.source.fingerprint
            if getattr(project, "source", None) and getattr(project.source, "path", None):
                request.video_path = project.source.path
        source_path = getattr(project.source, "path", None)
        if source_path:
            if not os.path.exists(source_path):
                raise FileNotFoundError("Project source video was not found.")
            if os.path.normcase(request.video_path) != os.path.normcase(source_path):
                request.video_path = source_path

    def _validate_checkpoint(self, checkpoint, project) -> None:
        if checkpoint.project_id != project.project_id:
            raise ValueError("Sai Project ID: checkpoint belongs to another project.")
        if checkpoint.source_fingerprint != project.source.fingerprint:
            raise ValueError("Source video does not match checkpoint. Relink the project video before resuming.")

    @staticmethod
    def _is_unfilled_timing_text(text) -> bool:
        cleaned = (str(text) if text is not None else "").strip().casefold()
        if not cleaned:
            return True
        if cleaned.startswith("[") and cleaned.endswith("]"):
            inner = cleaned[1:-1].strip()
            return inner in {
                "",
                "chưa có nội dung",
                "chua co noi dung",
                "chưa có phụ đề",
                "empty",
                "no content",
            }
        return False

    def _coerce_segment_ms(self, raw) -> int | None:
        if isinstance(raw, bool) or raw is None:
            return None
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, str):
            val = raw.strip()
            if not val:
                return None
            if val.lstrip("-").isdigit():
                return int(val)
            try:
                return self._parse_srt_time_ms(val)
            except ValueError:
                return None
        return None

    def _extract_live_timing_rows(self, existing_segments=None) -> list[dict]:
        rows = existing_segments
        if rows is None:
            provider = getattr(self, "range_segments_provider", None)
            if callable(provider):
                try:
                    rows = provider()
                except Exception:
                    rows = None
        if not rows:
            return []
        extracted = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            start_ms = self._coerce_segment_ms(item.get("start_ms", item.get("start")))
            end_ms = self._coerce_segment_ms(item.get("end_ms", item.get("end")))
            if start_ms is None or end_ms is None or end_ms <= start_ms:
                continue
            extracted.append(
                {
                    "id": str(item.get("id") or uuid.uuid4()),
                    "start_ms": int(start_ms),
                    "end_ms": int(end_ms),
                    "text": str(item.get("text", "") or ""),
                    "status": item.get("status"),
                }
            )
        extracted.sort(key=lambda r: (r["start_ms"], r["end_ms"]))
        deduped = []
        seen = set()
        for row in extracted:
            key = (row["start_ms"], row["end_ms"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped

    def _load_timing_segment_ranges(self, project, existing_segments=None):
        """Read real segment ranges from live editor rows, Timing Artifact, or Subtitle Artifact."""
        live_rows = self._extract_live_timing_rows(existing_segments)
        if live_rows:
            return [(row["start_ms"], row["end_ms"]) for row in live_rows]

        timing_state = getattr(getattr(project, "state", None), "timing", None)
        timing_artifact_id = getattr(timing_state, "timing_artifact_id", None)
        store = getattr(self.project_service, "artifact_store", None)
        artifact = store.get(timing_artifact_id) if store and timing_artifact_id else None

        ranges = []
        if artifact and getattr(artifact, "path", None) and os.path.exists(artifact.path):
            with open(artifact.path, "r", encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            for line in lines:
                if "-->" not in line:
                    continue
                start_text, end_text = (part.strip() for part in line.split("-->", 1))
                try:
                    start_ms = self._parse_srt_time_ms(start_text)
                    end_ms = self._parse_srt_time_ms(end_text)
                except ValueError:
                    continue
                if end_ms > start_ms:
                    ranges.append((start_ms, end_ms))
        else:
            sub_artifact_id = getattr(getattr(project, "state", None), "subtitle_artifact_id", None)
            sub_art = store.get(sub_artifact_id) if store and sub_artifact_id else None
            if sub_art and getattr(sub_art, "path", None) and os.path.exists(sub_art.path):
                sub_segs = self.artifact_service.load_data(sub_art.path).get("segments", [])
                for row in sub_segs:
                    try:
                        s_ms = int(row.get("start_ms", 0))
                        e_ms = int(row.get("end_ms", 0))
                    except (TypeError, ValueError):
                        continue
                    if e_ms > s_ms:
                        ranges.append((s_ms, e_ms))
            else:
                raise ValueError(
                    "Segment-based batching requires a completed Timing Artifact."
                )

        if not ranges:
            raise ValueError("Timing Artifact does not contain valid subtitle ranges.")
        return ranges

    def get_timing_segment_counts(self, existing_segments=None) -> tuple[int, int]:
        """Return (total_timing_count, unfilled_timing_count) across live editor or artifacts."""
        live_rows = self._extract_live_timing_rows(existing_segments)
        if live_rows:
            pending = sum(
                1 for r in live_rows if self._is_unfilled_timing_text(r.get("text"))
            )
            return len(live_rows), pending

        project = getattr(self.project_service, "current_project", None)
        if not project:
            return 0, 0
        try:
            ranges = self._load_timing_segment_ranges(project)
        except Exception:
            return 0, 0

        store = getattr(self.project_service, "artifact_store", None)
        sub_art_id = getattr(getattr(project, "state", None), "subtitle_artifact_id", None)
        sub_art = store.get(sub_art_id) if store and sub_art_id else None
        if sub_art and getattr(sub_art, "path", None) and os.path.exists(sub_art.path):
            sub_rows = self.artifact_service.load_data(sub_art.path).get("segments", [])
            rows_by_key = {
                (int(r.get("start_ms", -1)), int(r.get("end_ms", -1))): r
                for r in sub_rows
            }
            pending = sum(
                1
                for start_ms, end_ms in ranges
                if (
                    rows_by_key.get((int(start_ms), int(end_ms))) is None
                    or (
                        self._is_unfilled_timing_text(
                            rows_by_key[(int(start_ms), int(end_ms))].get("text")
                        )
                        and rows_by_key[(int(start_ms), int(end_ms))].get("status") != "generated"
                    )
                )
            )
            return len(ranges), pending
        return len(ranges), len(ranges)

    def _get_timing_segment_cursor(self, project, artifact, total_ranges: int) -> int:
        """Restore the next segment index only for the same safe ASR artifact."""
        checkpoint = self.checkpoint_manager.load_checkpoint()
        if not checkpoint:
            return 0
        if (
            checkpoint.project_id != project.project_id
            or checkpoint.subtitle_artifact_id != artifact.artifact_id
            or checkpoint.request_data.get("batch_mode") != "segments"
        ):
            return 0
        if checkpoint.source_fingerprint != project.source.fingerprint:
            checkpoint.source_fingerprint = project.source.fingerprint
            self.checkpoint_manager.save_checkpoint(checkpoint)
        return max(0, min(int(checkpoint.timing_segment_cursor), total_ranges))

    def _assert_live_artifact_hash(self, artifact) -> None:
        """Reject a file edit made after the batch checkpoint was written."""
        expected_hash = self.current_checkpoint.artifact_content_hash
        if not expected_hash or not os.path.exists(artifact.path):
            return
        current_hash = self.artifact_service.content_hash(artifact.path)
        if current_hash != expected_hash:
            raise RuntimeError(
                "STALE_SUBTITLE_FILE: subtitle artifact was edited externally "
                "during inference."
            )

    def _ensure_timing_rows(self, artifact, timing_ranges, existing_segments=None) -> None:
        """Seed missing subtitle rows from Timing and sync live filled/unfilled state."""
        data = self.artifact_service.load_data(artifact.path)
        existing = data.get("segments", [])
        rows_by_key = {
            (int(row.get("start_ms", -1)), int(row.get("end_ms", -1))): row
            for row in existing
        }
        live_rows = self._extract_live_timing_rows(existing_segments)
        live_by_key = {
            (row["start_ms"], row["end_ms"]): row for row in live_rows
        }
        has_live_source = bool(live_by_key)

        changed = False
        for start_ms, end_ms in timing_ranges:
            key = (int(start_ms), int(end_ms))
            live_row = live_by_key.get(key)
            live_text = (live_row.get("text") or "").strip() if live_row else ""
            live_unfilled = self._is_unfilled_timing_text(live_text)
            if key not in rows_by_key:
                new_row = {
                    "id": live_row["id"] if live_row else str(uuid.uuid4()),
                    "start_ms": int(start_ms),
                    "end_ms": int(end_ms),
                    "text": "" if (not has_live_source or live_unfilled) else live_text,
                    "words": None,
                    "status": "timing" if (not has_live_source or live_unfilled) else "generated",
                }
                existing.append(new_row)
                rows_by_key[key] = new_row
                changed = True
            elif has_live_source and live_row is not None:
                row = rows_by_key[key]
                if not live_unfilled and (row.get("text") != live_text or row.get("status") != "generated"):
                    row["text"] = live_text
                    row["status"] = "generated"
                    changed = True
                elif live_unfilled and (row.get("text") != "" or row.get("status") != "timing"):
                    row["text"] = ""
                    row["status"] = "timing"
                    changed = True

        if not changed:
            return

        existing.sort(key=lambda r: int(r.get("start_ms", 0)))
        data["segments"] = existing
        self.artifact_service._save_atomic(artifact.path, data)
        artifact.revision += 1
        artifact.updated_at = self._now()
        mark_dirty = getattr(self.project_service, "mark_dirty", None)
        if mark_dirty:
            mark_dirty()

    @staticmethod
    def _fill_timing_rows(existing, segments):
        """Update text in exact Timing slots instead of appending duplicate rows."""
        rows_by_range = {
            (int(row.get("start_ms", -1)), int(row.get("end_ms", -1))): row
            for row in existing
        }
        applied = []
        for segment in segments:
            key = (int(segment.start_ms), int(segment.end_ms))
            row = rows_by_range.get(key)
            if row is None:
                row = {
                    "id": str(uuid.uuid4()),
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                }
                existing.append(row)
                rows_by_range[key] = row
            row.update(
                {
                    "text": segment.text,
                    "words": segment.words,
                    "status": "generated",
                }
            )
            applied.append(segment)
        return applied

    @staticmethod
    def _align_text_to_timing_ranges(segments, timing_ranges):
        """Keep Timing boundaries authoritative while assigning ASR text."""
        text_buckets = [[] for _range in timing_ranges]
        for segment in segments:
            overlaps = [
                max(
                    0,
                    min(segment.end_ms, end_ms)
                    - max(segment.start_ms, start_ms),
                )
                for start_ms, end_ms in timing_ranges
            ]
            if not overlaps or max(overlaps) <= 0:
                continue
            target_index = max(range(len(overlaps)), key=overlaps.__getitem__)
            text = (segment.text or "").strip()
            if text:
                text_buckets[target_index].append(text)

        return [
            WhisperSegmentResult(
                start_ms=start_ms,
                end_ms=end_ms,
                text=" ".join(text_buckets[index]),
                words=None,
            )
            for index, (start_ms, end_ms) in enumerate(timing_ranges)
        ]

    @staticmethod
    def _parse_srt_time_ms(value: str) -> int:
        match = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})", value)
        if not match:
            raise ValueError(f"Invalid SRT timestamp: {value}")
        hours, minutes, seconds, milliseconds = match.groups()
        return (
            int(hours) * 3600000
            + int(minutes) * 60000
            + int(seconds) * 1000
            + int(milliseconds.ljust(3, "0"))
        )

    def _notify_progress(self, percent: int, message: str) -> None:
        if self.on_progress:
            self.on_progress(max(0, min(100, percent)), message)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
