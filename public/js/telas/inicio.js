// Tela inicial: um card por obra (abre o relatório da obra) e o cadastro de obras.
import { api, carregando, ehNumero, esc, fmt } from '../util.js';
import { abrirCadastro } from './cadastro_obra.js';

function cartaoObra(c, podeGerenciar) {
  const pct = c.viabilidade ? c.pago_total / c.viabilidade : null;
  const situacao = c.erro ? '<span class="badge b-error">Erro ao calcular</span>'
    : !c.arquivo ? '<span class="badge b-error">Sem arquivo de dados</span>'
      : c.com_dados === false ? '<span class="badge b-warning">Sem dados carregados</span>'
        : c.pendentes ? `<span class="badge b-warning">${c.pendentes} lançamento(s) a classificar</span>`
          : '<span class="badge b-success">Dados em dia</span>';
  const aporte = ehNumero(c.aporte_total) ? fmt.moeda(c.aporte_total) : '—';
  return `<a class="card cartao-obra" href="#${esc(c.codigo)}/resumo" aria-label="Abrir ${esc(c.nome)}">
    <div class="cartao-obra-topo">
      <div><h3>${esc(c.nome)}</h3><span class="muted">${c.empresa_spe ? `SPE ${esc(c.empresa_spe)}` : 'SPE não informada'}</span></div>
      ${podeGerenciar ? `<button class="btn ghost sm" data-configurar="${esc(c.codigo)}" title="Configurar obra">Configurar</button>` : ''}
    </div>
    ${c.erro ? `<p class="erro-cartao">${esc(c.erro)}</p>` : !('aporte_total' in c) ? '<p class="muted">Abrir a obra para lançar a projeção do seu setor.</p>' : `
    <div class="cartao-obra-aporte">
      <span class="l">Aporte necessário · ${fmt.mesLongo(c.mes)}</span>
      <span class="v">${aporte}</span>
      ${!ehNumero(c.joy) ? '' : c.com_investidor === false ? `<span class="h">100% Joy+ · obra sem investidor</span>`
        : `<span class="h">Investidor ${fmt.moeda(c.investidor)} · Joy+ ${fmt.moeda(c.joy)}</span>`}
    </div>
    <dl class="cartao-obra-numeros">
      <div><dt>Custo do mês</dt><dd>${fmt.moeda(c.custo_mes)}</dd></div>
      <div><dt>Saldo (mês anterior)</dt><dd>${fmt.moeda(c.saldo_anterior)}</dd></div>
      <div><dt>Pago / viabilidade</dt><dd>${fmt.pct(pct)}</dd></div>
    </dl>`}
    <div class="cartao-obra-rodape">${situacao}<span class="muted">${c.ultima_atualizacao ? `Atualizado ${fmt.dataHora(c.ultima_atualizacao)}` : 'Nunca atualizado'}</span></div>
  </a>`;
}

export async function render(el, { usuario, dataBase, aoMudarObras }) {
  el.innerHTML = carregando(6);
  const cards = await api(`/api/inicio?data=${dataBase}`);
  const podeGerenciar = usuario.permissoes['obras.gerenciar'];
  el.innerHTML = `<div class="fade">
    <div class="cabecalho"><div>
      <div class="eyebrow">Joy+ · Controladoria</div><h2>Obras</h2>
      <p>Escolha uma obra para abrir o relatório de aporte. Os números são da data-base ${fmt.data(dataBase)}.</p>
    </div></div>
    <div class="grade-obras">
      ${cards.map((c) => cartaoObra(c, podeGerenciar)).join('')}
      ${podeGerenciar ? `<button class="card cartao-obra cartao-nova" id="nova-obra">
        <span class="mais" aria-hidden="true">+</span><h3>Nova obra</h3>
        <span class="muted">Dados principais, viabilidade e linhas de projeção</span></button>` : ''}
    </div>
    ${!cards.length && !podeGerenciar ? '<div class="card empty"><h3>Nenhuma obra liberada</h3><p>Fale com a Controladoria.</p></div>' : ''}
  </div>`;

  const obras = podeGerenciar ? await api('/api/obras') : [];
  el.querySelector('#nova-obra')?.addEventListener('click', () => abrirCadastro({ obras, aoSalvar: aoMudarObras }));
  el.querySelectorAll('[data-configurar]').forEach((b) => b.addEventListener('click', (e) => {
    e.preventDefault();                       // o botão fica dentro do card (link)
    e.stopPropagation();
    abrirCadastro({ obra: obras.find((o) => o.codigo === b.dataset.configurar), obras, aoSalvar: aoMudarObras });
  }));
}
