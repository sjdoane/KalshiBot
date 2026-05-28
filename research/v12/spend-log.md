# v12 Spend Log

Round 17 (v12) is a methodology refinement on v11 GRANGER-PARTIAL.
Per operator authorization 2026-05-27: NO capital, NO new trading rule;
apply Phase 3 critic Section D fixes and re-test.

## Budget guidance
- LLM: target $2 to $3 (within remaining shared cap; v11 used $3.30 of
  earlier-estimated $5 to $8 headroom; ~$2 remaining if upper)
- External: $0 to $5 (existing 14,740 the-odds-api credits)
- Capital: $0

## Entries

| When (UTC) | Source | Description | Cost (USD) | Running total LLM | Running total external |
|---|---|---|---|---|---|
| 2026-05-27 | orchestrator | v12 kickoff, directory + tasks | ~$0.05 | $0.05 | $0 |
| 2026-05-27 | orchestrator | v12 methodology lock (Granger refinement with day/night, sport-specific offsets, block-bootstrap, NFL window expansion) | ~$0.10 | $0.15 | $0 |
| 2026-05-27 | orchestrator | Phase 2a NFL extended-window pulls (122 unique snapshots, 1,220 of 19,990 credits) | ~$0.05 | $0.20 | $0 |
| 2026-05-27 | orchestrator | Phase 2b analysis (3 reruns due to bugs: tz, windowing default, team1_is_home) + sanity check | ~$0.20 | $0.40 | $0 |
| 2026-05-27 | Phase 3 critic agent | Critique: 3 KILLER + 6 IMPORTANT + 3 NICE-TO-HAVE; verdict GRANGER-PARTIAL-MLB-NIGHT (cumulative) / NULL-v12 (literal) | ~$0.30 | $0.70 | $0 |
| 2026-05-27 | orchestrator | Phase 5 FINAL-VERDICT + replay-prevention | ~$0.10 | $0.80 | $0 |
