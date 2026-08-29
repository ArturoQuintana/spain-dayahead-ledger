"""Property-based tests (hypothesis) for the three pure primitives the money
math rests on. Example-based tests pin the cases we thought of; these assert
INVARIANTS that must hold for every input — the oracle can't be beaten, the
hour-pick truly partitions cheap from dear, and Kendall tau stays a valid
correlation. A counterexample here is a real bug in the P&L foundation."""
from hypothesis import assume, given
from hypothesis import strategies as st

from talea.loop import (FEE_EUR_MWH, N_HOURS, POWER_MW, RT_EFF,
                              kendall_tau, pick_hours, pnl_eur)

prices = st.floats(min_value=-500, max_value=4000, allow_nan=False,
                   allow_infinity=False)
profiles = st.lists(prices, min_size=24, max_size=24).map(
    lambda xs: {h: xs[h] for h in range(24)})
four_hours = st.lists(st.integers(0, 23), min_size=4, max_size=4, unique=True)


@st.composite
def paired_sequences(draw):
    n = draw(st.integers(2, 24))
    return (draw(st.lists(prices, min_size=n, max_size=n)),
            draw(st.lists(prices, min_size=n, max_size=n)))


# ---- pnl_eur -----------------------------------------------------------------

@given(profiles, four_hours)
def test_no_2x2_strategy_ever_beats_the_oracle(profile, hrs):
    """Capture <= 100%: buying the 2 cheapest and selling the 2 dearest hours is
    the unbeatable choice, so any other disjoint 2/2 pick earns no more."""
    buy, sell = sorted(hrs[:2]), sorted(hrs[2:])
    oracle = pnl_eur(*pick_hours(profile), profile)
    assert pnl_eur(buy, sell, profile) <= oracle


@given(four_hours)
def test_zero_prices_reduce_to_the_pure_fee_floor(hrs):
    """With free energy, P&L is exactly minus the fees on every MWh moved —
    costs are always explicit, never hidden."""
    profile = {h: 0.0 for h in range(24)}
    buy, sell = sorted(hrs[:2]), sorted(hrs[2:])
    expected = round(-FEE_EUR_MWH * (POWER_MW * 2 + POWER_MW * RT_EFF * 2), 2)
    assert pnl_eur(buy, sell, profile) == expected


@given(profiles, four_hours, st.floats(min_value=0.01, max_value=1000))
def test_a_dearer_sell_hour_never_lowers_pnl(profile, hrs, bump):
    """Monotonicity: raising the price of an hour you SELL into can only help."""
    buy, sell = sorted(hrs[:2]), sorted(hrs[2:])
    base = pnl_eur(buy, sell, profile)
    lifted = dict(profile); lifted[sell[0]] += bump
    assert pnl_eur(buy, sell, lifted) >= base


# ---- pick_hours --------------------------------------------------------------

@given(profiles)
def test_pick_hours_partitions_cheap_strictly_below_dear(profile):
    buy, sell = pick_hours(profile)
    assert len(buy) == N_HOURS and len(sell) == N_HOURS
    assert set(buy).isdisjoint(sell)                      # never buy and sell the same hour
    assert set(buy) | set(sell) <= set(profile)          # only real hours
    assert buy == sorted(buy) and sell == sorted(sell)   # deterministic order
    assert max(profile[h] for h in buy) <= min(profile[h] for h in sell)


@given(profiles)
def test_pick_hours_is_deterministic(profile):
    assert pick_hours(profile) == pick_hours(profile)


# ---- kendall_tau -------------------------------------------------------------

@given(paired_sequences())
def test_tau_is_none_or_within_unit_range(xy):
    t = kendall_tau(*xy)
    assert t is None or -1.0 <= t <= 1.0


@given(paired_sequences())
def test_tau_is_symmetric(xy):
    x, y = xy
    assert kendall_tau(x, y) == kendall_tau(y, x)


@given(st.lists(prices, min_size=2, max_size=24))
def test_tau_of_a_sequence_with_itself_is_one(x):
    assume(len(set(x)) >= 2)                 # at least one non-tied pair
    assert kendall_tau(x, x) == 1.0


@given(st.lists(prices, min_size=2, max_size=24))
def test_tau_against_the_reversed_ranking_is_minus_one(x):
    assume(len(set(x)) == len(x))            # strictly distinct -> no ties
    assert kendall_tau(x, [-v for v in x]) == -1.0
