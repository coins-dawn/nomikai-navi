/* 開発用: Python のサーバに計算させる版。 */
const API = {
  async meta(){
    const m = await (await fetch("/api/meta")).json();
    m.presets = [19,20].map(h=>h*60);
    Object.assign(m, await fetch("site.json").then(r=>r.ok?r.json():{}).catch(()=>({})));
    Object.assign(m, await fetch("/api/geo").then(r=>r.json()));
    m.contact = {contact_label:m.contact_label, contact_url:m.contact_url};
    return m;
  },
  search: p => fetch("/api/search",{method:"POST",body:JSON.stringify(p)}).then(r=>r.json()),
  detail: p => fetch("/api/detail",{method:"POST",body:JSON.stringify(p)}).then(r=>r.json()),
};
