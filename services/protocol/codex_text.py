from __future__ import annotations

import time
import uuid
from typing import Any, Iterable, Iterator

from fastapi import HTTPException

from services.account_service import account_service
from services.openai_backend_api import CODEX_RESPONSES_MODEL, OpenAIBackendAPI
from services.protocol.openai_v1_chat_complete import chat_messages_from_body, completion_chunk, completion_response
from services.protocol.openai_v1_response import messages_from_input, response_completed, response_created, text_output_item
from services.protocol.conversation import count_message_text_tokens, count_text_tokens, normalize_messages
from utils.image_tokens import token_usage


CODEX_PUBLIC_MODEL = "codex"


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    return ""


def _codex_input_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user").strip().lower()
        if role not in {"system", "user", "assistant"}:
            role = "user"
        text = _as_text(message.get("content")).strip()
        if not text:
            continue
        output.append({
            "role": "developer" if role == "system" else role,
            "content": [{"type": "input_text", "text": text}],
        })
    if not output:
        raise HTTPException(status_code=400, detail={"error": "input text is required"})
    return output


def _codex_payload(body: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    model = str(body.get("model") or CODEX_RESPONSES_MODEL).strip() or CODEX_RESPONSES_MODEL
    if model in {"codex", "auto"}:
        model = CODEX_RESPONSES_MODEL
    payload = {
        "model": model,
        "store": bool(body.get("store", False)),
        "input": _codex_input_from_messages(messages),
    }
    instructions = str(body.get("instructions") or "").strip()
    if instructions:
        payload["instructions"] = instructions
    for key in ("reasoning", "tools", "tool_choice", "parallel_tool_calls", "metadata"):
        if key in body:
            payload[key] = body[key]
    return payload


def _event_text_delta(event: dict[str, Any]) -> str:
    delta = event.get("delta")
    if isinstance(delta, str):
        return delta
    if isinstance(delta, dict):
        text = delta.get("text") or delta.get("content")
        if isinstance(text, str):
            return text
    for key in ("text", "content"):
        value = event.get(key)
        if isinstance(value, str) and event.get("type") in {"response.output_text.delta", "thread.message.delta"}:
            return value
    return ""


def _extract_text(value: Any) -> str:
    if isinstance(value, dict):
        value_type = str(value.get("type") or "")
        if value_type in {"output_text", "input_text"} and isinstance(value.get("text"), str):
            return value["text"]
        texts: list[str] = []
        for key in ("output_text",):
            item = value.get(key)
            if isinstance(item, str):
                texts.append(item)
        for item in value.values():
            nested = _extract_text(item)
            if nested:
                texts.append(nested)
        return "".join(texts)
    if isinstance(value, list):
        return "".join(_extract_text(item) for item in value)
    return ""


def _event_final_text(event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "")
    if event_type not in {"response.completed", "response.done"} and "response" not in event:
        return ""
    response = event.get("response")
    if isinstance(response, dict):
        return _extract_text(response.get("output"))
    return _extract_text(event.get("output"))


def _codex_events(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    attempted: set[str] = set()
    last_error: Exception | None = None
    for _ in range(3):
        token = account_service.get_codex_access_token(attempted)
        if not token:
            break
        attempted.add(token)
        try:
            backend = OpenAIBackendAPI(access_token=token)
            yield from backend.iter_codex_response_events(payload)
            account_service.mark_text_used(token)
            return
        except Exception as exc:
            last_error = exc
            account = account_service.get_account(token) or {}
            status = "限流" if getattr(exc, "status_code", None) == 429 else "异常"
            account_service.update_account(token, {"status": status}, quiet=True)
            if getattr(exc, "status_code", None) not in {401, 403, 429}:
                raise
    if last_error:
        raise last_error
    raise RuntimeError("no available codex account")


def collect_codex_text(events: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []
    final_text = ""
    for event in events:
        delta = _event_text_delta(event)
        if delta:
            parts.append(delta)
        text = _event_final_text(event)
        if text:
            final_text = text
    return final_text or "".join(parts)


def stream_codex_response(body: dict[str, Any], messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    public_model = str(body.get("model") or CODEX_PUBLIC_MODEL).strip() or CODEX_PUBLIC_MODEL
    response_id = f"resp_{uuid.uuid4().hex}"
    item_id = f"msg_{uuid.uuid4().hex}"
    created = int(time.time())
    full_text = ""
    final_text = ""
    yield response_created(response_id, public_model, created)
    yield {"type": "response.output_item.added", "output_index": 0, "item": text_output_item("", item_id, "in_progress")}
    for event in _codex_events(_codex_payload(body, messages)):
        delta = _event_text_delta(event)
        if delta:
            full_text += delta
            yield {"type": "response.output_text.delta", "item_id": item_id, "output_index": 0, "content_index": 0, "delta": delta}
            continue
        event_final_text = _event_final_text(event)
        if event_final_text:
            final_text = event_final_text
    if not full_text and final_text:
        full_text = final_text
        yield {"type": "response.output_text.delta", "item_id": item_id, "output_index": 0, "content_index": 0, "delta": final_text}
    yield {"type": "response.output_text.done", "item_id": item_id, "output_index": 0, "content_index": 0, "text": full_text}
    item = text_output_item(full_text, item_id, "completed")
    yield {"type": "response.output_item.done", "output_index": 0, "item": item}
    usage = token_usage(
        input_text_tokens=count_message_text_tokens(messages, public_model),
        input_image_tokens=0,
        output_text_tokens=count_text_tokens(full_text, public_model),
    )
    yield response_completed(response_id, public_model, created, [item], usage)


def codex_response(body: dict[str, Any]) -> dict[str, Any]:
    messages = normalize_messages(messages_from_input(body.get("input"), body.get("instructions")))
    events = stream_codex_response(body, messages)
    completed: dict[str, Any] = {}
    for event in events:
        if event.get("type") == "response.completed":
            response = event.get("response")
            if isinstance(response, dict):
                completed = response
    if not completed:
        raise RuntimeError("codex response generation failed")
    return completed


def codex_response_events(body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    messages = normalize_messages(messages_from_input(body.get("input"), body.get("instructions")))
    yield from stream_codex_response(body, messages)


def stream_codex_chat_completion(body: dict[str, Any], messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    public_model = str(body.get("model") or CODEX_PUBLIC_MODEL).strip() or CODEX_PUBLIC_MODEL
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    sent_role = False
    final_text = ""
    for event in _codex_events(_codex_payload(body, messages)):
        delta = _event_text_delta(event)
        if not delta:
            event_final_text = _event_final_text(event)
            if event_final_text:
                final_text = event_final_text
            continue
        if not sent_role:
            sent_role = True
            yield completion_chunk(public_model, {"role": "assistant", "content": delta}, None, completion_id, created)
        else:
            yield completion_chunk(public_model, {"content": delta}, None, completion_id, created)
    if not sent_role and final_text:
        sent_role = True
        yield completion_chunk(public_model, {"role": "assistant", "content": final_text}, None, completion_id, created)
    if not sent_role:
        yield completion_chunk(public_model, {"role": "assistant", "content": ""}, None, completion_id, created)
    yield completion_chunk(public_model, {}, "stop", completion_id, created)


def codex_chat_completion(body: dict[str, Any]) -> dict[str, Any]:
    messages = normalize_messages(chat_messages_from_body(body))
    text = collect_codex_text(_codex_events(_codex_payload(body, messages)))
    return completion_response(
        str(body.get("model") or CODEX_PUBLIC_MODEL).strip() or CODEX_PUBLIC_MODEL,
        text,
        messages=messages,
    )


def codex_chat_completion_events(body: dict[str, Any]) -> Iterator[dict[str, Any]]:
    messages = normalize_messages(chat_messages_from_body(body))
    yield from stream_codex_chat_completion(body, messages)


def handle_response(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    if body.get("stream"):
        return codex_response_events(body)
    return codex_response(body)


def handle_chat_completion(body: dict[str, Any]) -> dict[str, Any] | Iterator[dict[str, Any]]:
    if body.get("stream"):
        return codex_chat_completion_events(body)
    return codex_chat_completion(body)


def list_codex_accounts() -> dict[str, Any]:
    items = []
    for account in account_service.list_codex_accounts():
        token = str(account.get("access_token") or "")
        items.append({
            "email": account.get("email"),
            "type": account.get("type"),
            "source_type": account.get("source_type"),
            "status": account.get("status"),
            "quota": account.get("quota"),
            "quota_state": "unknown" if account.get("image_quota_unknown") else "local_image_quota",
            "last_used_at": account.get("last_used_at"),
            "restore_at": account.get("restore_at"),
            "token_prefix": f"{token[:12]}..." if token else "",
        })
    return {
        "object": "list",
        "total": len(items),
        "available": sum(1 for item in items if item.get("status") not in {"禁用", "异常", "限流"}),
        "items": items,
    }
