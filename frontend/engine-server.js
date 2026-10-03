/* 開発用: Python のサーバに計算させる版。 */
const API = {
  async meta(){
    const m = await (await fetch("/api/meta")).json();
    m.presets = [19,20].map(h=>h*60);
    Object.assign(m, await fetch("site.json").then(r=>r.ok?r.json():{}).catch(()=>({})));
    return m;
  },
  busstops: st => fetch("/api/busstops?station="+encodeURIComponent(st)).then(r=>r.json()),
  search: p => fetch("/api/search",{method:"POST",body:JSON.stringify(p)}).then(r=>r.json()),
  detail: p => fetch("/api/detail",{method:"POST",body:JSON.stringify(p)}).then(r=>r.json()),
};
