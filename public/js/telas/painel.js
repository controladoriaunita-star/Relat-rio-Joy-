// Aba Painel: realizado x projetado x EVE e linha do tempo mensal (jan/2024 a dez/2030).
// Regras de cálculo e correções em relação à planilha: backend/app/motor/painel.py.
import { api, carregando, ehNumero, esc, fmt, focarMesCorrente, montarGrafico } from '../util.js';

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
const ROTULOS_TL = { 95: 'Saldo de caixa acumulado (operação)', 119: 'Fluxo de caixa do mês (operação + sócios)',
  122: 'Saldo de caixa acumulado (banco)' };
let visao = 'consolidado';
let anoSelecionado = null;
let ocultarZeradas = false;     // esconde rubricas sem nenhum valor (realizado, projetado e EVE)

function range(a, b) { return Array.from({ length: b - a + 1 }, (_, i) => a + i); }

function valor(v, pct = false) {
  if (!ehNumero(v)) return '';
  return pct ? fmt.pct(v) : fmt.numero(v);
}

const zerada = (l) => ['H', 'P', 'X'].every((c) => !ehNumero(l[c]) || Math.abs(l[c]) < 0.005);

/** Linhas que divergem na conferência linha do tempo × colunas (deve ser zero). */
const divergentes = (dados) => dados.linhas.filter((l) => l.extras?.FT === 'ERRO' || l.extras?.FU === 'ERRO');

function tabelaConsolidado(dados) {
  const linhas = Object.fromEntries(dados.linhas.map((l) => [l.linha_excel, l]));
  const t = dados.titulos;
  let corpo = '';
  for (const secao of SECOES) {
    corpo += `<tr class="secao"><td class="first" colspan="9">${secao.titulo}</td></tr>`;
    for (const item of secao.linhas) {
      const [r, estilo] = Array.isArray(item) ? item : [item, ''];
      const l = linhas[r];
      if (!l || (ocultarZeradas && !estilo && zerada(l))) continue;
      const pct = estilo === 'pct';
      // Custo/despesa acima do EVE: F = −D ÷ E passa de 100%.
      const alerta = ['custo', 'despesa'].includes(l.grupo) && ehNumero(l.AB) && l.AB > 1;
      corpo += `<tr class="${estilo === 'pct' ? '' : estilo}" title="Linha ${r} do Painel">
        <td class="first">${esc(l.rotulo || (r === 99 ? 'M T I R (a.m.)' : ''))}</td>
        <td>${valor(l.H, pct)}</td><td>${valor(l.L, pct)}</td><td>${valor(l.P, pct)}</td>
        <td>${valor(l.T, pct)}</td><td>${valor(l.X, pct)}</td><td>${valor(l.Y, true)}</td>
        <td class="${alerta ? 'alerta' : ''}" ${alerta ? 'title="Acima do previsto no EVE"' : ''}>${valor(l.AB, true)}</td></tr>`;
    }
  }
  const inicioProjecao = t.projetado_mes.replace('Projetado ', '');
  return `<div class="sheet" style="max-height:72vh"><table><thead><tr>
      <th class="first">Rubrica</th>
      <th title="Fontes do SharePoint até o mês de análise"><span class="letra">A</span>${esc(t.realizado)}</th>
      <th title="Projeção dos setores para o mês corrente"><span class="letra">B</span>${esc(t.projetado_mes)}</th>
      <th title="Projeção do mês corrente até dez/2030"><span class="letra">C</span>Projetado desde ${esc(inicioProjecao)}</th>
      <th><span class="letra">D = A + C</span>Total (Real. + Proj.)</th>
      <th><span class="letra">E</span>Previsto Total no EVE</th>
      <th><span class="letra">AV</span>% VGV</th>
      <th title="Receitas: D ÷ E. Custos e despesas: % do EVE consumido (acima de 100% em vermelho)."><span class="letra">F = D / E</span>% do EVE</th>
    </tr></thead><tbody>${corpo}</tbody></table></div>`;
}

function tabelaLinhaDoTempo(dados) {
  const linhas = Object.fromEntries(dados.linhas.map((l) => [l.linha_excel, l]));
  const indices = dados.meses.map((m, i) => [m, i]).filter(([m]) => !anoSelecionado || m.startsWith(anoSelecionado));
  const corte = dados.datas.corte;
  const cab = indices.map(([m], j) => `<th class="${m === corte ? 'cur' : ''} ${m.endsWith('-01-31') && j ? 'ano-inicio' : ''}">${fmt.mes(m)}</th>`).join('');
  let corpo = '';
  for (const secao of [...SECOES, { titulo: 'Acumulados', linhas: [[122, 'total']] }]) {
    corpo += `<tr class="secao"><td class="first">${secao.titulo}</td><td colspan="${indices.length + 2}"></td></tr>`;
    for (const item of secao.linhas) {
      const [r, estilo] = Array.isArray(item) ? item : [item, ''];
      const l = linhas[r];
      if (!l || !l.tl.some((v) => v !== null)) continue;
      if (ocultarZeradas && !estilo && l.tl.every((v) => !ehNumero(v) || Math.abs(v) < 0.005)) continue;
      corpo += `<tr class="${estilo === 'pct' ? '' : estilo}"><td class="first">${esc(ROTULOS_TL[r] || l.rotulo || (r === 95 ? 'Saldo acumulado' : ''))}</td>
        ${indices.map(([m, i], j) => `<td class="${m === corte ? 'cur' : ''} ${m > dados.datas.mes_analise ? 'proj' : ''} ${m.endsWith('-01-31') && j ? 'ano-inicio' : ''}">${valor(l.tl[i])}</td>`).join('')}
        <td class="tot">${valor(l.extras?.FS)}</td><td class="tot">${valor(l.extras?.FV)}</td></tr>`;
    }
  }
  return `<div class="sheet" style="max-height:70vh"><table><thead><tr><th class="first">Rubrica</th>${cab}
    <th class="tot">Realizado</th><th class="tot">Projetado</th></tr></thead><tbody>${corpo}</tbody></table></div>
    <div class="legend"><span><i style="background:var(--cell-current)"></i>Mês corrente (primeiro mês projetado)</span>
      <span><i style="background:#fff;border-color:var(--color-primary)"></i><span style="color:var(--color-primary)">Valores em roxo</span>: meses futuros (projeção)</span></div>`;
}

/** Barras do saldo de caixa mensal + linha do saldo acumulado, na largura real do card. */
function grafico(dados, L) {
  const linhas = Object.fromEntries(dados.linhas.map((l) => [l.linha_excel, l]));
  const mensal = linhas[93].tl.map((v) => v ?? 0);
  const acumulado = linhas[95].tl.map((v) => v ?? 0);
  const A = 200, m = { e: 56, d: 8, t: 10, b: 24 };
  const maxAbs = Math.max(1, ...mensal.map(Math.abs), ...acumulado.map(Math.abs));
  const meio = (A - m.t - m.b) / 2;
  const y = (v) => m.t + meio - (v / maxAbs) * meio;
  const passo = (L - m.e - m.d) / mensal.length;
  const folga = Math.min(2, passo * 0.25);
  const barras = mensal.map((v, i) => {
    const y0 = y(0), y1 = y(v);
    return `<rect x="${(m.e + i * passo + folga / 2).toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${Math.max(passo - folga, 1).toFixed(1)}" height="${Math.max(Math.abs(y1 - y0), 0.5).toFixed(1)}" rx="1"><title>${fmt.mes(dados.meses[i])}: ${fmt.moeda(v)}</title></rect>`;
  }).join('');
  const pontos = acumulado.map((v, i) => `${(m.e + i * passo + passo / 2).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const anos = dados.meses.map((mm, i) => (mm.endsWith('-01-31')
    ? `<line x1="${m.e + i * passo}" x2="${m.e + i * passo}" y1="${m.t}" y2="${A - m.b}" stroke="var(--ink-100)"/>
       <text x="${m.e + i * passo + 4}" y="${A - 8}">${mm.slice(0, 4)}</text>` : '')).join('');
  const iCorte = dados.meses.indexOf(dados.datas.corte);
  const eixo = [maxAbs, 0, -maxAbs].map((v) => `<text x="${m.e - 8}" y="${y(v) + 4}" text-anchor="end">${v ? fmt.compacto(v) : '0'}</text>`).join('');
  return `<svg viewBox="0 0 ${L} ${A}" width="${L}" height="${A}" role="img" aria-label="Saldo de caixa mensal e acumulado" class="grafico">
      <g font-size="11" fill="var(--muted)" font-family="Inter">${anos}${eixo}</g>
      ${iCorte >= 0 ? `<rect x="${m.e + iCorte * passo}" y="${m.t}" width="${passo}" height="${A - m.t - m.b}" fill="var(--cell-current)"/>` : ''}
      <line x1="${m.e}" x2="${L - m.d}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ink-200)"/>
      <g fill="var(--chart-1)">${barras}</g>
      <polyline points="${pontos}" fill="none" stroke="var(--chart-2)" stroke-width="2" stroke-linejoin="round"/>
    </svg>`;
}

const cartaoGrafico = `<div class="card pad" style="margin-bottom:16px"><p class="sub">Saldo de caixa da operação (receitas − custos − despesas, sem aportes): mensal (barras) e acumulado (linha)</p>
    <div class="grafico-area" id="grafico-caixa"></div>
    <div class="legend"><span><i style="background:var(--chart-1);border:0"></i>Saldo de caixa do mês</span>
      <span><i style="background:var(--chart-2);border:0;height:3px;vertical-align:3px"></i>Acumulado</span></div></div>`;

/** Conciliação: saldo do Painel no mês de análise × saldo dos extratos (aba Saldo). */
function kpiConciliacao(c) {
  if (c.saldo_banco === null) {
    return `<div class="card kpi"><p class="l">Conciliação com o extrato</p><p class="v tab">Sem extrato</p>
      <p class="h">Nenhum saldo lançado em ${fmt.mesLongo(c.mes)}</p></div>`;
  }
  const confere = Math.abs(c.diferenca) < 0.01;
  return `<div class="card kpi"><p class="l">Conciliação com o extrato</p>
    <p class="v tab">${confere ? 'Confere' : fmt.moeda(c.diferenca)}</p>
    <p class="h">${confere ? `Extrato ${fmt.moeda(c.saldo_banco)}` : 'Diferença: revise classificações ou o ajuste do saldo'}</p></div>`;
}

export async function render(el, { dataBase }) {
  el.innerHTML = carregando(12);
  const dados = await api(`/api/painel?data=${dataBase}`);
  const linhas = Object.fromEntries(dados.linhas.map((l) => [l.linha_excel, l]));
  const anos = [...new Set(dados.meses.map((m) => m.slice(0, 4)))];
  anoSelecionado ??= dados.datas.corte.slice(0, 4);
  const erros = divergentes(dados);
  if (erros.length) console.warn('Painel: linha do tempo difere das colunas', erros.map((l) => l.linha_excel));

  const desenhar = () => {
    el.querySelector('#visao').innerHTML = visao === 'consolidado' ? tabelaConsolidado(dados)
      : cartaoGrafico + tabelaLinhaDoTempo(dados);
    if (visao !== 'consolidado') {
      montarGrafico(el.querySelector('#grafico-caixa'), (largura) => grafico(dados, largura));
      focarMesCorrente(el.querySelector('#visao'));
    }
    el.querySelector('#anos').hidden = visao === 'consolidado';
    el.querySelector('#zeradas').classList.toggle('on', ocultarZeradas);
    el.querySelectorAll('[data-visao]').forEach((b) => b.classList.toggle('on', b.dataset.visao === visao));
    el.querySelectorAll('[data-ano]').forEach((b) => b.classList.toggle('on', b.dataset.ano === (anoSelecionado || '')));
  };

  el.innerHTML = `<div class="fade">
    <div class="cabecalho"><div>
      <div class="eyebrow">Painel · ${esc(dados.titulos.ate)}</div>
      <h2>Realizado × Projetado × EVE</h2>
      <p>Realizado até ${fmt.mesLongo(dados.datas.mes_analise)} (fontes do SharePoint) · projetado de ${fmt.mesLongo(dados.datas.corte)} em diante (Projeção dos setores). Custos e despesas com sinal negativo.</p>
    </div>
    <div class="acoes-painel sem-impressao">
      <button class="chip" id="zeradas" title="Esconde rubricas sem realizado, projetado e EVE">Ocultar linhas zeradas</button>
      <div class="segmentado" role="tablist">
        <button data-visao="consolidado">Consolidado</button><button data-visao="linha">Linha do tempo</button>
      </div>
    </div></div>
    <div class="kpis">
      <div class="card kpi"><p class="l">Receita total (VGV) · EVE</p><p class="v tab">${fmt.moeda(linhas[36].X)}</p>
        <p class="h">Realizado ${fmt.moeda(linhas[36].H)}</p></div>
      <div class="card kpi"><p class="l">Margem operacional · realizado</p><p class="v tab">${fmt.moeda(linhas[59].H)}</p>
        <p class="h">EVE ${fmt.moeda(linhas[59].X)}</p></div>
      <div class="card kpi"><p class="l">EBITDA · realizado + projetado</p><p class="v tab">${fmt.moeda(linhas[79].T)}</p>
        <p class="h">EVE ${fmt.moeda(linhas[79].X)}</p></div>
      <div class="card kpi"><p class="l">Exposição máxima</p><p class="v tab">${fmt.moeda(linhas[101].T)}</p>
        <p class="h">Pior saldo acumulado da operação</p></div>
      <div class="card kpi destaque"><p class="l">Saldo de caixa (banco)</p><p class="v tab">${fmt.moeda(linhas[119].H)}</p>
        <p class="h">Fim de ${fmt.mesLongo(dados.datas.mes_analise)}</p></div>
      ${kpiConciliacao(dados.conciliacao)}
    </div>
    <div class="chips" id="anos" style="margin-bottom:12px">
      ${anos.map((a) => `<button class="chip" data-ano="${a}">${a}</button>`).join('')}<button class="chip" data-ano="">Todos</button>
    </div>
    <div id="visao"></div></div>`;
  el.querySelectorAll('[data-visao]').forEach((b) => (b.onclick = () => { visao = b.dataset.visao; desenhar(); }));
  el.querySelectorAll('[data-ano]').forEach((b) => (b.onclick = () => { anoSelecionado = b.dataset.ano || ''; desenhar(); }));
  el.querySelector('#zeradas').onclick = () => { ocultarZeradas = !ocultarZeradas; desenhar(); };
  desenhar();
}
