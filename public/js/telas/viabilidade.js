// Viabilidade (EVE) e rubricas da obra ativa: editor usado no Resumo (modal) e em API's › Viabilidade.
// Cada obra tem a sua lista de rubricas (despesas e custos): dá para criar, renomear e excluir.
import { api, erroToast, esc, fmt, lerNumero, modal, toast } from '../util.js';

const GRUPOS = [{ id: 'despesa', titulo: 'Despesas' }, { id: 'custo', titulo: 'Custos' }];

/** Valor do campo; se o texto não mudou, usa o valor completo guardado (o campo mostra 2 casas). */
function valorDoCampo(input) {
  const exato = Number(input.dataset.exato || 0);
  return input.value.trim() === (exato ? fmt.numero(exato) : '') ? exato : lerNumero(input.value);
}

/** Monta o formulário em `el`. Devolve uma função que salva (para o botão do modal ou da tela). */
export async function montarViabilidade(el, { obra, obras = [], pode }) {
  const { viabilidade, grupos } = await api('/obra/parametros');
  const outras = obras.filter((o) => o.codigo !== obra.codigo);
  // Modelo: uma entrada por rubrica; `anterior` = nome salvo (vazio nas rubricas novas).
  let itens = GRUPOS.flatMap((g) => (grupos[g.titulo] || []).map((nome) => (
    { nome, anterior: nome, grupo: g.id, valor: viabilidade[nome] || 0 })));
  let estrutura = false;          // modo "Editar rubricas"
  let mudouEstrutura = false;

  // Lê o que está digitado para o modelo (antes de redesenhar ou salvar).
  const lerCampos = () => {
    el.querySelectorAll('[data-item]').forEach((campo) => {
      const item = itens[Number(campo.dataset.item)];
      const valor = campo.querySelector('[data-valor]');
      item.valor = valorDoCampo(valor);
      const nome = campo.querySelector('[data-nome]');
      if (nome) item.nome = nome.value.replace(/\s+/g, ' ').trim();
    });
  };

  const somar = () => {
    let total = 0;
    const porGrupo = {};
    el.querySelectorAll('[data-item]').forEach((campo) => {
      const v = valorDoCampo(campo.querySelector('[data-valor]')) || 0;
      porGrupo[campo.dataset.grupo] = (porGrupo[campo.dataset.grupo] || 0) + v;
      total += v;
    });
    el.querySelectorAll('[data-total-grupo]').forEach((b) => (b.textContent = fmt.moeda(porGrupo[b.dataset.totalGrupo] || 0)));
    el.querySelector('[data-total-viab]').textContent = fmt.moeda(total);
  };

  const campo = (item, i) => {
    const valor = `<input data-valor inputmode="decimal" placeholder="0,00" data-exato="${item.valor || 0}"
      value="${item.valor ? fmt.numero(item.valor) : ''}" ${pode ? '' : 'disabled'} aria-label="Viabilidade de ${esc(item.nome || 'nova rubrica')}" />`;
    if (!estrutura) return `<div class="field" data-item="${i}" data-grupo="${item.grupo}"><label>${esc(item.nome)}</label>${valor}</div>`;
    const renomeada = item.anterior && item.anterior !== item.nome;
    return `<div class="field campo-rubrica" data-item="${i}" data-grupo="${item.grupo}">
      <div class="nome-rubrica"><input data-nome value="${esc(item.nome)}" placeholder="Nome da rubrica" aria-label="Nome da rubrica" />
        <button type="button" class="btn ghost xs" data-excluir="${i}" title="Excluir rubrica" aria-label="Excluir ${esc(item.nome)}">✕</button></div>
      ${valor}
      ${!item.anterior ? '<small class="nota-rubrica">nova</small>' : renomeada ? `<small class="nota-rubrica">antes: ${esc(item.anterior)}</small>` : ''}</div>`;
  };

  const desenhar = () => {
    el.innerHTML = `<p class="muted" style="margin:0">Valor previsto na viabilidade (EVE) de <b>${esc(obra.nome)}</b> para cada rubrica:
        coluna "Viabilidade" do Resumo e do Painel e base do consumo nos Dashboards e na Projeção. Vale só para esta obra.</p>
      <div class="row-flex" style="margin:12px 0;flex-wrap:wrap">
        ${pode && outras.length && !estrutura ? `<label class="row-flex muted" style="gap:6px">Copiar de
          <select class="campo" data-copiar style="width:auto">${outras.map((o) => `<option value="${esc(o.codigo)}">${esc(o.nome)}</option>`).join('')}</select></label>
          <button type="button" class="btn secondary sm" data-aplicar>Copiar valores</button>` : ''}
        ${pode && !estrutura ? '<button type="button" class="btn ghost sm" data-zerar>Zerar</button>' : ''}
        ${pode ? `<button type="button" class="btn ${estrutura ? 'primary' : 'secondary'} sm" data-estrutura>${estrutura ? 'Concluir edição das rubricas' : 'Editar rubricas'}</button>` : ''}
        <span class="total-viab">Total <b data-total-viab></b></span>
      </div>
      ${estrutura ? `<div class="alert a-info" style="margin-bottom:12px"><b>Rubricas desta obra</b>
        <div>Renomear leva junto os valores, as linhas de projeção e a classificação dos lançamentos (DePara) desta obra.
        Para os lançamentos entrarem numa rubrica nova, a classificação no DePara precisa ter o mesmo nome.</div></div>` : ''}
      ${GRUPOS.map((g) => `<fieldset class="grupo-viab"><legend>${g.titulo} <b data-total-grupo="${g.id}"></b></legend>
        <div class="grid form-viab">${itens.map((item, i) => (item.grupo === g.id ? campo(item, i) : '')).join('')}</div>
        ${estrutura ? `<button type="button" class="btn ghost sm" data-nova="${g.id}" style="margin-top:10px">+ Rubrica em ${g.titulo.toLowerCase()}</button>` : ''}
      </fieldset>`).join('')}`;
    somar();
  };

  el.addEventListener('input', somar);
  el.addEventListener('click', async (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if ('estrutura' in b.dataset) { lerCampos(); estrutura = !estrutura; desenhar(); }
    if (b.dataset.nova) {
      lerCampos();
      itens.push({ nome: '', anterior: '', grupo: b.dataset.nova, valor: 0 });
      mudouEstrutura = true;
      desenhar();
      el.querySelectorAll(`[data-grupo="${b.dataset.nova}"] [data-nome]`).forEach((i, n, todos) => { if (n === todos.length - 1) i.focus(); });
    }
    if (b.dataset.excluir) {
      lerCampos();
      itens = itens.filter((_, i) => i !== Number(b.dataset.excluir));
      mudouEstrutura = true;
      desenhar();
    }
    if ('zerar' in b.dataset) { lerCampos(); itens.forEach((i) => (i.valor = 0)); desenhar(); }
    if ('aplicar' in b.dataset) {
      try {
        const origem = el.querySelector('[data-copiar]').value;
        const dados = await api(`/api/obras/${encodeURIComponent(origem)}/parametros`);
        lerCampos();
        itens.forEach((i) => (i.valor = dados.viabilidade[i.nome] || 0));
        const faltam = Object.keys(dados.viabilidade).filter((n) => !itens.some((i) => i.nome === n));
        desenhar();
        toast('Valores copiados', { tipo: faltam.length ? 'warning' : 'info',
          texto: faltam.length ? `Sem rubrica correspondente nesta obra: ${faltam.join(', ')}.`
            : 'Confira e clique em "Salvar viabilidade" para gravar.', duracao: faltam.length ? 8000 : 3500 });
      } catch (erro) { erroToast(erro); }
    }
  });
  el.addEventListener('change', (e) => { if (e.target.matches('[data-nome]')) mudouEstrutura = true; });
  desenhar();

  return async () => {
    lerCampos();
    for (const i of itens) {
      if (Number.isNaN(i.valor)) throw new Error(`Valor inválido em "${i.nome || 'rubrica nova'}".`);
      if (!i.nome) throw new Error('Há rubrica sem nome.');
    }
    const valores = Object.fromEntries(itens.map((i) => [i.nome, i.valor || 0]));
    const renomeou = itens.some((i) => i.anterior && i.anterior !== i.nome);
    if (!mudouEstrutura && !renomeou) {
      await api('/obra/parametros/viabilidade', { metodo: 'PUT', corpo: valores });
    } else {
      const corpo = { rubricas: itens.map((i) => ({ nome: i.nome, grupo: i.grupo, nome_anterior: i.anterior || null })),
                      viabilidade: valores, forcar: false };
      try {
        await api('/obra/parametros/rubricas', { metodo: 'PUT', corpo });
      } catch (erro) {
        if (erro.status !== 409 || !window.confirm(`${erro.message}\n\nExcluir mesmo assim?`)) throw erro;
        await api('/obra/parametros/rubricas', { metodo: 'PUT', corpo: { ...corpo, forcar: true } });
      }
      itens.forEach((i) => (i.anterior = i.nome));
      mudouEstrutura = false;
    }
    toast('Viabilidade salva', { texto: obra.nome });
  };
}

/** Modal de edição (botão "Viabilidade" do Resumo). */
export function editarViabilidade(ctx) {
  let salvar = null;
  const caixa = modal({
    titulo: `Viabilidade · ${ctx.obra.nome}`,
    conteudo: '<div data-viab><div class="skel"></div></div>',
    acoes: [{ rotulo: 'Salvar viabilidade', classe: 'primary', ao: async () => {
      if (!salvar) return false;
      await salvar();
      ctx.recarregar();
    } }],
  });
  caixa.querySelector('.modal').classList.add('modal-largo');
  montarViabilidade(caixa.querySelector('[data-viab]'), { obra: ctx.obra, obras: ctx.obras, pode: true })
    .then((f) => { salvar = f; })
    .catch((erro) => { erroToast(erro); caixa.remove(); });
}
