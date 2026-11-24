// Card de análise de uma rubrica (aba Resumo): os lançamentos classificados nela que compõem
// Pago até, Pago no mês e Contas a pagar, com resumo, filtros, busca e visão por fornecedor.
import { api, erroToast, esc, fmt, modal } from '../util.js';

const COLUNAS = [
  { id: 'pago_ate', rotulo: 'Pago até o mês anterior' },
  { id: 'pago_mes', rotulo: 'Pago no mês' },
  { id: 'a_pagar', rotulo: 'Contas a pagar' },
];
const CURTO = { pago_ate: 'Pago anterior', pago_mes: 'Pago no mês', a_pagar: 'A pagar' };
const soma = (itens) => itens.reduce((a, i) => a + i.valor, 0);
const normal = (t) => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** `linha` = linha da rubrica no Resumo (viabilidade, pago_ate, pago_mes, a_pagar, projetado...). */
export function abrirRubrica({ linha, dataBase, mesAtual }) {
  const estado = { itens: null, coluna: '', busca: '', visao: 'lancamentos', ordem: 'data' };
  const caixa = modal({
    titulo: linha.rubrica,
    conteudo: '<div data-rubrica-card><div class="skel"></div><div class="skel"></div></div>',
    rotuloFechar: 'Fechar',
  });
  caixa.querySelector('.modal').classList.add('modal-rubrica');
  const corpo = caixa.querySelector('[data-rubrica-card]');

  const filtrados = () => {
    const termo = normal(estado.busca.trim());
    const lista = estado.itens.filter((i) => (!estado.coluna || i.coluna === estado.coluna)
      && (!termo || normal(`${i.fornecedor} ${i.descricao} ${i.fonte}`).includes(termo)));
    return estado.ordem === 'valor' ? [...lista].sort((a, b) => b.valor - a.valor) : lista;
  };

  const resumo = () => {
    const consumido = (linha.pago_ate || 0) + (linha.pago_mes || 0) + (linha.a_pagar || 0);
    const pct = linha.viabilidade ? consumido / linha.viabilidade : null;
    const kpi = (rotulo, valor, extra = '', classe = '') =>
      `<div class="kpi-rubrica ${classe}"><span>${rotulo}</span><b>${fmt.moeda(valor)}</b>${extra ? `<small>${extra}</small>` : ''}</div>`;
    return `<div class="kpis-rubrica">
      ${kpi(`Viabilidade · ${linha.grupo === 'despesa' ? 'despesa' : 'custo'}`, linha.viabilidade || 0)}
      ${kpi('Pago até mês anterior', linha.pago_ate || 0)}
      ${kpi(`Pago em ${fmt.mes(mesAtual)}`, linha.pago_mes || 0)}
      ${kpi('A pagar', linha.a_pagar || 0)}
      ${kpi('Consumido', consumido, pct === null ? 'sem viabilidade' : `${fmt.pct(pct)} da viabilidade`, pct > 1 ? 'alerta' : '')}
      ${kpi('Saldo', (linha.viabilidade || 0) - consumido, 'viabilidade − consumido', (linha.viabilidade || 0) - consumido < 0 ? 'alerta' : '')}
    </div>`;
  };

  // Fornecedor e descrição na mesma célula (duas linhas): a tabela cabe na largura do card.
  // Em telas estreitas, Fonte e Data saem das colunas e vão para a linha de baixo.
  const tabelaLancamentos = (lista) => `<table class="tabela-lancamentos"><thead><tr><th class="esq c-data">Data</th><th class="esq">Fornecedor · descrição</th><th class="esq c-fonte">Fonte</th>
      <th class="esq c-entra">Entra em</th><th class="c-valor">Valor</th></tr></thead>
    <tbody>${lista.map((i) => `<tr><td class="esq c-data">${fmt.data(i.data)}</td>
      <td class="esq celula-lanc" title="${esc([i.fornecedor, i.descricao].filter(Boolean).join(' — '))}">
        <span class="forn">${esc(i.fornecedor || i.fonte)}</span>
        <small>${esc(i.descricao || '—')}</small><small class="so-estreito">${fmt.data(i.data)} · ${esc(i.fonte)}<span class="so-celular"> · ${CURTO[i.coluna]}</span></small></td>
      <td class="esq c-fonte">${esc(i.fonte)}</td>
      <td class="esq c-entra"><span class="badge ${i.coluna === 'a_pagar' ? 'b-warning' : i.coluna === 'pago_mes' ? 'b-primary' : 'b-neutral'}">${CURTO[i.coluna]}</span></td>
      <td class="valor">${fmt.numero(i.valor)}</td></tr>`).join('')}</tbody></table>`;

  const tabelaFornecedores = (lista) => {
    const grupos = new Map();
    for (const i of lista) {
      const nome = i.fornecedor || `(sem fornecedor · ${i.fonte})`;
      const g = grupos.get(nome) || { nome, qtd: 0, pago: 0, a_pagar: 0, ultima: null };
      g.qtd += 1;
      g[i.coluna === 'a_pagar' ? 'a_pagar' : 'pago'] += i.valor;
      if (i.data && (!g.ultima || i.data > g.ultima)) g.ultima = i.data;
      grupos.set(nome, g);
    }
    const total = soma(lista) || 1;
    const linhas = [...grupos.values()].sort((a, b) => (b.pago + b.a_pagar) - (a.pago + a.a_pagar));
    return `<table class="tabela-fornecedores"><thead><tr><th class="esq">Fornecedor</th><th class="c-qtd">Lanç.</th><th class="c-ultimo">Último</th><th class="c-num">Pago</th>
        <th class="c-num">A pagar</th><th class="c-num">Total</th><th class="c-pct">%</th></tr></thead>
      <tbody>${linhas.map((g) => `<tr><td class="esq celula-lanc" title="${esc(g.nome)}"><span class="forn">${esc(g.nome)}</span>
          <small class="so-estreito">${g.qtd} lançamento(s) · pago ${fmt.numero(g.pago)} · a pagar ${fmt.numero(g.a_pagar)}</small></td>
        <td class="c-qtd">${g.qtd}</td><td class="c-ultimo">${fmt.data(g.ultima)}</td>
        <td class="c-num">${fmt.numero(g.pago)}</td><td class="c-num">${fmt.numero(g.a_pagar)}</td><td class="c-num"><b>${fmt.numero(g.pago + g.a_pagar)}</b></td>
        <td class="c-pct">${fmt.pct((g.pago + g.a_pagar) / total)}</td></tr>`).join('')}</tbody></table>`;
  };

  const desenharLista = () => {
    const lista = filtrados();
    corpo.querySelector('[data-lista]').innerHTML = !lista.length
      ? `<p class="muted vazio-rubrica">${estado.itens.length ? 'Nenhum lançamento com esse filtro.' : 'Nenhum lançamento pago ou a pagar nesta rubrica.'}</p>`
      : estado.visao === 'fornecedores' ? tabelaFornecedores(lista) : tabelaLancamentos(lista);
    corpo.querySelector('[data-rodape]').innerHTML = `<span>${lista.length} de ${estado.itens.length} lançamento(s)</span>
      <span>Total ${estado.coluna || estado.busca ? 'filtrado' : ''} <b>${fmt.moeda(soma(lista))}</b></span>`;
    corpo.querySelectorAll('[data-coluna]').forEach((b) => b.classList.toggle('on', b.dataset.coluna === estado.coluna));
    corpo.querySelectorAll('[data-visao]').forEach((b) => b.classList.toggle('on', b.dataset.visao === estado.visao));
    corpo.querySelector('[data-ordem]').hidden = estado.visao !== 'lancamentos';
  };

  const desenhar = () => {
    const conta = (c) => estado.itens.filter((i) => !c || i.coluna === c).length;
    corpo.innerHTML = `${resumo()}
      <div class="barra-rubrica">
        <div class="chips">${[{ id: '', rotulo: 'Todos' }, ...COLUNAS].map((c) =>
          `<button class="chip" data-coluna="${c.id}">${c.rotulo} <span class="muted">${conta(c.id)}</span></button>`).join('')}</div>
        <div class="row-flex" style="gap:8px">
          <input class="campo busca-rubrica" type="search" placeholder="Buscar fornecedor ou descrição" value="${esc(estado.busca)}" aria-label="Buscar" />
          <select class="campo" data-ordem style="width:auto" aria-label="Ordenar"><option value="data">Mais recentes</option>
            <option value="valor" ${estado.ordem === 'valor' ? 'selected' : ''}>Maiores valores</option></select>
          <div class="segmentado"><button data-visao="lancamentos">Lançamentos</button><button data-visao="fornecedores">Por fornecedor</button></div>
        </div>
      </div>
      <div class="sheet lista-rubrica" data-lista></div>
      <div class="rodape-rubrica" data-rodape></div>`;
    corpo.querySelector('.busca-rubrica').addEventListener('input', (e) => { estado.busca = e.target.value; desenharLista(); });
    corpo.querySelector('[data-ordem]').addEventListener('change', (e) => { estado.ordem = e.target.value; desenharLista(); });
    corpo.addEventListener('click', (e) => {
      const b = e.target.closest('[data-coluna],[data-visao]');
      if (!b) return;
      if ('coluna' in b.dataset) estado.coluna = b.dataset.coluna;
      if (b.dataset.visao) estado.visao = b.dataset.visao;
      desenharLista();
    });
    desenharLista();
  };

  api(`/obra/resumo/lancamentos?data=${dataBase}&rubrica=${encodeURIComponent(linha.rubrica)}`)
    .then((itens) => { estado.itens = itens; desenhar(); caixa.querySelector('.busca-rubrica')?.focus(); })
    .catch((erro) => {
      erroToast(erro);
      corpo.innerHTML = `<div class="alert a-error"><b>Não foi possível carregar os lançamentos</b><div>${esc(erro.message)}</div></div>`;
    });
}
