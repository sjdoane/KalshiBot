"""v5 package: combined Polymarket-fade + sportsbook-fade + cross-market filter.

V5 Track A2: extends v4's filter overlay (Polymarket-fade and Kalshi
cross-market consistency) with a sportsbook-fade rule based on
the-odds-api implied probabilities. Defensive overlay only; filter can
REMOVE trades v1 would have made, never ADD new ones. OR-logic across
the three sub-rules: skip if ANY rule fires.

Pre-registered thresholds locked per V5 master plan and V5-A1:
    fade_threshold_cents_poly = 7.0   (matches V4-E locked value)
    fade_threshold_cents_book = 5.0   (V5-A1 measured +1.70c mean, smaller)
    monotonicity_threshold_cents = 5.0 (matches V4-E)
"""
