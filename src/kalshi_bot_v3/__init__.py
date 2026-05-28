"""kalshi_bot_v3 research package.

v3 is the research track that tests whether external team-stat features
improve calibration over v1's flat-prior heuristic at n=147 with proper
leak-free walk-forward CV. The orthogonality protocol in V3-B1 dropped
11 of 12 candidate features; only `nfl_games_played_pre_t35d` (effectively
a league-dummy plus season-progress signal) survived. This package
contains the trainer + decision_fn factory used by the gate runner.

Nothing in this package imports into the live-trading v1 codepath. Live
v1 (in `kalshi_bot/`) is untouched.
"""
