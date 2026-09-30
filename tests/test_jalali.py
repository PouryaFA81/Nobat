# SPDX-License-Identifier: AGPL-3.0-or-later
import unittest
from datetime import date, timedelta

from app import jalali


class JalaliTests(unittest.TestCase):
    def test_known_dates(self):
        self.assertEqual(jalali.to_jalali(date(2025, 3, 21)), (1404, 1, 1))
        self.assertEqual(jalali.to_jalali(date(2024, 3, 20)), (1403, 1, 1))
        self.assertEqual(jalali.to_jalali(date(2026, 9, 29)), (1405, 7, 7))
        self.assertEqual(jalali.to_gregorian(1405, 7, 7), date(2026, 9, 29))

    def test_round_trip_over_many_years(self):
        d = date(1990, 1, 1)
        for i in range(0, 60 * 366, 3):
            x = d + timedelta(days=i)
            self.assertEqual(jalali.to_gregorian(*jalali.to_jalali(x)), x)

    def test_leap_years_and_month_lengths(self):
        self.assertTrue(jalali.is_leap(1403))
        self.assertFalse(jalali.is_leap(1404))
        self.assertEqual(jalali.month_length(1403, 12), 30)
        self.assertEqual(jalali.month_length(1404, 12), 29)
        self.assertEqual(jalali.month_length(1404, 6), 31)
        self.assertEqual(jalali.month_length(1404, 7), 30)
        self.assertFalse(jalali.valid(1404, 7, 31))

    def test_formatting(self):
        self.assertEqual(jalali.fa("12:30"), "۱۲:۳۰")
        self.assertEqual(jalali.en_digits("۱۴۰۵-۰۷-۰۸"), "1405-07-08")
        self.assertEqual(jalali.long_date(date(2026, 9, 29)), "سه‌شنبه ۷ مهر ۱۴۰۵")
        self.assertEqual(jalali.jstr(date(2026, 9, 29)), "1405-07-07")
        self.assertEqual(jalali.parse_jstr("۱۴۰۵-۰۷-۰۷"), date(2026, 9, 29))
        with self.assertRaises(ValueError):
            jalali.parse_jstr("1404-12-30")  # 1404 is not a leap year


if __name__ == "__main__":
    unittest.main()
