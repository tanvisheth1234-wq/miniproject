"""Renders the PWA icons (PNG) from the same glyph as public/icon.svg, with
nothing but the standard library. Run once: python make_icons.py"""

import pathlib
import struct
import zlib

CRIMSON = (155, 28, 28)


def pixel(X, Y, maskable):
    if not maskable:
        r = 112
        dx = max(abs(X - 256) - (256 - r), 0)
        dy = max(abs(Y - 256) - (256 - r), 0)
        if dx * dx + dy * dy > r * r:
            return (255, 255, 255, 0)
    s = 0.72 if maskable else 1.0  # maskable icons keep the glyph inside the safe zone
    gx, gy = 256 + (X - 256) / s, 256 + (Y - 256) / s

    def circle(cx, cy, r):
        return (gx - cx) ** 2 + (gy - cy) ** 2 <= r * r

    def segment(ax, ay, bx, by, w):
        vx, vy = bx - ax, by - ay
        t = max(0, min(1, ((gx - ax) * vx + (gy - ay) * vy) / (vx * vx + vy * vy)))
        return (gx - (ax + t * vx)) ** 2 + (gy - (ay + t * vy)) ** 2 <= (w / 2) ** 2

    if circle(256, 150, 18):
        return (*CRIMSON, 255)
    if circle(256, 150, 46) or circle(130, 330, 40) or circle(382, 330, 40):
        return (255, 255, 255, 255)
    if segment(256, 150, 130, 330, 22) or segment(256, 150, 382, 330, 22) or segment(130, 330, 382, 330, 22):
        return (255, 255, 255, 230)
    return (*CRIMSON, 255)


def png(size, maskable):
    ss = 3
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    r, g, b, a = pixel((x * ss + sx) / (size * ss) * 512, (y * ss + sy) / (size * ss) * 512, maskable)
                    acc[0] += r * a
                    acc[1] += g * a
                    acc[2] += b * a
                    acc[3] += a
            if acc[3] == 0:
                row += bytes([0, 0, 0, 0])
            else:
                row += bytes([acc[0] // acc[3], acc[1] // acc[3], acc[2] // acc[3], acc[3] // (ss * ss)])
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    out = pathlib.Path(__file__).parent / "public"
    (out / "icon-192.png").write_bytes(png(192, False))
    (out / "icon-512.png").write_bytes(png(512, False))
    (out / "icon-maskable-512.png").write_bytes(png(512, True))
    print("icons written to", out)
