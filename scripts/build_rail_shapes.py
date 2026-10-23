#!/usr/bin/env python3
"""OpenStreetMap の路線（route リレーション）から、隣り合う駅どうしの実際の線形をつくる。

駅と駅を直線で結ぶと地図が嘘になるので、線路の上で最短経路を引く。
以前は全路線の線路をひとつのグラフにして引いていたが、並行する別の線路・渡り線・車庫線に
乗り移って、行き過ぎて戻る形や大回りの形（地下鉄で直線の 3〜5 倍）ができた。
そこで **その路線の route リレーションに含まれる線路だけ** で引く。

ODPT の路線と OSM のリレーションは **名前では対応づけない**（「都営新宿線」が「西武新宿線」に
当たるような誤爆が起きるため）。駅が線路の近くに並んでいるかで対応づける:
  1. リレーションごとに、ODPT の路線の駅のうち COVER_M 以内に線路がある駅を数える
  2. 多くの駅を覆うリレーションから順に採る（上り・下り、根岸線のような続きの区間も採られる）
  3. 駅間ごとに、両端の駅を覆う採用済みのリレーションの線路の上で最短経路を引く。
     その路線そのもののリレーションの中で最短を採る（直線の DETOUR 倍＋300m まで）。
  4. それでも引けない駅間は、全路線の線路で、ほとんど回り道しない経路があれば採る。なければ直線のまま

    osmium tags-filter kanto-latest.osm.pbf r/route=train,subway,light_rail,monorail,tram -o routes.osm.pbf
    osmium cat routes.osm.pbf -f opl -o routes.opl
    python3 scripts/build_rail_shapes.py routes.opl

出力: data/rail_shapes.json  {路線の番号: [[ [lat,lon], ... ] ← 駅間ごと ]}
"""
import heapq, json, math, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from network import Network, dist_m   # noqa: E402

CELL = 0.005         # 近傍さがし用の格子（約 500m）
COVER_M = 300        # 駅からこの距離に線路があれば、そのリレーションが駅を覆うとみなす
DETOUR = 2.0         # 直線距離のこの倍（＋300m）を超える経路は採らない
TRACK = {"rail", "subway", "light_rail", "monorail", "narrow_gauge", "tram", "funicular"}


def unesc(s):
    """OPL の %xxxx% エスケープを戻す。"""
    return re.sub(r"%([0-9a-f]+)%", lambda m: chr(int(m.group(1), 16)), s)


def tags_of(tok):
    out = {}
    if tok.startswith("T") and len(tok) > 1:
        for kv in tok[1:].split(","):
            k, _, v = kv.partition("=")
            out[unesc(k)] = unesc(v)
    return out


def load_opl(path):
    nodes, ways, rels = {}, {}, []
    for line in open(path, encoding="utf-8"):
        f = line.rstrip("\n").split(" ")
        kind = f[0][0]
        if kind == "n":
            x = y = None
            for t in f[1:]:
                if t.startswith("x"):
                    x = float(t[1:])
                elif t.startswith("y"):
                    y = float(t[1:])
            if x is not None:
                nodes[int(f[0][1:])] = (y, x)
        elif kind == "w":
            tags, refs = {}, []
            for t in f[1:]:
                if t.startswith("T"):
                    tags = tags_of(t)
                elif t.startswith("N"):
                    refs = [int(r[1:]) for r in t[1:].split(",") if r]
            if tags.get("railway") in TRACK:
                ways[int(f[0][1:])] = refs
        elif kind == "r":
            tags, mem = {}, []
            for t in f[1:]:
                if t.startswith("T"):
                    tags = tags_of(t)
                elif t.startswith("M"):
                    for m in t[1:].split(","):
                        if m.startswith("w"):
                            ref, _, role = m[1:].partition("@")
                            if unesc(role) in ("", "forward", "backward", "main"):
                                mem.append(int(ref))
            if mem:
                rels.append({"id": int(f[0][1:]), "name": tags.get("name", ""), "ways": mem})
    print(f"節点 {len(nodes)} / 線路 {len(ways)} / 路線リレーション {len(rels)}")
    return nodes, ways, rels


class Rel:
    """1 本のリレーションの線路だけのグラフ。"""

    def __init__(self, r, nodes, ways):
        self.id, self.name = r["id"], r["name"]
        self.adj = defaultdict(list)
        for w in r["ways"]:
            refs = [n for n in ways.get(w, []) if n in nodes]
            for a, b in zip(refs, refs[1:]):
                if a != b:
                    d = dist_m(nodes[a], nodes[b])
                    self.adj[a].append((b, d))
                    self.adj[b].append((a, d))
        self.pos = {n: nodes[n] for n in self.adj}
        self.grid = defaultdict(list)
        for n, p in self.pos.items():
            self.grid[(int(p[0] / CELL), int(p[1] / CELL))].append(n)

    def nearest(self, lat, lon):
        ci, cj = int(lat / CELL), int(lon / CELL)
        best = (1e18, None)
        for i in (ci - 1, ci, ci + 1):
            for j in (cj - 1, cj, cj + 1):
                for n in self.grid.get((i, j), ()):
                    d = dist_m((lat, lon), self.pos[n])
                    if d < best[0]:
                        best = (d, n)
        return best

    def route(self, a, b, limit):
        dist, prev, pq = {a: 0.0}, {}, [(0.0, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, 1e18):
                continue
            if u == b:
                path = [u]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return d, [self.pos[n] for n in path[::-1]]
            if d > limit:
                return None
            for v, w in self.adj[u]:
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(pq, (nd, v))
        return None


def unspike(line):
    """同じ点の重なりと、100° を超える折り返し（渡り線で上下線を乗り換えたところ）を取り除く。"""
    def back(a, b, c):
        ux, uy, vx, vy = b[1] - a[1], b[0] - a[0], c[1] - b[1], c[0] - b[0]
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        return n == 0 or (ux * vx + uy * vy) / n < -0.2
    out = []
    for p in line:
        if out and out[-1] == p:
            continue
        out.append(p)
        while len(out) >= 3 and back(out[-3], out[-2], out[-1]):
            del out[-2]
    return out


def main(path):
    nodes, ways, rels = load_opl(path)
    rels = [Rel(r, nodes, ways) for r in rels]
    rels = [r for r in rels if r.pos]
    ALL = Rel({"id": 0, "name": "全路線", "ways": list(ways)}, nodes, ways)
    loose = 0
    net = Network(since=19 * 60)
    out, hit, miss = {}, 0, 0
    for ri, rid in enumerate(net.railways):
        order, seen = [], set()
        for sid in net.railway_order.get(rid, []):
            nid = net.sta2node.get(sid)
            if nid is not None and nid not in seen:
                seen.add(nid)
                order.append(nid)
        pos = [net.node_pos[n] for n in order]

        # リレーションごとに、どの駅を覆うか（駅 → 線路上のいちばん近い点）
        cover = {}
        for r in rels:
            c = {}
            for k, p in enumerate(pos):
                d, n = r.nearest(*p)
                if d <= COVER_M:
                    c[k] = n
            # 隣り合う 2 駅以上を覆うものだけ（交差するだけの路線を除く）
            if any(k + 1 in c for k in c):
                cover[r] = c
        # 多くの駅を覆うものから採る。まだ覆われていない駅を増やすものだけ足す
        chosen, done = [], set()
        for r in sorted(cover, key=lambda r: -len(cover[r])):
            if set(cover[r]) - done or len(cover[r]) >= 0.8 * len(pos):
                chosen.append(r)
                done |= set(cover[r])

        segs, prev_rel = [], None
        for k in range(len(order) - 1):
            pa, pb = pos[k], pos[k + 1]
            limit = dist_m(pa, pb) * DETOUR + 300
            best = None
            # その路線そのもの（駅をいちばん多く覆うリレーションの半分以上を覆うもの）の中で最短を採る。
            # 並行する別路線のリレーションは、それで引けないときだけ使う
            # 前の駅間と同じリレーションで引けて、最短と大差なければそれを使う
            # （上り・下りのリレーションが駅ごとに入れ替わると、駅で線が横に 10〜20m 跳ねる）
            top = max((len(cover[r]) for r in chosen), default=0)
            for main_only in (True, False):
                found = {}
                for r in chosen:
                    c = cover[r]
                    if main_only != (len(c) >= top / 2) or k not in c or k + 1 not in c:
                        continue
                    res = r.route(c[k], c[k + 1], limit)
                    if res and len(res[1]) > 1 and res[0] <= limit:
                        found[r] = res
                if found:
                    r = min(found, key=lambda r: found[r][0])
                    if prev_rel in found and found[prev_rel][0] <= found[r][0] * 1.15 + 50:
                        r = prev_rel
                    best, prev_rel = found[r], r
                    break
            # リレーションで引けない駅間（線路が途切れている）や、リレーションでは大回りになる駅間
            # （リレーションに短絡線が入っていない）は、全路線の線路で引く。
            # 別路線への乗り移りを避けるため、回り道はほとんど許さない
            if not best or best[0] > dist_m(pa, pb) * 1.5 + 500:
                d0, n0 = ALL.nearest(*pa)
                d1, n1 = ALL.nearest(*pb)
                tight = dist_m(pa, pb) * 1.3 + 200
                if d0 <= COVER_M and d1 <= COVER_M:
                    res = ALL.route(n0, n1, tight)
                    if res and len(res[1]) > 1 and res[0] <= tight:
                        best = res
                        loose += 1
            if best:
                segs.append(unspike([[round(p[0], 5), round(p[1], 5)] for p in best[1]]))
                hit += 1
            else:
                segs.append([[round(pa[0], 5), round(pa[1], 5)], [round(pb[0], 5), round(pb[1], 5)]])
                miss += 1
        out[ri] = segs
        names = "・".join(sorted({r.name for r in chosen})[:4])
        print(f"[{ri+1}/{len(net.railways)}] {net.railway_title.get(rid)}: 駅間 {len(segs)}"
              f"  リレーション {len(chosen)}（{names}）", flush=True)
    p = ROOT / "data" / "rail_shapes.json"
    p.write_text(json.dumps(out, separators=(",", ":")))
    print(f"線路なりに引けた駅間 {hit}（うち全路線の線路で引いた {loose}） / 直線のまま {miss} → {p} ({p.stat().st_size/1e6:.1f}MB)")


if __name__ == "__main__":
    main(sys.argv[1])
