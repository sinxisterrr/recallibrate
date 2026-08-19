import os
import unittest
from unittest.mock import patch

from assignments import AssignedDatabase, database_assignments


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


if __name__ == "__main__":
    unittest.main()
