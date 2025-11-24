# Daily Investor

An automated investment strategy tool that combines fundamental analysis with AI-powered sentiment analysis to make informed investment decisions. The system evaluates stocks based on financial metrics, market sentiment, and news analysis.

## 🚀 Key Features

- **AI-Powered Sentiment Analysis**: Leverages LangGraph and Claude to analyze news and social media sentiment
- **Confidence-Based Trading**: Implements confidence thresholds to ensure high-quality trade decisions
- **Auto-Approval System**: Option to automatically execute trades that meet confidence criteria
- **Flexible Operation Modes**: Run in fully automated, semi-automated, or manual confirmation modes
- **Fundamental Analysis**: Screens for undervalued stocks using P/E, P/B ratios, and dividend yields
- **Real-time Market Data**: Automatically updates P/E and P/B ratio benchmarks
- **Sector/Industry Analysis**: Applies different valuation thresholds based on real-time benchmarks
- **Portfolio Management**: Automates buying and selling decisions with sentiment-based validation
- **ETF Dollar-Cost Averaging**: Supports automated periodic investments in a set of predefined ETFs
- **Risk Management**: Implements stop-loss, take-profit, and sentiment-based trade validation
- **Comprehensive Logging**: Detailed logging of all operations, decisions, and sentiment analysis

## 🏗️ Project Structure

```
daily_investor/
├── src/
│   ├── main.py              # Main application entry point
│   ├── sentiments.py        # Sentiment analysis module
│   ├── source_data.py       # Data collection and processing
│   └── util.py             # Utility functions and configurations
├── data/                   # Data storage directory
├── .env                    # Environment variables
└── requirements.txt        # Python dependencies
```

## 🤖 Sentiment Analysis with LangGraph

The system includes advanced sentiment analysis using LangGraph and Claude:

- **Multi-source Analysis**: Combines news and Reddit sentiment
- **Workflow-based Processing**: Uses LangGraph for structured sentiment analysis
- **Confidence Scoring**: Provides confidence levels for each recommendation
- **Explainable AI**: Includes reasoning behind each recommendation
- **Configurable Thresholds**: Set minimum confidence levels for trade execution
- **Auto-Approval**: Optional automatic execution of high-confidence trades

### Sentiment Analysis Workflow

1. **Data Collection**:
   - News articles from yfinance
   - Reddit sentiment data
   - Market sentiment indicators

2. **Analysis**:
   - Sentiment scoring
   - Source credibility assessment
   - Trend analysis
   - Confidence calculation

3. **Decision Making**:
   - Buy/sell recommendations
   - Confidence scoring (0-100%)
   - Detailed reasoning for each recommendation
   - Auto-approval for high-confidence trades (configurable threshold)
   - Manual review for borderline cases

## 🛠️ Prerequisites

- Python 3.7+
- Robinhood account (for trading)
- Anthropic API key (for sentiment analysis)
- Required Python packages (see requirements.txt)

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
   ANTHROPIC_API_KEY=your_anthropic_api_key  # Required for sentiment analysis
   ```

## ⚙️ Configuration

### Running Modes

The system supports three main operating modes that can be configured in `investments.yaml`:

1. **Safe Mode (Recommended for New Users)**
   ```yaml
   auto_approve: false
   use_sentiment_analysis: true
   confidence_threshold: 70
   ```
   - Requires manual confirmation for all trades
   - Shows sentiment analysis results before each trade
   - Best for learning and validation

2. **Automated Mode (Confidence-Based)**
   ```yaml
   auto_approve: true
   use_sentiment_analysis: true
   confidence_threshold: 80
   ```
   - Automatically executes high-confidence trades (≥80% confidence)
   - Requires manual review for lower confidence trades
   - Balances automation with oversight

3. **Fully Automated Mode**
   ```yaml
   auto_approve: true
   use_sentiment_analysis: true
   confidence_threshold: 0  # Accepts all confidence levels
   ```
   - Fully automated trading
   - No manual intervention required
   - Use with caution - only recommended for experienced users

### Main Configuration (investments.yaml)

The `investments.yaml` file contains all application configurations and sector/industry specific parameters:

```yaml
config:
  # Basic Settings
  ignore_negative_pe: false    # Ignore stocks with negative P/E ratios
  ignore_negative_pb: false    # Ignore stocks with negative P/B ratios
  dividend_threshold: 3        # Minimum dividend yield percentage
  metric_threshold: 5          # Minimum number of metrics to consider
  auto_approve: false          # Auto-confirm trades without manual approval
  use_sentiment_analysis: true # Enable/disable AI sentiment analysis
  confidence_threshold: 70     # Minimum confidence percentage (0-100) required for trade execution
  selloff_threshold: 30        # Percentage drop to trigger sell analysis
  weekly_investment: 400       # Weekly investment amount in USD
  index_pct: 0.8               # Percentage of funds to allocate to ETFs (vs individual stocks)
  
  # Sentiment Analysis
  use_sentiment_analysis: true # Enable/disable sentiment analysis
  confidence_threshold: 70     # Minimum confidence percentage required for trade execution
  auto_approve: false          # Automatically approve trades without confirmation
  
  # ETF Configuration
  etfs:
    - SPY
    - VOO
    - VTI
    - QQQ
    - SCHD
```

### Sentiment Analysis Features

The sentiment analysis system includes several powerful features:

- **Confidence Threshold**: 
  - Only executes trades when the sentiment analysis confidence is above the specified threshold (default: 70%)
  - Helps prevent low-confidence trades from being executed
  - Configurable in `investments.yaml`

- **Auto-Approval**:
  - When enabled (`auto_approve: true`), the system will automatically execute trades without manual confirmation
  - When disabled, you'll be prompted to confirm each trade
  - Recommended to keep disabled during testing

- **Multi-source Analysis**:
  - Combines news articles and Reddit sentiment
  - Analyzes both positive and negative sentiment indicators
  - Considers source credibility and recency

### Enabling/Disabling Features

You can enable or disable features by modifying the `investments.yaml` file:

```yaml
# Enable auto-approval of trades (use with caution)
auto_approve: false

# Enable/disable sentiment analysis
use_sentiment_analysis: true

# Adjust confidence threshold (0-100)
confidence_threshold: 70
```

### Environment Variables

Set these in your `.env` file:

```
RB_ACCT=your_robinhood_email
RB_CREDS=your_robinhood_password
ANTHROPIC_API_KEY=your_anthropic_api_key  # Required for sentiment analysis
USE_SENTIMENT_ANALYSIS=true              # Optional: Override YAML setting
```

### Running with Different Configurations

1. **Safe Mode (Recommended for Initial Setup)**:
   ```yaml
   # Disable auto-approve and enable confirmation prompts
   auto_approve: false
   use_sentiment_analysis: true
   confidence_threshold: 70
   ```

2. **Automated Mode (For Experienced Users)**:
   ```yaml
   # Enable auto-approve for fully automated trading
   auto_approve: true
   use_sentiment_analysis: true
   confidence_threshold: 75  # Higher threshold for automated trading
   ```

3. **Manual Mode**:
   ```yaml
   # Disable sentiment analysis completely
   use_sentiment_analysis: false
   ```

## 🏃‍♂️ Running the Application

1. First, ensure your `.env` file is properly configured
2. Run the main script:
   ```bash
   python src/main.py
   ```

3. The system will:
   - Log in to your Robinhood account
   - Check available funds
   - Analyze market conditions
   - Present trading opportunities
   - Execute trades based on your configuration

## �️ Sample Output

Here's an example of the system in action, showing the sentiment analysis and trade decision process:

```
2025-11-24 13:28:23,138 - investment_bot - INFO - Allocation: $320.00 to ETFs (80%), $80.00 to picked stocks (20%)

=== Sentiment Analysis for BABA ===
2025-11-24 13:28:44,255 - investment_bot - INFO - Recommendation: YES
2025-11-24 13:28:44,255 - investment_bot - INFO - Confidence: 75.0%
2025-11-24 13:28:44,255 - investment_bot - INFO - Reasoning: The sentiment is strongly positive with Alibaba's Qwen AI app achieving impressive 10+ million downloads...

=== Sentiment Analysis for WB ===
2025-11-24 13:29:18,066 - investment_bot - INFO - Recommendation: NO
2025-11-24 13:29:18,066 - investment_bot - INFO - Confidence: 75.0%
2025-11-24 13:29:18,066 - investment_bot - INFO - Reasoning: The sentiment data shows mixed to negative signals with WB experiencing a 14.2% decline...
2025-11-24 13:29:18,066 - investment_bot - INFO - Skipping purchase of WB based on sentiment analysis (NO recommendation)

=== Sentiment Analysis for FSLR ===
2025-11-24 13:29:23,765 - investment_bot - INFO - Confidence 65.0% is below threshold of 70%
2025-11-24 13:29:23,765 - investment_bot - INFO - Recommendation: NEUTRAL

=== Sentiment Analysis for MRK ===
2025-11-24 13:29:49,733 - investment_bot - INFO - Recommendation: YES
2025-11-24 13:29:49,733 - investment_bot - INFO - Confidence: 75.0%
2025-11-24 13:29:49,733 - investment_bot - INFO - Reasoning: The sentiment is strongly positive with multiple bullish catalysts...
2025-11-24 13:30:05,268 - investment_bot - INFO - Order Response for MRK: unconfirmed
```

This output shows:
1. The system allocating funds between ETFs and individual stocks
2. Sentiment analysis being performed for each potential stock purchase
3. Clear recommendations (YES/NO/NEUTRAL) with confidence levels
4. Reasoning behind each recommendation
5. Automatic skipping of stocks with negative sentiment
6. Successful order placement for approved trades

## ❓ Troubleshooting and Logs

- All actions are logged to `investment_bot.log`
- Detailed trade rationales are provided for each recommendation
- Sentiment analysis results include confidence scores and reasoning
- Check logs for any API errors or connection issues
- Verify your Robinhood and API credentials if authentication fails

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📧 Contact

For questions or support, please open an issue on GitHub.

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

#### Automatic Valuation Updates

The system can automatically update sector and industry valuation metrics using live market data from Finviz. To update the valuations:

```bash
python -c "from util import update_industry_valuations; update_industry_valuations()"
```

Or use the included command in the investment interface:

```bash
python src/main.py
# Then choose 'Update Valuations' from the menu
```

The update process will:
1. Fetch current P/E and P/B ratios for all sectors and industries from Finviz
2. Update the `investments.yaml` file with the latest metrics
3. Preserve any custom thresholds you've set
4. Show a detailed report of all changes made

#### Manual Overrides

To set custom valuation criteria for a specific industry, add or update its entry under the appropriate sector. The first number represents the P/E ratio threshold, and the second number represents the P/B ratio threshold. Use `null` to ignore a particular metric for an industry.

Custom values will be preserved during automatic updates, allowing you to maintain manual control over specific sectors or industries while still benefiting from automatic updates for others.

## Usage

### Running the Strategy

```bash
python src/main.py
```

### Main Components

- **generate_daily_buy_list()**: Fetches and analyzes stock data to identify undervalued opportunities
- **make_buys()**: Handles the execution of buy orders for both individual stocks and ETFs
- **make_sales()**: Manages sell orders based on predefined criteria
- **get_available_cash()**: Calculates available cash, accounting for pending orders
- **update_valuations()**: Updates sector/industry P/E and P/B ratios using current market data

### Supported Commands

- Run the full strategy: `python src/main.py`
- Generate buy list: `generate_daily_buy_list()`
- Execute buys: `make_buys()`
- Execute sales: `make_sales()`
- Check available cash: `get_available_cash()`
- Update valuations: `update_valuations()`

## Strategy Details

The investment strategy focuses on:

1. **Value Investing**: Identifies stocks trading below intrinsic value
2. **Sentiment Analysis**: Validates trades using AI-powered sentiment
3. **Sector Rotation**: Adjusts based on sector/industry benchmarks
4. **Risk Management**: Implements stop-loss and position sizing

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
