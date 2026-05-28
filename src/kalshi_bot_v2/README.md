# kalshi_bot_v2

Research-mode package for v2 strategies. NOT wired into live trading.

## What's here

- `gate.py`: 6-criteria gate evaluator (5 from Strategy B Round 4 + C6 "v2 must
  beat v1 by 2pp"). Model-agnostic; takes a `(should_trade, predicted_prob)`
  decision function plus a DataFrame and returns a `GateResult`.
- `__init__.py`: package init only.

## What's coming (planned by master plan)

- A baseline gradient-boosted model trained on `data/v2/joined_mlb_dataset.parquet`.
- A `predict.py` that loads the model and returns trade decisions per market row.
- A `backtest.py` that ties model + gate together and prints the v2 vs v1 comparison.

## How a research agent should use this

```python
from kalshi_bot_v2.gate import evaluate, v1_decision_fn
import pandas as pd

df = pd.read_parquet("data/v2/joined_mlb_dataset.parquet")

def my_model_decision_fn(row: dict) -> tuple[bool, float]:
    # Replace with actual model prediction
    pred = ...
    return (pred > 0.75, pred)

# Baseline (what v1 would do on this dataset)
res_v1 = evaluate(df, v1_decision_fn, note="v1_baseline")
# Model
res_v2 = evaluate(df, my_model_decision_fn, note="lgb_v2")

print(res_v1.holdout_mean, res_v2.holdout_mean)
print(res_v2.criteria)
```

## Strict separation from v1

Nothing in this package should be imported by `kalshi_bot/*` modules. The
live bot must keep running on its own dependency graph. v2 reuses v1 code
in the OTHER direction (importing from `kalshi_bot.analysis.bootstrap`,
`kalshi_bot.analysis.metrics`, `kalshi_bot.data.kalshi_client`).
