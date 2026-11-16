"""Event timeline: Vimshottari dasha changes and planet rashi transits in one sequence.

Design
------
::

    TimeRange                 start/end of any event (half-open [start, end))
    TimelineEvent (Protocol)  anything with a ``time_range`` and ``get_details()``
    |-- DashaEvent            one Mahadasha/Antardasha span
    `-- TransitEvent          one planet's stay in a rashi, from its ingress
    EventTimeline             ordered TimelineEvents + a cursor (get_next/peek/reset)

``EventTimeline`` knows only the ``TimelineEvent`` protocol: it orders,
walks, and queries events without knowing about dashas or transits. Each
kind of event is built by its own function (``dasha_events`` /
``transit_events``), so a new kind only needs to carry a ``time_range`` and
``get_details()``::

    timeline = EventTimeline([*dasha_events(vimsottari, start, end),
                              *transit_events(planets, start, end)])
    while timeline.has_next():
        event = timeline.get_next()          # a DashaEvent or a TransitEvent
        print(event.get_details())

Rules
-----
* Dasha: Mahadasha and Antardasha only. Each AD overlapping the window is
  one event, clipped to the window. ``changed`` is MAHADASHA when a new MD
  begins with it, ANTARDASHA when only the AD changes, and None for the AD
  already running when the window opens.
* Transit: ``transit_type == 'rashi'`` rows of the planets file only; the
  Moon is never used. Each ingress is one event lasting until the planet's
  next ingress, clipped to the window.
* Change types reuse existing enums (vimsottari.VimsottariLevel,
  chart.PadaTransitKind) rather than new strings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Iterator, Protocol, TypeVar, runtime_checkable

import pandas as pd

try:
    from domain.core.chart import GrahaId, PadaTransitKind, RashiId
    from domain.core.transit import TRANSIT_PLANET_CODES
    from domain.core.vimsottari import Vimsottari, VimsottariLevel
except ImportError:  # Flat module layout (tests, standalone tooling)
    from chart import GrahaId, PadaTransitKind, RashiId
    from transit import TRANSIT_PLANET_CODES
    from vimsottari import Vimsottari, VimsottariLevel

from transit_pada_query import coverage, rashi_transits


def _utc(moment: date | datetime) -> datetime:
    """Timezone-aware UTC datetime; naive datetimes and dates are read as UTC."""
    if isinstance(moment, pd.Timestamp):
        moment = moment.to_pydatetime()
    if not isinstance(moment, datetime):
        return datetime(moment.year, moment.month, moment.day, tzinfo=timezone.utc)
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


# =============================================================================
# Time range and the event protocol
# =============================================================================

@dataclass(frozen=True)
class TimeRange:
    """Half-open span [start, end) in UTC.

    ``starts_before`` / ``ends_after`` mark a span clipped to a query window:
    the real period began earlier or runs on beyond it.
    """
    start: datetime
    end: datetime
    starts_before: bool = False
    ends_after: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'start', _utc(self.start))
        object.__setattr__(self, 'end', _utc(self.end))
        if self.end < self.start:
            raise ValueError(f'TimeRange end {self.end} precedes its start {self.start}')

    @property
    def duration(self):
        return self.end - self.start

    def contains(self, moment: date | datetime) -> bool:
        return self.start <= _utc(moment) < self.end

    def overlaps(self, other: TimeRange) -> bool:
        return self.start < other.end and other.start < self.end

    def clip(self, window: TimeRange) -> TimeRange:
        """This span cut to ``window``, flagging the sides that were cut."""
        return TimeRange(max(self.start, window.start), min(self.end, window.end),
                         starts_before=self.starts_before or self.start < window.start,
                         ends_after=self.ends_after or self.end > window.end)

    def __str__(self) -> str:
        return f'{self.start:%d %b %Y %H:%M:%S} -> {self.end:%d %b %Y %H:%M:%S}'


@runtime_checkable
class TimelineEvent(Protocol):
    """Anything an EventTimeline can hold: a span plus a description of itself."""
    time_range: TimeRange

    def get_details(self) -> dict:
        """Flat, serialisable description (also the row in EventTimeline.to_frame)."""
        ...


# =============================================================================
# Events
# =============================================================================

@dataclass(frozen=True)
class DashaEvent:
    """One Antardasha span within its Mahadasha."""
    time_range: TimeRange
    md: GrahaId
    ad: GrahaId
    changed: VimsottariLevel | None = None       # None: already running when the window opens

    def get_details(self) -> dict:
        return {'event': 'dasha', 'start': self.time_range.start, 'end': self.time_range.end,
                'changed': self.changed.value if self.changed is not None else None,
                'md': self.md.value, 'ad': self.ad.value,
                'starts_before': self.time_range.starts_before, 'ends_after': self.time_range.ends_after}

    def __str__(self) -> str:
        what = self.changed.value if self.changed is not None else 'RUNNING'
        return f'{self.time_range}  DASHA    {what:<11}  MD {self.md.value} / AD {self.ad.value}'


@dataclass(frozen=True)
class TransitEvent:
    """``planet`` in ``to_rashi`` from its ingress until its next rashi ingress."""
    time_range: TimeRange
    planet: GrahaId
    from_rashi: RashiId
    to_rashi: RashiId
    retrograde: bool = False

    @property
    def changed(self) -> PadaTransitKind:
        return PadaTransitKind.RASHI

    def get_details(self) -> dict:
        return {'event': 'transit', 'start': self.time_range.start, 'end': self.time_range.end,
                'changed': self.changed.value, 'planet': self.planet.value,
                'from_rashi': self.from_rashi.name.title(), 'to_rashi': self.to_rashi.name.title(),
                'retrograde': self.retrograde,
                'starts_before': self.time_range.starts_before, 'ends_after': self.time_range.ends_after}

    def __str__(self) -> str:
        motion = ' (retrograde)' if self.retrograde else ''
        return (f'{self.time_range}  TRANSIT  {self.planet.value:<7} {self.from_rashi.name.title()} -> '
                f'{self.to_rashi.name.title()}{motion}')


# =============================================================================
# Timeline
# =============================================================================

E = TypeVar('E')


@dataclass
class EventTimeline:
    """Events ordered by start, walked with a cursor.

    Events sharing a start keep the order they were given in (the sort is
    stable), so callers decide tie order -- e.g. dasha before transits.
    ``__iter__`` walks every event without moving the cursor.
    """
    events: list[TimelineEvent] = field(default_factory=list)
    cursor: int = 0

    def __post_init__(self):
        for event in self.events:
            if not isinstance(event, TimelineEvent):
                raise TypeError(f'{event!r} is not a TimelineEvent (needs time_range and get_details)')
        self.events = sorted(self.events, key=lambda event: event.time_range.start)

    # --- cursor ----------------------------------------------------------------
    def has_next(self) -> bool:
        return self.cursor < len(self.events)

    def get_next(self) -> TimelineEvent | None:
        """The event at the cursor (then advance), or None once exhausted."""
        if not self.has_next():
            return None
        event = self.events[self.cursor]
        self.cursor += 1
        return event

    def peek(self) -> TimelineEvent | None:
        return self.events[self.cursor] if self.has_next() else None

    def reset(self) -> None:
        self.cursor = 0

    # --- queries ---------------------------------------------------------------
    def add(self, events: Iterable[TimelineEvent]) -> None:
        """Merge more events in. Events already returned stay consumed; added
        events that sort after the last returned one will still be walked."""
        events = list(events)
        for event in events:
            if not isinstance(event, TimelineEvent):
                raise TypeError(f'{event!r} is not a TimelineEvent (needs time_range and get_details)')
        last = self.events[self.cursor - 1] if self.cursor else None
        self.events = sorted([*self.events, *events], key=lambda event: event.time_range.start)
        self.cursor = (next(i for i, event in enumerate(self.events) if event is last) + 1
                       if last is not None else 0)

    def of_type(self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]

    def active_at(self, moment: date | datetime, kind: type[E] | None = None) -> list[E]:
        """Events whose range contains ``moment``, optionally of one kind."""
        return [event for event in self.events if event.time_range.contains(moment)
                and (kind is None or isinstance(event, kind))]

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([event.get_details() for event in self.events])

    def __iter__(self) -> Iterator[TimelineEvent]:
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)


# =============================================================================
# Event builders (the only dasha- / transit-aware code)
# =============================================================================

def dasha_events(vimsottari: Vimsottari, start: date | datetime, end: date | datetime) -> list[DashaEvent]:
    """MD/AD spans overlapping [start, end), each clipped to the window."""
    window = TimeRange(_utc(start), _utc(end))
    if window.end <= window.start:
        raise ValueError('Dasha window end must follow its start')
    events = []
    for md, ad in vimsottari.window(window.start, window.end, levels=2):
        span = TimeRange(ad.start_date, ad.end_date)
        if span.start < window.start:
            changed = None                                     # already running at the window start
        elif ad.start_date == md.start_date:
            changed = VimsottariLevel.MAHADASHA                # a new MD begins (with its own AD)
        else:
            changed = VimsottariLevel.ANTARDASHA
        events.append(DashaEvent(span.clip(window), md.lord, ad.lord, changed))
    return events


def transit_events(planets: pd.DataFrame, start: date | datetime, end: date | datetime) -> list[TransitEvent]:
    """Rashi ingresses (never the Moon) in [start, end), in file order at equal instants.

    ``planets`` is a load_planet_transits() frame that must cover the window.
    """
    window = TimeRange(_utc(start), _utc(end))
    if window.end <= window.start:
        raise ValueError('Transit window end must follow its start')
    first, last = coverage(planets)
    if window.start < first or (last is not None and window.end > last):
        raise ValueError(f'Window [{window.start}, {window.end}) is outside the transit file '
                         f'coverage [{first}, {last})')
    return [TransitEvent(TimeRange(row.start_at, row.end_at, ends_after=bool(row.open_ended)).clip(window),
                         TRANSIT_PLANET_CODES[row.planet], RashiId(row.from_rashi), RashiId(row.to_rashi),
                         bool(row.retrograde))
            for row in rashi_transits(planets, window.start, window.end).itertuples(index=False)]


def build_event_timeline(vimsottari: Vimsottari, planets: pd.DataFrame,
                         start: date | datetime, end: date | datetime) -> EventTimeline:
    """Dasha events then transit events for [start, end), merged into one timeline.

    Dasha events are listed first so, at an equal start, a dasha change
    precedes the transits of that instant.
    """
    transits = transit_events(planets, start, end)      # validates coverage first
    return EventTimeline([*dasha_events(vimsottari, start, end), *transits])
