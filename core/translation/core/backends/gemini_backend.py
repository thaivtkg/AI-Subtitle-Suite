import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Generator, List, Tuple

from .base_backend import BaseInferenceBackend

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _scrub_key(text: str) -> str:
    return re.sub(r"([?&]key=)[^&\s'\"]+", r"\1***", str(text or ""))


def _extract_http_error_message(code: int, body: str) -> str:
    detail = ""
    try:
        parsed = json.loads(body)
        detail = str(parsed.get("error", {}).get("message", "")).strip()
    except Exception:
        detail = _scrub_key(body).strip()

    if code in (400, 401, 403):
        if "API_KEY_INVALID" in body or "API key not valid" in detail or code in (401, 403):
            return f"API Key không hợp lệ hoặc không có quyền truy cập ({code})."
        return f"Yêu cầu Gemini không hợp lệ ({code}): {detail or 'Kiểm tra lại API Key.'}"
    if code == 404:
        return f"Không tìm thấy model trên Gemini API (404): {detail}"
    if code == 429:
        return "Đã vượt quá giới hạn lượt gọi / quota của Gemini API (429)."
    if code >= 500:
        return f"Máy chủ Gemini đang bận ({code}), vui lòng thử lại sau."
    return f"Lỗi Gemini API ({code}): {detail}"


class GeminiBackend(BaseInferenceBackend):
    """Cloud inference backend using Google Gemini REST API (SSE streaming + live discovery)."""

    DEFAULT_MODEL = "gemini-3.8-flash"

    def __init__(self, api_key: str = "", timeout: float = 45.0):
        self.api_key: str = (api_key or "").strip()
        self.current_model: str = ""
        self.timeout: float = timeout
        self._is_cancelled: bool = False
        self._active_response = None

    def load_model(self, model_identifier: str, **kwargs) -> bool:
        api_key = str(kwargs.get("api_key") or self.api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        if not model_identifier or not api_key:
            return False
        self.current_model = str(model_identifier).strip()
        self.api_key = api_key
        self._is_cancelled = False
        return True

    def unload_model(self) -> None:
        self.cancel()
        self.current_model = ""

    def cancel(self) -> None:
        self._is_cancelled = True
        resp = self._active_response
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def _build_payload(self, prompt: str, system_prompt: str = "", **kwargs) -> dict:
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": float(kwargs.get("temperature", 0.1)),
                "topP": float(kwargs.get("top_p", 0.9)),
                "maxOutputTokens": int(kwargs.get("max_tokens", 1024)),
            },
        }
        if system_prompt and system_prompt.strip():
            payload["systemInstruction"] = {"parts": [{"text": system_prompt.strip()}]}
        return payload

    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        return "".join(self.stream(prompt, system_prompt=system_prompt, **kwargs)).strip()

    def stream(self, prompt: str, system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        self._is_cancelled = False
        if not self.current_model:
            raise RuntimeError("Chưa chọn model Gemini.")
        api_key = (kwargs.get("api_key") or self.api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("Chưa cấu hình Gemini API Key.")

        encoded_model = urllib.parse.quote(self.current_model, safe="")
        url = f"{_API_BASE}/{encoded_model}:streamGenerateContent?alt=sse&key={urllib.parse.quote(api_key, safe='')}"
        data = json.dumps(self._build_payload(prompt, system_prompt, **kwargs)).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._active_response = resp
                for raw_line in resp:
                    if self._is_cancelled:
                        break
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        chunk_obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    for cand in chunk_obj.get("candidates", []):
                        parts = cand.get("content", {}).get("parts", [])
                        for part in parts:
                            if part.get("thought") is True:
                                continue
                            text = part.get("text", "")
                            if text:
                                yield text
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(_extract_http_error_message(exc.code, body)) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            if self._is_cancelled:
                return
            raise RuntimeError(f"Lỗi kết nối mạng tới Gemini: {_scrub_key(str(exc))}") from None
        finally:
            self._active_response = None

    @staticmethod
    def list_available_models(
        api_key: str,
        timeout: float = 10.0,
    ) -> Tuple[bool, List[Dict[str, str]], str]:
        """Validate API key against /v1beta/models and return text-capable Gemini models."""
        key = str(api_key or "").strip()
        if not key:
            return False, [], "Vui lòng nhập Gemini API Key."

        url = f"{_API_BASE}?pageSize=100&key={urllib.parse.quote(key, safe='')}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            return False, [], _extract_http_error_message(exc.code, body)
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            return False, [], f"Không thể kết nối Google Gemini: {_scrub_key(str(exc))}"
        except Exception as exc:
            return False, [], f"Lỗi kiểm tra kết nối: {_scrub_key(str(exc))}"

        discovered: List[Dict[str, str]] = []
        skip_tokens = ("embedding", "imagen", "veo", "aqa", "-tts", "-image", "robotics", "computer-use", "deep-research")
        for item in payload.get("models", []):
            raw_name = str(item.get("name", ""))
            model_id = raw_name.split("/")[-1].strip()
            if not model_id.startswith("gemini-"):
                continue
            if any(tok in model_id.lower() for tok in skip_tokens):
                continue
            methods = item.get("supportedGenerationMethods") or []
            if methods and "generateContent" not in methods:
                continue
            discovered.append({
                "model_id": model_id,
                "display_name": str(item.get("displayName") or model_id),
                "description": str(item.get("description") or "").strip(),
            })

        return True, discovered, ""

    @staticmethod
    def test_connection(
        api_key: str,
        model_identifier: str = DEFAULT_MODEL,
        timeout: float = 10.0,
    ) -> Tuple[bool, str]:
        ok, models, err_msg = GeminiBackend.list_available_models(api_key, timeout=timeout)
        if not ok:
            return False, err_msg
        if not models:
            # Fallback direct probe if list returned empty
            key = str(api_key or "").strip()
            model_id = str(model_identifier or GeminiBackend.DEFAULT_MODEL).strip()
            encoded_model = urllib.parse.quote(model_id, safe="")
            url = f"{_API_BASE}/{encoded_model}?key={urllib.parse.quote(key, safe='')}"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    display_name = data.get("displayName") or model_id
                    return True, f"Kết nối thành công ({display_name})"
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                return False, _extract_http_error_message(exc.code, body)
            except Exception as exc:
                return False, f"Lỗi kiểm tra kết nối: {_scrub_key(str(exc))}"

        wanted = str(model_identifier or "").strip()
        match = next((m for m in models if m["model_id"] == wanted), None) or models[0]
        return True, f"Kết nối thành công ({match['display_name']} · {len(models)} model khả dụng)"

    def get_runtime_info(self) -> Dict[str, Any]:
        return {
            "backend": "gemini_cloud",
            "model": self.current_model,
            "device": "Cloud API",
        }
