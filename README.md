# Instagram Reels MCP

An MCP server that lets Claude (or any MCP client) **publish Reels** from files on your computer
and **read your Instagram account**, through Meta's official Instagram Graph API. Plus an
optional timer script that posts a list of Reels on a schedule (e.g. 3 a day).

- No third-party posting service, no browser automation, no password sharing.
- Uses a Meta **system-user token** that never expires, stored in a private file.
- Your video never needs to be hosted anywhere: a temporary Cloudflare link opens for that one
  file while Instagram fetches it, then closes.

## Tools

| Tool | What it does |
|---|---|
| `account_info` | Username, post count, followers. |
| `list_media(limit)` | Your latest posts with caption, link and time. |
| `publish_reel(file_path, caption, share_to_feed=True)` | Publishes a local MP4/MOV as a Reel now. Takes 3-6 minutes. |

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
brew install cloudflared                  # macOS; see TUTORIAL.md for Linux
examples/save-token.sh                    # saves your Meta token without showing it
IG_USER_ID=17841XXXXXXXXXXXX .venv/bin/python server.py --check
claude mcp add instagram --scope local -e IG_USER_ID=17841XXXXXXXXXXXX -- \
  "$PWD/.venv/bin/python" "$PWD/server.py"
```

Getting the token and the account id takes some clicking on Meta's sites:
**follow [TUTORIAL.md](TUTORIAL.md)** step by step. Using Claude Code? Open this folder and ask
it to set things up; [CLAUDE.md](CLAUDE.md) tells it how.

## Files

| File | Purpose |
|---|---|
| `server.py` | The MCP server. `--check` runs a read-only live test. |
| `post_next.py` | Posts the next Reel from `schedule.json`. `--dry-run`, `--selftest`. |
| `schedule.example.json` | Format of the posting list. |
| `examples/save-token.sh` | Saves the token through a hidden field. |
| `examples/com.example.instagram-post.plist` | macOS timer for 12:00, 18:00, 21:00. |

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `IG_USER_ID` | (required) | Instagram account id, starts with `17841`. |
| `IG_TOKEN_FILE` | `~/.config/instagram-mcp/token` | File holding the system-user token. |
| `IG_SCHEDULE` | `schedule.json` next to the scripts | Posting list for `post_next.py`. |

## Requirements

Python 3.10+, `cloudflared`, an Instagram professional account in a Meta business portfolio, and
a Meta app with `instagram_basic` + `instagram_content_publish`. API limit: 100 posts per 24 h.

Only post videos you have the rights to.

## License

MIT, see [LICENSE](LICENSE).
