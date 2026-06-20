"""
Generate ``llmime.ico`` from the same artwork as the in-app tray icon.

The tray icon is drawn at runtime by ``daemon.render_icon_pixmap``; Windows
shortcuts (.lnk) and PyInstaller need an on-disk ``.ico`` instead. This script
renders that exact artwork at several sizes and packs them into a single
multi-resolution ICO (each entry stored as PNG, which Windows Vista+ supports),
so the Start-menu / taskbar / Explorer icon matches the tray icon.

Run:  py make_icon.py   (or:  venv-win\\Scripts\\python.exe make_icon.py)
"""

import sys
import struct

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice

from daemon import render_icon_pixmap

ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT_PATH = "llmime.ico"


def pixmap_to_png_bytes(pixmap) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return data


def build_ico(images) -> bytes:
    """images: list of (size, png_bytes) -> ICO container bytes."""
    count = len(images)
    header = struct.pack('<HHH', 0, 1, count)  # reserved, type=icon, count
    offset = 6 + 16 * count
    entries = b''
    payload = b''
    for size, png in images:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO spec
        entries += struct.pack(
            '<BBBBHHII',
            dim, dim,        # width, height
            0,               # color count (0 = >=256 colors)
            0,               # reserved
            1,               # color planes
            32,              # bits per pixel
            len(png),        # size of image data
            offset,          # offset of image data
        )
        payload += png
        offset += len(png)
    return header + entries + payload


def main():
    app = QApplication(sys.argv)  # required to create QPixmap/QPainter
    images = [(sz, pixmap_to_png_bytes(render_icon_pixmap(sz))) for sz in ICON_SIZES]
    ico = build_ico(images)
    with open(OUT_PATH, "wb") as f:
        f.write(ico)
    print(f"Wrote {OUT_PATH} ({len(ico)} bytes, sizes: {ICON_SIZES})")
    app.quit()


if __name__ == "__main__":
    main()
