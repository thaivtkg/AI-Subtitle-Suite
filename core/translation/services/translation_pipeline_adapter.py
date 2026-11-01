from .translation_execution_port import TranslationExecutionPort


class TranslationPipelineAdapter(TranslationExecutionPort):
    """Adapts one explicit-target controller request to the batch port."""

    def __init__(self, controller, source_lang="English", target_lang="Vietnamese", story_summary=""):
        self._controller = controller
        self._source_lang = source_lang
        self._target_lang = target_lang
        self._story_summary = story_summary
        self._pending = None
        controller.translationCompleted.connect(self._on_completed)
        controller.translationFailed.connect(self._on_failed)

    def translate(self, target_index, on_success, on_error):
        if self._pending is not None:
            raise RuntimeError("A translation request is already active")
        self._pending = (target_index, on_success, on_error)
        self._controller.requestTranslation(
            target_index,
            self._source_lang,
            self._target_lang,
            self._story_summary,
        )

    def configure(self, source_lang, target_lang, story_summary):
        if self._pending is not None:
            raise RuntimeError("Cannot reconfigure while a translation is active")
        self._source_lang = source_lang
        self._target_lang = target_lang
        self._story_summary = story_summary

    def _on_completed(self, target_index):
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        bound_target, on_success, on_error = pending
        if target_index != bound_target:
            on_error(bound_target, f"Callback target mismatch: callback={target_index}")
            return
        on_success(bound_target)

    def _on_failed(self, target_index, message):
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        bound_target, _, on_error = pending
        if target_index != bound_target:
            on_error(bound_target, f"Callback target mismatch: callback={target_index}")
            return
        on_error(bound_target, message)
