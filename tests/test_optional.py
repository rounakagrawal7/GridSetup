import subprocess
import unittest
from unittest.mock import patch

from grid_optional import nuclei_scan, pio_build, sherlock_scan


class OptionalToolTests(unittest.TestCase):
    def fake_run(self, returncode=0, stdout="ok", stderr=""):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def test_sherlock_missing(self):
        with patch("grid_optional.shutil.which", return_value=""):
            self.assertIn("not installed", sherlock_scan("alice"))

    def test_sherlock_command(self):
        with patch("grid_optional.shutil.which", return_value="sherlock"), patch(
            "grid_optional.subprocess.run", return_value=self.fake_run(stdout="found")
        ) as run:
            self.assertEqual(sherlock_scan("@alice"), "found")
            command = run.call_args.args[0]
            self.assertEqual(command[0], "sherlock")
            self.assertIn("alice", command)

    def test_nuclei_requires_authorization(self):
        self.assertIn("authorized", nuclei_scan("example.com"))

    def test_nuclei_command(self):
        with patch("grid_optional.shutil.which", return_value="nuclei"), patch(
            "grid_optional.subprocess.run", return_value=self.fake_run(stdout="[info]")
        ) as run:
            self.assertIn("info", nuclei_scan("authorized https://example.com"))
            command = run.call_args.args[0]
            self.assertIn("https://example.com", command)

    def test_platformio_missing(self):
        with patch("grid_optional.shutil.which", return_value=""):
            self.assertIn("not installed", pio_build("firmware"))

    def test_platformio_command(self):
        with patch("grid_optional.shutil.which", return_value="pio"), patch(
            "grid_optional.subprocess.run", return_value=self.fake_run(stdout="built")
        ) as run:
            self.assertEqual(pio_build("firmware"), "built")
            command = run.call_args.args[0]
            self.assertIn("-d", command)
            self.assertIn("firmware", command)


if __name__ == "__main__":
    unittest.main()
