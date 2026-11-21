# CLAUDE.md

Guidance for Claude Code when working in this repo or setting it up for someone.

## What this is

An MCP server (`server.py`, FastMCP, stdlib only besides `mcp`) that publishes Instagram Reels
through the Instagram Graph API (`graph.facebook.com/v27.0`), plus `post_next.py`, which a timer
runs to post the next Reel from a schedule file. Full human walkthrough: `TUTORIAL.md`.

## Setting it up for a user

Follow `TUTORIAL.md` in order. Do the commands yourself; the user does the clicks on Meta's sites.

1. Install: venv + `pip install -r requirements.txt`, `brew install cloudflared`.
2. Meta side (user clicks; you can guide or drive a browser): business portfolio, app with the
   "Manage messaging & content on Instagram" use case, permissions `instagram_basic` +
   `instagram_content_publish` added in the use case, system user with the Instagram account and
   the app assigned, token with expiry **Never**.
3. Token: run `examples/save-token.sh` (hidden pop-up on macOS). Then validate without printing
   it, e.g. length, `startswith("EAA")`, and `GET /debug_token`.
4. Account id: the `17841...` id from Business Suite page data (TUTORIAL step 7). Business
   settings asset ids (`1031...`) are not API ids.
5. `IG_USER_ID=... .venv/bin/python server.py --check`, then `claude mcp add instagram --scope local -e IG_USER_ID=... -- <venv python> <server.py>`.
   MCP tools load in the **next** session; in the current one, import `server` and call functions.

## Rules

- **Never** ask the user to paste the token into chat or onto a command line, and never print
  it. If it appears in a transcript or terminal, tell the user plainly, have them revoke it
  (System users > Revoke tokens) and save a new one with `save-token.sh`.
- Publishing is public: publish only what the user asked for, with the caption they approved.
- If `publish_reel` fails after the video was processed, call `list_media` before retrying, or
  the Reel may post twice. `post_next.py` already does this.
- Accepting Meta's terms or policies, creating the app, and generating tokens are the user's
  clicks, not yours.
- Keep `token`, `schedule.json`, `post.log` out of git (`.gitignore` covers them).

## Known facts (verified)

- Direct resumable upload (`rupload.facebook.com/ig-api-upload`) fails most of the time with
  `400 ProcessingFailedError`, independent of client, caption, fps and size. Don't switch back to
  it; `publish_reel` serves the file through a cloudflared quick tunnel and posts by `video_url`.
- A fresh quick tunnel takes about 85 s to resolve; `_wait_public` waits up to 180 s.
- Instagram processing of a 40 s 1080x1920 Reel: about 1-3 min to `FINISHED`.
- System-user tokens: `expires_at: 0`, and `/debug_token` granular scopes have no target ids,
  hence `IG_USER_ID`.
- Quota: `GET /{ig-id}/content_publishing_limit`, 100 posts per 24 h.

## Commands

```bash
.venv/bin/python server.py --check          # live, read-only
.venv/bin/python post_next.py --selftest    # offline: double-post guard, failure counting
.venv/bin/python post_next.py --dry-run     # shows the next Reel, changes nothing
```
