import unittest
from app import is_even


class T(unittest.TestCase):
    def test_even(self):
        self.assertTrue(is_even(4))
        self.assertFalse(is_even(7))
        self.assertTrue(is_even(0))


if __name__ == "__main__":
    unittest.main()
