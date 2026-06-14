from __future__ import annotations

from services.protocol import codex_text


def test_codex_chat_completion_formats_openai_response(monkeypatch):
    def fake_events(payload):
        assert payload["model"] == "gpt-5.5"
        assert payload["input"][0]["role"] == "user"
        yield {"type": "response.output_text.delta", "delta": "hello"}
        yield {"type": "response.output_text.delta", "delta": " codex"}

    monkeypatch.setattr(codex_text, "_codex_events", fake_events)

    response = codex_text.handle_chat_completion({
        "model": "codex",
        "messages": [{"role": "user", "content": "who are you"}],
    })

    assert response["object"] == "chat.completion"
    assert response["model"] == "codex"
    assert response["choices"][0]["message"]["content"] == "hello codex"


def test_codex_response_formats_responses_response(monkeypatch):
    def fake_events(payload):
        assert payload["model"] == "gpt-5.5"
        yield {"type": "response.output_text.delta", "delta": "response text"}

    monkeypatch.setattr(codex_text, "_codex_events", fake_events)

    response = codex_text.handle_response({
        "model": "codex",
        "input": "say hi",
    })

    assert response["object"] == "response"
    assert response["status"] == "completed"
    assert response["output"][0]["content"][0]["text"] == "response text"


def test_list_codex_accounts_masks_tokens(monkeypatch):
    monkeypatch.setattr(
        codex_text.account_service,
        "list_codex_accounts",
        lambda: [{
            "access_token": "abcdefghijklmnopqrstuvwxyz",
            "email": "user@example.com",
            "type": "Plus",
            "source_type": "codex",
            "status": "正常",
            "quota": 0,
            "image_quota_unknown": True,
        }],
    )

    response = codex_text.list_codex_accounts()

    assert response["total"] == 1
    assert response["available"] == 1
    assert response["items"][0]["token_prefix"] == "abcdefghijkl..."
    assert "access_token" not in response["items"][0]
