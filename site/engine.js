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
  return {id, limit:home.limit, travel:home.travel, back:home.back, back_x:home.back_x, back_depart:home.back_depart,
          route:() => get(`route/${id}.json`)};
}

/* 区間 [路線, 乗る駅, 降りる駅] を、路線の駅順から駅の並びに戻す */
function expand(leg){
  const [rw, a, b] = leg;
  if (rw < 0) return {kind:"walk", line:"徒歩", rw:-1, a, b, nodes:[a, b]};
  const rail = META.rails[rw], o = rail.o;
  const i = o.indexOf(a), j = o.indexOf(b);
  let nodes = [a, b];
  if (i >= 0 && j >= 0) nodes = i <= j ? o.slice(i, j + 1) : o.slice(j, i + 1).reverse();
  // 環状線（山手線）は、両端（品川・大崎）をまたいだほうが近ければそちら回りにする
  if (i >= 0 && j >= 0 && LOOP.has(rw) && Math.abs(i - j) > o.length / 2)
    nodes = i < j ? [...o.slice(0, i + 1).reverse(), ...o.slice(j).reverse()] : [...o.slice(i), ...o.slice(0, j + 1)];
  return {kind:"train", line:rail.t, rw, a, b, nodes};
}
const LOOP = new Set();   // 環状線の路線番号（fare.json の loops。読み込むまでは空）
const stop = n => ({name:META.byId[n].n, lat:META.byId[n].lat, lon:META.byId[n].lon, time:null});

const API = {
  async meta(){
    META = await get("meta.json");
    META.shapes = await get("rail_shapes.json").catch(() => null);
    META.byId = Object.fromEntries(META.stations.map(s => [s.id, s]));
    await fareData().catch(() => null);
    return {
      stations: META.stations.map(s => ({n:s.n, b:s.b, l:s.l})),
      presets: META.presets, rails: META.rails, geo: META.stations, shapes: META.shapes,
      acquired: META.acquired, contact: META.contact, built: META.built,
      loops: [...LOOP],
    };
  },

  async search({people, depart, min_bars, max_travel, sort = "cost"}){
    // 自宅の行（終電・帰りの所要時間）と、行きの出発地の行（会社から来る人は会社の駅）
    const rows = [], from = [];
    for (const p of people){
      const r = await rowOf(p);
      rows.push(r);
      from.push(p.from === "office" ? await rowOf({station:p.office}) : r);
    }
    ROWS = rows;
    // 交通費: 全候補への行きの経路と、全候補からの帰りの経路を読んで、定期の区間の外の運賃を足す
    const fd = await fareData();
    const passes = await Promise.all(people.map(p => passOf(p)));
    const goPaths = await Promise.all(people.map((p, k) => get(`go/${from[k].id}.json`)));
    const backPaths = await Promise.all(rows.map(r => get(`backto/${r.id}.json`)));
    const all = [];
    META.stations.forEach((s, i) => {
      const limits = rows.map(r => r.limit[i]);
      const times  = from.map(r => r.travel[String(depart)][i]);
      if (limits.some(v => v < 0) || times.some(v => v < 0)) return;
      const stay = limits.map((l, k) => l - (depart + times[k]));
      if (Math.min(...stay) <= 0) return;
      const back = rows.map(r => r.back ? r.back[i] : -1);
      const cost = back.some(v => v < 0) ? null
        : times.reduce((a,b)=>a+b,0) + back.reduce((a,b)=>a+b,0);
      // 帰りの乗り換え回数（経路が組めなかった人は数えようがないので多めに 9 とする）
      const xs = rows.map(r => r.back_x && r.back_x[i] >= 0 ? r.back_x[i] : 9);
      // 行き＋帰りの運賃（経路が無い人がいれば分からない＝null）
      const fares = people.map((p, k) => {
        const g = from[k].id === s.id ? [] : goPaths[k][s.id];
        const b = rows[k].id === s.id ? [] : backPaths[k][s.id];
        if (!g || !b) return null;
        return tripFare(g.map(expand), passes[k]).yen + tripFare(b.map(expand), passes[k]).yen;
      });
      const fare = fares.some(v => v == null) ? null : fares.reduce((a,b)=>a+b,0);
      all.push({id:s.id, name:s.n, bars:s.b, median_m:s.m, lines:s.l, lat:s.lat, lon:s.lon,
                times, back, cost, limits, stay, xs, fares, fare, max_x:Math.max(...xs), sum_x:xs.reduce((a,b)=>a+b,0), min_stay:Math.min(...stay), min_limit:Math.min(...limits),
                sum:times.reduce((a,b)=>a+b,0), max:Math.max(...times),
                tight:limits.indexOf(Math.min(...limits))});
    });
    const pool = all.filter(r => r.bars >= min_bars && r.max <= max_travel && r.cost != null && (sort !== "fare" || r.fare != null));
    const ok = pool.slice().sort((a,b) => cmp(SORT_KEY[sort] || SORT_KEY.cost, a, b)).slice(0,5);
    return {
      people: people.map(p => ({name:p.name || p.station, home:p.station, from:p.from,
                                where: p.from === "office" ? `${p.office}駅（会社）` : `${p.station}駅（自宅）`})),
      depart, back_depart: rows[0].back_depart, sort, candidates: ok, all,
      // 比較用: 前の方式（いちばん早い人がいちばん長くいられる駅）
      by_stay: pool.length ? pool.reduce((a,b) => b.min_stay > a.min_stay ? b : a) : null,
      n_all: all.length, n_ok: ok.length,
    };
  },

  /* 自宅〜会社の通勤経路（定期の区間）。経由駅を入れると、そこを通る最速の経路にする */
  async commute({home, office, via}){
    await fareData();
    const p = await passOf({station:home, office, via});
    return p ? {text:p.text, minutes:p.minutes} : null;
  },

  async detail({people, station, depart}){
    const cid = stationId(station);
    const bars = META.byId[cid].b ? await get(`bars/${cid}.json`) : [];
    // 帰りは候補駅を 21:30 に出る経路（候補駅＝飲み屋 10 軒以上のときだけ用意してある）
    const back = await get(`back/${cid}.json`).catch(() => ({}));
    const legsOf = (list, pass) => {
      const legs = (list || []).map(expand), f = tripFare(legs, pass);
      return {fare:f, legs:legs.map((l, i) => ({...l, stops:l.nodes.map(stop), pass:f.legPass[i]}))};
    };
    await fareData();
    const out = [];
    for (let k = 0; k < people.length; k++){
      const p = people[k], r = ROWS[k], pass = await passOf(p);
      const oid = p.from === "office" ? stationId(p.office) : r.id;
      const go = oid === cid ? [] : (await get(`go/${oid}.json`))[cid];
      const lim = r.limit[cid];
      const g = legsOf(go, pass), b = legsOf(r.id === cid ? [] : back[r.id], pass);
      out.push({name:p.name || p.station, home:p.station, from:p.from,
                origin: p.from === "office" ? p.office : p.station,
                go: g.legs, back: b.legs, fare_go: g.fare, fare_back: b.fare, pass: pass && pass.text,
                limit:lim, limit_s:hhmm(lim),
                home_lat:META.byId[r.id].lat, home_lon:META.byId[r.id].lon});
    }
    const s = META.byId[cid];
    return {station:s.n, lat:s.lat, lon:s.lon, bars, routes:out,
            tight: out.reduce((best,x,i,arr) => x.limit < arr[best].limit ? i : best, 0)};
  },
};
let ROWS = [];

/* ---------- 交通費（定期の区間の外に出た分の運賃・IC・大人） ----------
   ODPT の駅間運賃表は配れない（基本ライセンス第8条4項(1)）ので、線路の長さから距離帯の運賃を当てる概算。
   段の境目は ODPT の運賃に合わせてある（scripts/build_fares.py）。JR は ODPT に運賃が無いので公表の賃率から出す */
let FD = null;
async function fareData(){
  if (FD) return FD;
  const f = await get("fare.json");
  f.pos = META.rails.map(r => new Map(r.o.map((n, i) => [n, i])));
  f.opOf = rw => rw >= 0 ? f.ops[f.rw_op[rw]] : null;
  // 通勤経路を探すための路線網: 駅 → [路線, 隣の駅, 分]
  f.adj = new Map();
  const add = (a, x) => { if (!f.adj.has(a)) f.adj.set(a, []); f.adj.get(a).push(x); };
  META.rails.forEach((r, rw) => r.o.forEach((n, i) => {
    if (i + 1 < r.o.length){ add(n, [rw, r.o[i+1], f.run[rw][i]]); add(r.o[i+1], [rw, n, f.run[rw][i]]); }
  }));
  f.foot.forEach(([a, b, c]) => { add(a, [-1, b, c]); add(b, [-1, a, c]); });
  f.loopKm = new Map();
  (f.loops || []).forEach(([rw, km, min]) => {
    const o = META.rails[rw].o, a = o[0], b = o[o.length - 1];
    LOOP.add(rw); f.loopKm.set(rw, km); add(a, [rw, b, min]); add(b, [rw, a, min]);
  });
  return FD = f;
}
/* JR東日本（幹線）の運賃。2026-03-14 改定後: 10km までは定額、11km からは 16.96円/km を距離帯の中ほどの km に掛ける。
   IC は 1 円単位（税込みの端数は切り上げ） */
function jrFare(km){
  const k = Math.max(1, Math.ceil(km - 1e-9));
  if (k <= 3) return 155;
  if (k <= 6) return 199;
  if (k <= 10) return 209;
  const [w, lo] = k <= 50 ? [5, 11] : k <= 100 ? [10, 51] : [20, 101];
  const a = lo + Math.floor((k - lo) / w) * w, mid = Math.floor((a + a + w - 1) / 2);
  let base = mid * 16.96;
  base = k <= 100 ? Math.ceil(base / 10) * 10 : Math.round(base / 100) * 100;
  return Math.ceil(base * 1.1 - 1e-9);
}
function opFare(op, km){
  if (op.jr) return jrFare(km);
  for (const [upto, y] of op.bands) if (km <= upto) return y;
  return op.bands[op.bands.length - 1][1];
}
/* 区間を「隣り合う駅の間」に分ける。[事業者, 駅, 駅, km] の並び */
function segsOf(leg){
  const f = FD, out = [];
  if (leg.rw < 0) return out;
  const pos = f.pos[leg.rw], op = f.opOf(leg.rw);
  for (let i = 0; i + 1 < leg.nodes.length; i++){
    const a = leg.nodes[i], b = leg.nodes[i+1], pa = pos.get(a), pb = pos.get(b);
    let km = pa != null && pb != null && Math.abs(pa - pb) === 1 ? f.seg_km[leg.rw][Math.min(pa, pb)]
      : pa != null && pb != null && f.loopKm.has(leg.rw) && Math.abs(pa - pb) === pos.size - 1 ? f.loopKm.get(leg.rw) : null;
    if (km == null){   // 路線の駅順で隣でない（分岐など）ときは直線距離の 1.2 倍
      const A = META.byId[a], B = META.byId[b];
      km = Math.hypot((A.lat - B.lat) * 111, (A.lon - B.lon) * 91) * 1.2;
    }
    out.push([op, a, b, km * (f.rw_mult ? f.rw_mult[leg.rw] : 1)]);
  }
  return out;
}
/* 経路の運賃。事業者ごとにひとまとまり（同じ事業者の乗り換えは通し）にして、
   定期の区間に入っていない駅間が続くところごとに、その距離の運賃を払う。
   定期の区間＝定期の経路のうち同じ事業者で続くひとまとまりに、駅間の両端の駅が両方とも入っていること */
function tripFare(legs, pass){
  const groups = [], legPass = legs.map(() => null);
  legs.forEach((l, i) => {
    if (l.rw < 0) return;
    const segs = segsOf(l), op = segs.length ? segs[0][0] : FD.opOf(l.rw);
    const cov = segs.map(([o, a, b]) => !!pass && pass.runs.some(r => r.op === o && r.nodes.has(a) && r.nodes.has(b)));
    legPass[i] = cov.every(Boolean) ? "all" : cov.some(Boolean) ? "part" : "none";
    const last = groups[groups.length - 1];
    const g = last && last.op === op && last.end === i - 1 - (legs[i-1] && legs[i-1].rw < 0 ? 1 : 0) ? last : null;
    const items = segs.map((s, k) => ({km:s[3], cov:cov[k]}));
    if (g){ g.items.push(...items); g.end = i; } else groups.push({op, items, end:i});
  });
  let yen = 0;
  const parts = groups.map(g => {
    let y = 0, run = 0;
    const flush = () => { if (run > 0) y += opFare(g.op, run); run = 0; };
    g.items.forEach(it => { if (it.cov) flush(); else run += it.km; });
    flush();
    yen += y;
    return {op:g.op.name, yen:y};
  });
  // 東京メトロ⇔都営地下鉄の乗り継ぎ割引（IC 70円）
  for (let i = 0; i + 1 < groups.length; i++){
    const a = groups[i].op.id, b = groups[i+1].op.id;
    if (parts[i].yen > 0 && parts[i+1].yen > 0 && ((a === "TokyoMetro" && b === "Toei") || (a === "Toei" && b === "TokyoMetro"))) yen -= 70;
  }
  return {yen, parts, legPass};
}
/* 自宅〜会社の最速経路（路線網の上で、駅間の所要時間の中央値と乗り換え 5 分で探す）。経由駅があればそこを通す */
const PASS_CACHE = {};
async function passOf(p){
  if (!p.office || !p.station) return null;
  const key = [p.station, p.office, p.via || ""].join("|");
  if (key in PASS_CACHE) return PASS_CACHE[key];
  const ids = [p.station, ...(p.via ? [p.via] : []), p.office].map(n => { try { return stationId(n); } catch(e){ return null; } });
  if (ids.some(x => x == null) || ids[0] === ids[ids.length-1]) return PASS_CACHE[key] = null;
  let legs = [], minutes = 0;
  for (let i = 0; i + 1 < ids.length; i++){
    const r = fastest(ids[i], ids[i+1]);
    if (!r) return PASS_CACHE[key] = null;
    legs = legs.concat(r.legs); minutes += r.minutes;
  }
  const ex = legs.map(expand), runs = [];
  ex.forEach(l => {
    if (l.rw < 0) return;
    const op = FD.opOf(l.rw), last = runs[runs.length - 1];
    if (last && last.op === op) l.nodes.forEach(n => last.nodes.add(n));
    else runs.push({op, nodes:new Set(l.nodes)});
  });
  const text = [META.byId[ids[0]].n, ...ex.filter(l => l.rw >= 0).flatMap(l => [l.line, META.byId[l.b].n])].join("→");
  return PASS_CACHE[key] = {runs, text, minutes:Math.round(minutes)};
}
function fastest(src, dst){
  const T = FD.transfer, K = (n, rw) => n * 128 + rw + 1;
  const dist = new Map([[K(src, -1), 0]]), prev = new Map(), heap = [[0, src, -1]];
  const push = x => { heap.push(x); let i = heap.length - 1; while (i){ const j = (i - 1) >> 1; if (heap[j][0] <= heap[i][0]) break; [heap[i], heap[j]] = [heap[j], heap[i]]; i = j; } };
  const pop = () => { const top = heap[0], x = heap.pop(); if (heap.length){ heap[0] = x; let i = 0; for(;;){ let m = i; const l = 2*i+1, r = l+1;
    if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[i], heap[m]] = [heap[m], heap[i]]; i = m; } } return top; };
  let end = null;
  while (heap.length){
    const [d, n, rw] = pop();
    if (d > dist.get(K(n, rw))) continue;
    if (n === dst){ end = [n, rw, d]; break; }
    for (const [r2, m, c] of FD.adj.get(n) || []){
      const nd = d + c + (r2 >= 0 && rw >= 0 && r2 !== rw ? T : 0);
      const nr = r2;
      if (nd < (dist.get(K(m, nr)) ?? 1e18)){ dist.set(K(m, nr), nd); prev.set(K(m, nr), [n, rw]); push([nd, m, nr]); }
    }
  }
  if (!end) return null;
  // たどり直して [路線, 乗る駅, 降りる駅] にまとめる
  const st = []; let cur = [end[0], end[1]];
  while (cur){ st.push(cur); cur = prev.get(K(cur[0], cur[1])); }
  st.reverse();
  const legs = [];
  for (let i = 1; i < st.length; i++){
    const [n, rw] = st[i], a = st[i-1][0], last = legs[legs.length - 1];
    if (last && last[0] === rw && rw >= 0) last[2] = n; else legs.push([rw, a, n]);
  }
  return {legs, minutes:end[2]};
}
/* 何を優先して駅を選ぶか。どれも同じ順位なら移動時間の合計が少ない駅を先に（server.py の SORT_KEY と同じ） */
const SORT_KEY = {
  cost:   r => [r.cost],                      // 移動時間（行き＋帰り）の合計が少ない
  stay:   r => [-r.min_limit, r.cost],        // いちばん早い人の終電が遅い（＝その人が遅くまでいられる）
  simple: r => [r.max_x, r.sum_x, r.cost],    // 帰りの乗り換えが少ない（いちばん多い人の回数、次に合計）
  work:   r => [r.max, r.cost],               // いちばん遠い人の行きが短い（＝その人が遅くまで仕事できる）
  fare:   r => [r.fare ?? 1e9, r.cost],       // 全員の交通費（定期の区間の外の運賃）の合計が安い
};
const cmp = (key, a, b) => {
  const x = key(a), y = key(b);
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] - y[i];
  return 0;
};
const hhmm = v => `${String(Math.floor(v/60)%24).padStart(2,"0")}:${String(v%60).padStart(2,"0")}`;
window.API = API;
window.FARE_JR = jrFare;   // 確かめ用
})();
