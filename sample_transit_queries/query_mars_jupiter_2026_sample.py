"""Query: when are Mars (MAR) and Jupiter (JUP) in any of the five relationships during 2026?

    python3 sample_transit_queries/query_mars_jupiter_2026_sample.py

The five relationships are chart.FIVE_SAMBANDHAS: exchange, conjunction, mutual
aspect, occupies-and-aspects-lord, occupies-and-receives-lord-aspect.

Each period is reported with its real start and end, even when it began in
2025 or runs into 2027; the 2025-2027 pada files provide that margin.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from transit_pada_query import load_moon_transits, load_planet_transits, relationship_periods

DATA = Path(__file__).resolve().parent.parent / 'data'
PLANETS_CSV = DATA / 'transit_pada_planets_2025-2027.csv'
MOON_CSV = DATA / 'transit_pada_moon_2025-2027.csv'

YEAR_2026 = (date(2026, 1, 1), date(2027, 1, 1))


def mars_jupiter_relationships_in_2026() -> pd.DataFrame:
    """One row per relationship period of Mars and Jupiter touching 2026."""
    planets = load_planet_transits(PLANETS_CSV)
    moon = load_moon_transits(MOON_CSV)
    periods = relationship_periods('MAR', 'JUP', planets, moon, *YEAR_2026)
    return pd.DataFrame([{
        'relationship': period.relationship.type.value,
        'mars_rashi': _rashi_of('MAR', period),
        'jupiter_rashi': _rashi_of('JUP', period),
        'start': period.start,
        'end': period.end,
        'duration': period.duration,
        'cut_by_data': period.starts_before_coverage or period.ends_after_coverage,
    } for period in periods])


def _rashi_of(planet: str, period) -> str:
    facts = period.relationship.to_dict()
    return facts['source_rashi_name'] if facts['source'] == planet else facts['target_rashi_name']


def print_report(periods: pd.DataFrame) -> None:
    """Periods sharing one span (same placements) are printed together."""
    print('Mars-Jupiter relationships during 2026 (times in UTC)\n')
    spans = periods.groupby(['start', 'end', 'mars_rashi', 'jupiter_rashi'], sort=True)
    for (start, end, mars_rashi, jupiter_rashi), span in spans:
        print(f'{start:%d %b %Y %H:%M:%S}  ->  {end:%d %b %Y %H:%M:%S}   '
              f'({(end - start).days} days)   Mars in {mars_rashi}, Jupiter in {jupiter_rashi}')
        for relationship in span['relationship']:
            print(f'    - {relationship}')
        if span['cut_by_data'].any():
            print('    ! limited by the data files; extend the pada files for the full span')


if __name__ == '__main__':
    report = mars_jupiter_relationships_in_2026()
    print_report(report)
