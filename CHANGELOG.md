# Changelog

## 2026-07-18

- Implemented and independently reviewed GO the read-only v34 derivatives
  arithmetic core. It uses exact rational atomic cells, integer five-copy
  recipes, exact aggregate per-leg fee ceilings, and a two-percentage-point
  edge test without floating arithmetic. It fails closed before any incomplete
  recipe or irreducibility scan can return a result.
- Added published incrementality evidence for the exact v29 pair rule, every
  qualifying support-one or support-two recipe with the same normalized payoff
  relation, every profitable proper subrecipe, and every lower-support
  componentwise dominator. Equivalent recipes retain the exact best
  representative per event snapshot.
- Adversarial reviews found and closed false-candidate routes involving an
  unequal-quantity two-leg relation, Decimal midpoint and tail rounding,
  nonfinite strikes, duplicate exceptional states, Boolean integer aliases,
  and unbounded quadratic audit work. The complete v34 suite now has 80 passing
  tests with Ruff and strict mypy clean.
- Rechecked the live July Bitcoin maximum and minimum ladders at 22:13 UTC.
  Each then had seven open markets, quadratic fees with multiplier one, current
  fixed-point quotes, and null legacy integer quote fields. All seven minimum
  contracts had directionally inconsistent primary and secondary rule text, so
  the frozen compatibility gate excludes that event. The maximum event had no
  such mismatch. This inspection received zero candidate or gate credit.
- Implemented and independently reviewed the first v34 correctness and decision
  core. It reconstructs exact ordered prefixes, rejects score-component
  regressions, freezes the threshold-crossing basis, verifies whole-prefix
  exact endTime exercises, and binds every decision to canonical launch and
  parent feed-state provenance.
- Added stable-generation decision commits, structured eligibility and end
  proofs, a hash-chained event log, and semantic state-cache recovery that
  cannot retain phantom orders. Repeated adversarial reviews found and closed
  all Critical and High issues. The settled v34 suite has 43 passing tests with
  Ruff and strict mypy clean.
- Reproduced the v34 prefix logic on a real archived MLB payload with SHA256
  `ce79fe32bb7f02661e63ba73fae466c585e20cd59c55dec30adfb011aaab6a28`:
  50 completed plays and five exact scoring prefixes. This smoke test received
  zero prospective gate credit.
- Inspected the live public July Bitcoin maximum and minimum event ladders at
  21:17 UTC. Each had eight markets, but an orderbook-backed exploratory v29
  pair scan found zero candidates. The result is read-only telemetry and earns
  zero derivatives sidecar credit.
- Rechecked authenticated exchange truth at 21:27 UTC: $5.77 cash, $3.76
  portfolio value, five positions, $3.70 exposure, one unfilled one-contract
  97c v30 rest, and zero fills in the preceding 24 hours.
- Stopped and terminally failed v33 feed lock2 and queue lock3. Feed lock2
  finished with 20 eligible triggers across four games, four revisions, nine
  posteligibility violations, no fresh exact endTime-only exercise, and a false
  gate. Queue lock3 finished with five hypothetical submissions across two
  games, two frozen-definition cycle gaps, and a false gate. No capital
  endpoint existed.
- Diagnosed the mechanism rather than refitting the guard. Three transient
  current-at-bat complete-to-incomplete states arrived within 27.54 seconds,
  while v33's game-wide taint invalidated unrelated earlier triggers. The
  60-second correction guard remains fixed; v34 must instead reconstruct and
  fingerprint the complete official play prefix through each trigger.
- Independently sealed and reproduced the terminal v33 feed and queue bundles
  at SHA256
  `27b540cac297360ce0cb99b6e8bc67f79404b0f23c8782d61fa0ab5ef3cee5ca`
  and
  `25e3d51f23f440d21c0f1b7bf0ce642faaf1b7ce60ffd4eb0d74341419eb8089`.
  Recorded the separate overwritten-feed-generation custody defect and blank
  PowerShell child ExitCode finding.
- Locked the v34 pivot before any replacement replay or observation. Initial
  independent reviews returned NO-GO and identified incomplete prefix closure,
  tunable liveness, incomplete all-cycle archives, self-attested exits,
  declarative freshness, an incorrectly unit-normalized lattice objective,
  multi-leg atomicity risk, and correlated ML sample minima.
- Amended v34 methodology to close those findings. The canonical primary policy
  SHA256 is
  `6c85a6a901fd0f4c0eb639869b0f43bf438e24c5ea1f7739827e81c6361b80d0`.
  It freezes full prefix reconstruction, exact crossing fields, numeric HTTP
  and monotonic heartbeat limits, every-consumption feed archives,
  independently observed OS exits for feed and queue, mechanical fresh-start
  assertions, and a maximum 24-hour horizon. Independent rereview is in
  progress before implementation.
- Closed the second review's remaining specification gaps before code:
  decisions now commit only after identical archived start and end feed
  generations plus repeated prefix checks; feed and queue have separate
  terminal manifest schemas and an outer custody receipt; the historical
  correction manifest is the sole permitted v33-named artifact; the required
  timing exercise must occur after eligibility inside the frozen prefix; and
  lattice candidates must be irreducible, fully edge-enumerated, and
  event-independent. ML positive and negative labels now have per-fold event
  minima. A third independent methodology review is in progress.
- Closed the final evidence-independence review findings by requiring three
  distinct derivative event tickers across at least two dates or cohorts and
  treating all same-event repeats as persistence only. Correction modeling now
  requires censored rows across three censored games per fold, while every game
  or event group stays wholly inside one chronological fold with a 24-hour
  embargo. The recomputed canonical policy hash is the value above.
- Received final independent methodology GO from both reviewers with no
  remaining Critical or High finding. Both reproduced canonical policy SHA256
  `6c85a6a901fd0f4c0eb639869b0f43bf438e24c5ea1f7739827e81c6361b80d0`.
  V34 may now enter implementation, but replay, observation, and capital remain
  prohibited until code and launch reviews pass.
- Added a separate read-only derivatives lattice lock. Its integer objective
  maximizes guaranteed payout minus executable ask cost and exact rounded fees
  across every atomic outcome cell. It supports baskets above one dollar,
  singleton strike boundaries, primitive five-copy depth, and independent
  arithmetic verification. Multi-leg results are non-atomic candidates only.
- Rechecked v29 at 4,004 rows and 71 completed bursts with zero sightings.
  Rechecked production at 20:26 UTC: $5.77 cash, $3.76 portfolio value, five
  positions, $3.70 exposure, one unfilled one-contract 97c v30 rest, and zero
  fills in the preceding 24 hours.
- Failed feed lock1 and dependent queue lock2 as binding evidence after live
  observation exposed a High integrity defect: `eligible_at` drifted to each
  later valid poll and could understate queue latency. Both observers stopped
  cleanly and none of their rows can authorize or contribute to replacement
  gates.
- Implemented the frozen minimal first-poll-only fix and fresh feed lock2,
  queue lock3, schemas, paths, locks, sentinels, receipts, logs, and supervisor.
  Added strict boundary, immutability, later-disruption, and old-feed rejection
  coverage. All 140 v33 tests pass with Ruff, strict mypy, and PowerShell
  parsing clean. Independent prelaunch review returned GO with no Critical or
  High finding.
- Started fresh read-only feed lock2 at 18:01:39 UTC and queue lock3 under its
  reviewed supervisor at 18:02:16 UTC. The replacement began with baseline
  rows only, empty order state, zero submissions, empty error logs, and a hard
  15:55 UTC July 19 deadline. No capital path was enabled.
- Received independent postlaunch GO for continued read-only observation with
  no Critical or High finding. The audit verified every frozen hash, all five
  process identities, all three locks, coherent receipts, no failed-run reuse,
  empty queue order state, and no private exchange or capital endpoint. Both
  fresh gates remain false, so capital remains prohibited.
- Recorded the first replacement live evidence by 18:40 UTC: four clean
  eligible score increases across two games. Every `eligible_at` is the first
  poll strictly after 60 seconds and remains immutable across later polls,
  directly exercising the repaired defect. All fatal feed counters remain
  zero. Queue lock3 remains at zero submissions because one game is the locked
  zero-credit doubleheader exclusion and the mapped game's total remained below
  its lowest live threshold.
- Received independent first-trigger GO with no Critical or High finding after
  rehashing all four exact MLB payloads, proving every strict sub-60 and first
  post-60 boundary, checking later immutable confirmations, verifying both
  receipt chains, and measuring queue cycles within 2.094 seconds of each
  eligibility. The review confirmed queue silence is expected rather than a
  missed trigger.
- Reverified production truth at 18:40 UTC: $5.77 cash, $3.71 portfolio value,
  five positions with $3.70 exposure, one resting one-contract v30 TSA YES bid
  at 97c, and zero fills in the preceding 24 hours.
- Preserved v33 queue lock1 as failed pretrade evidence after the public PIT at
  CLE event timestamp was exactly 10,800 seconds from each of two same-day MLB
  doubleheader games. The frozen mapper returned `ambiguous_time_match`; the
  process exited before acquiring its lock and created no output directory,
  event, state, summary, receipt, shadow order, or capital path.
- Locked a fresh queue lock2 policy before implementation. It may exclude only
  an exact unresolved minimum-distance tie whose candidates have no status
  reason or exact `rescheduled_game`, records every tied candidate and status,
  gives the event zero market and gate credit, and leaves every other mapping
  failure fatal. Independent methodology review returned GO.
- Closed two High implementation findings before launch. Queue lock2 now
  persists every unique assignment before discovery, binds event ticker and
  game identity to every order, kills unique-to-ambiguous transitions before
  reconcile or publication, and rejects assignment and exclusion overlap. It
  also pins and artifact-binds shared mapper SHA256
  `db547b9cde54b7228d9bad40956b86786e743480a8183ecc11e001d7c554f57b`.
  Independent rereview returned GO. The v33 suite has 137 passing tests with
  Ruff and strict mypy clean.
- Preserved one Windows launcher quoting failure that occurred before the
  supervisor script executed and created no lock or queue artifact. A fresh
  quoted launch started the reviewed lock2 supervisor at 17:10:55 UTC and queue
  runtime at 17:10:58 UTC. The first verified summary binds 14 assignments and
  one zero-credit PIT at CLE exclusion, with zero submissions, snapshot
  failures, or queue gaps. Both process logs are empty.
- Received independent post-launch GO with no Critical or High finding after
  rechecking every source hash, process and lock, hard deadline, summary and
  receipt binding, zero-credit exclusion, empty order state, public-only v33
  endpoint surface, and authenticated absence of any v33 exchange order.
- Recorded the first clean v33 feed trigger at 17:36 UTC: game 824414, at-bat
  10, increased the official score by two runs to 2-0. Feed progress is one of
  20 triggers and one of five games. One earlier review correction and one
  later description-only edit were classified as intended before eligibility,
  with zero feed error, gap, regression, timing revision, or posteligibility
  finding. Queue lock2 correctly gives the ambiguously mapped PIT at CLE event
  zero submission and gate credit.
- Completed and independently sealed v32 feed lock5 after its scheduled
  18-hour audit window. Both processes and the exclusive lock are absent, both
  process logs are empty, both local and binding terminal summary pairs verify,
  and the canonical 4,284-file, 191,727,777-byte tree has SHA256
  `9ef625f7b224879b664df11e80dcd9cb3be4ebf5f0748e679eff1e755d768e36`.
  The terminal gate remains false with exactly one posteligibility violation,
  so this seal preserves failed evidence and authorizes no capital.
- Reverified production truth at 17:36 UTC: $5.77 cash, $3.48 portfolio value,
  five positions with $3.70 exposure, one unfilled one-contract v30 Arm D TSA
  YES bid resting at 97c, and zero fills in the preceding 24 hours.
- Preserved feed lock5 as permanently failed v32 evidence after an exact
  end-time-only revision occurred four seconds after eligibility in game
  824170, at-bat 5. The frozen artifact remains unmodified and continues only
  to its terminal audit receipt.
- Preserved queue lock6 as failed evidence after its unguarded second feed read
  observed a torn summary and receipt generation. Recorded exact event, state,
  summary, receipt, and stderr hashes. The queue is stopped and cannot restart.
- Locked the v33 determination-impact reset before prospective observation or
  outcome backtesting. Score, sequence, completion, review, status, malformed,
  and unknown changes remain fail-closed. End-time-only changes cannot change
  game-scoped trigger identity or refit the correction guard.
- Implemented a fresh v33 feed and queue family with stable receipt-summary-
  receipt reads, one captured generation per cycle, globally fatal successful-
  cycle gaps, exact end-time-only exercise, future-timestamp rejection, and
  all-eligible-games-final gating.
- Preserved correction lock1 as failed partial evidence after MLB returned an
  unadvertised intermediate timestamp. Its two completed files and stderr are
  hash-recorded and it has no manifest.
- Locked and independently approved correction lock2's two exact source rules.
  One unadvertised intermediate state requires an exact full-payload replay.
  Four advertised-boundary raw variants collapse to one state only under one
  identical raw-derived determination hash and emit no synthetic revision.
- Closed two High lock2 verifier findings. Strict-interior confirmation is
  mandatory during replay, and all 730 legacy files are now cross-checked from
  raw payloads for scores, statuses, current gate flags, and completed plays.
  Exact source-set checks compare literal filenames.
- Received final independent code GO on builder SHA256
  `720484738a46ccb7bf2836c29290122558ff3b8f900812593c60639894abc447`
  and started the fresh read-only lock2 historical build under both exclusive
  locks and an empty output directory.
- Completed correction lock2 and independently replayed its full verifier in a
  separate process. Both passes reproduced terminal manifest SHA256
  `4b334616454f170ad9f7c909f353e68f1f12968b2ac5d94ee2a348b2ca8ef94e`
  across 735 games and 357,307 raw retained states, with zero determination
  revision, null delay p95, and the frozen 60-second guard.
- Bound that exact historical manifest and fixed guard into the new v33 feed
  and queue. Prospective delay remains diagnostic and cannot refit strategy
  eligibility. The final independent observer review returned GO with no
  Critical or High finding. All 134 v33 tests pass, and Ruff and mypy are
  clean.
- Started fresh read-only v33 feed lock1 at 05:30:12 UTC from an empty artifact
  set. Verified its process, exclusive lock, exact reviewed code hashes, and
  empty logs.
- Stopped the first queue watcher before any queue artifact after independent
  audit found a High duration-custody flaw: a delayed fixed 16-hour queue could
  outlive the 30-hour feed. Added a replacement supervisor that validates the
  first receipt-backed summary, derives queue duration from a hard pre-feed
  deadline, monitors both process locks, and requests clean queue stop if feed
  custody disappears. Closed follow-up High findings around original feed PID
  continuity, concurrent launch ownership, post-launch exception cleanup,
  forced process-tree cleanup, and final custody checks. Independent rereview
  returned GO on exact SHA256
  `fd9a27dccdf12bca11ea38bbbb4f0f07072ba127db4e7e3cd75f542e3befeafb`.
- Started the corrected single-owner supervisor at 05:58:12 UTC. Verified its
  PID 54940, exclusive lock, original feed PID 60364 binding, strict 11:25 UTC
  queue deadline, empty error log, and continued absence of every queue
  artifact before the first live-game feed summary.
- Reverified production truth at 05:35 UTC: $5.77 cash, $3.49 portfolio value,
  five positions, one unfilled one-contract Arm D TSA YES bid resting at 97c,
  no fill after the invalid July 11 Moana fills, and no v32 or v33 deployment.

## 2026-07-17

- Audited the complete v1 through v31 strategy history, scheduled processes,
  recent fires, exchange state, fills, losses, and current order truth.
- Confirmed the v30 live pilot is the only scheduled money writer. Its Arm E
  has no orders or fills, and its recent qualifying scans lacked executable
  supply at the quoted price.
- Rejected v31 for live use because its claimed cadence and fill model did not
  survive review and its stop and exposure controls were unsafe.
- Locked v32 KXMLBTOTAL methodology with a 30 percent strategy cap, explicit
  historical-data limits, prospective gates, and precommitted kill criteria.
- Completed immutable binding collection for 740 events, 735 matched games,
  9,148 markets, and 5,961,525 reconciled trades.
- Added full retained-timecode MLB correction collection with raw all-play
  evidence, revision detection, immutable manifests, restart-safe cache
  validation, rate limiting, and current-base provenance checks.
- Added the locked v32 backtest with reachability-only 97c and 98c treatment,
  queue-only historical 99c treatment, continuous correction guards, complete
  correction reporting, and explicit G1 composition in G4.
- Resolved all Critical and High methodology and code-review findings. The
  independent pre-pull verdict is GO; 24 tests pass and static checks are clean.
- Installed a recurring same-task heartbeat for autonomous continuation.
- Started the independently reviewed read-only prospective MLB observer. It
  records unchanged-poll heartbeats, raw hashes, revisions, regressions, review
  and status state, feed gaps, and end-to-end processing latency. Its gate is
  fail-closed on stale evidence and has no order-placement path.
- Started the independently reviewed depth-aware 99c Kalshi queue shadow. It
  sits hypothetically behind displayed depth, uses canonical public trade
  direction, and derives restart state from an fsynced event stream.
- Preserved all pre-final-review prospective output as excluded pilot evidence,
  then started clean binding runs with signatures
  `prospective-20260717-lock1` and `prospective-queue-20260717-lock1` only after
  both independent GO verdicts.
- Verified the correction pull survived its shell-wrapper timeout and continued
  under its child lock, reaching 133 cache files and 3.57 GB. Verified both
  signed prospective collectors remain alive, continuously writing, and have
  empty stderr logs.
- Preserved queue lock1 as failed binding evidence after a transient OneDrive
  access denial killed an atomic state-cache replacement before any shadow
  submission. Recorded exact hashes and excluded the run from every gate.
- Added bounded atomic-replace retry with persistent fail-closed behavior and
  tests for both transient and sustained denial. Full v32 verification now has
  40 passing tests, Ruff clean, and mypy clean. Independent rereview returned
  GO and `prospective-queue-20260717-lock2` is live.
- Stopped and froze feed lock1 after one exact description-only MLB wording edit
  triggered two post-eligibility violations under the frozen all-change rule.
  Lock1 remains failed, its dependent queue lock2 is nonbinding, and neither run
  may contribute evidence to a replacement gate.
- Recorded canonical tree and key-file hashes for both stopped runs. Independent
  methodology review approved only an exact `/result/description` carveout with
  complete-path comparison and malformed or unknown changes defaulting to
  material.
- Added one shared hash-bound revision classifier for prospective and historical
  paths, feed lock2 schema 2, queue lock3 schema 2 with exact feed binding, and
  versioned backtest output that leaves correction lock5 immutable. The expanded
  suite has 73 passing tests, with Ruff and mypy clean. Fresh code review is in
  progress before either collector starts.
- Recorded the operator's latest capital authorization: keep the strategy and
  initial 30 percent pilot unchanged, but permit eventual scaling up to all free
  Kalshi cash after the full historical, prospective, operational, and durable
  live-evidence gates pass. Current low cash does not alter edge selection.
- Resolved three High amendment-review findings: correction delay now uses the
  maximum parseable before/after end-time delay and fails closed if neither
  parses; historical finding collections reject non-object rows; and missing
  `review_details` cannot masquerade as explicit null. Rereview returned GO with
  no remaining Critical or High finding.
- Started fresh `prospective-20260717-lock2` and
  `prospective-queue-20260717-lock3`. Verified schema 2, empty inherited state,
  exact policy and code hashes, exact queue-to-feed signature and summary-path
  binding, active process locks, and empty stderr for both.
- Found a Critical trigger defect during a read-only full-base diagnostic before
  either fresh process recorded a trigger or order. The MLB cumulative score
  increased on 93 completed at-bats across 91 games while `isScoringPlay` was
  false, including strikeouts, field outs, walks, singles, a hit by pitch, and
  a fielder's choice out.
- Stopped feed lock2 and queue lock3 cleanly at zero trigger rows and zero shadow
  orders. Preserved both directories and canonical hashes as aborted,
  nonbinding evidence. No money was deployed.
- Received independent methodology GO for a fresh structured cumulative-score
  amendment and NO-GO for reusing either aborted run or any prior derived
  metric.
- Added one shared completed-run-increase implementation for historical
  crossings, prospective first-seen detection, and heartbeats. It enforces a
  contiguous sequence from at-bat index 0, exact structured scores and aware end
  times, nondecreasing cumulative totals, live and final linescore consistency,
  multi-run deltas, and fail-closed malformed or revised state.
- Added fresh isolated signatures for feed lock3, queue lock4, and run-increase
  backtest lock1. Queue state and events now pin both revision-classifier hashes
  and run-increase policy/code hashes, as well as the exact feed signature,
  schema, and summary path.
- Added a signed full-corpus trigger coverage builder and expanded regression
  coverage to 106 passing v32 tests. Ruff and mypy are clean, and independent
  code review is in progress.
- Closed five independent High findings in the structured-score family. Exact
  boolean review state and trigger arithmetic now fail closed, A/B/A trigger
  identity changes reset the guard, coverage binds one stable base-manifest
  snapshot, and feed publication uses an fsynced generation and hash receipt.
- Unified the prospective and historical timing contract. Queue lock5 measures
  actual crossing-to-submit and eligibility-to-submit latency. Historical
  simulation waits for both exact observed guard readiness and the full measured
  publication plus execution delay, and tests prove an earlier trade is not
  credited.
- Independent timing and integration rereviews returned GO with no Critical or
  High findings. Full v32 verification is 146 tests passing, Ruff clean, and
  mypy clean.
- Published `trigger-coverage-20260518-20260715-lock2` atomically after a full
  735-game scan. It reproduced 93 false-flag score increases across 91 games,
  with cases payload SHA256
  `9070d087016399ef46bef3f098143b32263556d57f1983333364cbe68af892cd`.
- Started read-only feed lock4 and queue lock5. A launch-only package-path error
  occurred before either process created evidence and was corrected. The live
  queue then exposed one postponed event; a narrowly reviewed repair skips only
  authoritative prohibited or rescheduled mappings and preserves fatal handling
  for every other mapping failure. Both corrected observers are live under
  process locks and cannot place orders.
- Ran an early correction-lock5 integrity diagnostic while collection
  continued. All 368 completed artifacts had explicit empty regression and
  revision lists, and six evenly spaced files passed full recomputation across
  2,914 retained states. Final manifest verification remains mandatory.
- Evaluated the exact shared 60-second guard across the first 368 completed
  crossed games. A total of 366 passed. Games 823544 and 823861 were
  conservatively excluded because their retained streams ended 30 seconds
  after the crossing identity appeared, before the strict guard could be
  proven. Neither contained a regression, revision, exclusion, or settlement
  contradiction.
- Ran a real-print historical queue sensitivity at 60, 90, 120, 180, and 300
  seconds across 5,087 crossed markets. Every cell cleared the frozen
  queue-opportunity thresholds. Even at 300 seconds, 680 of 702 crossed games
  and all 56 active days had qualifying flow, with a 95.39 percent day-rate
  Wilson lower bound and 679 persistent games. The result is explicitly
  nonbinding and is not labeled a fill or P&L estimate.
- Repaired a queue-opportunity denominator defect found by independent audit.
  Crossed markets that are closed before hypothetical submission now emit an
  explicit zero-opportunity row instead of disappearing. Added a regression
  test, replayed all 5,087 real crossed-market rows, and confirmed 702 games at
  every latency. The corrected 180-second and 300-second rates are 687/702
  (97.86 percent) and 680/702 (96.87 percent). The gate verdict is unchanged.
  Two independent reviews returned GO with no Critical or High findings; the
  complete v32 suite passes 146 tests and Ruff and mypy are clean.
- Re-read production exchange truth and scheduled runtime state. Cash is now
  $5.77 and portfolio value is $3.50, with five nonzero positions, one live
  one-contract TSA YES bid at 97c, and zero fills since July 13. V30 Arm E has
  logged 610 scans and 161 intents without placing an order. Arms C and D placed
  three maker bids over the same interval; the first two closed unfilled and the
  third is the current rest. The small balance does not alter v32 strategy or
  evidence standards.
- Extended the in-progress correction integrity audit over six newly completed
  artifacts. The exact cache verifier recomputed 2,837 retained states and
  matched every raw hash, play projection, audit, final feed, score, provenance,
  and exclusion. Combined with the earlier sample, 12 artifacts and 5,751
  retained states have passed with zero regression or revision finding.
- Verified the exact prospective slate against current MLB and Kalshi data.
  Thirteen games remain after observer startup, beginning at 23:05 UTC, and 132
  open KXMLBTOTAL markets map exactly to 12 of them at 11 strikes per game. The
  sample has enough breadth for the frozen 20-trigger, five-game gate without
  importing the earlier completed game or the postponed game.
- Verified the current KXMLBTOTAL fee classification from production and
  Kalshi's official documentation. The series is `quadratic`, not
  `quadratic_with_maker_fees`, and has no scheduled fee changes. The current
  July 7 schedule sets the default maker multiplier to zero and does not list
  KXMLBTOTAL as nonstandard, establishing zero maker fee for an order that rests
  before filling. Recorded the dated evidence
  and fail-closed recheck rules in
  `research/v32/12-current-fee-and-slate-check.md`.
- Closed the fee/slate reviewers' provenance finding by publishing create-once
  snapshot `predeployment-snapshot-20260717T213156Z`. It retains raw series,
  fee-change, schedule, and market-page responses plus every mapped ticker.
  Independent local rehash matched all five files to manifest SHA256
  `56fc2502db66ac573e847216dc8f2c7040bc1de1de8cc32648a1cad98baa21be`.
  Added an explicit pre-POST checklist that requires fresh fee-horizon,
  exchange-exposure, market, book, resting-ack, and first-fill fee evidence and
  kills on an immediate taker race or nonzero fee.
- Preserved the exact current fee PDF in create-once artifact
  `fee-schedule-20260707-lock1`. Its 382,507 bytes hash to
  `815e2d5127d02d2fb90773d1a3844dc15a987696171eddc4e58de87b59c6124c`.
  Full text extraction plus visual review confirmed the effective date, default
  maker multiplier zero, KXMLBTOTAL absence, and KXMLBGAME exception.
- Closed a High fee-lifecycle review finding in the frozen money-path
  requirements. Any live v32 rest now requires a 10-second classification and
  fee-change watchdog plus a 60-second conditional fee-schedule hash check.
  Failure or change de-arms and confirms cancel-all. A lifecycle rereview caught
  that the fills endpoint exposes `fee_cost` and `is_taker`, not split maker and
  taker fee fields. Every partial and later fill must now match exact order IDs,
  report a present and parseable zero `fee_cost`, and report `is_taker=false`
  before receiving credit.
- The exact lifecycle closure rereview returned GO with no Critical, High, or
  Medium finding. The review certifies the frozen requirement, not a future
  money-path implementation.
- The independent quantitative rereview likewise returned GO at the requirements
  level and independently rehashed and inspected the official 12-page PDF. Its
  prior High lifecycle and Medium provenance findings are closed. Capital still
  requires a separate implementation review after all binding evidence passes.
- Rechecked all three active read-only collectors. Correction lock5 advanced to
  456 of 735 game artifacts. Feed lock4 and queue lock5 process pairs remain
  alive with empty stderr; before the 23:05 UTC first pitch, the absent feed
  summary and queue's `feed_summary_unavailable` rows are the expected
  fail-closed state.
- Refreshed authenticated exchange truth at 21:52 UTC. Cash remains $5.77,
  portfolio value remains $3.50, five positions remain nonzero, one v30 Arm D
  order remains resting 1x97c, and there are still zero fills since July 13.
- Found and repaired a stale production-schema bug in the read-only balance
  diagnostic. It had looked for legacy position and cent fields and printed zero
  positions on the current fixed-point and dollar-string response. The repair
  requires both authoritative balance fields, rejects missing, blank, malformed,
  nonfinite, negative, or fractional required values, validates page and row
  shapes, requests `count_filter=position`, drains all cursors without a cap,
  and kills repeated cursors.
- Added 33 focused diagnostic tests. A real production smoke returned exactly
  five nonzero positions, $3.70 exposure, $3.70 total traded, zero realized P&L,
  and $0.0171 fees. Both independent closure reviews returned GO with no
  remaining Critical, High, or Medium finding; the code reviewer also reported
  no Low. Combined v32 and diagnostic verification is 179 tests passing, Ruff
  clean, and mypy clean.
- Rechecked collector health after the repair. Correction lock5 reached 479 of
  735 artifacts; feed lock4 and queue lock5 remain alive, read-only, pregame,
  and empty on stderr.
- Ran a third exact correction audit over six of the newest completed artifacts
  and 2,812 retained states. Every wrapper, raw hash, completed-play projection,
  recomputed audit, final-feed hash, final score, base provenance, and exclusion
  matched. All finding collections were empty. The three exact samples now cover
  18 artifacts and 8,563 states. Correction lock5 reached 483 of 735 artifacts.
- Stopped feed lock4 and queue lock5 before the first game and before any
  trigger or shadow order after two independent audits found that early
  schedule failures and preeligibility poll gaps were not globally sticky.
  Preserved queue lock5's pregame-only log with SHA256
  `cd440fd9d4d3f6e2ad9f8a40244e717c1fcf1730468cc7a8b0230cc02f6d7f95`
  and excluded both runs from every gate.
- Added durable schedule-error evidence, strict scheduled-game validation, and
  globally fatal error and gap handling. Added restart and boundary regression
  tests. Both independent closure reviews returned GO, then fresh read-only
  feed lock5 schema 5 and queue lock6 schema 5 started with exact signature
  pinning and empty stderr.
- Closed the binding-backtest audit findings in new lock3 schema 4. G1 now
  enforces the frozen 111, 173, and 401 unique-game minima. The 97c and 98c
  review population uses the prospective deployable latency. The verifier
  binds the exact zero-maker-fee PDF and manifest, all base and correction
  constituents, trigger coverage, mapping audit, and every prospective input,
  then rehashes them before atomic publication. G3 reports contracts and P&L
  dollars in every active calendar week. G4 reports first and last queue-print
  offsets and calendar-week concentration. Unexpected output files are fatal.
  Independent rereview returned GO.
- Built the frozen 50-market mapping population, then rejected its first
  automated-only audit design. An independent Codex review agent, explicitly
  not a human reviewer, inspected all 50 raw cases without accepting the
  builder's pass field. It returned 50 PASS across 45 matched games and all five
  exclusions. Source and code TOCTOU findings and exact reviewer binding were
  fixed and independently rereviewed GO.
- Published create-once mapping artifact
  `mapping-audit-20260518-20260715-lock1`. It covers 43 dates, 29 teams, 15
  integer thresholds, and four doubleheader candidate rows. Manifest SHA256 is
  `84b849b13df5ac2d0f5437bd98dbe9f64b4ca56187ebd890ff37bb1758467def`.
  The full v32 suite passes 168 tests with Ruff and strict mypy clean.
- Verified the new live observers after their first baseline publication.
  Feed lock5 has zero triggers, errors, gaps, regressions, or eligible plays;
  queue lock6 has zero orders and remains fail-closed. Both process pairs are
  alive with empty stderr. Correction lock5 reached 585 of 735 artifacts and
  15.76 GB.
