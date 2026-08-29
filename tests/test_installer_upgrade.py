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

    def test_build_collects_qt_runtime_from_a_verified_environment(self):
        build_script = (Path(__file__).resolve().parents[1] / "build_executavel.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("from PySide6 import QtCore", build_script)
        self.assertIn("--force-reinstall --no-cache-dir", build_script)
        self.assertIn("--collect-all PySide6", build_script)
        self.assertIn("--collect-all shiboken6", build_script)


if __name__ == "__main__":
    unittest.main()
