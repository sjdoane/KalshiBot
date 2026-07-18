# V33 feed lock2 and queue lock3 terminal failure

Date: 2026-07-18.

## Binding verdict

Feed lock2 and queue lock3 are terminal failed evidence. Both stopped
fail-closed and all three process locks are absent. These signatures cannot
restart, authorize capital, or contribute any row to a replacement gate.

Feed lock2 ended with 20 eligible triggers across four games, four completed
play revisions, nine posteligibility violations, no exact endTime-only policy
exercise, and `gate_met=false`. Queue lock3 ended with five hypothetical
submissions across two games, two queue-cycle gaps, `feed_gate_met=false`, and
`gate_met=false`. No real order or capital endpoint existed in either process.

## What actually failed

Three material rows were transient complete-to-incomplete regressions of the
current at-bat, with normalized `after=null`. Their delays from the prior
completed endTime were 25.878390, 25.506998, and 27.530841 seconds. One separate
description-only edit arrived after 30.023254 seconds. All four revision pairs
have before and after raw payloads that independently hash-match the event
evidence.

The frozen feed policy treated any completed-play revision anywhere in a game
as a disruption to every prior eligible trigger. That game-wide taint created
nine violations even though none of the three material changes altered a prior
scoring trigger, reduced its score basis, or changed its trigger identity. This
does not show that the 60-second trigger guard was too short. It shows that the
taint dependency was too broad. Lock2 cannot be retroactively reinterpreted.

The two queue gaps were 33.171421 and 45.061671 seconds, but the process was not
stalled. It emitted 10 and 14 `feed_generation_advanced` rows during those
intervals. The frozen gap metric ignored completed loop outcomes whenever the
feed generation advanced during public market and trade reads. Under the
locked definition the gaps still fail queue lock3.

## Separate operational findings

The queue terminal summary and receipt bind each other and the exact terminal
event log, but the consumed feed generation was overwritten before feed
shutdown. The official cross-feed terminal verifier therefore cannot reproduce
that historical generation. This is a High terminal-sealing defect.

The supervisor again read a blank child exit code after `WaitForExit()` and
`Refresh()`. It correctly treated the missing value as fatal, but this proves
that `Process.ExitCode` is not a usable custody receipt in this launcher. This
is a separate High finding.

A replacement must archive every consumed feed generation or embed the exact
feed summary bytes in its queue receipt. Shutdown must freeze feed publication,
let queue seal that exact generation, then stop queue. The child must publish a
durable exit receipt with PID, terminal generation and hashes, and explicit
status.

## Terminal seals

The canonical bundle method uses rows of relative slash path, TAB, byte count,
TAB, lowercase file SHA256, and newline. Rows use ordinal sorting, UTF-8 without
BOM, and a final SHA256 over the complete row payload.

- Feed bundle: 939 files, 36,433,061 bytes, SHA256
  `27b540cac297360ce0cb99b6e8bc67f79404b0f23c8782d61fa0ab5ef3cee5ca`.
- Queue bundle: 9 files, 4,556,518 bytes, SHA256
  `25e3d51f23f440d21c0f1b7bf0ce642faaf1b7ce60ffd4eb0d74341419eb8089`.

An independent process reproduced both seals exactly. The machine-readable
record is `data/v32/v33-lock2-lock3-terminal-seal.json`.

## Replacement boundary

A fresh primary continuation may test trigger-local tainting only if locked
before recomputing this failed run. Direct dependencies are the trigger's own
completed play and identity, score regression below its post-total basis,
review ambiguity affecting that play, or another explicitly enumerated
determination dependency. Unrelated active-play regressions remain feed-quality
telemetry but do not automatically taint every earlier trigger.

Queue liveness must count every completed loop outcome, including a coherent
generation advance, while separately measuring time to a receipt-backed
snapshot. All replacement signatures, schemas, paths, logs, receipts, locks,
and source hashes must be fresh. Historical profitability testing and capital
remain prohibited until a new prospective gate passes.
