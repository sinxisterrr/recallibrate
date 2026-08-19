import os
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet
from fastapi import HTTPException

from runtime import RuntimeStore


class RuntimePairingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("CREATE TABLE users (discord_id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO users (discord_id) VALUES ('123')")
            conn.commit()
        finally:
            conn.close()
        self.store = RuntimeStore(self.path, Fernet(Fernet.generate_key()))

    def tearDown(self):
        os.unlink(self.path)

    async def test_pairing_claim_saves_encrypted_runtime_connection(self):
        with patch.object(
            self.store, "validate_endpoint", AsyncMock(return_value="https://sage.example.com")
        ):
            pairing = await self.store.start("123", "https://sage.example.com")

        responses = [
            {
                "protocolVersion": "1.0",
                "serviceName": "Ash database runtime",
                "capabilities": [
                    "database.tables.read",
                    "database.records.read",
                    "database.records.write",
                    "database.records.delete",
                ],
            },
            {"ok": True, "databaseReachable": True, "credentialsExposed": False},
        ]
        with patch.object(self.store, "_request", AsyncMock(side_effect=responses)):
            result = await self.store.claim(pairing["code"], "scoped-runtime-token")

        self.assertEqual(result, {"ok": True})
        saved = self.store.connection("123")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.endpoint, "https://sage.example.com")
        self.assertEqual(saved.token, "scoped-runtime-token")
        self.assertEqual(saved.label, "Ash database runtime")
        self.assertEqual(self.store.status("123", pairing["id"])["status"], "connected")

    async def test_invalid_pairing_code_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            await self.store.claim("NOT-A-CODE", "token")
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
