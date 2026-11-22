import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ModelMetadata:
    model_id: str
    display_name: str
    filename: str
    size_bytes: int
    size_gb_formatted: str
    min_vram_gb: float
    min_ram_gb: float
    recommended_ctx: int
    download_url: str
    description: str
    is_cloud: bool = False
    provider: str = "local"
    cloud_model_name: str = ""


MODEL_CATALOG: Dict[str, ModelMetadata] = {
    "qwen2.5-7b-instruct-q4_k_m": ModelMetadata(
        model_id="qwen2.5-7b-instruct-q4_k_m",
        display_name="Qwen 2.5 7B Instruct (Q4_K_M)",
        filename="qwen2.5-7b-instruct-q4_k_m.gguf",
        size_bytes=4683074240,
        size_gb_formatted="4.36 GB",
        min_vram_gb=6.5,
        min_ram_gb=8.0,
        recommended_ctx=4096,
        download_url="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        description="Tiêu chuẩn vàng cho dịch thuật và bản địa hóa phụ đề tiếng Việt. Cân bằng hoàn hảo giữa ngữ pháp tự nhiên và tốc độ.",
    ),
    "qwen2.5-3b-instruct-q4_k_m": ModelMetadata(
        model_id="qwen2.5-3b-instruct-q4_k_m",
        display_name="Qwen 2.5 3B Instruct (Q4_K_M)",
        filename="qwen2.5-3b-instruct-q4_k_m.gguf",
        size_bytes=2104932768,
        size_gb_formatted="1.96 GB",
        min_vram_gb=3.5,
        min_ram_gb=4.0,
        recommended_ctx=4096,
        download_url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        description="Mô hình siêu nhẹ, tốc độ dịch cực nhanh. Tối ưu cho GPU cấu hình thấp (VRAM < 4GB) hoặc máy chạy thuần CPU.",
    ),
    "qwen2.5-14b-instruct-q4_k_m": ModelMetadata(
        model_id="qwen2.5-14b-instruct-q4_k_m",
        display_name="Qwen 2.5 14B Instruct (Q4_K_M)",
        filename="qwen2.5-14b-instruct-q4_k_m.gguf",
        size_bytes=8988110976,
        size_gb_formatted="8.37 GB",
        min_vram_gb=12.0,
        min_ram_gb=16.0,
        recommended_ctx=4096,
        download_url="https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        description="Chất lượng dịch thuật cao cấp nhất, nắm bắt xuất sắc tiếng lóng và sắc thái văn hóa phức tạp. Yêu cầu GPU mạnh (VRAM ≥ 12GB).",
    ),
    "deepseek-r1-distill-qwen-7b-q4_k_m": ModelMetadata(
        model_id="deepseek-r1-distill-qwen-7b-q4_k_m",
        display_name="DeepSeek R1 Distill Qwen 7B (Q4_K_M)",
        filename="deepseek-r1-distill-qwen-7b-q4_k_m.gguf",
        size_bytes=4683073248,
        size_gb_formatted="4.36 GB",
        min_vram_gb=6.5,
        min_ram_gb=8.0,
        recommended_ctx=4096,
        download_url="https://huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        description="Tăng cường khả năng suy luận ngữ cảnh sâu, thích hợp cho các bộ phim có đối thoại ẩn ý và cấu trúc câu phức tạp.",
    ),
    "qwen3-8b-q4_k_m": ModelMetadata(
        model_id="qwen3-8b-q4_k_m",
        display_name="Qwen 8B Default (Q4_K_M)",
        filename="qwen3-8b-q4_k_m.gguf",
        size_bytes=5027783872,
        size_gb_formatted="4.68 GB",
        min_vram_gb=6.5,
        min_ram_gb=8.0,
        recommended_ctx=4096,
        download_url="",
        description="Mô hình mặc định có sẵn trong hệ thống.",
    ),
    "llama-3.1-8b-instruct-q4_k_m": ModelMetadata(
        model_id="llama-3.1-8b-instruct-q4_k_m",
        display_name="Llama 3.1 8B Instruct (Q4_K_M)",
        filename="Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        size_bytes=4920000000,
        size_gb_formatted="4.58 GB",
        min_vram_gb=6.5,
        min_ram_gb=8.0,
        recommended_ctx=4096,
        download_url="https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        description="Mô hình mã nguồn mở hàng đầu từ Meta. Khả năng dịch đàm thoại tự nhiên, câu văn mượt mà và triệt tiêu hoàn toàn lỗi lẫn chữ Hán.",
    ),
    "llama-3.3-8b-instruct-q4_k_m": ModelMetadata(
        model_id="llama-3.3-8b-instruct-q4_k_m",
        display_name="Llama 3.3 8B Instruct (Q4_K_M)",
        filename="allura-forge_Llama-3.3-8B-Instruct-Q4_K_M.gguf",
        size_bytes=4920734720,
        size_gb_formatted="4.58 GB",
        min_vram_gb=6.5,
        min_ram_gb=8.0,
        recommended_ctx=4096,
        download_url="https://huggingface.co/bartowski/allura-forge_Llama-3.3-8B-Instruct-GGUF/resolve/main/allura-forge_Llama-3.3-8B-Instruct-Q4_K_M.gguf",
        description="Phiên bản tinh chỉnh 8B kiến trúc Llama 3.3 mở công khai. Nắm bắt xuất sắc ẩn ý hội thoại và cấu trúc phụ đề dài.",
    ),
    "translategemma-9b-q4_k_m": ModelMetadata(
        model_id="translategemma-9b-q4_k_m",
        display_name="TranslateGemma / Gemma 2 9B IT (Q4_K_M)",
        filename="gemma-2-9b-it-Q4_K_M.gguf",
        size_bytes=5820000000,
        size_gb_formatted="5.42 GB",
        min_vram_gb=7.5,
        min_ram_gb=10.0,
        recommended_ctx=4096,
        download_url="https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q4_K_M.gguf",
        description="Kiến trúc dịch thuật chuyên sâu từ Google DeepMind (4-bit). Cân bằng tốt giữa tốc độ và bộ nhớ, không bao giờ lẫn ký tự CJK.",
    ),
    "translategemma-9b-q5_k_m": ModelMetadata(
        model_id="translategemma-9b-q5_k_m",
        display_name="TranslateGemma / Gemma 2 9B IT (Q5_K_M)",
        filename="gemma-2-9b-it-Q5_K_M.gguf",
        size_bytes=7140000000,
        size_gb_formatted="6.65 GB",
        min_vram_gb=8.5,
        min_ram_gb=12.0,
        recommended_ctx=4096,
        download_url="https://huggingface.co/bartowski/gemma-2-9b-it-GGUF/resolve/main/gemma-2-9b-it-Q5_K_M.gguf",
        description="Phiên bản 5-bit lượng tử hóa cao cấp của Google Gemma 2 9B. Giữ trọn độ chính xác Kanji, kính ngữ và sắc thái ngữ pháp tiếng Nhật phức tạp vượt trội so với bản Q4.",
    ),
    "gemini-3.8-flash": ModelMetadata(
        model_id="gemini-3.8-flash",
        display_name="Google Gemini 3.8 Flash (Cloud API)",
        filename="gemini-3.8-flash",
        size_bytes=0,
        size_gb_formatted="Cloud API",
        min_vram_gb=0.0,
        min_ram_gb=0.0,
        recommended_ctx=65536,
        download_url="",
        description="Mô hình đám mây tốc độ cao mới nhất từ Google Gemini API. Không tốn VRAM/RAM cục bộ, dịch tự nhiên đa ngôn ngữ (yêu cầu Gemini API Key).",
        is_cloud=True,
        provider="gemini",
        cloud_model_name="gemini-3.8-flash",
    ),
    "gemini-3.1-pro-preview": ModelMetadata(
        model_id="gemini-3.1-pro-preview",
        display_name="Google Gemini 3.1 Pro Preview (Cloud API)",
        filename="gemini-3.1-pro-preview",
        size_bytes=0,
        size_gb_formatted="Cloud API",
        min_vram_gb=0.0,
        min_ram_gb=0.0,
        recommended_ctx=65536,
        download_url="",
        description="Mô hình suy luận & ngữ cảnh cao cấp từ Google Gemini API cho hội thoại phức tạp và văn phong sâu sắc (yêu cầu Gemini API Key).",
        is_cloud=True,
        provider="gemini",
        cloud_model_name="gemini-3.1-pro-preview",
    ),
    "gemini-3.5-flash-lite": ModelMetadata(
        model_id="gemini-3.5-flash-lite",
        display_name="Google Gemini 3.5 Flash Lite (Cloud API)",
        filename="gemini-3.5-flash-lite",
        size_bytes=0,
        size_gb_formatted="Cloud API",
        min_vram_gb=0.0,
        min_ram_gb=0.0,
        recommended_ctx=32768,
        download_url="",
        description="Mô hình Google Gemini nhẹ, phản hồi cực nhanh và tiết kiệm chi phí qua Cloud API (yêu cầu Gemini API Key).",
        is_cloud=True,
        provider="gemini",
        cloud_model_name="gemini-3.5-flash-lite",
    ),
}


def calculate_recommendation(
    model: ModelMetadata,
    gpu_info: dict,
    llama_has_cuda: bool = True,
    ram_gb: float = 16.0,
) -> Tuple[str, str]:
    """
    Tính toán mức độ khuyên dùng (Advisory Recommendation) cho một model dựa trên phần cứng.
    Trả về: (badge, reason)
    badge: 'RECOMMENDED' | 'COMPATIBLE' | 'NOT_RECOMMENDED'
    """
    if getattr(model, "is_cloud", False):
        return "RECOMMENDED", "Chạy trực tiếp trên Google Gemini Cloud API, không tiêu tốn VRAM/RAM cục bộ."

    has_gpu = bool(gpu_info.get("has_gpu_hardware", False)) and llama_has_cuda
    vram = float(gpu_info.get("vram_gb", 0.0)) if has_gpu else 0.0

    if has_gpu:
        if vram >= model.min_vram_gb:
            if vram >= 11.5 and model.min_vram_gb >= 11.0:
                return "RECOMMENDED", "Tối ưu cho GPU cao cấp của bạn (Full GPU Offload)."
            elif vram >= 6.0 and 6.0 <= model.min_vram_gb <= 8.0:
                return "RECOMMENDED", "Cấu hình chuẩn tối ưu nhất cho GPU hiện tại."
            elif vram < 6.0 and model.min_vram_gb <= 4.0:
                return "RECOMMENDED", "Mô hình phù hợp nhất cho dung lượng VRAM hiện có."
            else:
                return "COMPATIBLE", "Tương thích hoàn toàn, chạy mượt mà trên GPU."
        elif ram_gb >= model.min_ram_gb:
            if model.min_vram_gb <= 4.0:
                return "RECOMMENDED", f"Mô hình phù hợp nhất cho GPU cấu hình thấp ({vram:.1f}GB VRAM) + RAM hệ thống."
            elif model.min_vram_gb <= 8.0:
                return "COMPATIBLE", f"Chạy được ở chế độ kết hợp GPU ({vram:.1f}GB VRAM) + RAM hệ thống."
            else:
                return "NOT_RECOMMENDED", f"VRAM ({vram:.1f}GB) quá thấp so với yêu cầu ({model.min_vram_gb}GB), có thể gây suy giảm tốc độ."
        else:
            return "NOT_RECOMMENDED", f"VRAM ({vram:.1f}GB) và RAM ({ram_gb:.1f}GB) thấp hơn mức yêu cầu."
    else:
        # Chế độ CPU
        if model.min_ram_gb <= 4.0 and ram_gb >= 6.0:
            return "RECOMMENDED", "Mô hình nhẹ nhất, tối ưu khi chạy trên CPU."
        elif ram_gb >= model.min_ram_gb:
            return "COMPATIBLE", "Có thể chạy trên CPU và RAM hệ thống nhưng tốc độ sẽ chậm hơn GPU."
        else:
            return "NOT_RECOMMENDED", f"Dung lượng RAM hệ thống ({ram_gb:.1f}GB) không đủ cho mô hình này ({model.min_ram_gb}GB)."


def scan_local_models(models_dir: str) -> Dict[str, bool]:
    """
    Quét thư mục models/ để kiểm tra sự tồn tại của các file model .gguf hợp lệ.
    Trả về dict {model_id: bool}
    """
    availability: Dict[str, bool] = {}
    if not os.path.exists(models_dir):
        return {model_id: False for model_id in MODEL_CATALOG}

    existing_files = set(os.listdir(models_dir))
    for model_id, meta in MODEL_CATALOG.items():
        # Model tồn tại nếu file .gguf có trên đĩa và không phải là file .part rỗng
        is_present = meta.filename in existing_files
        if is_present:
            full_path = os.path.join(models_dir, meta.filename)
            try:
                is_present = os.path.getsize(full_path) > 0
            except OSError:
                is_present = False
        availability[model_id] = is_present

    return availability
