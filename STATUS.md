# Project Kalshi status

Updated 2026-07-18.

## Superseding terminal v33 and v34 pivot update

- V33 feed lock2 and queue lock3 are terminal failed evidence. Both stopped
  fail-closed, all three process locks are absent, and neither signature can
  restart or contribute to a replacement gate.
- Feed lock2 ended with 20 eligible triggers across four games, four completed
  play revisions, nine posteligibility violations, no fresh exact endTime-only
  exercise, and a false gate. Queue lock3 ended with five hypothetical
  submissions across two games, two nominal queue-cycle gaps, a false feed
  gate, and a false queue gate. Neither process had an order or capital
  endpoint.
- Three material revisions were transient complete-to-incomplete states of the
  current at-bat after 25.878390, 25.506998, and 27.530841 seconds. The frozen
  game-wide taint rule invalidated nine earlier triggers even though the revised
  later plays did not alter those trigger prefixes. This does not show the
  frozen 60-second guard was too short. It shows that v33's dependency scope was
  too broad.
- The two nominal queue gaps were 33.171421 and 45.061671 seconds, while the
  queue durably emitted 10 and 14 feed-generation-advanced outcomes. The
  process was not stalled. The frozen metric ignored those outcomes, so the
  failed result remains binding.
- A separate High custody finding remains part of the v33 failure: queue
  terminal evidence bound a feed generation that was later overwritten before
  feed shutdown. The PowerShell supervisor also observed a blank child
  ExitCode after waiting. V33 cannot be repaired or retroactively
  reinterpreted.
- Independent reproduction sealed the 939-file feed bundle at SHA256
  `27b540cac297360ce0cb99b6e8bc67f79404b0f23c8782d61fa0ab5ef3cee5ca`
  and the nine-file queue bundle at SHA256
  `25e3d51f23f440d21c0f1b7bf0ce642faaf1b7ce60ffd4eb0d74341419eb8089`.
  Exact evidence is in
  `data/v32/v33-lock2-lock3-terminal-seal.json` and
  `research/v33/06-lock2-lock3-terminal-failure.md`.
- V34 is a wholly fresh candidate. Its amended preimplementation lock freezes
  the entire ordered play prefix through each trigger, exact crossing
  reconstruction, a 60-second guard, numerical network and heartbeat limits,
  archival of every consumed feed generation, OS-observed feed and queue exit
  custody, new schemas and paths, and a maximum 24-hour prospective horizon.
  The primary policy canonical SHA256 is
  `6c85a6a901fd0f4c0eb639869b0f43bf438e24c5ea1f7739827e81c6361b80d0`.
- Initial and second independent methodology reviews correctly returned NO-GO.
  Prefix masking and the original liveness, archive, freshness, and custody
  findings are closed. The latest amendment adds stable-generation decision
  commit, separate feed and queue custody manifests, the sole historical
  correction-manifest exception, an exact posteligibility prefix endTime
  exercise, irreducible event-independent lattice cases, and event-clustered ML
  labels. The final amendment requires three distinct derivative events and
  complete game or event isolation across every ML fold. Both final methodology
  reviewers returned GO with no remaining Critical or High finding.
- The first v34 implementation chunk is independently reviewed GO by two
  reviewers with no remaining Critical or High finding. It implements exact
  ordered-prefix reconstruction, score-component regression rejection,
  immutable trigger basis and threshold crossing, whole-prefix exact endTime
  exercise evidence, canonical launch and source provenance, exact parent feed
  state membership, stable-generation decision commits, structured end proofs,
  a hash-chained event log, and state-cache recovery that cannot retain phantom
  orders. The settled suite has 43 passing tests with Ruff and strict mypy
  clean. A real archived MLB file with SHA256
  `ce79fe32bb7f02661e63ba73fae466c585e20cd59c55dec30adfb011aaab6a28`
  reproduced 50 completed plays and five exact scoring prefixes. It received
  zero prospective gate credit. No v34 replay, observer, order path, or capital
  exists; feed, queue, archive, and Python process-custody integration are next.
- A separate read-only derivatives lock models the full integer payoff lattice
  across compatible digital-option legs. It handles baskets whose cost exceeds
  one dollar, exact strike boundaries, displayed depth, and per-leg rounded
  fees. Findings are labeled non-atomic displayed-depth candidates and cannot
  authorize a pilot without a separate legging-risk design.
- Fresh public derivatives inspection at 21:17 UTC found one open July monthly
  Bitcoin maximum event and one open July monthly minimum event with eight
  markets each. An exploratory orderbook-backed v29 pair scan found zero
  candidates. This is read-only telemetry with zero sidecar gate credit.
- V29 remains unchanged. It currently has 4,004 log rows, 71 completed burst
  sessions, and zero sightings. Its close horizon remains 2026-08-15.
- Fresh authenticated exchange truth at 21:27 UTC is $5.77 cash and $3.76
  portfolio value, or $9.53 total, with five positions and $3.70 exposure.
  One v30 TSA YES bid for one contract at 97c remains resting with zero fills.
  The authenticated fill ledger has zero fills in the preceding 24 hours. V30
  remains the only money writer.

## Superseding v33 update

- v32 feed lock5 is binding failed evidence and cannot authorize capital. Its
  frozen classifier treated an exact end-time-only edit as determination
  material after eligibility in game 824170, at-bat 5. The scheduled 18-hour
  audit completed cleanly. An independent process reproduced its terminal
  receipt, exact key-file hashes, and a 4,284-file artifact-tree seal. Its gate
  is permanently false.
- v32 queue lock6 is stopped failed evidence. It recorded 22 hypothetical
  submissions across four games, then exited on a torn feed summary and receipt
  generation. Its frozen summary has `gate_met=false`; exact artifact hashes
  are recorded in `research/v32/14-lock5-lock6-failure-and-v33-pivot.md`.
- v33 is the fresh candidate. Its locked policy separates score, sequence,
  completion, and review determination changes from timing and descriptive
  metadata. Trigger identity is game-scoped and excludes endTime. No v32
  prospective trigger, latency, eligibility, queue, or guard value carries
  forward.
- The original 730-game correction cache is complete but the v32 collector had
  no manifest because five MLB queries returned later timestamps. v33
  correction lock1 correctly failed closed after two partial files when one
  response was not the next advertised timestamp. Lock1 is preserved with no
  manifest and cannot be reused.
- Fresh correction lock2 schema 2 has independent methodology and code GO with
  no remaining Critical or High finding. It hard-codes the exact five source
  behaviors, requires full-payload confirmation for the one unadvertised
  intermediate state, and collapses four same-second raw variants only when
  every raw-derived determination and gate field hashes identically. It
  revalidates all 730 legacy files from raw evidence, owns both locks for the
  full build, and publishes its manifest once.
- Correction lock2 completed under builder SHA256
  `720484738a46ccb7bf2836c29290122558ff3b8f900812593c60639894abc447`.
  It published 735 games and 357,307 raw retained states with zero
  determination revision, a null historical delay p95, and a fixed 60-second
  guard. A separate process reacquired both locks and reproduced the exact
  terminal manifest SHA256
  `4b334616454f170ad9f7c909f353e68f1f12968b2ac5d94ee2a348b2ca8ef94e`.
- Feed lock1 exposed a High eligibility-provenance defect: its published
  `eligible_at` changed on every later valid poll. Feed lock1 and dependent
  queue lock2 are stopped failed evidence and contribute no row or gate value.
  The minimal first-poll-only fix and entirely fresh reset received independent
  prelaunch GO with no Critical or High finding.
- Feed lock2 schema 7 binds source SHA256
  `567e43ff7d162bd180b745a8cbdc9cfe15e09cd119475b68d5fa4039e8526cc9`.
  Queue lock3 schema 8 binds source SHA256
  `7d58344766275d6d52e07a1ad0d6382583b27fb70d62efb797e1c25ac95c25a1`.
  The supervisor SHA256 is
  `c83ea2c66a706c1becced813b4eb6b985f5a6123331cd25a3c69d2b81411707b`.
  All 140 v33 tests pass with Ruff and strict mypy clean.
- Fresh feed lock2 started from empty paths at 18:01:39 UTC. Its reviewed
  supervisor started queue lock3 at 18:02:16 UTC with a hard 15:55 UTC July 19
  deadline. All three new locks are live, all error logs are empty, queue order
  state is empty, and neither observer has a capital endpoint.
- The 2026-07-18 18:40 UTC production account read is $5.77 cash and $3.71
  portfolio value, or $9.48 total, with five nonzero positions. v30 remains the
  only authorized money writer. One v30 Arm D TSA YES bid for one contract at
  97c remains resting with zero fills. The authenticated fill ledger has zero
  fills in the last 24 hours. No v32 or v33 capital is deployed.

## Exchange and live truth

- The only scheduled process currently authorized to write money is the v30
  live pilot, on a five-minute cadence. Its Arms C, D, and E can write when
  their gates fire. The older v1 money path is disabled. v31 is not armed and
  is not safe to arm.
- At the 2026-07-18 18:40 UTC verified snapshot, the account held $5.77 cash
  and $3.71 in portfolio value, for $9.48 total. Five positions were nonzero and
  one v30 Arm D TSA YES order rested for one contract at 97c. Exchange truth
  showed zero fills in the preceding 24 hours. State must be re-read before
  allocation.
- From July 13 through that snapshot, v30 Arm E logged 610 scans and 161
  disarmed-style opportunity intents but found no room on its latest scans and
  submitted zero Arm E orders. Other v30 arms submitted three maker bids: Arm C
  14 contracts at 95c on July 13, Arm D 25 at 97c on July 16, and Arm D one at
  97c on July 17. The first two closed with zero fills and only the last remained
  live. The no-fill diagnosis is still lack of executable supply at the quote,
  not lack of trigger activity.
- The prior Moana fills were invalid strategy evidence because the resolver had
  cached the wrong 2016 page. They lost about $44.50. Historical v1 realized
  P&L is about negative $58.59; v14 lost $6.08; v16 was fee-negative in all 65
  tested rows.

## Current candidate

v33 is the only active candidate. It retains the KXMLBTOTAL mechanism: after a
completed MLB at-bat raises the official structured cumulative score above a
total-runs threshold, quote the provisionally determined YES side as a maker.
The MLB `isScoringPlay` flag is evidence only and has no trigger authority.
The v33 reset changes determination-impact classification, trigger identity,
and the historical correction source, while carrying forward no v32
prospective result. Historical 97c and 98c prints remain reachability evidence
only because submission-time books are absent. Historical 99c flow is queue
opportunity, not a credited fill. A fresh prospective depth-aware shadow and a
real maker pilot remain mandatory.

The initial deployment cap remains 30 percent of current total account value.
The operator's latest authorization permits eventual scaling up to all free
Kalshi cash after the same historical, prospective, operational, and durable
live-evidence gates pass. This changes only later sizing, not the strategy,
selection criteria, or initial pilot. Existing exposure from every bot counts
against each applicable cap.

## Current v33 evidence state

- Historical correction lock2 is terminal and independently reproduced. Its
  manifest binds 735 games, 357,307 raw retained states, zero determination
  revision, a null historical delay p95, and the frozen 60-second guard.
- The v33 feed and queue bind that exact manifest and guard. Prospective
  observation cannot refit either strategy eligibility or the guard.
- Feed lock1 and queue lock2 are stopped failed evidence. A High defect caused
  feed lock1 to rewrite `eligible_at` on every later valid poll, which could
  understate queue latency. No feed lock1 trigger, eligibility, timing, gate,
  or queue lock2 row may be reused.
- The fresh first-poll-only fix, feed lock2, queue lock3, and supervisor passed
  independent prelaunch review with no Critical or High finding. The v33 suite
  has 140 passing tests, with Ruff and strict mypy clean.
- The first reviewed queue supervisor correctly started queue lock1 from the
  first receipt-backed feed summary, then stopped it fail-closed before process
  lock acquisition when the frozen mapper refused an exact PIT at CLE schedule
  tie. Lock1 has no output directory, event, state, summary, receipt, shadow
  order, or gate value and can never restart.
- Queue lock3 schema 8 binds mapping policy SHA256
  `6aa3840a5ff8725e049ca6f487a82a9d35ec99cbfa845339d0079c3fba864cdd`,
  queue source SHA256
  `7d58344766275d6d52e07a1ad0d6382583b27fb70d62efb797e1c25ac95c25a1`,
  supervisor SHA256
  `c83ea2c66a706c1becced813b4eb6b985f5a6123331cd25a3c69d2b81411707b`,
  and shared mapper SHA256
  `db547b9cde54b7228d9bad40956b86786e743480a8183ecc11e001d7c554f57b`.
  Independent implementation review closed two High findings around
  unique-to-ambiguous credit and mapper source custody. The v33 suite now has
  140 passing tests with Ruff and strict mypy clean.
- Feed lock2 parent PID 11548 and runtime PID 15208 started from empty paths at
  18:01:39 UTC. Supervisor PID 15864 started at 18:02:15 UTC and launched queue
  parent PID 63416 and runtime PID 27532 at 18:02:16 UTC. Its hard deadline is
  15:55 UTC July 19. All three new locks are live and every error log is empty.
- The replacement began with fresh game baselines. By 18:40 UTC it had four
  clean eligible triggers across two games. Each `eligible_at` is the first
  poll strictly after 60 seconds and remains fixed while later polls advance.
  The four observed delays from `t_seen` to eligibility are 60.389596,
  60.002922, 60.028486, and 60.019656 seconds. Feed errors, monitoring gaps,
  score regressions, revisions, future anomalies, and posteligibility
  violations all remain zero.
- Queue lock3 binds only feed lock2 and currently has 14 mapping assignments,
  one exact zero-credit PIT at CLE exclusion, an empty order state, and zero
  shadow submissions. Zero is expected at this checkpoint: game 824414 is the
  excluded doubleheader candidate, while mapped game 824657 had total 2 and its
  lowest live threshold was 3.5. No failed-run reference or v33 portfolio,
  order, fill, or capital endpoint exists.
- Independent first-trigger audit returned GO for continued read-only
  collection with no Critical or High finding. It verified all four raw payload
  hashes and completed plays, each prior sub-60 poll, each first post-60 poll,
  hundreds of later clean confirmations, exact receipt bindings, and queue
  cycles within 2.094 seconds of every eligibility timestamp. Queue silence is
  therefore explained by the frozen exclusion and market floors, not by a lost
  trigger or dead process. Capital remains prohibited while the gate is false.
- Independent postlaunch review returned GO for continued read-only observation
  with no Critical or High finding. It verified all five frozen source and
  manifest hashes, all five live processes, all three locks, coherent receipts,
  fresh baseline-only feed events, zero orders, empty error logs, and the
  absence of any private exchange or capital mutation surface. Capital remains
  prohibited while both fresh gates are false.
- The prospective gate requires at least 20 clean triggers across at least five
  final games, at least 20 depth-aware queue opportunities across at least five
  games, a genuinely fresh exact endTime-only policy exercise, every eligible
  game final, and no fatal feed, timing, revision, snapshot, binding, or
  monitoring finding.
- The binding historical profitability and robustness backtest is prohibited
  until the fresh prospective gate passes. The money path is prohibited until
  both prospective and historical gates pass and then requires its own tests
  and independent review.
- V32 feed lock5 completed its scheduled audit and is terminal failed evidence.
  Independent review verified absent processes and lock, both zero-byte logs,
  both verified local and binding summary pairs, one exact posteligibility
  violation, and the canonical 4,284-file tree SHA256
  `9ef625f7b224879b664df11e80dcd9cb3be4ebf5f0748e679eff1e755d768e36`.
- The initial v33 live pilot remains capped at 30 percent of fresh total account
  value. Only after durable live evidence and every sizing gate passes may the
  reviewed path scale toward all free cash.

### Historical v32 evidence trail

The items below preserve the chronological v32 trail. Present-tense process
references in this subsection describe their dated observation and are
superseded by the current v33 evidence state above.

- The methodology and kill criteria were locked before binding data.
- Binding base data from 2026-05-18 through 2026-07-15 is complete: 740 Kalshi
  events, 735 matched MLB games, 9,148 settled markets, and 5,961,525 reconciled
  trades.
- The complete MLB retained-timecode correction pull is running under lock5,
  schema 3. It retrieves every retained state, preserves raw all-play evidence,
  detects completed-play changes, and validates caches against the current base
  manifest and final feeds. It has advanced through 585 cache files and 15.76 GB
  while remaining healthy after its original shell wrapper timed out.
- A read-only early scan of 371 atomically completed correction artifacts
  found explicit empty `score_regressions` and `completed_play_revisions` lists
  in every file. This is a progress diagnostic only, not a substitute for the
  remaining games, final manifest, or locked correction-gate verifier.
- Six evenly spaced completed artifacts also passed the full cache verifier. It
  recomputed 2,914 retained states, raw evidence hashes, play projections,
  audits, final-feed hashes, base provenance, final scores, and exclusions with
  zero regression or revision finding.
- A second exact verifier sample covered six newer artifacts and recomputed
  another 2,837 retained states. All raw hashes, play projections, audits,
  final-feed hashes, scores, provenance, and exclusions matched. The combined
  sample is 12 artifacts and 5,751 retained states with zero finding.
- A provisional exact-guard evaluation covered 368 historically crossed games
  with completed correction artifacts. At a 60-second guard, 366 games were
  eligible and two were correctly ineligible because their retained streams
  ended only 30 seconds after the crossing identity first appeared. Both had
  zero regression, revision, exclusion, or settlement contradiction. The
  frozen 99c G1 minimum is 401 games. The final prospective guard, remaining
  games, post-guard checks, and final manifest remain authoritative.
- Independent pre-pull review is GO.
- Feed lock1 and its dependent queue lock2 are stopped and preserved as failed
  or nonbinding evidence. Feed lock1 recorded no score regression, but its
  frozen schema treated an exact description-only wording edit as two
  post-eligibility violations. It remains failed and none of its observations
  may count.
- Pre-review observer and queue output is preserved in explicitly named pilot
  directories and excluded from every binding gate. Queue lock1 later failed
  before any submission when OneDrive denied an atomic cache replacement. Its
  files and hashes are preserved as failed evidence. Bounded retry was added,
  independently rereviewed, and retained.
- Independent methodology review approved only a narrow predeclared amendment:
  a complete diff exactly at `/result/description` may be editorial when both
  projections are well-formed; every other change stays material and
  fail-closed. Final code review found three High issues, all fixed and tested,
  then returned GO with no remaining Critical or High finding.
- A later full-base diagnostic found a separate Critical trigger defect before
  feed lock2 or queue lock3 recorded any scoring row or shadow order. Across
  the immutable 735-game corpus, 93 cumulative score increases in 91 games had
  `isScoringPlay=false`, so the old flag-based trigger could miss real runs.
  Feed lock2 and queue lock3 were stopped cleanly at zero trigger rows and zero
  orders, preserved with canonical hashes, and excluded from all evidence.
- Methodology review approved a fresh structured-score amendment and prohibited
  reuse of old metrics. One shared implementation now serves historical
  crossings, prospective first-seen events, and heartbeats. It requires a
  complete contiguous completed-at-bat sequence from index 0, exact nonnegative
  integer cumulative scores, timezone-aware end times, a nondecreasing score
  path, live linescore at least the completed maximum, and final equality. It
  fails closed on malformed values, path regressions, score revisions, trigger
  disappearance, and identity drift. Trigger identities enforce exact score
  arithmetic. One shared strict correction-guard policy applies to prospective
  and historical paths.
- Two rounds of independent adversarial review are GO with no remaining
  Critical or High finding. Feed summaries are fsynced and followed by an exact
  generation and file-hash receipt. Queue timing measures both score crossing to
  actual shadow submission and feed eligibility to actual submission.
  Historical simulation uses the later of crossing plus end-to-end latency and
  observed guard readiness plus the full eligibility-to-submit delay, so a late
  revision reset cannot create a time-travel fill.
- Fresh signatures are feed lock5 schema 5, queue lock6 schema 5, run-increase
  backtest lock3 schema 4, and coverage lock2 schema 2. The suite has 168
  passing v32 tests, Ruff is clean, and mypy is clean.
- Feed lock4 and queue lock5 were stopped before the first game and before any
  trigger or shadow order after review found two monitoring-continuity holes.
  Their evidence is excluded. Feed lock5 now records schedule discovery errors
  durably and makes every feed error or poll gap globally fatal across restart.
  Queue lock6 pins that exact feed generation. Two independent closure reviews
  returned GO.
- The frozen 50-market mapping audit is published under
  `mapping-audit-20260518-20260715-lock1`. It covers 45 matched games and all
  five exclusions across 43 dates, 29 teams, 15 integer thresholds, and four
  doubleheader candidate rows. An independent Codex review agent, explicitly
  not a human reviewer, inspected all 50 raw cases and returned 50 PASS. The
  published manifest SHA256 is
  `84b849b13df5ac2d0f5437bd98dbe9f64b4ca56187ebd890ff37bb1758467def`.
- Backtest lock3 now enforces the frozen G1 minimum game counts of 111, 173,
  and 401, uses the prospective deployable latency for its strict-below review
  population, binds the exact dated zero-maker-fee PDF and mapping audit,
  captures every base and correction constituent, rejects any extra output,
  and reports per-week G3 values plus G4 offsets and concentration. Independent
  review is GO with no remaining Critical or High issue.
- The signed full-corpus coverage artifact is published. It scanned all 735
  games and reproduced 93 false-flag run increases across 91 games with the
  exact expected event counts and cases payload SHA256
  `9070d087016399ef46bef3f098143b32263556d57f1983333364cbe68af892cd`.
  It binds one stable base-manifest snapshot and was atomically published only
  after source, payload, code, count, and file-hash verification.
- A real-data provisional latency sensitivity over all 5,087 crossed markets
  found that the frozen historical queue-opportunity gate passes at every tested
  latency from 60 through 300 seconds. At 300 seconds, 680 of 702 games and all
  56 active days had a basic opportunity, the day-rate Wilson lower bound was
  95.39 percent, and 679 basic games were persistent. This is strong queue-flow
  evidence only, never a historical fill or P&L claim. See
  `research/v32/11-provisional-queue-latency-sensitivity.md`.
- The queue collector now retains a zero-opportunity row when a crossed market
  closes before hypothetical submission. This repairs the frozen game
  denominator instead of dropping late-latency failures. A full real-data
  replay preserved all 5,087 rows and all 702 games at every latency. Both
  independent reviewers returned GO with no Critical or High findings.
- The read-only feed lock5 and queue lock6 observers are live under process
  locks. They have no portfolio or order endpoint. The remaining July 17 MLB
  first monitored game had only baseline polls at the last check. Feed lock5
  had zero triggers, feed errors, monitoring gaps, or regressions, and queue
  lock6 was fail-closed with zero orders. A
  postponed event is narrowly excluded while every other mapping failure stays
  fatal.
- The current MLB schedule has 13 not-yet-started games beginning at 23:05 UTC.
  Kalshi exposes 132 open KXMLBTOTAL markets across 12 exactly mapped games,
  with 11 strikes per game. This gives tonight's prospective sample enough game
  breadth to reach the frozen five-game gate if at least 20 clean score increases
  are observed. The earlier completed game is outside the fresh observer window
  and the postponed game is excluded.
- A current production fee check reports KXMLBTOTAL `fee_type=quadratic`, not
  `quadratic_with_maker_fees`, with no scheduled fee changes. Under Kalshi's
  July 7 fee schedule, the default maker multiplier is zero and KXMLBTOTAL is
  absent from the nonstandard fee list. A resting KXMLBTOTAL maker order
  therefore currently has zero maker fee, so the dated G4 fee condition passes.
  It must be re-read before arming and each POST. See
  `research/v32/12-current-fee-and-slate-check.md`.
- Raw proof is preserved in create-once snapshot
  `predeployment-snapshot-20260717T213156Z`. It contains the exact series, fee
  change, MLB schedule, market-page, and 132-ticker mapping payloads. All five
  file hashes reverified against manifest SHA256
  `56fc2502db66ac573e847216dc8f2c7040bc1de1de8cc32648a1cad98baa21be`.
  The pre-POST checklist now fails closed on fee-horizon changes, immediate-fill
  races, non-resting acknowledgments, and any nonzero maker or taker fee.
- The exact 382,507-byte July 7 fee PDF is also preserved under
  `fee-schedule-20260707-lock1`, PDF SHA256
  `815e2d5127d02d2fb90773d1a3844dc15a987696171eddc4e58de87b59c6124c`.
  Local extraction and visual inspection confirm default maker multiplier zero,
  no KXMLBTOTAL exception, and the distinct KXMLBGAME exception.
- A fee lifecycle finding tightened the future money path. While any v32 rest
  exists, a 10-second watchdog must re-read classification and fee changes, a
  60-second conditional schedule check must preserve the approved PDF hash, and
  any failure or change de-arms then confirms cancel-all. Every partial and full
  fill must match exact order IDs, report a present and parseable zero
  `fee_cost`, and report `is_taker=false` before credit.
- The lifecycle rereview initially found one High schema mismatch in the fill
  fields. The requirement was corrected before implementation, and the exact
  closure rereview returned GO with no Critical, High, or Medium finding.
- The independent quantitative rereview also returned GO at the requirements
  level after rehashing and inspecting the 12-page official fee artifact. Its
  prior High lifecycle and Medium provenance findings are both closed. A future
  money-path implementation still requires its own mandatory review.
- A fresh authenticated account read exposed a stale-schema defect in the
  read-only `scripts/v20/probe_balance.py`: it looked for legacy position and
  cent fields and could print zero positions. The diagnostic now requires the
  authoritative balance fields, validates every current or legacy position
  field, requests only nonzero positions, drains and validates every cursor
  page, and fails on missing or malformed data. The production smoke returned
  exactly five positions with $3.70 exposure and $0.0171 paid fees. Its 33
  targeted tests pass, both independent rereviews returned GO with no remaining
  Critical, High, or Medium finding, the code reviewer also reported no Low,
  and the combined v32 plus diagnostic suite passes 201 tests with Ruff and
  mypy clean. This repair changes no live strategy or money path.
- Correction lock5 remains healthy and advanced to 585 of 735 game artifacts at
  the latest read. Feed lock5 and queue lock6 processes remain alive with empty
  stderr. Feed lock5 has a valid receipt-backed baseline summary with zero
  trigger, error, gap, or regression; queue lock6 remains fail-closed with zero
  orders.
- A third exact correction sample recomputed six of the newest completed
  artifacts across 2,812 retained states. Every wrapper, raw payload hash,
  completed-play projection, full audit, final-feed hash, final score, base
  provenance, status exclusion, and correction exclusion matched. All six had
  zero regression, revision, exclusion, or prohibited-status finding. Across
  the three samples, 18 artifacts and 8,563 retained states now match exactly.
- A same-task heartbeat wakes the work every 15 minutes so a goal badge change
  does not stop progress.

## Kill criteria

Kill v33 before capital if the fresh feed or queue evidence is incomplete or
fatal, the required endTime-only policy exercise is absent, historical
profitability or robustness fails its frozen threshold, current fees remove the
margin, the money path cannot prove exact order and exposure custody, or the
initial cap cannot be enforced from fresh exchange truth. After arming, any
determination violation, ambiguous POST, nonzero unexpected fee, exposure-cap
breach, failed reconciliation, or failed cancel path de-arms and cancels the
strategy.

## Next actions

1. Keep v33 feed lock2, queue lock3, and the lock3 supervisor under exact
   process and lock custody through the full signed prospective window.
2. Evaluate the signed feed and queue artifacts only after the full window and
   every eligible game reach terminal state.
3. Run the frozen binding historical profitability and robustness backtest only
   if the prospective gate passes.
4. Build, test, and independently review the fail-closed money path only if both
   prospective and historical gates pass.
5. Start with the frozen 30 percent real maker pilot, reconcile against fresh
   exchange truth, then scale toward all free cash only after the reviewed
   durable-live gate and exposure schedule pass.
