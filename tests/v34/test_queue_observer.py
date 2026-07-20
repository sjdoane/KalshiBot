from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from scripts.v34 import decision_commit, feed_lifecycle, feed_lineage, policy
from scripts.v34 import queue_observer as queue

if TYPE_CHECKING:
    from pathlib import Path

BASE = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)
GAME_PK = 825100


def feed_anchor() -> policy.FeedLaunchAnchor:
    source_hashes = {
        source_name: hashlib.sha256(
            (policy.REPOSITORY_ROOT / source_name).read_bytes()
        ).hexdigest()
        for source_name in sorted(policy.REQUIRED_LAUNCH_SOURCES)
    }
    return policy.verify_feed_launch_manifest_bytes(
        policy.canonical_json_bytes(
            {
                "created_at": BASE.isoformat(),
                "launch_nonce": "queue-feed-test-nonce",
                "manifest_kind": "v34_feed_launch",
                "output_root": policy.FEED_OUTPUT_ROOT,
                "policy_sha256": policy.POLICY_CANONICAL_SHA256,
                "run_signature": policy.FEED_RUN_SIGNATURE,
                "schema_version": policy.FEED_SCHEMA_VERSION,
                "source_hashes": source_hashes,
            }
        )
    )


def queue_anchor() -> policy.QueueLaunchAnchor:
    source_hashes = {
        source_name: hashlib.sha256(
            (policy.REPOSITORY_ROOT / source_name).read_bytes()
        ).hexdigest()
        for source_name in sorted(policy.REQUIRED_QUEUE_LAUNCH_SOURCES)
    }
    return policy.verify_queue_launch_manifest_bytes(
        policy.canonical_json_bytes(
            {
                "created_at": BASE.isoformat(),
                "launch_nonce": "queue-test-nonce",
                "manifest_kind": "v34_queue_launch",
                "output_root": policy.QUEUE_OUTPUT_ROOT,
                "policy_sha256": policy.POLICY_CANONICAL_SHA256,
                "run_signature": policy.QUEUE_RUN_SIGNATURE,
                "schema_version": policy.QUEUE_SCHEMA_VERSION,
                "source_hashes": source_hashes,
            }
        )
    )


def schedule_payload(
    *,
    game_pk: int = GAME_PK,
    game_time: datetime = BASE + timedelta(hours=1, minutes=10),
    away: str = "LAD",
    home: str = "PHI",
) -> dict[str, object]:
    return {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": game_pk,
                        "gameDate": game_time.isoformat(),
                        "status": {"detailedState": "Scheduled"},
                        "teams": {
                            "away": {"team": {"abbreviation": away}},
                            "home": {"team": {"abbreviation": home}},
                        },
                    }
                ]
            }
        ]
    }


def schedule_snapshot_raw(payload: dict[str, object] | None = None) -> bytes:
    if payload is None:
        payload = schedule_payload()
    game = cast("dict[str, object]", cast("list[object]", cast("dict[str, object]", cast("list[object]", payload["dates"])[0])["games"])[0])
    payload_raw = json.dumps(payload, separators=(",", ":")).encode()
    return policy.canonical_json_bytes(
        {
            "fetched_at": (BASE + timedelta(seconds=1)).isoformat(),
            "games": [
                {
                    "game_pk": game["gamePk"],
                    "scheduled_at": datetime.fromisoformat(str(game["gameDate"])).astimezone(UTC).isoformat(),
                }
            ],
            "horizon_hard_stop_at": (BASE + timedelta(hours=24)).isoformat(),
            "horizon_start_at": BASE.isoformat(),
            "kind": "v34_frozen_mlb_schedule",
            "launch_nonce": feed_anchor().provenance["launch_nonce"],
            "query_end_date": "2026-07-21",
            "query_start_date": "2026-07-20",
            "raw_payload_base64": base64.b64encode(payload_raw).decode(),
            "raw_payload_sha256": hashlib.sha256(payload_raw).hexdigest(),
            "run_signature": policy.FEED_RUN_SIGNATURE,
        }
    )


def play(index: int, *, away: int, home: int, end_seconds: int) -> dict[str, object]:
    return {
        "about": {
            "atBatIndex": index,
            "endTime": (BASE + timedelta(seconds=end_seconds)).isoformat(),
            "hasReview": False,
            "isComplete": True,
            "isScoringPlay": away + home > 0,
        },
        "result": {
            "awayScore": away,
            "description": f"play {index}",
            "event": "Single",
            "eventType": "single",
            "homeScore": home,
            "rbi": max(0, away + home),
        },
        "review_details": None,
    }


def transition(
    prior: feed_lifecycle.FeedGameState | None,
    completed: dict[str, object],
    *,
    seconds: int,
    total: int,
    abstract: str = "Live",
    detailed: str = "In Progress",
) -> feed_lifecycle.FeedGameState:
    return feed_lifecycle.transition_game(
        prior,
        game_pk=GAME_PK,
        completed_plays=completed,
        official_current_total=total,
        abstract_state=abstract,
        detailed_state=detailed,
        observed_at=BASE + timedelta(seconds=seconds),
        successful_poll_monotonic_ns=seconds * 1_000_000_000,
        expected_prior_state_commitment_sha256=(
            None if prior is None else prior.state_commitment_sha256
        ),
    ).state


def eligible_state(*, final: bool = False) -> feed_lifecycle.FeedGameState:
    baseline: dict[str, object] = {"0": play(0, away=0, home=0, end_seconds=0)}
    scored: dict[str, object] = {
        **baseline,
        "1": play(1, away=2, home=0, end_seconds=1),
    }
    state = transition(None, baseline, seconds=1, total=0)
    state = transition(state, scored, seconds=2, total=2)
    for seconds in (11, 20, 29, 38, 47, 56, 65):
        state = transition(state, scored, seconds=seconds, total=2)
    assert len(state.eligible) == 1
    if final:
        state = transition(
            state,
            scored,
            seconds=66,
            total=2,
            abstract="Final",
            detailed="Final",
        )
    return state


def archived_pair(
    *,
    generation: str = "g00000001",
    state: feed_lifecycle.FeedGameState | None = None,
) -> decision_commit.ArchivedFeedPair:
    if state is None:
        state = eligible_state()
    feed = feed_anchor()
    qanchor = queue_anchor()
    state_row = {
        **feed.provenance,
        "abstract_state": state.last_abstract_state,
        "completed_plays": json.loads(state.last_completed_plays_bytes),
        "detailed_state": state.last_detailed_state,
        "game_pk": GAME_PK,
        "generation_id": generation,
        "observed_at": state.last_observed_at,
        "official_current_total": state.last_official_current_total,
    }
    summary_bytes = policy.canonical_json_bytes(
        {
            **feed.provenance,
            "cycle_observed_at": state.last_observed_at,
            "game_states": {str(GAME_PK): state_row},
            "generation_id": generation,
            "kind": "v34_feed_generation",
            "lifecycle_states": {
                str(GAME_PK): json.loads(feed_lineage.serialize_game_state(state))
            },
        }
    )
    summary_sha = hashlib.sha256(summary_bytes).hexdigest()
    receipt_bytes = policy.canonical_json_bytes(
        {
            **feed.provenance,
            "generation_id": generation,
            "summary_sha256": summary_sha,
        }
    )
    archive_bytes = policy.canonical_json_bytes(
        {
            **feed.provenance,
            "archive_id": "queue-test-archive",
            "feed_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "generation_id": generation,
            "queue_provenance": qanchor.provenance,
            "summary_sha256": summary_sha,
        }
    )
    return decision_commit.ArchivedFeedPair(
        generation_id=generation,
        summary_bytes=summary_bytes,
        feed_receipt_bytes=receipt_bytes,
        archive_receipt_bytes=archive_bytes,
    )


def market_row(game_pk: int = GAME_PK, threshold: str = "1.5") -> queue.MarketRow:
    suffix = int(Decimal(threshold) + Decimal("0.5"))
    ticker = f"KXMLBTOTAL-26JUL201410LADPHI-{suffix}"
    raw: dict[str, object] = {
        "event_ticker": "KXMLBTOTAL-26JUL201410LADPHI",
        "floor_strike": float(threshold),
        "status": "active",
        "ticker": ticker,
    }
    return queue.MarketRow(
        game_pk=game_pk,
        event_ticker=cast("str", raw["event_ticker"]),
        ticker=ticker,
        threshold=Decimal(threshold),
        raw=raw,
    )


def candidate() -> queue.Candidate:
    pair = archived_pair()
    contexts = queue.feed_eligible_contexts(
        pair,
        feed_anchor=feed_anchor(),
        queue_anchor=queue_anchor(),
        now=BASE + timedelta(seconds=66),
    )
    return queue.Candidate(
        market=market_row(),
        eligible=contexts[GAME_PK][0],
        prior_order=None,
    )


def test_parse_event_ticker_uses_unique_team_split() -> None:
    parsed = queue.parse_event_ticker("KXMLBTOTAL-26JUL201410LADPHI")
    assert parsed is not None
    assert parsed[0].isoformat() == "2026-07-20T14:10:00-04:00"
    assert parsed[1:] == ("LAD", "PHI")
    assert queue.parse_event_ticker("KXMLBTOTAL-26JUL201410LALA") is None


def test_schedule_snapshot_recovers_exact_frozen_team_binding() -> None:
    games = queue.load_schedule_snapshot(schedule_snapshot_raw(), feed_anchor=feed_anchor())
    assert games == (
        queue.ScheduleGame(
            game_pk=GAME_PK,
            scheduled_at=BASE + timedelta(hours=1, minutes=10),
            away_code="LAD",
            home_code="PHI",
            detailed_state="Scheduled",
            status_reason=None,
        ),
    )
    value = json.loads(schedule_snapshot_raw())
    value["raw_payload_sha256"] = "0" * 64
    with pytest.raises(queue.QueueObserverFatalError, match="hash differs"):
        queue.load_schedule_snapshot(policy.canonical_json_bytes(value), feed_anchor=feed_anchor())


def test_market_universe_maps_horizon_and_rejects_wrong_suffix() -> None:
    games = queue.load_schedule_snapshot(schedule_snapshot_raw(), feed_anchor=feed_anchor())
    row = market_row().raw
    outside = {
        **row,
        "event_ticker": "KXMLBTOTAL-26JUL191920LADNYY",
        "ticker": "KXMLBTOTAL-26JUL191920LADNYY-2",
    }
    universe = queue.parse_market_universe(
        {"markets": [row, outside], "cursor": ""},
        games=games,
    )
    assert [item.ticker for item in universe.markets] == [market_row().ticker]
    assert universe.assignments[0].event_ticker == row["event_ticker"]
    assert universe.exclusions == ()
    malformed = {**row, "ticker": str(row["ticker"]) + "0"}
    with pytest.raises(queue.QueueObserverFatalError, match="suffix"):
        queue.parse_market_universe({"markets": [malformed]}, games=games)


def test_ambiguous_mapping_must_be_in_bound_and_status_eligible() -> None:
    expected = datetime(2026, 7, 20, 18, 10, tzinfo=UTC)
    distant = tuple(
        queue.ScheduleGame(
            game_pk=index,
            scheduled_at=expected + offset,
            away_code="LAD",
            home_code="PHI",
            detailed_state="Scheduled",
            status_reason=None,
        )
        for index, offset in (
            (1, timedelta(hours=-6)),
            (2, timedelta(hours=6)),
        )
    )
    valid = queue.ScheduleGame(
        game_pk=3,
        scheduled_at=datetime(2026, 7, 20, 19, 7, tzinfo=UTC),
        away_code="TB",
        home_code="TOR",
        detailed_state="Scheduled",
        status_reason=None,
    )
    rows = [
        market_row().raw,
        {
            "event_ticker": "KXMLBTOTAL-26JUL201507TBTOR",
            "floor_strike": 1.5,
            "status": "active",
            "ticker": "KXMLBTOTAL-26JUL201507TBTOR-2",
        },
    ]
    with pytest.raises(queue.QueueObserverFatalError, match="four-hour"):
        queue.parse_market_universe({"markets": rows}, games=(*distant, valid))

    prohibited = (
        queue.ScheduleGame(
            game_pk=1,
            scheduled_at=expected - timedelta(hours=1),
            away_code="LAD",
            home_code="PHI",
            detailed_state="Scheduled",
            status_reason=None,
        ),
        queue.ScheduleGame(
            game_pk=2,
            scheduled_at=expected + timedelta(hours=1),
            away_code="LAD",
            home_code="PHI",
            detailed_state="Postponed",
            status_reason="prohibited_status:postponed",
        ),
    )
    with pytest.raises(queue.QueueObserverFatalError, match="prohibited"):
        queue.parse_market_universe({"markets": [market_row().raw]}, games=prohibited)


def test_mapping_continuity_rejects_disappear_reappear_and_forged_identity() -> None:
    event = market_row().event_ticker
    assignment = queue.MappingAssignment(
        event,
        GAME_PK,
        policy.canonical_sha256({"event_ticker": event, "game_pk": GAME_PK}),
    )
    prior = queue.MarketUniverse((), (assignment,), (), (event,))
    ledger = queue.validate_mapping_continuity(None, prior)
    ledger = queue.validate_mapping_continuity(
        ledger,
        queue.MarketUniverse((), (), (), ()),
    )
    changed_assignment = queue.MappingAssignment(
        event,
        GAME_PK + 1,
        policy.canonical_sha256(
            {"event_ticker": event, "game_pk": GAME_PK + 1}
        ),
    )
    changed = queue.MarketUniverse(
        (),
        (changed_assignment,),
        (),
        (event,),
    )
    with pytest.raises(queue.QueueObserverFatalError, match="changed during"):
        queue.validate_mapping_continuity(ledger, changed)
    forged = queue.MarketUniverse(
        (),
        (replace(changed_assignment, identity_sha256=assignment.identity_sha256),),
        (),
        (event,),
    )
    with pytest.raises(queue.QueueObserverFatalError, match="hash differs"):
        queue.validate_mapping_continuity(None, forged)


def test_mapping_continuity_rejects_malformed_exclusion_and_lifetime_overlap() -> None:
    event = market_row().event_ticker
    expected = datetime(2026, 7, 20, 18, 10, tzinfo=UTC)
    tied = tuple(
        queue.ScheduleGame(
            game_pk=index,
            scheduled_at=expected + offset,
            away_code="LAD",
            home_code="PHI",
            detailed_state="Scheduled",
            status_reason=None,
        )
        for index, offset in (
            (1, timedelta(hours=-1)),
            (2, timedelta(hours=1)),
        )
    )
    exclusion = queue._mapping_exclusion(event, tied)
    malformed = queue.MarketUniverse(
        (),
        (),
        (replace(exclusion, identity_sha256="c" * 64),),
        (event,),
    )
    with pytest.raises(queue.QueueObserverFatalError, match="hash differs"):
        queue.validate_mapping_continuity(None, malformed)

    assignment = queue.MappingAssignment(
        event,
        GAME_PK,
        policy.canonical_sha256({"event_ticker": event, "game_pk": GAME_PK}),
    )
    ledger = queue.validate_mapping_continuity(
        None,
        queue.MarketUniverse((), (assignment,), (), (event,)),
    )
    ledger = queue.validate_mapping_continuity(
        ledger,
        queue.MarketUniverse((), (), (), ()),
    )
    after_absence = queue.MarketUniverse((), (), (exclusion,), (event,))
    with pytest.raises(queue.QueueObserverFatalError, match="changed during"):
        queue.validate_mapping_continuity(ledger, after_absence)

    overlapped = queue.MarketUniverse((), (assignment,), (exclusion,), (event,))
    with pytest.raises(queue.QueueObserverFatalError, match="overlaps"):
        queue.validate_mapping_continuity(None, overlapped)
    with pytest.raises(queue.QueueObserverFatalError, match="malformed"):
        queue.validate_mapping_continuity(
            {event: ("assignment", "Z" * 64)},
            queue.MarketUniverse((), (), (), ()),
        )


def test_mapping_rejects_equal_time_duplicate_and_prohibited_status() -> None:
    game = queue.ScheduleGame(
        game_pk=1,
        scheduled_at=BASE + timedelta(hours=1, minutes=10),
        away_code="LAD",
        home_code="PHI",
        detailed_state="Scheduled",
        status_reason=None,
    )
    twin = queue.ScheduleGame(
        game_pk=2,
        scheduled_at=game.scheduled_at,
        away_code="LAD",
        home_code="PHI",
        detailed_state="Scheduled",
        status_reason=None,
    )
    assert queue.match_event_to_game("KXMLBTOTAL-26JUL201410LADPHI", (game, twin)) == (
        None,
        "ambiguous_time_match",
    )
    prohibited = queue.ScheduleGame(
        game_pk=1,
        scheduled_at=game.scheduled_at,
        away_code="LAD",
        home_code="PHI",
        detailed_state="Postponed",
        status_reason="prohibited_status:postponed",
    )
    assert queue.match_event_to_game("KXMLBTOTAL-26JUL201410LADPHI", (prohibited,))[0] is None


def test_orderbook_100_cent_ask_and_depth_are_exact() -> None:
    view = queue.parse_orderbook(
        {
            "orderbook_fp": {
                "yes_dollars": [["0.9800", "3.00"], ["0.9900", "7.50"]],
                "no_dollars": [],
            }
        }
    )
    assert view.yes_ask == Decimal("1")
    assert view.yes_depth_99 == Decimal("7.50")
    crossed = queue.parse_orderbook(
        {
            "orderbook_fp": {
                "yes_dollars": [["0.9900", "7.50"]],
                "no_dollars": [["0.0100", "2.00"]],
            }
        }
    )
    assert crossed.yes_ask == Decimal("0.9900")
    with pytest.raises(queue.QueueObserverFatalError, match="repeats"):
        queue.parse_orderbook(
            {
                "orderbook_fp": {
                    "yes_dollars": [["0.9900", "1"], ["0.9900", "2"]],
                    "no_dollars": [],
                }
            }
        )


def test_public_http_allowlist_blocks_money_and_uses_one_retry() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"markets": []}, request=request)

    async def run() -> dict[str, object]:
        async def record_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            payload, _raw = await queue.bounded_public_get_json(
                client,
                "/markets",
                sleep=record_sleep,
            )
            with pytest.raises(queue.QueueObserverFatalError, match="allowlist"):
                await queue.bounded_public_get_json(client, "/portfolio/balance")
            return payload

    assert asyncio.run(run()) == {"markets": []}
    assert calls == 2
    assert sleeps == [queue.HTTP_RETRY_SECONDS]


def test_feed_context_reconstructs_eligible_trigger_and_rejects_stale() -> None:
    pair = archived_pair()
    contexts = queue.feed_eligible_contexts(
        pair,
        feed_anchor=feed_anchor(),
        queue_anchor=queue_anchor(),
        now=BASE + timedelta(seconds=66),
    )
    assert len(contexts[GAME_PK]) == 1
    assert contexts[GAME_PK][0].basis.post_total == 2
    with pytest.raises(queue.QueueObserverFatalError, match="stale"):
        queue.feed_eligible_contexts(
            pair,
            feed_anchor=feed_anchor(),
            queue_anchor=queue_anchor(),
            now=BASE + timedelta(seconds=90),
        )
    final_pair = archived_pair(state=eligible_state(final=True))
    assert queue.feed_eligible_contexts(
        final_pair,
        feed_anchor=feed_anchor(),
        queue_anchor=queue_anchor(),
        now=BASE + timedelta(days=1),
    )[GAME_PK]
    with pytest.raises(queue.QueueObserverFatalError, match="future-dated"):
        queue.feed_eligible_contexts(
            final_pair,
            feed_anchor=feed_anchor(),
            queue_anchor=queue_anchor(),
            now=BASE + timedelta(seconds=65),
        )


def test_candidate_selection_caps_at_two_and_prefers_distinct_games() -> None:
    basis = candidate().eligible
    eligibility = {1: (basis,), 2: (basis,), 3: (basis,)}
    markets = tuple(market_row(game_pk=game_pk, threshold=threshold) for game_pk, threshold in ((1, "0.5"), (1, "1.5"), (2, "0.5"), (3, "0.5")))
    selected = queue.select_candidates(
        markets,
        eligibility,
        {"orders": {}, "skip_keys": []},
        now=BASE + timedelta(seconds=66),
    )
    assert len(selected) == 2
    assert len({row.market.game_pk for row in selected}) == 2


@pytest.mark.parametrize(
    "no_levels, expected_kind, expected_status",
    [
        ([], "submit", "resting"),
        ([["0.0100", "2.00"]], "skip", "watching"),
    ],
)
def test_staged_decision_is_five_contract_shadow_or_watcher(
    no_levels: list[list[str]],
    expected_kind: str,
    expected_status: str,
) -> None:
    row = candidate()
    market_payload = {"market": row.market.raw}
    market_raw = json.dumps(market_payload).encode()
    book_payload = {
        "orderbook_fp": {
            "yes_dollars": [["0.9900", "7.00"]],
            "no_dollars": no_levels,
        }
    }
    book_raw = json.dumps(book_payload).encode()
    staged = queue.build_staged_decision(
        row,
        market_payload=market_payload,
        market_raw=market_raw,
        orderbook_payload=book_payload,
        orderbook_raw=book_raw,
        observed_at=BASE + timedelta(seconds=66),
    )
    assert staged.decision_kind == expected_kind
    value = cast("dict[str, object]", staged.mutations[0]["value"])
    assert value["status"] == expected_status
    assert value["contracts"] == "5.00"
    assert value["depth_ahead"] == "7.00"
    assert staged.evidence["shadow_price"] == "0.9900"
    assert base64.b64decode(cast("str", staged.evidence["market_raw_base64"])) == market_raw
    assert base64.b64decode(cast("str", staged.evidence["orderbook_raw_base64"])) == book_raw


def test_staged_decision_rejects_unrelated_raw_and_freezes_payload() -> None:
    row = candidate()
    market_payload: dict[str, object] = {"market": row.market.raw.copy()}
    book_payload: dict[str, object] = {
        "orderbook_fp": {"yes_dollars": [], "no_dollars": []}
    }
    market_raw = json.dumps(market_payload).encode()
    book_raw = json.dumps(book_payload).encode()
    with pytest.raises(queue.QueueObserverFatalError, match="raw bytes differ"):
        queue.build_staged_decision(
            row,
            market_payload=market_payload,
            market_raw=b'{"unrelated":true}',
            orderbook_payload=book_payload,
            orderbook_raw=book_raw,
            observed_at=BASE + timedelta(seconds=66),
        )
    staged = queue.build_staged_decision(
        row,
        market_payload=market_payload,
        market_raw=market_raw,
        orderbook_payload=book_payload,
        orderbook_raw=book_raw,
        observed_at=BASE + timedelta(seconds=66),
    )
    cast("dict[str, object]", market_payload["market"])["status"] = "mutated"
    cast("dict[str, object]", book_payload["orderbook_fp"])["yes_dollars"] = [
        ["0.9900", "999"]
    ]
    assert cast("dict[str, object]", staged.evidence["market_payload"])["status"] == "active"
    assert base64.b64decode(cast("str", staged.evidence["orderbook_raw_base64"])) == book_raw


def test_end_revalidation_binds_exact_generation_and_crossing() -> None:
    row = candidate()
    market_payload = {"market": row.market.raw}
    book_payload: dict[str, object] = {
        "orderbook_fp": {"yes_dollars": [], "no_dollars": []}
    }
    staged = queue.build_staged_decision(
        row,
        market_payload=market_payload,
        market_raw=json.dumps(market_payload).encode(),
        orderbook_payload=book_payload,
        orderbook_raw=json.dumps(book_payload).encode(),
        observed_at=BASE + timedelta(seconds=66),
    )
    pair = archived_pair()
    proof = queue.revalidate_staged_end(
        pair,
        staged,
        feed_anchor=feed_anchor(),
        queue_anchor=queue_anchor(),
        now=BASE + timedelta(seconds=66),
    )
    assert proof.feed_generation_id == pair.generation_id
    assert proof.crossing_valid is True


def test_stable_decision_commits_and_generation_change_discards(tmp_path: Path) -> None:
    row = candidate()
    market_payload = {"market": row.market.raw}
    book_payload: dict[str, object] = {
        "orderbook_fp": {"yes_dollars": [], "no_dollars": []}
    }
    staged = queue.build_staged_decision(
        row,
        market_payload=market_payload,
        market_raw=json.dumps(market_payload).encode(),
        orderbook_payload=book_payload,
        orderbook_raw=json.dumps(book_payload).encode(),
        observed_at=BASE + timedelta(seconds=66),
    )
    start = archived_pair()
    event = decision_commit.commit_staged_decision(
        event_path=tmp_path / "events.jsonl",
        state_path=tmp_path / "state.json",
        expected_feed_launch=feed_anchor(),
        expected_queue_launch=queue_anchor(),
        start_pair=start,
        end_pair=start,
        staged=staged,
        revalidate_end=lambda end, decision: queue.revalidate_staged_end(
            end,
            decision,
            feed_anchor=feed_anchor(),
            queue_anchor=queue_anchor(),
            now=BASE + timedelta(seconds=66),
        ),
    )
    assert event["type"] == "decision_commit"
    state = json.loads((tmp_path / "state.json").read_bytes())
    assert row.market.ticker in state["orders"]

    changed = archived_pair(generation="g00000002")
    discarded = decision_commit.commit_staged_decision(
        event_path=tmp_path / "events.jsonl",
        state_path=tmp_path / "state.json",
        expected_feed_launch=feed_anchor(),
        expected_queue_launch=queue_anchor(),
        start_pair=start,
        end_pair=changed,
        staged=staged,
        revalidate_end=lambda _end, _decision: pytest.fail("must not revalidate"),
    )
    assert discarded["type"] == "feed_generation_advanced"
