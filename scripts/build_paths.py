#!/usr/bin/env python3
"""行きと帰りの経路を site/data に書く。所要時間（home/*.json の travel・back）と同じ条件で探索する。

    python3 scripts/build_paths.py               # build_static.py を流し直さずに足せる
    python3 scripts/build_paths.py --transfers   # 帰りの乗り換え回数だけ足し直す
    python3 scripts/build_paths.py --backto      # backto だけ作り直す

  go/<出発駅>.json    その駅を集合時刻（19:00）に出て、候補駅に着く経路   {候補駅: [[路線, 乗る駅, 降りる駅], ...]}
  back/<候補駅>.json  その候補駅を BACK_DEPART（21:30）に出て、各駅に着く経路 {駅: [...]}
  home/<駅>.json の back_x  候補駅からその駅へ帰るときの乗り換え回数（候補でない駅・帰れない駅は -1）
  backto/<自宅>.json  back を自宅ごとに並べ替えたもの {候補駅: [...]}。全候補の運賃を出すのに使う（中身は back と同じ）

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
    add_transfers(len(net.node_name), cands)
    add_backto(len(net.node_name), cands)


def transfers(legs):
    """乗り換え回数＝乗る列車の本数 − 1（徒歩の区間は数えない。乗らないなら 0）。"""
    return max(sum(1 for rw, _, _ in legs if rw >= 0) - 1, 0)


def add_transfers(n_node, cands):
    """back/<候補駅>.json から、帰りの乗り換え回数を home/<駅>.json の back_x に書く。"""
    x = [[-1] * n_node for _ in range(n_node)]   # x[自宅][候補]
    for c in cands:
        x[c][c] = 0
        for h, legs in json.loads((DATA / "back" / f"{c}.json").read_text()).items():
            x[int(h)][c] = transfers(legs)
    for f in (DATA / "home").glob("*.json"):
        rec = json.loads(f.read_text())
        rec["back_x"] = x[int(f.stem)]
        f.write_text(json.dumps(rec, separators=(",", ":")))
    print("帰りの乗り換え回数を home に追加", flush=True)


def add_backto(n_node, cands):
    """back/<候補駅>.json（候補駅 → 全駅）を、自宅ごと（全候補駅 → その自宅）に並べ替えて backto/<自宅>.json に書く。
    運賃で候補を順位づけるには全候補の帰りの経路が要るが、back を候補の数だけ読むと重いので。"""
    out = [{} for _ in range(n_node)]
    for c in cands:
        for h, legs in json.loads((DATA / "back" / f"{c}.json").read_text()).items():
            out[int(h)][c] = legs
    (DATA / "backto").mkdir(parents=True, exist_ok=True)
    for h in range(n_node):
        (DATA / "backto" / f"{h}.json").write_text(json.dumps(out[h], separators=(",", ":")))
    print("帰りの経路を自宅ごとに並べ替えた（backto）", flush=True)


if __name__ == "__main__":
    index = json.loads((ROOT / "data" / "index.json").read_text())
    cands = [n["id"] for n in index if n["bars"] >= CAND_MIN_BARS]
    if "--transfers" in sys.argv:   # 経路は作り直さず、乗り換え回数だけ足す
        add_transfers(len(index), cands)
    elif "--backto" in sys.argv:
        add_backto(len(index), cands)
    else:
        add_paths(Network(since=DEPART), index)
