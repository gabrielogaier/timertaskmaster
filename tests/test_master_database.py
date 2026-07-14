import tempfile
import unittest
from pathlib import Path

from master_database import MasterDatabase


class MasterDatabaseTest(unittest.TestCase):
    def test_user_lifecycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = MasterDatabase(Path(temporary) / "master.db")
            user_id = db.add_user("Usuario A", "Usuario A", temporary)
            users = db.list_users()
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0]["display_name"], "Usuario A")
            db.set_user_active(user_id, False)
            self.assertEqual(db.list_users(active_only=True), [])
            db.delete_user(user_id)
            self.assertEqual(db.list_users(), [])


if __name__ == "__main__":
    unittest.main()
