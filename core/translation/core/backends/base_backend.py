from abc import ABC, abstractmethod
from typing import Generator, Dict, Any, Optional

class BaseInferenceBackend(ABC):
    @abstractmethod
    def load_model(self, model_identifier: str, **kwargs) -> bool:
        """Khởi tạo mô hình hoặc kết nối tới runtime server."""
        pass

    @abstractmethod
    def unload_model(self) -> None:
        """Giải phóng VRAM/RAM và đóng tiến trình inference."""
        pass

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        """Sinh chuỗi dịch hoàn chỉnh (blocking)."""
        pass

    @abstractmethod
    def stream(self, prompt: str, system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        """Streaming token phục vụ realtime UI rendering."""
        pass

    @abstractmethod
    def cancel(self) -> None:
        """Ngắt phiên inference đang chạy."""
        pass

    @abstractmethod
    def get_runtime_info(self) -> Dict[str, Any]:
        """Trả về thông số: Tên model, Backend type, VRAM usage, Device."""
        pass