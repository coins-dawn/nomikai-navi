#!/usr/bin/env python3
"""運賃の概算に使う site/data/fare.json を作る。

    python3 scripts/fetch_fares.py   # ODPT の駅間運賃を data/raw/fares.json に取る（配らない）
    python3 scripts/build_fares.py

**ODPT の駅間運賃表そのものは配らない**（基本ライセンス第8条4項(1)：元のデータの大部分を
復元できる派生データの再配布の禁止）。配るのは次のものだけで、運賃はブラウザで距離から出す。

  seg_km   路線ごと・隣り合う駅間の線路の長さ（OSM の線形 rail_shapes.json から。ODbL）
  bands    事業者ごとの「距離 → 運賃（IC・大人）」の段。事業者が公表している距離帯の運賃と同じ形で、
           段の境目は ODPT の駅間運賃に合うように線路の長さの上で合わせる（線路の長さと営業キロのずれを吸収する）
  JR       ODPT に運賃が無いので、公表の賃率（幹線 16.96円/km・2026-03-14 改定）と計算のきまりで出す（画面側）
  run      路線ごと・隣り合う駅間の所要時間（分）の中央値。通勤経路（定期の区間）の最速経路を探すのに使う。
           発車時刻は入れないので時刻表は復元できない
  foot     徒歩でつなぐ駅どうし（分）
  loops    環状線の両端をつなぐ駅間 [路線, km, 分]
  rw_mult  運賃を出すときに路線ごとに距離に掛ける倍率（擬制キロや加算運賃がある路線を近似する。ふつうは 1）

当たり具合（ODPT の運賃と比べて何 % が一致したか）は data/fare_check.json に書く。
"""
import heapq, json, statistics, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from network import Network, dist_m   # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "site" / "data" / "fare.json"
OP_NAME = {"TokyoMetro": "東京メトロ", "Toei": "都営地下鉄", "MIR": "つくばエクスプレス", "TWR": "りんかい線",
           "TamaMonorail": "多摩モノレール", "YokohamaMunicipal": "横浜市営地下鉄", "JR-East": "JR東日本",
           "Keio": "京王電鉄", "Tobu": "東武鉄道", "Sotetsu": "相模鉄道",
           "Toei.Arakawa": "都電荒川線", "Toei.NipporiToneri": "日暮里・舎人ライナー"}
# 同じ事業者でも運賃の体系が別の路線（都営の路面電車・新交通は地下鉄と運賃が別）
SEPARATE = {"Toei.Arakawa", "Toei.NipporiToneri"}
MIN_SHARE = 0.005   # 組の 0.5% に満たない運賃の値（加算運賃などの例外）は段にしない（ただし 3 組以上あれば段にする）


def op_of(rid):
    """運賃の体系。ふつうは事業者、SEPARATE の路線はその路線だけで 1 つ。駅の ID（odpt.Station:事業者.路線.駅）にも使える。"""
    parts = rid.split(":")[1].split(".")
    two = ".".join(parts[:2])
    return two if two in SEPARATE else parts[0]


def rail_orders(net):
    out = []
    for rid in net.railways:
        order, seen = [], set()
        for sid in net.railway_order.get(rid, []):
            nid = net.sta2node.get(sid)
            if nid is not None and nid not in seen:
                seen.add(nid)
                order.append(nid)
        out.append(order)
    return out


def seg_lengths(net, orders):
    shapes = json.loads((ROOT / "data" / "rail_shapes.json").read_text())
    out = []
    for ri, order in enumerate(orders):
        segs = shapes.get(str(ri), [])
        km = []
        for k in range(len(order) - 1):
            line = segs[k] if k < len(segs) and len(segs[k]) > 1 else [net.node_pos[order[k]], net.node_pos[order[k + 1]]]
            km.append(round(sum(dist_m(a, b) for a, b in zip(line, line[1:])) / 1000, 2))
        out.append(km)
    return out


def run_minutes(net, orders, km):
    """隣り合う駅間の所要時間の中央値。各駅停車の隣り合う 2 駅だけを数える。"""
    pos = [{n: k for k, n in enumerate(o)} for o in orders]
    samples = [defaultdict(list) for _ in orders]
    for ti, seq in enumerate(net.trips):
        ri = net.trip_rw[ti]
        if ri < 0:
            continue
        for (a, _, dep), (b, arr, _) in zip(seq, seq[1:]):
            i, j = pos[ri].get(a), pos[ri].get(b)
            if i is not None and j is not None and abs(i - j) == 1:
                samples[ri][min(i, j)].append(arr - dep)
    out = []
    for ri, o in enumerate(orders):
        out.append([statistics.median(samples[ri][k]) if samples[ri][k] else round(km[ri][k] / 0.6 + 0.5, 1)
                    for k in range(len(o) - 1)])
    return out


def op_graph(orders, km, rw_op, op, mult=None):
    """その運賃体系の路線だけの網。mult があれば路線ごとに距離を掛ける（運賃計算用の擬制キロ・加算の近似）。"""
    adj = defaultdict(list)
    for ri, o in enumerate(orders):
        if rw_op[ri] != op:
            continue
        m = mult[ri] if mult else 1.0
        for k in range(len(o) - 1):
            adj[o[k]].append((o[k + 1], km[ri][k] * m))
            adj[o[k + 1]].append((o[k], km[ri][k] * m))
    return adj


def shortest(adj, src):
    dist, pq = {src: 0.0}, [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in adj[u]:
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w
                heapq.heappush(pq, (d + w, v))
    return dist


def fit_bands(samples):
    """(線路の長さ, 運賃) の組から、距離の段 [[この km 以下, 運賃], ...] を合わせる。
    運賃の値ごとに段を作り、隣の段との境目は「取り違える組がいちばん少ない距離」に置く。"""
    count = defaultdict(int)
    for _, f in samples:
        count[f] += 1
    levels = sorted(f for f, c in count.items() if c >= max(3, MIN_SHARE * len(samples)))
    bands = []
    lo = 0.0
    for k in range(len(levels) - 1):
        f, g = levels[k], levels[k + 1]
        pts = sorted((d, fare) for d, fare in samples if fare in (f, g))
        # 境目を i 番目と次の点の間に置いたとき、手前で g のもの・先で f のものが取り違え。いちばん少ない境目を採る
        best, err = None, 1e18
        n_g_below = 0
        n_f_above = sum(1 for _, fare in pts if fare == f)
        for i, (d, fare) in enumerate(pts):
            if fare == f:
                n_f_above -= 1
            else:
                n_g_below += 1
            nxt = pts[i + 1][0] if i + 1 < len(pts) else d + 1
            t = (d + nxt) / 2
            e = n_g_below + n_f_above
            if t > lo and e < err:
                best, err = t, e
        lo = best if best is not None else lo
        bands.append([round(lo, 2), f])
    if levels:
        bands.append([9999, levels[-1]])
    return bands


def band_fare(bands, km):
    for upto, f in bands:
        if km <= upto:
            return f
    return bands[-1][1]


def main():
    net = Network()
    orders = rail_orders(net)
    km = seg_lengths(net, orders)
    rw_op_name = [op_of(r) for r in net.railways]
    ops = list(dict.fromkeys(rw_op_name))
    rw_op = [ops.index(o) for o in rw_op_name]

    fares = json.loads((RAW / "fares.json").read_text())
    by_op = defaultdict(list)
    for r in fares:
        a, b = net.sta2node.get(r["from"]), net.sta2node.get(r["to"])
        if a is None or b is None or a == b or not r["ic"] or op_of(r["from"]) != op_of(r["to"]):
            continue
        by_op[op_of(r["from"])].append((a, b, r["ic"]))

    out_ops, check = [], {}
    mult = [1.0] * len(net.railways)
    for oi, op in enumerate(ops):
        ent = {"id": op, "name": OP_NAME.get(op, op)}
        if op == "JR-East":
            ent["jr"] = True
            out_ops.append(ent)
            continue
        def fit(mult):
            adj, cache, samples = op_graph(orders, km, rw_op, oi, mult), {}, []
            for a, b, f in by_op.get(op, []):
                if a not in cache:
                    cache[a] = shortest(adj, a)
                d = cache[a].get(b)
                if d is not None:
                    samples.append((d, f))
            bands = fit_bands(samples)
            hit = sum(band_fare(bands, d) == f for d, f in samples) / max(len(samples), 1)
            return hit, bands, samples
        hit, bands, samples = fit(mult)
        # 当たりが悪い体系は、路線ごとに距離を何倍かして（擬制キロ・加算運賃のある路線）当たりが増えるか試す
        mine = [ri for ri in range(len(rw_op)) if rw_op[ri] == oi]
        if hit < 0.95 and len(mine) > 1:
            for _ in range(2):
                for ri in mine:
                    best = (hit, mult[ri], bands, samples)
                    for m in (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0):
                        if m == mult[ri]:
                            continue
                        old_m, mult[ri] = mult[ri], m
                        h, b_, s_ = fit(mult)
                        if h > best[0] + 0.005:
                            best = (h, m, b_, s_)
                        mult[ri] = old_m
                    hit, mult[ri], bands, samples = best
            changed = {net.railway_title.get(net.railways[ri]): mult[ri] for ri in mine if mult[ri] != 1.0}
            if changed:
                print(f"  {OP_NAME.get(op, op)}: 距離を掛けた路線 {changed}")
        ent["bands"] = bands
        out_ops.append(ent)
        if samples:
            errs = [abs(band_fare(bands, d) - f) for d, f in samples]
            check[op] = {"pairs": len(samples), "exact": round(sum(e == 0 for e in errs) / len(errs), 3),
                         "within_10yen": round(sum(e <= 10 for e in errs) / len(errs), 3),
                         "mean_abs_yen": round(sum(errs) / len(errs), 1), "max_abs_yen": max(errs),
                         "bands": len(bands)}
            print(f"{OP_NAME.get(op, op)}: 組 {len(samples)}  一致 {check[op]['exact']:.1%}  ±10円 {check[op]['within_10yen']:.1%}"
                  f"  平均の誤差 {check[op]['mean_abs_yen']}円  段 {len(bands)}", flush=True)

    run = run_minutes(net, orders, km)
    # 環状線（山手線）は駅の並びが 大崎 … 品川 で切れているので、両端をつなぐ駅間を足す
    loops = []
    for ri, o in enumerate(orders):
        if len(o) > 5 and dist_m(net.node_pos[o[0]], net.node_pos[o[-1]]) < 3000:
            d = round(dist_m(net.node_pos[o[0]], net.node_pos[o[-1]]) * 1.1 / 1000, 2)
            loops.append([ri, d, round(d / 0.6 + 0.5, 1)])
            print(f"環状: {net.railway_title.get(net.railways[ri])} {net.node_name[o[-1]]}〜{net.node_name[o[0]]} {d}km")
    foot = sorted({(min(i, j), max(i, j), c) for i in net.foot for j, c in net.foot[i]})
    OUT.write_text(json.dumps({"ops": out_ops, "rw_op": rw_op, "seg_km": km, "run": run,
                               "foot": [list(x) for x in foot], "loops": loops, "rw_mult": mult, "transfer": 5},
                              ensure_ascii=False, separators=(",", ":")))
    (ROOT / "data" / "fare_check.json").write_text(json.dumps(check, ensure_ascii=False, indent=1))
    print(f"→ {OUT} ({OUT.stat().st_size/1e3:.0f}KB)")


if __name__ == "__main__":
    main()
