"""Instagram MCP: publish Reels and read the account through the Instagram Graph API.

Auth: a Meta system-user token (Business Suite > System users > Generate token, scopes
instagram_basic + instagram_content_publish) saved as one line in ~/.config/instagram-mcp/token
(chmod 600, or set IG_TOKEN_FILE), never in this file. IG_USER_ID = the Instagram account id.

Upload: Meta's direct (resumable) upload failed 13 of 16 tries with 400 ProcessingFailedError for
these clips, so publish_reel serves the one local file through a temporary Cloudflare quick tunnel
and lets Instagram fetch it by video_url (tested: FINISHED in ~3 min). The tunnel closes after.
"""
import functools, http.server, json, os, re, shutil, subprocess, sys, tempfile, threading, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

API = "https://graph.facebook.com/v27.0"
TOKEN_FILE = Path(os.environ.get("IG_TOKEN_FILE", Path.home() / ".config/instagram-mcp/token")).expanduser()
CLOUDFLARED = shutil.which("cloudflared") or "/opt/homebrew/bin/cloudflared"
TUNNEL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")  # api. shows up in error lines
# Instagram account id (17841...). System-user tokens don't list it in /debug_token and the business
# endpoints need business_management, so it is set by hand; TUTORIAL.md shows how to find it.
IG_USER = os.environ.get("IG_USER_ID", "")

mcp = FastMCP("instagram")


def _token():
    if not TOKEN_FILE.exists():
        raise RuntimeError(f"No token. Save the system-user token as one line in {TOKEN_FILE}")
    return TOKEN_FILE.read_text().strip()


def _call(method, path, **params):
    if not IG_USER.isdigit():
        raise RuntimeError("Set IG_USER_ID to your Instagram account id (17841...). See TUTORIAL.md step 6.")
    params["access_token"] = _token()
    data = urllib.parse.urlencode(params).encode()
    req = (urllib.request.Request(f"{API}/{path}?{data.decode()}") if method == "GET"
           else urllib.request.Request(f"{API}/{path}", data=data, method="POST"))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta API {e.code}: {e.read().decode()[:500]}") from None


class _OneFile(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # stdio is the MCP channel; keep it clean
        pass

    def list_directory(self, path):  # never reveal the random file name
        self.send_error(404)


def _serve_file(path):
    """Serve only this file on 127.0.0.1 under a random name. Returns (server, url_path)."""
    tmp = tempfile.mkdtemp(prefix="igmcp-")
    name = os.urandom(8).hex() + path.suffix.lower()
    os.symlink(path, os.path.join(tmp, name))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_OneFile, directory=tmp))
    srv.tmp = tmp
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, name


def _stop(srv):
    srv.shutdown()
    shutil.rmtree(srv.tmp, ignore_errors=True)


def _open_tunnel(port):
    proc = subprocess.Popen([CLOUDFLARED, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    timer = threading.Timer(60, proc.kill)  # killing closes stderr, which ends the loop below
    timer.start()
    for line in proc.stderr:  # cloudflared prints the public URL on stderr
        if m := TUNNEL_RE.search(line):
            timer.cancel()
            threading.Thread(target=lambda: [None for _ in proc.stderr], daemon=True).start()  # keep draining
            return proc, m.group(0)
    timer.cancel()
    proc.kill()
    raise RuntimeError("cloudflared did not give a tunnel URL within 60 s")


def _wait_public(url, timeout=180):  # measured: a fresh quick tunnel takes 83-85 s to resolve
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=10) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError(f"Tunnel URL never became reachable: {url}")


@mcp.tool()
def account_info() -> dict:
    """Instagram account the token can post to: id, username, post count, followers."""
    return _call("GET", IG_USER, fields="id,username,name,media_count,followers_count")


@mcp.tool()
def list_media(limit: int = 10) -> dict:
    """Most recent posts with caption, type, link and time."""
    return _call("GET", f"{IG_USER}/media", fields="id,caption,media_type,permalink,timestamp",
                 limit=max(1, min(limit, 50)))


@mcp.tool()
def publish_reel(file_path: str, caption: str, share_to_feed: bool = True) -> dict:
    """Publish a local MP4/MOV as a Reel right now, with this caption. Returns the post id and link.
    Takes 3-6 minutes: a temporary link opens (~85 s), Instagram fetches and processes the video,
    then it goes live. If this fails after processing, check list_media before retrying."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in (".mp4", ".mov"):
        raise ValueError(f"Not an MP4/MOV file: {path}")
    if len(caption) > 2200:
        raise ValueError("Caption is over Instagram's 2,200 character limit")
    srv, name = _serve_file(path)
    tunnel = None
    try:
        tunnel, base = _open_tunnel(srv.server_address[1])
        video_url = f"{base}/{name}"
        _wait_public(video_url)
        container = _call("POST", f"{IG_USER}/media", media_type="REELS", video_url=video_url,
                          caption=caption, share_to_feed=str(share_to_feed).lower())["id"]
        status = {}
        for _ in range(60):  # up to ~10 min of processing
            status = _call("GET", container, fields="status_code,status")
            if status.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"):
                break
            time.sleep(10)
        if status.get("status_code") != "FINISHED":
            raise RuntimeError(f"Instagram could not process the video: {status}")
        media_id = _call("POST", f"{IG_USER}/media_publish", creation_id=container)["id"]
        return _call("GET", media_id, fields="id,permalink,timestamp")
    finally:
        if tunnel:
            tunnel.kill()
        _stop(srv)


def _check():
    """Live, read-only: token works, account is right, publish quota left; plus the local file server."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"fake video bytes")
    srv, name = _serve_file(Path(f.name))
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/{name}") as r:
            assert r.read() == b"fake video bytes"
        for bad in ("/", f"/../{Path(f.name).name}"):  # no listing, nothing outside the folder
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}{bad}")
                raise AssertionError(f"served {bad}")
            except urllib.error.HTTPError as e:
                assert e.code == 404
    finally:
        _stop(srv)
        os.unlink(f.name)
    assert not TUNNEL_RE.search('failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel"')
    acc = account_info()
    assert acc.get("username"), acc
    quota = _call("GET", f"{IG_USER}/content_publishing_limit", fields="quota_usage,config")["data"][0]
    print(f"check ok: @{acc['username']}, {acc.get('media_count', 0)} posts, "
          f"{quota['quota_usage']}/{quota['config']['quota_total']} publishes used in 24 h")


if __name__ == "__main__":
    _check() if sys.argv[1:] == ["--check"] else mcp.run()
