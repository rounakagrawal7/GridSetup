import unittest

from grid_tray import _icon_image


class TrayTests(unittest.TestCase):
    def test_icon_is_generated(self):
        image = _icon_image()
        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
