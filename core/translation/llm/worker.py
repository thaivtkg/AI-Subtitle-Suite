import os
import re
from PySide6.QtCore import QThread, Signal
from core.translation.llm.model_manager import ModelManager

class TranslationWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(int, str)
    error = Signal(int, str)
    termsExtracted = Signal(int, list)

    def __init__(self, target_index, prompt, profile):
        super().__init__()
        self.target_index = target_index
        self.prompt = prompt
        self.profile = profile
        self.model_path = profile.get("model_path") or os.path.join("models", profile.get("model_name", "qwen2.5-7b-instruct-q4_k_m.gguf"))
        self._is_cancelled = False
        self.extracted_terms = []

    def cancel(self):
        self._is_cancelled = True

    @staticmethod
    def extract_auto_terms(raw_text):
        """Bóc tách cặp từ gốc và nghĩa tiếng Việt từ khối [TỪ GỐC] hoặc các biến thể."""
        if not raw_text:
            return []
        match = re.search(
            r'(?:\[?\s*(?:TỪ GỐC|TU GOC|Từ gốc|TU_GOC|VOCAB|Vocabulary|Thuật ngữ)\s*\]?|(?:Từ gốc|Tu goc|从根源)\s*(?:->|➔|=>|:|=))',
            raw_text,
            re.IGNORECASE
        )
        if not match:
            return []
        terms_block = raw_text[match.start():]
        terms = []
        seen = set()
        for line in terms_block.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'^(?:[-*•]|\d+\.)\s*', '', line).strip()
            line = re.sub(
                r'^(?:\[?\s*(?:TỪ GỐC|TU GOC|Từ gốc|TU_GOC|VOCAB|Vocabulary|Thuật ngữ)\s*\]?|(?:Từ gốc|Tu goc|从根源)\s*(?:->|➔|=>|:|=))\s*',
                '',
                line,
                flags=re.IGNORECASE
            ).strip()
            line = re.sub(r'^(?:->|➔|=>|:|=)\s*', '', line).strip()
            parts = re.split(r'\s*(?:->|➔|=>|:|=)\s*', line, maxsplit=1)
            if len(parts) == 2:
                src = parts[0].strip().strip('"`\'')
                tgt = parts[1].strip().strip('"`\'')
                if src and tgt and src.lower() not in seen:
                    seen.add(src.lower())
                    terms.append({"source": src, "target": tgt})
        return terms

    @staticmethod
    def _visible_translation(raw_text):
        """Return only translated text; keep model reasoning and rogue vocab tags out of UI."""
        if not raw_text:
            return ""
        text = raw_text
        if "</think>" in text:
            text = text.split("</think>", 1)[1]
        elif "<think>" in text:
            return ""
        else:
            for size in range(len("<think>") - 1, 0, -1):
                if text.endswith("<think>"[:size]):
                    text = text[:-size].strip()
                    break

        # Cắt bỏ lặp lại prompt echo nếu model nhắc lại prompt
        if "--- CURRENT SUBTITLE" in text or "--- current subtitle" in text:
            out_match = re.search(r'(?:---\s*Output[^\n]*\n|Translation:\s*\n?)(.*)', text, re.DOTALL | re.IGNORECASE)
            if out_match:
                text = out_match.group(1)
            else:
                return ""

        # Chặn độc thoại suy luận thô nếu model DeepSeek rò rỉ suy luận
        if "So final output:" in text or "Final output:" in text:
            text = re.split(r'(?:So final output:|Final output:)', text, flags=re.IGNORECASE)[-1]
        elif re.search(r'(?:Wait, that can\'t be right|Let\'s think carefully|Alright, I need to translate|Let me break it down)', text, re.IGNORECASE):
            return ""

        # Cắt bỏ bất kỳ dòng nào bắt đầu bằng biến thể từ gốc (TỪ GỐC, -Tu goc->, -从根源->...)
        parts = re.split(
            r'(?im)(?:^\s*[-*•]?\s*|\n\s*[-*•]?\s*)(?:\[?\s*(?:TỪ GỐC|Tu goc|Từ gốc|VOCAB|Vocabulary|Thuật ngữ)\s*\]?|Từ gốc\s*->|Tu goc\s*->|从根源\s*->)',
            text,
            maxsplit=1
        )
        if len(parts) > 1:
            text = parts[0].strip()
        else:
            # Lá chắn chống rò rỉ token dở dang khi stream
            prefixes = [
                "[từ gốc", "[từ gố", "[từ g", "[từ ", "[từ",
                "[tu goc", "[tu go", "[tu g", "[tu ", "[tu",
                "-tu goc", "-tu go", "-tu g", "-tu ", "-tu",
                "-từ gốc", "-từ gố", "-từ g", "-từ ", "-từ",
                "-从根源", "-从根", "-从",
                "[vocab", "[thuật ngữ", "[thuat ngu",
            ]
            text_lower = text.lower().rstrip()
            for p in prefixes:
                if text_lower.endswith(p):
                    cut_len = len(text_lower) - text_lower.rfind(p)
                    text = text.rstrip()[:-cut_len].strip()
                    break

        return text.strip()

    def run(self):
        try:
            # --- 1. KIỂM TRA TỒN TẠI MODEL THẬT (CHẶN HOÀN TOÀN MOCK) ---
            if not os.path.exists(self.model_path):
                self.error.emit(self.target_index, f"Lỗi: Không tìm thấy file model tại '{self.model_path}'. Vui lòng đặt file GGUF vào thư mục models/.")
                return

            # --- 2. NẠP MODEL THẬT QUA MODEL MANAGER ---
            backend_type = "llama_cpp" if self.model_path.lower().endswith(".gguf") else "ollama"
            manager = ModelManager.get_instance(backend_type)
            n_ctx = self.profile.get("n_ctx", 4096)
            n_gpu_layers = self.profile.get("n_gpu_layers", -1)
            
            try:
                manager.load_model(self.model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers)
            except Exception as load_err:
                if n_gpu_layers != 0 and backend_type == "llama_cpp":
                    print(f"[Worker Warning] GPU load failed ({load_err}), falling back to CPU...")
                    manager.unload_model()
                    manager.load_model(self.model_path, n_ctx=min(n_ctx, 2048), n_gpu_layers=0)
                else:
                    raise load_err
            
            # Tăng max_tokens lên 1024 để model có đủ không gian suy luận và trả kết quả
            stream = manager.generate_stream(self.prompt, max_tokens=1024)
            
            raw_text = ""
            is_prefilled_think = "<think>" in self.prompt and not self.prompt.rstrip().endswith("</think>")

            for output in stream:
                if self._is_cancelled:
                    return
                chunk = output["choices"][0]["text"] if isinstance(output, dict) else output
                raw_text += chunk

                # --- 3. ẨN THINK VÀ [TỪ GỐC], CHỈ STREAM PHẦN DỊCH ---
                if is_prefilled_think and "</think>" not in raw_text:
                    display_text = ""
                else:
                    display_text = self._visible_translation(raw_text)

                if display_text:
                    self.progress.emit(self.target_index, display_text)

            if is_prefilled_think and "</think>" in raw_text:
                final_clean = self._visible_translation(raw_text.split("</think>", 1)[1])
                auto_terms = self.extract_auto_terms(raw_text.split("</think>", 1)[1])
            else:
                final_clean = self._visible_translation(raw_text)
                auto_terms = self.extract_auto_terms(raw_text)
            self.extracted_terms = auto_terms
            if final_clean:
                print(f"[CAT] Câu #{self.target_index + 1}: {final_clean}", flush=True)
            if auto_terms:
                self.termsExtracted.emit(self.target_index, auto_terms)
            self.finished.emit(self.target_index, final_clean)
            
        except Exception as e:
            self.error.emit(self.target_index, str(e))

