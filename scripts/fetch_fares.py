#!/usr/bin/env python3
"""ODPT の駅間運賃（odpt:RailwayFare）を事業者ごとに取得して data/raw/fares.json に置く。

1 回の問い合わせは 1000 件で頭打ちになるので、乗る駅（odpt:fromStation）ごとに取る。
JR東日本は運賃データが提供されていない（0 件）ので取らない。

ここで取った運賃表は **配らない**（基本ライセンス第8条4項(1)）。build_fares.py で
距離帯の境目を合わせることと、概算の当たり具合を測ることにだけ使う。
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_odpt import OPERATORS, RAW, get   # noqa: E402


def main():
    stations = json.loads((RAW / "stations.json").read_text())
    out = []
    for op, ch in OPERATORS.items():
        if op == "JR-East":
            continue
        sids = sorted({s["owl:sameAs"] for s in stations if s["owl:sameAs"].split(":")[1].split(".")[0] == op})
        n = 0
        for k, sid in enumerate(sids, 1):
            rows = get("odpt:RailwayFare", ch, **{"odpt:fromStation": sid})
            if len(rows) >= 1000:
                print(f"  ** {sid} は 1000 件で頭打ち")
            out += [{"from": r["odpt:fromStation"], "to": r["odpt:toStation"],
                     "ic": r.get("odpt:icCardFare"), "ticket": r.get("odpt:ticketFare")} for r in rows]
            n += len(rows)
            time.sleep(0.6)
        print(f"{op}: 駅 {len(sids)} / 運賃 {n}", flush=True)
    (RAW / "fares.json").write_text(json.dumps(out, ensure_ascii=False))
    print(f"合計 {len(out)} 件")


if __name__ == "__main__":
    main()
