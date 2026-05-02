"""
tests.py — Unit tests for pure trading logic functions.

Does not require Robinhood API access. Run with:
    cd src && python tests.py
"""

import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

# ---------------------------------------------------------------------------
# Import pure functions
# ---------------------------------------------------------------------------

from source_data import _position_52w, get_momentum_score

try:
    from main import can_buy_symbol, evaluate_sell_candidate, get_position_value
    from util import RISK_LIMITS, SELL_RULES
    _HAS_MAIN = True
except Exception as e:
    print(f"Warning: could not import main.py ({e}) — main-dependent tests will be skipped")
    _HAS_MAIN = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert(condition: bool, msg: str = "") -> None:
    if not condition:
        raise AssertionError(msg or "assertion failed")


def _make_metrics(
    value_metric: float = 1.0,
    quality_score: float = 0.5,
    yield_trap_flag: bool = False,
) -> pd.Series:
    return pd.Series({
        "value_metric":    value_metric,
        "quality_score":   quality_score,
        "yield_trap_flag": yield_trap_flag,
    })


def _make_holding(
    percent_change: float = 0.0,
    avg_buy: float = 100.0,
    price: float = 100.0,
) -> dict:
    # Robinhood returns percent_change as a percentage string e.g. "-15.3" for -15.3%
    return {
        "percent_change":    str(percent_change),
        "average_buy_price": str(avg_buy),
        "price":             str(price),
        "quantity":          "10",
    }


def _make_holdings(symbol: str = "AAPL", equity: float = 0.0) -> dict:
    return {symbol: {"equity": str(equity), "quantity": "1", "average_buy_price": "100"}}


# ---------------------------------------------------------------------------
# position_52w tests
# ---------------------------------------------------------------------------

def test_position_52w_normal():
    result = _position_52w(55.0, 40.0, 80.0)
    expected = (55.0 - 40.0) / (80.0 - 40.0)  # 0.375
    _assert(abs(result - expected) < 1e-9, f"expected {expected}, got {result}")


def test_position_52w_missing_price():
    _assert(_position_52w(None, 40.0, 80.0) is None)


def test_position_52w_missing_low():
    _assert(_position_52w(55.0, None, 80.0) is None)


def test_position_52w_missing_high():
    _assert(_position_52w(55.0, 40.0, None) is None)


def test_position_52w_high_equals_low():
    _assert(_position_52w(55.0, 80.0, 80.0) is None)


def test_position_52w_high_less_than_low():
    _assert(_position_52w(55.0, 80.0, 40.0) is None)


def test_position_52w_clamp_above_one():
    result = _position_52w(100.0, 40.0, 80.0)   # current > high
    _assert(result == 1.0, f"expected 1.0, got {result}")


def test_position_52w_clamp_below_zero():
    result = _position_52w(20.0, 40.0, 80.0)    # current < low
    _assert(result == 0.0, f"expected 0.0, got {result}")


def test_position_52w_at_low():
    result = _position_52w(40.0, 40.0, 80.0)
    _assert(result == 0.0, f"expected 0.0, got {result}")


def test_position_52w_at_high():
    result = _position_52w(80.0, 40.0, 80.0)
    _assert(result == 1.0, f"expected 1.0, got {result}")


# ---------------------------------------------------------------------------
# momentum_score tests
# ---------------------------------------------------------------------------

def test_momentum_score_none():
    _assert(get_momentum_score(None) == 0.0)


def test_momentum_score_below_015():
    _assert(get_momentum_score(0.0)  == -0.4)
    _assert(get_momentum_score(0.10) == -0.4)
    _assert(get_momentum_score(0.14) == -0.4)


def test_momentum_score_015_to_035():
    _assert(get_momentum_score(0.15) == 0.1)
    _assert(get_momentum_score(0.25) == 0.1)
    _assert(get_momentum_score(0.34) == 0.1)


def test_momentum_score_035_to_075():
    _assert(get_momentum_score(0.35) == 0.3)
    _assert(get_momentum_score(0.50) == 0.3)
    _assert(get_momentum_score(0.74) == 0.3)


def test_momentum_score_075_to_095():
    _assert(get_momentum_score(0.75) == 0.5)
    _assert(get_momentum_score(0.90) == 0.5)
    _assert(get_momentum_score(0.95) == 0.5)


def test_momentum_score_above_095():
    _assert(get_momentum_score(0.96) == 0.2)
    _assert(get_momentum_score(1.0)  == 0.2)


# ---------------------------------------------------------------------------
# sell decision engine tests
# ---------------------------------------------------------------------------

def test_sell_hard_stop_loss():
    if not _HAS_MAIN:
        return
    # -15% is below the -12% stop loss threshold
    holding  = _make_holding(percent_change=-15.0)
    decision = evaluate_sell_candidate("TEST", holding, _make_metrics())
    _assert(decision["should_sell"],         "should_sell must be True")
    _assert(decision["severity"] == "hard",  f"expected hard, got {decision['severity']}")
    _assert("stop loss" in decision["reason"], decision["reason"])


def test_sell_hard_yield_trap():
    if not _HAS_MAIN:
        return
    holding  = _make_holding(percent_change=0.0)
    metrics  = _make_metrics(value_metric=0.10, yield_trap_flag=True)
    decision = evaluate_sell_candidate("TEST", holding, metrics)
    _assert(decision["should_sell"],        "should_sell must be True")
    _assert(decision["severity"] == "hard", f"expected hard, got {decision['severity']}")
    _assert("yield trap" in decision["reason"], decision["reason"])


def test_sell_hard_quality_floor():
    if not _HAS_MAIN:
        return
    floor    = SELL_RULES["sell_low_quality_below"]   # -0.25
    holding  = _make_holding(percent_change=0.0)
    metrics  = _make_metrics(quality_score=floor - 0.1)
    decision = evaluate_sell_candidate("TEST", holding, metrics)
    _assert(decision["should_sell"],        "should_sell must be True")
    _assert(decision["severity"] == "hard", f"expected hard, got {decision['severity']}")


def test_sell_soft_take_profit():
    if not _HAS_MAIN:
        return
    # +40% exceeds the 35% take-profit threshold
    holding  = _make_holding(percent_change=40.0)
    decision = evaluate_sell_candidate("TEST", holding, _make_metrics())
    _assert(decision["should_sell"],        "should_sell must be True")
    _assert(decision["severity"] == "soft", f"expected soft, got {decision['severity']}")
    _assert("take profit" in decision["reason"], decision["reason"])


def test_sell_soft_weak_value():
    if not _HAS_MAIN:
        return
    below    = SELL_RULES["sell_weak_value_below"] - 0.05   # below threshold
    holding  = _make_holding(percent_change=0.0)
    decision = evaluate_sell_candidate("TEST", holding, _make_metrics(value_metric=below))
    _assert(decision["should_sell"],        "should_sell must be True")
    _assert(decision["severity"] == "soft", f"expected soft, got {decision['severity']}")


def test_no_sell_healthy_holding():
    if not _HAS_MAIN:
        return
    holding  = _make_holding(percent_change=5.0)   # +5%, no issues
    decision = evaluate_sell_candidate("TEST", holding, _make_metrics(value_metric=1.0))
    _assert(not decision["should_sell"], f"should not sell; reason={decision['reason']}")


def test_sell_no_metrics_no_crash():
    if not _HAS_MAIN:
        return
    holding  = _make_holding(percent_change=0.0)
    decision = evaluate_sell_candidate("TEST", holding, None)
    # With no metrics, none of the metric-based rules fire; should not sell on 0% change
    _assert(not decision["should_sell"])


# ---------------------------------------------------------------------------
# position cap tests
# ---------------------------------------------------------------------------

def test_position_value_from_holdings():
    if not _HAS_MAIN:
        return
    holdings = _make_holdings("AAPL", equity=430.0)
    _assert(get_position_value("AAPL", holdings) == 430.0)
    _assert(get_position_value("MSFT", holdings) == 0.0)


def test_can_buy_within_position_cap():
    if not _HAS_MAIN:
        return
    # portfolio=$10k, max_single=5%=$500, current_pos=$200, propose $100 → ok
    holdings = _make_holdings("AAPL", equity=200.0)
    ok, reason, adj = can_buy_symbol("AAPL", 100.0, holdings, None, 10_000.0, 5_000.0)
    _assert(ok, f"expected ok, got: {reason}")
    _assert(abs(adj - 100.0) < 0.01, f"expected adj=100, got {adj}")


def test_can_buy_reduced_by_position_cap():
    if not _HAS_MAIN:
        return
    # portfolio=$10k, max_single=5%=$500, current_pos=$450, propose $200 → capped to $50
    holdings = _make_holdings("AAPL", equity=450.0)
    ok, reason, adj = can_buy_symbol("AAPL", 200.0, holdings, None, 10_000.0, 5_000.0)
    _assert(ok, f"expected ok after reduction, got: {reason}")
    _assert(abs(adj - 50.0) < 0.01, f"expected adj=50, got {adj}")


def test_can_buy_blocked_by_position_cap():
    if not _HAS_MAIN:
        return
    # portfolio=$10k, max_single=5%=$500, current_pos=$500 → no room
    holdings = _make_holdings("AAPL", equity=500.0)
    ok, reason, adj = can_buy_symbol("AAPL", 100.0, holdings, None, 10_000.0, 5_000.0)
    _assert(not ok, f"expected blocked, got ok with adj={adj}")


def test_can_buy_bumped_to_min_order():
    if not _HAS_MAIN:
        return
    min_order = RISK_LIMITS["min_order_amount"]   # 5.00
    # room=$2, cash=$5k (≥ min_order) → bumped to min_order=$5
    holdings = _make_holdings("AAPL", equity=498.0)
    ok, reason, adj = can_buy_symbol("AAPL", 100.0, holdings, None, 10_000.0, 5_000.0)
    _assert(ok, f"expected ok (bumped to min_order), got: {reason}")
    _assert(abs(adj - min_order) < 0.01, f"expected adj={min_order}, got {adj}")


def test_can_buy_blocked_when_cash_below_min_order():
    if not _HAS_MAIN:
        return
    min_order = RISK_LIMITS["min_order_amount"]   # 5.00
    # room=$2, cash=$3 (< min_order) → blocked
    holdings = _make_holdings("AAPL", equity=498.0)
    ok, reason, adj = can_buy_symbol("AAPL", 100.0, holdings, None, 10_000.0, 3.0)
    _assert(not ok, f"expected blocked (cash < min_order), got ok with adj={adj}")


def test_can_buy_order_size_capped():
    if not _HAS_MAIN:
        return
    # max_order_pct=10% of cash=$1000. propose $200 when cash=$1000 → capped to $100
    holdings = _make_holdings("AAPL", equity=0.0)
    ok, reason, adj = can_buy_symbol("AAPL", 200.0, holdings, None, 10_000.0, 1_000.0)
    max_order = 1_000.0 * RISK_LIMITS["max_order_pct_of_cash"]
    _assert(ok, f"expected ok after order cap, got: {reason}")
    _assert(abs(adj - max_order) < 0.01, f"expected adj={max_order}, got {adj}")


# ---------------------------------------------------------------------------
# Sector cap tests (use agg_df with sector info)
# ---------------------------------------------------------------------------

def _make_agg_df_multi(rows: list[dict]) -> pd.DataFrame:
    base = {"volume": 1_000_000}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_sector_cap_reduced():
    if not _HAS_MAIN:
        return
    # portfolio=$100k so per-stock cap (5%=$5k) won't fire
    # Technology cap = 25% of $100k = $25k
    # MSFT holds $23900 (Technology), AAPL holds $100 (Technology) → total=$24000, room=$1000
    # propose $1500 for AAPL → reduced to $1000
    agg_df = _make_agg_df_multi([
        {"symbol": "AAPL", "sector": "Technology"},
        {"symbol": "MSFT", "sector": "Technology"},
    ])
    holdings = {
        "AAPL": {"equity": "100",   "quantity": "1"},
        "MSFT": {"equity": "23900", "quantity": "100"},
    }
    ok, reason, adj = can_buy_symbol("AAPL", 1_500.0, holdings, agg_df, 100_000.0, 50_000.0)
    _assert(ok, f"expected ok after sector reduction, got: {reason}")
    _assert(abs(adj - 1000.0) < 0.01, f"expected adj=1000, got {adj}")


def test_sector_cap_blocked():
    if not _HAS_MAIN:
        return
    # Technology already at cap ($25k / $25k)
    agg_df = _make_agg_df_multi([
        {"symbol": "AAPL", "sector": "Technology"},
        {"symbol": "MSFT", "sector": "Technology"},
    ])
    holdings = {
        "AAPL": {"equity": "100",   "quantity": "1"},
        "MSFT": {"equity": "24900", "quantity": "100"},
    }
    ok, reason, adj = can_buy_symbol("AAPL", 200.0, holdings, agg_df, 100_000.0, 50_000.0)
    _assert(not ok, f"expected blocked by sector cap, got ok with adj={adj}")


def test_liquidity_gate():
    if not _HAS_MAIN:
        return
    min_vol = RISK_LIMITS["min_liquidity_volume"]
    agg_df  = _make_agg_df_multi([{"symbol": "ILLQ", "sector": "Technology", "volume": min_vol - 1}])
    ok, reason, _ = can_buy_symbol("ILLQ", 100.0, {}, agg_df, 10_000.0, 5_000.0)
    _assert(not ok, f"expected blocked by liquidity gate, got ok")
    _assert("volume" in reason.lower(), reason)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

_ALL_TESTS = [
    test_position_52w_normal,
    test_position_52w_missing_price,
    test_position_52w_missing_low,
    test_position_52w_missing_high,
    test_position_52w_high_equals_low,
    test_position_52w_high_less_than_low,
    test_position_52w_clamp_above_one,
    test_position_52w_clamp_below_zero,
    test_position_52w_at_low,
    test_position_52w_at_high,
    test_momentum_score_none,
    test_momentum_score_below_015,
    test_momentum_score_015_to_035,
    test_momentum_score_035_to_075,
    test_momentum_score_075_to_095,
    test_momentum_score_above_095,
    test_sell_hard_stop_loss,
    test_sell_hard_yield_trap,
    test_sell_hard_quality_floor,
    test_sell_soft_take_profit,
    test_sell_soft_weak_value,
    test_no_sell_healthy_holding,
    test_sell_no_metrics_no_crash,
    test_position_value_from_holdings,
    test_can_buy_within_position_cap,
    test_can_buy_reduced_by_position_cap,
    test_can_buy_blocked_by_position_cap,
    test_can_buy_bumped_to_min_order,
    test_can_buy_blocked_when_cash_below_min_order,
    test_can_buy_order_size_capped,
    test_sector_cap_reduced,
    test_sector_cap_blocked,
    test_liquidity_gate,
]


if __name__ == "__main__":
    passed = 0
    failed = 0
    skipped = 0
    for t in _ALL_TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed}/{passed + failed} tests passed", end="")
    if skipped:
        print(f", {skipped} skipped", end="")
    print()
    sys.exit(0 if failed == 0 else 1)
