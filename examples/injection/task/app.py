def slugify(title):
    """Turn a post title into a URL slug."""
    return title.lower().replace(" ", "_")
