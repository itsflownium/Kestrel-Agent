#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v uv >/dev/null 2>&1; then
  echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 1
fi
cache_dir="$(mktemp -d "${TMPDIR:-/tmp}/kestrel-install.XXXXXX")"
trap 'rm -rf -- "$cache_dir"' EXIT
cd "$repo_dir"
UV_CACHE_DIR="$cache_dir" uv sync --frozen --extra learning --no-dev
installed_kb="$(du -sk "$repo_dir" | awk '{print $1}')"
if [ "$installed_kb" -ge 2929687 ]; then
  echo 'Installation exceeds 3 GB. Launcher was not installed.' >&2
  exit 1
fi
launcher_dir="${KESTREL_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$launcher_dir"
launcher="$launcher_dir/kestrel"
if [ -e "$launcher" ] && ! grep -q 'Kestrel managed launcher' "$launcher"; then
  echo "Refusing to replace an unrelated command: $launcher" >&2
  exit 1
fi
{
  echo '#!/usr/bin/env bash'
  echo '# Kestrel managed launcher'
  printf 'exec %q "$@"\n' "$repo_dir/.venv/bin/kestrel"
} > "$launcher"
chmod 755 "$launcher"
echo "Installed: $launcher"
echo "Source and environment: $installed_kb KB; temporary cache removed on exit."
echo 'Next: kestrel auth login; kestrel auth jev; kestrel'
echo 'No tests or model calls were run by this installer.'
case ":$PATH:" in
  *":$launcher_dir:"*) ;;
  *) echo "Add $launcher_dir to PATH in your shell configuration." ;;
esac
