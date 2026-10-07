#!/usr/bin/env python3
"""OpenStreetMap の線路から、隣り合う駅どうしの実際の線形をつくる。

駅と駅を直線で結ぶと地図が嘘になるので、線路のグラフの上で最短経路を引く。
**路線名での対応づけはしない**（OSM と ODPT で名前が揃わず、
「都営新宿線」が「西武新宿線」に当たるような誤爆が起きるため）。
隣り合う駅は物理的に近いので、その間の最短の線路がその路線の線形になる。

    osmium tags-filter kanto-latest.osm.pbf w/railway=rail,subway,light_rail,monorail,narrow_gauge -o rail.osm.pbf
    osmium export rail.osm.pbf -f geojsonseq -o rail.geojsonl
    python3 scripts/build_rail_shapes.py rail.geojsonl

出力: data/rail_shapes.json  {路線の番号: [[ [lat,lon], ... ] ← 駅間ごと ]}
"""
import heapq, json, math, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from network import Network, dist_m   # noqa: E402

CELL = 0.01          # 近傍さがし用の格子
SNAP_M = 800         # 駅からこの距離までの線路に乗り移る
DETOUR = 4.5         # 直線距離のこの倍を超える経路は採らない


def load_ways(path):
    pts, edges = {}, defaultdict(list)

    def key(c):
        return (round(c[1], 6), round(c[0], 6))

    n = 0
    for line in open(path):
        line = line.strip("\x1e\n ")
        if not line:
            continue
        f = json.loads(line)
        if f["properties"].get("service"):      # 車庫・待避線は除く
            continue
        g = f["geometry"]
        if g["type"] != "LineString":
            continue
        n += 1
        prev = None
        for c in g["coordinates"]:
            k = key(c)
            pts[k] = k
            if prev is not None and prev != k:
                d = dist_m(prev, k)
                edges[prev].append((k, d))
                edges[k].append((prev, d))
            prev = k
    print(f"線路 {n} 本 / 節点 {len(pts)}")
    return edges


def main(path):
    edges = load_ways(path)
    grid = defaultdict(list)
    for p in edges:
        grid[(int(p[0] / CELL), int(p[1] / CELL))].append(p)

    # 線路の連結成分を先に求める。地下鉄と JR はつながっていないので、
    # 駅のいちばん近くの線路に吸着すると「別路線に乗り移って経路なし」になる。
    comp, cid = {}, 0
    for start in edges:
        if start in comp:
            continue
        stack, cid = [start], cid + 1
        comp[start] = cid
        while stack:
            u = stack.pop()
            for v, _ in edges[u]:
                if v not in comp:
                    comp[v] = cid
                    stack.append(v)
    print(f"線路の連結成分 {cid}")

    def near(lat, lon, r=SNAP_M, keep=14):
        """半径 r 以内の線路を連結成分ごとに 1 つずつ返す（近い順）。"""
        best = {}
        ci, cj = int(lat / CELL), int(lon / CELL)
        for i in (ci - 1, ci, ci + 1):
            for j in (cj - 1, cj, cj + 1):
                for p in grid.get((i, j), ()):
                    d = dist_m((lat, lon), p)
                    if d < r:
                        c = comp[p]
                        if c not in best or d < best[c][0]:
                            best[c] = (d, p)
        return sorted(best.items(), key=lambda kv: kv[1][0])[:keep]

    def route(a, b, limit):
        """a から b までの線路上の最短経路。limit を超えたら諦める。"""
        dist = {a: 0.0}
        prev = {}
        pq = [(0.0, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, 1e18):
                continue
            if u == b:
                path = [u]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return path[::-1]
            if d > limit:
                return None
            for v, w in edges[u]:
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        return None

    net = Network(since=19 * 60)
    out, hit, miss = {}, 0, 0
    for ri, rid in enumerate(net.railways):
        order, seen = [], set()
        for sid in net.railway_order.get(rid, []):
            nid = net.sta2node.get(sid)
            if nid is not None and nid not in seen:
                seen.add(nid)
                order.append(nid)
        segs = []
        for a, b in zip(order, order[1:]):
            pa, pb = net.node_pos[a], net.node_pos[b]
            straight = dist_m(pa, pb)
            ca, cb = dict(near(*pa)), dict(near(*pb))
            path = None
            for c in sorted(set(ca) & set(cb), key=lambda c: ca[c][0] + cb[c][0]):
                path = route(ca[c][1], cb[c][1], straight * DETOUR + 500)
                if path and len(path) > 1:
                    break
            if path and len(path) > 1:
                segs.append([[round(p[0], 5), round(p[1], 5)] for p in path])
                hit += 1
            else:
                segs.append([[round(pa[0], 5), round(pa[1], 5)], [round(pb[0], 5), round(pb[1], 5)]])
                miss += 1
        out[ri] = segs
        print(f"[{ri+1}/{len(net.railways)}] {net.railway_title.get(rid)}: 駅間 {len(segs)}", flush=True)
    p = ROOT / "data" / "rail_shapes.json"
    p.write_text(json.dumps(out, separators=(",", ":")))
    print(f"線路なりに引けた駅間 {hit} / 直線のまま {miss} → {p} ({p.stat().st_size/1e6:.1f}MB)")


if __name__ == "__main__":
    main(sys.argv[1])
