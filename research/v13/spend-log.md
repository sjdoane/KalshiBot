# v13 Spend Log

Round 18 (v13) is the money-deployment verification on v12's
GRANGER-PARTIAL-MLB-NIGHT cumulative finding. Per operator authorization
2026-05-27: continue verification until either (a) a signal strong
enough to put money on, or (b) clear NULL.

## Budget guidance
- LLM: target $2 to $3 (cumulative v11+v12+v13 should stay under $7)
- External: $0 to $5 (existing 13,500 the-odds-api credits)
- Capital: $0 in-session; operator-authorized small deployment ($5-10)
  conditional on positive verdict

## Entries

| When (UTC) | Source | Description | Cost (USD) | Running total LLM | Running total external |
|---|---|---|---|---|---|
| 2026-05-27 | orchestrator | v13 kickoff | ~$0.05 | $0.05 | $0 |
| 2026-05-27 | orchestrator | v13 lock with money-deployment gate | ~$0.10 | $0.15 | $0 |
| 2026-05-27 | orchestrator | Phase 2a script + run (v11 centered VWAP rerun) | ~$0.15 | $0.30 | $0 |
| 2026-05-27 | orchestrator | Phase 2b live spread probe (3 iterations to fix Kalshi API parsing) | ~$0.20 | $0.50 | $0 |
| 2026-05-27 | orchestrator | Phase 2c strategy P&L | ~$0.10 | $0.60 | $0 |
| 2026-05-27 | Phase 3 critic agent | Adversarial review: 3 KILLER + 4 IMPORTANT + 3 NICE-TO-HAVE; verdict DEFER-FOR-MORE-DATA | ~$0.80 | $1.40 | $0 |
| 2026-05-27 | orchestrator | FINAL-VERDICT + 3-option presentation | ~$0.20 | $1.60 | $0 |
