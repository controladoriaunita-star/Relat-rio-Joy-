// Aba Aportes: aportes feitos na SPE até a data-base, do investidor (aba Recebidas) e da
// Joy+ (Transferências Bancárias para a SPE). Regras em backend/app/motor/aportes.py.
import { api, carregando, esc, fmt } from '../util.js';

let filtro = 'todos';     // todos | investidor | joy

const ORIGEM = { investidor: 'Investidor', joy: 'Joy+' };

function kpis(t) {
  const porEmpresa = Object.entries(t.joy_por_empresa).map(([nome, v]) => `${esc(nome)} ${fmt.moeda(v)}`).join(' · ');
  return `<div class="kpis">
    <div class="card kpi"><p class="l">Aporte investidores</p><p class="v">${fmt.moeda(t.investidor)}</p>
      <p class="h">Aba Recebidas</p></div>
    <div class="card kpi"><p class="l">Aporte Joy+</p><p class="v">${fmt.moeda(t.joy)}</p>
      <p class="h">${porEmpresa}${t.nao_identificada ? ` · não identificada ${fmt.moeda(t.nao_identificada)}` : ''}</p></div>
    <div class="card kpi destaque"><p class="l">Aporte total (Joy+ e investidores)</p><p class="v">${fmt.moeda(t.geral)}</p>
      <p class="h">${t.geral ? `Investidores ${fmt.pct(t.investidor / t.geral)} · Joy+ ${fmt.pct(t.joy / t.geral)}` : '—'}</p></div>
  </div>`;
}

function avisoApontamentos(lista) {
  if (!lista.length) return '';
  return `<div class="alert a-warning" style="margin-bottom:16px"><b>${lista.length} transferência(s) com empresa não identificada</b>
    <div>Empresa_tb diferente de 10 (Joy+) e 1 (Unità): ${lista.map((a) => `${fmt.data(a.data)} · empresa ${esc(a.codigo ?? 'vazia')} · ${fmt.moeda(a.valor)}`).join('; ')}.
    O valor está somado no aporte Joy+ como "não identificada"; confira o código na tabela Transferências Bancárias.</div></div>`;
}

function tabela(lancamentos) {
  const linhas = lancamentos.filter((a) => filtro === 'todos' || a.origem === filtro);
  const total = linhas.reduce((s, a) => s + a.valor, 0);
  const corpo = linhas.map((a) => {
    const empresa = a.origem === 'investidor'
      ? `Cliente ${esc(a.codigo ?? '—')}`
      : a.empresa ? esc(a.empresa) : `<span class="badge b-warning" title="Empresa_tb fora de 10 e 1">Empresa ${esc(a.codigo ?? 'vazia')} · verificar</span>`;
    return `<tr><td class="first">${fmt.data(a.data)}</td>
      <td style="text-align:left">${ORIGEM[a.origem]}</td><td style="text-align:left">${empresa}</td><td>${fmt.numero(a.valor)}</td></tr>`;
  }).join('');
  return `<section class="card painel-card">
    <header><div><p class="sub">Aportes realizados</p>
      <p class="muted" style="margin:0">${linhas.length} lançamento(s), do mais recente ao mais antigo</p></div>
      <div class="acoes-painel"><select id="filtro-aportes" aria-label="Filtrar por origem">
        <option value="todos" ${filtro === 'todos' ? 'selected' : ''}>Todos</option>
        <option value="investidor" ${filtro === 'investidor' ? 'selected' : ''}>Investidores</option>
        <option value="joy" ${filtro === 'joy' ? 'selected' : ''}>Joy+</option></select></div></header>
    <div class="sheet" style="max-height:60vh"><table><thead><tr><th class="first">Data</th><th style="text-align:left">Origem</th>
      <th style="text-align:left">Empresa / cliente</th><th>Valor</th></tr></thead>
      <tbody>${corpo || '<tr><td class="first muted" colspan="4">Nenhum aporte até a data-base.</td></tr>'}
      ${linhas.length ? `<tr class="grande"><td class="first">Total</td><td colspan="2"></td><td>${fmt.numero(total)}</td></tr>` : ''}</tbody></table></div>
  </section>`;
}

export async function render(alvo, { dataBase }) {
  alvo.innerHTML = carregando();
  const d = await api(`/api/aportes?data=${dataBase}`);
  const desenhar = () => {
    alvo.innerHTML = `<div class="fade">
      <div class="titulo-pagina" style="margin-bottom:16px"><h2 style="margin:0">Aportes até ${fmt.data(d.ate)}</h2>
        <p class="muted" style="margin:4px 0 0">Investidores: aba Recebidas · Joy+: transferências de outras empresas para a SPE (73)
        ${d.ultima_atualizacao ? ` · dados de ${fmt.dataHora(d.ultima_atualizacao)}` : ''}</p></div>
      ${kpis(d.totais)}${avisoApontamentos(d.apontamentos)}${tabela(d.lancamentos)}</div>`;
    alvo.querySelector('#filtro-aportes').onchange = (e) => { filtro = e.target.value; desenhar(); };
  };
  desenhar();
}
