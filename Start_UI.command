#!/bin/zsh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "Starting LEOLRS0-3..."
echo "Project: $PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Please install Python 3.11 or newer first."
  echo "Press any key to close this window."
  read -k 1
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

source ".venv/bin/activate"

if ! python -c "import streamlit" >/dev/null 2>&1; then
  echo "Installing required packages..."
  python -m pip install --upgrade pip
  python -m pip install -e .
fi

PORT="$(
python - <<'PY'
import socket

for port in range(8501, 8511):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit("No free port found from 8501 to 8510.")
PY
)"

URL="http://localhost:$PORT"
echo "Opening UI: $URL"

(
  sleep 3
  open "$URL"
) &

echo "The UI is starting. Leave this Terminal window open while using the app."
echo "Press Control+C in this window to stop the program."

exec python -m streamlit run app.py \
  --server.address localhost \
  --server.port "$PORT" \
  --server.headless true
