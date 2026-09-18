"""El informe HTML: una sola pagina oscura, sin internet, que se regenera sola.

Todo va embebido (datos, estilos y scripts) para que el archivo funcione con
doble clic, sin servidor y sin conexion.

Se organiza en tres bloques fijos, siempre en el mismo orden:

    1. Resumen    - como estan las cosas ahora
    2. Actividad  - que ha ido cambiando, lo mas reciente primero
    3. Detalle    - las listas completas, plegadas

Dentro de cada uno todo se alinea a la misma rejilla, para que la vista no se
desordene por mucho que varien los nombres.
"""

from __future__ import annotations

import json
from typing import Any

TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StillFriends</title>
<style>
/* Oscuro siempre, a proposito: no se sigue el tema del sistema. */
:root {
  color-scheme: dark;
  --bg: #0a0c10; --card: #131720; --card2: #1a1f2a; --ink: #e9ecf1; --dim: #7e8796;
  --line: #222835; --accent: #a78bfa;
  --up: #4ade80; --up-bg: #11291c; --down: #f87171; --down-bg: #2c1518;
  --warn: #fbbf24; --warn-bg: #2b2413;
  --r: 12px;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  padding: 0 20px 80px;
}
.wrap { max-width: 920px; margin: 0 auto; }

/* ---------- cabecera ---------- */
header { padding: 34px 0 0; }
h1 { margin: 0; font-size: 25px; letter-spacing: -.02em; }
h1 span { color: var(--accent); }
.sub { color: var(--dim); font-size: 13px; margin-top: 5px; }
nav { display: flex; gap: 8px; flex-wrap: wrap; margin: 22px 0 0; }
nav button {
  font: inherit; font-size: 14px; cursor: pointer; padding: 7px 15px; border-radius: 999px;
  border: 1px solid var(--line); background: var(--card); color: var(--ink);
}
nav button:hover { border-color: var(--accent); }
nav button[aria-selected="true"] {
  background: var(--accent); color: #12151c; border-color: var(--accent); font-weight: 600;
}

/* ---------- titulos de bloque ---------- */
.bloque { margin-top: 38px; }
.bloque > h2 {
  font-size: 12px; text-transform: uppercase; letter-spacing: .09em; color: var(--dim);
  margin: 0 0 14px; padding-bottom: 9px; border-bottom: 1px solid var(--line);
}

/* ---------- 1. resumen ---------- */
.cards { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: var(--r); padding: 15px 17px; }
.card .k { color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
.card .n { font-size: 32px; font-weight: 650; letter-spacing: -.03em; margin: 3px 0 2px;
           font-variant-numeric: tabular-nums; }
.card.ojo { border-color: #3a2f12; }
.card.ojo .n { color: var(--warn); }
.delta { font-size: 13px; font-weight: 600; }
.delta.up { color: var(--up); } .delta.down { color: var(--down); } .delta.flat { color: var(--dim); }

.tools { margin: 14px 0 0; }
input[type=search] {
  font: inherit; width: 100%; padding: 10px 14px; border-radius: 10px;
  border: 1px solid var(--line); background: var(--card); color: var(--ink);
}
input[type=search]:focus { outline: none; border-color: var(--accent); }
input[type=search]::placeholder { color: var(--dim); }

/* ---------- 2. actividad ---------- */
.pase {
  background: var(--card); border: 1px solid var(--line); border-radius: var(--r);
  padding: 15px 17px; margin-bottom: 12px;
}
.pase.ahora { border-color: #35306b; }
.pase > .cab {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  padding-bottom: 12px; border-bottom: 1px solid var(--line);
}
.pase .cuando { font-weight: 600; font-size: 14px; }
.pase .desde { color: var(--dim); font-size: 12px; margin-right: auto; }
.chip {
  font-size: 12px; padding: 3px 10px; border-radius: 999px;
  background: var(--card2); color: var(--dim); white-space: nowrap;
}
.chip b { color: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
.chip .up { color: var(--up); } .chip .down { color: var(--down); }
.pase.ahora .cuando::before {
  content: ''; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent); margin-right: 8px; vertical-align: middle;
}
.grupo { margin-top: 14px; }
.grupo > h3 {
  font-size: 13px; font-weight: 600; margin: 0 0 7px;
  display: flex; align-items: center; gap: 8px;
}
.cuenta { font-size: 11px; padding: 1px 8px; border-radius: 999px; font-weight: 700; }
.cuenta.up { background: var(--up-bg); color: var(--up); }
.cuenta.down { background: var(--down-bg); color: var(--down); }
.cuenta.warn { background: var(--warn-bg); color: var(--warn); }
.quieto { color: var(--dim); font-size: 13px; margin-top: 12px; }

/* ---------- filas: todo sobre la misma rejilla ---------- */
.list {
  background: var(--bg); border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
}
.row {
  display: grid; grid-template-columns: 14px minmax(0, 1fr) auto;
  gap: 10px; align-items: center; padding: 8px 13px; border-top: 1px solid var(--line);
}
.row:first-child { border-top: 0; }
.row .mark { font-weight: 700; text-align: center; }
.mark.up { color: var(--up); } .mark.down { color: var(--down); }
.mark.warn { color: var(--warn); } .mark.flat { color: var(--dim); }
.quien { min-width: 0; }
.quien .nom { font-weight: 550; }
.quien a { color: var(--dim); text-decoration: none; font-size: 13px; margin-left: 7px; }
.quien a:hover { color: var(--accent); text-decoration: underline; }
.motivo {
  font-size: 12px; padding: 2px 9px; border-radius: 999px; white-space: nowrap;
  background: var(--warn-bg); color: var(--warn);
}
.motivo.viva { background: var(--card2); color: var(--dim); }
.empty { padding: 14px; color: var(--dim); font-size: 13px; }

/* ---------- 3. detalle ---------- */
details { background: var(--card); border: 1px solid var(--line); border-radius: var(--r);
          margin-bottom: 10px; }
details > summary {
  cursor: pointer; color: var(--ink); font-size: 14px; padding: 12px 17px; list-style-position: inside;
}
details > summary:hover { color: var(--accent); }
details[open] > summary { border-bottom: 1px solid var(--line); }
details .list { border: 0; border-radius: 0; background: transparent; }
.grupo details { background: transparent; border: 0; margin: 0; }
.grupo details > summary { padding: 7px 0; font-size: 13px; color: var(--dim); }
.grupo details[open] > summary { border-bottom: 0; }

.hidden { display: none !important; }
footer { color: var(--dim); font-size: 12px; margin-top: 46px; text-align: center; }

@media (max-width: 560px) {
  body { padding: 0 14px 64px; }
  .row { grid-template-columns: 14px minmax(0, 1fr); row-gap: 3px; }
  .motivo { grid-column: 2; justify-self: start; }
  .quien a { display: block; margin: 2px 0 0; }
}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Still<span>Friends</span></h1>
    <div class="sub" id="sub"></div>
    <nav id="tabs"></nav>
  </header>
  <main id="main"></main>
  <footer>Generado por StillFriends. Los datos viven en <code>data/</code>.</footer>
</div>
<script id="payload" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('payload').textContent);

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => (
  {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const fechaLarga = iso => iso ? new Date(iso).toLocaleString('es',
  {day:'numeric', month:'long', year:'numeric', hour:'2-digit', minute:'2-digit'}) : '';

function haceCuanto(iso) {
  const dias = Math.floor((Date.now() - new Date(iso)) / 86400000);
  if (dias <= 0) return 'hoy';
  if (dias === 1) return 'ayer';
  if (dias < 30) return `hace ${dias} dias`;
  const meses = Math.floor(dias / 30);
  return meses < 12 ? `hace ${meses} ${meses === 1 ? 'mes' : 'meses'}`
                    : `hace ${Math.floor(meses / 12)} anos`;
}

const signo = d => (d > 0 ? '+' : '') + d;

const MOTIVOS = {
  desaparecida: ['cuenta borrada, inactiva o te bloqueo', ''],
  viva: ['la dejaste de seguir', 'viva'],
};

// Que significa un alta y una baja en cada lista: no es lo mismo perder un
// seguidor que dejar de seguir a alguien.
const etiquetas = (kind, noun) => kind === 'following'
  ? ['Empezaste a seguir', 'Dejaste de seguir']
  : [`Nuevos en ${noun}`, `Se fueron de ${noun}`];

function filas(gente, marca, clase) {
  if (!gente.length) return '<div class="empty">Nadie por aqui.</div>';
  return gente.map(p => {
    const m = MOTIVOS[p.status];
    return `<div class="row" data-buscar="${esc((p.name + ' ' + p.handle).toLowerCase())}">
      <span class="mark ${clase}">${marca}</span>
      <span class="quien"><span class="nom">${esc(p.name || p.handle || p.uid)}</span>${
        p.handle ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">@${esc(p.handle)}</a>` : ''}</span>
      ${m ? `<span class="motivo ${m[1]}">${esc(m[0])}</span>` : '<span></span>'}
    </div>`;
  }).join('');
}

// Las listas largas se pliegan para que la actividad siga siendo legible.
function grupo(titulo, gente, clase, marca) {
  if (!gente.length) return '';
  const cuerpo = `<div class="list">${filas(gente, marca, clase)}</div>`;
  const cabecera = `<h3>${esc(titulo)} <span class="cuenta ${clase}">${gente.length}</span></h3>`;
  return `<div class="grupo">${cabecera}${gente.length <= 8 ? cuerpo
    : `<details><summary>Ver los ${gente.length}</summary>${cuerpo}</details>`}</div>`;
}

function pinta(p) {
  const tarjeta = (k, n, extra, clase) => `
    <div class="card${clase ? ' ' + clase : ''}">
      <div class="k">${esc(k)}</div><div class="n">${n}</div>${extra}
    </div>`;

  const dl = (total, previo) => previo === null || previo === undefined
    ? '<span class="delta flat">primera pasada</span>'
    : `<span class="delta ${total - previo > 0 ? 'up' : total - previo < 0 ? 'down' : 'flat'}">${
        signo(total - previo)}</span>`;

  // ---- 1. resumen ----
  let html = '<section class="bloque"><h2>Resumen</h2><div class="cards">';
  html += p.lists.map(l => tarjeta(l.noun, l.total, dl(l.total, l.previous_total))).join('');
  if (p.unrequited) html += tarjeta('no te siguen', p.unrequited.length,
    `<span class="delta flat">de ${p.following_total} seguidos</span>`, 'ojo');
  html += `</div><div class="tools"><input type="search" id="buscar"
    placeholder="Filtrar por nombre o usuario en toda la pagina..."></div></section>`;

  // ---- 2. actividad ----
  html += '<section class="bloque"><h2>Actividad</h2>';
  html += p.timeline.length ? p.timeline.map((pase, i) => {
    const chips = pase.changes.map(c => {
      const d = c.previous_total == null ? null : c.total - c.previous_total;
      return `<span class="chip">${esc(c.noun)} <b>${c.total}</b>${
        d ? ` <span class="${d > 0 ? 'up' : 'down'}">${signo(d)}</span>` : ''}</span>`;
    }).join('');

    let cuerpo = '', hubo = false;
    for (const c of pase.changes) {
      const [alta, baja] = etiquetas(c.kind, c.noun);
      if (c.added.length || c.removed.length) hubo = true;
      cuerpo += grupo(alta, c.added, 'up', '+') + grupo(baja, c.removed, 'down', '-');
    }
    if (!hubo) cuerpo = `<div class="quieto">Sin cambios${
      pase.changes.some(c => c.previous_total == null) ? ': punto de partida.' : '.'}</div>`;

    return `<article class="pase${i === 0 ? ' ahora' : ''}">
      <div class="cab">
        <span class="cuando">${esc(fechaLarga(pase.at))}</span>
        <span class="desde">${i === 0 ? 'ultima revision' : esc(haceCuanto(pase.at))}</span>
        ${chips}
      </div>${cuerpo}</article>`;
  }).join('') : '<div class="empty">Todavia no hay pasadas guardadas.</div>';
  html += '</section>';

  // ---- 3. detalle ----
  html += '<section class="bloque"><h2>Detalle</h2>';
  if (p.unrequited) {
    html += `<details><summary>No te siguen de vuelta (${p.unrequited.length})</summary>
      <div class="list">${filas(p.unrequited, '!', 'warn')}</div></details>`;
  }
  for (const l of p.lists) {
    html += `<details><summary>Todos los ${l.noun} (${l.total})</summary>
      <div class="list">${filas(l.accounts, '', 'flat')}</div></details>`;
  }
  html += '</section>';

  document.getElementById('main').innerHTML = html;

  const buscar = document.getElementById('buscar');
  buscar.addEventListener('input', () => {
    const q = buscar.value.trim().toLowerCase();
    // Al filtrar se abre todo lo plegado, o los resultados quedarian escondidos.
    if (q) document.querySelectorAll('details').forEach(d => d.open = true);
    document.querySelectorAll('.row[data-buscar]').forEach(r =>
      r.classList.toggle('hidden', q && !r.dataset.buscar.includes(q)));
  });
}

document.getElementById('sub').textContent = 'Ultima revision: ' + fechaLarga(DATA.generated);

const tabs = document.getElementById('tabs');
DATA.platforms.forEach((p, i) => {
  const b = document.createElement('button');
  b.textContent = p.emoji + '  ' + p.label;
  b.setAttribute('aria-selected', i === 0);
  b.onclick = () => {
    [...tabs.children].forEach(x => x.setAttribute('aria-selected', x === b));
    pinta(p);
  };
  tabs.appendChild(b);
});
if (DATA.platforms.length) pinta(DATA.platforms[0]);
else document.getElementById('main').innerHTML =
  '<div class="empty">Todavia no hay datos. Corre <code>stillfriends check</code>.</div>';
</script>
</body>
</html>
"""


def build(payload: dict[str, Any]) -> str:
    """Embed the data in the page. `</script>` inside JSON would end the tag."""
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", blob)
