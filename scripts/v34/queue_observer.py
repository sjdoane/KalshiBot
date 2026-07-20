"""Read-only V34 KXMLBTOTAL queue observer.

The observer consumes exact receipt-backed V34 feed generations, archives every
consumed pair before inspecting Kalshi, and commits shadow decisions only after
the same generation is visible at cycle end. It has no authenticated client and
rejects every portfolio or order endpoint by construction.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never, cast
from zoneinfo import ZoneInfo

import httpx

from scripts.v34 import decision_commit, feed_lineage, policy
from scripts.v34 import prefix_dependency as prefix

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

KALSHI_BASE: Final = "https://api.elections.kalshi.com/trade-api/v2"
SERIES_TICKER: Final = "KXMLBTOTAL"
EASTERN: Final = ZoneInfo("America/New_York")
HTTP_ATTEMPTS: Final = 2
HTTP_TIMEOUT_SECONDS: Final = 5.0
HTTP_RETRY_SECONDS: Final = 0.25
MAX_HTTP_RESPONSE_BYTES: Final = 8 * 1024 * 1024
MAX_SCHEDULE_DELTA_SECONDS: Final = 4 * 60 * 60
MAX_FEED_AGE_SECONDS: Final = 12.0
SHADOW_CONTRACTS: Final = Decimal("5.00")
MAX_NEW_DECISIONS_PER_CYCLE: Final = 2
WATCH_RETRY_SECONDS: Final = 30.0
MAX_MARKETS: Final = 1000

TEAM_CODES: Final = frozenset(
    {
        "ATH",
        "AZ",
        "ATL",
        "BAL",
        "BOS",
        "CHC",
        "CIN",
        "CLE",
        "COL",
        "CWS",
        "DET",
        "HOU",
        "KC",
        "LAA",
        "LAD",
        "MIA",
        "MIL",
        "MIN",
        "NYM",
        "NYY",
        "PHI",
        "PIT",
        "SD",
        "SEA",
        "SF",
        "STL",
        "TB",
        "TEX",
        "TOR",
        "WSH",
    }
)
MONTHS: Final = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
EVENT_RE: Final = re.compile(
    r"^KXMLBTOTAL-(?P<year>\d{2})(?P<month>[A-Z]{3})(?P<day>\d{2})"
    r"(?P<hhmm>\d{4})(?P<teams>[A-Z]+)$"
)
_ALLOWED_PUBLIC_PATHS: Final = (
    re.compile(r"/markets\Z"),
    re.compile(r"/markets/[A-Z0-9.-]+\Z"),
    re.compile(r"/markets/[A-Z0-9.-]+/orderbook\Z"),
    re.compile(r"/markets/trades\Z"),
)


class QueueObserverFatalError(RuntimeError):
    """A frozen queue invariant failed and the prospective run must stop."""


def _fatal(message: str, *, cause: Exception | None = None) -> Never:
    error = QueueObserverFatalError(message)
    if cause is None:
        raise error
    raise error from cause


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utc(value: object, *, field: str) -> datetime:
    if type(value) is not str:
        _fatal(f"{field} must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        _fatal(f"{field} is not an ISO timestamp", cause=exc)
    if parsed.tzinfo is None:
        _fatal(f"{field} is timezone-naive")
    return parsed.astimezone(UTC)


def _canonical_object(raw: bytes, *, field: str) -> dict[str, object]:
    if type(raw) is not bytes:
        _fatal(f"{field} must be immutable bytes")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fatal(f"{field} is not valid JSON", cause=exc)
    if not isinstance(parsed, dict) or raw != policy.canonical_json_bytes(parsed):
        _fatal(f"{field} is not a canonical object")
    return cast("dict[str, object]", parsed)


def _decode_public_raw(raw: bytes, *, field: str) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > MAX_HTTP_RESPONSE_BYTES:
        _fatal(f"{field} is not bounded immutable bytes")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fatal(f"{field} is not valid JSON", cause=exc)
    if not isinstance(parsed, dict):
        _fatal(f"{field} is not an object")
    return cast("dict[str, object]", parsed)


def _exact_decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        _fatal(f"{field} is not an exact decimal input")
    if isinstance(value, float) and not math.isfinite(value):
        _fatal(f"{field} is not finite")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        _fatal(f"{field} is not decimal", cause=exc)
    if not parsed.is_finite():
        _fatal(f"{field} is not finite")
    return parsed


def _split_team_codes(value: str) -> tuple[str, str] | None:
    candidates = [
        (value[:index], value[index:])
        for index in range(2, len(value) - 1)
        if value[:index] in TEAM_CODES and value[index:] in TEAM_CODES
    ]
    return candidates[0] if len(candidates) == 1 else None


def parse_event_ticker(event_ticker: object) -> tuple[datetime, str, str] | None:
    """Return the frozen Eastern start time and exact away and home codes."""

    if type(event_ticker) is not str:
        return None
    match = EVENT_RE.fullmatch(event_ticker)
    if match is None:
        return None
    teams = _split_team_codes(match.group("teams"))
    if teams is None:
        return None
    hhmm = match.group("hhmm")
    try:
        scheduled = datetime(
            2000 + int(match.group("year")),
            MONTHS[match.group("month")],
            int(match.group("day")),
            int(hhmm[:2]),
            int(hhmm[2:]),
            tzinfo=EASTERN,
        )
    except (KeyError, ValueError):
        return None
    return scheduled, teams[0], teams[1]


@dataclass(frozen=True, slots=True)
class ScheduleGame:
    game_pk: int
    scheduled_at: datetime
    away_code: str
    home_code: str
    detailed_state: str
    status_reason: str | None


@dataclass(frozen=True, slots=True)
class MarketRow:
    game_pk: int
    event_ticker: str
    ticker: str
    threshold: Decimal
    raw: dict[str, object]


@dataclass(frozen=True, slots=True)
class MappingAssignment:
    event_ticker: str
    game_pk: int
    identity_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event_ticker": self.event_ticker,
            "game_pk": self.game_pk,
            "identity_sha256": self.identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class MappingExclusion:
    event_ticker: str
    reason: str
    minimum_delta_seconds: str
    tied_candidates: tuple[dict[str, object], ...]
    identity_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event_ticker": self.event_ticker,
            "identity_sha256": self.identity_sha256,
            "minimum_delta_seconds": self.minimum_delta_seconds,
            "reason": self.reason,
            "tied_candidates": [dict(row) for row in self.tied_candidates],
        }


@dataclass(frozen=True, slots=True)
class MarketUniverse:
    markets: tuple[MarketRow, ...]
    assignments: tuple[MappingAssignment, ...]
    exclusions: tuple[MappingExclusion, ...]
    open_event_tickers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrderbookView:
    best_yes: Decimal | None
    best_no: Decimal | None
    yes_ask: Decimal
    yes_depth_99: Decimal


@dataclass(frozen=True, slots=True)
class EligibleContext:
    basis: prefix.TriggerBasis
    observed_at: datetime
    abstract_state: str
    detailed_state: str
    official_current_total: int
    completed_plays: dict[str, object]


@dataclass(frozen=True, slots=True)
class Candidate:
    market: MarketRow
    eligible: EligibleContext
    prior_order: dict[str, object] | None


def _status_reason(game: Mapping[str, object]) -> str | None:
    status = game.get("status")
    if not isinstance(status, dict):
        _fatal("schedule game status is missing")
    detailed = status.get("detailedState")
    if type(detailed) is not str or not detailed:
        _fatal("schedule detailed state is missing")
    lowered = detailed.casefold()
    if any(token in lowered for token in ("postpon", "suspend", "cancel", "resched")):
        return f"prohibited_status:{lowered}"
    if any(
        game.get(field)
        for field in (
            "rescheduledFrom",
            "rescheduledFromDate",
            "rescheduleDate",
            "rescheduledGameDate",
        )
    ):
        return "rescheduled_game"
    return None


def load_schedule_snapshot(
    raw: bytes,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
) -> tuple[ScheduleGame, ...]:
    """Validate the feed-owned schedule snapshot and recover exact team bindings."""

    anchor = policy.reverify_feed_launch_anchor(feed_anchor)
    snapshot = _canonical_object(raw, field="schedule snapshot")
    required = {
        "fetched_at",
        "games",
        "horizon_hard_stop_at",
        "horizon_start_at",
        "kind",
        "launch_nonce",
        "query_end_date",
        "query_start_date",
        "raw_payload_base64",
        "raw_payload_sha256",
        "run_signature",
    }
    if set(snapshot) != required:
        _fatal("schedule snapshot keys differ")
    if (
        snapshot.get("kind") != "v34_frozen_mlb_schedule"
        or snapshot.get("launch_nonce") != anchor.provenance["launch_nonce"]
        or snapshot.get("run_signature") != policy.FEED_RUN_SIGNATURE
    ):
        _fatal("schedule snapshot provenance differs")
    _utc(snapshot.get("fetched_at"), field="schedule.fetched_at")
    start = _utc(snapshot.get("horizon_start_at"), field="schedule.horizon_start_at")
    hard_stop = _utc(
        snapshot.get("horizon_hard_stop_at"), field="schedule.horizon_hard_stop_at"
    )
    if hard_stop <= start or (hard_stop - start).total_seconds() > 24 * 60 * 60:
        _fatal("schedule horizon exceeds the frozen maximum")
    encoded = snapshot.get("raw_payload_base64")
    if type(encoded) is not str:
        _fatal("schedule raw payload encoding is missing")
    try:
        payload_raw = base64.b64decode(encoded, validate=True)
        payload = json.loads(payload_raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fatal("schedule raw payload is invalid", cause=exc)
    if _sha256(payload_raw) != snapshot.get("raw_payload_sha256"):
        _fatal("schedule raw payload hash differs")
    if not isinstance(payload, dict) or not isinstance(payload.get("dates"), list):
        _fatal("schedule raw payload root is malformed")
    frozen_rows = snapshot.get("games")
    if not isinstance(frozen_rows, list) or not frozen_rows:
        _fatal("schedule frozen game list is empty")
    frozen: dict[int, str] = {}
    for row in frozen_rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"game_pk", "scheduled_at"}
            or type(row.get("game_pk")) is not int
            or cast("int", row["game_pk"]) < 1
            or type(row.get("scheduled_at")) is not str
        ):
            _fatal("schedule frozen game row is malformed")
        game_pk = cast("int", row["game_pk"])
        if game_pk in frozen:
            _fatal("schedule frozen game list has a duplicate")
        frozen[game_pk] = cast("str", row["scheduled_at"])

    observed: dict[int, ScheduleGame] = {}
    for day in cast("list[object]", payload["dates"]):
        if not isinstance(day, dict) or not isinstance(day.get("games"), list):
            _fatal("schedule raw day is malformed")
        for raw_game in cast("list[object]", day["games"]):
            if not isinstance(raw_game, dict) or type(raw_game.get("gamePk")) is not int:
                _fatal("schedule raw game is malformed")
            game_pk = cast("int", raw_game["gamePk"])
            if game_pk not in frozen:
                continue
            scheduled = _utc(raw_game.get("gameDate"), field="schedule.gameDate")
            if scheduled.isoformat() != frozen[game_pk] or not start <= scheduled < hard_stop:
                _fatal("schedule raw game differs from the frozen horizon")
            teams = raw_game.get("teams")
            status = raw_game.get("status")
            if not isinstance(teams, dict) or not isinstance(status, dict):
                _fatal("schedule team or status root is missing")
            codes: dict[str, str] = {}
            for side in ("away", "home"):
                side_row = teams.get(side)
                team = side_row.get("team") if isinstance(side_row, dict) else None
                code = team.get("abbreviation") if isinstance(team, dict) else None
                if type(code) is not str or code not in TEAM_CODES:
                    _fatal("schedule team abbreviation is unsupported")
                codes[side] = code
            detailed = status.get("detailedState")
            if type(detailed) is not str or not detailed:
                _fatal("schedule detailed state is missing")
            candidate = ScheduleGame(
                game_pk=game_pk,
                scheduled_at=scheduled,
                away_code=codes["away"],
                home_code=codes["home"],
                detailed_state=detailed,
                status_reason=_status_reason(cast("Mapping[str, object]", raw_game)),
            )
            if game_pk in observed and observed[game_pk] != candidate:
                _fatal("schedule raw payload duplicates a game differently")
            observed[game_pk] = candidate
    if set(observed) != set(frozen):
        _fatal("schedule raw payload does not cover every frozen game")
    return tuple(sorted(observed.values(), key=lambda row: (row.scheduled_at, row.game_pk)))


def _event_candidates(
    event_ticker: str,
    games: Sequence[ScheduleGame],
) -> tuple[tuple[float, ScheduleGame], ...]:
    parsed = parse_event_ticker(event_ticker)
    if parsed is None:
        return ()
    expected, away, home = parsed
    expected_utc = expected.astimezone(UTC)
    return tuple(
        sorted(
            (
                (abs((game.scheduled_at - expected_utc).total_seconds()), game)
                for game in games
                if game.away_code == away and game.home_code == home
            ),
            key=lambda row: (row[0], row[1].game_pk),
        )
    )


def match_event_to_game(
    event_ticker: str,
    games: Sequence[ScheduleGame],
) -> tuple[int | None, str]:
    """Apply the unchanged four-hour team and time mapping policy."""

    if parse_event_ticker(event_ticker) is None:
        return None, "ticker_parse_failed"
    candidates = _event_candidates(event_ticker, games)
    if not candidates:
        return None, "no_team_date_match"
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None, "ambiguous_time_match"
    delta, game = candidates[0]
    if delta > MAX_SCHEDULE_DELTA_SECONDS:
        return None, "time_delta_exceeded"
    if game.status_reason is not None:
        return None, game.status_reason
    return game.game_pk, "matched"


def _mapping_assignment(event_ticker: str, game_pk: int) -> MappingAssignment:
    identity = policy.canonical_sha256(
        {"event_ticker": event_ticker, "game_pk": game_pk}
    )
    return MappingAssignment(
        event_ticker=event_ticker,
        game_pk=game_pk,
        identity_sha256=identity,
    )


def _mapping_exclusion(
    event_ticker: str,
    games: Sequence[ScheduleGame],
) -> MappingExclusion:
    candidates = _event_candidates(event_ticker, games)
    if len(candidates) < 2 or candidates[0][0] != candidates[1][0]:
        _fatal("ambiguous mapping exclusion is not an exact tie")
    minimum_delta = candidates[0][0]
    if minimum_delta > MAX_SCHEDULE_DELTA_SECONDS:
        _fatal("ambiguous mapping tie exceeds the frozen four-hour bound")
    tied = tuple(row for row in candidates if row[0] == minimum_delta)
    evidence: list[dict[str, object]] = []
    for delta, game in tied:
        if game.status_reason not in {None, "rescheduled_game"}:
            _fatal("ambiguous mapping tie contains a prohibited game status")
        evidence.append(
            {
                "delta_seconds": format(Decimal(str(delta)), "f"),
                "game_pk": game.game_pk,
                "scheduled_at": game.scheduled_at.astimezone(UTC).isoformat(),
                "status_reason": game.status_reason,
            }
        )
    evidence.sort(key=lambda row: cast("int", row["game_pk"]))
    identity_input = {
        "event_ticker": event_ticker,
        "minimum_delta_seconds": format(Decimal(str(minimum_delta)), "f"),
        "reason": "ambiguous_time_match",
        "tied_candidates": evidence,
    }
    return MappingExclusion(
        event_ticker=event_ticker,
        reason="ambiguous_time_match",
        minimum_delta_seconds=cast("str", identity_input["minimum_delta_seconds"]),
        tied_candidates=tuple(evidence),
        identity_sha256=policy.canonical_sha256(identity_input),
    )


def parse_market_universe(
    payload: Mapping[str, object],
    *,
    games: Sequence[ScheduleGame],
) -> MarketUniverse:
    """Validate and map every open in-horizon KXMLBTOTAL market."""

    rows = payload.get("markets")
    cursor = payload.get("cursor")
    if not isinstance(rows, list) or len(rows) > MAX_MARKETS:
        _fatal("public market universe is missing or exceeds its bound")
    if cursor not in (None, ""):
        _fatal("public market universe was not drained in one bounded page")
    horizon_dates = {game.scheduled_at.astimezone(EASTERN).date() for game in games}
    mapping: dict[str, int] = {}
    game_to_event: dict[int, str] = {}
    markets: dict[str, MarketRow] = {}
    assignments: dict[str, MappingAssignment] = {}
    exclusions: dict[str, MappingExclusion] = {}
    open_events: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            _fatal("public market row is malformed")
        event_ticker = raw.get("event_ticker")
        parsed = parse_event_ticker(event_ticker)
        if parsed is None:
            _fatal("KXMLBTOTAL event ticker is unparseable")
        if parsed[0].date() not in horizon_dates:
            continue
        assert isinstance(event_ticker, str)
        open_events.add(event_ticker)
        if event_ticker not in mapping and event_ticker not in exclusions:
            game_pk, reason = match_event_to_game(event_ticker, games)
            if game_pk is None:
                if reason == "ambiguous_time_match":
                    exclusions[event_ticker] = _mapping_exclusion(event_ticker, games)
                    continue
                _fatal(f"in-horizon market mapping failed: {event_ticker}: {reason}")
            prior_event = game_to_event.get(game_pk)
            if prior_event is not None and prior_event != event_ticker:
                _fatal("two Kalshi events map to one MLB game")
            mapping[event_ticker] = game_pk
            game_to_event[game_pk] = event_ticker
            assignments[event_ticker] = _mapping_assignment(event_ticker, game_pk)
        game_pk = mapping.get(event_ticker)
        if game_pk is None:
            continue
        ticker = raw.get("ticker")
        if type(ticker) is not str or not ticker.startswith(f"{event_ticker}-"):
            _fatal("market ticker does not bind its event")
        if raw.get("status") not in {"active", "open"}:
            _fatal("open market page contains a prohibited status")
        threshold = _exact_decimal(raw.get("floor_strike"), field="market.floor_strike")
        if threshold < 0 or threshold % 1 != Decimal("0.5"):
            _fatal("market threshold is not a nonnegative half-run")
        suffix = ticker.rsplit("-", 1)[-1]
        expected_suffix = threshold + Decimal("0.5")
        if expected_suffix != expected_suffix.to_integral_value() or suffix != str(
            int(expected_suffix)
        ):
            _fatal("market ticker suffix differs from its threshold")
        if ticker in markets:
            _fatal("public market universe contains a duplicate ticker")
        markets[ticker] = MarketRow(
            game_pk=game_pk,
            event_ticker=event_ticker,
            ticker=ticker,
            threshold=threshold,
            raw=cast("dict[str, object]", raw.copy()),
        )
    if not markets:
        _fatal("public market universe has no in-horizon mapped market")
    if set(assignments) & set(exclusions):
        _fatal("mapping evidence assigns and excludes the same event")
    if set(assignments) | set(exclusions) != open_events:
        _fatal("mapping evidence does not cover every open in-horizon event")
    return MarketUniverse(
        markets=tuple(
            sorted(markets.values(), key=lambda row: (row.game_pk, row.threshold, row.ticker))
        ),
        assignments=tuple(assignments[key] for key in sorted(assignments)),
        exclusions=tuple(exclusions[key] for key in sorted(exclusions)),
        open_event_tickers=tuple(sorted(open_events)),
    )


def _validated_assignment_identity(row: MappingAssignment) -> tuple[str, str]:
    if (
        type(row.event_ticker) is not str
        or parse_event_ticker(row.event_ticker) is None
        or type(row.game_pk) is not int
        or row.game_pk < 1
    ):
        _fatal("mapping assignment fields are malformed")
    expected = policy.canonical_sha256(
        {"event_ticker": row.event_ticker, "game_pk": row.game_pk}
    )
    if row.identity_sha256 != expected:
        _fatal("mapping assignment identity hash differs")
    return "assignment", expected


def _validated_exclusion_identity(row: MappingExclusion) -> tuple[str, str]:
    if (
        type(row.event_ticker) is not str
        or parse_event_ticker(row.event_ticker) is None
        or row.reason != "ambiguous_time_match"
    ):
        _fatal("mapping exclusion fields are malformed")
    minimum_delta = _exact_decimal(
        row.minimum_delta_seconds,
        field="mapping exclusion minimum delta",
    )
    if not Decimal("0") <= minimum_delta <= Decimal(MAX_SCHEDULE_DELTA_SECONDS):
        _fatal("mapping exclusion minimum delta exceeds the frozen bound")
    if len(row.tied_candidates) < 2:
        _fatal("mapping exclusion does not contain an exact tie")
    prior_game_pk = 0
    evidence: list[dict[str, object]] = []
    for candidate in row.tied_candidates:
        if set(candidate) != {
            "delta_seconds",
            "game_pk",
            "scheduled_at",
            "status_reason",
        }:
            _fatal("mapping exclusion candidate keys differ")
        game_pk = candidate.get("game_pk")
        delta = _exact_decimal(
            candidate.get("delta_seconds"),
            field="mapping exclusion candidate delta",
        )
        status_reason = candidate.get("status_reason")
        if (
            type(game_pk) is not int
            or game_pk <= prior_game_pk
            or delta != minimum_delta
            or status_reason not in {None, "rescheduled_game"}
        ):
            _fatal("mapping exclusion candidate differs from the frozen tie")
        scheduled = _utc(
            candidate.get("scheduled_at"),
            field="mapping exclusion candidate scheduled_at",
        )
        prior_game_pk = game_pk
        evidence.append(
            {
                "delta_seconds": format(delta, "f"),
                "game_pk": game_pk,
                "scheduled_at": scheduled.isoformat(),
                "status_reason": status_reason,
            }
        )
    identity_input = {
        "event_ticker": row.event_ticker,
        "minimum_delta_seconds": format(minimum_delta, "f"),
        "reason": row.reason,
        "tied_candidates": evidence,
    }
    expected = policy.canonical_sha256(identity_input)
    if row.identity_sha256 != expected:
        _fatal("mapping exclusion identity hash differs")
    return "exclusion", expected


def validate_mapping_continuity(
    cumulative_identities: Mapping[str, tuple[str, str]] | None,
    current: MarketUniverse,
) -> dict[str, tuple[str, str]]:
    """Return a launch-long mapping ledger that never forgets an event."""

    retained = {} if cumulative_identities is None else dict(cumulative_identities)
    for event_ticker, identity in retained.items():
        if (
            type(event_ticker) is not str
            or parse_event_ticker(event_ticker) is None
            or not isinstance(identity, tuple)
            or len(identity) != 2
            or identity[0] not in {"assignment", "exclusion"}
            or type(identity[1]) is not str
        ):
            _fatal("cumulative mapping identity ledger is malformed")
        try:
            policy.validate_sha256(
                identity[1],
                field=f"cumulative mapping identity[{event_ticker}]",
            )
        except ValueError as exc:
            _fatal("cumulative mapping identity ledger is malformed", cause=exc)
    observed: dict[str, tuple[str, str]] = {}
    for assignment in current.assignments:
        if assignment.event_ticker in observed:
            _fatal("mapping continuity input repeats an event")
        observed[assignment.event_ticker] = _validated_assignment_identity(assignment)
    for exclusion in current.exclusions:
        if exclusion.event_ticker in observed:
            _fatal("mapping continuity input overlaps assignment and exclusion")
        observed[exclusion.event_ticker] = _validated_exclusion_identity(exclusion)
    if set(observed) != set(current.open_event_tickers):
        _fatal("mapping continuity input lacks open-event evidence")
    for event_ticker, identity in observed.items():
        prior = retained.get(event_ticker)
        if prior is not None and prior != identity:
            _fatal(f"mapping identity changed during the launch: {event_ticker}")
        retained[event_ticker] = identity
    return retained


def parse_orderbook(payload: Mapping[str, object]) -> OrderbookView:
    """Return the executable YES ask and displayed depth ahead at 99 cents."""

    book = payload.get("orderbook_fp")
    if not isinstance(book, dict):
        _fatal("orderbook_fp is missing")

    def levels(side: str) -> tuple[tuple[Decimal, Decimal], ...]:
        values = book.get(side)
        if not isinstance(values, list):
            _fatal(f"orderbook {side} is missing")
        observed: dict[Decimal, Decimal] = {}
        for level in values:
            if not isinstance(level, list) or len(level) != 2:
                _fatal(f"orderbook {side} level is malformed")
            price = _exact_decimal(level[0], field=f"orderbook.{side}.price")
            count = _exact_decimal(level[1], field=f"orderbook.{side}.count")
            if not Decimal("0") < price < Decimal("1") or count <= 0:
                _fatal(f"orderbook {side} level is outside bounds")
            if price in observed:
                _fatal(f"orderbook {side} repeats a price level")
            observed[price] = count
        return tuple(sorted(observed.items()))

    yes = levels("yes_dollars")
    no = levels("no_dollars")
    best_yes = max((price for price, _count in yes), default=None)
    best_no = max((price for price, _count in no), default=None)
    yes_ask = Decimal("1") - best_no if best_no is not None else Decimal("1")
    depth_99 = sum(
        (count for price, count in yes if price == Decimal("0.9900")),
        start=Decimal("0"),
    )
    return OrderbookView(
        best_yes=best_yes,
        best_no=best_no,
        yes_ask=yes_ask,
        yes_depth_99=depth_99,
    )


async def _bounded_response_bytes(response: httpx.Response) -> bytes:
    claimed_raw = response.headers.get("content-length")
    if claimed_raw is not None:
        try:
            claimed = int(claimed_raw)
        except ValueError as exc:
            _fatal("public HTTP Content-Length is malformed", cause=exc)
        if claimed < 0 or claimed > MAX_HTTP_RESPONSE_BYTES:
            _fatal("public HTTP response exceeds its byte bound")
    value = bytearray()
    async for chunk in response.aiter_bytes():
        value.extend(chunk)
        if len(value) > MAX_HTTP_RESPONSE_BYTES:
            _fatal("public HTTP response exceeds its byte bound")
    return bytes(value)


def _validate_public_path(path: str) -> None:
    if type(path) is not str or not any(pattern.fullmatch(path) for pattern in _ALLOWED_PUBLIC_PATHS):
        _fatal("public HTTP path is outside the frozen read-only allowlist")
    lowered = path.casefold()
    if "portfolio" in lowered or "order" in lowered and "orderbook" not in lowered:
        _fatal("public HTTP path could address money or orders")


async def bounded_public_get_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: Mapping[str, str | int] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[dict[str, object], bytes]:
    """GET one allowlisted public payload with the frozen total attempt deadline."""

    if not isinstance(client, httpx.AsyncClient):
        _fatal("public HTTP client type is invalid")
    _validate_public_path(path)
    last_error: Exception | None = None
    for attempt in range(HTTP_ATTEMPTS):
        try:
            async with asyncio.timeout(HTTP_TIMEOUT_SECONDS):
                async with client.stream(
                    "GET",
                    KALSHI_BASE + path,
                    params=params,
                    timeout=None,
                ) as response:
                    response.raise_for_status()
                    raw = await _bounded_response_bytes(response)
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                _fatal("public HTTP payload is not an object")
            return cast("dict[str, object]", parsed), raw
        except (
            TimeoutError,
            httpx.HTTPError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            QueueObserverFatalError,
        ) as exc:
            last_error = exc
        if attempt + 1 < HTTP_ATTEMPTS:
            await sleep(HTTP_RETRY_SECONDS)
    assert last_error is not None
    _fatal("public HTTP request exhausted its frozen attempts", cause=last_error)


def feed_eligible_contexts(
    archived: decision_commit.ArchivedFeedPair,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
    now: datetime,
) -> dict[int, tuple[EligibleContext, ...]]:
    """Rebuild every currently valid eligible trigger from one archived pair."""

    archived.validate(feed_anchor, queue_anchor)
    if now.tzinfo is None:
        _fatal("queue feed validation time is timezone-naive")
    summary = _canonical_object(archived.summary_bytes, field="archived feed summary")
    if summary.get("kind") != "v34_feed_generation":
        _fatal("archived feed summary kind differs")
    game_states = summary.get("game_states")
    lifecycle_states = summary.get("lifecycle_states")
    if not isinstance(game_states, dict) or not isinstance(lifecycle_states, dict):
        _fatal("archived feed summary state maps are missing")
    if set(game_states) != set(lifecycle_states) or not game_states:
        _fatal("archived feed summary state populations differ")
    result: dict[int, tuple[EligibleContext, ...]] = {}
    for game_key in sorted(game_states):
        if (
            type(game_key) is not str
            or not game_key.isdigit()
            or str(int(game_key)) != game_key
            or int(game_key) < 1
        ):
            _fatal("archived feed summary game key is noncanonical")
        state_row = game_states[game_key]
        lifecycle_row = lifecycle_states[game_key]
        if not isinstance(state_row, dict) or not isinstance(lifecycle_row, dict):
            _fatal("archived feed summary game state is malformed")
        game_pk = int(game_key)
        try:
            lifecycle = feed_lineage.deserialize_game_state(
                policy.canonical_json_bytes(lifecycle_row)
            )
        except (TypeError, ValueError, feed_lineage.FeedLineageFatalError) as exc:
            _fatal("archived lifecycle state is invalid", cause=exc)
        completed = state_row.get("completed_plays")
        observed_at = _utc(state_row.get("observed_at"), field="game.observed_at")
        total = state_row.get("official_current_total")
        abstract = state_row.get("abstract_state")
        detailed = state_row.get("detailed_state")
        if (
            lifecycle.game_pk != game_pk
            or state_row.get("game_pk") != game_pk
            or state_row.get("generation_id") != archived.generation_id
            or not isinstance(completed, dict)
            or type(total) is not int
            or total < 0
            or type(abstract) is not str
            or type(detailed) is not str
            or lifecycle.last_completed_plays_bytes != policy.canonical_json_bytes(completed)
            or lifecycle.last_official_current_total != total
            or lifecycle.last_abstract_state != abstract
            or lifecycle.last_detailed_state != detailed
            or _utc(lifecycle.last_observed_at, field="lifecycle.observed_at") != observed_at
        ):
            _fatal("archived game state differs from its lifecycle state")
        age = (now.astimezone(UTC) - observed_at).total_seconds()
        if age < 0:
            _fatal("archived feed game is future-dated at queue decision time")
        fresh = abstract == "Final" or age <= MAX_FEED_AGE_SECONDS
        if not fresh:
            _fatal("archived feed game is stale at queue decision time")
        contexts: list[EligibleContext] = []
        for eligible in lifecycle.eligible:
            basis = eligible.basis
            try:
                prefix.revalidate_trigger_basis(
                    basis,
                    cast("Mapping[str, object]", completed),
                    official_current_total=total,
                    abstract_state=abstract,
                    detailed_state=detailed,
                    observed_at=observed_at,
                )
            except (TypeError, ValueError) as exc:
                _fatal("eligible trigger failed queue reconstruction", cause=exc)
            contexts.append(
                EligibleContext(
                    basis=basis,
                    observed_at=observed_at,
                    abstract_state=abstract,
                    detailed_state=detailed,
                    official_current_total=total,
                    completed_plays=cast("dict[str, object]", completed.copy()),
                )
            )
        result[game_pk] = tuple(
            sorted(contexts, key=lambda row: (row.basis.eligible_at, row.basis.trigger_at_bat_index))
        )
    return result


def select_candidates(
    markets: Sequence[MarketRow],
    eligibility: Mapping[int, Sequence[EligibleContext]],
    state: Mapping[str, object],
    *,
    now: datetime,
) -> tuple[Candidate, ...]:
    """Choose at most two deterministic candidates with game diversity first."""

    if now.tzinfo is None:
        _fatal("candidate selection time is timezone-naive")
    orders = state.get("orders")
    skip_keys = state.get("skip_keys")
    if not isinstance(orders, dict) or not isinstance(skip_keys, list):
        _fatal("queue state collections are malformed")
    options: list[Candidate] = []
    for market in markets:
        prior = orders.get(market.ticker)
        if prior is not None:
            if not isinstance(prior, dict) or prior.get("ticker") != market.ticker:
                _fatal("queue state order identity differs")
            status = prior.get("status")
            if status != "watching":
                continue
            last_observed = _utc(prior.get("last_observed_at"), field="order.last_observed_at")
            if (now.astimezone(UTC) - last_observed).total_seconds() < WATCH_RETRY_SECONDS:
                continue
        if market.ticker in skip_keys:
            continue
        eligible_rows = [
            row
            for row in eligibility.get(market.game_pk, ())
            if prefix.crossing_holds(row.basis, market.threshold)
            and _utc(row.basis.eligible_at, field="basis.eligible_at") <= now.astimezone(UTC)
        ]
        if not eligible_rows:
            continue
        basis = min(
            eligible_rows,
            key=lambda row: (row.basis.eligible_at, row.basis.trigger_at_bat_index),
        )
        options.append(
            Candidate(
                market=market,
                eligible=basis,
                prior_order=cast("dict[str, object] | None", prior),
            )
        )
    options.sort(
        key=lambda row: (
            row.eligible.basis.eligible_at,
            row.market.game_pk,
            row.market.threshold,
            row.market.ticker,
        )
    )
    selected: list[Candidate] = []
    used_games: set[int] = set()
    for option in options:
        if option.market.game_pk in used_games:
            continue
        selected.append(option)
        used_games.add(option.market.game_pk)
        if len(selected) == MAX_NEW_DECISIONS_PER_CYCLE:
            return tuple(selected)
    for option in options:
        if option in selected:
            continue
        selected.append(option)
        if len(selected) == MAX_NEW_DECISIONS_PER_CYCLE:
            break
    return tuple(selected)


def build_staged_decision(
    candidate: Candidate,
    *,
    market_payload: Mapping[str, object],
    market_raw: bytes,
    orderbook_payload: Mapping[str, object],
    orderbook_raw: bytes,
    observed_at: datetime,
) -> decision_commit.StagedDecision:
    """Freeze one watcher or five-contract 99-cent shadow submission."""

    if observed_at.tzinfo is None:
        _fatal("market observation time is timezone-naive")
    decoded_market_payload = _decode_public_raw(
        market_raw,
        field="exact market raw payload",
    )
    decoded_orderbook_payload = _decode_public_raw(
        orderbook_raw,
        field="exact orderbook raw payload",
    )
    if decoded_market_payload != dict(market_payload):
        _fatal("exact market raw bytes differ from the supplied payload")
    if decoded_orderbook_payload != dict(orderbook_payload):
        _fatal("exact orderbook raw bytes differ from the supplied payload")
    market = decoded_market_payload.get("market")
    if not isinstance(market, dict) or market.get("ticker") != candidate.market.ticker:
        _fatal("exact market payload identity differs")
    if market.get("event_ticker") != candidate.market.event_ticker:
        _fatal("exact market event identity differs")
    if market.get("status") not in {"active", "open"}:
        _fatal("exact market is not open")
    threshold = _exact_decimal(market.get("floor_strike"), field="exact market threshold")
    if threshold != candidate.market.threshold:
        _fatal("exact market threshold differs from universe")
    view = parse_orderbook(decoded_orderbook_payload)
    basis = candidate.eligible.basis
    status = "resting" if view.yes_ask == Decimal("1") else "watching"
    decision_kind = "submit" if status == "resting" else "skip"
    order = {
        "basis": basis.to_dict(),
        "best_no": None if view.best_no is None else str(view.best_no),
        "best_yes": None if view.best_yes is None else str(view.best_yes),
        "contracts": str(SHADOW_CONTRACTS),
        "depth_ahead": str(view.yes_depth_99),
        "event_ticker": candidate.market.event_ticker,
        "game_pk": candidate.market.game_pk,
        "last_observed_at": observed_at.astimezone(UTC).isoformat(),
        "market_sha256": _sha256(market_raw),
        "orderbook_sha256": _sha256(orderbook_raw),
        "status": status,
        "submitted_at": (
            observed_at.astimezone(UTC).isoformat() if status == "resting" else None
        ),
        "threshold": str(candidate.market.threshold),
        "ticker": candidate.market.ticker,
        "yes_ask": str(view.yes_ask),
    }
    return decision_commit.StagedDecision(
        decision_kind=decision_kind,
        decision_key=f"{candidate.market.ticker}:{basis.trigger_play_identity}",
        market_ticker=candidate.market.ticker,
        threshold=str(candidate.market.threshold),
        game_pk=candidate.market.game_pk,
        trigger_at_bat_index=basis.trigger_at_bat_index,
        trigger_play_identity=basis.trigger_play_identity,
        ordered_prefix_fingerprint=basis.ordered_prefix_fingerprint,
        pre_total=basis.pre_total,
        post_total=basis.post_total,
        run_delta=basis.run_delta,
        t_seen=basis.t_seen,
        eligible_at=basis.eligible_at,
        mutations=(
            {
                "operation": "upsert_order",
                "key": candidate.market.ticker,
                "value": order,
            },
        ),
        evidence={
            "decision_observed_at": observed_at.astimezone(UTC).isoformat(),
            "market_payload": dict(market),
            "market_raw_base64": base64.b64encode(market_raw).decode("ascii"),
            "market_sha256": _sha256(market_raw),
            "orderbook_payload": decoded_orderbook_payload,
            "orderbook_raw_base64": base64.b64encode(orderbook_raw).decode("ascii"),
            "orderbook_sha256": _sha256(orderbook_raw),
            "shadow_price": "0.9900",
        },
    )


def revalidate_staged_end(
    archived: decision_commit.ArchivedFeedPair,
    staged: decision_commit.StagedDecision,
    *,
    feed_anchor: policy.FeedLaunchAnchor,
    queue_anchor: policy.QueueLaunchAnchor,
    now: datetime,
) -> decision_commit.EndValidationProof:
    """Prove the staged prefix, crossing, eligibility, and freshness at cycle end."""

    contexts = feed_eligible_contexts(
        archived,
        feed_anchor=feed_anchor,
        queue_anchor=queue_anchor,
        now=now,
    )
    exact = [
        row
        for row in contexts.get(staged.game_pk, ())
        if row.basis.trigger_play_identity == staged.trigger_play_identity
        and row.basis.ordered_prefix_fingerprint == staged.ordered_prefix_fingerprint
        and row.basis.trigger_at_bat_index == staged.trigger_at_bat_index
    ]
    if len(exact) != 1:
        _fatal("staged trigger is not uniquely eligible at cycle end")
    row = exact[0]
    basis = row.basis
    expected = (
        basis.pre_total == staged.pre_total
        and basis.post_total == staged.post_total
        and basis.run_delta == staged.run_delta
        and basis.t_seen == staged.t_seen
        and basis.eligible_at == staged.eligible_at
    )
    if not expected or not prefix.crossing_holds(basis, staged.threshold):
        _fatal("staged trigger or crossing differs at cycle end")
    return decision_commit.EndValidationProof(
        feed_generation_id=archived.generation_id,
        feed_summary_sha256=archived.summary_sha256,
        market_ticker=staged.market_ticker,
        threshold=staged.threshold,
        game_pk=staged.game_pk,
        trigger_at_bat_index=staged.trigger_at_bat_index,
        trigger_play_identity=staged.trigger_play_identity,
        ordered_prefix_fingerprint=staged.ordered_prefix_fingerprint,
        pre_total=staged.pre_total,
        post_total=staged.post_total,
        run_delta=staged.run_delta,
        t_seen=staged.t_seen,
        eligible_at=staged.eligible_at,
        crossing_valid=True,
        eligibility_valid=True,
        freshness_valid=True,
    )


async def fetch_market_universe(
    client: httpx.AsyncClient,
    *,
    games: Sequence[ScheduleGame],
) -> tuple[MarketUniverse, bytes]:
    payload, raw = await bounded_public_get_json(
        client,
        "/markets",
        params={"limit": MAX_MARKETS, "series_ticker": SERIES_TICKER, "status": "open"},
    )
    return parse_market_universe(payload, games=games), raw


async def fetch_exact_candidate(
    client: httpx.AsyncClient,
    candidate: Candidate,
) -> tuple[dict[str, object], bytes, dict[str, object], bytes]:
    ticker = candidate.market.ticker
    market, market_raw = await bounded_public_get_json(client, f"/markets/{ticker}")
    orderbook, orderbook_raw = await bounded_public_get_json(
        client,
        f"/markets/{ticker}/orderbook",
        params={"depth": 100},
    )
    return market, market_raw, orderbook, orderbook_raw


def source_sha256() -> str:
    return _sha256(Path(__file__).read_bytes())
