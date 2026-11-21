# Tutorial: set up the Instagram Reels MCP

From zero to a published Reel in about 30 minutes. Every step here was done for real; the
"Watch out" notes are problems we actually hit.

You will need:

- An Instagram **professional** account (Creator or Business). Switch in the Instagram app:
  Settings > Account type and tools > Switch to professional account.
- A **Facebook account** (Meta's developer site only accepts Facebook logins).
- A Mac or Linux computer with **Python 3.10+**.
- About 10 minutes on Meta's websites, where you click; the rest is commands.

---

## 1. Install

```bash
git clone <this-repo-url> instagram-reels-mcp
cd instagram-reels-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Install `cloudflared` (it opens a short-lived public link so Instagram can fetch your video):

```bash
brew install cloudflared          # macOS
```

On Linux, see https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/.
No Cloudflare account is needed.

## 2. Put your Instagram account in a Meta business portfolio

1. Open https://business.facebook.com and log in **with Instagram**.
2. Meta Business Suite creates a business portfolio for the account (you can rename it later
   in Settings > Business info).

> **Watch out:** if Business Suite shows a language you don't read, log out, pick **English** in
> the language list at the bottom of the login page, and log back in. The language sticks to the
> login, not to a setting.

## 3. Create the Meta app

1. Go to https://developers.facebook.com, log in with Facebook, **My Apps > Create app**.
2. **App name:** anything, e.g. `My Reels Publisher`.
3. **Use case:** filter by *Content management* and pick
   **Manage messaging & content on Instagram**.
4. **Business:** choose the portfolio from step 2. If it isn't listed, choose
   "I don't want to connect a business portfolio yet" and connect it in the next screen.
5. Click **Create app** (this accepts Meta's Platform Terms).

> **Watch out:** new apps get "API setup with **Unified** login". The older "Instagram login"
> setup is not offered any more, and Unified login **requires** a business portfolio.

## 4. Turn on the two permissions

In the app: **Use cases > Customize (Instagram API) > Permissions and features**, and click
**Add** on:

- `instagram_basic` (read the profile and posts)
- `instagram_content_publish` (publish Reels)

Both should show **Ready for testing**. No App Review is needed to post to your own account.

> **Watch out:** if you skip this, the token screen in step 5 says **"No permissions available"**.

## 5. Create a system user and its token

A *system user* is a non-human account inside your business portfolio. Its token can be set to
**never expire**, so scheduled posting keeps working.

1. https://business.facebook.com > **Settings > Users > System users > Add**.
   Accept the Non-discrimination policy if asked. Name it, role **Admin**.
2. **Assign assets** (the `...` menu or the button on the user):
   - **Instagram accounts:** your account, at least **Content** and **Insights**.
   - **Apps:** your app from step 3 (**Develop app** is enough; **Manage app** also works).
3. **Generate token:**
   - App: your app
   - Expiration: **Never**
   - Permissions: `instagram_basic`, `instagram_content_publish`
4. Click **Copy**. Meta shows the token only once.

## 6. Save the token safely

```bash
examples/save-token.sh
```

On a Mac this opens a pop-up with a hidden field: paste with Cmd+V and click Save. Elsewhere it
asks in the terminal without showing what you paste. The token goes to
`~/.config/instagram-mcp/token` (only you can read it).

> **Watch out:** never paste the token as a terminal command or into a chat. That is how we
> leaked two tokens. If it happens: System users > **Revoke tokens**, generate a new one, save again.

## 7. Find your Instagram account id

The API needs the account's numeric id (it starts with `17841`). System-user tokens don't report
it, so read it from Business Suite:

1. Open https://business.facebook.com with your Instagram account selected.
2. Open the browser's developer console (Chrome: View > Developer > JavaScript Console).
3. Paste and press Enter:

   ```js
   [...new Set(document.documentElement.innerHTML.match(/17841\d{10,12}/g))]
   ```

4. You get your id, e.g. `["17841400000000000"]`.

> **Watch out:** the ids shown in Business settings (like `1031...` for the Instagram asset)
> are **not** the API id. Only the `17841...` one works.

## 8. Test

```bash
IG_USER_ID=17841XXXXXXXXXXXX .venv/bin/python server.py --check
```

Expected: `check ok: @yourname, N posts, 0/100 publishes used in 24 h`. This only reads; it posts
nothing.

## 9. Connect it to Claude Code

```bash
claude mcp add instagram --scope local -e IG_USER_ID=17841XXXXXXXXXXXX -- \
  "$PWD/.venv/bin/python" "$PWD/server.py"
claude mcp get instagram     # Status: Connected
```

Start a new Claude Code session, then ask things like:

- "Show my last 5 Instagram posts."
- "Publish `/path/to/clip.mp4` as a Reel with this caption: ..."

Publishing takes **3-6 minutes**: about 85 s for the temporary link to come online, then
Instagram downloads and processes the video.

## 10. Optional: automatic posting, 3 Reels a day

1. Copy `schedule.example.json` to `schedule.json` and list your Reels in posting order
   (absolute file paths, captions, `"status": "todo"`).
2. Dry run (changes nothing): `IG_USER_ID=... .venv/bin/python post_next.py --dry-run`
3. **macOS:** fill in `examples/com.example.instagram-post.plist` (paths, id), copy it to
   `~/Library/LaunchAgents/`, then
   `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.instagram-post.plist`.
   **Linux:** a cron line per time, e.g.
   `0 12,18,21 * * * cd /path/instagram-reels-mcp && IG_USER_ID=... .venv/bin/python post_next.py >> post.log 2>&1`

Each run posts the **next** unposted Reel (order, not dates), so a missed run (computer asleep)
just shifts the rest. A failed Reel is retried up to 3 times. Before retrying it checks your
posts, so a crash never posts the same Reel twice. Stop the macOS timer with
`launchctl bootout gui/$(id -u)/com.example.instagram-post`.

---

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| `Set IG_USER_ID ...` | The id from step 7 isn't set where the server runs (MCP `-e`, plist `EnvironmentVariables`, cron line). |
| `Meta API 400 ... Invalid OAuth access token` | Token wrong, revoked, or the saved file holds other text. Run `examples/save-token.sh` again. |
| "No permissions available" when generating the token | Step 4 skipped, or the app isn't assigned to the system user (step 5.2). |
| `Tunnel URL never became reachable` | Cloudflare quick tunnels sometimes take 85+ s or fail; just retry. |
| `Instagram could not process the video` | The file breaks Instagram's Reel rules: MP4/MOV, H.264/HEVC, 23-60 fps, 3 s to 15 min, 9:16 recommended. |
| Why not upload the file directly? | Meta's resumable upload (`rupload.facebook.com`) failed 13 of 16 times with `400 ProcessingFailedError` for normal 9:16 clips, whatever the client, caption, frame rate or size. Fetch-by-link worked every time. |
| Posting limit | 100 API posts per 24 hours per account. |

## Responsibility

Only post videos you have the right to post. Clips from other creators can be muted, removed or
earn copyright strikes on your account.
