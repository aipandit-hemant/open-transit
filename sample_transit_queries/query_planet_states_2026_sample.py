"""Queries for the planet-state dignities (exaltation, debilitation, own
sign, Moolatrikona, Vargottama, and the Panchadha Maitri relation from Adhi
Mitra down to Adhi Shatru) added to ``transit_pada_query.dignity_periods``.

    python3 sample_transit_queries/query_planet_states_2026_sample.py

Three example queries, each printed with the start (and, where the state can
end again, the end) of every matching span between 1 May 2026 and 31 Dec 2026:

1. When does Jupiter go Uccha (exalted)?
2. When is Mars debilitated (neecha)?
3. When are Mars and Jupiter conjunct while Mars is *not* debilitated?

Run ``python3 transit_pada.py --start 2026-05-01 --end 2027-01-01
--timezone UTC --label 2026-05-01_2026-12-31`` first to (re)build the CSVs
this script reads.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chart import DignityType, SambandhaType
from transit_pada_query import (dignity_periods, filter_dignities, load_moon_transits,
                                load_planet_transits, merge_touching, relationship_periods,
                                subtract_periods)

DATA = Path(__file__).resolve().parent.parent / 'data'
PLANETS_CSV = DATA / 'transit_pada_planets_2026-05-01_2026-12-31.csv'
MOON_CSV = DATA / 'transit_pada_moon_2026-05-01_2026-12-31.csv'

QUERY_WINDOW = (date(2026, 5, 1), date(2026, 12, 31))


def _load():
    return load_planet_transits(PLANETS_CSV), load_moon_transits(MOON_CSV)


# --- 1. When does Jupiter go Uccha (exalted)? --------------------------------

def jupiter_exaltation_periods() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Every span in which Jupiter stands exalted (in Cancer) during the window."""
    planets, moon = _load()
    windows = dignity_periods('JUP', planets, moon, *QUERY_WINDOW)
    exalted = filter_dignities(windows, [DignityType.EXALTED])
    return merge_touching((window.start, window.end) for window in exalted)


# --- 2. When is Mars debilitated (neecha)? -----------------------------------

def mars_debilitation_periods() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Every span in which Mars stands debilitated (in Cancer) during the window."""
    planets, moon = _load()
    windows = dignity_periods('MAR', planets, moon, *QUERY_WINDOW)
    debilitated = filter_dignities(windows, [DignityType.DEBILITATED])
    return merge_touching((window.start, window.end) for window in debilitated)


# --- 3. Mars and Jupiter conjunct, Mars not debilitated ---------------------

def mars_jupiter_conjunction_not_debilitated() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Conjunction spans of Mars/Jupiter, minus any time Mars is debilitated."""
    planets, moon = _load()
    conjunctions = relationship_periods('MAR', 'JUP', planets, moon, *QUERY_WINDOW,
                                        types=[SambandhaType.CONJUNCTION])
    mars_debilitated = filter_dignities(
        dignity_periods('MAR', planets, moon, *QUERY_WINDOW), [DignityType.DEBILITATED])
    return merge_touching(subtract_periods(conjunctions, mars_debilitated))


def _print_periods(title: str, periods: list[tuple[pd.Timestamp, pd.Timestamp]]) -> None:
    print(title)
    if not periods:
        print('    (none in this window)')
    for start, end in periods:
        print(f'    {start:%d %b %Y %H:%M:%S}  ->  {end:%d %b %Y %H:%M:%S}   ({(end - start).days} days)')
    print()


if __name__ == '__main__':
    _print_periods('1. Jupiter exalted (Uccha):', jupiter_exaltation_periods())
    _print_periods('2. Mars debilitated (Neecha):', mars_debilitation_periods())
    _print_periods('3. Mars conjunct Jupiter, Mars not debilitated:',
                   mars_jupiter_conjunction_not_debilitated())
