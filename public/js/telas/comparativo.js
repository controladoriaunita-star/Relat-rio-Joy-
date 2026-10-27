// Aba Projeção › Projetado × Incorrido: consulta do mês por setor. Mostra o que cada linha
// projetou e os lançamentos da base de custos (Custos SPE e NN's) nas rubricas do setor.
import { api, carregando, esc, fmt } from '../util.js';

const estado = { mes: null, setor: null, versao: 0 };   // versao: descarta resposta de filtro antigo

function tabelaProjetado(d) {
  const linhas = d.projetado.filter((p) => p.valor);
  const semValor = d.projetado.length - linhas.length;
  return `<section class="card painel-card">
    <header><div><p class="sub">Projetado por linha</p>
      <p class="muted" style="margin:0">${linhas.length} linha(s) com valor${semValor ? ` · ${semValor} sem projeção no mês` : ''}</p></div></header>
    <div class="sheet"><table><thead><tr><th class="first">Linha de projeção</th><th style="text-align:left">Rubrica</th><th>Projetado</th></tr></thead>
      <tbody>${linhas.map((p) => `<tr><td class="first">${esc(p.linha)}${d.setor ? '' : `<span class="rubrica-sub">${esc(p.setor)}</span>`}</td>
        <td style="text-align:left">${esc(p.rubrica)}</td><td>${fmt.numero(p.valor)}</td></tr>`).join('')
        || '<tr><td class="first muted" colspan="3">Nada projetado neste mês.</td></tr>'}
      ${linhas.length ? `<tr class="grande"><td class="first">Total</td><td></td><td>${fmt.numero(d.totais.projetado)}</td></tr>` : ''}</tbody></table></div>
  </section>`;
}

function tabelaIncorrido(d) {
  const grupos = new Map();
  for (const i of d.incorrido) grupos.set(i.rubrica, [...(grupos.get(i.rubrica) || []), i]);
  let corpo = '';
  for (const [rubrica, itens] of grupos) {
    corpo += `<tr class="secao"><td class="first">${esc(rubrica)}</td><td colspan="3"></td>
      <td>${fmt.numero(itens.reduce((a, i) => a + i.valor, 0))}</td></tr>`;
    corpo += itens.map((i) => `<tr><td class="first">${esc(i.fornecedor || '—')}<span class="rubrica-sub">${esc(i.fonte)} · ${esc(i.processo || '')}</span></td>
      <td class="texto">${esc(i.insumo || '')}</td>
      <td>${fmt.data(i.data)}</td>
      <td><span class="badge ${/^pago$/i.test(i.status || '') ? 'b-success' : 'b-warning'}">${esc(i.status || '—')}</span></td>
      <td>${fmt.numero(i.valor)}</td></tr>`).join('');
  }
  return `<section class="card painel-card">
    <header><div><p class="sub">Incorrido · base de custos</p>
      <p class="muted" style="margin:0">Custos SPE e NN's com data de pagamento no mês, nas rubricas ${d.setor ? 'do setor' : 'dos setores'}</p></div></header>
    <div class="sheet"><table><thead><tr><th class="first">Fornecedor</th><th style="text-align:left">Insumo</th><th>Data</th><th>Status</th><th>Valor</th></tr></thead>
      <tbody>${corpo || '<tr><td class="first muted" colspan="5">Nenhum custo lançado neste mês.</td></tr>'}
      ${d.incorrido.length ? `<tr class="grande"><td class="first">Total</td><td colspan="3"></td><td>${fmt.numero(d.totais.incorrido)}</td></tr>` : ''}</tbody></table></div>
  </section>`;
}

function caixas(d) {
  const t = d.totais;
  return `<div class="kpis comparativo-kpis">
    <div class="card kpi destaque"><p class="l">Total projetado no mês</p><p class="v tab">${fmt.moeda(t.projetado)}</p>
      <p class="h">${d.projetado.filter((p) => p.valor).length} linha(s) de projeção</p></div>
    <div class="card kpi"><p class="l">Total incorrido no mês</p><p class="v tab">${fmt.moeda(t.incorrido)}</p>
      <p class="h">${t.projetado ? `${fmt.pct(t.incorrido / t.projetado)} do projetado · ` : ''}pago ${fmt.moeda(t.pago)} · a pagar ${fmt.moeda(t.a_pagar)}</p></div>
  </div>`;
}

/** `topo` é o cabeçalho da aba (com o alternador Grade | Projetado × Incorrido);
 * `aoDesenhar` religa o alternador sempre que o cabeçalho é redesenhado. */
export async function render(el, opcoes) {
  const { usuario, dataBase, setores, topo, aoDesenhar } = opcoes;
  const versao = ++estado.versao;
  estado.mes ??= dataBase.slice(0, 7);
  if (estado.setor === null) estado.setor = setores.some((s) => s.codigo === usuario.perfil) ? usuario.perfil : '';
  el.innerHTML = `<div class="fade">${topo}
    <div class="barra-ferramentas">
      <div class="chips" id="comp-setores"><button class="chip" data-setor="">Todos</button>
        ${setores.map((s) => `<button class="chip" data-setor="${esc(s.codigo)}">${esc(s.nome)}</button>`).join('')}</div>
      <label class="row-flex muted" style="gap:8px;font-size:13px">Mês
        <input type="month" class="campo" id="comp-mes" value="${estado.mes}" style="width:auto;height:32px" /></label>
    </div>
    <div id="comp-conteudo">${carregando(8)}</div></div>`;
  aoDesenhar?.();
  el.querySelectorAll('#comp-setores [data-setor]').forEach((b) => {
    b.classList.toggle('on', b.dataset.setor === estado.setor);
    b.onclick = () => { estado.setor = b.dataset.setor; render(el, opcoes); };
  });
  el.querySelector('#comp-mes').onchange = (e) => {
    if (!e.target.value) return;
    estado.mes = e.target.value;
    render(el, opcoes);
  };
  const [ano, mes] = estado.mes.split('-').map(Number);
  const fim = new Date(ano, mes, 0).toLocaleDateString('sv-SE');
  const d = await api(`/api/projecao/comparativo?mes=${fim}${estado.setor ? `&setor=${encodeURIComponent(estado.setor)}` : ''}`);
  const conteudo = el.querySelector('#comp-conteudo');
  // Outro filtro foi escolhido, ou o usuário voltou para a Grade, antes da resposta chegar.
  if (versao !== estado.versao || !conteudo) return;
  conteudo.innerHTML = `${caixas(d)}
    <div class="comparativo">${tabelaProjetado(d)}${tabelaIncorrido(d)}</div>`;
}
