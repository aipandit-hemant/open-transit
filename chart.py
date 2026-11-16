"""Chart entities, placement indexes, and aggregate context contracts.

No runtime dependency on Horoscope or yoga evaluation. Yoga association types
are imported only for static annotations; the aggregate supplies their indexes.
"""
from __future__ import annotations

from enum import Enum, IntEnum
from typing import Dict, List, Mapping, Optional, Protocol, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from domain.core.yogas import Yoga, HoroscopeYogas
    from domain.core.vimsottari import Vimsottari, VimsottariDasha


class GrahaId(Enum):
    """Full English planet names; Sanskrit member aliases preserve callers."""
    SUN = "Sun"
    MOON = "Moon"
    MARS = "Mars"
    MERCURY = "Mercury"
    JUPITER = "Jupiter"
    VENUS = "Venus"
    SATURN = "Saturn"
    RAHU = "Rahu"
    KETU = "Ketu"

    SURYA = SUN
    CHANDRA = MOON
    MANGAL = MARS
    BUDHA = MERCURY
    GURU = JUPITER
    SHUKRA = VENUS
    SHANI = SATURN

    # Three-letter codes (transit CSVs, YAML config); SUN is already a member.
    MON = MOON
    MAR = MARS
    MER = MERCURY
    JUP = JUPITER
    VEN = VENUS
    SAT = SATURN
    RAH = RAHU
    KET = KETU

    @classmethod
    def _missing_(cls, value):
        """Read legacy serialized enum values while writing English names."""
        return cls.__members__.get(value) if isinstance(value, str) else None


class NaturalRelation(str, Enum):
    FRIEND = "Mitra"
    NEUTRAL = "Sama"
    ENEMY = "Shatru"

    def __str__(self) -> str:
        return self.value


class RashiId(IntEnum):
    """Zodiac sign numbers with English names and legacy Sanskrit aliases."""
    ARIES = 1
    TAURUS = 2
    GEMINI = 3
    CANCER = 4
    LEO = 5
    VIRGO = 6
    LIBRA = 7
    SCORPIO = 8
    SAGITTARIUS = 9
    CAPRICORN = 10
    AQUARIUS = 11
    PISCES = 12

    MESHA = ARIES
    VRISHABHA = TAURUS
    MITHUNA = GEMINI
    KARKA = CANCER
    SIMHA = LEO
    KANYA = VIRGO
    TULA = LIBRA
    VRISCHIKA = SCORPIO
    DHANU = SAGITTARIUS
    MAKARA = CAPRICORN
    KUMBHA = AQUARIUS
    MEENA = PISCES


class BhavaNumber(IntEnum):
    H1 = 1
    H2 = 2
    H3 = 3
    H4 = 4
    H5 = 5
    H6 = 6
    H7 = 7
    H8 = 8
    H9 = 9
    H10 = 10
    H11 = 11
    H12 = 12


class HouseLord(Enum):
    """A chart-relative house lord: H8L resolves to the current chart's eighth lord."""
    H1L = 1
    H2L = 2
    H3L = 3
    H4L = 4
    H5L = 5
    H6L = 6
    H7L = 7
    H8L = 8
    H9L = 9
    H10L = 10
    H11L = 11
    H12L = 12


# H2 means the second bhava; H2L means its ruling planet, wherever it is placed.
H1, H2, H3, H4, H5, H6, H7, H8, H9, H10, H11, H12 = BhavaNumber
H1L, H2L, H3L, H4L, H5L, H6L, H7L, H8L, H9L, H10L, H11L, H12L = HouseLord


class BhavaGroup(Enum):
    """Inclusive house groups, counted from Lagna or a specified reference.

    Trikona includes the first house, which is both a kendra and a trikona.
    """
    KENDRA = (1, 4, 7, 10)
    TRIKONA = (1, 5, 9)
    DUSTHANA = (6, 8, 12)
    UPACHAYA = (3, 6, 10, 11)
    PANAPHARA = (2, 5, 8, 11)
    APOKLIMA = (3, 6, 9, 12)
    MARAKA = (2, 7)


class Tatva(Enum):
    FIRE = "FIRE"
    EARTH = "EARTH"
    AIR = "AIR"
    WATER = "WATER"


class SambandhaType(Enum):
    EXCHANGE = "EXCHANGE"              # Parivartana
    CONJUNCTION = "CONJUNCTION"        # Yuti
    MUTUAL_ASPECT = "MUTUAL_ASPECT"    # Purna Drishti
    OCCUPIES_AND_ASPECTS_LORD = "OCCUPIES_AND_ASPECTS_LORD"
    OCCUPIES_AND_RECEIVES_LORD_ASPECT = "OCCUPIES_AND_RECEIVES_LORD_ASPECT"
    DISPOSITOR = "DISPOSITOR"          # Rahu and Ketu only


class DignityType(Enum):
    EXALTED = "EXALTED"
    VARGOTTAMA = "VARGOTTAMA"
    MOOLATRIKONA = "MOOLATRIKONA"
    SWARASHI = "SWARASHI"
    ADHI_MITRA = "ADHI_MITRA"
    MITRA = "MITRA"
    SAMA = "SAMA"
    SHATRU = "SHATRU"
    ADHI_SHATRU = "ADHI_SHATRU"
    DEBILITATED = "DEBILITATED"


class VargaType(Enum):
    D1_RASHI = "D1_RASHI"
    D2_HORA = "D2_HORA"
    D3_DREKKANA = "D3_DREKKANA"
    D4_CHATURTHAMSHA = "D4_CHATURTHAMSHA"
    D7_SAPTAMSHA = "D7_SAPTAMSHA"
    D9_NAVAMSHA = "D9_NAVAMSHA"
    D10_DASHAMSHA = "D10_DASHAMSHA"
    D12_DWADASHAMSHA = "D12_DWADASHAMSHA"
    D16_SHODASHAMSHA = "D16_SHODASHAMSHA"
    D20_VIMSHAMSHA = "D20_VIMSHAMSHA"
    D24_CHATURVIMSHAMSHA = "D24_CHATURVIMSHAMSHA"
    D27_BHAMSHA = "D27_BHAMSHA"
    D30_TRIMSHAMSHA = "D30_TRIMSHAMSHA"
    D40_KHAVEDAMSHA = "D40_KHAVEDAMSHA"
    D45_AKSHAVEDAMSHA = "D45_AKSHAVEDAMSHA"
    D60_SHASHTIAMSHA = "D60_SHASHTIAMSHA"

    @property
    def factor(self) -> int:
        return int(self.value.split("_")[0][1:])

    @classmethod
    def from_factor(cls, factor: int) -> VargaType:
        for varga in cls:
            if varga.factor == factor:
                return varga
        raise ValueError(f"Unsupported divisional chart: D{factor}")


# =====================================================================
# 2. RESTRICTED QUERY INTERFACE (LEAST ACCESSIBILITY PRINCIPLE)
# =====================================================================

def exclude_grahas(grahas: list[Graha], exclude: list[GrahaId] | None = None) -> list[Graha]:
    """Skip the filter entirely when no exclusions were supplied."""
    if exclude is None:
        return grahas
    return [graha for graha in grahas if graha.type not in exclude]


def graha_potency_factors(participating_grahas: Sequence[Graha]) -> tuple[list[str], list[str]]:
    """Describe participating planets' dignity and combustion strengths or weaknesses."""
    strengths, weaknesses, seen = [], [], set()
    for graha in participating_grahas:
        if graha.type in seen:
            continue
        seen.add(graha.type)
        if graha.dignity.is_own_or_exalted:
            strengths.append(f'{graha.name} is {graha.dignity.type.value}.')
        if graha.dignity.is_vargottama:
            strengths.append(f'{graha.name} is vargottama.')
        if graha.dignity.is_debilitated:
            weaknesses.append(f'{graha.name} is debilitated; formation remains present.')
        if graha.is_combust:
            weaknesses.append(f'{graha.name} is combust; formation remains present.')
    return strengths, weaknesses


class IChartQueryContext(Protocol):
    """Chart lookups return lists; results can be changed without mutating chart indexes."""
    def get_occupants_for_bhava(self, bhava_num: BhavaNumber, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def get_aspecting_planets_for_bhava(self, bhava_num: BhavaNumber, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def get_aspecting_planets_for_graha(self, target: GrahaId, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def get_planets_aspected_by_graha(self, source: GrahaId, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def get_bhavas_aspected_by_graha(self, source: GrahaId) -> list[Bhava]: ...
    def get_occupants_for_nakshatra(self, nakshatra_index: int, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def get_sambandha_planets_for_graha(self, source: GrahaId, type: SambandhaType, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def get_bhavas_ruled_by_graha(self, graha_type: GrahaId) -> list[Bhava]: ...
    def get_rashi_lord(self, rashi_type: RashiId) -> Graha: ...
    def get_graha(self, graha_type: GrahaId) -> Graha: ...
    def get_bhava(self, bhava_num: BhavaNumber) -> Bhava: ...
    def get_rashi(self, rashi_type: RashiId) -> Rashi: ...
    def get_graha_in_varga(self, graha_type: GrahaId, varga_type: VargaType) -> Graha: ...
    def get_yogas_for_graha(self, graha_type: GrahaId) -> list[Yoga]: ...
    def get_all_detected_yogas(self) -> list[Yoga]: ...
    def get_yoga_activation_periods(self, grahas: Sequence[GrahaId]) -> list[VimsottariDasha]: ...
    def get_shadbala_for_graha(self, graha_type: GrahaId) -> Optional[GrahaAstabala]: ...
    def classical_grahas(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def natural_benefics(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def natural_malefics(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def functional_benefics(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...
    def functional_malefics(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]: ...


# =====================================================================
# 5. DOMAIN VALUE OBJECTS & COMPOSED STATE CONTAINERS
# =====================================================================

class GrahaAvastha:
    def __init__(self, deeptadi: str, baladi: str = "YUVA", jagratadi: str = "JAGRAT"):
        self._deeptadi = deeptadi
        self._baladi = baladi
        self._jagratadi = jagratadi

    @property
    def deeptadi(self) -> str: return self._deeptadi
    @property
    def baladi(self) -> str: return self._baladi
    @property
    def jagratadi(self) -> str: return self._jagratadi

    def __repr__(self) -> str:
        return f"Avastha({self._deeptadi}/{self._baladi})"


class GrahaDignity:
    def __init__(self, type: DignityType, is_vargottama: bool = False, *,
                 is_swarashi: Optional[bool] = None, is_moolatrikona: Optional[bool] = None):
        self._type = type
        self._is_vargottama = is_vargottama
        self._is_swarashi = type in (DignityType.SWARASHI, DignityType.MOOLATRIKONA) if is_swarashi is None else is_swarashi
        self._is_moolatrikona = type == DignityType.MOOLATRIKONA if is_moolatrikona is None else is_moolatrikona

    @property
    def type(self) -> DignityType: return self._type
    @property
    def is_exalted(self) -> bool: return self._type == DignityType.EXALTED
    @property
    def is_debilitated(self) -> bool: return self._type == DignityType.DEBILITATED
    @property
    def is_swarashi(self) -> bool: return self._is_swarashi
    @property
    def is_moolatrikona(self) -> bool: return self._is_moolatrikona
    @property
    def is_vargottama(self) -> bool: return self._is_vargottama

    @property
    def is_own_or_exalted(self) -> bool:
        """Own sign includes moolatrikona; retain each dignity's native flag."""
        return self.is_swarashi or self.is_exalted or self.is_moolatrikona

    def __repr__(self) -> str:
        v_str = "/VARGOTTAMA" if self._is_vargottama else ""
        return f"Dignity({self._type.value}{v_str})"


class GrahaAstabala:
    """Shadbala value object; absence is explicit, never a fabricated zero."""
    def __init__(
        self, virupas: Optional[float], *,
        category_scores: Optional[Dict[str, float]] = None,
        category_breakdown: Optional[dict] = None,
        strength_ratio: Optional[float] = None,
        minimum_rupa: Optional[float] = None,
        unavailable_reason: Optional[str] = None,
    ):
        from copy import deepcopy
        from math import isfinite
        if virupas is not None and not isfinite(virupas):
            raise ValueError("Shadbala must be finite")
        self._virupas = virupas
        self._category_scores = dict(category_scores or {})
        self._category_breakdown = deepcopy(category_breakdown or {})
        self._strength_ratio = strength_ratio
        self._minimum_rupa = minimum_rupa
        self._unavailable_reason = (unavailable_reason or "Birth details or a Shadbala calculation were not supplied") if virupas is None else None

    @property
    def virupas(self) -> Optional[float]: return self._virupas
    @property
    def rupas(self) -> Optional[float]:
        return round(self._virupas / 60.0, 2) if self._virupas is not None else None
    @property
    def is_available(self) -> bool: return self._virupas is not None
    @property
    def unavailable_reason(self) -> Optional[str]: return self._unavailable_reason
    @property
    def category_scores(self) -> Dict[str, float]: return dict(self._category_scores)
    @property
    def category_breakdown(self) -> dict:
        from copy import deepcopy
        return deepcopy(self._category_breakdown)
    @property
    def strength_ratio(self) -> Optional[float]: return self._strength_ratio
    @property
    def minimum_rupa(self) -> Optional[float]: return self._minimum_rupa

    def __repr__(self) -> str:
        return f"Astabala({self.rupas} Rupas)" if self.is_available else f"Astabala(Unavailable: {self.unavailable_reason})"


class GrahaSambandha:
    def __init__(self, graha_type: GrahaId, context: IChartQueryContext):
        self._graha_type = graha_type
        self._context = context

    @property
    def exchange(self) -> Sequence[Graha]:
        return self._context.get_sambandha_planets_for_graha(self._graha_type, SambandhaType.EXCHANGE)

    @property
    def conjunction(self) -> Sequence[Graha]:
        return self._context.get_sambandha_planets_for_graha(self._graha_type, SambandhaType.CONJUNCTION)

    @property
    def mutual_aspect(self) -> Sequence[Graha]:
        return self._context.get_sambandha_planets_for_graha(self._graha_type, SambandhaType.MUTUAL_ASPECT)

    @property
    def occupies_and_aspects_lord(self) -> Sequence[Graha]:
        return self.get(SambandhaType.OCCUPIES_AND_ASPECTS_LORD)

    @property
    def occupies_and_receives_lord_aspect(self) -> Sequence[Graha]:
        return self.get(SambandhaType.OCCUPIES_AND_RECEIVES_LORD_ASPECT)

    @property
    def dispositor(self) -> Graha:
        graha = self._context.get_graha(self._graha_type)
        return self._context.get_rashi_lord(graha.rashi.type)

    @property
    def all(self) -> Sequence[Graha]:
        all_planets = set()
        for stype in SambandhaType:
            all_planets.update(self._context.get_sambandha_planets_for_graha(self._graha_type, stype))
        return tuple(sorted(all_planets, key=lambda g: list(GrahaId).index(g.type)))

    def is_associated_with(self, other_graha: Graha) -> bool:
        """Use the chart's existing full sambandha definition."""
        return other_graha in self.all

    def get(self, type: SambandhaType, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return self._context.get_sambandha_planets_for_graha(self._graha_type, type, exclude=exclude)

    def __repr__(self) -> str:
        return f"Sambandha(Dispositor={self.dispositor.type.value})"


# =====================================================================
# 6. CORE ASTROLOGICAL DOMAIN ENTITIES
# =====================================================================

class Rashi:
    def __init__(self, type: RashiId, element: Tatva, context: IChartQueryContext):
        self._type = type
        self._element = element
        self._context = context

    @property
    def type(self) -> RashiId: return self._type
    @property
    def element(self) -> Tatva: return self._element

    @property
    def lord(self) -> Graha:
        return self._context.get_rashi_lord(self._type)

    @property
    def name(self) -> str:
        return rashi_name_from_num(self._type.value)

    @property
    def id(self) -> str:
        return self.name.lower()

    def __repr__(self) -> str:
        return f"Rashi({self.name})"


class NakshatraId(IntEnum):
    """Canonical 1-based nakshatra IDs with display name and Vimshottari lord."""
    nakshatra_name: str
    lord: GrahaId

    def __new__(cls, nakshatra_id: int, nakshatra_name: str, lord: GrahaId):
        member = int.__new__(cls, nakshatra_id)
        member._value_ = nakshatra_id
        member.nakshatra_name = nakshatra_name
        member.lord = lord
        return member

    @property
    def id(self) -> int:
        return self.value

    ASHWINI = (1, 'Ashwini', GrahaId.KETU)
    BHARANI = (2, 'Bharani', GrahaId.VENUS)
    KRITTIKA = (3, 'Krittika', GrahaId.SUN)
    ROHINI = (4, 'Rohini', GrahaId.MOON)
    MRIGASHIRA = (5, 'Mrigashira', GrahaId.MARS)
    ARDRA = (6, 'Ardra', GrahaId.RAHU)
    PUNARVASU = (7, 'Punarvasu', GrahaId.JUPITER)
    PUSHYA = (8, 'Pushya', GrahaId.SATURN)
    ASHLESHA = (9, 'Ashlesha', GrahaId.MERCURY)
    MAGHA = (10, 'Magha', GrahaId.KETU)
    PURVA_PHALGUNI = (11, 'Purva Phalguni', GrahaId.VENUS)
    UTTARA_PHALGUNI = (12, 'Uttara Phalguni', GrahaId.SUN)
    HASTA = (13, 'Hasta', GrahaId.MOON)
    CHITRA = (14, 'Chitra', GrahaId.MARS)
    SWATI = (15, 'Swati', GrahaId.RAHU)
    VISHAKHA = (16, 'Vishakha', GrahaId.JUPITER)
    ANURADHA = (17, 'Anuradha', GrahaId.SATURN)
    JYESHTHA = (18, 'Jyeshtha', GrahaId.MERCURY)
    MULA = (19, 'Mula', GrahaId.KETU)
    PURVA_ASHADHA = (20, 'Purva Ashadha', GrahaId.VENUS)
    UTTARA_ASHADHA = (21, 'Uttara Ashadha', GrahaId.SUN)
    SHRAVANA = (22, 'Shravana', GrahaId.MOON)
    DHANISHTA = (23, 'Dhanishta', GrahaId.MARS)
    SHATABHISHA = (24, 'Shatabhisha', GrahaId.RAHU)
    PURVA_BHADRAPADA = (25, 'Purva Bhadrapada', GrahaId.JUPITER)
    UTTARA_BHADRAPADA = (26, 'Uttara Bhadrapada', GrahaId.SATURN)
    REVATI = (27, 'Revati', GrahaId.MERCURY)


class Nakshatra:
    def __init__(self, index: int, name: str, pada: int, lord_type: GrahaId, context: IChartQueryContext):
        self._id = NakshatraId(index)
        self._index = self._id.value
        self._name = self._id.nakshatra_name
        self._pada = pada
        self._lord_type = self._id.lord
        self._context = context

    @property
    def id(self) -> NakshatraId: return self._id
    @property
    def index(self) -> int: return self._index
    @property
    def name(self) -> str: return self._name
    @property
    def pada(self) -> int: return self._pada

    @property
    def lord(self) -> Graha:
        return self._context.get_graha(self._lord_type)

    def occupants(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return self._context.get_occupants_for_nakshatra(self._index, exclude=exclude)

    def __repr__(self) -> str:
        return f"Nakshatra({self._name}, Pada={self._pada})"


class Bhava:
    def __init__(self, number: BhavaNumber, rashi: Rashi, context: IChartQueryContext):
        self._number = number
        self._rashi = rashi
        self._context = context

    @property
    def number(self) -> BhavaNumber: return self._number
    @property
    def rashi(self) -> Rashi: return self._rashi

    @property
    def lord(self) -> Graha:
        return self._rashi.lord

    def occupants(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return self._context.get_occupants_for_bhava(self._number, exclude=exclude)

    @property
    def aspecting_planets(self) -> Sequence[Graha]:
        return self._context.get_aspecting_planets_for_bhava(self._number)

    def __repr__(self) -> str:
        return f"Bhava(House={self._number.value}, {self._rashi.name})"


class GrahCharitra:
    """Factual graha characteristics; no interpretation or verdict."""

    def __init__(self, graha_type: GrahaId, context: IChartQueryContext):
        self._graha_type = graha_type
        self._context = context

    @property
    def owned_bhavas(self) -> Sequence[Bhava]:
        return self._context.get_bhavas_ruled_by_graha(self._graha_type)


class Graha:
    """
    Planet Entity incorporating position attributes, cross-chart navigation,
    and direct O(1) property access to its Yogas.
    """
    def __init__(
        self,
        graha_type: GrahaId,
        decimal_degrees: float,
        rashi: Rashi,
        bhava: Bhava,
        nakshatra: Nakshatra,
        avastha: GrahaAvastha,
        dignity: GrahaDignity,
        astabala: GrahaAstabala,
        is_retrograde: bool,
        is_combust: bool,
        context: IChartQueryContext
    ):
        self._type = graha_type
        self._decimal_degrees = decimal_degrees % 360.0
        self._rashi = rashi
        self._bhava = bhava
        self._nakshatra = nakshatra
        self._avastha = avastha
        self._dignity = dignity
        self._astabala = astabala
        self._is_retrograde = is_retrograde
        self._is_combust = is_combust
        self._context = context
        self._sambandha = GrahaSambandha(graha_type, context)
        self._charitra = GrahCharitra(graha_type, context)

    @property
    def type(self) -> GrahaId: return self._type
    @property
    def name(self) -> str: return GRAHA_NAMES[self._type]
    @property
    def id(self) -> str: return self.name.lower()
    @property
    def dignity(self) -> GrahaDignity: return self._dignity
    @property
    def astabala(self) -> GrahaAstabala:
        return self._context.get_shadbala_for_graha(self._type) or self._astabala
    @property
    def shadbala(self) -> GrahaAstabala: return self.astabala
    @property
    def sambandha(self) -> GrahaSambandha: return self._sambandha
    @property
    def charitra(self) -> GrahCharitra: return self._charitra

    @property
    def decimal_degrees(self) -> float: return self._decimal_degrees
    @property
    def degree_in_sign(self) -> float: return round(self._decimal_degrees % 30.0, 2)
    @property
    def sign_index(self) -> int: return int(self._decimal_degrees // 30) + 1
    @property
    def rashi(self) -> Rashi: return self._rashi
    @property
    def bhava(self) -> Bhava: return self._bhava
    @property
    def nakshatra(self) -> Nakshatra: return self._nakshatra
    @property
    def avastha(self) -> GrahaAvastha: return self._avastha
    @property
    def is_retrograde(self) -> bool: return self._is_retrograde
    @property
    def is_combust(self) -> bool: return self._is_combust

    def conjunct(self, other: Graha) -> bool:
        """Use this chart's conjunction index; a planet never conjuncts itself."""
        return other in self.sambandha.conjunction

    def ref_house(self, house_no: int) -> Bhava:
        """Return the inclusive nth bhava from this planet in its own chart."""
        if isinstance(house_no, bool) or not isinstance(house_no, int) or not 1 <= house_no <= 12:
            raise ValueError('Relative house must be an integer between 1 and 12')
        return self._context.get_bhava(BhavaNumber(house_rashi(self.bhava.number, house_no)))

    def house(self, reference: Graha | Bhava | BhavaNumber | HouseLord | None = None) -> int:
        """Inclusive house from a planet, bhava or house lord; default is Lagna.

        sun.house(moon) counts from Moon's placement. sun.house(H2) counts
        from the second bhava. sun.house(H8L) counts from the eighth lord's
        placement in Sun's chart, not from the eighth bhava itself.
        """
        if isinstance(reference, HouseLord):
            reference = self._context.get_bhava(BhavaNumber(reference.value)).lord
        if isinstance(reference, Graha):
            reference = reference.bhava
        if isinstance(reference, Bhava):
            reference = reference.number
        if reference is None:
            reference = H1
        if not isinstance(reference, BhavaNumber):
            raise TypeError('Reference must be a planet, bhava, H1–H12 or H1L–H12L')
        return relative_house(reference, self.bhava.number)

    # Short predicates read as sutras: jupiter.kendra(moon), sun.trikona(H2).
    # One reference resolver and the existing relative_house own all arithmetic.
    kendra = lambda self, reference=None: self.house(reference) in BhavaGroup.KENDRA.value
    trikona = lambda self, reference=None: self.house(reference) in BhavaGroup.TRIKONA.value
    dusthana = lambda self, reference=None: self.house(reference) in BhavaGroup.DUSTHANA.value
    dusthan = dusthana
    upachaya = lambda self, reference=None: self.house(reference) in BhavaGroup.UPACHAYA.value
    panaphara = lambda self, reference=None: self.house(reference) in BhavaGroup.PANAPHARA.value
    apoklima = lambda self, reference=None: self.house(reference) in BhavaGroup.APOKLIMA.value
    maraka = lambda self, reference=None: self.house(reference) in BhavaGroup.MARAKA.value

    # --- Yogas Property directly on Graha ---
    @property
    def yogas(self) -> Sequence[Yoga]:
        """O(1) direct access to all detected Yogas involving this planet."""
        return self._context.get_yogas_for_graha(self._type)

    @property
    def owned_bhavas(self) -> Sequence[Bhava]:
        return self._charitra.owned_bhavas

    @property
    def co_occupants(self) -> Sequence[Graha]:
        return [g for g in self._bhava.occupants() if g.type != self._type]

    @property
    def aspecting_planets(self) -> Sequence[Graha]:
        return self._context.get_aspecting_planets_for_graha(self._type)

    @property
    def aspected_planets(self) -> Sequence[Graha]:
        return self._context.get_planets_aspected_by_graha(self._type)

    @property
    def aspected_bhavas(self) -> Sequence[Bhava]:
        return self._context.get_bhavas_aspected_by_graha(self._type)

    # --- CROSS-CHART NAVIGATION ---
    def varga(self, varga_type: VargaType) -> Graha:
        return self._context.get_graha_in_varga(self._type, varga_type)

    @property
    def d1(self) -> Graha: return self.varga(VargaType.D1_RASHI)
    @property
    def d9(self) -> Graha: return self.varga(VargaType.D9_NAVAMSHA)
    @property
    def d10(self) -> Graha: return self.varga(VargaType.D10_DASHAMSHA)

    def __repr__(self) -> str:
        return f"Graha({self._type.value})"


# =====================================================================
# 7. UNIFIED CHART CLASS (WITH PRE-INDEXED YOGA MAP)
# =====================================================================

class IHoroscopeChartContext(Protocol):
    """Services supplied by the owning aggregate, without importing its facade."""
    def varga(self, varga_type: VargaType) -> Chart: ...
    def is_vargottama(self, graha_type: GrahaId) -> bool: ...
    def get_shadbala_for_graha(self, graha_type: GrahaId) -> Optional[GrahaAstabala]: ...
    def get_yoga_activation_periods(self, grahas: Sequence[GrahaId]) -> list[VimsottariDasha]: ...
    def get_chart_yogas(self, chart: Chart) -> HoroscopeYogas: ...
    @property
    def vimsottari(self) -> Vimsottari: ...


class Chart(IChartQueryContext):
    """
    Unified Astrological Chart object.
    Owns placements and relationship indexes; Horoscope coordinates yoga evaluation.
    """
    def __init__(
        self,
        varga_type: VargaType,
        raw_position_inputs: Dict[GrahaId, Tuple[float, RashiId, BhavaNumber, int, str, int, GrahaId, GrahaAvastha, DignityType, Optional[float], bool, bool]],
        house_rashi_map: Dict[BhavaNumber, RashiId],
        horoscope_root: IHoroscopeChartContext,
        *, lagna_longitude: Optional[float] = None,
        bhava_madhya_longitudes: Optional[Sequence[float]] = None,
        dignities: Optional[Dict[GrahaId, GrahaDignity]] = None,
    ):
        self._varga_type = varga_type
        self._horoscope_root = horoscope_root
        self._lagna_longitude = lagna_longitude
        self._bhava_madhya_longitudes = tuple(bhava_madhya_longitudes or ())

        # 1. Instantiate 12 Rashis
        self._rashis: Dict[RashiId, Rashi] = {
            r_type: Rashi(r_type, elem, self) for r_type, elem in RASHI_ELEMENT.items()
        }

        # 2. Instantiate 12 Bhavas
        self._bhavas: Dict[BhavaNumber, Bhava] = {
            b_num: Bhava(b_num, self._rashis[r_type], self) for b_num, r_type in house_rashi_map.items()
        }

        # 3. Instantiate Grahas
        self._grahas: Dict[GrahaId, Graha] = {}
        for g_type, data in raw_position_inputs.items():
            deg, r_type, b_num, nak_idx, nak_name, nak_pada, nak_lord, avastha, dig_type, virupas, is_ret, is_comb = data

            rashi_obj = self._rashis[r_type]
            bhava_obj = self._bhavas[b_num]
            nakshatra_obj = Nakshatra(nak_idx, nak_name, nak_pada, nak_lord, self)
            dignity_obj = (dignities or {}).get(g_type) or GrahaDignity(dig_type, is_vargottama=horoscope_root.is_vargottama(g_type))
            astabala_obj = GrahaAstabala(virupas)

            self._grahas[g_type] = Graha(
                graha_type=g_type,
                decimal_degrees=deg,
                rashi=rashi_obj,
                bhava=bhava_obj,
                nakshatra=nakshatra_obj,
                avastha=avastha,
                dignity=dignity_obj,
                astabala=astabala_obj,
                is_retrograde=is_ret,
                is_combust=is_comb,
                context=self
            )

        # 4. Pre-index relationship matrices
        self._bhava_occupants: Dict[BhavaNumber, List[Graha]] = {b: [] for b in BhavaNumber}
        self._bhava_aspects: Dict[BhavaNumber, List[Graha]] = {b: [] for b in BhavaNumber}
        self._graha_aspected_planets: Dict[GrahaId, List[Graha]] = {g: [] for g in GrahaId}
        self._graha_aspected_bhavas: Dict[GrahaId, List[Bhava]] = {g: [] for g in GrahaId}
        self._nakshatra_occupants: Dict[int, List[Graha]] = {}
        self._sambandha_map: Dict[Tuple[GrahaId, SambandhaType], List[Graha]] = {}

        # O(1) Fast Yoga Lookups
        self._yoga_view: HoroscopeYogas | None = None
        self._yoga_map: Dict[str, Yoga] = {}
        self._graha_yoga_map: Dict[GrahaId, List[Yoga]] = {g: [] for g in GrahaId}

        self._build_relationship_graph()
        self._ruled_bhavas = {
            g: tuple(b for b in self._bhavas.values() if b.lord.type == g)
            for g in GrahaId
        }

    @property
    def varga_type(self) -> VargaType: return self._varga_type

    @property
    def lagna_longitude(self) -> float:
        if self._lagna_longitude is None:
            raise ValueError("Ascendant longitude was not supplied")
        return self._lagna_longitude

    @property
    def bhava_madhya_longitudes(self) -> Sequence[float]:
        if len(self._bhava_madhya_longitudes) != 12:
            raise ValueError("Twelve sidereal bhava cusp longitudes were not supplied")
        return self._bhava_madhya_longitudes

    def get_yoga_activation_periods(self, grahas: Sequence[GrahaId]) -> list[VimsottariDasha]:
        return self._horoscope_root.get_yoga_activation_periods(grahas)

    def get_shadbala_for_graha(self, graha_type: GrahaId) -> Optional[GrahaAstabala]:
        return self._horoscope_root.get_shadbala_for_graha(graha_type)

    def classical_grahas(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return exclude_grahas([graha for graha in self._grahas.values()
                               if graha.type not in (GrahaId.RAHU, GrahaId.KETU)], exclude)

    def natural_benefics(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        sun, moon, mercury = (self._grahas[graha_id] for graha_id in
                              (GrahaId.SUN, GrahaId.MOON, GrahaId.MERCURY))
        benefics = [self._grahas[GrahaId.JUPITER], self._grahas[GrahaId.VENUS]]
        if 0 < (moon.decimal_degrees - sun.decimal_degrees) % 360 <= 180:
            benefics.append(moon)
        malefics = [sun, self._grahas[GrahaId.MARS], self._grahas[GrahaId.SATURN],
                    self._grahas[GrahaId.RAHU], self._grahas[GrahaId.KETU]]
        if moon not in benefics:
            malefics.append(moon)
        if not any(mercury.conjunct(graha) for graha in malefics):
            benefics.append(mercury)
        return exclude_grahas(benefics, exclude)

    def natural_malefics(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        benefics = {graha.type for graha in self.natural_benefics()}
        return exclude_grahas([graha for graha in self._grahas.values()
                               if graha.type not in benefics], exclude)

    def functional_benefics(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        """Lords of H1/H5/H9; mixed house ownership can classify a planet both ways."""
        trikona_houses = {BhavaNumber.H1, BhavaNumber.H5, BhavaNumber.H9}
        return exclude_grahas([graha for graha in self._grahas.values()
                               if any(bhava.number in trikona_houses for bhava in graha.owned_bhavas)], exclude)

    def functional_malefics(self, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        """Lords of H2/H3/H6/H7/H8/H11/H12, including maraka houses H2/H7."""
        adverse_houses = {BhavaNumber.H2, BhavaNumber.H3, BhavaNumber.H6, BhavaNumber.H7,
                          BhavaNumber.H8, BhavaNumber.H11, BhavaNumber.H12}
        return exclude_grahas([graha for graha in self._grahas.values()
                               if any(bhava.number in adverse_houses for bhava in graha.owned_bhavas)], exclude)

    def _build_relationship_graph(self) -> None:
        """Computes relationships and evaluates Yoga sutras."""
        for graha_type, graha in self._grahas.items():
            b_num = graha.bhava.number
            self._bhava_occupants[b_num].append(graha)

            nak_idx = graha.nakshatra.index
            self._nakshatra_occupants.setdefault(nak_idx, []).append(graha)

        for graha_type, source_graha in self._grahas.items():
            source_b_num = source_graha.bhava.number.value
            offsets = self._get_aspect_offsets(graha_type)

            for offset in offsets:
                target_b_num = BhavaNumber((source_b_num - 1 + offset) % 12 + 1)
                target_bhava = self._bhavas[target_b_num]

                self._bhava_aspects[target_b_num].append(source_graha)
                self._graha_aspected_bhavas[graha_type].append(target_bhava)

                for target_graha in self._bhava_occupants[target_b_num]:
                    if target_graha.type != graha_type:
                        self._graha_aspected_planets[graha_type].append(target_graha)

        # Index 5 Sambandhas
        for g1_type, g1 in self._grahas.items():
            for g2_type, g2 in self._grahas.items():
                if g1_type == g2_type:
                    continue
                if g1_type in (GrahaId.RAHU, GrahaId.KETU) and g1.rashi.lord.type == g2_type:
                    self._add_sambandha(g1_type, SambandhaType.DISPOSITOR, g2)
                if g1.bhava == g2.bhava:
                    self._add_sambandha(g1_type, SambandhaType.CONJUNCTION, g2)
                if g1.rashi.lord.type == g2_type and g2.rashi.lord.type == g1_type:
                    self._add_sambandha(g1_type, SambandhaType.EXCHANGE, g2)
                if g2 in self._graha_aspected_planets[g1_type] and g1 in self._graha_aspected_planets[g2_type]:
                    self._add_sambandha(g1_type, SambandhaType.MUTUAL_ASPECT, g2)
                if g1.rashi.lord.type == g2_type and g2 in self._graha_aspected_planets[g1_type]:
                    self._add_sambandha(g1_type, SambandhaType.OCCUPIES_AND_ASPECTS_LORD, g2)
                if g1.rashi.lord.type == g2_type and g1 in self._graha_aspected_planets[g2_type]:
                    self._add_sambandha(g1_type, SambandhaType.OCCUPIES_AND_RECEIVES_LORD_ASPECT, g2)

        # Yoga evaluation follows construction of every chart in the aggregate.

    def _add_sambandha(self, source: GrahaId, type: SambandhaType, target: Graha) -> None:
        key = (source, type)
        if key not in self._sambandha_map: self._sambandha_map[key] = []
        if target not in self._sambandha_map[key]: self._sambandha_map[key].append(target)

    def _get_aspect_offsets(self, graha_type: GrahaId) -> List[int]:
        offsets = [6]
        if graha_type == GrahaId.MARS: offsets.extend([3, 7])
        elif graha_type in (GrahaId.JUPITER, GrahaId.RAHU, GrahaId.KETU): offsets.extend([4, 8])
        elif graha_type == GrahaId.SATURN: offsets.extend([2, 9])
        return offsets

    # --- Protocol Implementation ---

    def graha(self, graha_type: GrahaId) -> Graha: return self._grahas[graha_type]
    def bhava(self, number: BhavaNumber) -> Bhava: return self._bhavas[number]
    def rashi(self, rashi_type: RashiId) -> Rashi: return self._rashis[rashi_type]

    def get_graha(self, graha_type: GrahaId) -> Graha: return self._grahas[graha_type]
    def get_bhava(self, bhava_num: BhavaNumber) -> Bhava: return self._bhavas[bhava_num]
    def get_rashi(self, rashi_type: RashiId) -> Rashi: return self._rashis[rashi_type]

    def get_graha_in_varga(self, graha_type: GrahaId, varga_type: VargaType) -> Graha:
        return self._horoscope_root.varga(varga_type).graha(graha_type)

    def get_rashi_lord(self, rashi_type: RashiId) -> Graha:
        return self._grahas[RASHI_LORDS[rashi_type]]

    def get_occupants_for_bhava(self, bhava_num: BhavaNumber, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return exclude_grahas(list(self._bhava_occupants[bhava_num]), exclude)

    def get_aspecting_planets_for_bhava(self, bhava_num: BhavaNumber, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return exclude_grahas(list(self._bhava_aspects[bhava_num]), exclude)

    def get_aspecting_planets_for_graha(self, target: GrahaId, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        target_b_num = self._grahas[target].bhava.number
        return exclude_grahas([g for g in self._bhava_aspects[target_b_num] if g.type != target], exclude)

    def get_planets_aspected_by_graha(self, source: GrahaId, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return exclude_grahas(list(self._graha_aspected_planets[source]), exclude)

    def get_bhavas_aspected_by_graha(self, source: GrahaId) -> list[Bhava]:
        return list(self._graha_aspected_bhavas[source])

    def get_occupants_for_nakshatra(self, nakshatra_index: int, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return exclude_grahas(list(self._nakshatra_occupants.get(nakshatra_index, [])), exclude)

    def get_sambandha_planets_for_graha(self, source: GrahaId, type: SambandhaType, *, exclude: list[GrahaId] | None = None) -> list[Graha]:
        return exclude_grahas(list(self._sambandha_map.get((source, type), [])), exclude)

    def get_bhavas_ruled_by_graha(self, graha_type: GrahaId) -> list[Bhava]:
        return list(self._ruled_bhavas[graha_type])

    def get_yogas_for_graha(self, graha_type: GrahaId) -> list[Yoga]:
        """Initialize once, then retrieve from the per-planet index."""
        self._horoscope_root.get_chart_yogas(self)
        return list(self._graha_yoga_map.get(graha_type, []))

    def get_all_detected_yogas(self) -> list[Yoga]:
        self._horoscope_root.get_chart_yogas(self)
        return [y for y in self._yoga_map.values() if y.is_present]

    @property
    def yogas(self) -> HoroscopeYogas:
        return self._horoscope_root.get_chart_yogas(self)

    @property
    def vimsottari(self) -> Vimsottari:
        """Every divisional chart uses the same natal-Moon dasha calculator."""
        return self._horoscope_root.vimsottari

    @property
    def lagna(self) -> Bhava: return self.bhava(BhavaNumber.H1)
    @property
    def lagnesh(self) -> Graha: return self.lagna.lord

    @property
    def own_house(self) -> List[Graha]:
        return [g for g in self._grahas.values() if g.sambandha.dispositor.type == g.type]

    @property
    def most_populated_bhava(self) -> Bhava:
        return max(self._bhavas.values(), key=lambda b: len(b.occupants()))

    @property
    def empty_bhavas(self) -> List[Bhava]:
        return [b for b in self._bhavas.values() if not b.occupants()]

    @property
    def retrograde_planets(self) -> List[Graha]:
        return [g for g in self._grahas.values() if g.is_retrograde]

    @property
    def combust_planets(self) -> List[Graha]:
        return [g for g in self._grahas.values() if g.is_combust]

    @property
    def exalted_planets(self) -> List[Graha]:
        return [g for g in self._grahas.values() if g.dignity.is_exalted]

    def __repr__(self) -> str:
        return f"Chart({self._varga_type.value})"




ZODIAC_SIGNS = ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo', 'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces']


def rashi_name_from_num(n):
    return RNUM_TO_NAME[n]


GRAHA_NAMES = {planet_type: planet_type.value for planet_type in GrahaId}


def relative_house(anchor_rashi: int, rashi: int) -> int:
    return (int(rashi) - int(anchor_rashi)) % 12 + 1


def house_rashi(anchor_rashi: int, house: int) -> int:
    return (int(anchor_rashi) + int(house) - 2) % 12 + 1


RNUM_TO_NAME = {i + 1: n for i, n in enumerate(ZODIAC_SIGNS)}




NATURAL_REL: dict[GrahaId, tuple[frozenset[GrahaId], frozenset[GrahaId]]] = {
    GrahaId.SUN: (frozenset((GrahaId.MOON, GrahaId.MARS, GrahaId.JUPITER)), frozenset((GrahaId.VENUS, GrahaId.SATURN))),
    GrahaId.MOON: (frozenset((GrahaId.SUN, GrahaId.MERCURY)), frozenset()),
    GrahaId.MARS: (frozenset((GrahaId.SUN, GrahaId.MOON, GrahaId.JUPITER)), frozenset((GrahaId.MERCURY,))),
    GrahaId.MERCURY: (frozenset((GrahaId.SUN, GrahaId.VENUS)), frozenset((GrahaId.MOON,))),
    GrahaId.JUPITER: (frozenset((GrahaId.SUN, GrahaId.MOON, GrahaId.MARS)), frozenset((GrahaId.MERCURY, GrahaId.VENUS))),
    GrahaId.VENUS: (frozenset((GrahaId.MERCURY, GrahaId.SATURN)), frozenset((GrahaId.SUN, GrahaId.MOON))),
    GrahaId.SATURN: (frozenset((GrahaId.VENUS, GrahaId.MERCURY)), frozenset((GrahaId.SUN, GrahaId.MOON, GrahaId.MARS))),
    GrahaId.RAHU: (frozenset(), frozenset()),
    GrahaId.KETU: (frozenset(), frozenset()),
}


def naisargik_relation(first: GrahaId | str, second: GrahaId | str) -> NaturalRelation:
    graha = first if isinstance(first, GrahaId) else GrahaId(first)
    other = second if isinstance(second, GrahaId) else GrahaId(second)
    friends, enemies = NATURAL_REL[graha]
    if other in friends:
        return NaturalRelation.FRIEND
    if other in enemies:
        return NaturalRelation.ENEMY
    return NaturalRelation.NEUTRAL


# =====================================================================
# SIGN DIGNITY (rashi-level; positions only, no birth chart needed)
#
# Used by transit queries to rate a planet's own sign (exaltation / own /
# moolatrikona / debilitation) plus its Panchadha Maitri ("five-fold
# friendship") with the current lord of whichever sign it occupies
# otherwise. Exact degree bands (e.g. Mercury's narrow moolatrikona arc in
# Virgo) are out of scope: every rule here works whole-sign, which is the
# resolution the nakshatra-pada transit files carry.
# =====================================================================

RASHI_ELEMENT: dict[RashiId, Tatva] = {
    RashiId.ARIES: Tatva.FIRE, RashiId.TAURUS: Tatva.EARTH, RashiId.GEMINI: Tatva.AIR,
    RashiId.CANCER: Tatva.WATER, RashiId.LEO: Tatva.FIRE, RashiId.VIRGO: Tatva.EARTH,
    RashiId.LIBRA: Tatva.AIR, RashiId.SCORPIO: Tatva.WATER, RashiId.SAGITTARIUS: Tatva.FIRE,
    RashiId.CAPRICORN: Tatva.EARTH, RashiId.AQUARIUS: Tatva.AIR, RashiId.PISCES: Tatva.WATER,
}

RASHI_LORDS: dict[RashiId, GrahaId] = {
    RashiId.ARIES: GrahaId.MARS, RashiId.TAURUS: GrahaId.VENUS,
    RashiId.GEMINI: GrahaId.MERCURY, RashiId.CANCER: GrahaId.MOON,
    RashiId.LEO: GrahaId.SUN, RashiId.VIRGO: GrahaId.MERCURY,
    RashiId.LIBRA: GrahaId.VENUS, RashiId.SCORPIO: GrahaId.MARS,
    RashiId.SAGITTARIUS: GrahaId.JUPITER, RashiId.CAPRICORN: GrahaId.SATURN,
    RashiId.AQUARIUS: GrahaId.SATURN, RashiId.PISCES: GrahaId.JUPITER,
}

#: Exaltation sign of each graha. Rahu/Ketu follow the common (if debated)
#: convention: Rahu exalted in Gemini, Ketu -- its shadow opposite -- in
#: Sagittarius.
EXALTATION_RASHI: dict[GrahaId, RashiId] = {
    GrahaId.SUN: RashiId.ARIES, GrahaId.MOON: RashiId.TAURUS, GrahaId.MARS: RashiId.CAPRICORN,
    GrahaId.MERCURY: RashiId.VIRGO, GrahaId.JUPITER: RashiId.CANCER, GrahaId.VENUS: RashiId.PISCES,
    GrahaId.SATURN: RashiId.LIBRA, GrahaId.RAHU: RashiId.GEMINI, GrahaId.KETU: RashiId.SAGITTARIUS,
}

#: Debilitation is always the exaltation sign's opposite (180 deg / 6 signs away).
DEBILITATION_RASHI: dict[GrahaId, RashiId] = {
    graha: RashiId((int(rashi) + 5) % 12 + 1) for graha, rashi in EXALTATION_RASHI.items()
}

#: Own sign(s); Rahu and Ketu own none in the classical (Parashari) scheme.
OWN_RASHIS: dict[GrahaId, frozenset[RashiId]] = {
    GrahaId.SUN: frozenset({RashiId.LEO}),
    GrahaId.MOON: frozenset({RashiId.CANCER}),
    GrahaId.MARS: frozenset({RashiId.ARIES, RashiId.SCORPIO}),
    GrahaId.MERCURY: frozenset({RashiId.GEMINI, RashiId.VIRGO}),
    GrahaId.JUPITER: frozenset({RashiId.SAGITTARIUS, RashiId.PISCES}),
    GrahaId.VENUS: frozenset({RashiId.TAURUS, RashiId.LIBRA}),
    GrahaId.SATURN: frozenset({RashiId.CAPRICORN, RashiId.AQUARIUS}),
    GrahaId.RAHU: frozenset(), GrahaId.KETU: frozenset(),
}

#: The one sign, among a graha's own sign(s), that also carries its Moolatrikona
#: degree band; reported as MOOLATRIKONA rather than plain SWARASHI throughout
#: that whole sign (see the module note on degree precision above).
MOOLATRIKONA_RASHI: dict[GrahaId, RashiId] = {
    GrahaId.SUN: RashiId.LEO, GrahaId.MOON: RashiId.TAURUS, GrahaId.MARS: RashiId.ARIES,
    GrahaId.MERCURY: RashiId.VIRGO, GrahaId.JUPITER: RashiId.SAGITTARIUS,
    GrahaId.VENUS: RashiId.LIBRA, GrahaId.SATURN: RashiId.AQUARIUS,
}

#: Tatkalika (positional/"temporary") friendship: houses counted sign-wise
#: from one planet to another. 2nd/3rd/4th/10th/11th/12th are friendly;
#: 1st(conjunction)/5th/6th/7th/8th/9th are hostile. Together with
#: ``naisargik_relation`` (permanent/natural relation) this gives the
#: Panchadha Maitri ("five-fold relationship") compound below.
TEMPORAL_FRIEND_HOUSES = frozenset({2, 3, 4, 10, 11, 12})
TEMPORAL_ENEMY_HOUSES = frozenset({1, 5, 6, 7, 8, 9})

#: Panchadha Maitri compound table: (natural relation, is temporal friend) -> compound.
_COMPOUND_RELATION: dict[tuple[NaturalRelation, bool], DignityType] = {
    (NaturalRelation.FRIEND, True): DignityType.ADHI_MITRA,
    (NaturalRelation.FRIEND, False): DignityType.SAMA,
    (NaturalRelation.NEUTRAL, True): DignityType.MITRA,
    (NaturalRelation.NEUTRAL, False): DignityType.SHATRU,
    (NaturalRelation.ENEMY, True): DignityType.SAMA,
    (NaturalRelation.ENEMY, False): DignityType.ADHI_SHATRU,
}


def temporal_relation_is_friend(from_rashi: RashiId | int, to_rashi: RashiId | int) -> bool:
    """Is ``to_rashi`` a tatkalika (positional) friend's house counted from ``from_rashi``?"""
    house = relative_house(int(from_rashi), int(to_rashi))
    if house in TEMPORAL_FRIEND_HOUSES:
        return True
    if house in TEMPORAL_ENEMY_HOUSES:
        return False
    raise AssertionError(f'relative_house returned {house}; 1..12 must all be classified')


def compound_relation(graha: GrahaId, other: GrahaId, graha_rashi: RashiId | int,
                      other_rashi: RashiId | int) -> DignityType:
    """Panchadha Maitri: ``graha``'s natural relation with ``other`` refined by their
    current signs -- friend+friend is Adhi Mitra, friend+enemy is Sama (demoted),
    neutral+friend is Mitra, neutral+enemy is Shatru, enemy+friend is Sama
    (promoted), enemy+enemy is Adhi Shatru.
    """
    natural = naisargik_relation(graha, other)
    is_friend_now = temporal_relation_is_friend(graha_rashi, other_rashi)
    return _COMPOUND_RELATION[(natural, is_friend_now)]


def navamsa_rashi(pada: int) -> RashiId:
    """D9 (Navamsha) sign of a zodiac-wide pada (1..108).

    Each rashi's own 9 padas of 3 deg 20' are exactly its 9 navamsas, so no
    birth data or continuous longitude is needed: fire signs' navamsas start
    from Aries, earth from Capricorn, air from Libra, water from Cancer.
    """
    rashi = pada_rashi(pada)
    position = (_valid_pada(pada) - 1) % PADAS_PER_RASHI        # 0..8 within the rashi
    start = {Tatva.FIRE: RashiId.ARIES, Tatva.EARTH: RashiId.CAPRICORN,
             Tatva.AIR: RashiId.LIBRA, Tatva.WATER: RashiId.CANCER}[RASHI_ELEMENT[rashi]]
    return RashiId((int(start) - 1 + position) % 12 + 1)


def graha_dignity(graha: GrahaId | str, pada: int, padas_by_graha: Mapping[GrahaId, int]) -> GrahaDignity:
    """Sign-level dignity of ``graha`` standing at ``pada``, given everyone's padas.

    Priority: exaltation, then debilitation, then the Moolatrikona sign (if
    one is designated), then any other own sign, and otherwise the Panchadha
    Maitri relation with the current lord of its sign. Vargottama is tracked
    independently: it can combine with any of the above.
    """
    graha = graha if isinstance(graha, GrahaId) else GrahaId(graha)
    rashi = pada_rashi(pada)
    is_vargottama = navamsa_rashi(pada) == rashi
    if rashi == EXALTATION_RASHI.get(graha):
        return GrahaDignity(DignityType.EXALTED, is_vargottama)
    if rashi == DEBILITATION_RASHI.get(graha):
        return GrahaDignity(DignityType.DEBILITATED, is_vargottama)
    if rashi == MOOLATRIKONA_RASHI.get(graha):
        return GrahaDignity(DignityType.MOOLATRIKONA, is_vargottama)
    if rashi in OWN_RASHIS.get(graha, frozenset()):
        return GrahaDignity(DignityType.SWARASHI, is_vargottama)
    lord = RASHI_LORDS[rashi]
    if lord not in padas_by_graha:
        raise ValueError(f"Need {lord.value}'s pada to rate {graha.value} in {rashi.name.title()}")
    dignity_type = compound_relation(graha, lord, rashi, pada_rashi(padas_by_graha[lord]))
    return GrahaDignity(dignity_type, is_vargottama)


# =====================================================================
# SPECIAL ASPECTS (house-counted, 7th aspect implied for every graha)
# =====================================================================

SPECIAL_ASPECTS: dict[str, list[int]] = {
    GrahaId.MARS.value: [4, 7, 8],
    GrahaId.JUPITER.value: [5, 7, 9],
    GrahaId.SATURN.value: [3, 7, 10],
    GrahaId.RAHU.value: [5, 7, 9],
    GrahaId.KETU.value: [5, 7, 9],
}


# =====================================================================
# POSITION-ONLY (TRANSIT) CHARTS AND SAMBANDHA LISTINGS
# =====================================================================

class TransitChartContext(IHoroscopeChartContext):
    """Minimal aggregate root for charts built from sign placements alone.

    Transit snapshots have no birth moment, so divisional charts, yogas,
    shadbala, and vimsottari are unavailable by definition.
    """

    def varga(self, varga_type: VargaType) -> Chart:
        raise ValueError("Divisional charts are unavailable for transit charts")

    def is_vargottama(self, graha_type: GrahaId) -> bool:
        return False

    def get_shadbala_for_graha(self, graha_type: GrahaId) -> Optional[GrahaAstabala]:
        return None

    def get_yoga_activation_periods(self, grahas: Sequence[GrahaId]) -> list["VimsottariDasha"]:
        return []

    def get_chart_yogas(self, chart: Chart) -> "HoroscopeYogas":
        raise ValueError("Yoga evaluation is unavailable for transit charts")

    @property
    def vimsottari(self) -> "Vimsottari":
        raise ValueError("Vimsottari is unavailable for transit charts")


# --- Nakshatra pada geometry (108 padas of 3 deg 20 min; 4 per nakshatra, 9 per rashi) ---

TOTAL_PADAS = 108
PADAS_PER_NAKSHATRA = 4
PADAS_PER_RASHI = 9
PADA_SPAN_DEGREES = 360.0 / TOTAL_PADAS


def _valid_pada(pada: int) -> int:
    pada = int(pada)
    if not 1 <= pada <= TOTAL_PADAS:
        raise ValueError(f"Nakshatra pada index must be 1..{TOTAL_PADAS}, got {pada}")
    return pada


def pada_from_longitude(longitude: float) -> int:
    """Zodiac-wide pada index (1..108) of a sidereal longitude."""
    return min(int((float(longitude) % 360.0) // PADA_SPAN_DEGREES), TOTAL_PADAS - 1) + 1


def pada_rashi(pada: int) -> RashiId:
    """Rashi containing a zodiac-wide pada (padas 1..9 are Aries, 100..108 Pisces)."""
    return RashiId((_valid_pada(pada) - 1) // PADAS_PER_RASHI + 1)


def pada_nakshatra(pada: int) -> NakshatraId:
    """Nakshatra containing a zodiac-wide pada (padas 1..4 are Ashwini)."""
    return NakshatraId((_valid_pada(pada) - 1) // PADAS_PER_NAKSHATRA + 1)


def pada_in_nakshatra(pada: int) -> int:
    """Quarter (1..4) of its nakshatra that a zodiac-wide pada represents."""
    return (_valid_pada(pada) - 1) % PADAS_PER_NAKSHATRA + 1


def rashi_padas(rashi: RashiId | int) -> range:
    """Zodiac-wide padas inside one rashi, e.g. Simha -> 37..45."""
    first = (int(RashiId(rashi)) - 1) * PADAS_PER_RASHI + 1
    return range(first, first + PADAS_PER_RASHI)


def nakshatra_padas(nakshatra: NakshatraId | int) -> range:
    """Zodiac-wide padas inside one nakshatra, e.g. Magha -> 37..40."""
    first = (int(NakshatraId(nakshatra)) - 1) * PADAS_PER_NAKSHATRA + 1
    return range(first, first + PADAS_PER_NAKSHATRA)


def nakshatra_pada_index(nakshatra: NakshatraId | int, quarter: int) -> int:
    """Zodiac-wide pada of one quarter (1..4) of a nakshatra, e.g. (Magha, 2) -> 38."""
    if not 1 <= int(quarter) <= PADAS_PER_NAKSHATRA:
        raise ValueError(f"Nakshatra quarter must be 1..{PADAS_PER_NAKSHATRA}, got {quarter}")
    return nakshatra_padas(nakshatra)[int(quarter) - 1]


def build_longitude_chart(longitude_by_graha: Dict[GrahaId, float],
                          *, lagna_rashi: RashiId = RashiId.ARIES) -> Chart:
    """Build a whole-sign Chart from sidereal longitudes alone (no birth data).

    All nine grahas must be supplied because sign lordship resolves against
    chart members. Dignity, avastha, and strength stay neutral placeholders.
    """
    lagna = RashiId(lagna_rashi)
    house_rashi_map = {
        BhavaNumber(house): RashiId(house_rashi(int(lagna), house)) for house in range(1, 13)
    }
    raw_position_inputs: Dict[GrahaId, Tuple] = {}
    for graha_type in GrahaId:
        if graha_type not in longitude_by_graha:
            raise ValueError(f"Missing placement for {graha_type.value}")
        degrees = float(longitude_by_graha[graha_type]) % 360.0
        rashi = RashiId(int(degrees // 30) + 1)
        pada = pada_from_longitude(degrees)
        nakshatra = pada_nakshatra(pada)
        raw_position_inputs[graha_type] = (
            degrees, rashi, BhavaNumber(relative_house(int(lagna), int(rashi))),
            nakshatra.id, nakshatra.nakshatra_name, pada_in_nakshatra(pada), nakshatra.lord,
            GrahaAvastha("SWASTHA"), DignityType.SAMA, None, False, False,
        )
    return Chart(VargaType.D1_RASHI, raw_position_inputs, house_rashi_map, TransitChartContext())


def build_rashi_chart(rashi_by_graha: Dict[GrahaId, RashiId | int],
                      *, lagna_rashi: RashiId = RashiId.ARIES) -> Chart:
    """Build a whole-sign Chart from graha sign placements alone.

    Degrees are normalised to mid-sign, so every rashi-level relationship
    (conjunction, exchange, mutual aspect, lordship links, dispositors) is
    exact while degree-sensitive values stay out of scope. All nine grahas
    must be supplied because sign lordship resolves against chart members.
    """
    for graha_type in GrahaId:
        if graha_type not in rashi_by_graha:
            raise ValueError(f"Missing sign placement for {graha_type.value}")
    return build_longitude_chart(
        {graha: (int(RashiId(rashi)) - 1) * 30 + 15.0 for graha, rashi in rashi_by_graha.items()},
        lagna_rashi=lagna_rashi)


def build_pada_chart(pada_by_graha: Dict[GrahaId, int],
                     *, lagna_rashi: RashiId = RashiId.ARIES) -> Chart:
    """Build a whole-sign Chart from zodiac-wide pada indexes (1..108).

    Each graha sits at its pada's mid-point, so rashi, nakshatra, and pada of
    every Graha object are exact.
    """
    for graha_type in GrahaId:
        if graha_type not in pada_by_graha:
            raise ValueError(f"Missing pada placement for {graha_type.value}")
    return build_longitude_chart(
        {graha: (_valid_pada(pada) - 0.5) * PADA_SPAN_DEGREES for graha, pada in pada_by_graha.items()},
        lagna_rashi=lagna_rashi)


#: The five sambandhas indexed between any two grahas; DISPOSITOR is the
#: additional node-only (Rahu/Ketu) lordship link.
FIVE_SAMBANDHAS: tuple[SambandhaType, ...] = (
    SambandhaType.EXCHANGE,
    SambandhaType.CONJUNCTION,
    SambandhaType.MUTUAL_ASPECT,
    SambandhaType.OCCUPIES_AND_ASPECTS_LORD,
    SambandhaType.OCCUPIES_AND_RECEIVES_LORD_ASPECT,
)


def chart_sambandhas(chart: Chart, *, exclude: list[GrahaId] | None = None,
                     types: Sequence[SambandhaType] | None = None
                     ) -> list[tuple[SambandhaType, GrahaId, GrahaId]]:
    """List every indexed sambandha as (type, source, target) triples.

    Symmetric types (conjunction, exchange, mutual aspect) surface once per
    direction; directional types (dispositor, lord occupancy/aspect links)
    keep their canonical source. Excluded grahas drop out on either side;
    ``types`` limits the listing (default: every SambandhaType).
    """
    excluded = set(exclude or ())
    triples: list[tuple[SambandhaType, GrahaId, GrahaId]] = []
    for source in GrahaId:
        if source in excluded:
            continue
        for sambandha_type in (types or tuple(SambandhaType)):
            for target in chart.get_sambandha_planets_for_graha(source, sambandha_type,
                                                                exclude=list(excluded) or None):
                triples.append((sambandha_type, source, target.type))
    return triples


def rashi_sambandhas(rashi_by_graha: Dict[GrahaId, RashiId | int],
                     *, exclude: list[GrahaId] | None = None
                     ) -> list[tuple[SambandhaType, GrahaId, GrahaId]]:
    """Detect every sambandha among grahas placed by sign (e.g. transits)."""
    return chart_sambandhas(build_rashi_chart(rashi_by_graha), exclude=exclude)


def pada_sambandhas(pada_by_graha: Dict[GrahaId, int], *,
                    exclude: list[GrahaId] | None = None,
                    types: Sequence[SambandhaType] | None = FIVE_SAMBANDHAS
                    ) -> list[tuple[SambandhaType, GrahaId, GrahaId]]:
    """Detect sambandhas among grahas placed by zodiac-wide pada (1..108).

    Defaults to the five inter-graha sambandhas; pass ``types=None`` to also
    list Rahu/Ketu DISPOSITOR links.
    """
    return chart_sambandhas(build_pada_chart(pada_by_graha), exclude=exclude, types=types)


# =====================================================================
# TRANSIT KINDS, KETU FROM RAHU, AND COMBUSTION
# =====================================================================

class PadaTransitKind(str, Enum):
    """Coarsest boundary a pada change crosses; every rashi/nakshatra change is a pada change."""
    RASHI = "rashi"
    NAKSHATRA = "nakshatra"
    PADA = "pada"

    def __str__(self) -> str:
        return self.value


def pada_transit_kind(from_pada: int, to_pada: int) -> PadaTransitKind:
    if pada_rashi(from_pada) != pada_rashi(to_pada):
        return PadaTransitKind.RASHI
    if pada_nakshatra(from_pada) != pada_nakshatra(to_pada):
        return PadaTransitKind.NAKSHATRA
    return PadaTransitKind.PADA


#: Ketu is exactly opposite Rahu: 180 degrees = 54 padas = 6 rashis. Rashi
#: ingresses of the nodes coincide; nakshatra changes never do (54 = 13.5 x 4).
KETU_PADA_OFFSET = TOTAL_PADAS // 2


def ketu_pada(rahu_pada: int) -> int:
    """Ketu's zodiac-wide pada from Rahu's."""
    return (_valid_pada(rahu_pada) - 1 + KETU_PADA_OFFSET) % TOTAL_PADAS + 1


#: Combustion orbs (degrees of longitude from the Sun), as recorded in
#: transit_v3.csv: one orb per graha, no reduction while retrograde. The Sun,
#: Moon, Rahu, and Ketu are never treated as combust.
COMBUSTION_ORBS: Dict[GrahaId, float] = {
    GrahaId.MARS: 17.0,
    GrahaId.MERCURY: 14.0,
    GrahaId.JUPITER: 11.0,
    GrahaId.VENUS: 10.0,
    GrahaId.SATURN: 15.0,
}


def longitude_separation(first: float, second: float) -> float:
    """Shortest arc (0..180 degrees) between two ecliptic longitudes."""
    return abs((float(first) - float(second) + 180.0) % 360.0 - 180.0)


def is_combust_by_longitude(graha: GrahaId, longitude: float, sun_longitude: float,
                            orbs: Dict[GrahaId, float] = COMBUSTION_ORBS) -> bool:
    """A graha is combust within its orb of the Sun's longitude."""
    orb = orbs.get(graha)
    return orb is not None and longitude_separation(longitude, sun_longitude) <= orb
