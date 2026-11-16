"""Transit listings: filters, planet codes, and the relationship CSV column.

Relationship *detection* lives in chart.py (build_rashi_chart / rashi_sambandhas);
this module only records, parses, and derives those results for transit_v3.csv.

Recording scheme
----------------
Every CSV row describes one planet over an interval in which its own rashi is
constant (rows split on any rashi/nakshatra change).  The ``relationship``
column of a row lists every sambandha involving that planet, detected from all
planets' signs at the row's ``start_at``.  An entry reads::

    MUTUAL_ASPECT:VEN.6:SAT.12

i.e. ``type:source.rashi:target.rashi``, entries joined by ``;``.  Because a
planet's sign never changes inside its row, the relationships valid at any
instant can be reconstructed exactly: for each pair, the entry recorded on the
*later-starting* of the two active rows was computed while the other planet's
current row was already running, so both signs match the queried instant
(see :func:`derive_relationships`).  Moon-based relationships are skipped.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence

import pandas as pd

try:
    from domain.core.chart import (GrahaId, RashiId, SambandhaType,
                                   rashi_name_from_num, rashi_sambandhas)
except ImportError:  # Flat module layout (tests, standalone tooling)
    from chart import (GrahaId, RashiId, SambandhaType,
                       rashi_name_from_num, rashi_sambandhas)


# --- Planet codes used by the transit CSV ----------------------------------

TRANSIT_PLANET_CODES: Dict[str, GrahaId] = {
    'SUN': GrahaId.SUN, 'MON': GrahaId.MOON, 'MAR': GrahaId.MARS,
    'MER': GrahaId.MERCURY, 'JUP': GrahaId.JUPITER, 'VEN': GrahaId.VENUS,
    'SAT': GrahaId.SATURN, 'RAH': GrahaId.RAHU, 'KET': GrahaId.KETU,
}
GRAHA_TO_TRANSIT_CODE: Dict[GrahaId, str] = {g: c for c, g in TRANSIT_PLANET_CODES.items()}

MOON_CODE = 'MON'

#: Sambandhas that read the same from either side; directional types
#: (DISPOSITOR, lord occupancy/aspect links) keep their canonical source.
SYMMETRIC_SAMBANDHAS = frozenset({
    SambandhaType.CONJUNCTION, SambandhaType.EXCHANGE, SambandhaType.MUTUAL_ASPECT,
})

RELATIONSHIP_ENTRY_SEPARATOR = ';'
RELATIONSHIP_FIELD_SEPARATOR = ':'
RELATIONSHIP_RASHI_SEPARATOR = '.'

_SAMBANDHA_ORDER = {stype: index for index, stype in enumerate(SambandhaType)}
_GRAHA_ORDER = {graha: index for index, graha in enumerate(GrahaId)}


@dataclass(frozen=True)
class TransitRelationship:
    """One detected sambandha between two transiting planets, with their signs."""
    type: SambandhaType
    source: GrahaId
    source_rashi: RashiId
    target: GrahaId
    target_rashi: RashiId

    def involves(self, graha: GrahaId) -> bool:
        return graha in (self.source, self.target)

    def canonical(self) -> 'TransitRelationship':
        """Order symmetric pairs consistently so both directions compare equal."""
        if self.type in SYMMETRIC_SAMBANDHAS and _GRAHA_ORDER[self.target] < _GRAHA_ORDER[self.source]:
            return TransitRelationship(self.type, self.target, self.target_rashi,
                                       self.source, self.source_rashi)
        return self

    @property
    def sort_key(self) -> tuple:
        return (_SAMBANDHA_ORDER[self.type], _GRAHA_ORDER[self.source], _GRAHA_ORDER[self.target])

    def format(self) -> str:
        return RELATIONSHIP_FIELD_SEPARATOR.join((
            self.type.value,
            f'{GRAHA_TO_TRANSIT_CODE[self.source]}{RELATIONSHIP_RASHI_SEPARATOR}{int(self.source_rashi)}',
            f'{GRAHA_TO_TRANSIT_CODE[self.target]}{RELATIONSHIP_RASHI_SEPARATOR}{int(self.target_rashi)}',
        ))

    @classmethod
    def parse(cls, entry: str) -> 'TransitRelationship':
        type_name, source_part, target_part = entry.strip().split(RELATIONSHIP_FIELD_SEPARATOR)
        source_code, source_rashi = source_part.split(RELATIONSHIP_RASHI_SEPARATOR)
        target_code, target_rashi = target_part.split(RELATIONSHIP_RASHI_SEPARATOR)
        return cls(SambandhaType(type_name),
                   TRANSIT_PLANET_CODES[source_code], RashiId(int(source_rashi)),
                   TRANSIT_PLANET_CODES[target_code], RashiId(int(target_rashi)))

    def to_dict(self) -> dict:
        return {
            'relationship': self.type.value,
            'source': GRAHA_TO_TRANSIT_CODE[self.source],
            'source_planet': self.source.value,
            'source_rashi': int(self.source_rashi),
            'source_rashi_name': rashi_name_from_num(int(self.source_rashi)),
            'target': GRAHA_TO_TRANSIT_CODE[self.target],
            'target_planet': self.target.value,
            'target_rashi': int(self.target_rashi),
            'target_rashi_name': rashi_name_from_num(int(self.target_rashi)),
        }


@dataclass(frozen=True)
class TransitFilter:
    """Criteria for transit listing queries."""
    start_date: date
    end_date: date
    planet_names: Optional[Sequence[str]] = None
    rashi_ids: Optional[Sequence[int]] = None
    sort_by_end_date: bool = False


# --- Relationship column serialisation --------------------------------------

def format_relationships(relationships: Iterable[TransitRelationship]) -> str:
    return RELATIONSHIP_ENTRY_SEPARATOR.join(
        rel.format() for rel in sorted(relationships, key=lambda rel: rel.sort_key))


def parse_relationships(value) -> tuple[TransitRelationship, ...]:
    """Read one CSV relationship cell; blank and NaN cells mean no relationship."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ()
    text = str(value).strip()
    if not text:
        return ()
    return tuple(TransitRelationship.parse(entry)
                 for entry in text.split(RELATIONSHIP_ENTRY_SEPARATOR) if entry.strip())


def relationship_entries_for_planet(planet_code: str,
                                    rashi_by_code: Mapping[str, int]) -> list[TransitRelationship]:
    """All sambandhas involving one planet for a full sign snapshot (Moon skipped).

    Detection is delegated entirely to chart.py; this merely maps CSV codes.
    Symmetric types are kept where the planet is the source (the mirrored
    triple covers the other side); directional types are kept on both sides
    so each row is self-contained for its planet.
    """
    if planet_code == MOON_CODE:
        return []
    graha = TRANSIT_PLANET_CODES[planet_code]
    positions = {TRANSIT_PLANET_CODES[code]: RashiId(int(rashi))
                 for code, rashi in rashi_by_code.items()}
    # Moon relationships are excluded; Cancer keeps its lord present in the chart.
    positions.setdefault(GrahaId.MOON, RashiId.CANCER)
    entries = []
    for stype, source, target in rashi_sambandhas(positions, exclude=[GrahaId.MOON]):
        if source == graha or (target == graha and stype not in SYMMETRIC_SAMBANDHAS):
            entries.append(TransitRelationship(
                stype, source, positions[source], target, positions[target]))
    return sorted(entries, key=lambda rel: rel.sort_key)


def derive_relationships(active_rows: Mapping[str, Mapping]) -> list[TransitRelationship]:
    """Reconstruct the relationships valid at one instant from the active rows.

    ``active_rows`` maps each planet code to its row covering the instant and
    must expose ``start_at`` and ``relationship``.  For every pair only the
    entry recorded on the later-starting row is trusted: at that row's start
    the partner's current row was already active, so both recorded signs equal
    the signs at the queried instant.  Symmetric duplicates are canonicalised.
    """
    chosen: dict[tuple, TransitRelationship] = {}
    for code, row in active_rows.items():
        if code == MOON_CODE:
            continue
        for relationship in parse_relationships(row.get('relationship')):
            source_code = GRAHA_TO_TRANSIT_CODE[relationship.source]
            target_code = GRAHA_TO_TRANSIT_CODE[relationship.target]
            if code not in (source_code, target_code):
                continue  # A row only vouches for pairs involving its own planet.
            other_code = target_code if source_code == code else source_code
            other_row = active_rows.get(other_code)
            if other_row is None or other_row['start_at'] > row['start_at']:
                continue
            canonical = relationship.canonical()
            chosen[(canonical.type, canonical.source, canonical.target)] = canonical
    return sorted(chosen.values(), key=lambda rel: rel.sort_key)


# --- CSV enrichment ----------------------------------------------------------

def build_relationship_column(frame: pd.DataFrame) -> pd.Series:
    """Compute the relationship cell for every transit row of ``frame``.

    Requires ``planet_name``, ``start_at`` and ``rashi`` columns; rows of the
    same planet must not overlap.  Moon rows stay blank (Moon is skipped).
    """
    starts = pd.to_datetime(frame['start_at'], format='ISO8601', utc=True).astype('int64')
    rashis = frame['rashi'].astype(int)
    planets = frame['planet_name'].astype(str)

    per_planet: Dict[str, tuple[list[int], list[int]]] = {}
    for code in planets.unique():
        subset = frame.index[planets == code]
        ordered = sorted(subset, key=lambda i: starts[i])
        per_planet[code] = ([starts[i] for i in ordered], [rashis[i] for i in ordered])

    def rashi_at(code: str, when: int) -> int:
        planet_starts, planet_rashis = per_planet[code]
        index = bisect_right(planet_starts, when) - 1
        return planet_rashis[max(index, 0)]

    snapshot_cache: Dict[tuple, Dict[str, str]] = {}
    non_moon_codes = sorted(code for code in per_planet if code != MOON_CODE)

    def cells_for_snapshot(snapshot: Mapping[str, int]) -> Dict[str, str]:
        key = tuple(snapshot[code] for code in non_moon_codes)
        cached = snapshot_cache.get(key)
        if cached is None:
            cached = {code: format_relationships(relationship_entries_for_planet(code, snapshot))
                      for code in non_moon_codes}
            snapshot_cache[key] = cached
        return cached

    values = []
    for index in frame.index:
        code = planets[index]
        if code == MOON_CODE:
            values.append('')
            continue
        when = starts[index]
        snapshot = {other: rashi_at(other, when) for other in non_moon_codes}
        snapshot[code] = int(rashis[index])  # the row's own sign is authoritative
        values.append(cells_for_snapshot(snapshot)[code])
    return pd.Series(values, index=frame.index, name='relationship')


def enrich_transit_csv(csv_path: Path | str, output_path: Path | str | None = None) -> pd.DataFrame:
    """Add (or refresh) the relationship column of a transit CSV in place."""
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    frame['relationship'] = build_relationship_column(frame)
    frame.to_csv(output_path or csv_path, index=False)
    return frame


if __name__ == '__main__':
    import sys

    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / 'transit_v3.csv'
    destination = Path(sys.argv[2]) if len(sys.argv) > 2 else source
    enriched = enrich_transit_csv(source, destination)
    print(f'Wrote {len(enriched)} rows with relationship column to {destination}')
