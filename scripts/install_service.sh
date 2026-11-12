#!/bin/bash
# Runs a project's studio page as a systemd user service, so it's always there at http://localhost:<port>.
#   scripts/install_service.sh --project ~/games/MyGame [--name mygame-voice] [--port 8765]
#                              [--python ~/venvs/verbaline/bin/python] [--env ~/.config/verbaline/env]
# Keeps an old unit of the same name beside the new one (<name>.service.bak-<time>), restarts the service and checks
# the page answers. The env file holds secrets such as XAI_API_KEY=..., one per line (it's optional).
# docs/details/install-details.md ("A service").
set -euo pipefail
STUDIO="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="" NAME="verbaline" PORT="" PY="$(command -v python3)" ENVF="%h/.config/verbaline/env"
while [ $# -gt 0 ]; do
	case "$1" in
		--project) PROJECT="$(cd "$2" && pwd)"; shift 2;;
		--name) NAME="$2"; shift 2;;
		--port) PORT="$2"; shift 2;;
		--python) PY="$2"; shift 2;;
		--env) ENVF="$2"; shift 2;;
		*) echo "unknown option $1"; exit 2;;
	esac
done
[ -n "$PROJECT" ] || { echo "--project <folder with verbaline.toml> is required"; exit 2; }
[ -f "$PROJECT/verbaline.toml" ] || { echo "No verbaline.toml in $PROJECT"; exit 1; }
[ -x "$PY" ] || { echo "No Python at $PY"; exit 1; }
"$PY" -c "import tomlkit, numpy, soundfile" 2>/dev/null || { echo "$PY lacks the studio's packages: $PY -m pip install -r $STUDIO/requirements.txt"; exit 1; }
if [ -z "$PORT" ]; then
	PORT="$("$PY" - "$PROJECT" "$STUDIO" <<'PY'
import sys; sys.path.insert(0, sys.argv[2])
from verbaline.project import Project
print(Project(sys.argv[1]).cfg['project'].get('port', 8765))
PY
)"
fi
UNIT="$HOME/.config/systemd/user/$NAME.service"
mkdir -p "$(dirname "$UNIT")"
if [ -f "$UNIT" ]; then cp -p "$UNIT" "$UNIT.bak-$(date +%Y%m%d-%H%M%S)"; fi
cat > "$UNIT" <<UNIT_EOF
[Unit]
Description=Verbaline For Games: $(basename "$PROJECT") (http://localhost:$PORT)

[Service]
WorkingDirectory=$PROJECT
ExecStart=$PY "$STUDIO/verbaline/cli.py" --project "$PROJECT" serve --port $PORT
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$ENVF
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNIT_EOF
systemctl --user daemon-reload
systemctl --user enable "$NAME" >/dev/null 2>&1 || true
systemctl --user restart "$NAME"
if curl -sf --retry 30 --retry-delay 1 --retry-connrefused -o /dev/null "http://localhost:$PORT/"; then
	echo "Verbaline For Games is up for $PROJECT: http://localhost:$PORT  (service $NAME)"
else
	echo "The studio didn't answer: journalctl --user -u $NAME"
	exit 1
fi
