"""V10-A pre-flight smoke test 5: synthetic Granger test.

Verifies that statsmodels.tsa.stattools.grangercausalitytests runs on
synthetic AR(1) data with known causality. If this passes, the Granger
implementation works; if it fails, halt before pulling any real data.

Per A2 v2 lock smoke test plan, item 5.
"""
from __future__ import annotations

import sys

import numpy as np
from statsmodels.tsa.stattools import grangercausalitytests


def main() -> None:
    rng = np.random.default_rng(42)
    n = 100
    # X is exogenous AR(1)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.5 * x[t - 1] + rng.normal()
    # Y depends on X lagged by 2 days
    y = np.zeros(n)
    for t in range(2, n):
        y[t] = 0.7 * x[t - 2] + 0.3 * y[t - 1] + rng.normal()

    # Test: X causes Y at lag 2 (true)
    data = np.column_stack([y, x])  # column 0 = Y, column 1 = X; convention is "does column 1 cause column 0"
    print("Granger test on synthetic data: does X cause Y (true at lag 2)?")
    try:
        result = grangercausalitytests(data, maxlag=5, verbose=False)
    except Exception as e:
        print(f"FAIL: grangercausalitytests raised exception: {e}")
        sys.exit(1)

    print("\nF-test p-values by lag:")
    p_at_lag2 = None
    for lag, vals in result.items():
        test = vals[0]
        f_p = test["ssr_ftest"][1]  # p-value from F-test
        print(f"  lag={lag}: F p-value = {f_p:.4f}")
        if lag == 2:
            p_at_lag2 = f_p

    if p_at_lag2 is None:
        print("ERROR: lag 2 not in results")
        sys.exit(1)

    if p_at_lag2 < 0.05:
        print(f"\nSmoke test PASS: lag 2 p-value {p_at_lag2:.4f} < 0.05 (detected true causality)")
        sys.exit(0)
    else:
        print(f"\nSmoke test FAIL: lag 2 p-value {p_at_lag2:.4f} >= 0.05 (did NOT detect true causality)")
        sys.exit(1)


if __name__ == "__main__":
    main()
