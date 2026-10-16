import unittest
from app import clamp


class T(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-3, 0, 10), 0)
        self.assertEqual(clamp(42, 0, 10), 10)


if __name__ == "__main__":
    unittest.main()
