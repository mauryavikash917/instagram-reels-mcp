"""Publish the next unposted Reel from the schedule file (IG_SCHEDULE, default schedule.json here).
Run it from a timer (launchd/cron) at your posting times; see examples/.

Order, not dates: each run posts the first entry that isn't published, so a missed slot (Mac asleep)
shifts the rest instead of skipping a Reel. `--dry-run` shows what would post and changes nothing.
"""
import fcntl, json, os, socket, subprocess, sys, tempfile, time, urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import server  # noqa: E402

SCHEDULE = Path(os.environ.get("IG_SCHEDULE", Path(__file__).parent / "schedule.json")).expanduser()
LOCK = Path(__file__).parent / ".post.lock"
MAX_TRIES = 3


def _notify(msg):
    subprocess.run(["osascript", "-e", f'display notification {json.dumps(msg, ensure_ascii=False)} '
                    'with title "Instagram Reels MCP"'], capture_output=True)


def _save(items):
    """Write-then-swap, so a crash mid-save can't leave a half-written schedule."""
    tmp = SCHEDULE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False))
    os.replace(tmp, SCHEDULE)


def _already_live(entry):
    """A crash between publish and saving the file must not cause a second post."""
    first = entry["caption"].splitlines()[0]
    return next((m for m in server.list_media(25).get("data", []) if (m.get("caption") or "").startswith(first)), None)


NET_HOSTS = ("graph.facebook.com", "api.trycloudflare.com")
NET_HINTS = ("Tunnel URL never", "cloudflared did not", "nodename nor servname", "timed out")


def _online(wait=300):
    """True once both hosts resolve. A timer firing right after wake often has no network yet."""
    end = time.time() + wait
    while True:
        try:
            for h in NET_HOSTS:
                socket.getaddrinfo(h, 443)
            return True
        except OSError:
            if time.time() > end:
                return False
            time.sleep(15)


def _is_network(e):
    """Our side's connection, not the video: these must not use up a Reel's tries."""
    return isinstance(e, OSError) or any(h in str(e) for h in NET_HINTS)  # URLError is an OSError


def _publish(entry):
    """One retry in the same run for network failures, re-checking Instagram first (no double post)."""
    for attempt in (1, 2):
        try:
            if live := _already_live(entry):
                return live, None
            return server.publish_reel(entry["file"], entry["caption"]), None
        except Exception as e:
            if not _is_network(e) or attempt == 2 or not _online():
                return None, e


def main(dry_run=False):
    with LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises if another run is still posting
        items = json.loads(SCHEDULE.read_text())
        entry = next((o for o in items if o["status"] != "published" and o.get("tries", 0) < MAX_TRIES), None)
        if not entry:
            print("nothing left to post")
            return
        print(f"next: #{entry['n']} {Path(entry['file']).name} | {entry['caption'].splitlines()[0]}")
        if dry_run:
            return
        if not _online():
            print(time.strftime("%Y-%m-%d %H:%M"), "no internet for 5 min; skipped this run, no try used")
            return
        entry["status"] = "posting"
        _save(items)
        r, err = _publish(entry)
        if r:
            entry.update(status="published", permalink=r.get("permalink"), published_at=r.get("timestamp"))
        elif _is_network(err):
            entry.update(status="todo", error=f"network (no try used): {str(err)[:250]}")
        else:
            entry.update(status="failed", tries=entry.get("tries", 0) + 1, error=str(err)[:300])
        _save(items)
        left = sum(o["status"] != "published" for o in items)
        msg = (f"Posted Reel #{entry['n']}. {left} left." if entry["status"] == "published"
               else f"Reel #{entry['n']} not posted (tries {entry.get('tries', 0)}/{MAX_TRIES}): {entry['error'][:80]}")
        print(time.strftime("%Y-%m-%d %H:%M"), msg, entry.get("permalink", ""))
        _notify(msg)


def _selftest():
    """Offline: fake Instagram calls on a temp schedule. Guards against double posts and lost tries."""
    global SCHEDULE, LOCK, _notify
    d = Path(tempfile.mkdtemp())
    SCHEDULE, LOCK, _notify = d / "s.json", d / "lock", lambda msg: None
    posted = []
    server.publish_reel = lambda f, c: posted.append(f) or {"permalink": "new"}
    # crash after publish: entry stuck on "posting" but already on Instagram -> no second post
    _save([{"n": 2, "file": "a.mp4", "caption": "Title A\nbody", "status": "posting", "tries": 1}])
    server.list_media = lambda n: {"data": [{"caption": "Title A\nbody", "permalink": "live-a"}]}
    main()
    e = json.loads(SCHEDULE.read_text())[0]
    assert posted == [] and e["status"] == "published" and e["permalink"] == "live-a", e
    # publish fails -> marked failed, try counted, retried next run
    _save([{"n": 3, "file": "b.mp4", "caption": "Title B", "status": "todo"}])
    server.list_media = lambda n: {"data": []}
    server.publish_reel = lambda f, c: (_ for _ in ()).throw(RuntimeError("boom"))
    main()
    e = json.loads(SCHEDULE.read_text())[0]
    assert e["status"] == "failed" and e["tries"] == 1 and "boom" in e["error"], e
    # network failure twice -> retried once in-run, no try used, stays queued
    global _online
    calls = []
    _online = lambda wait=300: True
    _save([{"n": 4, "file": "c.mp4", "caption": "Title C", "status": "todo"}])
    server.publish_reel = lambda f, c: calls.append(f) or (_ for _ in ()).throw(urllib.error.URLError("nodename nor servname"))
    main()
    e = json.loads(SCHEDULE.read_text())[0]
    assert len(calls) == 2 and e["status"] == "todo" and e.get("tries", 0) == 0, (calls, e)
    # network failure then success -> posted on the in-run retry
    calls.clear()
    server.publish_reel = lambda f, c: (calls.append(f), (_ for _ in ()).throw(RuntimeError("Tunnel URL never became reachable")) if len(calls) == 1 else {"permalink": "ok-c"})[1]
    main()
    e = json.loads(SCHEDULE.read_text())[0]
    assert len(calls) == 2 and e["status"] == "published" and e["permalink"] == "ok-c", (calls, e)
    # no internet at all -> nothing touched
    _online = lambda wait=300: False
    _save([{"n": 5, "file": "d.mp4", "caption": "Title D", "status": "todo"}])
    calls.clear()
    main()
    e = json.loads(SCHEDULE.read_text())[0]
    assert calls == [] and e == {"n": 5, "file": "d.mp4", "caption": "Title D", "status": "todo"}, e
    print("selftest ok")


if __name__ == "__main__":
    _selftest() if "--selftest" in sys.argv else main(dry_run="--dry-run" in sys.argv)
