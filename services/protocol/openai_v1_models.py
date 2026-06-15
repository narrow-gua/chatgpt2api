from __future__ import annotations

from typing import Any

from services.account_service import account_service
from services.openai_backend_api import OpenAIBackendAPI
from utils.helper import CODEX_IMAGE_MODEL


def _model_item(slug: str, owned_by: str = "chatgpt", created: int = 0) -> dict[str, Any]:
    return {
        "id": slug,
        "object": "model",
        "created": created,
        "owned_by": owned_by,
        "permission": [],
        "root": slug,
        "parent": None,
    }


def _account_model_slugs(account: dict[str, Any]) -> list[str]:
    raw = account.get("model_slugs")
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    slugs: list[str] = []
    for item in raw:
        slug = str(item or "").strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


def _load_account_model_slugs(account: dict[str, Any]) -> list[str]:
    slugs = _account_model_slugs(account)
    if slugs:
        return slugs
    token = str(account.get("access_token") or "").strip()
    if not token:
        return []
    try:
        result = OpenAIBackendAPI(token).list_models()
    except Exception:
        return []
    slugs = [
        slug
        for item in result.get("data", [])
        if isinstance(item, dict) and (slug := str(item.get("id") or "").strip())
    ]
    if slugs:
        account_service.update_account(token, {"model_slugs": slugs}, quiet=True)
    return slugs


def list_models() -> dict[str, Any]:
    accounts = account_service.list_accounts()
    web_text_accounts = [
        account
        for account in accounts
        if isinstance(account, dict)
           and account.get("status") not in {"禁用", "异常"}
           and account_service._normalize_source_type(account.get("source_type")) != "codex"
    ]
    if web_text_accounts:
        model_slugs: set[str] = set()
        for account in web_text_accounts:
            model_slugs.update(_load_account_model_slugs(account))
        data = [_model_item(slug) for slug in sorted(model_slugs)]
        result = {"object": "list", "data": data}
    else:
        result = OpenAIBackendAPI().list_models()
        data = result.get("data")
        if not isinstance(data, list):
            return result

    seen = {str(item.get("id") or "").strip() for item in data if isinstance(item, dict)}
    dynamic_models: set[str] = set()
    web_image_accounts = [
        account
        for account in accounts
        if isinstance(account, dict)
    ]
    codex_types = {
        normalized
        for account in accounts
        if isinstance(account, dict)
           and account_service._normalize_source_type(account.get("source_type")) == "codex"
           and (normalized := account_service._normalize_account_type(account.get("type")))
    }

    if web_image_accounts:
        dynamic_models.add("gpt-image-2")
    if codex_types & {"Plus", "Team", "Pro"}:
        dynamic_models.add(CODEX_IMAGE_MODEL)
    if "Plus" in codex_types:
        dynamic_models.add(f"plus-{CODEX_IMAGE_MODEL}")
    if "Team" in codex_types:
        dynamic_models.add(f"team-{CODEX_IMAGE_MODEL}")
    if "Pro" in codex_types:
        dynamic_models.add(f"pro-{CODEX_IMAGE_MODEL}")

    for model in sorted(dynamic_models):
        if model not in seen:
            data.append(_model_item(model, owned_by="chatgpt2api"))
    return result
