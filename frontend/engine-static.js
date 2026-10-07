/* GitHub Pages 用: 先に計算してある結果を読んで、順位づけだけブラウザでやる版。
   時刻表は配っていない（ライセンスの都合）ので、ここで経路探索はしない。 */
(function(){
const D = "data/";
let META = null;   // この即時関数の中だけの変数（画面側の META とは別）
const cache = {};
const get = (p) => (cache[p] ||= fetch(D + p).then(r => {
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
  return {id, limit:home.limit, travel:home.travel, route:get(`route/${id}.json`)};
}

/* 区間 [路線, 乗る駅, 降りる駅] を、路線の駅順から駅の並びに戻す */
function expand(leg){
  const [rw, a, b] = leg;
  if (rw < 0) return {kind:"walk", line:"徒歩", rw:-1, a, b, nodes:[a, b]};
  const rail = META.rails[rw], o = rail.o;
  const i = o.indexOf(a), j = o.indexOf(b);
  let nodes = [a, b];
  if (i >= 0 && j >= 0) nodes = i <= j ? o.slice(i, j + 1) : o.slice(j, i + 1).reverse();
  return {kind:"train", line:rail.t, rw, a, b, nodes};
}
const stop = n => ({name:META.byId[n].n, lat:META.byId[n].lat, lon:META.byId[n].lon, time:null});

const API = {
  async meta(){
    META = await get("meta.json");
    META.shapes = await get("rail_shapes.json").catch(() => null);
    META.byId = Object.fromEntries(META.stations.map(s => [s.id, s]));
    return {
      stations: META.stations.map(s => ({n:s.n, b:s.b, l:s.l})),
      presets: META.presets, rails: META.rails, geo: META.stations, shapes: META.shapes,
      acquired: META.acquired, contact: META.contact, built: META.built,
    };
  },

  async search({people, depart, min_bars, max_travel}){
    const rows = [];
    for (const p of people) rows.push(await rowOf(p));
    ROWS = rows;
    const all = [];
    META.stations.forEach((s, i) => {
      const limits = rows.map(r => r.limit[i]);
      const times  = rows.map(r => r.travel[String(depart)][i]);
      if (limits.some(v => v < 0) || times.some(v => v < 0)) return;
      const stay = limits.map((l, k) => l - (depart + times[k]));
      if (Math.min(...stay) <= 0) return;
      all.push({id:s.id, name:s.n, bars:s.b, median_m:s.m, lines:s.l, lat:s.lat, lon:s.lon,
                times, limits, stay, min_stay:Math.min(...stay), min_limit:Math.min(...limits),
                sum:times.reduce((a,b)=>a+b,0), max:Math.max(...times),
                tight:limits.indexOf(Math.min(...limits))});
    });
    const ok = all.filter(r => r.bars >= min_bars && r.max <= max_travel)
                  .sort((a,b) => b.min_stay - a.min_stay).slice(0,5);
    return {
      people: people.map(p => ({name:p.name || p.station, where:`${p.station}駅`})),
      depart, candidates: ok, all,
      by_time: all.length ? all.reduce((a,b) => b.sum < a.sum ? b : a) : null,
      n_all: all.length, n_ok: ok.length,
    };
  },

  async detail({people, station, depart}){
    const cid = stationId(station);
    const bars = META.byId[cid].b ? await get(`bars/${cid}.json`) : [];
    const out = [];
    for (let k = 0; k < people.length; k++){
      const p = people[k], r = ROWS[k];
      const routes = await r.route;
      const lim = r.limit[cid];
      const legs = (routes[cid] || []).map(expand).map(l => ({...l, stops:l.nodes.map(stop)}));
      if (legs.length) legs[0].stops[0].time = hhmm(lim);
      out.push({name:p.name || p.station, home:p.station, bus:null,
                limit:lim, limit_s:hhmm(lim),
                home_lat:META.byId[r.id].lat, home_lon:META.byId[r.id].lon, legs});
    }
    const s = META.byId[cid];
    return {station:s.n, lat:s.lat, lon:s.lon, bars, routes:out,
            tight: out.reduce((best,x,i,arr) => x.limit < arr[best].limit ? i : best, 0)};
  },
};
let ROWS = [];
const hhmm = v => `${String(Math.floor(v/60)%24).padStart(2,"0")}:${String(v%60).padStart(2,"0")}`;
window.API = API;
})();
