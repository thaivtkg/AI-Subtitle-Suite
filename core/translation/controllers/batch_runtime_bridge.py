from PySide6.QtCore import QObject, Signal

from core.translation.services.batch_translation_service import BatchTranslationService
from core.translation.services.translation_pipeline_adapter import TranslationPipelineAdapter


class _NotifyingExecutionPort:
    def __init__(self, delegate, notify):
        self._delegate = delegate
        self._notify = notify

    def translate(self, target_index, on_success, on_error):
        def success(index):
            on_success(index)
            self._notify()

        def error(index, message):
            on_error(index, message)
            self._notify()

        self._delegate.translate(target_index, success, error)


class BatchRuntimeBridge(QObject):
    jobChanged = Signal()

    def __init__(self, translation_controller, parent=None):
        super().__init__(parent)
        adapter = TranslationPipelineAdapter(translation_controller)
        self._service = BatchTranslationService(
            _NotifyingExecutionPort(adapter, self.jobChanged.emit)
        )
        self._adapter = adapter

    def configure(self, source_lang, target_lang, story_summary):
        self._adapter.configure(source_lang, target_lang, story_summary)

    def start(self, job):
        self._service.start(job)
        self.jobChanged.emit()

    def request_pause(self, job):
        self._service.request_pause(job)

    def resume(self, job):
        self._service.resume(job)

    def request_cancel(self, job):
        self._service.request_cancel(job)

    def retry_failed(self, job):
        self._service.retry_failed(job)

