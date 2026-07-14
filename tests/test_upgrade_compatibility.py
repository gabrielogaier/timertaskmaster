from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from database import Database
from master_database import MasterDatabase


class UpgradeCompatibilityTests(unittest.TestCase):
    def test_master_adds_tables_without_losing_timer_data(self):
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "timertask.db"
            timer_db = Database(db_path)
            timer_db.set_setting("user_name", "Usuario A")
            timer_db.add_item("projects", "Projeto preservado")
            project = next(row for row in timer_db.list_items("projects") if row["name"] == "Projeto preservado")
            activity = timer_db.list_items("activity_types", active_only=True)[0]
            timer_db.start_timer(project["id"], activity["id"], "Em andamento", "2026-07-13 08:00:00")

            master_db = MasterDatabase(db_path)
            master_db.add_user("Usuario A", "Usuario A", str(Path(directory) / "registros"))

            reopened = Database(db_path)
            self.assertEqual(reopened.get_setting("user_name"), "Usuario A")
            self.assertIsNotNone(reopened.get_active_timer())
            self.assertTrue(any(row["name"] == "Projeto preservado" for row in reopened.list_items("projects")))
            self.assertEqual(len(master_db.list_users()), 1)


if __name__ == "__main__":
    unittest.main()
