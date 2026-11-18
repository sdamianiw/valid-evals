import unittest
from app import slugify


class T(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(slugify("Hello World"), "hello-world")
        self.assertEqual(slugify("  Many   spaces here "), "many-spaces-here")


if __name__ == "__main__":
    unittest.main()
