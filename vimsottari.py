"""Vimshottari periods and their natal-frame transit enrichment.

Public methods live on Vimsottari; underscore-prefixed helpers are module-internal.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from itertools import accumulate
from math import isfinite

try:
    from domain.core.chart import BhavaNumber, Chart, Graha, GrahaId, NakshatraId, RashiId, SambandhaType
except ImportError:  # Flat module layout (tests, standalone tooling)
    from chart import BhavaNumber, Chart, Graha, GrahaId, NakshatraId, RashiId, SambandhaType


class VimsottariLevel(Enum):
    MAHADASHA = "MAHADASHA"
    ANTARDASHA = "ANTARDASHA"
    PRATYANTARDASHA = "PRATYANTARDASHA"
    SOOKSHMADASHA = "SOOKSHMADASHA"
    PRANADASHA = "PRANADASHA"


class VimsottariDasha:
    def __init__(self, lord: Graha, start_date: datetime, end_date: datetime, level_type: VimsottariLevel):
        self._lord = lord
        self._start_date = start_date
        self._end_date = end_date
        self._level_type = level_type

    @property
    def lord(self) -> Graha: return self._lord
    @property
    def start_date(self) -> datetime: return self._start_date
    @property
    def end_date(self) -> datetime: return self._end_date
    @property
    def type(self) -> VimsottariLevel: return self._level_type

    def __repr__(self) -> str:
        return f"VimsottariDasha({self._level_type.value}: Lord={self._lord.type.value})"


class VimsottariCurrentPeriods:
    def __init__(self, md: VimsottariDasha, ad: VimsottariDasha, pd: VimsottariDasha,
                 sd: VimsottariDasha, prd: VimsottariDasha):
        self._md, self._ad, self._pd, self._sd, self._prd = md, ad, pd, sd, prd

    @property
    def md(self) -> VimsottariDasha: return self._md
    @property
    def ad(self) -> VimsottariDasha: return self._ad
    @property
    def pd(self) -> VimsottariDasha: return self._pd
    @property
    def sd(self) -> VimsottariDasha: return self._sd
    @property
    def prd(self) -> VimsottariDasha: return self._prd


VIMSOTTARI_YEAR_DAYS = 365.25
VIMSOTTARI_ORDER = (GrahaId.KETU, GrahaId.VENUS, GrahaId.SUN, GrahaId.MOON,
                    GrahaId.MARS, GrahaId.RAHU, GrahaId.JUPITER, GrahaId.SATURN, GrahaId.MERCURY)
VIMSOTTARI_YEARS = (7, 20, 6, 10, 7, 18, 16, 19, 17)
VIMSOTTARI_LEVELS = tuple(VimsottariLevel)
VIMSOTTARI_LEVEL_NAMES = ('Mahadasha', 'Antardasha', 'Pratyantardasha', 'Sukshma', 'Prana')
_VIMSOTTARI_INDEX = {lord: index for index, lord in enumerate(VIMSOTTARI_ORDER)}
_VIMSOTTARI_CUMULATIVE = tuple(
    tuple(accumulate((VIMSOTTARI_YEARS[(first + offset) % 9] for offset in range(9)), initial=0))
    for first in range(9)
)
_MICROSECOND = timedelta(microseconds=1)


@dataclass(frozen=True, slots=True)
class VimsottariPeriod:
    """A lightweight period: planet ID and precise dates, without chart entities."""
    lord: GrahaId
    start_date: datetime
    end_date: datetime
    level: VimsottariLevel

    def to_dict(self) -> dict:
        return {'level': VIMSOTTARI_LEVEL_NAMES[VIMSOTTARI_LEVELS.index(self.level)],
                'lord': self.lord.value, 'startDate': self.start_date.isoformat(),
                'endDate': self.end_date.isoformat()}


# Private implementation helpers; callers use the Vimsottari public methods below.
def _instant(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError('Dasha query datetime must include a timezone')
        return value.astimezone(timezone.utc)
    return datetime.combine(value, datetime.min.time(), timezone.utc)


def _period(start: datetime, duration_us: int, first: int, offset: int, depth: int) -> VimsottariPeriod:
    cumulative = _VIMSOTTARI_CUMULATIVE[first]
    return VimsottariPeriod(
        VIMSOTTARI_ORDER[(first + offset) % 9],
        start + (duration_us * cumulative[offset] // 120) * _MICROSECOND,
        start + (duration_us * cumulative[offset + 1] // 120) * _MICROSECOND,
        VIMSOTTARI_LEVELS[depth],
    )


_TRANSIT_CODES = dict(zip(GrahaId, ('SUN', 'MON', 'MAR', 'MER', 'JUP', 'VEN', 'SAT', 'RAH', 'KET')))
_TRANSIT_PLANETS = {code: planet for planet, code in _TRANSIT_CODES.items()}
_NODES = {GrahaId.RAHU, GrahaId.KETU}


def _node_pair(source: GrahaId, target: GrahaId) -> bool:
    return source is not target and source in _NODES and target in _NODES


def _transit_planets(chart: Chart, md: GrahaId, ad: GrahaId, pd: GrahaId) -> tuple[str, ...]:
    lords = {md, ad, pd}
    selected = {*lords, chart.lagnesh.type}
    for lord in lords:
        selected.update(planet.type for planet in chart.graha(lord).sambandha.all
                        if not _node_pair(lord, planet.type))
    selected.update(planet for planet in GrahaId if chart.graha(planet).rashi.lord.type in lords)
    return tuple(_TRANSIT_CODES[planet] for planet in GrahaId
                 if planet in selected and planet is not GrahaId.MOON)


def _kundalis(value: str) -> tuple[str, ...]:
    choices = {'lagna': ('from_lagna',), 'chandra': ('from_moon',), 'both': ('from_lagna', 'from_moon')}
    if value not in choices:
        raise ValueError('kundali must be lagna, chandra, or both')
    return choices[value]


def _natal_targets(chart: Chart, *, frames=('from_lagna', 'from_moon')) -> list[tuple[str, str, str, RashiId]]:
    targets = []
    for frame in frames:
        reference = chart.lagna.rashi.type if frame == 'from_lagna' else chart.graha(GrahaId.MOON).rashi.type
        for house in BhavaNumber:
            rashi = RashiId((int(reference) + int(house) - 2) % 12 + 1)
            targets.append(('house', str(int(house)), frame, rashi))
            # A house lord is activated at that lord's natal placement, not its own sign.
            targets.append(('house_lord', str(int(house)), frame, chart.get_rashi_lord(rashi).rashi.type))
    return targets


def _aspected_rashis(planet: GrahaId, rashi: RashiId) -> set[RashiId]:
    try:
        from domain.core.horoscope import SPECIAL_ASPECTS
    except ImportError:  # chart.py carries the same house-counted aspect table
        try:
            from domain.core.chart import SPECIAL_ASPECTS
        except ImportError:
            from chart import SPECIAL_ASPECTS

    return {RashiId((int(rashi) + offset - 2) % 12 + 1)
            for offset in SPECIAL_ASPECTS.get(planet.value, [7])}


def _transit_activations(targets, planet: GrahaId, rashi: RashiId) -> list[tuple]:
    aspected = _aspected_rashis(planet, rashi)
    effects = []
    for kind, house, frame, target in targets:
        if target == rashi:
            effects.append((kind, house, frame, 'occupy_by' if kind == 'house' else 'conjunct_by', planet.value))
        if target in aspected:
            effects.append((kind, house, frame, 'aspect_by', planet.value))
    return effects


def _natal_relationships(graha: Graha) -> dict[GrahaId, set[str]]:
    relationships = {}
    for relation in SambandhaType:
        for other in graha.sambandha.get(relation):
            if not _node_pair(graha.type, other.type):
                relationships.setdefault(other.type, set()).add(relation.value.lower())
    for other in graha.aspected_planets:
        if not _node_pair(graha.type, other.type):
            relationships.setdefault(other.type, set()).add('aspect')
    return relationships


def _dasha_activation(chart: Chart, md: GrahaId, ad: GrahaId, pd: GrahaId, targets) -> dict:
    """Derive both kundalis from their own signs and actual natal lords."""
    house_lords = {(house, frame): chart.get_rashi_lord(rashi)
                   for kind, house, frame, rashi in targets if kind == 'house'}
    active = {}
    for level, planet in (('md', md), ('ad', ad), ('pd', pd)):
        graha = chart.graha(planet)
        aspected = _aspected_rashis(planet, graha.rashi.type)
        relationships = _natal_relationships(graha)
        for kind, house, frame, rashi in targets:
            lord = house_lords[(house, frame)].type
            reasons = set()
            if lord is planet:
                reasons.add('lordship')
            if kind == 'house':
                if graha.rashi.type == rashi:
                    reasons.add('occupancy')
                if rashi in aspected:
                    reasons.add('aspect')
                reasons.update(f'house_lord_{reason}' for reason in relationships.get(lord, ()))
            else:
                reasons.update(relationships.get(lord, ()))
            if reasons:
                evidence = active.setdefault(kind, {}).setdefault(house, {}).setdefault(
                    frame, {'lord': lord.value, 'dasha': {}})
                evidence['dasha'][level] = {'planet': planet.value, 'reasons': sorted(reasons)}
    return {kind: {house: frames for house, frames in sorted(houses.items(), key=lambda item: int(item[0]))}
            for kind, houses in active.items()}


def _karaka_house_links(chart: Chart, house: BhavaNumber, frame: str, planet: GrahaId) -> dict:
    reference = chart.lagna.rashi.type if frame == 'from_lagna' else chart.graha(GrahaId.MOON).rashi.type
    rashi = RashiId((int(reference) + int(house) - 2) % 12 + 1)
    graha, lord = chart.graha(planet), chart.get_rashi_lord(rashi)
    house_reasons = []
    if graha.rashi.type == rashi:
        house_reasons.append('occupancy')
    if rashi in _aspected_rashis(planet, graha.rashi.type):
        house_reasons.append('aspect')
    if lord.type is planet:
        house_reasons.append('lordship')
    links = {'house': house_reasons} if house_reasons else {}
    if reasons := _natal_relationships(graha).get(lord.type):
        links['house_lord'] = {'planet': lord.type.value, 'reasons': sorted(reasons)}
    return links


def _select_karakas(chart, configured, dasha, planet_evidence) -> dict:
    selected = {}
    for number, planets in configured.items():
        house = str(int(number))
        for frame in ('from_lagna', 'from_moon'):
            if not any(frame in dasha.get(kind, {}).get(house, {}) for kind in ('house', 'house_lord')):
                continue
            for planet in planets:
                name = planet.value
                natal = _karaka_house_links(chart, number, frame, planet)
                running = any('dasha_lord' in cause['reasons'] for cause in planet_evidence.get(name, {}).values())
                if not natal and not running:
                    continue
                evidence = {**({'natal': natal} if natal else {}),
                            **({'dasha': planet_evidence[name]} if name in planet_evidence else {})}
                selected.setdefault(house, {}).setdefault(frame, {})[name] = evidence
    return selected


def _karaka_activation(chart: Chart, md: GrahaId, ad: GrahaId, pd: GrahaId,
                       dasha: dict, bhava_karaka: dict, karya_karaka: dict) -> dict:
    """Gate bhava karakas by house; keep karya candidates independent of houses."""
    configured = {planet for planets in bhava_karaka.values() for planet in planets}
    configured.update(planet for planets in karya_karaka.values() for planet in planets)
    if not configured:
        return {}
    evidence = {}
    for level, source in (('md', md), ('ad', ad), ('pd', pd)):
        if source in configured:
            evidence.setdefault(source.value, {})[level] = {'planet': source.value, 'reasons': ['dasha_lord']}
        for planet, reasons in _natal_relationships(chart.graha(source)).items():
            # A running planet is not its own aspect or sambandha target.
            if planet in configured and planet is not source:
                evidence.setdefault(planet.value, {})[level] = {'planet': source.value, 'reasons': sorted(reasons)}
    bhava = _select_karakas(chart, bhava_karaka, dasha, evidence)
    covered = {planet for frames in bhava.values() for planets in frames.values() for planet in planets}
    # Empty evidence is a candidate for transit-only karya activation, checked per interval.
    karya = {name: selected for name, planets in karya_karaka.items()
             if (selected := {planet.value: {'dasha': evidence[planet.value]} if planet.value in evidence else {}
                              for planet in planets if planet.value not in covered})}
    return {**({'bhava_karaka': bhava} if bhava else {}), **({'karya_karaka': karya} if karya else {})}


def _karaka_transit_activations(chart: Chart, planets: set[GrahaId],
                                source: GrahaId, rashi: RashiId) -> list[tuple]:
    aspected = _aspected_rashis(source, rashi)
    effects = []
    for planet in planets:
        target = chart.graha(planet).rashi.type
        if target == rashi:
            effects.append((planet.value, 'conjunct_by', source.value))
        if target in aspected and not _node_pair(source, planet):
            effects.append((planet.value, 'aspect_by', source.value))
    return effects


def _evidence_count(evidence: dict) -> int:
    natal = evidence.get('natal', {})
    return (len(natal.get('house', [])) + len(natal.get('house_lord', {}).get('reasons', []))
            + sum(len(cause['reasons']) for cause in evidence.get('dasha', {}).values())
            + sum(len(planets) for planets in evidence.get('transit', {}).values()))


def _aggregate_karakas(karakas: dict, transits: list[tuple]) -> tuple[dict, dict]:
    by_planet = {}
    for target, effect, source in transits:
        by_planet.setdefault(target, {}).setdefault(effect, set()).add(source)
    counts, seen, covered = {}, set(), set()

    def aggregate(houses):
        result = {}
        for house, frames in sorted(houses.items(), key=lambda item: int(item[0])):
            for frame, planets in frames.items():
                for planet, natal in sorted(planets.items()):
                    evidence = dict(natal)
                    if planet in by_planet:
                        evidence['transit'] = {effect: sorted(sources) for effect, sources in by_planet[planet].items()}
                    result.setdefault(f'H{house}', {}).setdefault(frame, {})[planet] = evidence
                    covered.add(planet)
                    key = (house, frame, planet)
                    if key not in seen:
                        counts[house] = counts.get(house, 0) + _evidence_count(evidence)
                        seen.add(key)
        return result

    result = {}
    if bhava := karakas.get('bhava_karaka'):
        result['bhava_karaka'] = aggregate(bhava)
    if karya := karakas.get('karya_karaka'):
        works = {}
        for name, planets in sorted(karya.items()):
            active = {}
            for planet, natal in sorted(planets.items()):
                if planet in covered:
                    continue
                evidence = dict(natal)
                if planet in by_planet:
                    evidence['transit'] = {effect: sorted(sources) for effect, sources in by_planet[planet].items()}
                if evidence:
                    active[planet] = evidence
            if active:
                works[name] = active
        if works:
            result['karya_karaka'] = works
    return result, counts


def _aggregate_activation(dasha: dict, transits: list[tuple], *,
                          karakas: dict | None = None, karaka_transits: list[tuple] = ()) -> dict:
    """Keep dasha-only evidence and attach transit confirmation only to active targets."""
    result = {kind: {house: {frame: dict(evidence) for frame, evidence in frames.items()}
                     for house, frames in houses.items()} for kind, houses in dasha.items()}
    for kind, house, frame, effect, planet in transits:
        evidence = result.get(kind, {}).get(house, {}).get(frame)
        if evidence is not None:
            evidence.setdefault('transit', {}).setdefault(effect, []).append(planet)
    counts = {}
    for kind, houses in result.items():
        for house, frames in houses.items():
            details = counts.setdefault(house, {'house': 0, 'lord': 0, 'karaka': 0})
            for evidence in frames.values():
                for effect, planets in evidence.get('transit', {}).items():
                    evidence['transit'][effect] = sorted(set(planets))
                # Count distinct recorded mechanisms, including both kundalis.
                details['house' if kind == 'house' else 'lord'] += _evidence_count(evidence)
    karaka_sections, karaka_counts = _aggregate_karakas(karakas or {}, karaka_transits)
    for house, count in karaka_counts.items():
        counts[house]['karaka'] = count
    ranked = sorted(counts, key=lambda house: (-sum(counts[house].values()), int(house)))
    return {
        'natal_houses': [{f'H{house}': {'times': sum(counts[house].values()), 'details': counts[house]}}
                         for house in ranked],
        **{kind: {f'H{house}': frames for house, frames in sorted(houses.items(), key=lambda item: int(item[0]))}
           for kind, houses in result.items()},
        'karaka': karaka_sections,
    }


def _merge_transit_periods(chart: Chart, md: GrahaId, ad: GrahaId,
                           periods: list[VimsottariPeriod], spans, *,
                           bhava_karaka: dict | None = None, karya_karaka: dict | None = None,
                           frames=('from_lagna', 'from_moon'), include_analysis: bool = True) -> list[dict]:
    """Sweep sign changes and PD boundaries into consecutive half-open intervals."""
    targets = _natal_targets(chart, frames=frames)
    by_planet = {}
    for row in spans.itertuples(index=False) if spans is not None else ():
        by_planet.setdefault(row.planet_name, []).append(
            (row.start_at.to_pydatetime(), row.end_at.to_pydatetime(), RashiId(row.rashi)))
    bhava_karaka, karya_karaka = bhava_karaka or {}, karya_karaka or {}
    karaka_planets = {planet for planets in bhava_karaka.values() for planet in planets}
    karaka_planets.update(planet for planets in karya_karaka.values() for planet in planets)
    activations, karaka_activations, result = {}, {}, []
    for period in periods:
        dasha = _dasha_activation(chart, md, ad, period.lord, targets)
        karakas = _karaka_activation(chart, md, ad, period.lord, dasha, bhava_karaka, karya_karaka)
        changes = {period.start_date: []}
        for code in _transit_planets(chart, md, ad, period.lord) if spans is not None else ():
            for start, end, rashi in by_planet[code]:
                if start < period.end_date and end > period.start_date:
                    changes.setdefault(max(start, period.start_date), []).append((code, rashi))
        boundaries = sorted({*changes, period.end_date})
        current = {}
        for start, end in zip(boundaries, boundaries[1:]):
            current.update(changes[start])
            transit, karaka_transits = [], []
            for code, rashi in sorted(current.items()):
                key = (code, rashi)
                if key not in activations:
                    activations[key] = _transit_activations(targets, _TRANSIT_PLANETS[code], rashi)
                transit.extend(activations[key])
                if karakas:
                    if key not in karaka_activations:
                        karaka_activations[key] = _karaka_transit_activations(
                            chart, karaka_planets, _TRANSIT_PLANETS[code], rashi)
                    karaka_transits.extend(karaka_activations[key])
            activation = _aggregate_activation(dasha, transit, karakas=karakas, karaka_transits=karaka_transits)
            event = {'start_date': start.isoformat(), 'end_date': end.isoformat(),
                           'md': md.value, 'ad': ad.value, 'pd': period.lord.value,
                           'natal_houses': activation.pop('natal_houses')}
            if include_analysis:
                event['activation'] = {'house': activation.get('house', {}),
                                          'house_lord': activation.get('house_lord', {}),
                                          'karaka': activation['karaka']}
            result.append(event)
    return result


def _format_activation_events(events: list[dict], detail_level: str) -> list[dict]:
    if detail_level == 'summary':
        for event in events:
            event.pop('activation', None)
            event['natal_houses'] = [
                {house: {'times': score['times']}} for entry in event['natal_houses'][:3]
                for house, score in entry.items()
            ]
    return events


class Vimsottari:
    """Fast Moon-based dasha calculation and dasha-window transit JSON."""

    # Public API: initialize from the natal Moon longitude (or Moon Graha) and birth datetime.
    def __init__(self, moon_longitude: float | Graha, birth_datetime: datetime):
        if isinstance(moon_longitude, Graha) and moon_longitude.type is not GrahaId.MOON:
            raise ValueError('Vimshottari requires the natal Moon')
        longitude = moon_longitude.decimal_degrees if isinstance(moon_longitude, Graha) else moon_longitude
        if not isfinite(longitude) or not 0 <= longitude < 360:
            raise ValueError('Moon longitude must be finite and in [0, 360)')
        if birth_datetime.utcoffset() is None:
            raise ValueError('Birth datetime must include a timezone')
        self.birth_datetime = birth_datetime.astimezone(timezone.utc)
        nakshatra_position = longitude * 27 / 360
        self.nakshatra = NakshatraId(int(nakshatra_position) + 1)
        self.first_lord = self.nakshatra.lord
        self._first = _VIMSOTTARI_INDEX[self.first_lord]
        self._cycle_us = round(120 * VIMSOTTARI_YEAR_DAYS * 86400 * 1_000_000)
        elapsed = (nakshatra_position % 1) * VIMSOTTARI_YEARS[self._first]
        self.start_date = self.birth_datetime - timedelta(days=elapsed * VIMSOTTARI_YEAR_DAYS)

    @property
    def end_date(self) -> datetime:
        return self.start_date + self._cycle_us * _MICROSECOND

    # Public API: active MD through Prana at a date (defaults to now and all five levels).
    # Used by POST /api/v1/astrology/horoscope/vimshottari for current-period queries.
    def at(self, on_date: date | datetime | None = None, *, levels: int = 5) -> list[VimsottariPeriod]:
        """At most five direct cumulative-duration lookups, without sibling scans."""
        if not 1 <= levels <= 5:
            raise ValueError('levels must be between 1 and 5')
        when = _instant(on_date) if on_date is not None else datetime.now(timezone.utc)
        if not self.start_date <= when < self.end_date:
            raise ValueError('Query is outside the 120-year Vimshottari cycle')
        start, duration_us, first = self.start_date, self._cycle_us, self._first
        active = []
        for depth in range(levels):
            elapsed_us = (when - start) // _MICROSECOND
            threshold = ((elapsed_us + 1) * 120 - 1) // duration_us
            offset = bisect_right(_VIMSOTTARI_CUMULATIVE[first], threshold) - 1
            period = _period(start, duration_us, first, offset, depth)
            active.append(period)
            start, duration_us, first = period.start_date, (period.end_date - period.start_date) // _MICROSECOND, _VIMSOTTARI_INDEX[period.lord]
        return active

    # Public API: nine children of a lord prefix, or one Prana period with all five lords.
    # Used by POST /api/v1/astrology/horoscope/vimshottari for single-level queries.
    def periods(self, md: GrahaId | None = None, ad: GrahaId | None = None,
                pd: GrahaId | None = None, sd: GrahaId | None = None,
                pr: GrahaId | None = None) -> list[VimsottariPeriod]:
        """List nine children, or resolve the final Prana; lords must be contiguous."""
        parents = (md, ad, pd, sd, pr)
        count = sum(lord is not None for lord in parents)
        if any(lord is None for lord in parents[:count]):
            raise ValueError('Supply a contiguous md/ad/pd/sd/pr prefix')
        start, duration_us, first = self.start_date, self._cycle_us, self._first
        for depth, lord in enumerate(parents[:count]):
            lord = GrahaId(lord)
            offset = (_VIMSOTTARI_INDEX[lord] - first) % 9
            parent = _period(start, duration_us, first, offset, depth)
            if depth == len(VIMSOTTARI_LEVELS) - 1:
                return [parent]
            start, duration_us, first = parent.start_date, (parent.end_date - parent.start_date) // _MICROSECOND, _VIMSOTTARI_INDEX[lord]
        return [_period(start, duration_us, first, offset, count) for offset in range(9)]

    # Public convenience API: dispatch to at() without parents, or periods() with parents.
    def __call__(self, md: GrahaId | None = None, ad: GrahaId | None = None,
                 pd: GrahaId | None = None, sd: GrahaId | None = None,
                 pr: GrahaId | None = None,
                 *, on_date: date | datetime | None = None) -> list[VimsottariPeriod]:
        if all(lord is None for lord in (md, ad, pd, sd, pr)):
            return self.at(on_date)
        if on_date is not None:
            raise ValueError('Use either a parent-lord prefix or on_date')
        return self.periods(md, ad, pd, sd, pr)

    # Public domain API: flat active chains across a date window, used by context/timeline callers.
    def window(self, start: date | datetime, end: date | datetime, *, levels: int = 3) -> list[list[VimsottariPeriod]]:
        """Flat active chains covering a window; work scales with returned periods."""
        cursor, stop = max(_instant(start), self.start_date), min(_instant(end), self.end_date)
        if stop < cursor:
            raise ValueError('Dasha window end must follow its start')
        periods = []
        while cursor < stop:
            chain = self.at(cursor, levels=levels)
            periods.append(chain)
            cursor = chain[-1].end_date
        return periods

    def _resolve_period(self, md: GrahaId, ad: GrahaId | None = None, pd: GrahaId | None = None) -> VimsottariPeriod:
        """Resolve one MD, AD, or PD window from its lord prefix."""
        if pd is not None and ad is None:
            raise ValueError('ad is required when pd is provided')
        parents = (md, ad, pd)
        parent_lords = parents[:sum(item is not None for item in parents) - 1]
        candidates = self.periods(*parent_lords)
        target = parents[len(parent_lords)]
        return next(item for item in candidates if item.lord is GrahaId(target))

    # Public API: the complete AD timeline, split at PD and relevant transit boundaries.
    # Used by POST /api/v1/astrology/horoscope/vimshottari/transits and the
    # get_vimshottari_period_with_transits MCP tool via build_vimsottari_transit_context().
    def period_with_transits(self, chart: Chart, md: GrahaId, ad: GrahaId,
                             pd: GrahaId, *,
                             bhava_karaka: dict[BhavaNumber, list[GrahaId]] | None = None,
                             karya_karaka: dict[str, list[GrahaId]] | None = None,
                             include_transit: bool = True, kundali: str = 'both',
                             detail_level: str = 'detailed') -> list[dict]:
        """Resolve an MD/AD/PD path, then merge all PDs within its AD with transits."""
        from infrastructure.transit_dataframe import filter_transit_signs

        md, ad, pd = GrahaId(md), GrahaId(ad), GrahaId(pd)
        frames = _kundalis(kundali)
        if detail_level not in ('detailed', 'summary'):
            raise ValueError('detail_level must be detailed or summary')
        self._resolve_period(md, ad, pd)
        periods = self.periods(md, ad)
        spans = None
        if include_transit:
            planets = sorted({code for period in periods
                              for code in _transit_planets(chart, md, ad, period.lord)})
            spans = filter_transit_signs(planets, periods[0].start_date, periods[-1].end_date)
        events = _merge_transit_periods(chart, md, ad, periods, spans,
                                       bhava_karaka=bhava_karaka, karya_karaka=karya_karaka, frames=frames,
                                       include_analysis=detail_level == 'detailed')
        return _format_activation_events(events, detail_level)

    # Public query API: date-window evidence for retrospective and prospective questions.
    def query(self, chart: Chart, start: date | datetime, end: date | datetime, *,
              houses: list[BhavaNumber] | None = None, selection: str = 'timeline',
              include_transit: bool = True, kundali: str = 'both',
              detail_level: str = 'summary', bhava_karaka: dict | None = None,
              karya_karaka: dict | None = None) -> list[dict]:
        """Return clipped intervals or all tied maxima for each requested house.

        Dates are UTC half-open bounds. House selection precedes top-three summary
        projection, so a requested house is never lost to another house's rank.
        """
        from infrastructure.transit_dataframe import filter_transit_signs

        start, end = _instant(start), _instant(end)
        if end <= start or start < self.start_date or end > self.end_date:
            raise ValueError('Query requires an increasing range within the dasha lifespan')
        if selection not in ('timeline', 'maximum'):
            raise ValueError('selection must be timeline or maximum')
        if detail_level not in ('detailed', 'summary'):
            raise ValueError('detail_level must be detailed or summary')
        frames = _kundalis(kundali)
        selected = {f'H{int(BhavaNumber(house))}' for house in houses or []}
        events = []
        for md_period, ad_period in self.window(start, end, levels=2):
            md, ad = md_period.lord, ad_period.lord
            periods = [replace(period, start_date=max(start, period.start_date),
                               end_date=min(end, period.end_date))
                       for period in self.periods(md, ad)
                       if period.start_date < end and period.end_date > start]
            spans = None
            if include_transit:
                planets = sorted({code for period in periods
                                  for code in _transit_planets(chart, md, ad, period.lord)})
                spans = filter_transit_signs(planets, periods[0].start_date, periods[-1].end_date)
            events.extend(_merge_transit_periods(
                chart, md, ad, periods, spans, frames=frames,
                bhava_karaka=bhava_karaka, karya_karaka=karya_karaka,
                include_analysis=detail_level == 'detailed'))
        if selected:
            for event in events:
                event['natal_houses'] = [entry for entry in event['natal_houses'] if next(iter(entry)) in selected]
                activation = event.get('activation')
                if activation is None:
                    continue
                for kind in ('house', 'house_lord'):
                    activation[kind] = {house: value for house, value in activation[kind].items() if house in selected}
                if 'bhava_karaka' in activation['karaka']:
                    activation['karaka']['bhava_karaka'] = {
                        house: value for house, value in activation['karaka']['bhava_karaka'].items() if house in selected}
        if selection == 'maximum':
            maxima = {}
            for event in events:
                for entry in event['natal_houses']:
                    for house, score in entry.items():
                        maxima[house] = max(maxima.get(house, 0), score['times'])
            winners = []
            for event in events:
                matched = [house for entry in event['natal_houses'] for house, score in entry.items()
                           if score['times'] == maxima[house]]
                if matched:
                    event['maximum_for'] = sorted(matched, key=lambda house: int(house[1:]))
                    winners.append(event)
            events = winners
        return _format_activation_events(events, detail_level)
