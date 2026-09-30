# SPDX-License-Identifier: AGPL-3.0-or-later
"""Jalali (Shamsi) <-> Gregorian conversion and Persian formatting helpers.

Conversion algorithm ported from jalaali-js,
Copyright (c) 2020 Behrang Norouzinia, MIT License
(see licenses/jalaali-js-MIT.txt). Accurate for Jalali years -61 .. 3177.
"""
from datetime import date

MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
# Python weekday(): Monday=0 ... Sunday=6
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
WEEK_HEADER = ["ش", "ی", "د", "س", "چ", "پ", "ج"]  # Saturday first

_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
           1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]


def _div(a, b):
    return int(a / b)


def _mod(a, b):
    return a - int(a / b) * b


def _jal_cal(jy):
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    for jm in _BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return leap, gy, march


def _g2d(gy, gm, gd):
    d = (_div((gy + _div(gm - 8, 6) + 100100) * 1461, 4)
         + _div(153 * _mod(gm + 9, 12) + 2, 5) + gd - 34840408)
    return d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752


def _d2g(jdn):
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return gy, gm, gd


def _j2d(jy, jm, jd):
    _, gy, march = _jal_cal(jy)
    return _g2d(gy, 3, march) + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1


def _d2j(jdn):
    gy = _d2g(jdn)[0]
    jy = gy - 621
    leap, _, march = _jal_cal(jy)
    jdn1f = _g2d(gy, 3, march)
    k = jdn - jdn1f
    if k >= 0:
        if k <= 185:
            return jy, 1 + _div(k, 31), _mod(k, 31) + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if leap == 1:
            k += 1
    return jy, 7 + _div(k, 30), _mod(k, 30) + 1


def to_jalali(d: date):
    return _d2j(_g2d(d.year, d.month, d.day))


def to_gregorian(jy: int, jm: int, jd: int) -> date:
    return date(*_d2g(_j2d(jy, jm, jd)))


def is_leap(jy: int) -> bool:
    return _jal_cal(jy)[0] == 0


def month_length(jy: int, jm: int) -> int:
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_leap(jy) else 29


def valid(jy: int, jm: int, jd: int) -> bool:
    return 1 <= jm <= 12 and 1 <= jd <= month_length(jy, jm)


# ---------- formatting ----------
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def fa(value) -> str:
    """Convert Latin digits to Persian digits."""
    return str(value).translate(_FA_DIGITS)


def en_digits(value: str) -> str:
    """Convert Persian/Arabic digits typed by the user to Latin digits."""
    return (value or "").translate(_EN_DIGITS)


def jstr(d: date) -> str:
    """1405-07-08 (Latin digits, used in URLs and forms)."""
    jy, jm, jd = to_jalali(d)
    return f"{jy:04d}-{jm:02d}-{jd:02d}"


def parse_jstr(s: str) -> date:
    jy, jm, jd = (int(x) for x in en_digits(s).split("-"))
    if not valid(jy, jm, jd):
        raise ValueError("invalid jalali date")
    return to_gregorian(jy, jm, jd)


def long_date(d: date) -> str:
    """سه‌شنبه ۸ مهر ۱۴۰۵"""
    jy, jm, jd = to_jalali(d)
    return f"{WEEKDAYS[d.weekday()]} {fa(jd)} {MONTHS[jm - 1]} {fa(jy)}"


def short_date(d: date) -> str:
    """۸ مهر"""
    _, jm, jd = to_jalali(d)
    return f"{fa(jd)} {MONTHS[jm - 1]}"
