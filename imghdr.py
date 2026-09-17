"""Small compatibility implementation for Python 3.14.

The pinned python-telegram-bot 13.x release imports the removed stdlib
``imghdr`` module and only needs ``what`` for detecting uploaded images.
"""


def what(file, h=None):
    """Return a basic image type name from a file path or byte stream."""
    if h is None:
        if not hasattr(file, "read"):
            with open(file, "rb") as image_file:
                h = image_file.read(32)
        else:
            position = file.tell()
            h = file.read(32)
            file.seek(position)

    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if h[:3] == b"GIF":
        return "gif"
    if h[:2] == b"\xff\xd8":
        return "jpeg"
    if h[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if h.startswith(b"RIFF") and h[8:12] == b"WEBP":
        return "webp"
    return None
