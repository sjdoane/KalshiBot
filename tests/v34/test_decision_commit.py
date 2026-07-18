from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest
from scripts.v34 import decision_commit as commit
from scripts.v34 import policy

if TYPE_CHECKING:
    from pathlib import Path

SOURCE_HASHES = {
    source_name: hashlib.sha256(
        (policy.REPOSITORY_ROOT / source_name).read_bytes()
    ).hexdigest()
    for source_name in sorted(policy.REQUIRED_LAUNCH_SOURCES)
}
LAUNCH_MANIFEST_BYTES = policy.canonical_json_bytes(
    {
        "created_at": "2026-07-18T00:00:00+00:00",
        "launch_nonce": "v34-launch-test-nonce",
        "manifest_kind": "v34_feed_launch",
        "output_root": policy.FEED_OUTPUT_ROOT,
        "policy_sha256": policy.POLICY_CANONICAL_SHA256,
        "run_signature": policy.FEED_RUN_SIGNATURE,
        "schema_version": policy.FEED_SCHEMA_VERSION,
        "source_hashes": SOURCE_HASHES,
    }
)
LAUNCH_ANCHOR = policy.verify_feed_launch_manifest_bytes(LAUNCH_MANIFEST_BYTES)
PROVENANCE: dict[str, object] = LAUNCH_ANCHOR.provenance


def canonical_bytes(value: object) -> bytes:
    return policy.canonical_json_bytes(value)


def pair(
    generation: str = "generation-1",
    *,
    marker: str = "a",
    archive_id: str = "archive-a",
    provenance: dict[str, object] = PROVENANCE,
) -> commit.ArchivedFeedPair:
    summary_bytes = canonical_bytes(
        {**provenance, "generation_id": generation, "marker": marker}
    )
    summary_sha256 = commit._sha256_bytes(summary_bytes)
    feed_receipt_bytes = canonical_bytes(
        {
            **provenance,
            "generation_id": generation,
            "summary_sha256": summary_sha256,
        }
    )
    archive_receipt_bytes = canonical_bytes(
        {
            **provenance,
            "archive_id": archive_id,
            "feed_receipt_sha256": commit._sha256_bytes(feed_receipt_bytes),
            "generation_id": generation,
            "summary_sha256": summary_sha256,
        }
    )
    return commit.ArchivedFeedPair(
        generation_id=generation,
        summary_bytes=summary_bytes,
        feed_receipt_bytes=feed_receipt_bytes,
        archive_receipt_bytes=archive_receipt_bytes,
    )


def staged(value: int = 1) -> commit.StagedDecision:
    return commit.StagedDecision(
        decision_kind="submit",
        decision_key="TICKER-1",
        market_ticker="TICKER-1",
        threshold="1.5",
        game_pk=824999,
        trigger_at_bat_index=1,
        trigger_play_identity="e" * 64,
        ordered_prefix_fingerprint="f" * 64,
        pre_total=0,
        post_total=2,
        run_delta=2,
        t_seen="2026-07-18T00:00:10+00:00",
        eligible_at="2026-07-18T00:01:11+00:00",
        mutations=(
            {
                "operation": "upsert_order",
                "key": "TICKER-1",
                "value": {"contracts": value},
            },
        ),
        evidence={"threshold": "1.5"},
    )


def proof_for(
    end_pair: commit.ArchivedFeedPair,
    decision: commit.StagedDecision,
) -> commit.EndValidationProof:
    return commit.EndValidationProof(
        feed_generation_id=end_pair.generation_id,
        feed_summary_sha256=end_pair.summary_sha256,
        market_ticker=decision.market_ticker,
        threshold=decision.threshold,
        game_pk=decision.game_pk,
        trigger_at_bat_index=decision.trigger_at_bat_index,
        trigger_play_identity=decision.trigger_play_identity,
        ordered_prefix_fingerprint=decision.ordered_prefix_fingerprint,
        pre_total=decision.pre_total,
        post_total=decision.post_total,
        run_delta=decision.run_delta,
        t_seen=decision.t_seen,
        eligible_at=decision.eligible_at,
        crossing_valid=True,
        eligibility_valid=True,
        freshness_valid=True,
    )


def revalidate(
    end_pair: commit.ArchivedFeedPair,
    decision: commit.StagedDecision,
) -> commit.EndValidationProof:
    return proof_for(end_pair, decision)


def paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "events.jsonl", tmp_path / "state.json"


def commit_decision(**kwargs: Any) -> dict[str, object]:
    return commit.commit_staged_decision(
        expected_feed_launch=LAUNCH_ANCHOR,
        **kwargs,
    )


def test_stable_generation_binds_proof_then_commits_once(tmp_path: Path) -> None:
    event_path, state_path = paths(tmp_path)
    calls: list[str] = []

    def checked(
        end_pair: commit.ArchivedFeedPair,
        decision: commit.StagedDecision,
    ) -> commit.EndValidationProof:
        calls.append(end_pair.summary_sha256)
        return proof_for(end_pair, decision)

    end_pair = pair(archive_id="archive-b")
    event = commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=end_pair,
        staged=staged(5),
        revalidate_end=checked,
    )
    assert calls == [end_pair.summary_sha256]
    assert event["type"] == "decision_commit"
    assert event["feed_summary_sha256"] == end_pair.summary_sha256
    assert event["end_validation_proof_sha256"] == policy.canonical_sha256(
        event["end_validation_proof"]
    )
    assert len(commit.read_events(event_path)) == 1
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["orders"]["TICKER-1"] == {"contracts": 5}


def test_generation_or_summary_advance_discards_all_candidate_mutations(
    tmp_path: Path,
) -> None:
    event_path, state_path = paths(tmp_path)
    called = False

    def should_not_run(
        end_pair: commit.ArchivedFeedPair,
        decision: commit.StagedDecision,
    ) -> commit.EndValidationProof:
        nonlocal called
        called = True
        return proof_for(end_pair, decision)

    event = commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(generation="generation-2"),
        staged=staged(5),
        revalidate_end=should_not_run,
    )
    assert not called
    assert event["type"] == "feed_generation_advanced"
    assert json.loads(state_path.read_text(encoding="utf-8"))["orders"] == {}

    event = commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(generation="generation-2"),
        end_pair=pair(generation="generation-2", marker="changed"),
        staged=staged(6),
        revalidate_end=should_not_run,
    )
    assert event["type"] == "feed_generation_advanced"
    assert json.loads(state_path.read_text(encoding="utf-8"))["orders"] == {}


def test_failed_end_revalidation_writes_no_event_or_state(tmp_path: Path) -> None:
    event_path, state_path = paths(tmp_path)

    def fail(
        end_pair: commit.ArchivedFeedPair,
        decision: commit.StagedDecision,
    ) -> commit.EndValidationProof:
        raise ValueError("prefix changed")

    with pytest.raises(ValueError, match="prefix changed"):
        commit_decision(
            event_path=event_path,
            state_path=state_path,
            start_pair=pair(),
            end_pair=pair(archive_id="archive-b"),
            staged=staged(),
            revalidate_end=fail,
        )
    assert not event_path.exists()
    assert not state_path.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("feed_generation_id", "wrong", "bind"),
        ("threshold", "9.5", "bind"),
        ("eligible_at", "2026-07-18T00:02:11+00:00", "bind"),
        ("crossing_valid", False, "not true"),
        ("eligibility_valid", False, "not true"),
        ("freshness_valid", False, "not true"),
    ],
)
def test_end_proof_must_bind_every_decision_field_and_boolean(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    event_path, state_path = paths(tmp_path)

    def invalid(
        end_pair: commit.ArchivedFeedPair,
        decision: commit.StagedDecision,
    ) -> commit.EndValidationProof:
        return replace(proof_for(end_pair, decision), **{field: value})

    with pytest.raises(ValueError, match=message):
        commit_decision(
            event_path=event_path,
            state_path=state_path,
            start_pair=pair(),
            end_pair=pair(archive_id="archive-b"),
            staged=staged(),
            revalidate_end=invalid,
        )
    assert not event_path.exists()
    assert not state_path.exists()


def test_staged_mutations_are_frozen_before_revalidation(tmp_path: Path) -> None:
    event_path, state_path = paths(tmp_path)
    candidate = staged(3)

    def mutate_external_candidate(
        end_pair: commit.ArchivedFeedPair,
        frozen: commit.StagedDecision,
    ) -> commit.EndValidationProof:
        value = candidate.mutations[0]["value"]
        assert isinstance(value, dict)
        value["contracts"] = 99
        return proof_for(end_pair, frozen)

    commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(archive_id="archive-b"),
        staged=candidate,
        revalidate_end=mutate_external_candidate,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["orders"]["TICKER-1"] == {"contracts": 3}


def test_event_log_recovers_state_after_cache_loss(tmp_path: Path) -> None:
    event_path, state_path = paths(tmp_path)
    commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(archive_id="archive-b"),
        staged=staged(7),
        revalidate_end=revalidate,
    )
    state_path.unlink()
    recovered = commit.rebuild_state_cache(event_path, state_path)
    assert recovered["orders"] == {"TICKER-1": {"contracts": 7}}
    assert state_path.exists()


def test_semantically_corrupt_cache_is_never_authoritative(tmp_path: Path) -> None:
    event_path, state_path = paths(tmp_path)
    commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(archive_id="archive-b"),
        staged=staged(2),
        revalidate_end=revalidate,
    )
    corrupt = json.loads(state_path.read_text(encoding="utf-8"))
    corrupt["orders"]["PHANTOM"] = {"contracts": 999}
    state_path.write_text(json.dumps(corrupt), encoding="utf-8")
    commit._TAIL_CACHE.clear()
    commit._VERIFIED_STATE_CACHE.clear()

    commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(archive_id="archive-c"),
        staged=staged(8),
        revalidate_end=revalidate,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "PHANTOM" not in state["orders"]
    assert state["orders"]["TICKER-1"] == {"contracts": 8}
    assert state["last_event_sha256"] == commit.read_events(event_path)[-1][
        "event_sha256"
    ]


def test_repeated_commits_do_not_replay_the_full_log_each_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_path, state_path = paths(tmp_path)
    original = commit.read_events
    calls = 0

    def counted(path: Path) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(commit, "read_events", counted)
    for value in range(40):
        commit_decision(
            event_path=event_path,
            state_path=state_path,
            start_pair=pair(),
            end_pair=pair(archive_id="archive-b"),
            staged=staged(value),
            revalidate_end=revalidate,
        )
    assert calls <= 1
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["orders"]["TICKER-1"] == {"contracts": 39}


def test_advance_after_commit_preserves_orders_and_cache_chain(
    tmp_path: Path,
) -> None:
    event_path, state_path = paths(tmp_path)
    commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(archive_id="archive-b"),
        staged=staged(4),
        revalidate_end=revalidate,
    )
    event = commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(generation="generation-2"),
        staged=staged(9),
        revalidate_end=lambda *_: pytest.fail(
            "must not revalidate an advanced generation"
        ),
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["orders"]["TICKER-1"] == {"contracts": 4}
    assert state["last_event_sha256"] == event["event_sha256"]


def test_delete_and_skip_mutations_reduce_deterministically(tmp_path: Path) -> None:
    event_path, state_path = paths(tmp_path)
    commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(archive_id="archive-b"),
        staged=staged(2),
        revalidate_end=revalidate,
    )
    second = replace(
        staged(),
        decision_kind="reconcile",
        mutations=(
            {"operation": "delete_order", "key": "TICKER-1"},
            {"operation": "record_skip", "key": "NO-DEPTH"},
        ),
        evidence={"reason": "closed"},
    )
    commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(archive_id="archive-c"),
        staged=second,
        revalidate_end=revalidate,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["orders"] == {}
    assert state["skip_keys"] == ["NO-DEPTH"]


def test_tampered_event_partial_line_and_semantic_hash_fail_closed(
    tmp_path: Path,
) -> None:
    event_path, state_path = paths(tmp_path)
    commit_decision(
        event_path=event_path,
        state_path=state_path,
        start_pair=pair(),
        end_pair=pair(archive_id="archive-b"),
        staged=staged(),
        revalidate_end=revalidate,
    )
    original = json.loads(event_path.read_text(encoding="utf-8"))
    tampered = dict(original)
    tampered["decision_key"] = "tampered"
    event_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="payload hash"):
        commit.read_events(event_path)
    event_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="lacks newline"):
        commit.read_events(event_path)

    semantic = dict(original)
    semantic["resulting_semantic_state_sha256"] = "0" * 64
    semantic["event_sha256"] = commit._event_payload_sha256(semantic)
    event_path.write_text(json.dumps(semantic) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="semantic state hash"):
        commit.read_events(event_path)


def test_invalid_archive_mutation_and_nonfinite_evidence_fail_before_write(
    tmp_path: Path,
) -> None:
    event_path, state_path = paths(tmp_path)
    valid = pair()
    invalid_pair = replace(valid, feed_receipt_bytes=b'{}')
    with pytest.raises(ValueError, match="run signature mismatch"):
        commit_decision(
            event_path=event_path,
            state_path=state_path,
            start_pair=invalid_pair,
            end_pair=pair(),
            staged=staged(),
            revalidate_end=revalidate,
        )
    invalid = replace(
        staged(),
        mutations=({"operation": "delete_order", "key": "x", "value": {}},),
    )
    with pytest.raises(ValueError, match="cannot include value"):
        invalid.validate()
    nonfinite = replace(
        staged(),
        decision_kind="skip",
        mutations=({"operation": "record_skip", "key": "x"},),
        evidence={"bad": float("nan")},
    )
    with pytest.raises(ValueError):
        nonfinite.validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("run_signature", "prospective-v33-20260718-lock2", "run signature"),
        ("policy_sha256", "0" * 64, "policy hash"),
        ("launch_nonce", "foreign-launch", "provenance mismatch"),
    ],
)
def test_foreign_or_rewrapped_feed_provenance_is_rejected(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    event_path, state_path = paths(tmp_path)
    foreign = {**PROVENANCE, field: value}
    with pytest.raises(ValueError, match=message):
        commit_decision(
            event_path=event_path,
            state_path=state_path,
            start_pair=pair(provenance=foreign),
            end_pair=pair(provenance=foreign, archive_id="archive-b"),
            staged=staged(),
            revalidate_end=revalidate,
        )
    assert not event_path.exists()
    assert not state_path.exists()


def test_noncanonical_feed_json_is_rejected(tmp_path: Path) -> None:
    event_path, state_path = paths(tmp_path)
    valid = pair()
    noncanonical = replace(valid, summary_bytes=valid.summary_bytes + b" ")
    with pytest.raises(ValueError, match="not canonical JSON"):
        commit_decision(
            event_path=event_path,
            state_path=state_path,
            start_pair=noncanonical,
            end_pair=pair(archive_id="archive-b"),
            staged=staged(),
            revalidate_end=revalidate,
        )


def test_launch_anchor_hashes_canonical_manifest_and_actual_sources() -> None:
    assert LAUNCH_ANCHOR.manifest_sha256 == hashlib.sha256(
        LAUNCH_MANIFEST_BYTES
    ).hexdigest()
    manifest = json.loads(LAUNCH_MANIFEST_BYTES)
    manifest["source_hashes"]["scripts/v34/policy.py"] = "0" * 64
    with pytest.raises(ValueError, match="source hash mismatch"):
        policy.verify_feed_launch_manifest_bytes(
            policy.canonical_json_bytes(manifest)
        )
    with pytest.raises(ValueError, match="not canonical"):
        policy.verify_feed_launch_manifest_bytes(LAUNCH_MANIFEST_BYTES + b" ")


def test_directly_constructed_launch_anchor_is_reverified_before_use(
    tmp_path: Path,
) -> None:
    event_path, state_path = paths(tmp_path)
    forged = policy.FeedLaunchAnchor(
        manifest_bytes=b"not a canonical manifest",
        manifest_sha256="0" * 64,
        provenance_bytes=LAUNCH_ANCHOR.provenance_bytes,
    )
    with pytest.raises(ValueError, match="manifest JSON is invalid"):
        commit.commit_staged_decision(
            event_path=event_path,
            state_path=state_path,
            expected_feed_launch=forged,
            start_pair=pair(),
            end_pair=pair(archive_id="archive-b"),
            staged=staged(),
            revalidate_end=revalidate,
        )
