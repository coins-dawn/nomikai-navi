#!/usr/bin/env python3
"""終電ファースト飲み会ナビ — ローカル用の小さな API サーバ（標準ライブラリだけで動く）。

    python3 server.py  →  http://127.0.0.1:8000/
"""
import json, sys, urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from network import Network, fmt, dist_m   # noqa: E402

DEFAULT_DEPART = 19 * 60

print("データを読み込み中…")
NET = Network()
NODES = json.loads((ROOT / "data" / "index.json").read_text())
BUSSTOPS = json.loads((ROOT / "data" / "busstops.json").read_text())
BARS = json.loads((ROOT / "data" / "bars_points.json").read_text())
BAR_GRID = {}
for _b in BARS:
    BAR_GRID.setdefault((round(_b[0], 2), round(_b[1], 2)), []).append(_b)
NAME2ID = {}
for n in NODES:
    NAME2ID.setdefault(n["name"], n["id"])
print(f"駅ノード {len(NODES)} / 便 {len(NET.trips)} 準備完了")

_cache = {}


def limits_for(station, deadline):
    key = (station, deadline)
    if key not in _cache:
        _cache[key] = NET.latest_departure(station, deadline=deadline)
    return _cache[key]


def arrivals_for(station, t0):
    key = ("a", station, t0)
    if key not in _cache:
        _cache[key] = NET.earliest_arrival(station, t0)
    return _cache[key]


def bars_near(lat, lon, radius=500):
    out = []
    for dy in (-0.01, 0, 0.01):
        for dx in (-0.01, 0, 0.01):
            for b in BAR_GRID.get((round(lat + dy, 2), round(lon + dx, 2)), []):
                if dist_m((lat, lon), (b[0], b[1])) <= radius:
                    out.append({"lat": b[0], "lon": b[1], "name": b[2], "kind": b[3]})
    return out


def detail(payload):
    """選ばれた駅について、飲み屋の位置と各人の帰りの経路を返す。"""
    node = NAME2ID[payload["station"]]
    depart = payload.get("depart", DEFAULT_DEPART)
    people, routes = payload["people"], []
    for p in people:
        home = NAME2ID.get(p["station"])
        lim = limits_for(home, None)[node]
        j = NET.journey(node, lim, home) if lim > -10**6 else None
        legs = j["legs"] if j else []
        routes.append({
            "name": p.get("name") or p["station"],
            "home": p["station"], "bus": None,
            "limit": lim, "limit_s": fmt(lim),
            "home_lat": NET.node_pos[home][0], "home_lon": NET.node_pos[home][1],
            "legs": legs,
        })
    tight = min(range(len(routes)), key=lambda i: routes[i]["limit"])
    n = [x for x in NODES if x["id"] == node][0]
    return {"station": n["name"], "lat": n["lat"], "lon": n["lon"],
            "bars": bars_near(n["lat"], n["lon"]), "routes": routes, "tight": tight}


def search(payload):
    depart = payload.get("depart", DEFAULT_DEPART)
    people = payload["people"]
    min_bars = payload.get("min_bars", 30)
    max_travel = payload.get("max_travel", 90)

    ids, lims, arrs, labels = [], [], [], []
    for p in people:
        nid = NAME2ID.get(p["station"])
        if nid is None:
            raise ValueError(f"知らない駅です: {p['station']}")
        ids.append(nid)
        arrs.append(arrivals_for(nid, depart))
        lims.append(limits_for(nid, None))
        labels.append(f"{p['station']}駅")

    rows = []
    for n in NODES:
        i = n["id"]
        if any(a[i] >= 10**6 for a in arrs) or any(l[i] <= -10**6 for l in lims):
            continue
        times = [a[i] - depart for a in arrs]
        limits = [l[i] for l in lims]
        stay = [l - (depart + t) for l, t in zip(limits, times)]
        if min(stay) <= 0:
            continue
        rows.append({
            "id": n["id"],
            "name": n["name"], "bars": n["bars"], "median_m": n["median_m"], "lines": n["lines"],
            "lat": n["lat"], "lon": n["lon"],
            "times": times, "limits": limits, "stay": stay,
            "min_stay": min(stay), "min_limit": min(limits),
            "sum": sum(times), "max": max(times),
            "tight": limits.index(min(limits)),
        })

    ok = [r for r in rows if r["bars"] >= min_bars and r["max"] <= max_travel]
    ok.sort(key=lambda r: -r["min_stay"])
    ok = ok[:5]
    # 比較用: 所要時間だけで選んだ駅（飲み屋も終電も見ない）
    by_time = min(rows, key=lambda r: r["sum"]) if rows else None
    return {
        "people": [{"name": p.get("name") or p["station"], "where": labels[i]}
                   for i, p in enumerate(people)],
        "depart": depart,
        "candidates": ok,
        "all": rows,
        "by_time": by_time,
        "n_all": len(rows), "n_ok": len(ok),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "frontend"), **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/engine.js":
            self.path = "/engine-server.js"      # 開発中はサーバに計算させる版を使う
            return super().do_GET()
        if u.path == "/api/meta":
            return self._json({
                "stations": [{"n": x["name"], "b": x["bars"], "l": x["lines"]} for x in NODES],
                "bus_stations": sorted(BUSSTOPS.keys()),
            })
        if u.path == "/api/geo":
            rails = []
            for rid in NET.railways:
                order, seen = [], set()
                for sid in NET.railway_order.get(rid, []):
                    nid = NET.sta2node.get(sid)
                    if nid is not None and nid not in seen:
                        seen.add(nid)
                        order.append(nid)
                rails.append({"t": NET.railway_title.get(rid, ""),
                              "c": NET.railway_color.get(rid), "o": order})
            geo = [{"id": n["id"], "n": n["name"], "lat": n["lat"], "lon": n["lon"],
                    "b": n["bars"], "m": n["median_m"], "l": n["lines"]} for n in NODES]
            shapes = json.loads((ROOT / "data" / "rail_shapes.json").read_text()) \
                if (ROOT / "data" / "rail_shapes.json").exists() else None
            return self._json({"geo": geo, "rails": rails, "shapes": shapes})
        if u.path == "/api/busstops":
            q = urllib.parse.parse_qs(u.query).get("station", [""])[0]
            return self._json(BUSSTOPS.get(q, []))
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/api/search", "/api/detail"):
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n))
            return self._json(search(body) if path == "/api/search" else detail(body))
        except Exception as e:
            return self._json({"error": str(e)}, 400)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    host = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    print(f"http://127.0.0.1:{port}/")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
