import time

from PySide6.QtCore import QThread, Signal


class DeterministicTranslationWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(int, str)
    error = Signal(int, str)
    termsExtracted = Signal(int, list)

    RESPONSES = {
        0: "Nữ chiến binh phép thuật, Pontens!",
        1: "Đi thôi!",
        2: "Mau rời khỏi đây!",
    }

    def __init__(self, target_index, prompt, profile, mode="success"):
        super().__init__()
        self.target_index = target_index
        self.mode = mode.lower()

    def run(self):
        if self.mode == "error":
            self.error.emit(self.target_index, "Deterministic test error.")
            return

        if self.mode == "empty":
            self.finished.emit(self.target_index, "")
            return

        final_text = self.RESPONSES.get(self.target_index, "Deterministic translation")
        chunks = [
            "Nữ",
            "Nữ chiến binh",
            "Nữ chiến binh phép thuật",
            final_text,
        ] if self.target_index == 0 else [final_text]
        delay = 0.35 if self.mode == "slow" else 0.04

        for chunk in chunks:
            if self.isInterruptionRequested():
                return
            self.progress.emit(self.target_index, chunk)
            time.sleep(delay)

        if not self.isInterruptionRequested():
            self.finished.emit(self.target_index, final_text)


class DeterministicWorkerFactory:
    def __init__(self, mode="success"):
        self.mode = mode.lower()

    def set_mode(self, mode):
        self.mode = mode.lower()

    def create_worker(self, target_index, prompt, profile):
        return DeterministicTranslationWorker(target_index, prompt, profile, self.mode)
