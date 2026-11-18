# Slugs use underscores

Reported by a user: `slugify("Hello World")` returns `hello_world`. Slugs must use hyphens, and repeated or
surrounding spaces must not produce empty parts. `test_app.py` shows the expected output.
