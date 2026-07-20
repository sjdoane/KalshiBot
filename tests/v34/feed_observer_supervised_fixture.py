"""Run the real feed observer under its real supervisor with fixed HTTP bytes."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import patch

from scripts.v34 import feed_observer, policy


def main() -> None:
    if len(sys.argv) != 2:
        raise ValueError("supervised feed fixture argument count differs")
    value = json.loads(Path(sys.argv[1]).read_bytes())
    if not isinstance(value, dict):
        raise TypeError("supervised feed fixture config is invalid")
    created_at = datetime.fromisoformat(cast("str", value["created_at"]))
    game_pk = 824410

    async def fixed_http(
        _client: object,
        url: str,
        **_kwargs: object,
    ) -> tuple[dict[str, object], bytes]:
        if url == feed_observer.SCHEDULE_URL:
            payload: dict[str, object] = {
                "dates": [
                    {
                        "games": [
                            {
                                "gamePk": game_pk,
                                "gameDate": (created_at + timedelta(minutes=1)).isoformat(),
                            }
                        ]
                    }
                ]
            }
        else:
            payload = {
                "gamePk": game_pk,
                "gameData": {
                    "status": {
                        "abstractGameState": "Final",
                        "detailedState": "Final",
                    }
                },
                "liveData": {
                    "linescore": {
                        "teams": {"away": {"runs": 0}, "home": {"runs": 0}}
                    },
                    "plays": {"allPlays": []},
                },
            }
        return payload, policy.canonical_json_bytes(payload)

    config = feed_observer.ObserverConfig(
        runtime_root=Path(cast("str", value["runtime_root"])),
        custody_root=Path(cast("str", value["custody_root"])),
        feed_launch_manifest=Path(cast("str", value["feed_launch_manifest"])),
        queue_launch_manifest=Path(cast("str", value["queue_launch_manifest"])),
        heartbeat_path=Path(cast("str", value["heartbeat_path"])),
        job_gate_path=Path(cast("str", value["job_gate_path"])),
        stop_sentinel=Path(cast("str", value["stop_sentinel"])),
        public_root=Path(cast("str", value["public_root"])),
        schedule_snapshot_path=Path(cast("str", value["schedule_snapshot_path"])),
        completion_receipt_path=Path(
            cast("str", value["completion_receipt_path"])
        ),
        terminal_manifest_path=Path(cast("str", value["terminal_manifest_path"])),
        terminal_event_log_path=Path(
            cast("str", value["terminal_event_log_path"])
        ),
        terminal_state_path=Path(cast("str", value["terminal_state_path"])),
        launch_nonce=cast("str", value["launch_nonce"]),
        source_sha256=cast("str", value["source_sha256"]),
        created_at=cast("str", value["created_at"]),
        hard_stop_at=cast("str", value["hard_stop_at"]),
        schedule_start=datetime.fromisoformat(
            cast("str", value["schedule_start"])
        ).date(),
        schedule_end=datetime.fromisoformat(cast("str", value["schedule_end"])).date(),
    )
    with (
        patch.object(feed_observer, "bounded_get_json", fixed_http),
        patch.object(feed_observer, "POLL_TARGET_SECONDS", 0.01),
        patch.object(feed_observer, "FINAL_SETTLE_SECONDS", 0.0),
    ):
        result = feed_observer.run_observer(config)
    raise SystemExit(result)


if __name__ == "__main__":
    main()
