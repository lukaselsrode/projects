# Daily Investor

An automated investment strategy tool that helps identify and execute stock trades based on fundamental analysis metrics. The system evaluates stocks based on various financial ratios, sector/industry benchmarks, and market data to make informed investment decisions.

## Features

- **Automated Stock Screening**: Scans for undervalued stocks based on P/E, P/B ratios, and dividend yields
- **Sector/Industry Analysis**: Applies different valuation thresholds based on sector and industry benchmarks
- **Portfolio Management**: Automates buying and selling decisions with configurable parameters
- **ETF Dollar-Cost Averaging**: Supports automated periodic investments in a set of predefined ETFs
- **Risk Management**: Implements stop-loss and take-profit mechanisms
- **Logging**: Comprehensive logging of all operations and decisions

## Prerequisites

- Python 3.7+
- Robinhood account (for trading)
- Required API keys and credentials

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/daily_investor.git
   cd daily_investor
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables (see Configuration section below)

## Configuration

### Environment Variables

Create a `.env` file in the project root with the following variables:

```
RB_ACCT=your_robinhood_email
RB_CREDS=your_robinhood_password
RB_MFA_SECRET=your_mfa_secret  # Optional, for automated MFA
```

### Application Configuration (`investments.yaml`)

The `investments.yaml` file contains all application configurations and sector/industry specific parameters:

#### Global Configuration

```yaml
config:
  # Ignore negative P/E ratios in calculations
  ignore_negative_pe: false
  
  # Ignore negative P/B ratios in calculations
  ignore_negative_pb: false
  
  # Minimum dividend yield percentage to consider
  dividend_threshold: 2.5
  
  # Minimum value metric threshold for stock selection
  metric_threshold: 4
  
  # Percentage change threshold to trigger sell orders
  selloff_threshold: 30
  
  # Weekly investment amount in dollars
  weekly_investment: 400
  
  # List of ETFs for dollar-cost averaging
  etfs:
    - SPY
    - VOO
    - VTI
    - QQQ
    - SCHD
```

#### Sector/Industry Configuration

Below the global config, you'll find sector-specific P/E and P/B ratio thresholds. Each sector can have a default and industry-specific overrides:

```yaml
# Example sector configuration
Technology Services:
  default: [40, 6]  # [P/E ratio, P/B ratio]
  Software: [37, 9]
  Information Technology Services: [33.6, 4]
```

To modify the valuation criteria for a specific industry, add or update its entry under the appropriate sector. The first number represents the P/E ratio threshold, and the second number represents the P/B ratio threshold. Use `null` to ignore a particular metric for an industry.

## Usage

### Running the Strategy

```bash
python src/investments.py
```

### Main Components

- **generate_daily_buy_list()**: Fetches and analyzes stock data to identify undervalued opportunities
- **make_buys()**: Handles the execution of buy orders for both individual stocks and ETFs
- **make_sales()**: Manages sell orders based on predefined criteria
- **get_available_cash()**: Calculates available cash, accounting for pending orders

### Supported Commands

- Run the full strategy: `python src/investments.py`
- Generate buy list: `generate_daily_buy_list()`
- Execute buys: `make_buys()`
- Execute sales: `make_sales()`
- Check available cash: `get_available_cash()`

## Strategy Details

The investment strategy focuses on:

1. **Value Investing**: Identifies stocks trading below their intrinsic value using P/E and P/B ratios
2. **Sector Rotation**: Adjusts valuation thresholds based on sector/industry benchmarks
3. **Diversification**: Spreads investments across sectors and asset classes
4. **Risk Management**: Implements stop-loss and position sizing rules

## Logging

All activities are logged to `investment_bot.log` in the project root directory.

## Security

- **Never commit sensitive data** (API keys, credentials) to version control
- Use environment variables for sensitive information
- The `.env` file is included in `.gitignore` by default

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred while using this tool. Always conduct your own research and consider consulting with a licensed financial advisor before making investment decisions.
