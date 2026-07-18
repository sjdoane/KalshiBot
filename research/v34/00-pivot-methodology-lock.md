# V34 pivot methodology lock

Locked 2026-07-18 before recomputing failed v33 evidence or starting a new
observer.

## Decision

V33 feed lock2 and queue lock3 are terminal failed evidence. V34 is a fresh
prospective candidate that keeps the same structured-score threshold mechanism
but corrects two dependency and custody definitions exposed live. It also opens
a separate, read-only derivatives sidecar. The sidecar cannot weaken, combine
with, or authorize the primary candidate.

Historical profitability and all capital remain prohibited until a fresh v34
prospective gate passes. No v33 trigger, eligibility, queue opportunity,
latency, or gate value carries into v34.

## Primary mechanism

After a completed MLB at-bat raises the official structured cumulative score
above a KXMLBTOTAL threshold, a future money path may quote the provisionally
determined YES side at 99c. The fixed historical correction guard remains 60
seconds. Trigger identity, mapping policy, sample minima, fee rules, finality,
and the initial 30 percent pilot cap remain unchanged.

## Frozen trigger dependency closure

The failed v33 policy tainted every prior trigger when any completed play in the
same game changed. V34 scopes a trigger to a frozen ordered prefix while
preventing later scoring from masking a correction inside that prefix. The
machine-readable policy is
`research/v34/01-primary-policy-lock.json`. Its canonical JSON SHA256 is
`6c85a6a901fd0f4c0eb639869b0f43bf438e24c5ea1f7739827e81c6361b80d0`
after serialization with sorted keys, compact separators, and UTF-8.

For a trigger at at-bat index i, v34 freezes every official play from index zero
through i, the exact prefix fingerprint, the trigger play identity, pre-total,
post-total, run delta, first-seen time, and immutable eligibility time. Every
queue opportunity also freezes its market ticker and threshold and must prove
pre-total is less than or equal to the threshold while post-total is strictly
greater than the threshold.

After every new state, v34 reconstructs that same prefix from official data.
Any missing, duplicate, reordered, incomplete, malformed, review-changed, or
score-changed prefix play is fatal. Score redistribution inside the prefix is
fatal even when later runs keep the current game total above the frozen
post-total. A threshold crossing that no longer holds is fatal. Unknown fields,
identity, or reconstruction are fatal.

Timing and descriptive fields remain outside the prefix fingerprint.
Description, event label, RBI, and isScoringPlay changes can remain telemetry.
An endTime change is nonfatal only when every prefix time remains parseable,
timezone-aware, not in the future, and the immutable eligibility time remains
strictly more than 60 seconds after both first sighting and the latest current
prefix endTime. The isScoringPlay flag remains evidence only.

A later suffix change is unrelated only after the exact prefix fingerprint,
same crossing, current-total floor, allowed game status, feed continuity, and
review rules all reverify. A transient complete-to-incomplete suffix state can
therefore remain telemetry without invalidating an earlier unchanged prefix.
This policy is hindsight-informed by v33, frozen before any v34 replay or live
evidence, prospective only, and cannot rehabilitate v33.

## Frozen liveness, archive, and custody

The numeric policy is locked in
`research/v34/01-primary-policy-lock.json`. Both processes target a
three-second cycle. Each HTTP call has two attempts, a five-second timeout per
attempt, and one 0.25-second inter-attempt delay. An individual failed attempt
is not a heartbeat. The full cycle maximum is 30 seconds. A durable monotonic
progress heartbeat may not age beyond 12 seconds, and the independent
supervisor checks it once per second and kills the complete owned process tree
when the strict boundary is crossed. Feed successful-poll gaps remain capped at
10 seconds per live game. Queue time without a coherent feed snapshot is capped
at 12 seconds.

The heartbeat contains a launch nonce, exact PID and process creation time,
sequence, phase, monotonic nanoseconds, UTC audit time, prior heartbeat hash,
and source and policy hashes. A retry can publish progress only when its
terminal success or fatal terminal failure completes inside the full frozen
budget. Wall time never determines elapsed duration.

Queue snapshot reads use exactly eight attempts with 0.05 seconds between
attempts and a one-second total read bound. Each attempt reads exact
receipt-before bytes, summary bytes, and receipt-after bytes. The receipts must
be byte-identical and bind the exact summary hash.

Every coherent feed pair consumed at cycle start, cycle end, or terminal
handshake is content-addressed and durably archived before any market decision.
This includes no-submit cycles and generations used only to detect an advance.
Existing identical bytes are idempotent; any collision is fatal. Every loop
outcome binds its archive receipt. A create-once terminal archive manifest
lists every consumption and every unique archived generation.

Every submit, skip, or order mutation is staged in memory. After public market
reads, queue archives a second coherent feed pair and requires exact equality
of its generation ID and summary hash to the start pair. It then reconstructs
the prefix, crossing, eligibility, and freshness again from the end pair. Only
after all checks pass can one fsynced decision-commit event record the complete
mutation and both archive receipts. The state cache is derived from that
durable event log. If generation changes, every staged mutation is discarded
and only a feed-generation-advanced heartbeat is appended.

A Python subprocess custodian, not the child and not PowerShell
`Process.ExitCode`, holds the direct process handle for both feed and queue.
It records the actual OS return code after exit and binds the launch nonce,
PIDs, creation times, command, source and policy hashes, stop sentinel,
terminal artifacts, and child intended-clean-completion receipt. Feed custody
binds a feed-owned terminal artifact manifest created before feed exit. Queue
custody separately binds its final all-consumption archive manifest and
terminal-feed acknowledgement. A clean child receipt is intent evidence only.
Success also requires wrapper, child, and descendants absent by PID, creation
time, nonce, and command line, with every owned lock absent.

Shutdown publishes the feed stop sentinel first. After feed terminal
publication and an independently observed zero exit, queue must archive and
acknowledge that exact terminal pair within 60 seconds. Only then is queue
stopped and sealed. Missing acknowledgements, nonzero exits, forced kills,
stale PIDs, receipt-then-crash cases, remaining descendants, or remaining locks
are fatal. A final outer supervisor receipt binds both completed custodian
receipts, the terminal acknowledgement, and global process and lock absence.

## Fresh prospective gate

V34 requires from its own fresh run:

- at least 20 clean eligible triggers across at least five final games;
- at least 20 depth-aware shadow submissions across at least five games;
- at least one genuinely fresh exact endTime-only revision exercise credited
  only when a posteligibility revision changes exactly `/about/endTime` for a
  play inside an eligible trigger's frozen prefix, exact before and after
  states are archived, eligibility remains immutable, the guard is recomputed,
  the fingerprint is unchanged, and every prefix and crossing check passes;
- every eligible game final;
- zero trigger-local determination violation, score regression, feed error,
  prohibited status, true liveness gap, unrecoverable snapshot failure, receipt
  mismatch, mapping transition, or custody failure;
- immutable first eligibility timestamps and exact end-to-end queue latency.

Kill the candidate on any violation. Do not refit the guard, thresholds, sample
minimums, or capital rule from the prospective run.

Freshness is mechanical. Feed signature
`prospective-v34-20260718-lock1` uses schema 8 and queue signature
`prospective-queue-v34-20260718-lock1` uses schema 9 under
`data/v34`. They have new output roots, locks, JSON stop sentinels,
heartbeats, archives, receipts, and launch nonces. A create-once launch manifest
must bind every code and policy hash, the correction manifest, exact processes,
empty-start assertions, start time, and hard-stop time before observation. The
maximum horizon is 24 hours. Any v33 signature, path, generation, state, row, or
prospective artifact is hard-rejected. The sole exception is the exact
hash-bound historical correction manifest
`4b334616454f170ad9f7c909f353e68f1f12968b2ac5d94ee2a348b2ca8ef94e`,
used only to preserve the frozen guard. No v33 prospective evidence is
permitted. If the exact endTime-only exercise is absent at the hard stop, v34
fails rather than extending the horizon.

## Derivatives sidecar

The exact sidecar lock is
`research/v34/02-derivatives-lattice-lock.md`. It models any nonnegative
integer quantities and a guaranteed-payout variable bounded by payoff in every
atomic outcome cell. A displayed-depth candidate requires guaranteed payout
minus executable ask cost minus exact per-leg rounded fees to be strictly
positive. This captures profitable baskets whose cost and minimum payout both
exceed one dollar.

Atomic cells include open intervals, both tails, and singleton strike
boundaries where inclusivity changes. Only contracts with identical underlying,
window, source, rules, and exceptional-settlement treatment may combine. Every
candidate must survive independent payoff verification and five complete
copies of its primitive integer recipe at a net edge of at least 0.02. These
size and edge constraints are enforced inside complete candidate enumeration,
not applied after choosing one absolute-profit optimum.

These are displayed-depth candidates, not locked realized arbitrages, because
multi-leg orders are non-atomic. Three distinct candidates with one consecutive
repeat would authorize only a separately reviewed atomicity and legging-risk
design. It would not authorize a pilot or an order.

Incrementality requires the exact v29 rule and every one-leg, two-leg, proper
subrecipe, and lower-support dominance check to fail at the same snapshot.
Economically equivalent payoff vectors collapse. At most one result counts per
event and snapshot. The gate requires three distinct event tickers spanning at
least two event dates or monthly cohorts. Same-event observations are
persistence telemetry only and cannot increase the independent count.

The existing v29 pair sentinel stays unchanged. It has 4,004 logged rows, 71
completed burst sessions, and zero sightings at this lock. The full lattice
sidecar must identify an irreducible relation that v29 cannot represent.

Current product inspection found defined daily and weekly Bitcoin maximum
series but no open or settled markets in either. Live monthly Bitcoin maximum
and minimum one-touch ladders exist, with only three monthly event cohorts
having populated market data per active family and July still active. They are
suitable for read-only implied-barrier and no-arbitrage measurement, not
supervised return modeling or capital.

## Modeling discipline

Complexity must address an observed bottleneck:

- A state-space or constrained spline model may denoise the digital-option CDF,
  but the raw no-arbitrage basket is the execution authority. Model residuals
  are diagnostics only until out-of-sample net returns beat the raw market mid.
- A correction-hazard survival model requires at least 100 unique trigger-play
  clusters across at least 50 final games, at least 30 independent official
  correction episodes spanning at least 15 corrected games, and three
  chronological folds each containing at least five positive episodes across
  at least three corrected games plus five censored clusters spanning at least
  three censored games. One episode groups all thresholds and triggers affected
  by the same game and revision sequence. Every row from one game stays in
  exactly one chronological fold assigned by game start, with a 24-hour
  boundary embargo. Observation starts at first trigger sighting and censors
  only at verified game finality.
- A queue fill-hazard model cannot select or size trades from inferred shadow
  fills. It requires at least 100 actual reviewed live order-priority outcomes,
  at least 30 fills across 15 events, 30 nonfills across 15 events, and at least
  30 events total. Each of three chronological folds requires positive labels
  across at least three events and negative labels across at least three
  events. Every outcome from one event ticker stays in exactly one fold assigned
  by event close time, with a 24-hour boundary embargo. Shadow labels remain
  diagnostic.
- Any future model uses chronological purged validation, event-clustered
  uncertainty, the market mid as the canonical baseline, current fees and
  executable asks, and a frozen holdout. TabPFN, LightGBM, isotonic, and logistic
  work already showed that model lift over a weaker baseline is not tradable
  edge.

Until those independent-sample and class minima exist, machine learning cannot
select or size trades. The immediate v34 work is correctness, live evidence,
and arithmetic derivatives measurement.

## Kill criteria

Kill v34 primary if exact prefix reconstruction fails, the fresh exact policy
exercise is absent, any prospective gate fails, the hard horizon expires, or
terminal custody is not reproducible. Kill the derivatives sidecar as an
execution candidate if its expanded scan adds no qualifying displayed-depth
candidate by the existing v29 close horizon on 2026-08-15. Keep all balance and
sizing decisions independent of these evidence rules.
