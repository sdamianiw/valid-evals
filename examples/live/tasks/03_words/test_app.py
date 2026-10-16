import unittest
from app import count_words


class T(unittest.TestCase):
    def test_words(self):
        self.assertEqual(count_words("one two  three"), 3)
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words("tab\tand\nnewline"), 3)


if __name__ == "__main__":
    unittest.main()
