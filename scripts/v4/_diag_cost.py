"""Final cost / cache summary."""
import pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
c = pd.read_parquet(ROOT / "data" / "v4" / "llm_forecast_cache.parquet")
print(f"Cache rows: {len(c)}")
print(f"Total cost: ${c['cost_usd'].sum():.4f}")
print()
print("By variant:")
g = c.groupby(["model", "prompt_variant"]).agg(n=("ticker", "count"), cost=("cost_usd", "sum"))
print(g.to_string())
print()
print(f"Total input tokens: {c['input_tokens'].sum():,}")
print(f"Total output tokens: {c['output_tokens'].sum():,}")
