#!/usr/bin/env python3
"""アプリが使う索引をつくる。

- data/index.json     : 駅ノード（名前・座標・飲み屋数・密集度・乗換路線数）
- data/busstops.json  : 「駅名」→ その駅から最終バスで行ける停留所（最終発と所要）
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from network import Network
from bus import GTFS_ROOT, _read

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ["kanto_bus", "keio_bus", "toei_bus"]


def build_busstops(node_names):
    out = defaultdict(dict)
    for feed in FEEDS:
        base = GTFS_ROOT / feed / "gtfs"
        if not base.exists():
            continue
        stops = {r["stop_id"]: r["stop_name"] for r in _read(base, "stops.txt")}
        coords = {r["stop_name"]: (round(float(r["stop_lat"]), 5), round(float(r["stop_lon"]), 5))
                  for r in _read(base, "stops.txt") if r.get("stop_lat")}
        weekday = {r["service_id"] for r in _read(base, "calendar.txt") if r["monday"] == "1"}
        trips = {r["trip_id"]: r["service_id"] for r in _read(base, "trips.txt")}
        seq = defaultdict(list)
        for r in _read(base, "stop_times.txt"):
            if trips.get(r["trip_id"]) not in weekday:
                continue
            h, m, _ = r["departure_time"].split(":")
            seq[r["trip_id"]].append((int(r["stop_sequence"]), stops[r["stop_id"]], int(h) * 60 + int(m)))
        for v in seq.values():
            v.sort()
            for i, (_, sname, t0) in enumerate(v):
                # 「○○駅」「○○駅北口」などを鉄道駅とみなす
                m = re.match(r"^(.+?)駅(?:$|[前北南東西口])", sname)
                if not m or m.group(1) not in node_names:
                    continue
                station = m.group(1)
                for k, (_, n, t) in enumerate(v[i + 1:], start=i + 1):
                    if n == sname or n.startswith(station + "駅"):
                        continue
                    cur = out[station].get(n)
                    if cur is None or t0 > cur["last"]:
                        line = [coords[m] for _, m, _ in v[i:k + 1] if m in coords]
                        out[station][n] = {"last": t0, "ride": t - t0, "feed": feed,
                                           "via": sname, "line": line}
                break
    # 18 時以降に最終便がある停留所だけ、駅ごとに最大 200 件
    res = {}
    for station, d in out.items():
        items = [{"stop": k, **v} for k, v in d.items() if 18 * 60 <= v["last"] <= 26 * 60]
        items.sort(key=lambda x: (x["last"], x["stop"]))
        if items:
            res[station] = items[:200]
    return res


def main():
    net = Network()
    bars = {b["node"]: b for b in json.loads((ROOT / "data" / "bars_by_station.json").read_text())}
    stations = json.loads((ROOT / "data" / "raw" / "stations.json").read_text())
    lines = defaultdict(set)
    for s in stations:
        nid = net.sta2node.get(s["owl:sameAs"])
        if nid is None:
            continue
        lines[nid].add(s["odpt:railway"])
        for r in s.get("odpt:connectingRailway", []):
            lines[nid].add(r)

    nodes = []
    for i, name in enumerate(net.node_name):
        b = bars.get(i, {})
        nodes.append({
            "id": i, "name": name,
            "lat": round(net.node_pos[i][0], 5), "lon": round(net.node_pos[i][1], 5),
            "bars": b.get("bars", 0), "median_m": b.get("median_m"),
            "lines": len(lines.get(i, ())),
        })
    (ROOT / "data" / "index.json").write_text(json.dumps(nodes, ensure_ascii=False))
    print(f"駅ノード {len(nodes)}")

    bs = build_busstops(set(net.node_name))
    (ROOT / "data" / "busstops.json").write_text(json.dumps(bs, ensure_ascii=False))
    print(f"バス停を持つ駅 {len(bs)} / 停留所 {sum(len(v) for v in bs.values())}")


if __name__ == "__main__":
    main()
