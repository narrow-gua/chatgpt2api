import unittest

from api.accounts import _account_payload_token, _is_codex_account_payload
from services.protocol.codex_text import _codex_payload


class AccountsApiTests(unittest.TestCase):
    def test_account_payload_token_accepts_raw_codex_cli_auth_json(self) -> None:
        payload = {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "access_token_test",
                "refresh_token": "rt_test",
            },
        }

        self.assertEqual(_account_payload_token(payload), "access_token_test")
        self.assertTrue(_is_codex_account_payload(payload))

    def test_codex_payload_includes_default_instructions(self) -> None:
        payload = _codex_payload(
            {"model": "codex"},
            [{"role": "user", "content": "hello"}],
        )

        self.assertIn("instructions", payload)
        self.assertTrue(payload["instructions"])


if __name__ == "__main__":
    unittest.main()
