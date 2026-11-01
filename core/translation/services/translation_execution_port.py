from collections.abc import Callable
from typing import Protocol


TranslationSuccessCallback = Callable[[int], None]
TranslationErrorCallback = Callable[[int, str], None]


class TranslationExecutionPort(Protocol):
    """Dispatches one translation and reports its terminal result."""

    def translate(
        self,
        target_index: int,
        on_success: TranslationSuccessCallback,
        on_error: TranslationErrorCallback,
    ) -> None:
        """Emit at most one terminal callback for the requested target."""
