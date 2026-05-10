# LEOLRS0-3 Deployment Log

## 2026-05-10

- Decided on Streamlit Community Cloud for the UI and GitHub Actions for twice-daily signal push.
- Added Telegram notification support via `trend_system.notify`, using repository secrets:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
- Added `requirements.txt` for Streamlit Cloud dependency installation.
- Fixed Streamlit Cloud startup path issues by resolving config, profile, and changelog paths from the package root instead of the process working directory.
- Made the GitHub repository public so Streamlit Cloud could access it without private-repo authorization.
- Added GitHub remote `origin` pointing to `https://github.com/bcdddm/LEOLRS0-3.git`.
- Used a GitHub Personal Access Token with `Contents: Read and write` plus `Workflows: Read and write` to push workflow changes.
- Flattened the GitHub repository layout so the project now lives at the repository root instead of inside an extra `LEOLRS0-3/` directory.
- Removed generated artifacts from version control:
  - `__pycache__/`
  - `outputs/`
  - `*.egg-info/`
- Updated Streamlit Cloud deployment path from `LEOLRS0-3/app.py` to `app.py`.
- Added `.github/workflows/daily-signal.yml`.
- Added report comparison logic so the daily message begins with:
  - `Action today: ACTION NEEDED`
  - `Action today: NO ACTION NEEDED`
  - `Action today: REVIEW MANUALLY`
- The action summary compares the latest signal against the previous trading signal and highlights execution allocation changes.
- Updated GitHub Actions runtime usage:
  - `actions/checkout@v5`
  - `actions/setup-python@v6`
  - `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`
- Updated schedule behavior to send one hour before each relevant market close:
  - NZ market: `15:45 Pacific/Auckland`
  - US market: `15:00 America/New_York`
- The workflow uses UTC candidate cron entries plus timezone gates, so daylight saving changes are handled automatically.

## Current Operating Notes

- Streamlit Cloud main file path should be `app.py`.
- GitHub Actions should show a workflow named `Daily Signal`.
- Manual test path: `Actions -> Daily Signal -> Run workflow`.
- Automatic push works when the two Telegram secrets are present and GitHub Actions is enabled.
- GitHub scheduled workflows can be delayed by a few minutes under platform load, so the alert is near the target time rather than guaranteed to-the-second.
- The Telegram bot token was once visible in a browser URL during setup; rotate it with BotFather if not already done.
