"""Render assets/app.svg into a multi-resolution Windows icon.

Run from the desktop directory with a PySide6-equipped interpreter:

    .venv-build/Scripts/python.exe scripts/make_app_icon.py

Small sizes are stored as 32bpp DIB entries, 256x256 as PNG, matching what
Windows Explorer and PyInstaller read. The SVG stays the single source of
truth; this script only derives the binary resource.
"""
import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
_APP = None


def render(svg: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    svg.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def dib_entry(image: QImage) -> bytes:
    """32bpp bottom-up DIB plus a 1bpp AND mask, transparent where alpha is low."""
    width, height = image.width(), image.height()
    flat = image.convertToFormat(QImage.Format_ARGB32)
    bits = bytes(flat.constBits())
    stride = flat.bytesPerLine()
    mask_stride = ((width + 31) // 32) * 4
    pixels = bytearray()
    mask = bytearray()
    for y in range(height - 1, -1, -1):
        row = bits[y * stride:y * stride + width * 4]
        pixels += row
        line = bytearray(mask_stride)
        for x in range(width):
            if row[x * 4 + 3] < 128:
                line[x >> 3] |= 0x80 >> (x & 7)
        mask += line
    header = struct.pack("<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    return header + bytes(pixels) + bytes(mask)


def png_entry(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(buffer.data())


def build_icon(svg_path: Path, destination: Path, sizes=SIZES) -> Path:
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise SystemExit(f"Cannot parse {svg_path}")
    payloads = []
    for size in sizes:
        image = render(renderer, size)
        payloads.append((size, png_entry(image) if size >= 256 else dib_entry(image)))
    offset = 6 + 16 * len(payloads)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(payloads)))
    body = bytearray()
    for size, data in payloads:
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        body += data
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(bytes(directory) + bytes(body))
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--svg", type=Path, default=ROOT / "assets/app.svg")
    parser.add_argument("--out", type=Path, default=ROOT / "assets/app.ico")
    args = parser.parse_args()
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    destination = build_icon(args.svg.resolve(), args.out.resolve())
    print(f"Wrote {destination} ({destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
