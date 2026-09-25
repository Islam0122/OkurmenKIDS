from __future__ import annotations

import datetime as dt

from django.test import SimpleTestCase

from apps.scholarships.models import AwardMode
from apps.scholarships.services.periods import cycle_window, due_cycles, latest_award_date


class CycleWindowTests(SimpleTestCase):
    def test_first_of_month_evaluates_previous_calendar_month(self):
        w = cycle_window(1, dt.date(2026, 10, 1))
        self.assertEqual((w.period_start, w.period_end), (dt.date(2026, 9, 1), dt.date(2026, 9, 30)))

    def test_spec_timeline(self):
        # Oct 1 → September, Nov 1 → October, Dec 1 → November.
        for award, start, end in [
            (dt.date(2026, 10, 1), dt.date(2026, 9, 1), dt.date(2026, 9, 30)),
            (dt.date(2026, 11, 1), dt.date(2026, 10, 1), dt.date(2026, 10, 31)),
            (dt.date(2026, 12, 1), dt.date(2026, 11, 1), dt.date(2026, 11, 30)),
        ]:
            w = cycle_window(1, award)
            self.assertEqual((w.period_start, w.period_end), (start, end))

    def test_fifteenth_cycle_is_a_rolling_month(self):
        w = cycle_window(15, dt.date(2026, 10, 15))
        self.assertEqual((w.period_start, w.period_end), (dt.date(2026, 9, 15), dt.date(2026, 10, 14)))

    def test_january_rolls_back_to_december(self):
        w = cycle_window(1, dt.date(2027, 1, 1))
        self.assertEqual((w.period_start, w.period_end), (dt.date(2026, 12, 1), dt.date(2026, 12, 31)))
        w = cycle_window(15, dt.date(2027, 1, 15))
        self.assertEqual((w.period_start, w.period_end), (dt.date(2026, 12, 15), dt.date(2027, 1, 14)))

    def test_february_and_leap_years(self):
        self.assertEqual(cycle_window(1, dt.date(2026, 3, 1)).period_end, dt.date(2026, 2, 28))
        self.assertEqual(cycle_window(1, dt.date(2028, 3, 1)).period_end, dt.date(2028, 2, 29))
        w = cycle_window(15, dt.date(2028, 3, 15))
        self.assertEqual((w.period_start, w.period_end), (dt.date(2028, 2, 15), dt.date(2028, 3, 14)))

    def test_period_always_ends_before_the_award_date(self):
        for day in (1, 15):
            for month in range(1, 13):
                w = cycle_window(day, dt.date(2026, month, day))
                self.assertLess(w.period_end, w.award_date)

    def test_rejects_mismatched_or_unsupported_days(self):
        with self.assertRaises(ValueError):
            cycle_window(1, dt.date(2026, 10, 2))
        with self.assertRaises(ValueError):
            cycle_window(10, dt.date(2026, 10, 10))


class DueCycleTests(SimpleTestCase):
    def test_latest_award_date(self):
        self.assertEqual(latest_award_date(1, dt.date(2026, 10, 1)), dt.date(2026, 10, 1))
        self.assertEqual(latest_award_date(15, dt.date(2026, 10, 14)), dt.date(2026, 9, 15))
        self.assertEqual(latest_award_date(15, dt.date(2026, 1, 3)), dt.date(2025, 12, 15))

    def test_monthly_mode_only_has_the_first(self):
        windows = due_cycles(AwardMode.MONTHLY, dt.date(2026, 10, 15))
        self.assertEqual([(w.award_day, w.award_date) for w in windows], [(1, dt.date(2026, 10, 1))])

    def test_twice_monthly_mode_has_two_independent_cycles(self):
        windows = due_cycles(AwardMode.TWICE_MONTHLY, dt.date(2026, 10, 10))
        self.assertEqual(
            [(w.award_day, w.award_date) for w in windows],
            [(1, dt.date(2026, 10, 1)), (15, dt.date(2026, 9, 15))],
        )
