/* GitHub Pages 用: 先に計算してある結果を読んで、順位づけだけブラウザでやる版。
   時刻表は配っていない（ライセンスの都合）ので、ここで経路探索はしない。 */
(function(){
const D = "data/";
let META = null;   // この即時関数の中だけの変数（画面側の META とは別）
const cache = {};
const get = async (p) => (cache[p] ??= fetch(D + p).then(r => {
  if (!r.ok) throw new Error(p + " が読めません");
  return r.json();
}));

function stationId(name){
  const s = META.stations.find(x => x.n === name);
  if (!s) throw new Error("知らない駅です: " + name);
  return s.id;
}

async function rowOf(p){
  const id = stationId(p.station);
  const home = await get(`home/${id}.json`);
  if (p.bus){
    const bus = await get(`bus/${id}.json`);
    const lim = bus.limits[String(p.bus.last)];
    if (!lim) throw new Error("このバス停の計算結果がありません");
    return {id, key:`b${id}_${p.bus.last}`, limit:lim, travel:home.travel};
  }
  return {id, key:String(id), limit:home.limit, travel:home.travel};
}

const API = {
  async meta(){
    META = await get("meta.json");
    const byId = Object.fromEntries(META.stations.map(s => [s.id, s]));
    META.byId = byId;
    return {
      stations: META.stations.map(s => ({n:s.n, b:s.b, l:s.l})),
      bus_stations: META.bus_stations.map(i => byId[i].n),
      presets: META.presets,
    };
  },

  async busstops(name){
    let id; try { id = stationId(name); } catch { return []; }
    try { return (await get(`bus/${id}.json`)).stops; } catch { return []; }
  },

  async search({people, depart, min_bars, max_travel}){
    const rows = [];
    for (const p of people) rows.push(await rowOf(p));
    const out = [];
    META.cands.forEach((cid, i) => {
      const limits = rows.map(r => r.limit[i]);
      const times  = rows.map(r => r.travel[String(depart)][i]);
      if (limits.some(v => v < 0) || times.some(v => v < 0)) return;
      const stay = limits.map((l, k) => l - (depart + times[k]));
      if (Math.min(...stay) <= 0) return;
      const s = META.byId[cid];
      out.push({name:s.n, bars:s.b, median_m:s.m, lines:s.l, lat:s.lat, lon:s.lon,
                times, limits, stay, min_stay:Math.min(...stay), min_limit:Math.min(...limits),
                sum:times.reduce((a,b)=>a+b,0), max:Math.max(...times),
                tight:limits.indexOf(Math.min(...limits))});
    });
    const ok = out.filter(r => r.bars >= min_bars && r.max <= max_travel)
                  .sort((a,b) => b.min_stay - a.min_stay).slice(0,5);
    return {
      people: people.map((p,i) => ({name:p.name || p.station,
        where: p.bus ? `${p.station}駅 →バス ${p.bus.stop}（最終 ${hhmm(p.bus.last)}）` : `${p.station}駅`})),
      depart, candidates: ok,
      by_time: out.length ? out.reduce((a,b) => b.sum < a.sum ? b : a) : null,
      n_all: out.length, n_ok: ok.length,
    };
  },

  async detail({people, station, depart}){
    const cid = stationId(station);
    const [routes, bars] = await Promise.all([get(`route/${cid}.json`), get(`bars/${cid}.json`)]);
    const out = [];
    for (const p of people){
      const r = await rowOf(p);
      const i = META.cands.indexOf(cid);
      const lim = r.limit[i];
      let legs = (routes[r.key] || []).map(a => ({
        kind: META.lines[a[0]] === "徒歩" ? "walk" : "train",
        line: META.lines[a[0]],
        stops: a.slice(1).map(n => ({name:META.byId[n].n, lat:META.byId[n].lat, lon:META.byId[n].lon, time:null})),
      }));
      if (legs.length) legs[0].stops[0].time = hhmm(lim);
      if (legs.length && p.bus && p.bus.line){
        const L = p.bus.line;
        legs = legs.concat([{kind:"bus", line:`バス ${p.bus.stop} 行`, shape:L,
          stops:[{name:p.station+"駅", lat:L[0][0], lon:L[0][1], time:hhmm(p.bus.last)},
                 {name:p.bus.stop, lat:L[L.length-1][0], lon:L[L.length-1][1], time:hhmm(p.bus.last+p.bus.ride)}]}]);
      }
      out.push({name:p.name || p.station, home:p.station, bus:p.bus ? p.bus.stop : null,
                limit:lim, limit_s:hhmm(lim),
                home_lat:META.byId[r.id].lat, home_lon:META.byId[r.id].lon, legs});
    }
    const s = META.byId[cid];
    return {station:s.n, lat:s.lat, lon:s.lon, bars, routes:out,
            tight: out.reduce((best,x,i,arr) => x.limit < arr[best].limit ? i : best, 0)};
  },
};
const hhmm = v => `${String(Math.floor(v/60)%24).padStart(2,"0")}:${String(v%60).padStart(2,"0")}`;

window.API = API;
})();
