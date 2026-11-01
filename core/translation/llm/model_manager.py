import threading
from typing import Optional, Dict, Any, Generator
from core.translation.core.backends.base_backend import BaseInferenceBackend
from core.translation.core.backends.llama_cpp_backend import LlamaCppBackend
from core.translation.core.backends.ollama_backend import OllamaBackend

class ModelManager:
    _instance = None

    def __init__(self, backend_type: str = "ollama"):
        self.backend: BaseInferenceBackend
        if backend_type == "ollama":
            self.backend = OllamaBackend()
        elif backend_type == "llama_cpp":
            self.backend = LlamaCppBackend()
        else:
            raise ValueError(f"Backend không hỗ trợ: {backend_type}")

        self.backend_type = backend_type
        self.current_model_name: str = ""
        # AUD-CONCUR-001: Khóa đồng bộ hóa độc quyền chống race condition trên C++ GGUF
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls, backend_type: str = "ollama"):
        if cls._instance is None or cls._instance.backend_type != backend_type:
            cls._instance = cls(backend_type)
        return cls._instance

    def load_model(self, model_name: str, **kwargs) -> bool:
        with self._lock:
            success = self.backend.load_model(model_name, **kwargs)
            if success:
                self.current_model_name = model_name
            return success

    def unload_model(self) -> None:
        with self._lock:
            self.backend.unload_model()
            self.current_model_name = ""

    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        with self._lock:
            return self.backend.generate(prompt, system_prompt=system_prompt, **kwargs)

    def stream(self, prompt: str, system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        with self._lock:
            yield from self.backend.stream(prompt, system_prompt=system_prompt, **kwargs)

    def generate_stream(self, prompt: str, max_tokens: int = 256):
        return self.stream(prompt, max_tokens=max_tokens)

    def cancel(self) -> None:
        # Không acquire lock tại đây để lệnh cancel có thể ngắt ngay luồng stream() đang giữ lock
        self.backend.cancel()

    def get_status(self) -> Dict[str, Any]:
        return self.backend.get_runtime_info()
