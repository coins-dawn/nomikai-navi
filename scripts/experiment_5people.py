#!/usr/bin/env python3
"""5 人ぶんの検証: 「所要時間が最小の駅」と「帰宅リミットが最大の駅」はズレるか。

変種1: 全員が駅の近くに住んでいる（鉄道だけで帰れる）
変種2: 2 人が駅から路線バスに乗り継ぐ（＝最終バスがリミットを決める）
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from network import Network, fmt
from bus import last_bus

PEOPLE_RAIL = [
    ("Aさん", "荻窪", None),
    ("Bさん", "川口", None),
    ("Cさん", "西船橋", None),
    ("Dさん", "蒲田", None),
    ("Eさん", "聖蹟桜ヶ丘", None),
]
PEOPLE_BUS = [
    ("Aさん", "荻窪", ("kanto_bus", "荻窪駅北口", "下井草二丁目")),
    ("Bさん", "川口", None),
    ("Cさん", "西船橋", None),
    ("Dさん", "蒲田", None),
    ("Eさん", "聖蹟桜ヶ丘", ("keio_bus", "聖蹟桜ヶ丘駅", "聖ヶ丘団地")),
]
DEPART = 19 * 60

net = Network()
bars = {b["node"]: b["bars"] for b in json.loads(Path("data/bars_by_station.json").read_text())}


def run(people, title):
    ids = [net.find(st) for _, st, _ in people]
    arr = [net.earliest_arrival(i, DEPART) for i in ids]
    lim = []
    for (who, st, busleg), i in zip(people, ids):
        if busleg is None:
            lim.append(net.latest_departure(i))
        else:
            feed, stop, home = busleg
            t, d = last_bus(feed, stop, home)
            lim.append(net.latest_departure(i, deadline=t))
    rows = []
    for i in range(len(net.node_name)):
        if any(a[i] >= 10**6 for a in arr) or any(l[i] <= -10**6 for l in lim):
            continue
        times = [a[i] - DEPART for a in arr]
        limits = [l[i] for l in lim]
        stay = [l - (DEPART + t) for l, t in zip(limits, times)]
        rows.append({"name": net.node_name[i], "sum": sum(times), "max": max(times),
                     "times": times, "minlimit": min(limits), "limits": limits,
                     "stay": stay, "minstay": min(stay),
                     "who": people[limits.index(min(limits))][0], "bars": bars.get(i, 0)})

    print(f"\n{'='*78}\n{title}\n{'='*78}")
    for (who, st, busleg) in people:
        if busleg:
            feed, stop, home = busleg
            t, d = last_bus(feed, stop, home)
            print(f"  {who}: {st} 駅 →〔{feed}〕{home} 停留所（{stop} {fmt(t)} 発が最終・{d}分）")
        else:
            print(f"  {who}: {st} 駅の近く")

    def show(label, key, filt=None, n=6):
        print(f"\n--- {label} ---")
        print(f"  {'駅':<10}{'合計':>5}{'最大':>5}{'リミット':>9} {'最も早い人':<8}{'飲み屋':>5}")
        for r in sorted([x for x in rows if filt is None or filt(x)], key=key)[:n]:
            print(f"  {r['name']:<10}{r['sum']:>5}{r['max']:>5}{fmt(r['minlimit']):>9} {r['who']:<8}{r['bars']:>5}")

    show("① 所要時間の合計が最小（atsumaru-now 方式）", lambda r: r["sum"])
    show("② 帰宅リミットが最大（この案の方式）", lambda r: -r["minlimit"])
    show("③ ②のうち 飲み屋 30 軒以上", lambda r: -r["minlimit"], filt=lambda r: r["bars"] >= 30)
    print("\n--- ④ 滞在できる時間（リミット−到着時刻）の最小値が最大／飲み屋 30 軒以上 ---")
    print(f"  {'駅':<10}{'合計':>5}{'最短滞在':>8}{'リミット':>9} {'最も早い人':<8}{'飲み屋':>5}")
    for r in sorted([x for x in rows if x["bars"] >= 30], key=lambda r: -r["minstay"])[:6]:
        print(f"  {r['name']:<10}{r['sum']:>5}{r['minstay']:>8}{fmt(r['minlimit']):>9} {r['who']:<8}{r['bars']:>5}")

    a = min(rows, key=lambda r: r["sum"])
    b = max([r for r in rows if r["bars"] >= 30], key=lambda r: r["minstay"])
    print(f"\n  → 所要時間で選ぶと【{a['name']}】リミット {fmt(a['minlimit'])}・飲み屋 {a['bars']}軒")
    print(f"  → 滞在時間＋飲み屋で選ぶと【{b['name']}】リミット {fmt(b['minlimit'])}・飲み屋 {b['bars']}軒")
    print(f"  → 駅は{'同じ' if a['name']==b['name'] else '違う'}。"
          f"いちばん短い人の滞在時間 {a['minstay']}分 → {b['minstay']}分（{b['minstay']-a['minstay']:+d} 分）"
          f"／合計所要時間は {b['sum']-a['sum']:+d} 分")
    print(f"\n  【{b['name']}】での各人の内訳")
    for (who, st, _), t, l in zip(people, b["times"], b["limits"]):
        print(f"    {who} ({st:<7}) 行き {t:>3}分   帰宅リミット {fmt(l)}   滞在できる {l-(DEPART+t)}分")
    return a, b


run(PEOPLE_RAIL, "変種1: 全員が駅の近くに住んでいる")
run(PEOPLE_BUS, "変種2: A さんと E さんは駅から路線バス")
