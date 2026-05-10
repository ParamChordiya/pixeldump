"""EXIF parsing helpers."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import exifread
import pillow_heif
from PIL import Image

from pixeldump.core.types import GPSCoord

# Register HEIF/HEIC opener once at module load so Image.open works for HEIC.
pillow_heif.register_heif_opener()

_RAW_EXTS = frozenset({".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"})

# EXIF tag IDs
_TAG_DATETIME_ORIGINAL = 36867
_TAG_DATETIME = 306
_TAG_GPSINFO = 34853
_TAG_MAKE = 271
_TAG_MODEL = 272


def _parse_exif_datetime(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def _read_date_with_exifread(path: Path) -> datetime | None:
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(
                f, details=False, stop_tag="EXIF DateTimeOriginal"
            )
        tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        if tag is None:
            return None
        return _parse_exif_datetime(str(tag))
    except Exception:
        return None


def read_date_taken(path: Path) -> datetime | None:
    """Return the EXIF DateTimeOriginal, or None if missing/unparseable."""
    suffix = path.suffix.lower()
    if suffix in _RAW_EXTS:
        return _read_date_with_exifread(path)

    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            value = exif.get(_TAG_DATETIME_ORIGINAL) or exif.get(_TAG_DATETIME)
            if value is None:
                # Try the EXIF IFD sub-block (some files put DateTimeOriginal there).
                try:
                    ifd = exif.get_ifd(0x8769)  # ExifOffset
                except Exception:
                    ifd = {}
                if ifd:
                    value = ifd.get(_TAG_DATETIME_ORIGINAL) or ifd.get(_TAG_DATETIME)
            if value is None:
                return None
            return _parse_exif_datetime(str(value))
    except Exception:
        return None


def _dms_to_decimal(dms: Any, ref: str) -> float:
    d, m, s = (float(x) for x in dms)
    decimal = d + m / 60.0 + s / 3600.0
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def read_gps(path: Path) -> GPSCoord | None:
    """Return GPS coordinates from EXIF, or None if absent."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            try:
                gps_ifd = exif.get_ifd(_TAG_GPSINFO)
            except Exception:
                gps_ifd = {}
            if not gps_ifd:
                return None
            # GPS sub-IFD tag IDs
            lat = gps_ifd.get(2)
            lat_ref = gps_ifd.get(1)
            lon = gps_ifd.get(4)
            lon_ref = gps_ifd.get(3)
            if lat is None or lon is None or lat_ref is None or lon_ref is None:
                return None
            lat_dec = _dms_to_decimal(lat, str(lat_ref))
            lon_dec = _dms_to_decimal(lon, str(lon_ref))
            if not (-90.0 <= lat_dec <= 90.0):
                return None
            if not (-180.0 <= lon_dec <= 180.0):
                return None
            return GPSCoord(lat=lat_dec, lon=lon_dec)
    except Exception:
        return None


def read_camera_model(path: Path) -> str | None:
    """Return camera model string from EXIF, or None if absent."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            make = exif.get(_TAG_MAKE)
            model = exif.get(_TAG_MODEL)
            make_s = str(make).strip() if make else ""
            model_s = str(model).strip() if model else ""
            if make_s and model_s:
                return f"{make_s} {model_s}"
            if model_s:
                return model_s
            if make_s:
                return make_s
            return None
    except Exception:
        return None
