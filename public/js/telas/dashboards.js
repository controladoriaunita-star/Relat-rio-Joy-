// Aba Dashboards: exposição de caixa (oculta, ver MOSTRAR_EXPOSICAO), gasto × projetado, recebimentos, custos por rubrica,
// setores que mais gastaram e acerto da projeção. Os números vêm de /api/dashboards, com as
// mesmas definições do Resumo, do Painel e da Projeção.
import { api, carregando, esc, fmt, montarGrafico } from '../util.js';

const COR = { c1: 'var(--chart-1)', c2: 'var(--chart-2)', c3: 'var(--chart-3)' };
// Gráfico de exposição de caixa oculto a pedido da controladoria (out/2026). O cálculo continua
// no backend; para voltar a exibir, basta trocar para true.
const MOSTRAR_EXPOSICAO = false;
const estado = { setorGasto: '', periodoSetores: 'total', periodoAcerto: 'analise' };
const soma = (lista, f) => lista.reduce((a, x) => a + f(x), 0);
const ate = (iso, limite) => iso <= limite;

// ------------------------------------------------------------------ utilitários de desenho
function escalaY(min, max, topo, base) {
  const faixa = max - min || 1;
  return (v) => topo + ((max - v) / faixa) * (base - topo);
}

/** Marcas de eixo "redondas" (1, 2 ou 5 × 10^n) entre min e max. */
function marcas(min, max, quantas = 4) {
  const bruto = (max - min) / quantas || 1;
  const mag = 10 ** Math.floor(Math.log10(Math.abs(bruto)));
  const passo = [1, 2, 5, 10].map((k) => k * mag).find((p) => p >= bruto) || mag;
  const lista = [];
  for (let v = Math.ceil(min / passo) * passo; v <= max + passo / 1000; v += passo) lista.push(Math.round(v / passo) * passo);
  return lista;
}

const eixoY = (ticks, y, x0, x1) => ticks.map((t) => `
  <line x1="${x0}" x2="${x1}" y1="${y(t)}" y2="${y(t)}" stroke="var(--ink-100)"/>
  <text x="${x0 - 8}" y="${y(t) + 4}" text-anchor="end" class="rotulo-eixo">${t ? fmt.compacto(t) : '0'}</text>`).join('');

function rotulosMeses(meses, x, passo, A) {
  const cada = Math.max(1, Math.ceil(48 / passo));          // não sobrepor rótulos
  return meses.map((m, i) => (i % cada === 0
    ? `<text x="${x(i)}" y="${A - 6}" text-anchor="middle" class="rotulo-eixo">${fmt.mes(m)}</text>` : '')).join('');
}

function legenda(itens) {
  return `<div class="legend">${itens.map(([cor, rotulo, tracejado]) => `<span><i style="background:${tracejado ? 'transparent' : cor};border:${tracejado ? `2px dashed ${cor}` : 0}"></i>${esc(rotulo)}</span>`).join('')}</div>`;
}

function chips(id, opcoes, ativo) {
  return `<div class="chips" data-chips="${id}">${opcoes.map(([v, r]) => `<button class="chip ${v === ativo ? 'on' : ''}" data-valor="${esc(v)}">${esc(r)}</button>`).join('')}</div>`;
}

function cartao(classe, titulo, subtitulo, corpo, controles = '') {
  return `<section class="card painel-card ${classe}">
    <header><div><p class="sub">${titulo}</p>${subtitulo ? `<p class="muted" style="margin:0">${subtitulo}</p>` : ''}</div>${controles}</header>
    ${corpo}</section>`;
}

// Dica (tooltip) única, por delegação: qualquer marca com data-tip.
function ligarDicas(el) {
  if (el.dataset.dicas) return;
  el.dataset.dicas = '1';
  let dica = document.querySelector('.dica');
  if (!dica) { dica = document.createElement('div'); dica.className = 'dica'; dica.hidden = true; document.body.append(dica); }
  el.addEventListener('pointermove', (e) => {
    const alvo = e.target.closest('[data-tip]');
    if (!alvo) { dica.hidden = true; return; }
    dica.textContent = alvo.dataset.tip;
    dica.hidden = false;
    const x = Math.min(e.clientX + 14, innerWidth - dica.offsetWidth - 8);
    dica.style.left = `${x}px`;
    dica.style.top = `${e.clientY + 14}px`;
  });
  el.addEventListener('pointerleave', () => { dica.hidden = true; });
}

// ------------------------------------------------------------------ 1. exposição de caixa
const DESCRICAO_PONTOS = {
  A: 'Investimento inicial', B: 'Máxima necessidade de investimento (maior exposição de caixa)',
  C: 'Primeiro fluxo de caixa positivo', D: 'Ponto de equilíbrio financeiro',
};

function graficoExposicao(e, L) {
  const s = e.serie;
  const A = 300, m = { e: 76, d: 28, t: 24, b: 26 };
  const valores = s.map((p) => p.acumulado);
  const min = Math.min(0, ...valores), max = Math.max(0, ...valores);
  const folga = (max - min) * 0.12 || 1;
  const y = escalaY(min - folga, max + folga, m.t, A - m.b);
  const passo = (L - m.e - m.d) / Math.max(s.length - 1, 1);
  const x = (i) => m.e + i * passo;
  const iCorte = s.findIndex((p) => p.mes >= e.corte);
  const ponto = (i) => `${x(i).toFixed(1)},${y(s[i].acumulado).toFixed(1)}`;
  const real = s.map((_, i) => i).filter((i) => iCorte < 0 || i <= iCorte);
  const proj = iCorte < 0 ? [] : s.map((_, i) => i).filter((i) => i >= iCorte);
  const area = `M${x(0)},${y(0)} ${s.map((_, i) => `L${ponto(i)}`).join(' ')} L${x(s.length - 1)},${y(0)} Z`;
  const indice = (mes) => s.findIndex((p) => p.mes === mes);
  const marcadores = Object.entries(e.pontos).filter(([, p]) => p && indice(p.mes) >= 0).map(([letra, p]) => {
    const i = indice(p.mes), px = x(i), py = y(p.acumulado ?? p.valor);
    const seta = letra === 'B' ? `<line x1="${px}" x2="${px}" y1="${y(0)}" y2="${py - 6}" stroke="var(--ink-600)" stroke-width="1.5" marker-end="url(#seta)" marker-start="url(#seta)"/>` : '';
    const acima = letra === 'B' ? 18 : -12;
    return `${seta}<circle cx="${px}" cy="${py}" r="5" fill="var(--ink-900)" stroke="var(--surface)" stroke-width="2"/>
      <text x="${px + (letra === 'A' ? -10 : 0)}" y="${py + acima}" text-anchor="middle" class="rotulo-ponto">${letra}</text>`;
  }).join('');
  const alvos = s.map((p, i) => `<rect x="${x(i) - passo / 2}" y="${m.t}" width="${Math.max(passo, 1)}" height="${A - m.t - m.b}" fill="transparent"
    data-tip="${fmt.mesLongo(p.mes)}${i >= iCorte && iCorte >= 0 ? ' (projetado)' : ''}\nNo mês: ${fmt.moeda(p.mensal)}\nAcumulado: ${fmt.moeda(p.acumulado)}"/>`).join('');
  return `<svg viewBox="0 0 ${L} ${A}" width="${L}" height="${A}" class="grafico" role="img" aria-label="Exposição de caixa acumulada">
    <defs><marker id="seta" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="var(--ink-600)"/></marker></defs>
    ${eixoY(marcas(min - folga, max + folga), y, m.e, L - m.d)}
    ${iCorte >= 0 ? `<line x1="${x(iCorte)}" x2="${x(iCorte)}" y1="${m.t - 8}" y2="${A - m.b}" stroke="var(--ink-300)" stroke-dasharray="4 4"/>
      <text x="${x(iCorte) - 6}" y="${m.t - 10}" text-anchor="end" class="rotulo-eixo">realizado</text>
      <text x="${x(iCorte) + 6}" y="${m.t - 10}" class="rotulo-eixo">projetado</text>` : ''}
    <path d="${area}" fill="var(--chart-1)" opacity=".10"/>
    <line x1="${m.e}" x2="${L - m.d}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ink-700)" stroke-width="1.25"/>
    <polyline points="${real.map(ponto).join(' ')}" fill="none" stroke="var(--chart-1)" stroke-width="2.5" stroke-linejoin="round"/>
    ${proj.length > 1 ? `<polyline points="${proj.map(ponto).join(' ')}" fill="none" stroke="var(--chart-1)" stroke-width="2.5" stroke-dasharray="6 5" stroke-linejoin="round"/>` : ''}
    ${marcadores}${alvos}
    ${rotulosMeses(s.map((p) => p.mes), x, passo, A)}
  </svg>`;
}

function cartaoExposicao(d) {
  const e = d.exposicao;
  const ultimo = e.serie.at(-1)?.mes;
  const item = (letra) => {
    const p = e.pontos[letra];
    const valor = p ? `<b>${letra === 'C' || letra === 'D' ? fmt.mesLongo(p.mes) : fmt.moeda(p.valor)}</b>
        <span class="muted">${letra === 'C' || letra === 'D' ? `acumulado ${fmt.moeda(p.valor)}` : fmt.mesLongo(p.mes)}</span>`
      : `<b class="muted">Não ocorre até ${fmt.mesLongo(ultimo)}</b>`;
    return `<li><span class="letra-ponto">${letra}</span><div><span>${DESCRICAO_PONTOS[letra]}</span>${valor}</div></li>`;
  };
  const semRetorno = !e.pontos.D;
  return cartao('span-12', 'Exposição de caixa', 'Fluxo de caixa acumulado do empreendimento (receitas − custos − despesas), sem os aportes',
    `<div class="exposicao"><div class="grafico-area" id="g-exposicao"></div>
      <ul class="pontos-exposicao">${['A', 'B', 'C', 'D'].map(item).join('')}</ul></div>
      ${legenda([[COR.c1, 'Acumulado realizado'], [COR.c1, 'Acumulado projetado', true]])}
      ${semRetorno ? '<p class="nota">A curva não volta a subir porque a projeção ainda não tem receitas de vendas. Com as vendas projetadas, os pontos C e D aparecem.</p>' : ''}`);
}

// ------------------------------------------------------------------ barras por mês (agrupadas ou empilhadas)
function graficoBarras(meses, series, L, { empilhado = false, altura = 260 } = {}) {
  const A = altura, m = { e: 76, d: 8, t: 12, b: 24 };
  const totais = meses.map((_, i) => (empilhado ? soma(series, (s) => s.valores[i]) : Math.max(...series.map((s) => s.valores[i]))));
  const max = Math.max(1, ...totais);
  const ticks = marcas(0, max);
  const y = escalaY(0, Math.max(max, ticks.at(-1)), m.t, A - m.b);
  const passo = (L - m.e - m.d) / meses.length;
  const grupo = Math.min(passo * 0.72, 56);
  const x = (i) => m.e + i * passo + passo / 2;
  const barras = meses.map((mes, i) => {
    const tip = `${fmt.mesLongo(mes)}\n${series.map((s) => `${s.rotulo}: ${fmt.moeda(s.valores[i])}`).join('\n')}`;
    let marcasMes = '';
    if (empilhado) {
      let acumulado = 0;
      marcasMes = series.map((s) => {
        const v = s.valores[i];
        if (v <= 0) return '';
        const topo = y(acumulado + v), base = y(acumulado);
        acumulado += v;
        return `<rect x="${x(i) - grupo / 2}" y="${topo}" width="${grupo}" height="${Math.max(base - topo - 2, 1)}" rx="2" fill="${s.cor}"/>`;
      }).join('');
    } else {
      const larg = (grupo - 2 * (series.length - 1)) / series.length;
      marcasMes = series.map((s, k) => {
        const v = s.valores[i];
        if (v <= 0) return '';
        return `<rect x="${x(i) - grupo / 2 + k * (larg + 2)}" y="${y(v)}" width="${larg}" height="${Math.max(y(0) - y(v), 1)}" rx="3" fill="${s.cor}"/>`;
      }).join('');
    }
    return `${marcasMes}<rect x="${x(i) - passo / 2}" y="${m.t}" width="${passo}" height="${A - m.t - m.b}" fill="transparent" data-tip="${esc(tip)}"/>`;
  }).join('');
  return `<svg viewBox="0 0 ${L} ${A}" width="${L}" height="${A}" class="grafico" role="img">
    ${eixoY(ticks, y, m.e, L - m.d)}${barras}
    <line x1="${m.e}" x2="${L - m.d}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ink-300)"/>
    ${rotulosMeses(meses, x, passo, A)}</svg>`;
}

function tabelaMeses(meses, colunas) {
  return `<details class="detalhe"><summary>Ver tabela</summary><div class="sheet"><table>
    <thead><tr><th class="first">Mês</th>${colunas.map((c) => `<th>${esc(c.rotulo)}</th>`).join('')}</tr></thead>
    <tbody>${meses.map((m, i) => `<tr><td class="first">${fmt.mesLongo(m)}</td>${colunas.map((c) => `<td>${fmt.numero(c.valores[i])}</td>`).join('')}</tr>`).join('')}</tbody>
  </table></div></details>`;
}

// ------------------------------------------------------------------ 2. gasto × projetado
function janelaGasto(d) {
  const atual = d.datas.mes_atual;
  const meses = d.setores.meses;
  const iAtual = meses.findIndex((m) => m >= atual);
  const fim = iAtual < 0 ? meses.length - 1 : Math.min(meses.length - 1, iAtual + 6);
  const ini = Math.max(0, (iAtual < 0 ? meses.length : iAtual) - 11);
  return meses.slice(ini, fim + 1);
}

function seriesSetor(d, codigo, campo, meses) {
  const codigos = codigo ? [codigo] : d.setores.setores.map((s) => s.codigo);
  return meses.map((mes) => soma(codigos, (c) => d.setores.valores[c].find((v) => v.mes === mes)?.[campo] || 0));
}

function cartaoGasto(d) {
  const meses = janelaGasto(d);
  const proj = seriesSetor(d, estado.setorGasto, 'projetado', meses);
  const inc = seriesSetor(d, estado.setorGasto, 'incorrido', meses);
  const opcoes = [['', 'Todos'], ...d.setores.setores.map((s) => [s.codigo, s.nome])];
  return cartao('span-12', 'Gasto × projetado',
    `Base de custos (pago + a pagar) nas rubricas dos setores × projeção dos setores · projeção registrada desde ${fmt.mesLongo(d.setores.inicio_projecao)}`,
    `<div class="grafico-area" id="g-gasto"></div>
     ${legenda([[COR.c2, 'Projetado'], [COR.c1, 'Gasto (incorrido)']])}
     ${tabelaMeses(meses, [{ rotulo: 'Projetado', valores: proj }, { rotulo: 'Gasto', valores: inc },
        { rotulo: 'Gasto − projetado', valores: inc.map((v, i) => v - proj[i]) }])}`,
    chips('setorGasto', opcoes, estado.setorGasto));
}

// ------------------------------------------------------------------ 3. recebimentos
function cartaoRecebimentos(d) {
  const r = d.recebimentos.slice(-12);
  const total = soma(r, (x) => x.investidor + x.holding + x.receitas);
  const mes = r.at(-1);
  return cartao('span-6', 'Recebimentos',
    `Últimos ${r.length} meses · ${fmt.moeda(total)} no período · ${fmt.mesLongo(mes?.mes)}: ${fmt.moeda(mes ? mes.investidor + mes.holding + mes.receitas : 0)}`,
    `<div class="grafico-area" id="g-recebimentos"></div>
     ${legenda([[COR.c1, 'Aporte do investidor'], [COR.c2, 'Aporte da holding / Joy+'], [COR.c3, 'Receitas (rendimentos)']])}
     ${tabelaMeses(r.map((x) => x.mes), [{ rotulo: 'Investidor', valores: r.map((x) => x.investidor) },
        { rotulo: 'Holding / Joy+', valores: r.map((x) => x.holding) }, { rotulo: 'Receitas', valores: r.map((x) => x.receitas) }])}`);
}

// ------------------------------------------------------------------ 4. custos por rubrica
function cartaoCustos(d) {
  const linhas = d.custos.filter((c) => c.pago + c.a_pagar > 0).sort((a, b) => (b.pago + b.a_pagar) - (a.pago + a.a_pagar));
  const total = soma(linhas, (c) => c.pago + c.a_pagar);
  const corpo = linhas.map((c) => {
    const base = Math.max(c.viabilidade, c.pago + c.a_pagar) || 1;
    const pct = c.viabilidade ? (c.pago + c.a_pagar) / c.viabilidade : null;
    const acima = pct !== null && pct > 1;
    return `<div class="barra-h" data-tip="${esc(`${c.rubrica}\nPago: ${fmt.moeda(c.pago)}\nA pagar: ${fmt.moeda(c.a_pagar)}\nViabilidade: ${fmt.moeda(c.viabilidade)}`)}">
      <div class="barra-h-topo"><span>${esc(c.rubrica)}</span><span class="tab"><b>${fmt.compacto(c.pago + c.a_pagar)}</b>
        <span class="muted">${pct === null ? 'sem viabilidade' : `${fmt.pct(pct)} de ${fmt.compacto(c.viabilidade)}`}</span>
        ${acima ? '<span class="badge b-error">acima da viabilidade</span>' : ''}</span></div>
      <div class="barra-h-trilho"><i style="width:${(c.pago / base) * 100}%;background:${COR.c1}"></i><i style="width:${(c.a_pagar / base) * 100}%;background:${COR.c2}"></i>
        ${c.viabilidade && c.viabilidade < base ? `<b class="marca-viab" style="left:${(c.viabilidade / base) * 100}%"></b>` : ''}</div></div>`;
  }).join('');
  return cartao('span-6', 'Custos por rubrica', `Pago + a pagar sobre a viabilidade · total ${fmt.moeda(total)}`,
    `<div class="barras-h">${corpo || '<p class="muted">Sem custos lançados.</p>'}</div>
     ${legenda([[COR.c1, 'Pago'], [COR.c2, 'A pagar'], ['var(--ink-700)', 'Viabilidade (marca)']])}`);
}

// ------------------------------------------------------------------ 5. setores que mais gastaram
function valoresSetor(d, codigo, filtro) {
  return d.setores.valores[codigo].filter((v) => filtro(v.mes));
}

function cartaoSetores(d) {
  const atual = d.datas.mes_atual;
  const filtro = estado.periodoSetores === 'mes' ? (m) => m === atual : (m) => ate(m, atual);
  const linhas = d.setores.setores.map((s) => {
    const v = valoresSetor(d, s.codigo, filtro);
    return { ...s, pago: soma(v, (x) => x.pago), a_pagar: soma(v, (x) => x.a_pagar) };
  }).map((s) => ({ ...s, total: s.pago + s.a_pagar })).sort((a, b) => b.total - a.total);
  const maior = Math.max(1, ...linhas.map((s) => s.total));
  const corpo = linhas.map((s, i) => `<div class="barra-h" data-tip="${esc(`${s.nome}\nPago: ${fmt.moeda(s.pago)}\nA pagar: ${fmt.moeda(s.a_pagar)}`)}">
      <div class="barra-h-topo"><span>${i + 1}º · ${esc(s.nome)}</span><span class="tab"><b>${fmt.moeda(s.total)}</b></span></div>
      <div class="barra-h-trilho"><i style="width:${(s.pago / maior) * 100}%;background:${COR.c1}"></i><i style="width:${(s.a_pagar / maior) * 100}%;background:${COR.c2}"></i></div></div>`).join('');
  return cartao('span-6', 'Setores que mais gastaram',
    `${estado.periodoSetores === 'mes' ? fmt.mesLongo(atual) : `Acumulado até ${fmt.mesLongo(atual)}`} · base de custos nas rubricas de cada setor`,
    `<div class="barras-h">${corpo}</div>${legenda([[COR.c1, 'Pago'], [COR.c2, 'A pagar']])}`,
    chips('periodoSetores', [['total', 'Acumulado'], ['mes', fmt.mes(atual)]], estado.periodoSetores));
}

// ------------------------------------------------------------------ 6. acerto da projeção
/** Acerto = 1 − Σ|gasto − projetado| ÷ Σ maior(gasto, projetado), nos meses com movimento. */
function acerto(valores) {
  const meses = valores.filter((v) => v.projetado || v.incorrido);
  const base = soma(meses, (v) => Math.max(v.projetado, v.incorrido));
  return { meses: meses.length, projetado: soma(meses, (v) => v.projetado), gasto: soma(meses, (v) => v.incorrido),
    acerto: base ? 1 - soma(meses, (v) => Math.abs(v.incorrido - v.projetado)) / base : null };
}

function cartaoAcerto(d) {
  const { mes_analise: analise, mes_atual: atual } = d.datas;
  const inicio = d.setores.inicio_projecao;
  const filtros = { analise: (m) => m === analise, atual: (m) => m === atual, periodo: (m) => m >= inicio && m <= analise };
  const linhas = d.setores.setores.map((s) => ({ ...s, ...acerto(valoresSetor(d, s.codigo, filtros[estado.periodoAcerto])) }))
    .sort((a, b) => (b.acerto ?? -1) - (a.acerto ?? -1));
  const corpo = linhas.map((s, i) => {
    const pct = s.acerto === null ? null : Math.max(0, s.acerto);
    return `<div class="barra-h" data-tip="${esc(`${s.nome}\nProjetado: ${fmt.moeda(s.projetado)}\nGasto: ${fmt.moeda(s.gasto)}\nDiferença: ${fmt.moeda(s.gasto - s.projetado)}`)}">
      <div class="barra-h-topo"><span>${esc(s.nome)} ${i === 0 && pct >= 0.5 ? '<span class="badge b-success">melhor acerto</span>' : ''}</span>
        <span class="tab"><b>${pct === null ? '—' : fmt.pct(pct)}</b> <span class="muted">· proj. ${fmt.compacto(s.projetado)} · gasto ${fmt.compacto(s.gasto)}</span></span></div>
      <div class="barra-h-trilho"><i style="width:${(pct ?? 0) * 100}%;background:${COR.c1}"></i></div></div>`;
  }).join('');
  return cartao('span-6', 'Acerto da projeção por setor',
    'Acerto = 1 − |gasto − projetado| ÷ maior dos dois. 100% = gastou exatamente o projetado.',
    `<div class="barras-h">${corpo}</div>`,
    chips('periodoAcerto', [['analise', fmt.mes(analise)], ['atual', `${fmt.mes(atual)} (parcial)`], ['periodo', `Desde ${fmt.mes(inicio)}`]], estado.periodoAcerto));
}

// ------------------------------------------------------------------ tela
export async function render(el, ctx) {
  el.innerHTML = carregando(10);
  const d = await api(`/api/dashboards?data=${ctx.dataBase}`);
  const desenhar = () => {
    el.innerHTML = `<div class="fade">
      <div class="cabecalho"><div>
        <div class="eyebrow">Dashboards</div><h2>Caixa, custos e projeção</h2>
        <p>Mês corrente ${fmt.mesLongo(d.datas.mes_atual)} · realizado até ${fmt.mesLongo(d.datas.mes_analise)} · dados de ${fmt.dataHora(d.ultima_atualizacao)}</p>
      </div></div>
      <div class="dashboard">${MOSTRAR_EXPOSICAO ? cartaoExposicao(d) : ''}${cartaoGasto(d)}${cartaoRecebimentos(d)}${cartaoCustos(d)}${cartaoSetores(d)}${cartaoAcerto(d)}</div>
    </div>`;
    if (MOSTRAR_EXPOSICAO) montarGrafico(el.querySelector('#g-exposicao'), (L) => graficoExposicao(d.exposicao, L));
    const meses = janelaGasto(d);
    montarGrafico(el.querySelector('#g-gasto'), (L) => graficoBarras(meses, [
      { rotulo: 'Projetado', cor: COR.c2, valores: seriesSetor(d, estado.setorGasto, 'projetado', meses) },
      { rotulo: 'Gasto', cor: COR.c1, valores: seriesSetor(d, estado.setorGasto, 'incorrido', meses) }], L));
    const r = d.recebimentos.slice(-12);
    montarGrafico(el.querySelector('#g-recebimentos'), (L) => graficoBarras(r.map((x) => x.mes), [
      { rotulo: 'Investidor', cor: COR.c1, valores: r.map((x) => x.investidor) },
      { rotulo: 'Holding / Joy+', cor: COR.c2, valores: r.map((x) => x.holding) },
      { rotulo: 'Receitas', cor: COR.c3, valores: r.map((x) => x.receitas) }], L, { empilhado: true, altura: 240 }));
    el.querySelectorAll('[data-chips]').forEach((grupo) => grupo.querySelectorAll('[data-valor]').forEach((b) => (b.onclick = () => {
      estado[grupo.dataset.chips] = b.dataset.valor;
      const y = window.scrollY;
      desenhar();
      window.scrollTo(0, y);
    })));
  };
  desenhar();
  ligarDicas(el);
}
