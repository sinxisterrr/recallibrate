import socket
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from main import auth_store, database_label


class ConnectionSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_database_host_is_allowed(self):
        with patch.object(auth_store, "allowed_database_hosts", set()), patch(
            "main.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 5432))],
        ):
            label = await database_label("postgresql://user:secret@db.example.com:5432/postgres")
        self.assertEqual(label, "db.example.com:5432/postgres")

    async def test_unapproved_private_host_is_blocked(self):
        with patch.object(auth_store, "allowed_database_hosts", set()), patch(
            "main.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 5432))],
        ):
            with self.assertRaises(HTTPException) as caught:
                await database_label("postgresql://user:secret@internal-db:5432/postgres")
        self.assertEqual(caught.exception.status_code, 403)

    async def test_trusted_private_host_is_allowed_without_public_dns(self):
        with patch.object(auth_store, "allowed_database_hosts", {"internal-db"}), patch(
            "main.socket.getaddrinfo"
        ) as resolver:
            label = await database_label("postgresql://user:secret@internal-db:5432/postgres")
        self.assertEqual(label, "internal-db:5432/postgres")
        resolver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
