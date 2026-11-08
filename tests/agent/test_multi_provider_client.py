import pytest
from unittest.mock import MagicMock
from core.agent.multi_provider_client import MultiProviderLLMClient, ProviderConfig

def test_multi_provider_fallback_to_local_on_network_failure():
    client = MultiProviderLLMClient()
    
    # 2 online providers fail
    client._call_online = MagicMock(side_effect=[
        ConnectionError("Gemini timeout"),
        ConnectionError("OpenAI quota exceeded")
    ])
    client._call_local = MagicMock(return_value={
        "role": "assistant",
        "content": "Kế hoạch 3 bước: ASR -> Dịch -> Hardsub"
    })
    
    configs = [
        ProviderConfig(name="Gemini-Flash", provider_type="gemini", api_key="gem_1", model="gemini-2.0-flash"),
        ProviderConfig(name="OpenAI-Mini", provider_type="openai", api_key="sk_1", model="gpt-4o-mini")
    ]
    
    res = client.generate_with_fallback(
        messages=[{"role": "user", "content": "Tạo sub"}],
        online_configs=configs,
        allow_local_fallback=True
    )
    
    assert client._call_online.call_count == 2
    assert client._call_local.call_count == 1
    assert "Kế hoạch 3 bước" in res["content"]
    assert res["fallback_triggered"] is True
    assert "đã tự động chuyển sang mô hình Local" in res.get("fallback_notice", "")

def test_multi_provider_succeeds_on_first_try():
    client = MultiProviderLLMClient()
    client._call_online = MagicMock(return_value={
        "role": "assistant",
        "content": "Kế hoạch từ Gemini"
    })
    client._call_local = MagicMock()
    
    configs = [
        ProviderConfig(name="Gemini-Flash", provider_type="gemini", api_key="gem_1", model="gemini-2.0-flash")
    ]
    
    res = client.generate_with_fallback(
        messages=[{"role": "user", "content": "Tạo sub"}],
        online_configs=configs,
        allow_local_fallback=True
    )
    
    assert client._call_online.call_count == 1
    assert client._call_local.call_count == 0
    assert res["content"] == "Kế hoạch từ Gemini"
    assert res.get("fallback_triggered", False) is False

def test_multi_provider_succeeds_on_second_retry():
    client = MultiProviderLLMClient()
    client._call_online = MagicMock(side_effect=[
        ConnectionError("Gemini down"),
        {"role": "assistant", "content": "Kế hoạch từ OpenAI Backup"}
    ])
    client._call_local = MagicMock()
    
    configs = [
        ProviderConfig(name="Gemini-Flash", provider_type="gemini", api_key="gem_1", model="gemini-2.0-flash"),
        ProviderConfig(name="OpenAI-Mini", provider_type="openai", api_key="sk_1", model="gpt-4o-mini")
    ]
    
    res = client.generate_with_fallback(
        messages=[{"role": "user", "content": "Tạo sub"}],
        online_configs=configs,
        allow_local_fallback=True
    )
    
    assert client._call_online.call_count == 2
    assert client._call_local.call_count == 0
    assert res["content"] == "Kế hoạch từ OpenAI Backup"
    assert res.get("fallback_triggered", False) is True
    assert "OpenAI-Mini" in res.get("fallback_notice", "")
