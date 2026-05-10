# LEOLRS0-3
LEOLRS0-3 's daily report
LEOLRS0-3

This is a daily trend-following risk exposure system for a New Zealand-based investor.

It separates:

Signal market: usually SPY / S&P 500 data.
Execution market: US market, ASX, or another venue.
Holding asset: for example VOO, IVV.AX, UPRO, SPXL, or cash.
The system is designed to avoid destructive drawdowns first, then increase risk gradually in strong trends.

Install

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
Daily Signal

python -m trend_system daily --config config/settings.toml
Graphical Interface

streamlit run app.py
Then open the local URL shown by Streamlit.

Streamlit Cloud

Deploy app.py on Streamlit Community Cloud. The repository includes requirements.txt so Streamlit Cloud can install the same runtime dependencies.

Twice-Daily Message Push

The GitHub Actions workflow at .github/workflows/daily-signal.yml runs the daily signal twice per day and sends the report to Telegram.

Add these repository secrets in GitHub:

TELEGRAM_BOT_TOKEN: the token from BotFather.
TELEGRAM_CHAT_ID: your personal chat ID, or the target group/channel ID.
You can test the setup from GitHub by opening Actions -> Daily Signal -> Run workflow. The schedule uses UTC, so adjust the cron line if you want different local New Zealand delivery times.

Backtest

python -m trend_system backtest --config config/settings.toml --start 2010-01-01 --end 2026-05-09
Configuration

All floating values live in config/settings.toml:

Time zones
Signal tickers
Execution assets
Moving average windows
VIX thresholds and multipliers
Position limits
Rebalance rules
Backtest assumptions
Exposure is measured as equivalent S&P 500 exposure. For example, 300% means roughly 100% capital in a 3x ETF such as SPXL.
