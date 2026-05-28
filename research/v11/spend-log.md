# v11 Spend Log

Running tally of LLM spend (Anthropic API) plus external spend
(the-odds-api Starter, etc). Round 16 budget guidance from prompt:

- Anthropic API: shared $25 cap. Other sessions ~$13 to $15 cumulative.
  v11 LLM headroom approximately $5 to $8. STOP and report if approaching $5.
- External data: $30 to $60 authorized. The-odds-api Starter $30 fits.
- Capital: $100 cap, $32 deployed via v1. v11 does NOT deploy capital
  (Track 1 backtest only, Track 2 logging-only).

## Entries

| When (UTC) | Source | Description | Cost (USD) | Running total LLM | Running total external |
|---|---|---|---|---|---|
| 2026-05-27 (open) | orchestrator | v11 kickoff, context load (CLAUDE.md, lit INDEX), path discovery, task scaffolding | ~$0.05 | $0.05 | $0 |
| 2026-05-27 | v11-A1 | Becker game-resolution audit (5 prefixes, DuckDB SQL, report) | ~$0.30 | $0.35 | $0 |
| 2026-05-27 | v11-A2 | the-odds-api Starter pricing + docs scout | ~$0.15 | $0.50 | $0 |
| 2026-05-27 | v11-A3 | methodology meta-critique on F1-F11 + composite gate | ~$0.30 | $0.80 | $0 |
| 2026-05-27 | v11-A4 | Track 2 wiring scout (Explore agent, read-only) | ~$0.20 | $1.00 | $0 |
| 2026-05-27 | orchestrator | Phase 1 synthesis + Track 2 state audit | ~$0.10 | $1.10 | $0 |
| 2026-05-27 | orchestrator | Methodology lock v1 + read pre-critic prep | ~$0.10 | $1.20 | $0 |
| 2026-05-27 | methodology critic | Critique of lock v1 (3 KILLER + 9 IMPORTANT) | ~$0.40 | $1.60 | $0 |
| 2026-05-27 | orchestrator | Lock v2 revision (3 KILLERs + 7 IMPORTANTs addressed) | ~$0.15 | $1.75 | $0 |
| 2026-05-27 | orchestrator | Track 2 join script + 15 tests (Phase 2 Track 2 SHIPPED) | ~$0.20 | $1.95 | $0 |
| 2026-05-27 | orchestrator | Phase 2 Step 1a Becker prep (5574 universe; pilots identified; F4 Option B INFEASIBLE confirmed) | ~$0.20 | $2.15 | $0 |
| 2026-05-27 | operator | the-odds-api Starter $30/20k tier purchased; key added to .env as THE_ODDS_API_KEY | $0 LLM | $2.15 | $30 |
| 2026-05-27 | orchestrator | Lock v3 amendment (Granger-first scope) + probe (10 credits) + bulk pull (5260 credits of 19990) | ~$0.10 | $2.25 | $30 |
| 2026-05-27 | orchestrator | Granger F-test analysis: MLB strong signal (F=20.12, p~0.00002, gamma=0.77, n=89); NFL null (n=70, p=0.63, gamma=-0.12); NBA underpowered (n=17) | ~$0.20 | $2.45 | $30 |
| 2026-05-27 | orchestrator | Phase 2 Step 3 robustness: LOCO-by-bookmaker MLB robust (all 10 drops F > 17); offset sensitivity reveals F=0.63 to F=23.82 across +/- 1h | ~$0.10 | $2.55 | $30 |
| 2026-05-27 | Phase 3 critic agent | Adversarial review: 2 KILLER + 6 IMPORTANT + 3 NICE-TO-HAVE; verdict GRANGER-PARTIAL with KILLER-1 NBA date-tz bug flagged | ~$0.50 | $3.05 | $30 |
| 2026-05-27 | orchestrator | Phase 4 KILLER-1 salvage (date-tz fix); re-run Granger -> 2 of 3 pass (MLB n=131 PASS, NBA n=151 PASS, NFL n=90 FAIL); GRANGER-PARTIAL verdict | ~$0.10 | $3.15 | $30 |
| 2026-05-27 | orchestrator | Phase 5 FINAL-VERDICT + replay-prevention + operator handoff | ~$0.15 | $3.30 | $30 |

## Pre-spawn budget reservations

| Agent | Reserved budget | Notes |
|---|---|---|
| v11-A1 Becker game-resolution audit | $0.50 | Read README + 2 to 3 SQL aggregates; cap with brief-mode instruction |
| v11-A2 the-odds-api scout | $0.40 | WebFetch their pricing + endpoints page; brief report |
| v11-A3 methodology meta-critic | $0.80 | Cross-reference F1-F11 taxonomy; pre-register gate; longest agent |
| v11-A4 Track 2 wiring scout | $0.30 | Audit src/kalshi_bot/strategy/, locate decision point, test count baseline |

Reserved Phase 1 total: $2.00. Phase 1.5 critic estimated $0.80 (likely
the heaviest single turn). Phase 3 critic estimated $1.50. Buffer
remaining if all reservations hit: $5.00 - $4.30 = $0.70 then we are
at the cap. Will report at $4.50 cumulative.
