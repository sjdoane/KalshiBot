"""READ-ONLY: dump Kalshi /portfolio/balance + /portfolio/positions so we can
see what the bot's bankroll read (cash + portfolio_value) actually sees vs the
app UI (Positions / Cash / total). GET only; safe alongside the live bot.

Run: PYTHONPATH=src .venv-kronos/Scripts/python.exe -m scripts.v20.probe_balance
"""

from __future__ import annotations

import json

from kalshi_bot.config import load_settings
from kalshi_bot.data.kalshi_client import KalshiClient


def main() -> None:
    s = load_settings()
    with KalshiClient(s) as c:
        bal = c.get("/portfolio/balance")
        print("=== /portfolio/balance raw ===")
        print(json.dumps(bal, indent=2, default=str))
        cash = float(int(bal.get("balance") or bal.get("portfolio_balance") or 0)) / 100.0
        pv = float(int(bal.get("portfolio_value") or 0)) / 100.0
        print(f"\nbot reads: cash=${cash:.2f}  portfolio_value=${pv:.2f}  total=${cash + pv:.2f}")

        try:
            pos = c.get("/portfolio/positions")
        except Exception as exc:  # noqa: BLE001
            print(f"\n/portfolio/positions fetch failed: {exc}")
            return
        mps = pos.get("market_positions", []) if isinstance(pos, dict) else []
        print(f"\n=== market_positions (n={len(mps)}) ===")
        # Sum the fields Kalshi exposes so we can see which one == the UI's
        # "Positions $20.97" (market_value vs total_traded vs position * price).
        tot_mv = 0.0
        tot_cost = 0.0
        nonzero = 0
        for m in mps:
            posn = m.get("position", 0)
            if posn == 0:
                continue
            nonzero += 1
            mv = m.get("market_value", 0)
            cost = m.get("market_exposure", m.get("total_traded", 0))
            tot_mv += mv
            tot_cost += cost
            print(
                f"  {m.get('ticker',''):40} pos={posn:>4} "
                f"market_value={mv} exposure={m.get('market_exposure', '?')} "
                f"total_traded={m.get('total_traded','?')} "
                f"realized_pnl={m.get('realized_pnl','?')}"
            )
        print(f"\nnonzero positions: {nonzero}")
        print(f"sum market_value   = ${tot_mv/100.0:.2f}")
        print(f"sum exposure/cost  = ${tot_cost/100.0:.2f}")
        print("(UI showed Positions $20.97, Cash $57.61, total $78.58)")


if __name__ == "__main__":
    main()
