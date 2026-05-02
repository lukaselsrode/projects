# Daily Investor

An automated investment strategy tool that combines fundamental analysis with AI-powered sentiment analysis to make informed investment decisions. The system evaluates stocks based on financial metrics, momentum, market sentiment, and news analysis, then executes trades via Robinhood.

## Key Features

- **Factor-Based Scoring**: Combines value (P/E, P/B), income (dividend yield), quality, and 52-week momentum into a single `value_metric`
- **Valuation Guardrails**: Caps P/E and P/B components to prevent extreme scores from bad/thin fundamental data
- **Portfolio Risk Controls**: Per-position cap, per-sector cap, and per-order size cap enforced before every buy
- **Disciplined Sell Engine**: Separates hard sells (stop-loss, yield trap, quality floor) from soft sells (take-profit, weak value) with sentiment override only on soft sells
- **Batch AI Sentiment Analysis**: Analyzes multiple stocks per Claude API call using async concurrency
- **Async + Exponential Backoff**: Concurrent Claude calls with automatic retry on rate limits
- **Fractional + Whole Share Fallback**: Attempts fractional orders first; falls back to a whole-share market order
- **Live Cash Tracking**: Re-fetches real available cash before every order
- **Auto-Approval System**: Configurable automatic trade execution
- **Real-time Valuation Benchmarks**: Updates P/E and P/B thresholds per sector/industry via Finviz
- **ETF Dollar-Cost Averaging**: Periodic allocation to a configurable set of ETFs
- **Comprehensive Logging**: Per-decision reasoning, cap decisions, sell severity, and cash accounting at every step

## Project Structure

```
daily_investor/
├── src/
│   ├── main.py                # Entry point: login, buy/sell loops, risk controls
│   ├── sentiment_analysis.py  # Batch async + single-stock Claude sentiment
│   ├── sentiments.py          # News/Reddit data collection
│   ├── source_data.py         # Universe generation, fundamentals, scoring
│   ├── util.py                # Config constants, schema, CSV helpers
│   └── tests.py               # Pure-function unit tests (no API required)
├── data/                      # CSV cache (dated filenames, newest always used)
├── investments.yaml           # All configuration
└── .env                       # Credentials (never commit)
```

## Scoring Model

### Factor Scores

| Score | What it measures |
|-------|-----------------|
| `value_score` | P/E and P/B cheapness relative to sector thresholds |
| `income_score` | Dividend yield quality (0 if no yield or yield trap) |
| `quality_score` | Liquidity, earnings existence, dividend health signal |
| `momentum_score` | 52-week price-location health (see table below) |

### Momentum Score — 52-Week Position

`position_52w = (current_price − 52w_low) / (52w_high − 52w_low)`, clamped to [0, 1].

| position_52w | momentum_score | Signal |
|---|---|---|
| < 0.15 | −0.40 | Possible falling knife |
| 0.15 – 0.35 | +0.10 | Beaten down, not dead |
| 0.35 – 0.75 | +0.30 | Healthy mid/upper range |
| 0.75 – 0.95 | +0.50 | Strong momentum |
| > 0.95 | +0.20 | Near 52w high, possible extension |
| missing data | 0.00 | No signal |

### Final Metric Formula

```
value_metric = 0.45 × value_score
             + 0.25 × quality_score
             + 0.15 × income_score
             + 0.15 × momentum_score
```

Weights are YAML-configurable under `score_weights`. They must sum to 1.0; if not, defaults are used and a warning is logged.

### Valuation Guardrails

Before computing `value_score`, each component is gated and capped:

```
pe_comp = sector_PE / pe_ratio   (only if min_pe_ratio ≤ pe_ratio < sector_PE)
pe_comp = min(pe_comp, max_pe_component)

pb_comp = sector_PB / pb_ratio   (only if min_pb_ratio ≤ pb_ratio < sector_PB)
pb_comp = min(pb_comp, max_pb_component)

value_score = 0.6 × pe_comp + 0.4 × pb_comp
```

This prevents extreme value_metric values from thin/suspicious fundamentals (e.g. PE=0.05 previously produced scores in the hundreds).

### Agg Data Schema

Every scored stock row contains:

```
symbol, industry, sector, volume,
pe_ratio, pb_ratio, dividend_yield,
current_price, low_52w, high_52w, position_52w,
pe_comp, pb_comp,
value_score, income_score, quality_score, momentum_score,
yield_trap_flag, value_metric, buy_to_sell_ratio
```

## Portfolio Risk Controls

Applied to every buy before an order is placed:

| Rule | Config key | Default | Behaviour |
|------|-----------|---------|-----------|
| Liquidity gate | `min_liquidity_volume` | 500,000 | Skip if volume below threshold |
| Order size cap | `max_order_pct_of_cash` | 10% | Cap single order to 10% of available cash |
| Position cap | `max_single_position_pct` | 5% | Reduce buy so total position ≤ 5% of portfolio |
| Sector cap | `max_sector_pct` | 25% | Reduce buy so sector exposure ≤ 25% of portfolio |
| Minimum order | `min_order_amount` | $5.00 | Skip if reduced amount falls below this |

When a cap is hit, the allocation is **reduced** to the maximum allowed rather than skipped outright. Only if the reduced amount falls below `min_order_amount` is the buy skipped. Every cap decision is logged.

Example:
```
Portfolio $10,000 | AAPL position $430 | position cap $500 → room $70
Proposed buy $200 → reduced to $70
$70 ≥ min_order_amount $5.00 → buy $70
```

## Sell Decision Engine

Each non-ETF holding is evaluated by `evaluate_sell_candidate()` which classifies sells as **hard** or **soft**:

### Hard Sells — execute immediately, sentiment cannot override

| Trigger | Condition |
|---------|-----------|
| Stop loss | `percent_change ≤ stop_loss_pct` (default −12%) |
| Yield trap | `yield_trap_flag=True` and `value_metric < sell_weak_value_below` |
| Quality floor | `quality_score < sell_low_quality_below` (default −0.25) |

### Soft Sells — sentiment can hold

| Trigger | Condition |
|---------|-----------|
| Take profit | `percent_change ≥ take_profit_pct` (default +35%) |
| Weak value | `value_metric < sell_weak_value_below` (default 0.25) and held ≥ `min_days_held_before_value_exit` days |

If sentiment returns `YES` with confidence ≥ `confidence_threshold`, a soft sell is held. Hard sells always execute regardless of sentiment.

### Sell Cycle Summary Log

```
Sell scan: N holdings scanned | H hard | S soft | N no-action
Sell summary: N scanned | H hard | S soft candidates | X held on sentiment | Y executed
```

## Configuration

All settings live in `investments.yaml` under the `config:` key.

```yaml
config:
  # Fundamental screening
  ignore_negative_pe: false
  ignore_negative_pb: false
  dividend_threshold: 0.03       # Minimum dividend yield (decimal: 0.03 = 3%)
  metric_threshold: 0.8          # Minimum value_metric to pass pre-filter

  # Capital allocation
  weekly_investment: 400
  index_pct: 0.01                # Fraction of cash allocated to ETFs each run
  auto_approve: true
  use_sentiment_analysis: true
  confidence_threshold: 50
  etfs: [SPY, VOO, VTI, QQQ, SCHD, MPLY, SMH]

  # Factor weights (must sum to 1.0)
  score_weights:
    value: 0.45
    quality: 0.25
    income: 0.15
    momentum: 0.15

  # Valuation guardrails
  valuation_guardrails:
    max_pe_component: 5.0        # Cap on pe_comp to prevent extreme scores
    max_pb_component: 5.0
    min_pe_ratio: 1.0            # PE below this treated as suspicious → pe_comp=0
    min_pb_ratio: 0.1

  # Portfolio risk limits
  risk:
    max_single_position_pct: 0.05
    max_sector_pct: 0.25
    max_order_pct_of_cash: 0.10
    min_order_amount: 5.00
    min_liquidity_volume: 500000

  # Sell rules (all percentages as decimals)
  sell_rules:
    stop_loss_pct: -0.12
    trailing_stop_pct: -0.15
    take_profit_pct: 0.35
    sell_weak_value_below: 0.25
    sell_yield_trap: true
    sell_low_quality_below: -0.25
    min_days_held_before_value_exit: 7
```

The remainder of `investments.yaml` contains per-sector and per-industry `[PE_threshold, PB_threshold]` pairs used by the valuation engine.

### Operating Modes

| Mode | `auto_approve` | `use_sentiment_analysis` | `confidence_threshold` | Notes |
|------|---------------|--------------------------|------------------------|-------|
| Safe | `false` | `true` | `70` | Manual confirmation before each trade |
| Automated | `true` | `true` | `80` | Executes high-confidence trades automatically |
| Fully Automated | `true` | `true` | `0` | No manual intervention — use with caution |
| No Sentiment | `false` | `false` | n/a | Buys by value_metric weight only |

## Sentiment Analysis Architecture

### Buy Path — Batch Async
1. Pre-filter candidates by `metric_threshold`
2. Build batches of `BATCH_SIZE=6` stocks from cached CSV data
3. Dispatch all batches concurrently via `asyncio.gather()` with `Semaphore(MAX_CONCURRENT=5)`
4. Exponential backoff (`2^attempt × (1 + jitter)`) on 429s and transient errors
5. Parse per-symbol results and run through risk controls before placing orders

### Sell Path — Hard/Soft Engine
1. Load all holdings and agg_data once
2. Call `evaluate_sell_candidate()` for each non-ETF holding
3. Execute hard sells immediately (no sentiment check)
4. Batch soft sell candidates through Claude as a hold-check
5. Sentiment `YES` with sufficient confidence holds the position; otherwise sell executes

### LangGraph Single-Stock Path
Used when the batch client is unavailable. Short-circuits to `END` without calling Claude if there is no valid fundamental or news data for the symbol.

## Running the Application

```bash
# Full run — refresh data, fetch news, analyze, trade
python src/main.py

# Skip data generation — reuse today's cached CSVs (much faster)
python src/main.py --skip-data

# Run pure-function unit tests (no Robinhood or Claude API required)
python src/tests.py
```

The strategy runs in a loop (up to 10 iterations). Stocks that were skipped, failed, or already bought are excluded from subsequent iterations.

## Setup

**Requirements:** Python 3.10+, Robinhood account, Anthropic API key

```bash
git clone https://github.com/yourusername/daily_investor.git
cd daily_investor
pip install -r requirements.txt
```

`.env` file:
```
RB_ACCT=your_robinhood_email
RB_CREDS=your_robinhood_password
RB_MFA_SECRET=your_totp_secret        # Optional: skip interactive MFA prompt
ANTHROPIC_API_KEY=your_anthropic_key  # Required for sentiment analysis
```

## Troubleshooting

**Inflated value_metrics from old cached CSVs**
The bot always loads the most-recently dated CSV for each dataset. Delete stale files from `data/` or run with fresh data generation (answer `y` to the "Generate fresh data?" prompt). Old CSVs pre-dating the guardrail changes will have a different schema and produce incorrect scores.

**"All stocks show NEUTRAL"**
Batch Claude call failed. Check `investment_bot.log` for the stack trace. Common causes: missing `ANTHROPIC_API_KEY`, network issue, or Python < 3.10 event loop incompatibility.

**"Fractional order unavailable, retrying as market order"**
Some tickers (foreign ADRs, low-liquidity stocks) don't support fractional shares on Robinhood. The bot retries with `order_buy_market(symbol, 1)` automatically.

**"Skipping SYMBOL: position cap reached"**
The stock already fills its allowed slice of the portfolio (default 5%). This is expected risk-control behaviour. Adjust `max_single_position_pct` in `investments.yaml` if needed.

**"Skipping SYMBOL: sector cap reached"**
A single sector would exceed 25% of portfolio value. Either the sector is already concentrated or the stock's allocation would push it over. Adjust `max_sector_pct` to change the limit.

**"Cash exhausted" stops buys early**
Available cash is re-fetched from Robinhood before every order (accounting for all pending/queued orders). If the balance drops below $1 after ETF allocation, the buy loop exits correctly.

## Security

- Never commit `.env` or any file containing credentials
- All sensitive values are read from environment variables at runtime
- `.env` is `.gitignore`d by default

## Disclaimer

This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred while using this tool. Always conduct your own research and consider consulting with a licensed financial advisor before making investment decisions.

## License

MIT License — see [LICENSE](LICENSE) for details.
