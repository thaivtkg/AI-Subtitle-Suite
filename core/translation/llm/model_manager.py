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

    @classmethod
    def get_instance(cls, backend_type: str = "ollama"):
        if cls._instance is None or cls._instance.backend_type != backend_type:
            cls._instance = cls(backend_type)
        return cls._instance

    def load_model(self, model_name: str, **kwargs) -> bool:
        success = self.backend.load_model(model_name, **kwargs)
        if success:
            self.current_model_name = model_name
        return success

    def unload_model(self) -> None:
        self.backend.unload_model()
        self.current_model_name = ""

    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        return self.backend.generate(prompt, system_prompt=system_prompt, **kwargs)

    def stream(self, prompt: str, system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        return self.backend.stream(prompt, system_prompt=system_prompt, **kwargs)

    def generate_stream(self, prompt: str, max_tokens: int = 256):
        return self.stream(prompt, max_tokens=max_tokens)

    def cancel(self) -> None:
        self.backend.cancel()

    def get_status(self) -> Dict[str, Any]:
        return self.backend.get_runtime_info()

