# Daily Investor

An automated investment strategy tool that combines fundamental analysis with AI-powered sentiment analysis to make informed investment decisions. The system evaluates stocks based on financial metrics, market sentiment, and news analysis, then executes trades via Robinhood.

## 🚀 Key Features

- **Batch AI Sentiment Analysis**: Analyzes multiple stocks per Claude API call using async concurrency — reduces analysis time from hours to minutes
- **Pre-filtering by Value Metric**: Only stocks above `metric_threshold` are sent for sentiment analysis, eliminating wasted API calls
- **Async + Exponential Backoff**: Concurrent Claude calls with automatic retry on rate limits
- **Fractional + Whole Share Fallback**: Attempts fractional orders first; falls back to a whole-share market order if fractional is unavailable
- **Live Cash Tracking**: Re-fetches real available cash before every order to prevent overspending from stale balances
- **Smart Sell Logic**: Only sells on significant price swings (`selloff_threshold`); sentiment used as a hold-check, not a proactive sweep
- **Auto-Approval System**: Option to automatically execute trades that meet confidence criteria
- **Fundamental Analysis**: Screens for undervalued stocks using P/E, P/B ratios, and dividend yields
- **Real-time Market Data**: Automatically updates P/E and P/B ratio benchmarks via Finviz
- **Sector/Industry Analysis**: Applies different valuation thresholds based on real-time benchmarks
- **ETF Dollar-Cost Averaging**: Automated periodic investments in a configurable set of ETFs
- **Comprehensive Logging**: Full stack traces on errors, per-decision reasoning, and cash accounting at every step

## 🏗️ Project Structure

```
daily_investor/
├── src/
│   ├── main.py                # Main application entry point
│   ├── sentiment_analysis.py  # Batch + async Claude sentiment analysis
│   ├── sentiments.py          # News/Reddit data collection
│   ├── source_data.py         # Data collection and processing
│   └── util.py                # Utility functions and configurations
├── data/                      # Data storage directory (CSV cache)
├── .env                       # Environment variables
└── requirements.txt           # Python dependencies
```

## 🤖 Sentiment Analysis Architecture

Sentiment analysis uses a two-path design:

### Buy Path — Batch Async
All buy candidates are analyzed in a single async round-trip:
1. Pre-filter candidates by `metric_threshold` (eliminates stocks with no valuation signal)
2. Build batches of `BATCH_SIZE` stocks (default: 6) from cached CSV data
3. Dispatch all batches concurrently via `asyncio.gather()` with a `Semaphore(MAX_CONCURRENT=5)`
4. Exponential backoff (`2^attempt × (1 + jitter)`) on 429s and transient errors
5. Parse per-symbol results from Claude's structured response and execute orders

### Sell Path — Batch Async (Hold-Check Only)
Selling is purely reactive to price swings:
1. Scan all holdings for `abs(percent_change) > selloff_threshold` — zero API calls
2. If any candidates found, batch them in one async Claude call as a hold-check
3. If Claude recommends YES (hold) with sufficient confidence → keep the position
4. Otherwise → execute sell order

No proactive sentiment sweeps of all holdings. If nothing breaches the threshold, sales analysis exits immediately.

### LangGraph Single-Stock Path (Internal)
Used only when the batch path is unavailable. Includes a short-circuit router: if `gather_sentiments` determines there is no valid data (stock not in aggregated data, no news), it sets `skip_analysis=True` and the workflow jumps directly to `END` without calling Claude.

### Workflow Diagram

```
gather_sentiments
      │
      ├─ skip_analysis=True ──────────────→ END (no Claude call)
      │
      └─ skip_analysis=False → analyze_sentiment → END
```

## 🛠️ Prerequisites

- Python 3.10+
- Robinhood account
- Anthropic API key (for sentiment analysis)
- Required Python packages (see `requirements.txt`)

## 🚀 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/daily_investor.git
   cd daily_investor
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables in `.env`:
   ```
   RB_ACCT=your_robinhood_email
   RB_CREDS=your_robinhood_password
   RB_MFA_SECRET=your_totp_secret        # Optional: skip MFA prompt
   ANTHROPIC_API_KEY=your_anthropic_key  # Required for sentiment analysis
   ```

## ⚙️ Configuration

All settings live in `investments.yaml`.

### Main Configuration

```yaml
config:
  # Fundamental screening
  ignore_negative_pe: false    # Skip stocks with negative P/E
  ignore_negative_pb: false    # Skip stocks with negative P/B
  dividend_threshold: 3        # Minimum dividend yield %
  metric_threshold: 5          # Minimum value_metric score to pass pre-filter
  selloff_threshold: 30        # % price swing that triggers sell analysis

  # Capital allocation
  weekly_investment: 400       # Weekly investment amount (USD)
  index_pct: 0.8               # Fraction of funds allocated to ETFs

  # Sentiment analysis
  use_sentiment_analysis: true
  confidence_threshold: 70     # Minimum confidence % to execute a trade
  auto_approve: false          # Auto-confirm trades without manual prompts

  # ETFs for dollar-cost averaging
  etfs:
    - SPY
    - VOO
    - VTI
    - QQQ
    - SCHD
```

### Operating Modes

| Mode | `auto_approve` | `use_sentiment_analysis` | `confidence_threshold` | Notes |
|------|---------------|--------------------------|------------------------|-------|
| Safe | `false` | `true` | `70` | Manual confirmation, sentiment shown before each trade |
| Automated | `true` | `true` | `80` | Executes high-confidence trades automatically |
| Fully Automated | `true` | `true` | `0` | No manual intervention — use with caution |
| Manual | `false` | `false` | n/a | No sentiment, buy by value metric weight only |

### Valuation Scores Explained

The `value_metric` score drives both pre-filtering and portfolio weighting:

| Component | Formula | When scored |
|-----------|---------|-------------|
| `pe_comp` | `sector_PE / actual_PE` | Only if `actual_PE < sector_PE` |
| `pb_comp` | `sector_PB / actual_PB` | Only if `actual_PB < sector_PB` |
| `div_comp` | `dividend_yield / 3.0` | Only if `yield > 3%` |
| `value_metric` | `pe_comp + pb_comp + div_comp` | Sum of above |

- `value_metric = 0` → stock is not undervalued on any metric
- `value_metric ≥ 2` → undervalued on at least two metrics (strong case)
- Set `metric_threshold` in config to control the minimum score for consideration

## 🏃‍♂️ Running the Application

```bash
# Full run: refresh data, fetch news, analyze, trade
python src/main.py

# Skip data generation — reuse today's cached CSVs (much faster)
python src/main.py --skip-data

# Help
python src/main.py --help
```

The strategy runs in a loop (up to `max_iterations=10`), re-evaluating remaining candidates each iteration. Stocks that were skipped, failed, or already bought are permanently excluded from subsequent iterations.

## 📊 Performance

| Before | After |
|--------|-------|
| ~1 API call per stock, sequential | Batch of 6 stocks per call, all batches concurrent |
| `time.sleep(1)` per stock + `sleep(3)` every 5 | No sleeps in analysis; 0.5s between order placements only |
| 2400 stocks × ~6s = ~4 hours | Pre-filter to ~10–50 stocks, batch async = ~2–5 minutes |

## 🔍 Troubleshooting

**All stocks show "Batch error / NEUTRAL"**
The async Claude call failed silently. Check `investment_bot.log` — errors now log full stack traces (`exc_info=True`). Common causes: missing `ANTHROPIC_API_KEY`, network issue, or Python < 3.10 event loop incompatibility.

**"Fractional order unavailable, retrying as market order"**
Some tickers (often foreign ADRs or lower-liquidity stocks) don't support fractional shares on Robinhood. The bot automatically retries with `order_buy_market(symbol, 1)` for 1 whole share.

**"Cash exhausted" stops buys early**
Available cash is re-fetched from Robinhood before every order (accounting for all pending/queued orders). If the balance drops below $1 after ETF allocation, the buy loop exits. This is correct behaviour — it prevents overspending when many orders are queued.

**Robinhood 429 errors on orders**
A 0.5s sleep between successful order placements is enforced to stay within Robinhood's order rate limit. If 429s persist, increase this value in `make_buys()`.

**Stock not found in aggregated data**
If a stock appears in the buy candidates but not in `agg_data_*.csv`, it gets a warning and `skip_analysis=True` in the LangGraph workflow — no Claude call is made, and it is skipped. Re-run data generation with `generate_fresh=True` to rebuild the aggregated data file.

## 🔒 Security

- Never commit `.env` or any file containing credentials to version control
- `.env` is `.gitignore`d by default
- All sensitive values (API keys, passwords) are read from environment variables at runtime

## ⚠️ Disclaimer

This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred while using this tool. Always conduct your own research and consider consulting with a licensed financial advisor before making investment decisions.

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.