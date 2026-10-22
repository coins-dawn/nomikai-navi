#!/usr/bin/env python3
"""site/data/home/<駅>.json に「飲み会駅 → その駅」の帰りの所要時間（back）を足す。

    python3 scripts/build_back.py      # build_static.py を流し直さずに足せる（数分）

候補になる駅（飲み屋 CAND_MIN_BARS 軒以上）から BACK_DEPART に出る順方向探索を 1 本ずつ流し、
着いた時刻 − BACK_DEPART を、着いた駅の home ファイルに書く。候補でない駅は -1。
入るのは所要時間の数値だけで、時刻表は復元できない（build_static.py の方針と同じ）。
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from network import Network   # noqa: E402

HOME = ROOT / "site" / "data" / "home"
BACK_DEPART = 21 * 60 + 30   # 一次会がはねる時刻（帰りの所要時間はこの時刻に出たときで測る）
CAND_MIN_BARS = 10


def add_back(net, index):
    t0 = time.time()
    n_node = len(net.node_name)
    cands = [n["id"] for n in index if n["bars"] >= CAND_MIN_BARS]
    back = [[-1] * n_node for _ in range(n_node)]   # back[自宅][候補]
    for k, c in enumerate(cands, 1):
        arr = net.earliest_arrival(c, BACK_DEPART)
        for h in range(n_node):
            if arr[h] < 10**6:
                back[h][c] = arr[h] - BACK_DEPART
        if k % 50 == 0:
            print(f"  候補 {k}/{len(cands)}  {time.time()-t0:.0f}s", flush=True)
    for f in HOME.glob("*.json"):
        h = int(f.stem)
        rec = json.loads(f.read_text())
        rec["back"] = back[h]
        rec["back_depart"] = BACK_DEPART
        f.write_text(json.dumps(rec, separators=(",", ":")))
    print(f"帰りの所要時間: 候補 {len(cands)} 駅  {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    add_back(Network(since=19 * 60), json.loads((ROOT / "data" / "index.json").read_text()))
