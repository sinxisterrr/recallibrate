import os
from http.cookies import SimpleCookie
import io
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from starlette.requests import Request

from assignments import AssignedDatabase, database_assignments
from auth import AuthStore


class DatabaseAssignmentTests(unittest.TestCase):
    def test_assignment_resolves_secret_environment_variable(self):
        with patch.dict(
            os.environ,
            {
                "RECALLIBRATE_DATABASE_ASSIGNMENTS": (
                    '{"123":{"id":"ash","label":"Ash Memory","database_env":"ASH_DATABASE_URL"}}'
                ),
                "ASH_DATABASE_URL": "postgresql://owner:secret@ash-db:5432/postgres",
            },
            clear=False,
        ):
            self.assertEqual(
                database_assignments(),
                {
                    "123": (AssignedDatabase(
                        id="ash", label="Ash Memory",
                        url="postgresql://owner:secret@ash-db:5432/postgres",
                    ),)
                },
            )

    def test_assignment_rejects_missing_secret(self):
        with patch.dict(
            os.environ,
            {
                "RECALLIBRATE_DATABASE_ASSIGNMENTS": (
                    '{"123":{"id":"ash","label":"Ash Memory","database_env":"MISSING_DATABASE_URL"}}'
                )
            },
            clear=False,
        ):
            os.environ.pop("MISSING_DATABASE_URL", None)
            with self.assertRaisesRegex(RuntimeError, "references unset MISSING_DATABASE_URL"):
                database_assignments()

    def test_one_owner_can_have_multiple_databases(self):
        with patch.dict(
            os.environ,
            {
                "RECALLIBRATE_DATABASE_ASSIGNMENTS": (
                    '{"222":{"databases":['
                    '{"id":"aeron","label":"Aeron Memory","database_env":"AERON_DATABASE_URL"},'
                    '{"id":"kai","label":"Kai Memory","database_env":"KAI_DATABASE_URL"}'
                    ']}}'
                ),
                "AERON_DATABASE_URL": "postgresql://owner:a@aeron-db/postgres",
                "KAI_DATABASE_URL": "postgresql://owner:k@kai-db/postgres",
            },
            clear=False,
        ):
            result = database_assignments()["222"]
            self.assertEqual([item.id for item in result], ["aeron", "kai"])
            self.assertEqual([item.label for item in result], ["Aeron Memory", "Kai Memory"])

    def test_empty_assignment_configuration_is_deny_by_default(self):
        with patch.dict(os.environ, {"RECALLIBRATE_DATABASE_ASSIGNMENTS": ""}, clear=False):
            self.assertEqual(database_assignments(), {})


class GuestDatabaseSessionTests(unittest.TestCase):
    def test_guest_database_session_is_encrypted_and_removed_on_logout(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        key = Fernet.generate_key().decode("ascii")
        try:
            with patch.dict(os.environ, {
                "RECALLIBRATE_STATE_PATH": handle.name,
                "RECALLIBRATE_CREDENTIAL_KEY": key,
                "RECALLIBRATE_PORTFOLIO_ONLY": "false",
                "RECALLIBRATE_SECURE_COOKIES": "false",
            }, clear=False):
                store = AuthStore()
            raw_url = "postgresql://owner:very-secret@db.example.com/postgres"
            response = store.create_guest_database_session(raw_url, "db.example.com/postgres")
            cookie = SimpleCookie(); cookie.load(response.headers["set-cookie"])
            token = cookie["recallibrate_session"].value
            request = Request({"type": "http", "headers": [(b"cookie", f"recallibrate_session={token}".encode())]})
            user = store.current_user(request)
            self.assertTrue(user.is_guest)
            conn = sqlite3.connect(handle.name)
            try:
                row = conn.execute("SELECT encrypted_database_url FROM users WHERE discord_id=?", (user.discord_id,)).fetchone()
                self.assertIsNotNone(row)
                self.assertNotIn(b"very-secret", row[0])
            finally:
                conn.close()
            store.logout(request)
            conn = sqlite3.connect(handle.name)
            try:
                remaining = conn.execute("SELECT COUNT(*) FROM users WHERE discord_id=?", (user.discord_id,)).fetchone()[0]
                self.assertEqual(remaining, 0)
            finally:
                conn.close()
        finally:
            os.unlink(handle.name)


class DiscordOAuthRequestTests(unittest.TestCase):
    def test_discord_requests_identify_recallibrate(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            with patch.dict(os.environ, {
                "RECALLIBRATE_STATE_PATH": handle.name,
                "RECALLIBRATE_PORTFOLIO_ONLY": "false",
                "DISCORD_CLIENT_ID": "client-id",
                "DISCORD_CLIENT_SECRET": "client-secret",
                "DISCORD_REDIRECT_URI": "https://recallibrate.app/api/auth/discord/callback",
            }, clear=False):
                store = AuthStore()
            token_response = io.BytesIO(json.dumps({"access_token": "access-token"}).encode())
            profile_response = io.BytesIO(json.dumps({"id": "123", "username": "sin"}).encode())
            with patch("auth.urlopen", side_effect=[token_response, profile_response]) as mocked_urlopen:
                profile = store._discord_profile("authorization-code")
            self.assertEqual(profile["id"], "123")
            for call in mocked_urlopen.call_args_list:
                headers = dict(call.args[0].header_items())
                self.assertEqual(headers["User-agent"], "DiscordBot (https://recallibrate.app, 1.0)")
                self.assertEqual(headers["Accept"], "application/json")
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
