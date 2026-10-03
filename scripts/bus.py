#!/usr/bin/env python3
"""バス GTFS から「駅の停留所を何時に出る便が自宅の停留所に行く最終便か」を求める。

駅の終電に間に合っても、そこから乗る最終バスが先に終わっていれば家には帰れない。
この案の「帰宅リミット」は、鉄道ではなくここで決まることが多い。
"""
import csv
from collections import defaultdict
from pathlib import Path

GTFS_ROOT = Path(__file__).resolve().parents[2] / "data-exploration" / "data" / "gtfs"


def _read(base, name):
    return csv.DictReader((base / name).open(encoding="utf-8-sig"))


def last_bus(feed, station_stop, home_stop):
    """(駅の停留所の最終発車時刻[分], 所要[分]) を返す。見つからなければ None。"""
    base = GTFS_ROOT / feed / "gtfs"
    stops = {r["stop_id"]: r["stop_name"] for r in _read(base, "stops.txt")}
    weekday = {r["service_id"] for r in _read(base, "calendar.txt") if r["monday"] == "1"}
    trips = {r["trip_id"]: r["service_id"] for r in _read(base, "trips.txt")}
    seq = defaultdict(list)
    for r in _read(base, "stop_times.txt"):
        if trips.get(r["trip_id"]) not in weekday:
            continue
        h, m, _ = r["departure_time"].split(":")
        seq[r["trip_id"]].append((int(r["stop_sequence"]), stops[r["stop_id"]], int(h) * 60 + int(m)))
    best = None
    for v in seq.values():
        v.sort()
        idx = [i for i, (_, n, _) in enumerate(v) if n == station_stop]
        if not idx:
            continue
        i = idx[0]
        t0 = v[i][2]
        for _, n, t in v[i + 1:]:
            if n == home_stop and (best is None or t0 > best[0]):
                best = (t0, t - t0)
    return best
