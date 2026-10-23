#!/usr/bin/env python3
"""行きと帰りの経路を site/data に書く。所要時間（home/*.json の travel・back）と同じ条件で探索する。

    python3 scripts/build_paths.py     # build_static.py を流し直さずに足せる

  go/<出発駅>.json    その駅を集合時刻（19:00）に出て、候補駅に着く経路   {候補駅: [[路線, 乗る駅, 降りる駅], ...]}
  back/<候補駅>.json  その候補駅を BACK_DEPART（21:30）に出て、各駅に着く経路 {駅: [...]}

候補駅は飲み屋 CAND_MIN_BARS 軒以上。区間は乗る駅・降りる駅だけで、時刻は入れない（時刻表は復元できない）。
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from network import Network                            # noqa: E402
from build_back import BACK_DEPART, CAND_MIN_BARS      # noqa: E402

DATA = ROOT / "site" / "data"
DEPART = 19 * 60


def add_paths(net, index):
    t0 = time.time()
    cands = [n["id"] for n in index if n["bars"] >= CAND_MIN_BARS]
    for d in ("go", "back"):
        (DATA / d).mkdir(parents=True, exist_ok=True)
    for k, o in enumerate(range(len(net.node_name)), 1):
        _, par = net.earliest_arrival_paths(o, DEPART)
        out = {c: legs for c in cands if c != o and (legs := net.rebuild_forward(par, o, c))}
        (DATA / "go" / f"{o}.json").write_text(json.dumps(out, separators=(",", ":")))
        if k % 200 == 0:
            print(f"  行き {k}/{len(net.node_name)}  {time.time()-t0:.0f}s", flush=True)
    for c in cands:
        _, par = net.earliest_arrival_paths(c, BACK_DEPART)
        out = {h: legs for h in range(len(net.node_name)) if h != c and (legs := net.rebuild_forward(par, c, h))}
        (DATA / "back" / f"{c}.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"行きと帰りの経路  {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    add_paths(Network(since=DEPART), json.loads((ROOT / "data" / "index.json").read_text()))
