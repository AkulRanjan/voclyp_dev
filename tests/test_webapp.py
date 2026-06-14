"""Demo web app routes: pages served same-origin with a page CSP that allows
self-hosted scripts (and nothing else), API routes keep the strict no-content
CSP, and the asset route cannot be used to read arbitrary files."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False

from voclyp.config import Settings


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class WebAppTest(unittest.TestCase):
    def setUp(self):
        from voclyp.gateway.app import create_app

        self.data_dir = Path(tempfile.mkdtemp(prefix="voclyp-web-"))
        self.app = create_app(self.data_dir, Settings(master_key=b"test-key"))
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_root_redirects_to_app(self):
        resp = self.client.get("/", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 307))
        self.assertEqual(resp.headers["location"], "/app/")

    def test_index_and_assets_served(self):
        index = self.client.get("/app/")
        self.assertEqual(index.status_code, 200)
        self.assertIn("text/html", index.headers["content-type"])
        self.assertIn("VoClyp", index.text)
        for asset, ctype in (("agent.html", "text/html"),
                             ("dashboard.html", "text/html"),
                             ("agent.js", "text/javascript"),
                             ("app.css", "text/css")):
            resp = self.client.get(f"/app/{asset}")
            self.assertEqual(resp.status_code, 200, asset)
            self.assertIn(ctype, resp.headers["content-type"])

    def test_webapp_csp_allows_self_scripts_only(self):
        csp = self.client.get("/app/").headers["content-security-policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertNotIn("unsafe-inline", csp)

    def test_api_keeps_strict_csp(self):
        resp = self.client.get("/v1/insights", headers={"X-API-Key": "nope"})
        self.assertEqual(resp.headers["content-security-policy"],
                         "default-src 'none'")

    def test_asset_route_is_whitelisted(self):
        # wrong extension, traversal, and unknown files all 404
        for path in ("/app/app.py", "/app/..%2F..%2Fpyproject.toml",
                     "/app/%2e%2e/app.py", "/app/missing.js"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
