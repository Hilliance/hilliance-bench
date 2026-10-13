#!/usr/bin/env python3
"""Measure a running Hilliance server over HTTP, and print what it did.

    docker run -d -p 8080:8080 -v "$PWD/data:/data" hilliance/hilliance
    python3 gen.py --count 200000 --out products.jsonl
    python3 bench.py --objects products.jsonl

Nothing here is privileged: it uses the public HTTP API against the published
image, so the numbers can be checked by anyone who can run a container.

Two numbers are reported per query class, and they answer different questions:

  engine  what the server says it spent searching (`took_us`), which is the
          figure the documentation quotes
  client  wall clock from this process, which includes JSON, sockets and the
          Python in front of them — always larger, and the one your own
          application will feel

Both are medians over --repeat runs after --warmup discarded ones. The
population is synthetic; the point of the file is that you can regenerate it
exactly and disagree with us from the same starting place.
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

QUERIES = [
    ("exact type", {"type": "teacup"}),
    ("type + colour + capacity", {"type": "mug", "colour": "mustard", "capacity_ml": 350}),
    ("values never seen", {"type": "large espresso cup", "colour": "lemon"}),
    ("rich, eight properties", {"type": "mug", "colour": "mustard", "material": "porcelain",
                                "brand": "Vitmark", "series": "Hav", "origin": "Portugal",
                                "capacity_ml": 350, "price": 24.0}),
    ("numbers only", {"capacity_ml": 350, "price": 24.0}),
    ("weak evidence", {"in_stock": True}),
    ("cross-unit, cross-spelling", {"type": "mug", "color": "mustard", "capacity_l": 0.35}),
]
FILTERED = ("filtered: in stock, 10–25",
            {"type": "mug", "colour": "mustard", "capacity_ml": 350},
            [{"property": "in_stock", "any": ["true"]},
             {"property": "price", "min": 10, "max": 25}])


class Client:
    def __init__(self, base, key=None, timeout=600):
        self.base, self.key, self.timeout = base.rstrip("/"), key, timeout

    def _req(self, method, path, body=None, ctype="application/json", raw=None):
        url = self.base + path
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            r.add_header("Content-Type", ctype)
            r.add_header("Content-Length", str(len(data)))
        if self.key:
            r.add_header("Authorization", "Bearer " + self.key)
        try:
            with urllib.request.urlopen(r, timeout=self.timeout) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            # the server's own words are far more useful than a stack trace
            detail = (e.read() or b"").decode("utf-8", "replace").strip()
            sys.exit("%s %s → HTTP %d\n%s" % (method, path, e.code, detail[:800]))
        except OSError as e:
            # a broken pipe usually means the server answered and hung up mid-upload
            sys.exit("%s %s → %s\nThe server closed the connection. Two usual causes:\n"
                     "  1. /data is a bind mount the server cannot write to (it runs as uid 10001).\n"
                     "     Use a named volume: -v hilliance-data:/data\n"
                     "  2. something else; the server's log will say:\n"
                     "     docker logs <container> | tail -30" % (method, path, e))

    def get(self, path):
        return self._req("GET", path)

    def post(self, path, body):
        return self._req("POST", path, body)

    def upload(self, path, filename):
        with open(filename, "rb") as f:
            return self._req("POST", path, raw=f.read(), ctype="application/x-ndjson")


def ms(v):
    return "%.1f ms" % (v / 1000.0) if v >= 1000 else "%d µs" % round(v)


def search(c, space, obj, limit, filters=None, repeat=31, warmup=5):
    body = {"object": obj, "limit": limit}
    if filters:
        body["filters"] = filters
    engine, client, info = [], [], {}
    for i in range(repeat + warmup):
        t0 = time.perf_counter()
        d = c.post("/spaces/%s/search" % space, body)
        dt = (time.perf_counter() - t0) * 1e6
        if i >= warmup:
            engine.append(d["took_us"])
            client.append(dt)
        info = d
    return (statistics.median(engine), statistics.median(client),
            info.get("blocks_scanned"), info.get("blocks_total"), len(info.get("matches", [])))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--key", default=os.environ.get("HILLIANCE_KEY"),
                    help="bearer secret, if the server wants one")
    ap.add_argument("--objects", default="products.jsonl", help="JSON Lines to learn")
    ap.add_argument("--space", default="bench")
    ap.add_argument("--limit", type=int, default=10, help="matches per query")
    ap.add_argument("--repeat", type=int, default=31)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--skip-learn", action="store_true", help="the Space is already there")
    ap.add_argument("--json", help="also write the results here")
    a = ap.parse_args()

    c = Client(a.url, a.key)
    try:
        health = c.get("/health")
    except urllib.error.URLError as e:
        sys.exit("no server at %s (%s). Start one:\n"
                 "  docker run -d -p 8080:8080 -v \"$PWD/data:/data\" hilliance/hilliance" % (a.url, e))

    if not a.skip_learn:
        if not os.path.exists(a.objects):
            sys.exit("%s not found. Generate it:\n  python3 gen.py --count 200000 --out %s"
                     % (a.objects, a.objects))
        size = os.path.getsize(a.objects)
        print("learning %s (%.1f MB) …" % (a.objects, size / 1e6), flush=True)
        t0 = time.perf_counter()
        learned = c.upload("/spaces?name=%s&id_field=sku" % a.space, a.objects)
        learn_s = time.perf_counter() - t0
        space_id = learned["id"]
        objects = learned.get("object_count") or learned.get("objects")
        print("  %s, %s objects in %.1f s" % (space_id, objects, learn_s))
    else:
        learn_s, space_id = None, a.space
        objects = c.get("/spaces/%s" % a.space)["manifest"]["object_count"]

    print("\n%-28s %10s %10s %12s" % ("query", "engine", "client", "blocks"))
    print("-" * 64)
    results = []
    for name, obj in QUERIES:
        e, cl, bs, bt, n = search(c, a.space, obj, a.limit, None, a.repeat, a.warmup)
        print("%-28s %10s %10s %12s" % (name, ms(e), ms(cl), "%s / %s" % (bs, bt)))
        results.append({"query": name, "engine_us": e, "client_us": cl,
                        "blocks_scanned": bs, "blocks_total": bt, "matches": n})
    name, obj, filters = FILTERED
    e, cl, bs, bt, n = search(c, a.space, obj, a.limit, filters, a.repeat, a.warmup)
    print("%-28s %10s %10s %12s" % (name, ms(e), ms(cl), "%s / %s" % (bs, bt)))
    results.append({"query": name, "engine_us": e, "client_us": cl,
                    "blocks_scanned": bs, "blocks_total": bt, "matches": n, "filtered": True})

    print("\n%s objects · limit %d · median of %d runs after %d warm-up · %s"
          % (objects, a.limit, a.repeat, a.warmup, health.get("simd", "simd ?")))
    print("Results are exact: add \"exhaustive\": true to any query to compare against a full scan.")

    if a.json:
        d = os.path.dirname(a.json)
        if d:
            os.makedirs(d, exist_ok=True)
        out = {"space": space_id, "objects": objects, "limit": a.limit,
               "repeat": a.repeat, "warmup": a.warmup, "learn_seconds": learn_s,
               "health": health, "results": results,
               "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
        print("wrote %s" % a.json)


if __name__ == "__main__":
    main()
