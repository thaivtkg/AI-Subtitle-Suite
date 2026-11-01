from core.translation.batch.batch_item import BatchItem
from core.translation.batch.batch_job import BatchJob
from core.translation.batch.batch_state import BatchItemState, BatchJobState
from core.translation.batch.cancel_policy import (
    ensure_item_cancel_transition,
    ensure_job_cancel_transition,
)
from core.translation.batch.pause_policy import ensure_job_pause_transition
from core.translation.batch.retry_policy import (
    ensure_item_retry_transition,
    ensure_job_retry_transition,
    ensure_retry_eligible,
)
from core.translation.batch.transition_guard import ensure_item_transition, ensure_job_transition

from .translation_execution_port import TranslationExecutionPort


class BatchTranslationService:
    def __init__(self, execution_port: TranslationExecutionPort):
        self._execution_port = execution_port
        self._job: BatchJob | None = None
        self._active_index: int | None = None
        self._retry_targets: tuple[int, ...] | None = None
        self._retry_cursor = 0
        self._cancel_requested = False

    def start(self, job: BatchJob) -> None:
        if self._job is not None:
            raise RuntimeError("A batch job is already active")

        ensure_job_transition(job.state, BatchJobState.RUNNING)
        job.state = BatchJobState.RUNNING
        self._job = job
        self._retry_targets = None
        self._retry_cursor = 0
        self._cancel_requested = False
        self._dispatch_next()

    def retry_failed(self, job: BatchJob) -> None:
        if self._job is not None:
            raise RuntimeError("A batch job is already active")

        ensure_retry_eligible(job)
        retry_targets = tuple(
            sorted(
                target_index
                for target_index, item in job.items.items()
                if item.state is BatchItemState.FAILED
            )
        )
        ensure_job_retry_transition(job.state, BatchJobState.RUNNING)
        job.state = BatchJobState.RUNNING
        self._job = job
        self._retry_targets = retry_targets
        self._retry_cursor = 0
        self._cancel_requested = False
        self._dispatch_next()

    def request_cancel(self, job: BatchJob) -> None:
        if self._job is None:
            raise RuntimeError("No active batch job")
        if self._job is not job:
            raise RuntimeError("Cannot cancel a different batch job")
        if self._job.state is not BatchJobState.RUNNING:
            raise RuntimeError(
                f"Cancel requires RUNNING job, got {self._job.state.name}"
            )
        if self._cancel_requested:
            return

        self._cancel_requested = True

    def request_pause(self, job: BatchJob) -> None:
        if self._job is None:
            raise RuntimeError("No active batch job")
        if self._job is not job:
            raise RuntimeError("Cannot pause a different batch job")
        if self._cancel_requested:
            raise RuntimeError("Cannot pause while cancel is requested")
        if job.state is not BatchJobState.RUNNING:
            raise RuntimeError(
                f"Pause requires RUNNING job, got {job.state.name}"
            )

        ensure_job_pause_transition(
            job.state,
            BatchJobState.PAUSING,
        )
        job.state = BatchJobState.PAUSING

    def resume(self, job: BatchJob) -> None:
        if self._job is None:
            raise RuntimeError("No active batch job")
        if self._job is not job:
            raise RuntimeError("Cannot resume a different batch job")
        if self._active_index is not None:
            raise RuntimeError("Cannot resume while inference is active")

        ensure_job_pause_transition(
            job.state,
            BatchJobState.RUNNING,
        )
        job.state = BatchJobState.RUNNING
        self._dispatch_next()

    def _next_pending_item(self) -> BatchItem | None:
        assert self._job is not None

        for target_index in sorted(self._job.items):
            item = self._job.items[target_index]
            if item.state is BatchItemState.PENDING:
                return item

        return None

    def _dispatch_next(self) -> None:
        if self._active_index is not None:
            return

        is_retry = self._retry_targets is not None
        if is_retry:
            assert self._job is not None
            if self._retry_cursor >= len(self._retry_targets):
                self._finish_job()
                return
            target_index = self._retry_targets[self._retry_cursor]
            item = self._job.items[target_index]
            ensure_item_retry_transition(item.state, BatchItemState.RUNNING)
            self._retry_cursor += 1
        else:
            item = self._next_pending_item()
            if item is None:
                self._finish_job()
                return
            ensure_item_transition(item.state, BatchItemState.RUNNING)

        item.state = BatchItemState.RUNNING
        if is_retry:
            item.error_msg = None
        self._active_index = item.target_index

        try:
            self._execution_port.translate(
                target_index=item.target_index,
                on_success=self._handle_success,
                on_error=self._handle_error,
            )
        except Exception as error:
            item.state = BatchItemState.FAILED
            item.error_msg = str(error)
            self._active_index = None
            ensure_job_transition(self._job.state, BatchJobState.FAILED)
            self._job.state = BatchJobState.FAILED
            self._job = None
            self._retry_targets = None
            self._retry_cursor = 0
            self._cancel_requested = False
            raise

    def _handle_success(self, target_index: int) -> None:
        if self._job is None:
            raise RuntimeError("No active batch job")
        if self._active_index != target_index:
            raise RuntimeError(
                f"Callback target mismatch: active={self._active_index}, "
                f"callback={target_index}"
            )

        item = self._job.items[target_index]
        ensure_item_transition(item.state, BatchItemState.COMPLETED)
        item.state = BatchItemState.COMPLETED
        self._active_index = None
        if self._cancel_requested:
            self._finish_cancel()
        elif self._job.state is BatchJobState.PAUSING:
            self._finish_pause()
        else:
            self._dispatch_next()

    def _handle_error(self, target_index: int, message: str) -> None:
        if self._job is None:
            raise RuntimeError("No active batch job")
        if self._active_index != target_index:
            raise RuntimeError(
                f"Callback target mismatch: active={self._active_index}, "
                f"callback={target_index}"
            )

        item = self._job.items[target_index]
        ensure_item_transition(item.state, BatchItemState.FAILED)
        item.state = BatchItemState.FAILED
        item.error_msg = message
        self._active_index = None
        if self._cancel_requested:
            self._finish_cancel()
        elif self._job.state is BatchJobState.PAUSING:
            self._finish_pause()
        else:
            self._dispatch_next()

    def _finish_pause(self) -> None:
        assert self._job is not None
        assert self._active_index is None

        ensure_job_pause_transition(
            self._job.state,
            BatchJobState.PAUSED,
        )
        self._job.state = BatchJobState.PAUSED

    def _finish_cancel(self) -> None:
        assert self._job is not None

        for item in self._job.items.values():
            if item.state is BatchItemState.PENDING:
                ensure_item_cancel_transition(
                    item.state,
                    BatchItemState.CANCELLED,
                )
                item.state = BatchItemState.CANCELLED

        ensure_job_cancel_transition(
            self._job.state,
            BatchJobState.CANCELLED,
        )
        self._job.state = BatchJobState.CANCELLED
        self._job = None
        self._active_index = None
        self._retry_targets = None
        self._retry_cursor = 0
        self._cancel_requested = False

    def _finish_job(self) -> None:
        assert self._job is not None
        ensure_job_transition(self._job.state, BatchJobState.COMPLETED)
        self._job.state = BatchJobState.COMPLETED
        self._job = None
        self._active_index = None
        self._retry_targets = None
        self._retry_cursor = 0
        self._cancel_requested = False

