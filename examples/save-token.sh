#!/usr/bin/env bash
# Save the Meta system-user token without it ever showing on screen or in shell history.
# macOS: a hidden pop-up field. Elsewhere: a hidden terminal prompt.
set -euo pipefail
dir="${IG_TOKEN_DIR:-$HOME/.config/instagram-mcp}"
mkdir -p "$dir" && chmod 700 "$dir"
if command -v osascript >/dev/null; then
  T=$(osascript -e 'text returned of (display dialog "Paste your Meta system-user token (Cmd+V), then click Save." default answer "" with hidden answer with title "Instagram MCP" buttons {"Cancel", "Save"} default button "Save")')
else
  read -rs -p "Paste your Meta system-user token, then press Enter: " T; echo
fi
[ -n "$T" ] || { echo "Nothing pasted, not saved."; exit 1; }
umask 077 && printf '%s\n' "$T" > "$dir/token" && unset T
echo "Saved to $dir/token ($(wc -c < "$dir/token" | tr -d ' ') bytes). Never paste the token anywhere else."
