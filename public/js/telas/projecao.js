// Aba Projeção: cada setor projeta suas linhas mês a mês. O total por rubrica
// alimenta as colunas "Projetado" do Resumo e do Painel.
import { api, carregando, erroToast, esc, fmt, focarMesCorrente, lerNumero, modal, toast } from '../util.js';

const estado = { dados: null, alteracoes: new Map(), setor: null, ano: null, soComValor: false };
const chave = (linha, mes) => `${linha}|${mes}`;

function valorAtual(linha, mes) {
  const k = chave(linha.id, mes);
  return estado.alteracoes.has(k) ? estado.alteracoes.get(k) : linha.valores[mes] ?? 0;
}

function bloqueado(setor, mes) {
  return !setor.editavel || (mes < estado.dados.mes_atual && !estado.dados.pode_editar_passado);
}

function mesesVisiveis() {
  return estado.dados.meses.filter((m) => m.startsWith(estado.ano));
}

function setoresVisiveis() {
  return estado.dados.setores.filter((s) => !estado.setor || s.codigo === estado.setor);
}

const totalLinha = (linha, meses) => meses.reduce((a, m) => a + valorAtual(linha, m), 0);

// ------------------------------------------------------------------ grade
function grade() {
  const meses = mesesVisiveis();
  const todos = estado.dados.meses;
  const cab = meses.map((m) => `<th class="${m === estado.dados.mes_atual ? 'cur' : ''}">${fmt.mes(m)}</th>`).join('');
  let corpo = '';
  for (const setor of setoresVisiveis()) {
    const linhas = setor.linhas.filter((l) => !estado.soComValor || totalLinha(l, todos) !== 0);
    const somaMes = (m) => setor.linhas.reduce((a, l) => a + valorAtual(l, m), 0);
    corpo += `<tr class="setor"><td class="first">${esc(setor.nome)}
        ${setor.editavel ? '' : '<span class="cadeado">· somente leitura</span>'}</td>
      ${meses.map((m) => `<td class="${m === estado.dados.mes_atual ? 'cur' : ''}" data-setor-mes="${setor.id}|${m}">${fmt.numero(somaMes(m))}</td>`).join('')}
      <td class="tot" data-setor-ano="${setor.id}">${fmt.numero(meses.reduce((a, m) => a + somaMes(m), 0))}</td>
      <td class="tot" data-setor-total="${setor.id}">${fmt.numero(todos.reduce((a, m) => a + somaMes(m), 0))}</td></tr>`;
    for (const linha of linhas) {
      corpo += `<tr data-linha="${linha.id}"><td class="first">${esc(linha.nome)}<span class="rubrica-sub">${esc(linha.rubrica)}</span></td>
        ${meses.map((m) => {
          const k = chave(linha.id, m);
          const trava = bloqueado(setor, m);
          const v = valorAtual(linha, m);
          return `<td class="cel ${trava ? 'bloqueada' : ''} ${estado.alteracoes.has(k) ? 'alterada' : ''} ${m === estado.dados.mes_atual ? 'cur' : ''}">
            <input data-linha="${linha.id}" data-setor="${setor.id}" data-mes="${m}" value="${v ? fmt.numero(v) : ''}"
              ${trava ? 'readonly tabindex="-1"' : ''} inputmode="decimal" aria-label="${esc(linha.nome)} ${fmt.mes(m)}" /></td>`;
        }).join('')}
        <td class="tot" data-linha-ano="${linha.id}">${fmt.numero(totalLinha(linha, meses))}</td>
        <td class="tot" data-linha-total="${linha.id}">${fmt.numero(totalLinha(linha, todos))}</td></tr>`;
    }
    if (!linhas.length) corpo += `<tr><td class="first muted" colspan="${meses.length + 3}">Nenhuma linha com valor.</td></tr>`;
  }
  return `<div class="sheet grade-projecao" style="max-height:62vh"><table>
    <thead><tr><th class="first">Linha de projeção</th>${cab}<th class="tot">Total ${estado.ano}</th><th class="tot">Total geral</th></tr></thead>
    <tbody>${corpo}</tbody></table></div>
    <div class="legend"><span><i style="background:var(--cell-current)"></i>Mês corrente</span>
      <span><i style="background:var(--cell-manual)"></i>Alterado, não salvo</span>
      <span><i style="background:var(--cell-locked)"></i>Bloqueado (mês passado ou outro setor)</span>
      <span>Dica: cole valores copiados do Excel; Enter/↑/↓ movem entre linhas.</span></div>`;
}

function tabelaRubricas() {
  const linhas = estado.dados.rubricas.filter((r) => r.viabilidade || r.realizado || r.a_pagar || r.projetado);
  return `<div class="sheet"><table><thead><tr><th class="first">Rubrica</th><th>Viabilidade</th>
      <th>Realizado</th><th>Contas a pagar</th><th>Projetado</th><th>Saldo da viabilidade</th><th>Comprometido</th></tr></thead>
    <tbody>${linhas.map((r) => {
      const comprometido = r.viabilidade ? (r.realizado + r.a_pagar + r.projetado) / r.viabilidade : null;
      return `<tr><td class="first">${esc(r.rubrica)}</td><td>${fmt.numero(r.viabilidade)}</td><td>${fmt.numero(r.realizado)}</td>
        <td>${fmt.numero(r.a_pagar)}</td><td class="proj">${fmt.numero(r.projetado)}</td>
        <td class="${r.saldo < 0 ? 'alerta' : ''}">${fmt.numero(r.saldo)}</td>
        <td><div class="pct"><span>${fmt.pct(comprometido)}</span><div class="barra ${comprometido > 1 ? 'excedido' : ''}">
          <i style="width:${Math.min(Math.max(comprometido || 0, 0), 1) * 100}%"></i></div></div></td></tr>`;
    }).join('')}</tbody></table></div>`;
}

// ------------------------------------------------------------------ atualização incremental
function atualizarTotais(el) {
  const meses = mesesVisiveis();
  const todos = estado.dados.meses;
  for (const setor of setoresVisiveis()) {
    const somaMes = (m) => setor.linhas.reduce((a, l) => a + valorAtual(l, m), 0);
    meses.forEach((m) => { const c = el.querySelector(`[data-setor-mes="${setor.id}|${m}"]`); if (c) c.textContent = fmt.numero(somaMes(m)); });
    el.querySelector(`[data-setor-ano="${setor.id}"]`).textContent = fmt.numero(meses.reduce((a, m) => a + somaMes(m), 0));
    el.querySelector(`[data-setor-total="${setor.id}"]`).textContent = fmt.numero(todos.reduce((a, m) => a + somaMes(m), 0));
    for (const linha of setor.linhas) {
      const ano = el.querySelector(`[data-linha-ano="${linha.id}"]`);
      if (!ano) continue;
      ano.textContent = fmt.numero(totalLinha(linha, meses));
      el.querySelector(`[data-linha-total="${linha.id}"]`).textContent = fmt.numero(totalLinha(linha, todos));
    }
  }
  const barra = el.querySelector('.barra-salvar');
  barra.classList.toggle('visivel', estado.alteracoes.size > 0);
  barra.querySelector('b').textContent = `${estado.alteracoes.size} alteração(ões) não salva(s)`;
}

function linhaPorId(id) {
  for (const s of estado.dados.setores) for (const l of s.linhas) if (l.id === id) return l;
  return null;
}

function registrar(input, el) {
  const valor = lerNumero(input.value);
  if (Number.isNaN(valor)) {
    toast('Valor inválido', { tipo: 'error', texto: `"${input.value}" não é um número.` });
    input.value = '';
    return;
  }
  const linha = linhaPorId(Number(input.dataset.linha));
  const mes = input.dataset.mes;
  const k = chave(linha.id, mes);
  if (Math.abs(valor - (linha.valores[mes] ?? 0)) < 0.005) estado.alteracoes.delete(k);
  else estado.alteracoes.set(k, valor);
  input.value = valor ? fmt.numero(valor) : '';
  input.parentElement.classList.toggle('alterada', estado.alteracoes.has(k));
  atualizarTotais(el);
}

function mover(input, delta) {
  const entradas = [...input.closest('tbody').querySelectorAll(`input[data-mes="${input.dataset.mes}"]:not([readonly])`)];
  entradas[entradas.indexOf(input) + delta]?.focus();
}

function colar(evento, el) {
  const texto = evento.clipboardData.getData('text');
  if (!texto.includes('\t') && !texto.includes('\n')) return;      // colagem simples segue o padrão
  evento.preventDefault();
  const origem = evento.target;
  const linhasTr = [...origem.closest('tbody').querySelectorAll('tr[data-linha]')];
  const meses = mesesVisiveis();
  let tr = linhasTr.indexOf(origem.closest('tr'));
  const col0 = meses.indexOf(origem.dataset.mes);
  let aplicados = 0;
  for (const linhaTexto of texto.replace(/\r/g, '').split('\n').filter((l) => l.length)) {
    const destino = linhasTr[tr++];
    if (!destino) break;
    linhaTexto.split('\t').forEach((celula, j) => {
      const input = destino.querySelector(`input[data-mes="${meses[col0 + j]}"]`);
      if (!input || input.readOnly) return;
      input.value = celula;
      registrar(input, el);
      aplicados++;
    });
  }
  toast(`${aplicados} célula(s) coladas`, { tipo: 'info' });
}

// ------------------------------------------------------------------ administração de linhas
function gerenciarLinhas(recarregar) {
  const { setores, rubricas } = estado.dados;
  const opcoesSetor = setores.map((s) => `<option value="${s.id}">${esc(s.nome)}</option>`).join('');
  const opcoesRubrica = rubricas.map((r) => `<option>${esc(r.rubrica)}</option>`).join('');
  const lista = setores.map((s) => `<p class="sub" style="margin-top:16px">${esc(s.nome)} · perfil "${esc(s.codigo)}"</p>
    ${s.linhas.map((l) => `<div class="par"><span>${esc(l.nome)} <span class="muted">· ${esc(l.rubrica)}</span></span>
      <button class="btn ghost sm" data-desativar="${l.id}" data-setor="${s.id}">Desativar</button></div>`).join('')}`).join('');
  const janela = modal({
    titulo: 'Setores e linhas de projeção',
    conteudo: `<p>Um setor novo cria um perfil de acesso com o mesmo código. Linhas desativadas deixam de ser somadas.</p>
      <p class="sub" style="margin-top:16px">Nova linha</p>
      <div class="formulario"><div class="field"><label>Setor</label><select name="setor">${opcoesSetor}</select></div>
        <div class="field"><label>Nome da linha</label><input name="nome" placeholder="Ex.: ARQUITETURA | RSA" /></div>
        <div class="field"><label>Rubrica</label><select name="rubrica">${opcoesRubrica}</select></div></div>
      <p class="sub" style="margin-top:16px">Novo setor</p>
      <div class="formulario"><div class="field"><label>Código (perfil)</label><input name="codigo" placeholder="ex.: jur" /></div>
        <div class="field"><label>Nome</label><input name="nome_setor" placeholder="Ex.: Jurídico" /></div></div>
      ${lista}`,
    acoes: [{ rotulo: 'Salvar', classe: 'primary', ao: async (el) => {
      const v = (n) => el.querySelector(`[name=${n}]`).value.trim();
      if (v('codigo') || v('nome_setor')) await api('/api/setores', { metodo: 'POST', corpo: { codigo: v('codigo'), nome: v('nome_setor') } });
      if (v('nome')) await api('/api/linhas', { metodo: 'POST', corpo: { setor_id: Number(v('setor')), nome: v('nome'), rubrica: v('rubrica') } });
      toast('Cadastro atualizado');
      recarregar();
    } }],
  });
  janela.querySelectorAll('[data-desativar]').forEach((b) => (b.onclick = async () => {
    const linha = linhaPorId(Number(b.dataset.desativar));
    try {
      await api('/api/linhas', { metodo: 'POST', corpo: { ...linha, setor_id: Number(b.dataset.setor), ativo: 0 } });
      b.closest('.par').remove();
      toast('Linha desativada');
      recarregar();
    } catch (erro) { erroToast(erro); }
  }));
}

// ------------------------------------------------------------------ tela
export function sair() {
  if (!estado.alteracoes.size) return true;
  if (!window.confirm('Há alterações não salvas na projeção. Descartar?')) return false;
  estado.alteracoes.clear();
  return true;
}

export async function render(el, { usuario, dataBase, recarregar }) {
  el.innerHTML = carregando(10);
  estado.dados = await api(`/api/projecao?data=${dataBase}`);
  estado.alteracoes.clear();
  const d = estado.dados;
  estado.ano ??= d.mes_atual.slice(0, 4);
  if (estado.setor === null) estado.setor = d.setores.some((s) => s.codigo === usuario.perfil) ? usuario.perfil : '';
  const anos = [...new Set(d.meses.map((m) => m.slice(0, 4)))];
  const todas = d.setores.flatMap((s) => s.linhas);
  const somaMes = (m) => todas.reduce((a, l) => a + (l.valores[m] ?? 0), 0);
  const proximo = d.meses[d.meses.indexOf(d.mes_atual) + 1];
  const editaveis = d.setores.filter((s) => s.editavel).map((s) => s.nome);

  el.innerHTML = `<div class="fade">
    <div class="cabecalho"><div>
      <div class="eyebrow">Projeção de custos</div><h2>Projeção por setor</h2>
      <p>${editaveis.length === d.setores.length ? 'Você pode editar todos os setores.' : editaveis.length ? `Você edita: ${esc(editaveis.join(', '))}.` : 'Somente leitura.'}
        Os totais por rubrica entram no "Projetado" do Resumo e do Painel.</p>
    </div><div class="row-flex sem-impressao">
      ${usuario.permissoes.administrar ? '<button class="btn secondary sm" id="gerenciar">Setores e linhas</button>' : ''}
    </div></div>
    <div class="kpis">
      <div class="card kpi"><p class="l">Projetado total</p><p class="v tab">${fmt.moeda(todas.reduce((a, l) => a + l.total, 0))}</p><p class="h">${todas.length} linhas ativas</p></div>
      <div class="card kpi destaque"><p class="l">Projetado no mês corrente</p><p class="v tab">${fmt.moeda(somaMes(d.mes_atual))}</p><p class="h">${fmt.mesLongo(d.mes_atual)}</p></div>
      <div class="card kpi"><p class="l">Projetado no próximo mês</p><p class="v tab">${fmt.moeda(proximo ? somaMes(proximo) : 0)}</p><p class="h">${fmt.mesLongo(proximo)}</p></div>
      <div class="card kpi"><p class="l">Rubricas acima da viabilidade</p><p class="v tab">${d.rubricas.filter((r) => r.saldo < 0).length}</p><p class="h">realizado + a pagar + projetado</p></div>
    </div>
    <div class="barra-ferramentas">
      <div class="chips" id="setores"><button class="chip" data-setor="">Todos</button>
        ${d.setores.map((s) => `<button class="chip" data-setor="${esc(s.codigo)}">${esc(s.nome)}${s.editavel ? '' : ' 🔒'}</button>`).join('')}</div>
      <div class="row-flex"><label class="row-flex muted" style="gap:6px;font-size:13px">
          <input type="checkbox" id="so-valor" ${estado.soComValor ? 'checked' : ''}/> Só linhas com valor</label>
        <div class="chips" id="anos">${anos.map((a) => `<button class="chip" data-ano="${a}">${a}</button>`).join('')}</div></div>
    </div>
    <div id="grade"></div>
    <p class="sub" style="margin-top:28px">Consumo da viabilidade por rubrica</p>
    <div id="rubricas">${tabelaRubricas()}</div>
    <div class="barra-salvar" role="status"><b></b>
      <button class="btn inverse sm" id="descartar">Descartar</button>
      <button class="btn primary sm" id="salvar">Salvar projeção</button></div>
  </div>`;

  const desenhar = () => {
    el.querySelector('#grade').innerHTML = grade();
    focarMesCorrente(el.querySelector('#grade'));
    el.querySelectorAll('[data-setor]').forEach((b) => b.classList.toggle('on', b.dataset.setor === estado.setor));
    el.querySelectorAll('[data-ano]').forEach((b) => b.classList.toggle('on', b.dataset.ano === estado.ano));
  };
  el.querySelectorAll('#setores [data-setor]').forEach((b) => (b.onclick = () => { estado.setor = b.dataset.setor; desenhar(); }));
  el.querySelectorAll('#anos [data-ano]').forEach((b) => (b.onclick = () => { estado.ano = b.dataset.ano; desenhar(); }));
  el.querySelector('#so-valor').onchange = (e) => { estado.soComValor = e.target.checked; desenhar(); };
  el.querySelector('#gerenciar')?.addEventListener('click', () => gerenciarLinhas(recarregar));

  const gradeEl = el.querySelector('#grade');
  gradeEl.addEventListener('focusin', (e) => { if (e.target.matches('input:not([readonly])')) e.target.select(); });
  gradeEl.addEventListener('change', (e) => { if (e.target.matches('input')) registrar(e.target, el); });
  gradeEl.addEventListener('paste', (e) => { if (e.target.matches('input:not([readonly])')) colar(e, el); });
  gradeEl.addEventListener('keydown', (e) => {
    if (!e.target.matches('input')) return;
    if (e.key === 'Enter' || e.key === 'ArrowDown') { e.preventDefault(); registrar(e.target, el); mover(e.target, 1); }
    if (e.key === 'ArrowUp') { e.preventDefault(); registrar(e.target, el); mover(e.target, -1); }
    if (e.key === 'Escape') { const l = linhaPorId(Number(e.target.dataset.linha)); const v = valorAtual(l, e.target.dataset.mes); e.target.value = v ? fmt.numero(v) : ''; }
  });

  el.querySelector('#descartar').onclick = () => { estado.alteracoes.clear(); desenhar(); atualizarTotais(el); };
  el.querySelector('#salvar').onclick = async (e) => {
    const botao = e.currentTarget;
    botao.disabled = true;
    botao.innerHTML = '<span class="spin"></span>Salvando';
    try {
      const itens = [...estado.alteracoes].map(([k, valor]) => { const [linha, mes] = k.split('|'); return { linha_id: Number(linha), mes, valor }; });
      const { salvos } = await api(`/api/projecao?data=${dataBase}`, { metodo: 'PUT', corpo: itens });
      estado.alteracoes.clear();
      toast('Projeção salva', { texto: `${salvos} valor(es) atualizados. Resumo e Painel já refletem a mudança.` });
      await render(el, { usuario, dataBase, recarregar });
    } catch (erro) {
      erroToast(erro);
      botao.disabled = false;
      botao.textContent = 'Salvar projeção';
    }
  };
  desenhar();
}
