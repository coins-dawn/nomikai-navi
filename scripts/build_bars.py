#!/usr/bin/env python3
"""OSM から飲み屋（pub / bar / nightclub）を取り出し、駅ノードごとに数える。

日本の OSM では居酒屋は amenity=pub で入っている（cuisine=izakaya はほとんど使われない）。
"""
import json, math, subprocess, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from network import Network, dist_m

ROOT = Path(__file__).resolve().parents[1]
PBF = ROOT.parent / "data-exploration" / "data" / "osm" / "kanto-latest.osm.pbf"
OUT = ROOT / "data"
RADIUS = 500


def extract():
    tmp = OUT / "raw" / "kanto_drink.geojsonl"
    if tmp.exists():
        return tmp
    pbf = OUT / "raw" / "kanto_drink.osm.pbf"
    subprocess.run(["osmium", "tags-filter", str(PBF), "nwr/amenity=pub,bar,nightclub",
                    "-o", str(pbf), "--overwrite"], check=True)
    subprocess.run(["osmium", "export", str(pbf), "-f", "geojsonseq",
                    "-o", str(tmp), "--overwrite"], check=True)
    return tmp


def main():
    path = extract()
    pts, recs = [], []
    for line in path.open():
        line = line.strip("\x1e\n ")
        if not line:
            continue
        f = json.loads(line)
        g = f["geometry"]
        if g["type"] != "Point":
            continue
        lat, lon = g["coordinates"][1], g["coordinates"][0]
        pr = f["properties"]
        pts.append((lat, lon))
        recs.append([round(lat, 5), round(lon, 5), pr.get("name", ""), pr.get("amenity", "")])
    print(f"飲み屋 {len(pts)} 件")
    (OUT / "bars_points.json").write_text(json.dumps(recs, ensure_ascii=False))

    grid = defaultdict(list)
    for p in pts:
        grid[(round(p[0], 2), round(p[1], 2))].append(p)

    net = Network()
    out = []
    for i, pos in enumerate(net.node_pos):
        near = []
        for dy in (-0.01, 0, 0.01):
            for dx in (-0.01, 0, 0.01):
                for p in grid.get((round(pos[0] + dy, 2), round(pos[1] + dx, 2)), []):
                    d = dist_m(pos, p)
                    if d <= RADIUS:
                        near.append(d)
        near.sort()
        out.append({
            "node": i,
            "name": net.node_name[i],
            "bars": len(near),
            # 密集度: 近い方から 30 軒目までの距離の中央値（小さいほど固まっている）
            "median_m": int(near[len(near) // 2]) if near else None,
        })
    (OUT / "bars_by_station.json").write_text(json.dumps(out, ensure_ascii=False))
    top = sorted(out, key=lambda x: -x["bars"])[:10]
    for t in top:
        print(f"{t['bars']:5d}  中央{t['median_m']}m  {t['name']}")
    print("飲み屋0の駅", sum(1 for x in out if x["bars"] == 0), "/", len(out))


if __name__ == "__main__":
    main()
