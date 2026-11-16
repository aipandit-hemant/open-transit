"""Process-wide, read-only transit data shared by REST and MCP use cases."""
from functools import lru_cache
from pathlib import Path

import pandas as pd

try:
    from domain.core.transit import derive_relationships
except ImportError:  # Flat module layout (tests, standalone tooling)
    from transit import derive_relationships


_MODULE_DIR = Path(__file__).resolve().parent
TRANSIT_CSV = _MODULE_DIR / 'data/transit_v3.csv'
if not TRANSIT_CSV.exists():
    TRANSIT_CSV = _MODULE_DIR / 'transit_v3.csv'


@lru_cache(maxsize=1)
def transit_dataframe() -> pd.DataFrame:
    """Load the entire CSV once; callers must not mutate the shared DataFrame."""
    frame = pd.read_csv(TRANSIT_CSV,
                        dtype={'planet_name': 'category', 'rashi': 'int16', 'relationship': 'string'})
    for column in ('start_at', 'end_at'):
        if not frame[column].str.contains(r'(?:Z|[+-]\d{2}:\d{2})$', regex=True).all():
            raise ValueError('Transit timestamps must include a timezone')
        frame[column] = pd.to_datetime(frame[column], format='ISO8601', utc=True)
    if (frame.start_at >= frame.end_at).any() or not frame.rashi.between(1, 12).all():
        raise ValueError('Transit intervals require increasing timestamps and valid rashis')
    frame.sort_values(['planet_name', 'start_at'], inplace=True, ignore_index=True)
    previous = frame.groupby('planet_name', sort=False, observed=True).end_at.shift()
    if (previous.notna() & previous.ne(frame.start_at)).any():
        raise ValueError('Transit intervals must be contiguous for every planet')
    if set(frame.planet_name) != {'SUN', 'MON', 'MAR', 'MER', 'JUP', 'VEN', 'SAT', 'RAH', 'KET'}:
        raise ValueError('Transit CSV must contain all nine planets')
    return frame


@lru_cache(maxsize=1)
def transit_sign_dataframe() -> pd.DataFrame:
    """Prepare sign-only intervals once, without changing the complete shared data."""
    frame = transit_dataframe()
    changed = frame.planet_name.ne(frame.planet_name.shift()) | frame.rashi.ne(frame.rashi.shift())
    return frame.groupby(changed.cumsum(), sort=False).agg(
        planet_name=('planet_name', 'first'), start_at=('start_at', 'first'),
        end_at=('end_at', 'last'), rashi=('rashi', 'first'),
    ).reset_index(drop=True)


@lru_cache(maxsize=1)
def transit_coverage() -> dict:
    """Keep per-planet coverage bounds beside the shared data, prepared once."""
    bounds = transit_dataframe().groupby('planet_name', sort=False, observed=True).agg(
        start=('start_at', 'min'), end=('end_at', 'max'))
    return {code: (row.start, row.end) for code, row in bounds.iterrows()}


def transit_relationships_at(when) -> list:
    """Relationships among the transiting planets at one instant (Moon skipped).

    Reads the recorded relationship column of the rows active at ``when`` and
    reconstructs the exact pairings via transit.derive_relationships.
    """
    frame = transit_dataframe()
    when = pd.Timestamp(when)
    if when.tzinfo is None:
        when = when.tz_localize('UTC')
    active = frame.loc[(frame.start_at <= when) & (frame.end_at > when)]
    if set(active.planet_name) != set(frame.planet_name.cat.categories):
        raise ValueError('Requested instant is outside transit_v3.csv coverage')
    return derive_relationships({row.planet_name: {'start_at': row.start_at,
                                                   'relationship': row.relationship}
                                 for row in active.itertuples(index=False)})


def filter_transit_signs(planets: list[str], start, end) -> pd.DataFrame:
    """Filter all selected planets and overlapping intervals in one pandas query."""
    coverage = transit_coverage()
    if any(code not in coverage or start < coverage[code][0] or end > coverage[code][1]
           for code in planets):
        raise ValueError('Dasha window is outside transit_v3.csv coverage')
    frame = transit_sign_dataframe()
    return frame.loc[
        frame.planet_name.isin(planets) & (frame.start_at < end) & (frame.end_at > start)
    ]
