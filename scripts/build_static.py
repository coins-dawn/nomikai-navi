#!/usr/bin/env python3
"""GitHub Pages 用に site/ を作る。

**時刻表そのものは配らない。** 公共交通オープンデータ基本ライセンス第8条4項(1) が
「元のデータの大部分を復元可能な派生データ」の再配布を禁じているため、
ブラウザに時刻表を送って探索させる作りは採れない。
代わりに「自宅 × 駅」の探索結果（帰宅リミット・所要時間・経路の区間）だけを先に計算して配る。

出力（site/data/）
  meta.json            駅・路線（駅の並びとラインカラー）・集合時刻の一覧
  home/<駅>.json       その駅に住む人の 帰宅リミット と 所要時間（全駅ぶん）
  route/<自宅>.json    その自宅への帰りの経路。区間は [路線, 乗る駅, 降りる駅] の 3 つだけで、
                       途中の駅は路線の駅順から画面側で引き直す（容量を 1/4 にするため）
  bars/<駅>.json       その駅の半径 500m の飲み屋
"""
import json, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from network import Network, dist_m   # noqa: E402

SITE = ROOT / "site"
DATA = SITE / "data"
PRESETS = [19 * 60]   # 集合時刻は 19:00 に固定（画面からも外した）
NEG = -10**6


def main(limit_rows=None):
    t0 = time.time()
    net = Network(since=min(PRESETS))
    n_node = len(net.node_name)
    bars_by = {b["node"]: b for b in json.loads((ROOT / "data" / "bars_by_station.json").read_text())}
    bars_pts = json.loads((ROOT / "data" / "bars_points.json").read_text())
    index = json.loads((ROOT / "data" / "index.json").read_text())
    name2id = {}
    for n in index:
        name2id.setdefault(n["name"], n["id"])
    print(f"駅 {n_node} / 便 {len(net.trips)}", flush=True)

    for d in ("home", "route", "bars"):
        (DATA / d).mkdir(parents=True, exist_ok=True)

    # --- 飲み屋（飲み屋のある駅だけ） ---
    grid = {}
    for b in bars_pts:
        grid.setdefault((round(b[0], 2), round(b[1], 2)), []).append(b)
    n_bar_files = 0
    for n in index:
        if not n["bars"]:
            continue
        la, lo = n["lat"], n["lon"]
        near = [{"lat": b[0], "lon": b[1], "name": b[2], "kind": b[3]}
                for dy in (-0.01, 0, 0.01) for dx in (-0.01, 0, 0.01)
                for b in grid.get((round(la + dy, 2), round(lo + dx, 2)), [])
                if dist_m((la, lo), (b[0], b[1])) <= 500]
        (DATA / "bars" / f"{n['id']}.json").write_text(json.dumps(near, ensure_ascii=False))
        n_bar_files += 1
    print(f"飲み屋ファイル {n_bar_files} 本  {time.time()-t0:.0f}s", flush=True)

    # --- 行（自宅）の一覧。終電は鉄道だけで考える（2026-10-07 ユーザー指示でバスは外した） ---
    homes = [n["id"] for n in index]
    if limit_rows:
        homes = homes[:limit_rows]
    print(f"自宅 {len(homes)}", flush=True)

    def do_row(home, deadline, key, store_travel):
        """1 回の逆向き探索で、全駅のリミットと全駅からの帰りの経路が取れる。"""
        lab, par = net.latest_departure_paths(home, deadline=deadline)
        routes = {}
        for x in range(n_node):
            if lab[x] <= NEG or x == home:
                continue
            legs = net.rebuild(par, lab, x, home)
            if legs:
                routes[x] = [[lg["rw"], lg["nodes"][0], lg["nodes"][-1]] for lg in legs]
        (DATA / "route" / f"{key}.json").write_text(json.dumps(routes, separators=(",", ":")))
        rec = {"limit": [lab[x] if lab[x] > NEG else -1 for x in range(n_node)]}
        if store_travel:
            rec["travel"] = {}
            for p in PRESETS:
                arr = net.earliest_arrival(home, p)
                rec["travel"][str(p)] = [arr[x] - p if arr[x] < 10**6 else -1 for x in range(n_node)]
        return rec

    for i, h in enumerate(homes, 1):
        rec = do_row(h, None, str(h), True)
        (DATA / "home" / f"{h}.json").write_text(json.dumps(rec, separators=(",", ":")))
        if i % 100 == 0:
            print(f"  自宅 {i}/{len(homes)}  {time.time()-t0:.0f}s", flush=True)

    # --- 路線（駅の並びとラインカラー）。経路の描画と路線網の表示の両方に使う ---
    rails = []
    for rid in net.railways:
        order, seen = [], set()
        for sid in net.railway_order.get(rid, []):
            nid = net.sta2node.get(sid)
            if nid is not None and nid not in seen:
                seen.add(nid)
                order.append(nid)
        rails.append({"t": net.railway_title.get(rid, ""), "c": net.railway_color.get(rid), "o": order})

    site_cfg = json.loads((ROOT / "data" / "site.json").read_text())
    meta = {
        "stations": [{"id": n["id"], "n": n["name"], "lat": n["lat"], "lon": n["lon"],
                      "b": n["bars"], "m": n["median_m"], "l": n["lines"]} for n in index],
        "presets": PRESETS,
        "rails": rails,
        "built": time.strftime("%Y-%m-%d"),
        "acquired": site_cfg.get("acquired", {}),
        "contact": {k: site_cfg.get(k) for k in ("contact_label", "contact_url")},
    }
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")))

    shp = ROOT / "data" / "rail_shapes.json"
    if shp.exists():
        shutil.copy(shp, DATA / "rail_shapes.json")
    shutil.copy(ROOT / "frontend" / "index.html", SITE / "index.html")
    shutil.copy(ROOT / "frontend" / "engine-static.js", SITE / "engine.js")
    (SITE / ".nojekyll").write_text("")
    total = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"できあがり: {SITE}  {total/1e6:.1f}MB  {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
