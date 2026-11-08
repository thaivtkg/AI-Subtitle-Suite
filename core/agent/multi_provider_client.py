from dataclasses import dataclass
import json
import logging
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    name: str
    provider_type: str  # "gemini", "openai", "claude", "openrouter", "custom"
    api_key: str
    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None
    timeout_seconds: float = 12.0

    def get_effective_base_url(self) -> str:
        if self.base_url:
            return self.base_url.rstrip("/")
        if self.provider_type == "openai":
            return "https://api.openai.com/v1"
        elif self.provider_type == "gemini":
            # Gemini OpenAI-compatible endpoint
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        elif self.provider_type == "openrouter":
            return "https://openrouter.ai/api/v1"
        return "https://api.openai.com/v1"


class MultiProviderLLMClient:
    """
    Multi-Provider Client with 3-tier Hybrid Fallback:
    1. Online Provider 1 (Primary)
    2. Retry with Backup Online Providers (up to 2 retries / 3 attempts total)
    3. Seamless Fallback to Local Offline GGUF with notice.
    """

    def __init__(self, local_worker=None):
        self.local_worker = local_worker

    def generate_with_fallback(
        self,
        messages: List[Dict[str, Any]],
        online_configs: Optional[List[ProviderConfig]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        allow_local_fallback: bool = True,
    ) -> Dict[str, Any]:
        configs = online_configs or []
        fallback_notices: List[str] = []
        max_online_attempts = min(3, len(configs))

        for idx in range(max_online_attempts):
            cfg = configs[idx]
            try:
                result = self._call_online(cfg, messages, tools)
                result["provider_used"] = cfg.name
                if idx > 0:
                    result["fallback_triggered"] = True
                    notice = f"Mất kết nối với mô hình trước, đã chuyển sang dùng {cfg.name}."
                    result["fallback_notice"] = notice
                else:
                    result["fallback_triggered"] = False
                return result
            except Exception as e:
                logger.warning("Online provider %s failed: %s", cfg.name, e)
                fallback_notices.append(f"{cfg.name}: {str(e)}")

        # All online attempts failed or none configured
        if allow_local_fallback:
            try:
                local_result = self._call_local(messages, tools)
                local_result["provider_used"] = "Local-GGUF"
                local_result["fallback_triggered"] = True
                notice = "Mạng online bị gián đoạn, đã tự động chuyển sang mô hình Local để tiếp tục tác vụ cho bạn."
                local_result["fallback_notice"] = notice
                return local_result
            except Exception as e:
                logger.error("Local fallback also failed: %s", e)
                raise RuntimeError(f"All online providers and local fallback failed: {e}") from e

        raise ConnectionError(f"All {max_online_attempts} online providers failed: {fallback_notices}")

    def _call_online(
        self,
        config: ProviderConfig,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        url = f"{config.get_effective_base_url()}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        }

        payload: Dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                return {
                    "role": message.get("role", "assistant"),
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls", []),
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise ConnectionError(f"HTTP {e.code}: {err_body}") from e
        except Exception as e:
            raise ConnectionError(str(e)) from e

    def _call_local(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if self.local_worker and hasattr(self.local_worker, "generate"):
            return self.local_worker.generate(messages, tools)

        # Basic default local response when worker not passed directly
        last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        return {
            "role": "assistant",
            "content": f"Đã nhận lệnh từ Local LLM: {last_user}",
            "tool_calls": [],
        }
