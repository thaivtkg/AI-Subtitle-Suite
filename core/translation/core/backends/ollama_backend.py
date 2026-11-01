import requests
from typing import Generator, Dict, Any
from .base_backend import BaseInferenceBackend

class OllamaBackend(BaseInferenceBackend):
    def __init__(self, host: str = "http://127.0.0.1:11434"):
        self.host = host.rstrip('/')
        self.current_model: str = ""
        self._is_cancelled: bool = False

    def load_model(self, model_identifier: str, **kwargs) -> bool:
        try:
            res = requests.get(f"{self.host}/api/tags", timeout=3)
            if res.status_code == 200:
                self.current_model = model_identifier
                return True
            return False
        except requests.RequestException:
            return False

    def unload_model(self) -> None:
        # Ép Ollama unload model khỏi VRAM ngay lập tức
        if self.current_model:
            requests.post(f"{self.host}/api/generate", json={"model": self.current_model, "keep_alive": 0}, timeout=5)
            self.current_model = ""

    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        self._is_cancelled = False
        payload = {
            "model": self.current_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.1),
                "num_ctx": kwargs.get("n_ctx", 4096),
                "top_p": kwargs.get("top_p", 0.9)
            }
        }
        res = requests.post(f"{self.host}/api/generate", json=payload, timeout=60)
        res.raise_for_status()
        return res.json().get("response", "").strip()

    def stream(self, prompt: str, system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        self._is_cancelled = False
        payload = {
            "model": self.current_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": True,
            "options": {"temperature": kwargs.get("temperature", 0.1), "num_ctx": kwargs.get("n_ctx", 4096)}
        }
        with requests.post(f"{self.host}/api/generate", json=payload, stream=True, timeout=60) as res:
            for line in res.iter_lines():
                if self._is_cancelled:
                    break
                if line:
                    chunk = requests.compat.json.loads(line)
                    yield chunk.get("response", "")

    def cancel(self) -> None:
        self._is_cancelled = True

    def get_runtime_info(self) -> Dict[str, Any]:
        return {
            "backend": "Ollama (HTTP)",
            "model": self.current_model,
            "status": "Ready" if self.current_model else "No Model Loaded"
        }