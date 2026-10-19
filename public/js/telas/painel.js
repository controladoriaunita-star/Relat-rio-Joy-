// Aba Painel: realizado x projetado x EVE e linha do tempo mensal (jan/2024 a dez/2030).
import { api, carregando, ehNumero, esc, fmt, focarMesCorrente } from '../util.js';

// Ordem e estilo das linhas, seguindo a aba Painel da planilha.
const SECOES = [
  { titulo: 'Receitas', linhas: [25, 26, 27, 28, 29, 30, 32, 35, [36, 'total'], 38, [41, 'total']] },
  { titulo: 'Custos', linhas: [...range(43, 56), [59, 'total']] },
  { titulo: 'Despesas', linhas: [...range(61, 76), [79, 'total']] },
  { titulo: 'Resultado', linhas: [81, [83, 'total'], 85, 86, 87, 88, [93, 'grande'], [95, 'pct'], [99, 'pct'], 101] },
  { titulo: 'Investidor', linhas: [[105, 'total'], 106, 107, 108, 109] },
  { titulo: 'Holding', linhas: [[111, 'total'], 112, 113, 114, 115, 116] },
  { titulo: 'Caixa', linhas: [[119, 'grande']] },
];
const ROTULOS_TL = { 119: 'Saldo de caixa para consolidado', 122: 'Saldo de caixa acumulado final' };
let visao = 'consolidado';
let anoSelecionado = null;

function range(a, b) { return Array.from({ length: b - a + 1 }, (_, i) => a + i); }

function valor(v, pct = false) {
  if (v === '#VALUE!') return '<span class="badge b-error" title="Erro #VALOR! na planilha original">#VALOR!</span>';
  if (!ehNumero(v)) return '';
  return pct ? fmt.pct(v) : fmt.numero(v);
}

function verificacao(l) {
  const { FT, FU } = l.extras || {};
  if (!FT) return '<td></td>';
  const badge = (ok, rotulo) => `<span class="badge ${ok ? 'b-success' : 'b-warning'}" title="${rotulo}: linha do tempo ${ok ? 'confere' : 'difere'} da coluna">${ok ? 'OK' : 'Dif.'}</span>`;
  return `<td>${badge(FT === 'OK!', 'Realizado')} ${badge(FU === 'OK!', 'Projetado')}</td>`;
}

function tabelaConsolidado(dados) {
  const linhas = Object.fromEntries(dados.linhas.map((l) => [l.linha_excel, l]));
  const t = dados.titulos;
  let corpo = '';
  for (const secao of SECOES) {
    corpo += `<tr class="secao"><td class="first" colspan="9">${secao.titulo}</td></tr>`;
    for (const item of secao.linhas) {
      const [r, estilo] = Array.isArray(item) ? item : [item, ''];
      const l = linhas[r];
      if (!l) continue;
      const pct = estilo === 'pct';
      const alerta = ['custo', 'despesa'].includes(l.grupo) && ehNumero(l.AB) && l.AB > 1;
      corpo += `<tr class="${estilo === 'pct' ? '' : estilo}" title="Linha ${r} do Painel">
        <td class="first">${esc(l.rotulo || (r === 99 ? 'M T I R (a.m.)' : ''))}</td>
        <td>${valor(l.H, pct)}</td><td>${valor(l.L, pct)}</td><td>${valor(l.P, pct)}</td>
        <td>${valor(l.T, pct)}</td><td>${valor(l.X, pct)}</td><td>${valor(l.Y, true)}</td>
        <td class="${alerta ? 'alerta' : ''}">${valor(l.AB, true)}</td>${verificacao(l)}</tr>`;
    }
  }
  return `<div class="sheet"><table><thead><tr>
      <th class="first">Rubrica</th>
      <th><span class="letra">A</span>${esc(t.realizado)}</th>
      <th><span class="letra">B</span>Projetado (Mês)</th>
      <th><span class="letra">C</span>Projetado Total</th>
      <th><span class="letra">D = A + C</span>Total (Real. + Proj.)</th>
      <th><span class="letra">E</span>Previsto Total no EVE</th>
      <th><span class="letra">AV</span>% VGV</th>
      <th><span class="letra">F = D / E</span>Desvio</th>
      <th title="Conferência da planilha (colunas FT/FU)">Verificação</th>
    </tr></thead><tbody>${corpo}</tbody></table></div>`;
}

function tabelaLinhaDoTempo(dados) {
  const linhas = Object.fromEntries(dados.linhas.map((l) => [l.linha_excel, l]));
  const indices = dados.meses.map((m, i) => [m, i]).filter(([m]) => !anoSelecionado || m.startsWith(anoSelecionado));
  const corte = dados.datas.corte;
  const cab = indices.map(([m], j) => `<th class="${m === corte ? 'cur' : ''} ${m.endsWith('-01-31') && j ? 'ano-inicio' : ''}">${fmt.mes(m)}</th>`).join('');
  let corpo = '';
  for (const secao of [...SECOES, { titulo: 'Acumulados', linhas: [[122, 'total']] }]) {
    corpo += `<tr class="secao"><td class="first" colspan="${indices.length + 3}">${secao.titulo}</td></tr>`;
    for (const item of secao.linhas) {
      const [r, estilo] = Array.isArray(item) ? item : [item, ''];
      const l = linhas[r];
      if (!l || !l.tl.some((v) => v !== null)) continue;
      corpo += `<tr class="${estilo === 'pct' ? '' : estilo}"><td class="first">${esc(ROTULOS_TL[r] || l.rotulo || (r === 95 ? 'Saldo acumulado' : ''))}</td>
        ${indices.map(([m, i], j) => `<td class="${m === corte ? 'cur' : ''} ${m > dados.datas.mes_analise ? 'proj' : ''} ${m.endsWith('-01-31') && j ? 'ano-inicio' : ''}">${valor(l.tl[i])}</td>`).join('')}
        <td class="tot">${valor(l.extras?.FS)}</td><td class="tot">${valor(l.extras?.FV)}</td></tr>`;
    }
  }
  return `<div class="sheet" style="max-height:70vh"><table><thead><tr><th class="first">Rubrica</th>${cab}
    <th class="tot">Realizado</th><th class="tot">Projetado</th></tr></thead><tbody>${corpo}</tbody></table></div>
    <div class="legend"><span><i style="background:var(--cell-current)"></i>Mês de corte (realizado × projetado)</span>
      <span><i style="background:#fff;border-color:var(--color-primary)"></i><span style="color:var(--color-primary)">Valores em roxo</span>: meses futuros (projeção)</span></div>`;
}

/** Barras do saldo de caixa mensal + linha do saldo acumulado. */
function grafico(dados) {
  const linhas = Object.fromEntries(dados.linhas.map((l) => [l.linha_excel, l]));
  const mensal = linhas[93].tl.map((v) => v ?? 0);
  const acumulado = linhas[95].tl.map((v) => v ?? 0);
  const L = 960, A = 220, m = { e: 64, d: 16, t: 12, b: 28 };
  const maxAbs = Math.max(1, ...mensal.map(Math.abs), ...acumulado.map(Math.abs));
  const y = (v) => m.t + (A - m.t - m.b) / 2 - (v / maxAbs) * ((A - m.t - m.b) / 2);
  const passo = (L - m.e - m.d) / mensal.length;
  const barras = mensal.map((v, i) => {
    const y0 = y(0), y1 = y(v);
    return `<rect x="${(m.e + i * passo + 1).toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${(passo - 2).toFixed(1)}" height="${Math.max(Math.abs(y1 - y0), 0.5).toFixed(1)}" rx="1.5"><title>${fmt.mes(dados.meses[i])}: ${fmt.moeda(v)}</title></rect>`;
  }).join('');
  const pontos = acumulado.map((v, i) => `${(m.e + i * passo + passo / 2).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const anos = dados.meses.map((mm, i) => (mm.endsWith('-01-31') ? `<text x="${m.e + i * passo}" y="${A - 8}">${mm.slice(0, 4)}</text>` : '')).join('');
  const iCorte = dados.meses.indexOf(dados.datas.corte);
  return `<div class="card pad" style="margin-bottom:16px"><p class="sub">Saldo de caixa: mensal (barras) e acumulado (linha)</p>
    <svg viewBox="0 0 ${L} ${A}" width="100%" role="img" aria-label="Saldo de caixa mensal e acumulado">
      <line x1="${m.e}" x2="${L - m.d}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ink-200)"/>
      ${iCorte >= 0 ? `<rect x="${m.e + iCorte * passo}" y="${m.t}" width="${passo}" height="${A - m.t - m.b}" fill="var(--cell-current)"/>` : ''}
      <g fill="var(--chart-1)">${barras}</g>
      <polyline points="${pontos}" fill="none" stroke="var(--chart-2)" stroke-width="2"/>
      <g font-size="11" fill="var(--muted)" font-family="Inter">${anos}
        <text x="${m.e - 8}" y="${y(maxAbs) + 4}" text-anchor="end">${fmt.numero(maxAbs / 1e6)} mi</text>
        <text x="${m.e - 8}" y="${y(0) + 4}" text-anchor="end">0</text>
        <text x="${m.e - 8}" y="${y(-maxAbs) + 4}" text-anchor="end">-${fmt.numero(maxAbs / 1e6)} mi</text></g>
    </svg>
    <div class="legend"><span><i style="background:var(--chart-1);border:0"></i>Saldo de caixa do mês</span>
      <span><i style="background:var(--chart-2);border:0;height:3px;vertical-align:3px"></i>Acumulado</span></div></div>`;
}

export async function render(el, { dataBase }) {
  el.innerHTML = carregando(12);
  const dados = await api(`/api/painel?data=${dataBase}`);
  const linhas = Object.fromEntries(dados.linhas.map((l) => [l.linha_excel, l]));
  const anos = [...new Set(dados.meses.map((m) => m.slice(0, 4)))];
  anoSelecionado ??= dados.datas.corte.slice(0, 4);
  const divergencias = dados.linhas.filter((l) => l.extras?.FT === 'ERRO' || l.extras?.FU === 'ERRO').length;

  const desenhar = () => {
    el.querySelector('#visao').innerHTML = visao === 'consolidado' ? tabelaConsolidado(dados)
      : grafico(dados) + tabelaLinhaDoTempo(dados);
    if (visao !== 'consolidado') focarMesCorrente(el.querySelector('#visao'));
    el.querySelector('#anos').hidden = visao === 'consolidado';
    el.querySelectorAll('[data-visao]').forEach((b) => b.classList.toggle('on', b.dataset.visao === visao));
    el.querySelectorAll('[data-ano]').forEach((b) => b.classList.toggle('on', b.dataset.ano === (anoSelecionado || '')));
  };

  el.innerHTML = `<div class="fade">
    <div class="cabecalho"><div>
      <div class="eyebrow">Painel · ${esc(dados.titulos.ate)}</div>
      <h2>Realizado × Projetado × EVE</h2>
      <p>Corte realizado/projetado em ${fmt.mesLongo(dados.datas.corte)}. Valores de custos e despesas com sinal negativo, como na planilha.</p>
    </div>
    <div class="segmentado sem-impressao" role="tablist">
      <button data-visao="consolidado">Consolidado</button><button data-visao="linha">Linha do tempo</button>
    </div></div>
    <div class="kpis">
      <div class="card kpi"><p class="l">Receita total (VGV) · EVE</p><p class="v tab">${fmt.moeda(linhas[36].X)}</p></div>
      <div class="card kpi"><p class="l">Margem operacional · realizado</p><p class="v tab">${fmt.moeda(linhas[59].H)}</p>
        <p class="h">EVE ${fmt.moeda(linhas[59].X)}</p></div>
      <div class="card kpi"><p class="l">EBITDA · realizado + projetado</p><p class="v tab">${fmt.moeda(linhas[79].T)}</p>
        <p class="h">Desvio ${fmt.pct(linhas[79].AB)}</p></div>
      <div class="card kpi"><p class="l">Exposição máxima</p><p class="v tab">${fmt.moeda(linhas[101].T)}</p></div>
      <div class="card kpi destaque"><p class="l">Saldo de caixa (banco)</p><p class="v tab">${fmt.moeda(linhas[119].H)}</p>
        <p class="h">Realizado até ${fmt.mesLongo(dados.datas.mes_analise)}</p></div>
      <div class="card kpi"><p class="l">Verificações da planilha</p><p class="v tab">${divergencias ? `${divergencias} linha(s)` : 'Tudo confere'}</p>
        <p class="h">${divergencias ? 'linha do tempo ≠ coluna (como no Excel)' : ''}</p></div>
    </div>
    <div class="chips" id="anos" style="margin-bottom:12px">
      ${anos.map((a) => `<button class="chip" data-ano="${a}">${a}</button>`).join('')}<button class="chip" data-ano="">Todos</button>
    </div>
    <div id="visao"></div></div>`;
  el.querySelectorAll('[data-visao]').forEach((b) => (b.onclick = () => { visao = b.dataset.visao; desenhar(); }));
  el.querySelectorAll('[data-ano]').forEach((b) => (b.onclick = () => { anoSelecionado = b.dataset.ano || ''; desenhar(); }));
  desenhar();
}
