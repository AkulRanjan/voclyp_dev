"""Console authentication & authorization.

Covers: password hashing, signed/tamper-proof role tokens, invite-gated signup
(no self-elected managers), the unified principal (a session token authorizes
/v1 with role->scope), and server-side session revocation (logout)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp import security
from voclyp.store import Store

try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False

from voclyp.config import Settings

CONVERSATION = b"AGENT: Namaste ji!\nCUSTOMER: Ye pack costly hai.\n"


class SessionTokenTest(unittest.TestCase):
    def test_round_trip_and_tamper(self):
        secret = b"unit-secret"
        token = security.issue_session_token({"sub": "u1", "role": "sales"}, secret)
        self.assertEqual(security.verify_session_token(token, secret)["role"], "sales")
        self.assertIsNone(security.verify_session_token(token, b"other"))

        # splicing a different-secret body onto a valid signature is rejected
        _, sig = token.split(".")
        forged_body = security.issue_session_token({"role": "manager"}, b"x").split(".")[0]
        self.assertIsNone(security.verify_session_token(f"{forged_body}.{sig}", secret))

    def test_expired_token_rejected(self):
        token = security.issue_session_token({"sub": "u"}, b"s", ttl_seconds=-1)
        self.assertIsNone(security.verify_session_token(token, b"s"))


class UserStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp(prefix="voclyp-users-")) / "v.db")
        self.store.create_tenant("acme", "Acme", "fmcg")

    def test_create_and_verify(self):
        self.store.create_user("Boss@Acme.com", "Boss", "manager", "acme", "hunter2pass")
        self.assertIsNotNone(self.store.verify_user_password("boss@acme.com", "hunter2pass"))
        self.assertIsNone(self.store.verify_user_password("boss@acme.com", "wrong"))
        self.assertNotIn(b"hunter2pass", Path(self.store.db_path).read_bytes())

    def test_validation(self):
        for bad in [("x@y.com", "N", "root", "acme", "longenough"),
                    ("not-an-email", "N", "sales", "acme", "longenough"),
                    ("a@b.com", "N", "sales", "acme", "short")]:
            with self.assertRaises(ValueError):
                self.store.create_user(*bad)
        self.store.create_user("dup@b.com", "N", "sales", "acme", "longenough")
        with self.assertRaises(ValueError):
            self.store.create_user("dup@b.com", "N", "manager", "acme", "longenough")

    def test_invite_lifecycle(self):
        code = self.store.create_invite("acme", "sales", "usr_owner")
        self.assertIsNone(self.store.consume_invite(code, "other-tenant"))  # wrong tenant
        self.assertEqual(self.store.consume_invite(code, "acme"), "sales")  # ok
        self.assertIsNone(self.store.consume_invite(code, "acme"))          # single-use

    def test_session_epoch_bump(self):
        uid = self.store.create_user("e@b.com", "E", "sales", "acme", "longenough")
        self.assertEqual(self.store.get_user(uid)["session_epoch"], 0)
        self.store.bump_session_epoch(uid)
        self.assertEqual(self.store.get_user(uid)["session_epoch"], 1)


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class AuthEndpointsTest(unittest.TestCase):
    def setUp(self):
        from voclyp.gateway.app import create_app

        self.data_dir = Path(tempfile.mkdtemp(prefix="voclyp-auth-"))
        self.app = create_app(self.data_dir, Settings(
            master_key=b"k", session_secret=b"test-session"))
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def _signup(self, email, org="Acme", invite=None, pw="longenough", name="T"):
        body = {"email": email, "password": pw, "name": name, "role": "manager"}
        if org is not None:
            body["org"] = org
        if invite:
            body["invite"] = invite
        return self.client.post("/auth/signup", json=body)

    def _bearer(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_first_user_is_manager_owner(self):
        r = self._signup("owner@acme.com", org="Acme Co")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["user"]["role"], "manager")
        me = self.client.get("/auth/me", headers=self._bearer(r.json()["token"]))
        self.assertEqual(me.json()["user"]["role"], "manager")

    def test_join_requires_invite_and_is_single_use(self):
        owner = self._signup("owner@beta.com", org="Beta").json()["token"]
        # no invite -> rejected
        self.assertEqual(self._signup("rando@beta.com", org="Beta").status_code, 403)
        # manager mints a sales invite
        inv = self.client.post("/auth/invite", json={"role": "sales"}, headers=self._bearer(owner))
        self.assertEqual(inv.status_code, 201)
        code = inv.json()["invite"]
        joined = self._signup("rep@beta.com", org="Beta", invite=code)
        self.assertEqual(joined.status_code, 201)
        self.assertEqual(joined.json()["user"]["role"], "sales")  # role fixed by invite
        # invite cannot be reused
        self.assertEqual(self._signup("rep2@beta.com", org="Beta", invite=code).status_code, 403)

    def test_non_manager_cannot_invite(self):
        owner = self._signup("owner@gamma.com", org="Gamma").json()["token"]
        code = self.client.post("/auth/invite", json={"role": "sales"},
                                headers=self._bearer(owner)).json()["invite"]
        sales = self._signup("rep@gamma.com", org="Gamma", invite=code).json()["token"]
        self.assertEqual(
            self.client.post("/auth/invite", json={"role": "manager"},
                             headers=self._bearer(sales)).status_code, 403)

    def test_token_authorizes_v1_with_role_scopes(self):
        mgr = self._signup("m@delta.com", org="Delta").json()["token"]
        code = self.client.post("/auth/invite", json={"role": "sales"},
                                headers=self._bearer(mgr)).json()["invite"]
        sales = self._signup("s@delta.com", org="Delta", invite=code).json()["token"]

        # manager: read + admin
        self.assertEqual(self.client.get("/v1/insights", headers=self._bearer(mgr)).status_code, 200)
        self.assertEqual(self.client.get("/v1/metrics", headers=self._bearer(mgr)).status_code, 200)

        # sales: ingest yes, admin no
        ingest = self.client.post(
            "/v1/conversations", headers=self._bearer(sales),
            files={"audio": ("r.audio", CONVERSATION)},
            data={"consent_captured": "true", "agent_id": "a1"})
        self.assertEqual(ingest.status_code, 202)
        self.assertEqual(self.client.get("/v1/metrics", headers=self._bearer(sales)).status_code, 403)
        self.assertEqual(self.client.delete("/v1/conversations/x", headers=self._bearer(sales)).status_code, 403)

    def test_logout_revokes_outstanding_tokens(self):
        token = self._signup("u@eps.com", org="Eps").json()["token"]
        self.assertEqual(self.client.get("/auth/me", headers=self._bearer(token)).status_code, 200)
        self.assertEqual(self.client.post("/auth/logout", headers=self._bearer(token)).status_code, 200)
        # the same token is now dead, for /auth and /v1 alike
        self.assertEqual(self.client.get("/auth/me", headers=self._bearer(token)).status_code, 401)
        self.assertEqual(self.client.get("/v1/insights", headers=self._bearer(token)).status_code, 401)

    def test_unauth_and_bad_login(self):
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/v1/insights").status_code, 401)
        self._signup("u@zeta.com", org="Zeta")
        self.assertEqual(
            self.client.post("/auth/login", json={"email": "u@zeta.com", "password": "nope"}).status_code,
            401)


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed")
class ProductionFailClosedTest(unittest.TestCase):
    def test_production_requires_session_secret(self):
        from voclyp.gateway.app import create_app

        data_dir = Path(tempfile.mkdtemp(prefix="voclyp-prod-"))
        with self.assertRaises(RuntimeError):
            create_app(data_dir, Settings(env="production"))  # no secret, no master key
        # with a secret configured, production starts fine
        create_app(data_dir, Settings(env="production", session_secret=b"x" * 32))


if __name__ == "__main__":
    unittest.main()
