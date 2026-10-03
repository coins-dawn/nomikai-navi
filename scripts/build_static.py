#!/usr/bin/env python3
"""GitHub Pages 用に site/ を作る。

**時刻表そのものは配らない。** 公共交通オープンデータ基本ライセンス第8条4項(1) が
「元のデータの大部分を復元可能な派生データ」の再配布を禁じているため、
ブラウザに時刻表を送って探索させる作りは採れない。
代わりに「自宅 × 候補駅」の探索結果（帰宅リミット・所要時間・経路の駅の並び）だけを先に計算して配る。

出力（site/data/）
  meta.json            駅・候補駅・集合時刻の一覧
  home/<駅>.json       その駅に住む人の 帰宅リミット と 所要時間（候補駅ぶん）
  bus/<駅>.json        その駅から乗れるバスと、最終バスごとの帰宅リミット
  route/<候補>.json    その駅から各自宅への帰りの経路（駅の並びと路線名。時刻は出発時刻だけ）
  bars/<候補>.json     その駅の半径 500m の飲み屋
"""
import json, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from network import Network, fmt   # noqa: E402

SITE = ROOT / "site"
DATA = SITE / "data"
PRESETS = [19 * 60, 20 * 60]   # 集合時刻（事前計算なので候補を絞る。増やすと比例して時間がかかる）
CAND_MIN_BARS = 10        # 候補駅に入れる最低の飲み屋の数
NEG = -10**6


def main(limit_rows=None):
    t0 = time.time()
    net = Network(since=min(PRESETS))
    bars_by = {b["node"]: b for b in json.loads((ROOT / "data" / "bars_by_station.json").read_text())}
    bars_pts = json.loads((ROOT / "data" / "bars_points.json").read_text())
    busstops = json.loads((ROOT / "data" / "busstops.json").read_text())
    index = json.loads((ROOT / "data" / "index.json").read_text())
    name2id = {}
    for n in index:
        name2id.setdefault(n["name"], n["id"])

    cands = [n["id"] for n in index if n["bars"] >= CAND_MIN_BARS]
    cpos = {c: i for i, c in enumerate(cands)}
    print(f"候補駅 {len(cands)} / 駅 {len(index)}", flush=True)

    for d in ("home", "bus", "route", "bars"):
        (DATA / d).mkdir(parents=True, exist_ok=True)

    # --- 飲み屋（候補駅ごと） ---
    from network import dist_m
    grid = {}
    for b in bars_pts:
        grid.setdefault((round(b[0], 2), round(b[1], 2)), []).append(b)
    for c in cands:
        la, lo = net.node_pos[c]
        near = []
        for dy in (-0.01, 0, 0.01):
            for dx in (-0.01, 0, 0.01):
                for b in grid.get((round(la + dy, 2), round(lo + dx, 2)), []):
                    if dist_m((la, lo), (b[0], b[1])) <= 500:
                        near.append({"lat": b[0], "lon": b[1], "name": b[2], "kind": b[3]})
        (DATA / "bars" / f"{c}.json").write_text(json.dumps(near, ensure_ascii=False))
    print(f"飲み屋ファイル {len(cands)} 本  {time.time()-t0:.0f}s", flush=True)

    # --- 行（自宅）の一覧をつくる ---
    homes = [n["id"] for n in index]
    bus_rows = []        # (駅ノード, 最終バス時刻)
    for st, lst in busstops.items():
        nid = name2id.get(st)
        if nid is None:
            continue
        for last in sorted({b["last"] for b in lst}):
            bus_rows.append((nid, last))
    if limit_rows:
        homes, bus_rows = homes[:limit_rows], bus_rows[:limit_rows]
    print(f"自宅 {len(homes)} / バスの組 {len(bus_rows)}", flush=True)

    routes = {c: {} for c in cands}      # 候補駅 -> {行キー: 経路}
    lines = {}                           # 路線名 -> 連番

    def enc(legs):
        out = []
        for lg in legs:
            nm = lg["line"]
            if nm not in lines:
                lines[nm] = len(lines)
            out.append([lines[nm]] + lg["nodes"])
        return out

    def do_row(home, deadline, key, store_travel):
        lab, par = net.latest_departure_paths(home, deadline=deadline)
        lim = [lab[c] if lab[c] > NEG else -1 for c in cands]
        for c in cands:
            if lab[c] <= NEG:
                continue
            legs = net.rebuild(par, lab, c, home)
            if legs:
                routes[c][key] = enc(legs)
        rec = {"limit": lim}
        if store_travel:
            rec["travel"] = {}
            for p in PRESETS:
                arr = net.earliest_arrival(home, p)
                rec["travel"][str(p)] = [arr[c] - p if arr[c] < 10**6 else -1 for c in cands]
        return rec

    for i, h in enumerate(homes, 1):
        rec = do_row(h, None, str(h), True)
        (DATA / "home" / f"{h}.json").write_text(json.dumps(rec, separators=(",", ":")))
        if i % 100 == 0:
            print(f"  自宅 {i}/{len(homes)}  {time.time()-t0:.0f}s", flush=True)

    bus_out = {}
    for i, (nid, last) in enumerate(bus_rows, 1):
        rec = do_row(nid, last, f"b{nid}_{last}", False)
        bus_out.setdefault(nid, {})[str(last)] = rec["limit"]
        if i % 100 == 0:
            print(f"  バス {i}/{len(bus_rows)}  {time.time()-t0:.0f}s", flush=True)
    for st, lst in busstops.items():
        nid = name2id.get(st)
        if nid is None or nid not in bus_out:
            continue
        (DATA / "bus" / f"{nid}.json").write_text(json.dumps(
            {"stops": lst, "limits": bus_out[nid]}, ensure_ascii=False, separators=(",", ":")))

    for c in cands:
        (DATA / "route" / f"{c}.json").write_text(json.dumps(routes[c], separators=(",", ":")))

    meta = {
        "stations": [{"id": n["id"], "n": n["name"], "lat": n["lat"], "lon": n["lon"],
                      "b": n["bars"], "m": n["median_m"], "l": n["lines"]} for n in index],
        "cands": cands,
        "presets": PRESETS,
        "lines": [k for k, _ in sorted(lines.items(), key=lambda kv: kv[1])],
        "bus_stations": sorted(name2id[s] for s in busstops if name2id.get(s) in bus_out),
        "built": time.strftime("%Y-%m-%d"),
    }
    site_cfg = json.loads((ROOT / "data" / "site.json").read_text())
    meta["acquired"] = site_cfg.get("acquired", {})
    meta["contact"] = {k: site_cfg.get(k) for k in ("contact_label", "contact_url")}
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")))

    shutil.copy(ROOT / "frontend" / "index.html", SITE / "index.html")
    shutil.copy(ROOT / "frontend" / "engine-static.js", SITE / "engine.js")
    (SITE / ".nojekyll").write_text("")
    total = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"できあがり: {SITE}  {total/1e6:.1f}MB  {time.time()-t0:.0f}s")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(n)
