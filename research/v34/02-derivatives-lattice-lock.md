# V34 derivatives lattice methodology lock

Locked 2026-07-18 before implementation or scanning.

## Purpose and boundary

Kalshi threshold and interval ladders form strips of digital options. Their
payoffs imply monotonic survival probabilities, finite-difference interval
probabilities, complements, and exhaustive partitions. V29 checks only
two-leg complements. This sidecar searches the full within-event payoff
lattice, but it is read-only.

A result is a displayed-depth candidate, not a locked realized arbitrage.
Separate orders across legs are not atomic. No candidate can authorize orders
or even a pilot proposal until a separately reviewed legging design bounds
partial fills, cancellation time, residual exposure, hedge cost, and worst-case
loss.

## Eligible contracts

All legs must share the exact underlying, measurement window, settlement
source, event rules, close time, and exceptional-settlement treatment.
The scanner excludes an event when any of those fields is absent, ambiguous,
or inconsistent. The exact event and market rule bytes, series response,
fee-type response, upcoming fee-change response, market response, and orderbook
response are stored and hashed for every candidate.

Only displayed YES asks and NO asks are executable inputs. Prices and sizes use
fixed-point integers. A contract with an unknown fee type, a pending fee
change, an unparseable strike boundary, or an incompletely enumerated void or
exception state is excluded.

Atomic outcome cells include every open interval between strikes, both
unbounded tails, and singleton strike values wherever greater-than,
greater-than-or-equal, less-than, or less-than-or-equal language changes a
payoff. Discrete domains enumerate every possible integer value. Continuous
domains use boundary singletons plus open intervals. YES and NO payouts are
derived separately from the exact rule text. Every rule-defined cancellation,
void, tie, or exceptional settlement is another outcome cell with its exact
payout. If that payout is not machine-verifiable, the event is excluded.

## Integer optimization

For each displayed side \(i\):

- \(q_i\) is a nonnegative integer contract quantity;
- \(d_i\) is displayed executable depth;
- \(a_i\) is the displayed ask in integer cents;
- \(A_{si}\) is the payout in cents in atomic state \(s\);
- \(z\) is the basket's guaranteed payout in integer cents.

The constraints are:

\[
0 \le q_i \le d_i,\qquad
z \le \sum_i A_{si}q_i\quad\text{for every atomic state }s.
\]

Executable cost is the sum of ask notional and exact per-leg taker fees:

\[
C(q)=\sum_i \left(a_iq_i+F_i(q_i,a_i)\right).
\]

For the standard quadratic taker schedule, the cents fee for one leg is:

\[
F_i(q,a)=\left\lceil 7q(a/100)(1-a/100)\right\rceil.
\]

The implementation uses exact rational or decimal arithmetic and applies the
ceiling separately to each order leg. It does not linearize fee rounding. Any
other fee type requires a separately encoded and reviewed formula bound to the
current official schedule. The current official fee PDF and every series fee
response are hash-bound before a scan.

Guaranteed profit is:

\[
\Pi(q,z)=z-C(q).
\]

A candidate requires \(\Pi(q,z)>0\). This general form permits baskets whose
guaranteed payout and cost both exceed one dollar. The scanner does not keep
only one absolute-profit optimum. It enumerates the complete qualifying
primitive-recipe set with exact bounded enumeration or solver no-good cuts.

## Edge and size gate

The net edge is \(\Pi/z\). The two percentage point rule means
\(\Pi/z\ge0.02\) after exact aggregate fee rounding.

For displayed size five, reduce nonzero recipe quantities \(r_i\) by their
greatest common divisor. Candidate enumeration itself imposes
\(5r_i\le d_i\) on every leg. It computes aggregate five-copy quantities
\(q_i=5r_i\), exact per-leg fees, minimum payout, profit, and normalized edge.
The constraints \(\Pi(q,z)>0\) and \(\Pi(q,z)/z\ge0.02\) are inside the
enumeration. They are not post-filters on one maximum-profit solution.

Economically equivalent recipes are collapsed by their reduced primitive
recipe, normalized atomic payoff vector, and exact five-copy cost. At most one
candidate counts per event and snapshot. The measurement gate requires three
distinct event tickers spanning at least two event dates or monthly cohorts.
Repeated observations of one event are persistence telemetry and never increase
the independent-case count. A different recipe in the same event snapshot is
not independent. At least one candidate must also reproduce on consecutive
polls as a separate persistence condition. This gate authorizes only a
legging-risk design review.

## Solver verification

Every reported candidate is independently re-evaluated by exhaustive
atomic-cell payoff arithmetic outside the optimizer. The verifier checks
integer quantities, displayed bounds, rule compatibility, exact fee rounding,
minimum payout, profit, normalized edge, and the five-copy recipe.

Incrementality requires all of the following at the same snapshot:

1. The exact v29 pair rule finds no qualifying explanation.
2. Exhaustive enumeration finds no qualifying positive-profit recipe with two
   or fewer legs that has the candidate's payoff relation.
3. No nonempty proper subrecipe is itself a qualifying guaranteed-profit
   basket.
4. No lower-support recipe has a componentwise equal or greater atomic payoff
   vector at equal or lower exact cost.

Padding a profitable pair with a third leg therefore never counts as an
incremental lattice discovery. The verifier publishes the exhaustive pair,
subrecipe, and dominance results with each candidate.

Synthetic tests cover unit-cost and cost-above-one-dollar arbitrage,
nonprofitable monotonic ladders, singleton strike boundaries, inclusive versus
exclusive strikes, discrete domains, YES and NO complements, per-leg fee
rounding, insufficient fifth-copy depth, exceptional settlement, and a
three-leg partition missed by a pair-only scan. Tests also cover padded
two-leg arbs, economically equivalent recipes, an absolute-profit optimum that
fails the edge rule while a smaller recipe passes, same-event combinatorial
duplicates, and same-event observations inside and outside ten minutes.
Those same-event observations must never increase the independent gate count.

## Modeling connection

A monotone state-space or constrained-spline fit to the ladder is diagnostic.
It can estimate a smoothed risk-neutral survival curve and highlight local
curvature, but raw executable payoff arithmetic remains the only candidate
authority. Model residuals cannot select trades until a chronological frozen
holdout beats the market-mid identity baseline net of asks, fees, and the full
legging-risk bound.
