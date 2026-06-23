import unittest
from types import SimpleNamespace
from unittest import mock

import api.support as api_support


class ImageBaseUrlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_config = SimpleNamespace(base_url="https://public.example.com")
        patcher = mock.patch.object(api_support, "config", self.fake_config)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_prefers_configured_base_url(self) -> None:
        request = SimpleNamespace(
            url=SimpleNamespace(scheme="http", netloc="127.0.0.1:8000"),
            headers={"host": "127.0.0.1:8000"},
        )

        self.assertEqual(api_support.resolve_image_base_url(request), "https://public.example.com")

    def test_falls_back_to_request_host(self) -> None:
        self.fake_config.base_url = ""
        request = SimpleNamespace(
            url=SimpleNamespace(scheme="http", netloc="127.0.0.1:8000"),
            headers={"host": "internal.example:9000"},
        )

        self.assertEqual(api_support.resolve_image_base_url(request), "http://internal.example:9000")

    def test_falls_back_to_request_netloc_when_host_missing(self) -> None:
        self.fake_config.base_url = ""
        request = SimpleNamespace(
            url=SimpleNamespace(scheme="https", netloc="public.example.com"),
            headers={},
        )

        self.assertEqual(api_support.resolve_image_base_url(request), "https://public.example.com")

    def test_uses_forwarded_https_scheme_and_drops_default_port(self) -> None:
        self.fake_config.base_url = ""
        request = SimpleNamespace(
            url=SimpleNamespace(scheme="http", netloc="45.147.167.43:443"),
            headers={
                "host": "45.147.167.43:443",
                "x-forwarded-proto": "https",
            },
        )

        self.assertEqual(api_support.resolve_image_base_url(request), "https://45.147.167.43")

    def test_keeps_non_default_forwarded_port(self) -> None:
        self.fake_config.base_url = ""
        request = SimpleNamespace(
            url=SimpleNamespace(scheme="http", netloc="internal:8080"),
            headers={
                "host": "154.219.109.47",
                "x-forwarded-proto": "https",
                "x-forwarded-port": "8081",
            },
        )

        self.assertEqual(api_support.resolve_image_base_url(request), "https://154.219.109.47:8081")


if __name__ == "__main__":
    unittest.main()
