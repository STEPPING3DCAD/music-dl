"""Pure, deterministic album-release grouping decisions."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

_ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")
_TRAILING_MARKER = re.compile(r"\s*(?:\([^()] *\)|\[[^\[\]]*\])\s*$".replace(" ", ""))


def normalize_text(value: object | None) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    words: list[str] = []
    current: list[str] = []
    for character in plain.casefold():
        if character.isalnum():
            current.append(character)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return " ".join(words)


def base_title(value: object | None) -> str:
    title = str(value or "").strip()
    while True:
        stripped = _TRAILING_MARKER.sub("", title).strip()
        if stripped == title:
            return normalize_text(title)
        title = stripped


def compatible_title(left: str, right: str) -> bool:
    return normalize_text(left) == normalize_text(right) or base_title(left) == base_title(right)


def valid_isrc(value: object | None) -> str | None:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    return cleaned if _ISRC.fullmatch(cleaned) else None


def _integer(value: object | None) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


@dataclass(frozen=True)
class RecordingSlot:
    key: tuple[str, str, int | None, int | None, int]
    rows: tuple[dict, ...]
    duration: int | None
    isrcs: frozenset[str]

    @property
    def isrc(self) -> str | None:
        return next(iter(self.isrcs)) if len(self.isrcs) == 1 else None

    @property
    def sort_key(self) -> tuple[str, str, int, int, int]:
        artist, title, disc, track, ordinal = self.key
        return artist, title, disc or 0, track or 0, ordinal


@dataclass
class LocalAlbumGroup:
    title: str
    rows: tuple[dict, ...]
    slots: tuple[RecordingSlot, ...]
    album_artist: str | None
    signature: str

    def values(self, field_name: str) -> set[object]:
        return {
            value
            for row in self.rows
            if (value := row.get(field_name)) not in (None, "")
        }

    def confirmed_values(self, field_name: str) -> set[object]:
        counts: Counter[object] = Counter()
        for slot in self.slots:
            values = {
                value
                for row in slot.rows
                if (value := row.get(field_name)) not in (None, "")
            }
            if len(values) == 1:
                counts.update(values)
        threshold = min(3, len(self.slots))
        return {value for value, count in counts.items() if threshold and count >= threshold}


@dataclass(frozen=True)
class EvidenceItem:
    code: str
    family: str
    points: int
    sources: frozenset[str]
    explanation: str


@dataclass(frozen=True)
class Veto:
    code: str
    explanation: str


@dataclass
class GroupingAssessment:
    left_signature: str
    right_signature: str
    score: int = 0
    outcome: str = "separate"
    evidence: list[EvidenceItem] = field(default_factory=list)
    family_scores: dict[str, int] = field(default_factory=dict)
    diversity_bonus: int = 0
    vetoes: list[Veto] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    isrc_matches: int = 0
    fallback_matches: int = 0
    coverage: float = 0.0
    qualifying_sources: frozenset[str] = frozenset()
    user_decision: str | None = None
    user_decision_superseded: bool = False


def _cluster_slots(rows: Iterable[dict]) -> tuple[RecordingSlot, ...]:
    partitions: dict[tuple[str, str, int | None, int | None], list[dict]] = defaultdict(list)
    for row in rows:
        partitions[(
            normalize_text(row.get("artist")),
            normalize_text(row.get("title")),
            _integer(row.get("disc_number")),
            _integer(row.get("track_number")),
        )].append(row)

    slots: list[RecordingSlot] = []
    for partition, members in sorted(
        partitions.items(),
        key=lambda item: (item[0][0], item[0][1], item[0][2] or 0, item[0][3] or 0),
    ):
        ordered = sorted(
            members,
            key=lambda row: (
                _integer(row.get("duration")) is None,
                _integer(row.get("duration")) or 0,
                str(row.get("path") or ""),
            ),
        )
        clusters: list[list[dict]] = []
        for row in ordered:
            duration = _integer(row.get("duration"))
            joined = False
            for cluster in clusters:
                durations = [_integer(member.get("duration")) for member in cluster]
                known = [item for item in durations if item is not None]
                if duration is None and not known or duration is not None and known and max((*known, duration)) - min((*known, duration)) <= 5:
                    cluster.append(row)
                    joined = True
                if joined:
                    break
            if not joined:
                clusters.append([row])

        clusters.sort(key=lambda cluster: (
            min((_integer(row.get("duration")) for row in cluster), default=None) is None,
            min((value for row in cluster if (value := _integer(row.get("duration"))) is not None), default=0),
            min(str(row.get("path") or "") for row in cluster),
        ))
        for ordinal, cluster in enumerate(clusters):
            durations = [value for row in cluster if (value := _integer(row.get("duration"))) is not None]
            isrcs = frozenset(
                isrc for row in cluster if (isrc := valid_isrc(row.get("isrc")))
            )
            slots.append(RecordingSlot(
                key=(*partition, ordinal),
                rows=tuple(sorted(cluster, key=lambda row: str(row.get("path") or ""))),
                duration=min(durations) if durations else None,
                isrcs=isrcs,
            ))
    return tuple(sorted(slots, key=lambda slot: slot.sort_key))


def _album_artist(rows: Iterable[dict]) -> str | None:
    rows = tuple(rows)
    embedded = {normalize_text(row.get("album_artist")) for row in rows if normalize_text(row.get("album_artist"))}
    if len(embedded) == 1:
        return next(iter(embedded))
    if embedded:
        return None
    artists = {normalize_text(row.get("artist")) for row in rows if normalize_text(row.get("artist"))}
    return next(iter(artists)) if len(artists) == 1 else None


def _canonical_json_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _group_signature(title: str, rows: tuple[dict, ...], slots: tuple[RecordingSlot, ...], album_artist: str | None) -> str:
    fields = (
        "release_date", "track_total", "disc_total", "musicbrainz_release_id",
        "musicbrainz_release_group_id", "provider_namespace", "provider_album_id", "barcode",
    )
    payload = {
        "version": 1,
        "exact_album": title,
        "album": normalize_text(title),
        "album_artist": album_artist,
        "release": {
            field_name: sorted({str(row[field_name]) for row in rows if row.get(field_name) not in (None, "")})
            for field_name in fields
        },
        "slots": [list(slot.key) for slot in slots],
    }
    return _canonical_json_hash(payload)


def build_local_album_groups(rows: Iterable[dict]) -> list[LocalAlbumGroup]:
    exact: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        album = str(row.get("album") or "").strip()
        if album:
            exact[album].append(dict(row))
    groups: list[LocalAlbumGroup] = []
    for title, members in sorted(exact.items()):
        ordered = tuple(sorted(members, key=lambda row: str(row.get("path") or "")))
        slots = _cluster_slots(ordered)
        album_artist = _album_artist(ordered)
        groups.append(LocalAlbumGroup(
            title=title,
            rows=ordered,
            slots=slots,
            album_artist=album_artist,
            signature=_group_signature(title, ordered, slots, album_artist),
        ))
    return groups


def _provider_values(group: LocalAlbumGroup, *, confirmed: bool = False) -> set[tuple[str, str]]:
    rows = group.rows
    pairs = {
        (normalize_text(row.get("provider_namespace")), str(row.get("provider_album_id")))
        for row in rows
        if normalize_text(row.get("provider_namespace")) and row.get("provider_album_id") not in (None, "")
    }
    if not confirmed:
        return pairs
    return {
        pair for pair in pairs
        if pair[0] in {normalize_text(value) for value in group.confirmed_values("provider_namespace")}
        and pair[1] in {str(value) for value in group.confirmed_values("provider_album_id")}
    }


def find_candidates(groups: Iterable[LocalAlbumGroup]) -> list[tuple[LocalAlbumGroup, LocalAlbumGroup]]:
    candidates: list[tuple[LocalAlbumGroup, LocalAlbumGroup]] = []
    for left, right in combinations(groups, 2):
        same_mb = bool(left.values("musicbrainz_release_id") & right.values("musicbrainz_release_id"))
        same_provider = bool(_provider_values(left) & _provider_values(right))
        same_artist = bool(left.album_artist and left.album_artist == right.album_artist)
        title_match = compatible_title(left.title, right.title)
        left_isrcs = {slot.isrc for slot in left.slots if slot.isrc}
        right_isrcs = {slot.isrc for slot in right.slots if slot.isrc}
        overlap = len(left_isrcs & right_isrcs)
        smaller = min(len(left.slots), len(right.slots))
        isrc_candidate = smaller > 0 and overlap >= min(2, smaller) and overlap / smaller >= 0.5
        if same_mb or same_provider or (same_artist and title_match) or (same_artist and isrc_candidate):
            candidates.append((left, right))
    return candidates


def _match_recordings(left: LocalAlbumGroup, right: LocalAlbumGroup) -> tuple[int, int]:
    left_open = set(range(len(left.slots)))
    right_open = set(range(len(right.slots)))
    isrc_matches = 0
    for left_index in sorted(left_open, key=lambda index: left.slots[index].sort_key):
        isrc = left.slots[left_index].isrc
        if not isrc:
            continue
        matches = [
            right_index for right_index in right_open
            if right.slots[right_index].isrc == isrc
        ]
        if matches:
            right_index = min(matches, key=lambda index: right.slots[index].sort_key)
            left_open.remove(left_index)
            right_open.remove(right_index)
            isrc_matches += 1

    fallback_matches = 0
    possibilities: list[tuple[int, tuple, int, int]] = []
    for left_index in left_open:
        left_slot = left.slots[left_index]
        for right_index in right_open:
            right_slot = right.slots[right_index]
            la, lt, ld, ln, _ = left_slot.key
            ra, rt, rd, rn, _ = right_slot.key
            if not (la == ra and lt == rt and ln is not None and ln == rn):
                continue
            if not ((ld == rd) or (ld is None and rd is None)):
                continue
            if left_slot.duration is None or right_slot.duration is None:
                continue
            difference = abs(left_slot.duration - right_slot.duration)
            if difference <= 5:
                possibilities.append((difference, (left_slot.sort_key, right_slot.sort_key), left_index, right_index))
    for _, _, left_index, right_index in sorted(possibilities):
        if left_index in left_open and right_index in right_open:
            left_open.remove(left_index)
            right_open.remove(right_index)
            fallback_matches += 1
    return isrc_matches, fallback_matches


def _compatible_date(left: set[object], right: set[object]) -> bool:
    for left_value in left:
        for right_value in right:
            left_text, right_text = str(left_value), str(right_value)
            if left_text == right_text or (
                left_text[:4] == right_text[:4]
                and (len(left_text) == 4 or len(right_text) == 4)
            ):
                return True
    return False


def _conflict(
    left: LocalAlbumGroup,
    right: LocalAlbumGroup,
    field_name: str,
) -> tuple[bool, bool]:
    left_all, right_all = left.values(field_name), right.values(field_name)
    observed = bool(left_all and right_all and left_all.isdisjoint(right_all))
    left_confirmed = left.confirmed_values(field_name)
    right_confirmed = right.confirmed_values(field_name)
    confirmed = bool(left_confirmed and right_confirmed and left_confirmed.isdisjoint(right_confirmed))
    return observed, confirmed


def _vetoes(left: LocalAlbumGroup, right: LocalAlbumGroup) -> tuple[list[Veto], list[str]]:
    vetoes: list[Veto] = []
    contradictions: list[str] = []
    for field_name, code in (
        ("musicbrainz_release_id", "musicbrainz_release_conflict"),
        ("barcode", "barcode_conflict"),
        ("track_total", "track_total_conflict"),
        ("disc_total", "disc_total_conflict"),
    ):
        observed, confirmed = _conflict(left, right, field_name)
        if confirmed:
            vetoes.append(Veto(code, f"Confirmed {field_name} values disagree"))
        elif observed:
            contradictions.append(code)

    left_providers, right_providers = _provider_values(left, confirmed=True), _provider_values(right, confirmed=True)
    if any(namespace == other_namespace and album_id != other_id
           for namespace, album_id in left_providers
           for other_namespace, other_id in right_providers):
        vetoes.append(Veto("provider_release_conflict", "Confirmed provider album identities disagree"))

    left_positions = {(slot.key[2], slot.key[3]): slot for slot in left.slots if slot.key[3] is not None}
    right_positions = {(slot.key[2], slot.key[3]): slot for slot in right.slots if slot.key[3] is not None}
    for position in sorted(left_positions.keys() & right_positions.keys(), key=str):
        left_isrc, right_isrc = left_positions[position].isrc, right_positions[position].isrc
        if left_isrc and right_isrc and left_isrc != right_isrc:
            vetoes.append(Veto(
                "positioned_recording_conflict",
                f"Disc/track {position} has different verified ISRCs",
            ))
            break
    return vetoes, contradictions


def decide_outcome(
    score: int,
    *,
    source_count: int = 0,
    matched: int = 0,
    coverage: float = 0.0,
    direct_identity: bool = False,
    vetoes: Iterable[Veto] = (),
    contradictions: Iterable[str] = (),
    user_decision: str | None = None,
) -> str:
    if tuple(vetoes) or user_decision == "keep_separate":
        return "separate"
    if user_decision == "group_together":
        return "auto_group"
    if tuple(contradictions):
        return "review"
    if score >= 85:
        if direct_identity or (source_count >= 2 and matched >= 3 and coverage >= 0.9):
            return "auto_group"
        return "review"
    return "review" if score >= 60 else "separate"


def assess_pair(
    left: LocalAlbumGroup,
    right: LocalAlbumGroup,
    *,
    user_decision: str | None = None,
    catalog_results: Mapping[str, Mapping[str, object]] | None = None,
    artwork_digests: tuple[set[str], set[str]] | None = None,
    directory_names: tuple[set[str], set[str]] | None = None,
) -> GroupingAssessment:
    evidence: list[EvidenceItem] = []

    def add(code: str, family: str, points: int, sources: Iterable[str], explanation: str) -> None:
        if points > 0:
            evidence.append(EvidenceItem(code, family, points, frozenset(sources), explanation))

    same_mb = bool(left.values("musicbrainz_release_id") & right.values("musicbrainz_release_id"))
    same_provider = bool(_provider_values(left) & _provider_values(right))
    if same_mb:
        add("musicbrainz_release", "identity", 100, {"local_tags"}, "Same MusicBrainz Release ID")
    if same_provider:
        add("provider_release", "identity", 95, {"local_tags"}, "Same provider album identity")
    if left.values("barcode") & right.values("barcode"):
        add("barcode", "identity", 80, {"local_tags"}, "Same barcode")
    if left.values("musicbrainz_release_group_id") & right.values("musicbrainz_release_group_id"):
        add("musicbrainz_release_group", "identity", 20, {"local_tags"}, "Same release group")

    isrc_matches, fallback_matches = _match_recordings(left, right)
    smaller = min(len(left.slots), len(right.slots))
    if smaller:
        add("isrc_recordings", "recording", math.floor(40 * isrc_matches / smaller), {"local_tags"}, "Matching ISRC slots")
        add(
            "fallback_recordings",
            "recording",
            math.floor(25 * fallback_matches / smaller),
            {"local_tags", "decoded_audio"},
            "Matching artist, title, position, and duration slots",
        )

    if left.album_artist and left.album_artist == right.album_artist:
        add("album_artist", "metadata", 6, {"local_tags"}, "Same normalized album artist")
    if compatible_title(left.title, right.title):
        add("album_title", "metadata", 5, {"local_tags"}, "Compatible album title")
    if _compatible_date(left.values("release_date"), right.values("release_date")):
        add("release_date", "metadata", 4, {"local_tags"}, "Compatible release date")
    if left.values("track_total") & right.values("track_total"):
        add("track_total", "metadata", 6, {"local_tags"}, "Same embedded track total")
    if left.values("disc_total") & right.values("disc_total"):
        add("disc_total", "metadata", 4, {"local_tags"}, "Same embedded disc total")

    for source in ("tidal", "musicbrainz"):
        if (catalog_results or {}).get(source, {}).get("same_release") is True:
            add(f"{source}_catalog", "catalog", 10, {source}, f"{source.title()} confirms one release")

    if artwork_digests and artwork_digests[0] & artwork_digests[1]:
        add("artwork", "weak", 3, {"filesystem"}, "Artwork digest sets intersect")
    if directory_names and directory_names[0] & directory_names[1]:
        add("directory", "weak", 2, {"filesystem"}, "Normalized parent directories intersect")

    caps = {"identity": 100, "recording": 55, "metadata": 25, "catalog": 20, "weak": 5}
    family_scores = {
        family: min(cap, sum(item.points for item in evidence if item.family == family))
        for family, cap in caps.items()
    }
    qualifying_sources = frozenset(
        source
        for item in evidence
        if item.family != "weak" and item.points > 0
        for source in item.sources
        if source != "filesystem"
    )
    diversity_bonus = min(15, max(0, len(qualifying_sources) - 1) * 5)
    score = min(100, sum(family_scores.values()) + diversity_bonus)
    vetoes, contradictions = _vetoes(left, right)
    matched = isrc_matches + fallback_matches
    coverage = matched / smaller if smaller else 0.0
    direct_identity = same_mb or same_provider
    outcome = decide_outcome(
        score,
        source_count=len(qualifying_sources),
        matched=matched,
        coverage=coverage,
        direct_identity=direct_identity,
        vetoes=vetoes,
        contradictions=contradictions,
        user_decision=user_decision,
    )
    return GroupingAssessment(
        left.signature,
        right.signature,
        score=score,
        outcome=outcome,
        evidence=evidence,
        family_scores=family_scores,
        diversity_bonus=diversity_bonus,
        vetoes=vetoes,
        contradictions=contradictions,
        isrc_matches=isrc_matches,
        fallback_matches=fallback_matches,
        coverage=coverage,
        qualifying_sources=qualifying_sources,
        user_decision=user_decision,
        user_decision_superseded=bool(vetoes and user_decision == "group_together"),
    )


def accepted_components(
    groups: Iterable[LocalAlbumGroup],
    assessments: Mapping[frozenset[str], GroupingAssessment],
) -> tuple[list[list[LocalAlbumGroup]], set[str]]:
    groups = list(groups)
    by_signature = {group.signature: group for group in groups}
    adjacency = {group.signature: set() for group in groups}
    for pair, assessment in assessments.items():
        if assessment.outcome == "auto_group" and len(pair) == 2:
            left, right = tuple(pair)
            if left in adjacency and right in adjacency:
                adjacency[left].add(right)
                adjacency[right].add(left)

    seen: set[str] = set()
    components: list[list[LocalAlbumGroup]] = []
    review: set[str] = set()
    for signature in sorted(adjacency):
        if signature in seen:
            continue
        stack, component = [signature], set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency[current] - component)
        seen.update(component)
        complete = all(
            assessments.get(frozenset({left, right})) is not None
            and assessments[frozenset({left, right})].outcome == "auto_group"
            for left, right in combinations(component, 2)
        )
        if len(component) > 1 and not complete:
            review.update(component)
            components.extend([[by_signature[item]] for item in sorted(component)])
        else:
            components.append([by_signature[item] for item in sorted(component)])
    return components, review


def card_id(groups: Iterable[LocalAlbumGroup]) -> str:
    return "release:" + _canonical_json_hash(sorted(group.signature for group in groups))


def canonical_title(
    groups: Iterable[LocalAlbumGroup],
    *,
    user_titles: Iterable[str] = (),
    catalog_titles: Iterable[Mapping[str, object]] = (),
) -> str:
    groups = list(groups)
    group_titles = {group.title for group in groups}
    selected = {normalize_text(title) for title in user_titles if title in group_titles}
    if len(selected) == 1:
        normalized = next(iter(selected))
        return min(title for title in group_titles if normalize_text(title) == normalized)

    catalogs = [dict(item) for item in catalog_titles if item.get("title")]
    source_order = {"tidal": 0, "musicbrainz": 1}
    direct = [item for item in catalogs if item.get("direct")]
    if direct:
        return str(min(direct, key=lambda item: (
            source_order.get(str(item.get("source")), 99),
            normalize_text(item["title"]),
            str(item["title"]),
        ))["title"])
    counts = Counter(normalize_text(item["title"]) for item in catalogs)
    agreed = {title for title, count in counts.items() if count >= 2}
    if agreed:
        return str(min(
            (item for item in catalogs if normalize_text(item["title"]) in agreed),
            key=lambda item: (
                source_order.get(str(item.get("source")), 99),
                normalize_text(item["title"]),
                str(item["title"]),
            ),
        )["title"])

    def local_rank(group: LocalAlbumGroup) -> tuple:
        totals = [_integer(value) for value in group.values("track_total")]
        trusted = min((value for value in totals if value), default=None)
        ratio = len(group.slots) / trusted if trusted else -1.0
        return (trusted is not None, ratio, len(group.slots), -len(normalize_text(group.title)))

    best_rank = max(local_rank(group) for group in groups)
    tied = [group.title for group in groups if local_rank(group) == best_rank]
    return min(tied, key=lambda title: (normalize_text(title), title))


def weak_evidence_sets(
    rows: Iterable[dict],
    artwork_loader: Callable[[str], bytes | None],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    digests: set[str] = set()
    directories: set[str] = set()
    for row in rows:
        path = str(row.get("path") or "")
        artwork = artwork_loader(path)
        if artwork:
            digests.add(hashlib.sha256(artwork).hexdigest())
        directory = base_title(Path(path).parent.name)
        if directory:
            directories.add(directory)
    return tuple(sorted(digests)), tuple(sorted(directories))
