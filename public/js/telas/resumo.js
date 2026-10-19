// Aba Resumo: dashboard com os números da aba Resumo da planilha.
import { api, carregando, ehNumero, esc, fmt, lerNumero, modal, toast } from '../util.js';

const n = (v) => (ehNumero(v) ? v : 0);
const GRUPOS = [{ id: 'despesa', titulo: 'Despesas' }, { id: 'custo', titulo: 'Custos' }, { id: 'aporte', titulo: 'Retornos de Aporte' }];
const CAMPOS = ['pago_ate', 'pago_mes', 'a_pagar', 'projetado_mes', 'projetado_proximo', 'total_mes'];
const SERIES_MES = [
  { campo: 'pago_mes', rotulo: 'Pago no mês', cor: 'var(--chart-1)' },
  { campo: 'a_pagar', rotulo: 'Contas a pagar', cor: 'var(--chart-2)' },
  { campo: 'projetado_mes', rotulo: 'Projetado', cor: 'var(--chart-3)' },
];

// ------------------------------------------------------------------ cascata do aporte
/** Cascata da fórmula Z9: saldo + receita − caixa mínimo − custo; o que faltar é o aporte. */
function cascata(passos, aporte) {
  const L = 640, A = 250, m = { e: 8, d: 8, t: 26, b: 44 };
  let acumulado = 0;
  const barras = passos.map((p) => {
    const inicio = p.tipo === 'resultado' ? 0 : acumulado;
    const fim = p.tipo === 'resultado' ? acumulado : acumulado + p.valor;
    if (p.tipo !== 'resultado') acumulado = fim;
    return { ...p, inicio, fim };
  });
  if (ehNumero(aporte) && aporte > 0) barras.push({ rotulo: 'Aporte', valor: aporte, tipo: 'aporte', inicio: acumulado, fim: acumulado + aporte });
  const valores = barras.flatMap((b) => [b.inicio, b.fim]).concat(0);
  const min = Math.min(...valores), max = Math.max(...valores);
  const y = (v) => m.t + ((max - v) / (max - min || 1)) * (A - m.t - m.b);
  const passo = (L - m.e - m.d) / barras.length;
  const largura = Math.min(72, passo - 16);
  const cor = { entrada: 'var(--chart-3)', saida: 'var(--chart-neutro)', resultado: 'var(--ink-700)', aporte: 'var(--chart-1)' };
  const marcas = barras.map((b, i) => {
    const x = m.e + i * passo + (passo - largura) / 2;
    const topo = y(Math.max(b.inicio, b.fim)), altura = Math.max(Math.abs(y(b.inicio) - y(b.fim)), 2);
    const conector = i < barras.length - 1
      ? `<line x1="${x + largura}" x2="${x + passo}" y1="${y(b.fim)}" y2="${y(b.fim)}" stroke="var(--ink-300)" stroke-dasharray="3 3"/>` : '';
    const sinal = b.valor < 0 ? '−' : b.tipo === 'entrada' ? '+' : '';
    return `<g><title>${esc(b.rotulo)}: ${fmt.moeda(b.valor)}</title>
      <rect x="${x}" y="${topo}" width="${largura}" height="${altura}" rx="4" fill="${cor[b.tipo]}"/>
      <text x="${x + largura / 2}" y="${topo - 8}" text-anchor="middle" class="rotulo-valor">${sinal}${fmt.compacto(Math.abs(b.valor))}</text>
      <text x="${x + largura / 2}" y="${A - 24}" text-anchor="middle" class="rotulo-eixo">${esc(b.rotulo)}</text>
      ${b.sub ? `<text x="${x + largura / 2}" y="${A - 10}" text-anchor="middle" class="rotulo-eixo muted">${esc(b.sub)}</text>` : ''}
      </g>${conector}`;
  }).join('');
  return `<div class="rolavel"><svg viewBox="0 0 ${L} ${A}" width="100%" role="img" aria-label="Formação do aporte" class="grafico">
    <line x1="${m.e}" x2="${L - m.d}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ink-200)"/>${marcas}</svg></div>`;
}

function divisao(total, investidor, joy) {
  if (!ehNumero(total) || total <= 0) return '<p class="muted" style="margin:8px 0 0">Saldo cobre os custos: nenhum aporte necessário.</p>';
  return `<div class="divisao"><div class="divisao-barra"><i style="flex:${investidor}"></i><i style="flex:${joy}"></i></div>
    <div class="divisao-rotulos"><span><b>${fmt.moeda(investidor)}</b> Investidor (85%)</span><span><b>${fmt.moeda(joy)}</b> Joy+ (15%)</span></div></div>`;
}

function cartaoAporteMes(d) {
  const a = d.aporte_mes;
  const passos = [
    { rotulo: 'Saldo', sub: fmt.mes(d.datas.mes_analise), valor: a.saldo_anterior, tipo: 'entrada' },
    { rotulo: 'Receita', sub: 'do mês', valor: a.receita_projetada, tipo: 'entrada' },
    { rotulo: 'Caixa mínimo', valor: -a.caixa_minimo, tipo: 'saida' },
    { rotulo: 'Custo do mês', sub: 'pago + a pagar + proj.', valor: -a.custo_mes, tipo: 'saida' },
    { rotulo: 'Resultado', valor: a.saldo_anterior + a.receita_projetada - a.caixa_minimo - a.custo_mes, tipo: 'resultado' },
  ];
  return `<section class="card painel-card span-7">
    <header><div><p class="sub">Aporte do mês · ${fmt.mesLongo(d.datas.mes_atual)}</p>
      <p class="numero-heroi ${ehNumero(a.aporte_total) ? '' : 'muted'}">${ehNumero(a.aporte_total) ? fmt.moeda(a.aporte_total) : 'Sem aporte'}</p></div>
      <span class="badge b-primary">Calculado (Resumo Z9)</span></header>
    ${divisao(a.aporte_total, a.investidor, a.joy)}
    ${cascata(passos, a.aporte_total)}
    <div class="legend"><span><i style="background:var(--chart-3);border:0"></i>Entradas</span>
      <span><i style="background:var(--chart-neutro);border:0"></i>Saídas</span>
      <span><i style="background:var(--chart-1);border:0"></i>Aporte necessário</span></div>
  </section>`;
}

function linhaExtrato(rotulo, valor, classe = '', extra = '') {
  return `<div class="par ${classe}"><span>${esc(rotulo)}${extra}</span><b>${fmt.moeda(valor)}</b></div>`;
}

function cartaoProximo(d) {
  const p = d.aporte_proximo;
  return `<section class="card painel-card span-5">
    <header><div><p class="sub">Aporte do próximo mês · ${fmt.mesLongo(d.datas.proximo_mes)}</p>
      <p class="numero-heroi">${fmt.moeda(p.aporte_total)}</p></div></header>
    ${divisao(p.aporte_total, p.investidor, p.joy)}
    <div class="extrato">
      ${linhaExtrato('Saldo projetado no fim do mês', p.saldo_anterior)}
      ${linhaExtrato('Receita projetada', p.receita_projetada)}
      ${linhaExtrato('Custo projetado', p.custo_projetado, '', p.custo_automatico ? ' <span class="badge b-primary">automático</span>' : '')}
      ${linhaExtrato('Caixa mínimo', p.caixa_minimo)}
      ${linhaExtrato('Aporte total', p.aporte_total, 'forte destaque')}
    </div>
    <p class="nota">Custo projetado = projeção dos setores + contas a pagar com vencimento no próximo mês.</p>
  </section>`;
}

// ------------------------------------------------------------------ consumo e custo do mês
function cartaoConsumo(d) {
  const rubricas = d.linhas.filter((l) => ['despesa', 'custo'].includes(l.grupo))
    .map((l) => ({ ...l, consumido: n(l.pago_ate) + n(l.pago_mes) }));
  const linhas = rubricas.filter((l) => l.consumido > 0)
    .sort((a, b) => n(b.pct_consumido) - n(a.pct_consumido) || b.consumido - a.consumido);
  const semConsumo = rubricas.filter((l) => l.consumido <= 0 && n(l.viabilidade) > 0);
  const viabSemConsumo = semConsumo.reduce((a, l) => a + n(l.viabilidade), 0);
  return `<section class="card painel-card span-7">
    <header><div><p class="sub">Consumo da viabilidade por rubrica</p>
      <p class="muted" style="margin:0">Pago até ${fmt.data(d.datas.mes_atual)} sobre o valor da viabilidade</p></div></header>
    <div class="bullets">${linhas.map((l) => {
      const pct = l.viabilidade ? l.consumido / l.viabilidade : null;
      const excedido = ehNumero(pct) && pct > 1;
      return `<div class="bullet" title="${esc(l.rubrica)}: ${fmt.moeda(l.consumido)} de ${fmt.moeda(l.viabilidade)}">
        <div class="bullet-topo"><span>${esc(l.rubrica)}</span>
          <span class="tab"><b>${fmt.pct(pct)}</b> <span class="muted">· ${fmt.compacto(l.consumido)} de ${fmt.compacto(l.viabilidade)}</span>
          ${excedido ? '<span class="badge b-error">acima da viabilidade</span>' : ''}</span></div>
        <div class="bullet-trilho"><i style="width:${Math.min(n(pct), 1) * 100}%" class="${excedido ? 'excedido' : ''}"></i></div></div>`;
    }).join('')}</div>
    ${semConsumo.length ? `<p class="nota" title="${esc(semConsumo.map((l) => l.rubrica).join(', '))}">
      ${semConsumo.length} rubrica(s) ainda sem pagamento · ${fmt.moeda(viabSemConsumo)} de viabilidade</p>` : ''}
  </section>`;
}

function cartaoCustoMes(d) {
  const linhas = d.linhas.filter((l) => l.linha_excel <= 41 && SERIES_MES.some((s) => n(l[s.campo]) > 0))
    .map((l) => ({ ...l, soma: SERIES_MES.reduce((a, s) => a + n(l[s.campo]), 0) }))
    .sort((a, b) => b.soma - a.soma);
  const maior = Math.max(1, ...linhas.map((l) => l.soma));
  return `<section class="card painel-card span-12">
    <header><div><p class="sub">Custo do mês por rubrica · ${fmt.mesLongo(d.datas.mes_atual)}</p>
      <p class="muted" style="margin:0">Total ${fmt.moeda(d.aporte_mes.custo_mes)} (entra no cálculo do aporte)</p></div>
      <div class="legend" style="margin:0">${SERIES_MES.map((s) => `<span><i style="background:${s.cor};border:0"></i>${s.rotulo}</span>`).join('')}</div></header>
    <div class="empilhadas">${linhas.map((l) => `<div class="empilhada">
      <span class="empilhada-rotulo">${esc(l.rubrica)}</span>
      <div class="empilhada-barra" style="width:${(l.soma / maior) * 100}%">
        ${SERIES_MES.filter((s) => n(l[s.campo]) > 0).map((s) => `<i style="flex:${l[s.campo]};background:${s.cor}" title="${esc(l.rubrica)} · ${s.rotulo}: ${fmt.moeda(l[s.campo])}"></i>`).join('')}
      </div><span class="empilhada-total tab">${fmt.moeda(l.soma)}</span></div>`).join('') || '<p class="muted">Sem movimento no mês.</p>'}</div>
  </section>`;
}

function cartaoConta(d, classe = '') {
  const c = d.conta;
  return `<section class="card painel-card ${classe}">
    <header><p class="sub">Conta da SPE</p></header>
    <div class="extrato">
      ${linhaExtrato('Saldo do mês anterior', c.saldo_mes_anterior)}
      ${linhaExtrato(d.titulos.valor_recebido, c.valor_recebido)}
      ${linhaExtrato(d.titulos.pago_e_a_pagar, -c.pago_e_a_pagar)}
      ${linhaExtrato('Saldo atual em conta', c.saldo_atual, 'forte')}
      ${linhaExtrato('Valor a ser aportado', c.valor_a_aportar)}
      ${linhaExtrato('Saldo da conta no fim do mês', c.saldo_final, 'forte destaque')}
    </div></section>`;
}

function cartaoProgramados(d, classe = '') {
  return `<section class="card painel-card ${classe}">
    <header><p class="sub">Aportes programados</p></header>
    <div class="extrato">${d.aportes_programados.map((a) => `
      ${linhaExtrato(a.titulo, a.valor, 'forte')}
      <div class="par sub-par"><span>Joy+ 85% · Bapema 15%</span><b>${fmt.numero(a.investidor)} · ${fmt.numero(a.joy)}</b></div>`).join('')}
      ${linhaExtrato('Total programado', d.total_aportes_programados, 'forte destaque')}
    </div></section>`;
}

// ------------------------------------------------------------------ tabela completa (planilha)
function linhaTabela(l, classe = '') {
  const pct = ehNumero(l.pct_consumido) ? fmt.pct(l.pct_consumido) : '';
  return `<tr class="${classe}"><td class="first">${esc(l.rubrica)}</td>
    <td>${'viabilidade' in l ? fmt.numero(l.viabilidade) : ''}</td><td>${pct}</td>
    ${CAMPOS.map((c) => `<td class="${c.startsWith('projetado') ? 'proj' : ''}">${c in l ? fmt.numero(l[c]) : ''}</td>`).join('')}</tr>`;
}

function tabelaCompleta(d) {
  const t = d.titulos;
  let corpo = '';
  for (const g of GRUPOS) {
    corpo += `<tr class="secao"><td class="first" colspan="9">${g.titulo}</td></tr>`;
    corpo += d.linhas.filter((l) => l.grupo === g.id).map((l) => linhaTabela(l)).join('');
  }
  corpo += linhaTabela({ ...d.total, rubrica: 'Total' }, 'grande');
  return `<div class="sheet"><table><thead><tr><th class="first">Rubricas</th><th>Valor Viabilidade</th><th>% Consumido</th>
    <th>${esc(t.pago_ate)}</th><th>${esc(t.pago_mes)}</th><th>${esc(t.a_pagar.replace('  ', ' '))}</th><th>Projetado Mês</th>
    <th>${esc(t.projetado_proximo.replace('  ', ' '))}</th><th title="Pago no mês + contas a pagar">Total Mês</th></tr></thead>
    <tbody>${corpo}</tbody></table></div>`;
}

// ------------------------------------------------------------------ premissas
async function editarPremissas(recarregar) {
  const { premissas: p } = await api('/api/parametros');
  const campo = (nome, rotulo, ajuda = '') => `<div class="field"><label>${rotulo}</label>
    <input name="${nome}" value="${fmt.numero(p[nome])}" inputmode="decimal" />${ajuda ? `<small>${ajuda}</small>` : ''}</div>`;
  const aportes = p.aportes_programados.map((a, i) => `<div class="formulario" style="grid-template-columns:2fr 1fr">
    <div class="field"><label>Aporte ${i + 1}</label><input name="ap_titulo_${i}" value="${esc(a.titulo)}" /></div>
    <div class="field"><label>Valor</label><input name="ap_valor_${i}" value="${fmt.numero(a.valor)}" /></div></div>`).join('');
  const numericos = ['caixa_minimo', 'caixa_minimo_proximo', 'aporte_referencia', 'receita_projetada_proximo', 'ajuste_saldo_banco'];
  modal({
    titulo: 'Premissas do aporte',
    conteudo: `<p>Valores que a planilha recebe digitados. O custo do próximo mês é calculado automaticamente.</p>
      <div class="grid" style="margin-top:16px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
        ${campo('caixa_minimo', 'Caixa mínimo (mês)')}${campo('caixa_minimo_proximo', 'Caixa mínimo (próximo)')}
        ${campo('aporte_referencia', 'Base do valor a aportar', 'Resumo Z17 = base − valor recebido')}
        ${campo('receita_projetada_proximo', 'Receita projetada (próximo)')}
        ${campo('ajuste_saldo_banco', 'Ajuste do saldo banco', 'Painel H119')}
      </div><p class="sub" style="margin-top:20px">Aportes programados</p>${aportes}`,
    acoes: [{ rotulo: 'Salvar premissas', classe: 'primary', ao: async (el) => {
      const ler = (nome) => lerNumero(el.querySelector(`[name=${nome}]`).value);
      const corpo = Object.fromEntries(numericos.map((k) => [k, ler(k)]));
      corpo.aportes_programados = p.aportes_programados.map((_, i) => ({
        titulo: el.querySelector(`[name=ap_titulo_${i}]`).value, valor: ler(`ap_valor_${i}`) }));
      if (Object.values(corpo).some((v) => Number.isNaN(v)) || corpo.aportes_programados.some((a) => Number.isNaN(a.valor))) {
        throw new Error('Há valores inválidos.');
      }
      await api('/api/parametros/premissas', { metodo: 'PUT', corpo });
      toast('Premissas salvas');
      recarregar();
    } }],
  });
}

// ------------------------------------------------------------------ tela
export async function render(el, { usuario, dataBase, recarregar }) {
  el.innerHTML = carregando(10);
  const d = await api(`/api/resumo?data=${dataBase}`);
  const t = d.total;
  const pago = t.pago_ate + t.pago_mes;
  el.innerHTML = `<div class="fade">
    <div class="cabecalho"><div>
      <div class="eyebrow">Relatório de Aporte · Evans</div><h2>Resumo</h2>
      <p>Mês de análise ${fmt.mesLongo(d.datas.mes_analise)} · mês corrente ${fmt.mesLongo(d.datas.mes_atual)} · dados de ${fmt.dataHora(d.ultima_atualizacao)}</p>
    </div><div class="row-flex sem-impressao">
      ${usuario.permissoes.editar_premissas ? '<button class="btn secondary sm" id="premissas">Premissas</button>' : ''}
      <button class="btn secondary sm" onclick="window.print()">Imprimir</button></div></div>
    <div class="kpis">
      <div class="card kpi"><p class="l">Viabilidade total</p><p class="v tab">${fmt.moeda(t.viabilidade)}</p></div>
      <div class="card kpi"><p class="l">Pago total</p><p class="v tab">${fmt.moeda(pago)}</p><p class="h">${fmt.pct(t.viabilidade ? pago / t.viabilidade : null)} da viabilidade</p></div>
      <div class="card kpi"><p class="l">Pago no mês</p><p class="v tab">${fmt.moeda(t.pago_mes)}</p><p class="h">${fmt.mesLongo(d.datas.mes_atual)}</p></div>
      <div class="card kpi"><p class="l">Contas a pagar</p><p class="v tab">${fmt.moeda(t.a_pagar)}</p><p class="h">até ${fmt.data(d.datas.a_pagar_ate)}</p></div>
      <div class="card kpi"><p class="l">Projetado no mês</p><p class="v tab">${fmt.moeda(t.projetado_mes)}</p></div>
      <div class="card kpi"><p class="l">Projetado próximo mês</p><p class="v tab">${fmt.moeda(t.projetado_proximo)}</p><p class="h">${fmt.mesLongo(d.datas.proximo_mes)}</p></div>
    </div>
    <div class="dashboard">
      ${cartaoAporteMes(d)}${cartaoProximo(d)}${cartaoConsumo(d)}
      <div class="span-5 coluna">${cartaoConta(d)}${cartaoProgramados(d)}</div>
      ${cartaoCustoMes(d)}
    </div>
    <details class="detalhe sem-impressao"><summary>Tabela completa (como na aba Resumo da planilha)</summary>${tabelaCompleta(d)}</details>
  </div>`;
  el.querySelector('#premissas')?.addEventListener('click', () => editarPremissas(recarregar));
}
