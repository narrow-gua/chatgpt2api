import unittest

from api.accounts import _account_payload_token, _is_codex_account_payload


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


if __name__ == "__main__":
    unittest.main()
