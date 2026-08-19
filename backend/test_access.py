import unittest

from fastapi import HTTPException

from assignments import AssignedDatabase
from auth import AuthStore, DiscordUser


def user(discord_id: str) -> DiscordUser:
    return DiscordUser(
        discord_id=discord_id,
        username="owner",
        display_name="Owner",
        avatar_url=None,
        has_database=True,
        database_label="Assigned databases",
    )


class AssignedDatabaseAccessTests(unittest.TestCase):
    def setUp(self):
        self.store = AuthStore.__new__(AuthStore)
        self.store.allow_self_service_databases = False
        self.store.database_assignments = {
            "222": (
                AssignedDatabase(id="aeron", label="Aeron Memory", url="postgresql://aeron"),
                AssignedDatabase(id="kai", label="Kai Memory", url="postgresql://kai"),
            )
        }

    def test_owner_sees_only_assigned_database_metadata(self):
        self.assertEqual(
            self.store.database_choices_for(user("222")),
            [
                {"id": "aeron", "label": "Aeron Memory"},
                {"id": "kai", "label": "Kai Memory"},
            ],
        )

    def test_owner_can_select_each_assigned_database(self):
        self.assertEqual(self.store.database_url_for(user("222"), "aeron"), "postgresql://aeron")
        self.assertEqual(self.store.database_url_for(user("222"), "kai"), "postgresql://kai")

    def test_owner_cannot_select_another_database_id(self):
        with self.assertRaises(HTTPException) as caught:
            self.store.database_url_for(user("222"), "ash")
        self.assertEqual(caught.exception.status_code, 403)

    def test_unassigned_owner_is_denied(self):
        with self.assertRaises(HTTPException) as caught:
            self.store.database_url_for(user("999"), None)
        self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
