// Aba API's: validador de atualização das fontes, pendências de classificação,
// saldos bancários (lançamento manual), parâmetros, usuários e histórico.
import { api, carregando, erroToast, esc, fmt, lerNumero, modal, toast } from '../util.js';

let subAba = 'fontes';

function statusFonte(f) {
  if (!f.ultima) return ['b-neutral', 'Sem carga'];
  if (f.ultima.status === 'erro') return f.ultima_ok ? ['b-warning', 'Falhou · usando última carga'] : ['b-error', 'Erro'];
  if (f.pendentes) return ['b-warning', `${f.pendentes} pendência(s)`];
  return ['b-success', 'OK'];
}

function cartaoFonte(f) {
  const [classe, rotulo] = statusFonte(f);
  const ok = f.ultima_ok;
  const variacao = f.variacao_linhas === null ? '—' : `${f.variacao_linhas > 0 ? '+' : ''}${f.variacao_linhas}`;
  return `<div class="card fonte">
    <div class="topo"><div><h3>${esc(f.titulo)}</h3><div class="aba">Aba "${esc(f.aba)}"</div></div>
      <span class="badge ${classe}">${esc(rotulo)}</span></div>
    <dl>
      <dt>Linhas na última carga</dt><dt>Variação</dt>
      <dd>${ok ? ok.linhas : '—'}</dd><dd>${variacao}</dd>
      <dt>Registros usados no cálculo</dt><dt>Valor total</dt>
      <dd>${f.registros}</dd><dd>${fmt.numero(f.valor_total)}</dd>
      <dt>Última carga válida</dt><dt>Origem · duração</dt>
      <dd>${ok ? fmt.dataHora(ok.iniciado_em) : '—'}</dd><dd>${ok ? `${ok.origem === 'graph' ? 'SharePoint' : 'Excel'} · ${ok.duracao_s}s` : '—'}</dd>
    </dl>
    ${f.ultima?.status === 'erro' ? `<div class="erro"><b>${fmt.dataHora(f.ultima.iniciado_em)}</b> · ${esc(f.ultima.mensagem)}</div>` : ''}
    ${f.pendentes ? `<button class="btn secondary sm" data-pendentes="${f.codigo}">Classificar ${f.pendentes} lançamento(s)</button>` : ''}
  </div>`;
}

async function abrirPendentes(codigo, rubricas, recarregar) {
  const pendentes = await api(`/api/fontes/${codigo}/pendentes`);
  const opcoes = rubricas.map((r) => `<option>${esc(r)}</option>`).join('');
  const linhas = pendentes.map((p, i) => {
    const valor = p.TotalLiquido ?? p.Valor_es;
    const data = p.DataPagamento ?? p.Data_es;
    return `<div class="formulario" style="grid-template-columns:1.2fr 1fr;padding:10px 0;border-bottom:1px solid var(--border)">
      <div><b>${esc(p.concat)}</b><div class="muted" style="font-size:12px">${typeof data === 'number' ? 'serial ' + data : esc(fmt.data(String(data ?? '')))} · ${fmt.numero(valor)}</div></div>
      <select class="campo" data-i="${i}"><option value="">Classificar como…</option>${opcoes}</select></div>`;
  }).join('');
  modal({
    titulo: 'Lançamentos sem classificação',
    conteudo: `<p>Na planilha estes lançamentos dariam #N/D no DePara. Classifique para que entrem no cálculo; a escolha fica gravada no DePara.</p>${linhas}`,
    acoes: [{ rotulo: 'Salvar classificações', classe: 'primary', ao: async (el) => {
      const escolhas = [...el.querySelectorAll('select[data-i]')].filter((s) => s.value);
      for (const s of escolhas) {
        await api(`/api/fontes/${codigo}/classificar`, { metodo: 'POST',
          corpo: { concat: pendentes[s.dataset.i].concat, classificacao: s.value } });
      }
      toast(`${escolhas.length} lançamento(s) classificados`);
      recarregar();
    } }],
  });
}

async function fontes(el, ctx) {
  const dados = await api('/api/fontes');
  const ultima = dados.fontes.map((f) => f.ultima_ok?.iniciado_em).filter(Boolean).sort().pop();
  const falhas = dados.fontes.filter((f) => f.ultima?.status === 'erro');
  const pendentes = dados.fontes.reduce((a, f) => a + f.pendentes, 0);
  el.innerHTML = `
    <div class="kpis">
      <div class="card kpi"><p class="l">Última atualização válida</p><p class="v tab">${fmt.dataHora(ultima)}</p></div>
      <div class="card kpi"><p class="l">Fontes OK</p><p class="v tab">${dados.fontes.length - falhas.length} de ${dados.fontes.length}</p></div>
      <div class="card kpi"><p class="l">Pendências de classificação</p><p class="v tab">${pendentes}</p></div>
      <div class="card kpi"><p class="l">Conexão SharePoint</p><p class="v tab">${dados.graph_configurado ? 'Configurada' : 'Sem credenciais'}</p></div>
    </div>
    ${falhas.length ? `<div class="alert a-warning" style="margin-bottom:16px"><b>${falhas.length} fonte(s) falharam na última atualização</b>
      <div>O cálculo continua usando a última carga válida de cada fonte. ${esc(falhas[0].ultima.mensagem)}</div></div>` : ''}
    <div class="row-flex" style="margin-bottom:16px">
      <button class="btn primary" id="atualizar-graph">Atualizar do SharePoint</button>
      ${dados.excel_disponivel ? '<button class="btn secondary" id="atualizar-excel" title="Lê as tabelas do Controle - Joy+ Evans.xlsm da pasta do projeto">Importar do Excel local</button>' : ''}
    </div>
    <div class="fontes">${dados.fontes.map(cartaoFonte).join('')}</div>
    <p class="sub" style="margin-top:28px">Últimas cargas</p>
    <div class="sheet"><table><thead><tr><th class="first">Fonte</th><th>Data</th><th>Origem</th><th>Status</th><th>Linhas</th><th>Duração</th><th style="text-align:left">Mensagem</th></tr></thead>
      <tbody>${dados.fontes.flatMap((f) => f.historico.slice(0, 3).map((c) => `<tr><td class="first">${esc(f.titulo)}</td>
        <td>${fmt.dataHora(c.iniciado_em)}</td><td>${c.origem === 'graph' ? 'SharePoint' : 'Excel'}</td>
        <td><span class="badge ${c.status === 'ok' ? 'b-success' : 'b-error'}">${c.status === 'ok' ? 'OK' : 'Erro'}</span></td>
        <td>${c.linhas ?? '—'}</td><td>${c.duracao_s ?? '—'}s</td><td style="text-align:left;white-space:normal;min-width:260px">${esc(c.mensagem || '')}</td></tr>`)).join('')}</tbody></table></div>`;

  const atualizar = async (origem, botao) => {
    botao.disabled = true;
    botao.innerHTML = '<span class="spin"></span>Atualizando';
    try {
      const relatorio = await api('/api/fontes/atualizar', { metodo: 'POST', corpo: { origem } });
      const erros = relatorio.filter((r) => r.status === 'erro');
      if (erros.length) toast(`${erros.length} fonte(s) com erro`, { tipo: 'warning', texto: erros[0].mensagem, duracao: 7000 });
      else toast('Fontes atualizadas', { texto: `${relatorio.length} tabelas validadas.` });
    } catch (erro) { erroToast(erro); }
    ctx.recarregar();
  };
  el.querySelector('#atualizar-graph').onclick = (e) => atualizar('graph', e.currentTarget);
  el.querySelector('#atualizar-excel')?.addEventListener('click', (e) => atualizar('excel', e.currentTarget));
  el.querySelectorAll('[data-pendentes]').forEach((b) => (b.onclick = () => abrirPendentes(b.dataset.pendentes, dados.rubricas, ctx.recarregar)));
}

async function saldos(el, ctx) {
  const lista = await api('/api/saldos');
  const pode = ctx.usuario.permissoes.editar_saldos;
  el.innerHTML = `
    <div class="alert a-info" style="margin-bottom:16px"><b>Saldo bancário por lançamento manual</b>
      <div>O Resumo usa, para cada conta, o saldo do último dia lançado no mês (regra da aba Saldo da planilha).</div></div>
    ${pode ? `<div class="card pad" style="margin-bottom:16px"><form class="formulario" id="form-saldo">
      <div class="field"><label>Conta</label><input name="conta" required placeholder="98672-8" /></div>
      <div class="field"><label>Descrição</label><input name="descricao" placeholder="ITAU - SPE Evans" /></div>
      <div class="field"><label>Data</label><input name="data" type="date" required /></div>
      <div class="field"><label>Saldo</label><input name="saldo" inputmode="decimal" required placeholder="0,00" /></div>
      <button class="btn primary" type="submit">Lançar saldo</button></form></div>` : ''}
    <div class="sheet" style="max-height:60vh"><table><thead><tr><th class="first">Conta</th><th>Data</th><th>Saldo</th><th style="text-align:left">Descrição</th><th></th></tr></thead>
    <tbody>${lista.map((s) => `<tr><td class="first">${esc(s.conta)}</td><td>${fmt.data(s.data)}</td><td>${fmt.numero(s.saldo)}</td>
      <td style="text-align:left">${esc(s.descricao || '')}</td>
      <td>${pode ? `<button class="btn ghost sm" data-excluir="${s.id}">Excluir</button>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
  el.querySelector('#form-saldo')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.currentTarget;
    const saldo = lerNumero(f.saldo.value);
    if (Number.isNaN(saldo)) return toast('Saldo inválido', { tipo: 'error' });
    try {
      await api('/api/saldos', { metodo: 'POST', corpo: { conta: f.conta.value, descricao: f.descricao.value, data: f.data.value, saldo } });
      toast('Saldo lançado');
      ctx.recarregar();
    } catch (erro) { erroToast(erro); }
  });
  el.querySelectorAll('[data-excluir]').forEach((b) => (b.onclick = () => modal({
    titulo: 'Excluir saldo?', conteudo: '<p>O lançamento será removido do cálculo.</p>',
    acoes: [{ rotulo: 'Excluir', classe: 'danger', ao: async () => {
      await api(`/api/saldos/${b.dataset.excluir}`, { metodo: 'DELETE' });
      toast('Saldo excluído');
      ctx.recarregar();
    } }] })));
}

async function parametros(el, ctx) {
  const { viabilidade } = await api('/api/parametros');
  const pode = ctx.usuario.permissoes.editar_premissas;
  el.innerHTML = `<div class="alert a-info" style="margin-bottom:16px"><b>Valor de viabilidade (EVE) por rubrica</b>
      <div>Coluna D do Resumo e X do Painel. As premissas do aporte ficam no botão "Premissas" da aba Resumo.</div></div>
    <div class="card pad"><form id="form-viab"><div class="formulario">
      ${Object.entries(viabilidade).map(([r, v]) => `<div class="field"><label>${esc(r)}</label>
        <input name="${esc(r)}" value="${fmt.numero(v)}" inputmode="decimal" ${pode ? '' : 'disabled'} /></div>`).join('')}
    </div>${pode ? '<div class="row-flex" style="margin-top:16px"><button class="btn primary" type="submit">Salvar viabilidade</button></div>' : ''}</form></div>`;
  el.querySelector('#form-viab').onsubmit = async (e) => {
    e.preventDefault();
    const corpo = Object.fromEntries([...e.currentTarget.querySelectorAll('input')].map((i) => [i.name, lerNumero(i.value)]));
    if (Object.values(corpo).some(Number.isNaN)) return toast('Há valores inválidos', { tipo: 'error' });
    try { await api('/api/parametros/viabilidade', { metodo: 'PUT', corpo }); toast('Viabilidade salva'); ctx.recarregar(); }
    catch (erro) { erroToast(erro); }
  };
}

async function usuarios(el, ctx) {
  const { usuarios: lista, perfis } = await api('/api/usuarios');
  const opcoes = (atual) => Object.entries(perfis).map(([k, v]) => `<option value="${k}" ${k === atual ? 'selected' : ''}>${esc(v)} (${k})</option>`).join('');
  el.innerHTML = `<div class="card pad" style="margin-bottom:16px"><form class="formulario" id="form-usuario">
      <div class="field"><label>Nome</label><input name="nome" required /></div>
      <div class="field"><label>E-mail</label><input name="email" type="email" required /></div>
      <div class="field"><label>Perfil</label><select name="perfil">${opcoes('mkt')}</select></div>
      <div class="field"><label>Senha inicial (opcional)</label><input name="senha" type="password" autocomplete="new-password" />
        <small>Em branco: o usuário recebe um convite por e-mail</small></div>
      <button class="btn primary" type="submit">Cadastrar usuário</button></form></div>
    <div class="sheet"><table><thead><tr><th class="first">Nome</th><th style="text-align:left">E-mail</th><th style="text-align:left">Perfil</th><th>Situação</th><th></th></tr></thead>
    <tbody>${lista.map((u) => `<tr><td class="first">${esc(u.nome)}</td><td style="text-align:left">${esc(u.email)}</td>
      <td style="text-align:left"><select class="campo" data-perfil="${esc(u.usuario_id)}" style="height:32px">${opcoes(u.perfil)}</select></td>
      <td><span class="badge ${u.ativo ? 'b-success' : 'b-neutral'}">${u.ativo ? 'Ativo' : 'Inativo'}</span></td>
      <td><button class="btn ghost sm" data-ativo="${esc(u.usuario_id)}" data-valor="${u.ativo ? 0 : 1}">${u.ativo ? 'Desativar' : 'Reativar'}</button>
        <button class="btn ghost sm" data-senha="${esc(u.usuario_id)}">Redefinir senha</button></td></tr>`).join('')}</tbody></table></div>`;
  const alterar = async (id, corpo, msg) => {
    try { await api(`/api/usuarios/${encodeURIComponent(id)}`, { metodo: 'PATCH', corpo }); toast(msg); ctx.recarregar(); } catch (erro) { erroToast(erro); }
  };
  el.querySelector('#form-usuario').onsubmit = async (e) => {
    e.preventDefault();
    const f = e.currentTarget;
    try {
      await api('/api/usuarios', { metodo: 'POST', corpo: { nome: f.nome.value, email: f.email.value, perfil: f.perfil.value, senha: f.senha.value || null } });
      toast('Usuário cadastrado', { texto: f.senha.value ? '' : 'Convite enviado por e-mail.' });
      ctx.recarregar();
    } catch (erro) { erroToast(erro); }
  };
  el.querySelectorAll('[data-perfil]').forEach((s) => (s.onchange = () => alterar(s.dataset.perfil, { perfil: s.value }, 'Perfil alterado')));
  el.querySelectorAll('[data-ativo]').forEach((b) => (b.onclick = () => alterar(b.dataset.ativo, { ativo: b.dataset.valor === '1' }, 'Situação alterada')));
  el.querySelectorAll('[data-senha]').forEach((b) => (b.onclick = () => modal({
    titulo: 'Redefinir senha', conteudo: '<div class="field" style="margin-top:16px"><label>Nova senha</label><input type="password" name="nova" autocomplete="new-password" /></div>',
    acoes: [{ rotulo: 'Salvar', classe: 'primary', ao: (m) => alterar(b.dataset.senha, { senha: m.querySelector('[name=nova]').value }, 'Senha redefinida') }] })));
}

async function historico(el) {
  const itens = await api('/api/historico?limite=300');
  el.innerHTML = `<div class="sheet" style="max-height:70vh"><table><thead><tr><th class="first">Quando</th><th style="text-align:left">Usuário</th>
    <th style="text-align:left">Ação</th><th style="text-align:left">Detalhe</th></tr></thead>
    <tbody>${itens.map((h) => `<tr><td class="first">${fmt.dataHora(h.quando)}</td><td style="text-align:left">${esc(h.usuario || 'sistema')}</td>
      <td style="text-align:left"><span class="badge b-neutral">${esc(h.acao)}</span></td>
      <td style="text-align:left;white-space:normal;max-width:640px" class="muted">${esc((h.detalhe || '').slice(0, 300))}</td></tr>`).join('')}</tbody></table></div>`;
}

const SUB_ABAS = [
  { id: 'fontes', titulo: 'Fontes (APIs)', tela: fontes },
  { id: 'saldos', titulo: 'Saldos bancários', tela: saldos },
  { id: 'parametros', titulo: 'Viabilidade', tela: parametros },
  { id: 'usuarios', titulo: 'Usuários', tela: usuarios, permissao: 'gerir_usuarios' },
  { id: 'historico', titulo: 'Histórico', tela: historico },
];

export async function render(el, ctx) {
  const abas = SUB_ABAS.filter((a) => !a.permissao || ctx.usuario.permissoes[a.permissao]);
  if (!abas.some((a) => a.id === subAba)) subAba = 'fontes';
  el.innerHTML = `<div class="fade"><div class="cabecalho"><div><div class="eyebrow">Validador de atualização</div>
      <h2>API's e dados de apoio</h2><p>Situação de cada tabela de origem, pendências e lançamentos manuais.</p></div></div>
    <div class="sub-abas" role="tablist">${abas.map((a) => `<button data-sub="${a.id}" class="${a.id === subAba ? 'on' : ''}">${a.titulo}</button>`).join('')}</div>
    <div id="sub-conteudo">${carregando(6)}</div></div>`;
  el.querySelectorAll('[data-sub]').forEach((b) => (b.onclick = () => { subAba = b.dataset.sub; render(el, ctx); }));
  await abas.find((a) => a.id === subAba).tela(el.querySelector('#sub-conteudo'), ctx);
}
