#!/usr/bin/env python3
"""Generate a realistic GPS-tagged sample photo library for testing Meridian.

Creates ~150 JPEGs with genuine EXIF GPS coordinates and capture dates,
structured as a believable life: a home city photographed across three years,
four multi-stop trips, and a handful of photos with no GPS at all (to test
the "no location data" experience).

Output: sample-photos/ directory + meridian-sample-photos.zip
"""

from __future__ import annotations

import math
import random
import shutil
import zipfile
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

import piexif
from PIL import Image, ImageDraw, ImageFilter

random.seed(42)

OUT = Path(__file__).resolve().parent.parent / "sample-photos"
ZIP = Path(__file__).resolve().parent.parent / "meridian-sample-photos.zip"

# Palette pools per place mood: (sky, mid, ground)
PALETTES = {
    "city": [((28, 32, 52), (68, 76, 112), (188, 150, 96)),
             ((16, 20, 34), (52, 60, 96), (226, 178, 112)),
             ((44, 52, 80), (96, 104, 140), (240, 208, 152))],
    "coast": [((92, 148, 196), (56, 108, 160), (232, 212, 168)),
              ((136, 180, 216), (72, 128, 176), (244, 228, 188))],
    "nature": [((120, 156, 132), (68, 108, 84), (40, 68, 48)),
               ((160, 176, 136), (96, 124, 88), (56, 84, 60))],
    "night": [((8, 10, 22), (24, 28, 52), (120, 96, 160)),
              ((12, 14, 28), (32, 36, 64), (168, 128, 96))],
}

# (label, lat, lng, mood)
HOME = ("London", 51.5074, -0.1278, "city")

TRIPS = [
    {
        "name": "lisbon-2023",
        "stops": [
            ("Lisbon", 38.7223, -9.1393, "coast", "2023-06-10", 3, 14),
            ("Sintra", 38.8029, -9.3817, "nature", "2023-06-13", 2, 9),
            ("Porto", 41.1579, -8.6291, "city", "2023-06-15", 3, 12),
        ],
    },
    {
        "name": "kenya-2022",
        "stops": [
            ("Nairobi", -1.2921, 36.8219, "city", "2022-08-04", 2, 8),
            ("Maasai Mara", -1.4931, 35.1439, "nature", "2022-08-06", 4, 16),
        ],
    },
    {
        "name": "japan-2024",
        "stops": [
            ("Tokyo", 35.6762, 139.6503, "night", "2024-04-02", 4, 15),
            ("Kyoto", 35.0116, 135.7681, "nature", "2024-04-06", 3, 11),
            ("Osaka", 34.6937, 135.5023, "city", "2024-04-09", 2, 8),
        ],
    },
    {
        "name": "new-york-2024",
        "stops": [
            ("New York", 40.7128, -74.0060, "night", "2024-12-19", 5, 18),
        ],
    },
]

HOME_SESSIONS = 16          # distinct home days across 2022–2025
HOME_PHOTOS_PER_SESSION = (1, 3)
NO_GPS_COUNT = 8


def deg_to_dms_rationals(deg: float):
    d = abs(deg)
    degrees = int(d)
    minutes = int((d - degrees) * 60)
    seconds = round((d - degrees - minutes / 60) * 3600 * 100)
    return ((degrees, 1), (minutes, 1), (seconds, 100))


def build_exif(lat: float | None, lng: float | None, when: datetime) -> bytes:
    dt = when.strftime("%Y:%m:%d %H:%M:%S")
    zeroth = {piexif.ImageIFD.Make: b"Apple", piexif.ImageIFD.Model: b"iPhone 15 Pro",
              piexif.ImageIFD.DateTime: dt.encode()}
    exif_ifd = {piexif.ExifIFD.DateTimeOriginal: dt.encode(),
                piexif.ExifIFD.DateTimeDigitized: dt.encode(),
                piexif.ExifIFD.OffsetTimeOriginal: b"+00:00"}
    gps_ifd = {}
    if lat is not None and lng is not None:
        gps_ifd = {
            piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),
            piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
            piexif.GPSIFD.GPSLatitude: deg_to_dms_rationals(lat),
            piexif.GPSIFD.GPSLongitudeRef: b"E" if lng >= 0 else b"W",
            piexif.GPSIFD.GPSLongitude: deg_to_dms_rationals(lng),
        }
    return piexif.dump({"0th": zeroth, "Exif": exif_ifd, "GPS": gps_ifd})


def paint_photo(path: Path, mood: str, label: str, seq: int) -> None:
    w, h = random.choice([(1600, 1200), (1200, 1600), (1600, 1067)])
    sky, mid, ground = random.choice(PALETTES[mood])
    img = Image.new("RGB", (w, h))
    dr = ImageDraw.Draw(img)
    horizon = int(h * random.uniform(0.45, 0.65))
    for y in range(h):
        if y < horizon:
            t = y / max(horizon, 1)
            c = tuple(int(sky[i] + (mid[i] - sky[i]) * t) for i in range(3))
        else:
            t = (y - horizon) / max(h - horizon, 1)
            c = tuple(int(mid[i] + (ground[i] - mid[i]) * t) for i in range(3))
        dr.line([(0, y), (w, y)], fill=c)
    # sun/moon glow
    cx, cy = random.randint(w // 5, w * 4 // 5), random.randint(h // 6, horizon)
    r = random.randint(40, 110)
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r],
               fill=(255, 214, 160) if mood != "night" else (200, 190, 255))
    glow = glow.filter(ImageFilter.GaussianBlur(r * 0.9))
    img = Image.blend(img, Image.composite(glow, img, glow.convert("L")), 0.5)
    dr = ImageDraw.Draw(img)
    # skyline / landscape silhouettes
    sil = (12, 12, 20) if mood in ("city", "night") else (20, 30, 24)
    if mood in ("city", "night"):
        x = 0
        while x < w:
            bw = random.randint(60, 180)
            bh = random.randint(int(h * 0.08), int(h * 0.3))
            dr.rectangle([x, horizon - bh, x + bw, horizon + 4], fill=sil)
            if mood == "night":
                for _ in range(random.randint(4, 14)):
                    wx = random.randint(x + 6, max(x + 8, x + bw - 8))
                    wy = random.randint(horizon - bh + 6, horizon - 6)
                    dr.rectangle([wx, wy, wx + 4, wy + 6], fill=(255, 196, 120))
            x += bw + random.randint(8, 40)
    else:
        pts = [(0, horizon)]
        x = 0
        while x < w:
            x += random.randint(80, 220)
            pts.append((x, horizon - random.randint(10, int(h * 0.18))))
        pts += [(w, horizon), (w, horizon + 6), (0, horizon + 6)]
        dr.polygon(pts, fill=sil)
    # subtle film grain
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    img.save(path, "JPEG", quality=88)


def stamp(path: Path, lat, lng, when: datetime) -> None:
    piexif.insert(build_exif(lat, lng, when), str(path))


def jitter(v: float, amt: float) -> float:
    return v + random.uniform(-amt, amt)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    count = 0

    # Home sessions spread across 2022-01 .. 2025-06
    start = datetime(2022, 1, 8, 11, 0)
    for s in range(HOME_SESSIONS):
        day = start + timedelta(days=int(s * (1250 / HOME_SESSIONS)) + random.randint(0, 12))
        for p in range(random.randint(*HOME_PHOTOS_PER_SESSION)):
            count += 1
            f = OUT / f"IMG_{count:04d}.jpg"
            paint_photo(f, HOME[3], HOME[0], count)
            stamp(f, jitter(HOME[1], 0.03), jitter(HOME[2], 0.05),
                  day + timedelta(hours=p * 2, minutes=random.randint(0, 50)))

    # Trips
    for trip in TRIPS:
        for (label, lat, lng, mood, date_s, days, n_photos) in trip["stops"]:
            d0 = datetime.strptime(date_s, "%Y-%m-%d")
            for i in range(n_photos):
                count += 1
                f = OUT / f"IMG_{count:04d}.jpg"
                paint_photo(f, mood, label, count)
                when = d0 + timedelta(days=random.randint(0, max(days - 1, 0)),
                                      hours=random.randint(8, 21),
                                      minutes=random.randint(0, 59))
                stamp(f, jitter(lat, 0.02), jitter(lng, 0.02), when)

    # No-GPS strays (screenshots / downloads)
    for i in range(NO_GPS_COUNT):
        count += 1
        f = OUT / f"IMG_{count:04d}.jpg"
        paint_photo(f, "city", "nowhere", count)
        stamp(f, None, None, datetime(2023, 3, 1, 12) + timedelta(days=i * 40))

    # Zip it
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.iterdir()):
            z.write(f, f"meridian-sample-photos/{f.name}")

    placed = count - NO_GPS_COUNT
    print(f"Generated {count} photos ({placed} with GPS, {NO_GPS_COUNT} without)")
    print(f"Zip: {ZIP} ({ZIP.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
