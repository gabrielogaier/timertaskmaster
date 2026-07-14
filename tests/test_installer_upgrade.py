from pathlib import Path
import unittest


class InstallerUpgradeTests(unittest.TestCase):
    def test_master_reuses_timer_task_installer_identity(self):
        setup = (Path(__file__).resolve().parents[1] / "installer" / "setup.iss").read_text(encoding="utf-8")
        self.assertIn("AppId={{A8D1F4E9-DC92-4EBA-B5C8-70E28D3890A1}", setup)
        self.assertIn(r"DefaultDirName={localappdata}\Programs\Timer Task", setup)
        self.assertIn(r'Type: files; Name: "{app}\Timer Task.exe"', setup)
        self.assertIn(r'Source: "..\dist\Timer Task Master.exe"', setup)
        self.assertNotIn(r'{localappdata}\TimerTask', setup)


if __name__ == "__main__":
    unittest.main()
