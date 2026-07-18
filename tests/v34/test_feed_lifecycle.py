from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from scripts.v34 import feed_lifecycle as lifecycle
from scripts.v34 import policy

BASE = datetime(2026, 7, 18, tzinfo=UTC)
GAME_PK = 824999


def play(
    index: int,
    *,
    away: int,
    home: int,
    end_seconds: float,
    has_review: bool = False,
    review: object = None,
) -> dict[str, object]:
    return {
        "about": {
            "atBatIndex": index,
            "endTime": (BASE + timedelta(seconds=end_seconds)).isoformat(),
            "hasReview": has_review,
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
        "review_details": review,
    }


def observe(
    prior: lifecycle.FeedGameState | None,
    completed: dict[str, object],
    *,
    observed_seconds: float,
    total: int,
    abstract: str = "Live",
    detailed: str = "In Progress",
    monotonic_ns: int | None = None,
) -> lifecycle.FeedTransition:
    if monotonic_ns is None:
        monotonic_ns = int(
            Decimal(str(observed_seconds)) * lifecycle.NANOSECONDS_PER_SECOND
        )
    return lifecycle.transition_game(
        prior,
        game_pk=GAME_PK,
        completed_plays=completed,
        official_current_total=total,
        abstract_state=abstract,
        detailed_state=detailed,
        observed_at=BASE + timedelta(seconds=observed_seconds),
        successful_poll_monotonic_ns=monotonic_ns,
        expected_prior_state_commitment_sha256=(
            None if prior is None else prior.state_commitment_sha256
        ),
    )


def baseline(*, observed_seconds: float = 10) -> lifecycle.FeedTransition:
    return observe(
        None,
        {
            "0": play(0, away=0, home=0, end_seconds=4),
            "1": play(1, away=2, home=0, end_seconds=8),
        },
        observed_seconds=observed_seconds,
        total=2,
    )


def new_trigger(
    prior: lifecycle.FeedGameState | None = None,
    *,
    observed_seconds: float = 20,
    end_seconds: float = 18,
) -> lifecycle.FeedTransition:
    if prior is None:
        prior = observe(
            None,
            {"0": play(0, away=0, home=0, end_seconds=4)},
            observed_seconds=10,
            total=0,
        ).state
    return observe(
        prior,
        {
            "0": play(0, away=0, home=0, end_seconds=4),
            "1": play(1, away=2, home=0, end_seconds=end_seconds),
        },
        observed_seconds=observed_seconds,
        total=2,
    )


def event_types(result: lifecycle.FeedTransition) -> list[object]:
    return [row["type"] for row in result.events]


def poll_to(
    prior: lifecycle.FeedGameState,
    completed: dict[str, object],
    *,
    observed_seconds: float,
    total: int,
) -> lifecycle.FeedTransition:
    current = prior
    current_seconds = (
        datetime.fromisoformat(current.last_observed_at) - BASE
    ).total_seconds()
    result: lifecycle.FeedTransition | None = None
    while current_seconds < observed_seconds:
        current_seconds = min(current_seconds + 10, observed_seconds)
        result = observe(
            current,
            completed,
            observed_seconds=current_seconds,
            total=total,
        )
        current = result.state
    if result is None:
        raise ValueError("poll_to target must follow the prior observation")
    return result


def test_fresh_baseline_suppresses_all_historical_triggers() -> None:
    result = baseline()
    assert result.state.pending == ()
    assert result.state.eligible == ()
    assert result.state.seen_completed_indices == (0, 1)
    assert event_types(result) == ["game_baseline"]


def test_delayed_historical_scoring_tail_after_baseline_is_noncredit() -> None:
    initial = observe(
        None,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=10,
        total=2,
    )
    delayed = observe(
        initial.state,
        {
            "0": play(0, away=0, home=0, end_seconds=4),
            "1": play(1, away=2, home=0, end_seconds=8),
        },
        observed_seconds=20,
        total=2,
    )
    assert delayed.state.pending == ()
    assert delayed.state.eligible == ()
    assert "stale_scoring_play_first_seen_noncredit" in event_types(delayed)


def test_feed_lagged_score_is_fresh_when_prior_total_did_not_reflect_it() -> None:
    initial = observe(
        None,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=10,
        total=0,
    )
    lagged = observe(
        initial.state,
        {
            "0": play(0, away=0, home=0, end_seconds=4),
            "1": play(1, away=2, home=0, end_seconds=9.9),
        },
        observed_seconds=20,
        total=2,
    )
    assert [row.trigger_at_bat_index for row in lagged.state.pending] == [1]
    assert "stale_scoring_play_first_seen_noncredit" not in event_types(lagged)


def test_new_score_increase_is_pending_with_immutable_first_sighting() -> None:
    result = new_trigger()
    assert len(result.state.pending) == 1
    pending = result.state.pending[0]
    assert pending.trigger_at_bat_index == 1
    assert pending.pre_total == 0
    assert pending.post_total == 2
    assert pending.run_delta == 2
    assert pending.t_seen == (BASE + timedelta(seconds=20)).isoformat()
    assert pending.candidate_start == pending.t_seen
    assert event_types(result) == ["run_increase_observed", "poll_validated"]


def test_guard_is_strict_at_sixty_seconds_and_immutable_after_eligibility() -> None:
    trigger = new_trigger()
    at_boundary = poll_to(
        trigger.state,
        json.loads(trigger.state.last_completed_plays_bytes),
        observed_seconds=80,
        total=2,
    )
    assert len(at_boundary.state.pending) == 1
    assert at_boundary.state.eligible == ()

    eligible = observe(
        at_boundary.state,
        json.loads(at_boundary.state.last_completed_plays_bytes),
        observed_seconds=80.001,
        total=2,
    )
    assert eligible.state.pending == ()
    assert len(eligible.state.eligible) == 1
    frozen = eligible.state.eligible[0]
    assert frozen.basis.eligible_at == (
        BASE + timedelta(seconds=80.001)
    ).isoformat()

    later = observe(
        eligible.state,
        json.loads(eligible.state.last_completed_plays_bytes),
        observed_seconds=90,
        total=2,
    )
    assert later.state.eligible == (frozen,)
    assert "eligible_trigger_revalidated" in event_types(later)


def test_preeligibility_end_time_revision_delays_candidate_start() -> None:
    trigger = new_trigger(end_seconds=18)
    revised = {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=2, home=0, end_seconds=25),
    }
    result = observe(trigger.state, revised, observed_seconds=26, total=2)
    assert result.state.pending[0].t_seen == trigger.state.pending[0].t_seen
    assert result.state.pending[0].candidate_start == (
        BASE + timedelta(seconds=25)
    ).isoformat()
    assert event_types(result) == [
        "completed_play_revision",
        "pending_trigger_revalidated",
        "poll_validated",
    ]


def test_posteligibility_exact_end_time_revision_is_signaled_when_guard_holds() -> None:
    trigger = new_trigger()
    eligible = poll_to(
        trigger.state,
        json.loads(trigger.state.last_completed_plays_bytes),
        observed_seconds=81,
        total=2,
    )
    revised = {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=2, home=0, end_seconds=19),
    }
    result = observe(eligible.state, revised, observed_seconds=90, total=2)
    assert result.state.eligible == eligible.state.eligible
    assert "eligible_prefix_end_time_only_observed" in event_types(result)


def test_representation_only_end_time_rewrite_is_explicitly_noncredit() -> None:
    trigger = new_trigger()
    completed = json.loads(trigger.state.last_completed_plays_bytes)
    eligible = poll_to(
        trigger.state,
        completed,
        observed_seconds=81,
        total=2,
    )
    rewritten = copy.deepcopy(completed)
    selected = rewritten["1"]
    selected["about"]["endTime"] = "2026-07-17T17:00:18-07:00"
    result = observe(eligible.state, rewritten, observed_seconds=90, total=2)
    assert "eligible_prefix_end_time_only_observed" not in event_types(result)
    assert (
        "eligible_prefix_end_time_representation_only_noncredit"
        in event_types(result)
    )


def test_posteligibility_end_time_revision_that_breaks_guard_is_fatal() -> None:
    trigger = new_trigger()
    eligible = poll_to(
        trigger.state,
        json.loads(trigger.state.last_completed_plays_bytes),
        observed_seconds=81,
        total=2,
    )
    revised = {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=2, home=0, end_seconds=21),
    }
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="eligible_prefix_invalid",
    ):
        observe(eligible.state, revised, observed_seconds=90, total=2)


def test_posteligibility_revision_must_repass_immutable_monotonic_guard() -> None:
    trigger = new_trigger()
    completed = json.loads(trigger.state.last_completed_plays_bytes)
    current = trigger.state
    for wall_seconds, monotonic_seconds in (
        (930, 30),
        (940, 40),
        (950, 50),
        (960, 60),
        (970, 70),
        (980, 80),
        (1_000, 81),
    ):
        current = observe(
            current,
            completed,
            observed_seconds=wall_seconds,
            monotonic_ns=(
                monotonic_seconds * lifecycle.NANOSECONDS_PER_SECOND
            ),
            total=2,
        ).state
    assert len(current.eligible) == 1
    revised = {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=2, home=0, end_seconds=22),
    }
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="breaks monotonic guard",
    ):
        observe(
            current,
            revised,
            observed_seconds=1_001,
            monotonic_ns=82 * lifecycle.NANOSECONDS_PER_SECOND,
            total=2,
        )


def test_suffix_revision_does_not_taint_an_earlier_eligible_trigger() -> None:
    trigger = new_trigger()
    with_suffix = {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=2, home=0, end_seconds=18),
        "2": play(2, away=2, home=0, end_seconds=24),
    }
    suffix_added = observe(trigger.state, with_suffix, observed_seconds=25, total=2)
    eligible = poll_to(
        suffix_added.state,
        with_suffix,
        observed_seconds=81,
        total=2,
    )
    changed = copy.deepcopy(with_suffix)
    changed_play = changed["2"]
    assert isinstance(changed_play, dict)
    changed_result = changed_play["result"]
    assert isinstance(changed_result, dict)
    changed_result["description"] = "corrected suffix description"
    result = observe(eligible.state, changed, observed_seconds=90, total=2)
    assert result.state.eligible == eligible.state.eligible
    assert "eligible_prefix_end_time_only_observed" not in event_types(result)


@pytest.mark.parametrize("changed_field", ["score", "review", "description"])
def test_dependent_eligible_prefix_change_is_fatal(changed_field: str) -> None:
    trigger = new_trigger()
    eligible = poll_to(
        trigger.state,
        json.loads(trigger.state.last_completed_plays_bytes),
        observed_seconds=81,
        total=2,
    )
    current: dict[str, Any] = json.loads(eligible.state.last_completed_plays_bytes)
    selected = current["1"]
    if changed_field == "score":
        selected["result"]["awayScore"] = 3
        total = 3
    elif changed_field == "review":
        selected["about"]["hasReview"] = True
        selected["review_details"] = {"isOverturned": False}
        total = 2
    else:
        selected["result"]["description"] = "corrected description"
        total = 2
    if changed_field == "description":
        result = observe(eligible.state, current, observed_seconds=90, total=total)
        assert result.state.eligible == eligible.state.eligible
    else:
        with pytest.raises(lifecycle.FeedTransitionFatalError):
            observe(eligible.state, current, observed_seconds=90, total=total)


def test_team_score_path_regression_is_fatal_even_when_total_is_unchanged() -> None:
    prior = observe(
        None,
        {
            "0": play(0, away=1, home=0, end_seconds=4),
            "1": play(1, away=1, home=1, end_seconds=8),
        },
        observed_seconds=10,
        total=2,
    )
    regressed = {
        "0": play(0, away=1, home=0, end_seconds=4),
        "1": play(1, away=0, home=2, end_seconds=8),
    }
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="score_path_regression",
    ):
        observe(prior.state, regressed, observed_seconds=20, total=2)


def test_exact_ten_second_gap_passes_and_larger_gap_is_fatal() -> None:
    initial = baseline(observed_seconds=10)
    current = json.loads(initial.state.last_completed_plays_bytes)
    assert observe(initial.state, current, observed_seconds=20, total=2).state
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="successful_poll_gap",
    ):
        observe(initial.state, current, observed_seconds=20.001, total=2)


def test_poll_gap_uses_monotonic_clock_instead_of_wall_time() -> None:
    initial = baseline(observed_seconds=10)
    current = json.loads(initial.state.last_completed_plays_bytes)
    result = observe(
        initial.state,
        current,
        observed_seconds=25,
        monotonic_ns=20 * lifecycle.NANOSECONDS_PER_SECOND,
        total=2,
    )
    assert result.events[-1]["gap_monotonic_ns"] == (
        10 * lifecycle.NANOSECONDS_PER_SECOND
    )


def test_wall_jump_cannot_bypass_the_monotonic_guard() -> None:
    trigger = new_trigger()
    jumped = observe(
        trigger.state,
        json.loads(trigger.state.last_completed_plays_bytes),
        observed_seconds=1_000,
        monotonic_ns=30 * lifecycle.NANOSECONDS_PER_SECOND,
        total=2,
    )
    assert len(jumped.state.pending) == 1
    assert jumped.state.eligible == ()


def test_slow_wall_clock_does_not_force_promotion_or_fail_state_validation() -> None:
    trigger = new_trigger()
    current = trigger.state
    completed = json.loads(trigger.state.last_completed_plays_bytes)
    for step in range(1, 7):
        current = observe(
            current,
            completed,
            observed_seconds=20 + step,
            monotonic_ns=(20 + 10 * step) * lifecycle.NANOSECONDS_PER_SECOND,
            total=2,
        ).state
    slow_wall = observe(
        current,
        completed,
        observed_seconds=30,
        monotonic_ns=81 * lifecycle.NANOSECONDS_PER_SECOND,
        total=2,
    )
    assert len(slow_wall.state.pending) == 1
    assert slow_wall.state.eligible == ()


def test_removal_total_regression_and_prohibited_status_are_fatal() -> None:
    initial = baseline()
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="official_total_regression",
    ):
        observe(
            initial.state,
            json.loads(initial.state.last_completed_plays_bytes),
            observed_seconds=20,
            total=1,
        )
    pending = new_trigger()
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="completed_play_removed",
    ):
        observe(
            pending.state,
            {"0": play(0, away=0, home=0, end_seconds=4)},
            observed_seconds=30,
            total=2,
        )
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="prohibited_status",
    ):
        observe(
            initial.state,
            json.loads(initial.state.last_completed_plays_bytes),
            observed_seconds=20,
            total=2,
            detailed="Game Suspended",
        )


def test_final_requires_exact_completed_play_total() -> None:
    completed = {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=2, home=0, end_seconds=8),
    }
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="incomplete_final_projection",
    ):
        observe(
            None,
            completed,
            observed_seconds=10,
            total=3,
            abstract="Final",
            detailed="Final",
        )
    exact = observe(
        None,
        completed,
        observed_seconds=10,
        total=2,
        abstract="Final",
        detailed="Final",
    )
    assert exact.state.last_abstract_state == "Final"


def test_boolean_aliases_noncanonical_keys_and_forged_state_are_fatal() -> None:
    malformed: dict[str, Any] = {
        "0": play(0, away=0, home=0, end_seconds=4)
    }
    malformed["0"]["result"]["awayScore"] = False
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="malformed_projection",
    ):
        observe(None, malformed, observed_seconds=10, total=0)

    aliased = {
        "00": play(0, away=0, home=0, end_seconds=4),
    }
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="malformed_plays",
    ):
        observe(None, aliased, observed_seconds=10, total=0)

    integer_key: Any = {
        0: play(0, away=0, home=0, end_seconds=4),
    }
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="key is not a string",
    ):
        observe(None, integer_key, observed_seconds=10, total=0)

    initial = baseline()
    forged = replace(initial.state, pending=[])
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="immutable tuples",
    ):
        observe(
            forged,
            json.loads(initial.state.last_completed_plays_bytes),
            observed_seconds=20,
            total=2,
        )


def test_future_completed_end_time_is_fatal_even_without_a_trigger() -> None:
    future = {"0": play(0, away=0, home=0, end_seconds=11)}
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="future_completed_play",
    ):
        observe(None, future, observed_seconds=10, total=0)


def test_state_commitment_rejects_replace_style_history_injection() -> None:
    initial = baseline()
    trigger = new_trigger()
    eligible = poll_to(
        trigger.state,
        json.loads(trigger.state.last_completed_plays_bytes),
        observed_seconds=81,
        total=2,
    )
    injected = replace(initial.state, eligible=eligible.state.eligible)
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="state commitment differs",
    ):
        observe(
            injected,
            json.loads(initial.state.last_completed_plays_bytes),
            observed_seconds=20,
            total=2,
        )

    rewound_clock = replace(
        initial.state,
        last_successful_poll_monotonic_ns=0,
    )
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="state commitment differs",
    ):
        observe(
            rewound_clock,
            json.loads(initial.state.last_completed_plays_bytes),
            observed_seconds=20,
            total=2,
        )


def test_externally_retained_head_rejects_a_recomputed_forged_state() -> None:
    initial = baseline()
    trigger = new_trigger()
    eligible = poll_to(
        trigger.state,
        json.loads(trigger.state.last_completed_plays_bytes),
        observed_seconds=81,
        total=2,
    )
    forged = lifecycle._make_state(
        game_pk=initial.state.game_pk,
        seen_completed_indices=initial.state.seen_completed_indices,
        last_completed_plays_bytes=initial.state.last_completed_plays_bytes,
        last_official_current_total=initial.state.last_official_current_total,
        last_abstract_state=initial.state.last_abstract_state,
        last_detailed_state=initial.state.last_detailed_state,
        last_observed_at=initial.state.last_observed_at,
        last_successful_poll_monotonic_ns=(
            initial.state.last_successful_poll_monotonic_ns
        ),
        pending=(),
        eligible=eligible.state.eligible,
        transition_sequence=initial.state.transition_sequence,
        prior_state_commitment_sha256=(
            initial.state.prior_state_commitment_sha256
        ),
    )
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match="prior state differs from the externally retained commitment",
    ):
        lifecycle.transition_game(
            forged,
            game_pk=GAME_PK,
            completed_plays=json.loads(initial.state.last_completed_plays_bytes),
            official_current_total=2,
            abstract_state="Live",
            detailed_state="In Progress",
            observed_at=BASE + timedelta(seconds=20),
            successful_poll_monotonic_ns=(
                20 * lifecycle.NANOSECONDS_PER_SECOND
            ),
            expected_prior_state_commitment_sha256=(
                initial.state.state_commitment_sha256
            ),
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("pre_total", False), ("post_total", 2.0)],
)
def test_recommitted_pending_numeric_aliases_remain_fatal(
    field_name: str,
    value: object,
) -> None:
    trigger = new_trigger()
    malformed_pending = replace(
        trigger.state.pending[0],
        **{field_name: value},
    )
    forged = lifecycle._make_state(
        game_pk=trigger.state.game_pk,
        seen_completed_indices=trigger.state.seen_completed_indices,
        last_completed_plays_bytes=trigger.state.last_completed_plays_bytes,
        last_official_current_total=trigger.state.last_official_current_total,
        last_abstract_state=trigger.state.last_abstract_state,
        last_detailed_state=trigger.state.last_detailed_state,
        last_observed_at=trigger.state.last_observed_at,
        last_successful_poll_monotonic_ns=(
            trigger.state.last_successful_poll_monotonic_ns
        ),
        pending=(malformed_pending,),
        eligible=(),
        transition_sequence=trigger.state.transition_sequence,
        prior_state_commitment_sha256=(
            trigger.state.prior_state_commitment_sha256
        ),
    )
    with pytest.raises(
        lifecycle.FeedTransitionFatalError,
        match=f"pending.{field_name} must be an exact integer",
    ):
        observe(
            forged,
            json.loads(forged.last_completed_plays_bytes),
            observed_seconds=30,
            total=2,
        )


def test_unbound_completed_suffix_may_disappear_and_reappear_as_telemetry() -> None:
    trigger = new_trigger()
    with_suffix = {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=2, home=0, end_seconds=18),
        "2": play(2, away=2, home=0, end_seconds=24),
    }
    added = observe(trigger.state, with_suffix, observed_seconds=25, total=2)
    truncated = observe(
        added.state,
        {
            "0": play(0, away=0, home=0, end_seconds=4),
            "1": play(1, away=2, home=0, end_seconds=18),
        },
        observed_seconds=30,
        total=2,
    )
    assert "completed_suffix_play_disappeared" in event_types(truncated)
    assert truncated.state.seen_completed_indices == (0, 1, 2)
    reappeared = observe(
        truncated.state,
        with_suffix,
        observed_seconds=35,
        total=2,
    )
    assert "completed_suffix_play_reappeared" in event_types(reappeared)
    assert "run_increase_observed" not in event_types(reappeared)


def test_transition_owns_canonical_bytes_and_does_not_alias_input() -> None:
    completed = {"0": play(0, away=0, home=0, end_seconds=4)}
    result = observe(None, completed, observed_seconds=10, total=0)
    expected_state = result.state.last_completed_plays_bytes
    expected_events = result.event_bytes
    completed["0"] = play(0, away=9, home=0, end_seconds=4)
    assert result.state.last_completed_plays_bytes == expected_state
    assert result.event_bytes == expected_events
    for raw in result.event_bytes:
        assert raw == policy.canonical_json_bytes(json.loads(raw))


def test_multiple_new_score_jumps_create_separate_pending_triggers() -> None:
    initial = observe(
        None,
        {"0": play(0, away=0, home=0, end_seconds=4)},
        observed_seconds=10,
        total=0,
    )
    jumped = {
        "0": play(0, away=0, home=0, end_seconds=4),
        "1": play(1, away=1, home=0, end_seconds=14),
        "2": play(2, away=1, home=0, end_seconds=16),
        "3": play(3, away=1, home=2, end_seconds=18),
    }
    result = observe(initial.state, jumped, observed_seconds=20, total=3)
    assert [row.trigger_at_bat_index for row in result.state.pending] == [1, 3]
    assert event_types(result).count("run_increase_observed") == 2
