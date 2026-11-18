def slugify(title):
    """Turn a post title into a URL slug."""
    return "-".join(title.lower().split())
