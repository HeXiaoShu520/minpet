# coding:utf-8

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from windows.win32_frameless import (
    HTBOTTOM,
    HTBOTTOMLEFT,
    HTBOTTOMRIGHT,
    HTCAPTION,
    HTCLIENT,
    HTLEFT,
    HTRIGHT,
    HTTOP,
    HTTOPLEFT,
    HTTOPRIGHT,
    hit_test,
)


class Win32FramelessHitTest(unittest.TestCase):
    def test_corners_and_edges_resize(self):
        cases = {
            (0, 0): HTTOPLEFT,
            (199, 0): HTTOPRIGHT,
            (0, 119): HTBOTTOMLEFT,
            (199, 119): HTBOTTOMRIGHT,
            (0, 60): HTLEFT,
            (199, 60): HTRIGHT,
            (100, 0): HTTOP,
            (100, 119): HTBOTTOM,
        }
        for point, expected in cases.items():
            with self.subTest(point=point):
                self.assertEqual(expected, hit_test(*point, 200, 120, 54, 8))

    def test_title_blank_area_drags(self):
        self.assertEqual(HTCAPTION, hit_test(100, 20, 200, 120, 32, 8))

    def test_title_controls_stay_client_area(self):
        controls = [(104, 0, 32, 32), (136, 0, 32, 32), (168, 0, 32, 32)]
        self.assertEqual(HTCLIENT, hit_test(120, 16, 200, 120, 32, 8, controls))
        self.assertEqual(HTCLIENT, hit_test(184, 16, 200, 120, 32, 8, controls))

    def test_pet_header_and_content_are_client_area(self):
        self.assertEqual(HTCLIENT, hit_test(100, 32, 200, 120, 32, 8))
        self.assertEqual(HTCLIENT, hit_test(100, 60, 200, 120, 32, 8))

    def test_maximized_window_disables_resize(self):
        self.assertEqual(HTCAPTION, hit_test(0, 30, 200, 120, 54, 8, maximized=True))
        self.assertEqual(HTCLIENT, hit_test(0, 60, 200, 120, 54, 8, maximized=True))

    def test_maximized_title_controls_stay_client_area(self):
        controls = [(68, 0, 44, 32), (112, 0, 44, 32), (156, 0, 44, 32)]
        self.assertEqual(HTCAPTION, hit_test(40, 16, 200, 120, 32, 8, controls, maximized=True))
        self.assertEqual(HTCLIENT, hit_test(178, 16, 200, 120, 32, 8, controls, maximized=True))

    def test_scaled_resize_border(self):
        self.assertEqual(HTLEFT, hit_test(11, 60, 300, 180, 81, 12))
        self.assertEqual(HTCLIENT, hit_test(12, 100, 300, 180, 81, 12))


if __name__ == '__main__':
    unittest.main()
