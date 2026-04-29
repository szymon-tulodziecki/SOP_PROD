from __future__ import annotations

from datetime import date, timedelta


class JournalService:
    @staticmethod
    def count_working_days(date_from: date, date_to: date, country: str = 'PL') -> int:
        holidays_calendar = _load_holidays(country, years=range(date_from.year, date_to.year + 1))
        days = 0
        current = date_from
        while current < date_to:
            current += timedelta(days=1)
            if current.weekday() < 5 and current not in holidays_calendar:
                days += 1
        return days

    @staticmethod
    def detect_gaps(entries, threshold_days: int = 3, country: str = 'PL') -> list[dict]:
        if not entries:
            return []

        dates = sorted(entry.entry_date for entry in entries)
        gaps = []
        for previous, current in zip(dates, dates[1:]):
            working_days = JournalService.count_working_days(previous, current, country=country)
            if working_days > threshold_days:
                gaps.append({
                    'date_from': previous,
                    'date_to': current,
                    'working_days': working_days,
                })
        return gaps


def _load_holidays(country: str, years):
    try:
        import holidays
    except ImportError:
        return set()
    return holidays.country_holidays(country, years=years)
