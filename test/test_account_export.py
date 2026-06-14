import base64
import json
import unittest
from typing import Any

from services.account_service import AccountService
from services.openai_backend_api import OpenAIBackendAPI


class MemoryStorage:
    def __init__(self, accounts: list[dict[str, Any]] | None = None) -> None:
        self.accounts = list(accounts or [])

    def load_accounts(self) -> list[dict[str, Any]]:
        return list(self.accounts)

    def save_accounts(self, accounts: list[dict[str, Any]]) -> None:
        self.accounts = list(accounts)

    def load_auth_keys(self) -> list[dict[str, Any]]:
        return []

    def save_auth_keys(self, auth_keys: list[dict[str, Any]]) -> None:
        pass

    def health_check(self) -> dict[str, Any]:
        return {"ok": True}

    def get_backend_info(self) -> dict[str, Any]:
        return {"type": "memory"}


def make_jwt(payload: dict[str, Any]) -> str:
    def encode(value: dict[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f'{encode({"alg": "none", "typ": "JWT"})}.{encode(payload)}.sig'


class AccountExportTests(unittest.TestCase):
    def test_build_export_items_uses_codex_shape_and_jwt_claims(self) -> None:
        access_token = make_jwt(
            {
                "exp": 0,
                "iat": 3600,
                "https://api.openai.com/auth": {"chatgpt_account_id": "acct_123"},
                "https://api.openai.com/profile": {"email": "test@example.com"},
            }
        )
        id_token = make_jwt({"email": "fallback@example.com"})
        service = AccountService(
            MemoryStorage(
                [
                    {
                        "access_token": access_token,
                        "id_token": id_token,
                        "refresh_token": "rt_test",
                    }
                ]
            )
        )

        [item] = service.build_export_items([access_token])

        self.assertEqual(item["type"], "codex")
        self.assertEqual(item["email"], "test@example.com")
        self.assertEqual(item["expired"], "1970-01-01T08:00:00+08:00")
        self.assertEqual(item["account_id"], "acct_123")
        self.assertEqual(item["access_token"], access_token)
        self.assertEqual(item["last_refresh"], "1970-01-01T09:00:00+08:00")
        self.assertEqual(item["id_token"], id_token)
        self.assertEqual(item["refresh_token"], "rt_test")

    def test_build_export_items_skips_accounts_missing_complete_tokens(self) -> None:
        complete_access_token = make_jwt({"exp": 0})
        complete_id_token = make_jwt({"email": "complete@example.com"})
        service = AccountService(
            MemoryStorage(
                [
                    {"access_token": "only_access"},
                    {"access_token": "missing_id", "refresh_token": "rt_missing_id"},
                    {"access_token": complete_access_token, "id_token": complete_id_token, "refresh_token": "rt_complete"},
                ]
            )
        )

        items = service.build_export_items()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["access_token"], complete_access_token)
        self.assertEqual(items[0]["id_token"], complete_id_token)
        self.assertEqual(items[0]["refresh_token"], "rt_complete")

    def test_add_account_items_preserves_export_fields_without_overwriting_plan_type(self) -> None:
        service = AccountService(MemoryStorage())

        result = service.add_account_items(
            [
                {
                    "type": "codex",
                    "access_token": "access_token_test",
                    "refresh_token": "rt_test",
                    "account_id": "acct_123",
                }
            ]
        )

        account = service.get_account("access_token_test")
        self.assertEqual(result["added"], 1)
        self.assertIsNotNone(account)
        self.assertEqual(account["type"], "free")
        self.assertEqual(account["export_type"], "codex")
        self.assertEqual(account["refresh_token"], "rt_test")
        self.assertEqual(account["account_id"], "acct_123")

    def test_add_account_items_detects_raw_codex_cli_auth_json(self) -> None:
        service = AccountService(MemoryStorage())

        result = service.add_account_items(
            [
                {
                    "auth_mode": "chatgpt",
                    "OPENAI_API_KEY": None,
                    "tokens": {
                        "access_token": "access_token_test",
                        "refresh_token": "rt_test",
                        "id_token": "id_test",
                        "account_id": "acct_123",
                    },
                }
            ]
        )

        account = service.get_account("access_token_test")
        self.assertEqual(result["added"], 1)
        self.assertIsNotNone(account)
        self.assertEqual(account["source_type"], "codex")
        self.assertEqual(account["export_type"], "codex")
        self.assertEqual(account["refresh_token"], "rt_test")
        self.assertEqual(account["id_token"], "id_test")
        self.assertEqual(account["account_id"], "acct_123")

    def test_update_account_preserves_codex_source_when_remote_info_omits_it(self) -> None:
        service = AccountService(MemoryStorage())
        service.add_account_items(
            [
                {
                    "type": "codex",
                    "access_token": "access_token_test",
                    "refresh_token": "rt_test",
                }
            ]
        )

        account = service.update_account(
            "access_token_test",
            {
                "type": "Plus",
                "quota": 5,
                "status": "正常",
            },
        )

        self.assertIsNotNone(account)
        self.assertEqual(account["type"], "Plus")
        self.assertEqual(account["quota"], 5)
        self.assertEqual(account["source_type"], "codex")
        self.assertEqual(account["export_type"], "codex")

    def test_refreshed_access_token_preserves_codex_source(self) -> None:
        service = AccountService(MemoryStorage())
        service.add_account_items(
            [
                {
                    "type": "codex",
                    "access_token": "old_access_token",
                    "refresh_token": "old_refresh_token",
                }
            ]
        )

        new_token = service._apply_refreshed_tokens(
            "old_access_token",
            {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "id_token": "new_id_token",
            },
            "test",
        )
        account = service.get_account(new_token)

        self.assertEqual(new_token, "new_access_token")
        self.assertIsNotNone(account)
        self.assertEqual(account["source_type"], "codex")
        self.assertEqual(account["export_type"], "codex")
        self.assertEqual(account["refresh_token"], "new_refresh_token")

    def test_codex_accounts_use_codex_oauth_client_id_for_refresh(self) -> None:
        service = AccountService(MemoryStorage())

        self.assertEqual(
            service._oauth_client_id_for_account({"source_type": "codex"}),
            service._CODEX_OAUTH_CLIENT_ID,
        )
        self.assertEqual(
            service._oauth_client_id_for_account({"export_type": "codex"}),
            service._CODEX_OAUTH_CLIENT_ID,
        )
        self.assertEqual(
            service._oauth_client_id_for_account({"source_type": "web"}),
            service._OAUTH_CLIENT_ID,
        )

    def test_codex_response_headers_include_account_id(self) -> None:
        access_token = make_jwt(
            {
                "https://api.openai.com/auth": {
                    "chatgpt_account_id": "acct_from_claim",
                }
            }
        )
        service = AccountService(
            MemoryStorage(
                [
                    {
                        "type": "codex",
                        "access_token": access_token,
                        "account_id": "acct_from_record",
                    }
                ]
            )
        )
        import services.openai_backend_api as backend_module

        original_service = backend_module.account_service
        backend_module.account_service = service
        try:
            headers = OpenAIBackendAPI(access_token)._codex_responses_headers()
        finally:
            backend_module.account_service = original_service

        self.assertEqual(headers["ChatGPT-Account-ID"], "acct_from_record")
        self.assertEqual(headers["Originator"], "codex_cli_rs")
        self.assertEqual(headers["OpenAI-Beta"], "responses=experimental")


if __name__ == "__main__":
    unittest.main()
