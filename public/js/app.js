// Inicialização: sessão, app shell, navegação por abas e data-base.
import { api, erroToast, esc, modal, toast } from './util.js';
import * as sessao from './sessao.js';
import * as resumo from './telas/resumo.js';
import * as dashboards from './telas/dashboards.js';
import * as painel from './telas/painel.js';
import * as projecao from './telas/projecao.js';
import * as apis from './telas/apis.js';

const ABAS = [
  { id: 'resumo', titulo: 'Resumo', tela: resumo, permissao: 'resumo.ver' },
  { id: 'dashboards', titulo: 'Dashboards', tela: dashboards, permissao: 'dashboards.ver' },
  { id: 'painel', titulo: 'Painel', tela: painel, permissao: 'painel.ver' },
  { id: 'projecao', titulo: 'Projeção', tela: projecao, permissao: 'projecao.ver' },
  { id: 'apis', titulo: "API's", tela: apis, permissao: 'apis.ver' },
];
const raiz = document.getElementById('raiz');
const hojeIso = () => new Date().toLocaleDateString('sv-SE');
const estado = { usuario: null, dataBase: hojeIso(), abaAtual: null };

const emBreve = (aba) => (estado.usuario.em_breve || []).includes(aba.id);
const abasVisiveis = () => ABAS.filter((a) => !a.permissao || estado.usuario.permissoes[a.permissao]);

// ------------------------------------------------------------------ telas de acesso
function cartaoAcesso(titulo, subtitulo, corpo) {
  raiz.innerHTML = `<div class="login"><div class="card fade">
    <img src="/assets/logo-joy.png" alt="Joy+" />
    <div class="eyebrow">Evans · Controladoria</div>
    <h1>${esc(titulo)}</h1><p>${esc(subtitulo)}</p>${corpo}</div></div>`;
  return raiz.querySelector('.card');
}

function aguardar(botao, texto) {
  botao.disabled = true;
  botao.innerHTML = `<span class="spin"></span>${esc(texto)}`;
}

function telaLogin(mensagem = '') {
  const alerta = mensagem ? `<div class="alert a-error"><b>${esc(mensagem)}</b></div>` : '';
  if (sessao.modoLocal()) {
    const usuarios = sessao.usuariosLocais();
    const cartao = cartaoAcesso('Relatório de Aporte', 'Modo local de desenvolvimento: escolha um perfil.', `
      <form id="form-login" class="grid">
        <div class="field"><label for="usuario">Usuário</label><select id="usuario">
          ${usuarios.map((u) => `<option value="${esc(u.usuario_id)}">${esc(u.nome)} · ${esc(u.perfil)}</option>`).join('')}
        </select>${usuarios.length ? '' : '<small class="err">Nenhum perfil cadastrado. Rode: python -m backend.app.migrar admin</small>'}</div>
        ${alerta}<button class="btn primary" type="submit" ${usuarios.length ? '' : 'disabled'}>Entrar</button></form>`);
    cartao.querySelector('form').onsubmit = (e) => { e.preventDefault(); sessao.entrarLocal(cartao.querySelector('#usuario').value); iniciar(); };
    return;
  }
  const cartao = cartaoAcesso('Relatório de Aporte', 'Análise de custos e projeção de aportes.', `
    <form id="form-login" class="grid" novalidate>
      <div class="field"><label for="email">E-mail</label><input id="email" type="email" autocomplete="username" required /></div>
      <div class="field"><label for="senha">Senha</label><input id="senha" type="password" autocomplete="current-password" required /></div>
      ${alerta}<button class="btn primary" type="submit">Entrar</button>
      <button class="btn ghost sm" type="button" id="esqueci">Esqueci minha senha</button></form>`);
  const form = cartao.querySelector('form');
  form.email.focus();
  form.onsubmit = async (e) => {
    e.preventDefault();
    aguardar(form.querySelector('[type=submit]'), 'Entrando');
    try { await sessao.entrar(form.email.value.trim(), form.senha.value); await iniciar(); }
    catch (erro) { telaLogin(erro.message); }
  };
  cartao.querySelector('#esqueci').onclick = async () => {
    const email = form.email.value.trim();
    if (!email) return toast('Informe o e-mail', { tipo: 'warning', texto: 'Digite o e-mail e clique de novo.' });
    try { await sessao.recuperarSenha(email); toast('Verifique seu e-mail', { texto: 'Enviamos o link para criar uma nova senha.' }); }
    catch (erro) { erroToast(erro); }
  };
}

function telaDefinirSenha() {
  const cartao = cartaoAcesso('Defina sua senha', 'Crie a senha que você vai usar para entrar.', `
    <form class="grid"><div class="field"><label for="nova">Nova senha</label>
      <input id="nova" type="password" autocomplete="new-password" required /><small>Mínimo de 8 caracteres</small></div>
      <button class="btn primary" type="submit">Salvar e entrar</button></form>`);
  const form = cartao.querySelector('form');
  form.onsubmit = async (e) => {
    e.preventDefault();
    try { await sessao.definirSenha(form.nova.value); toast('Senha definida'); await iniciar(); }
    catch (erro) { erroToast(erro); }
  };
}

// ------------------------------------------------------------------ shell
function montarShell() {
  const u = estado.usuario;
  raiz.innerHTML = `
    <header class="app"><div class="in">
      <img class="logo" src="/assets/logo-joy.png" alt="Joy+" />
      <nav aria-label="Abas">${abasVisiveis().map((a) => `<a href="#${a.id}" data-aba="${a.id}">${esc(a.titulo)}${emBreve(a) ? ' <span class="badge b-neutral em-breve">Em breve</span>' : ''}</a>`).join('')}</nav>
      <div class="direita">
        <label class="data-base" title="Data usada como 'hoje' nos cálculos (a planilha usa HOJE())">
          <span>Data-base</span><input type="date" id="data-base" value="${estado.dataBase}" />
        </label>
        ${sessao.modoLocal() ? `<label class="troca-perfil" title="Modo local: troque de perfil para testar os acessos">
          <span>Perfil</span><select id="trocar-perfil">${sessao.usuariosLocais().map((l) => `<option value="${esc(l.usuario_id)}" ${l.usuario_id === u.usuario_id ? 'selected' : ''}>${esc(l.nome)}</option>`).join('')}</select></label>`
          : `<div class="u"><b>${esc(u.nome)}</b><span>${esc(u.perfil_nome)}</span></div>`}
        ${sessao.modoLocal() || sessao.semLogin() ? '' : '<button class="btn inverse sm" id="conta">Conta</button>'}
        ${sessao.semLogin() ? '' : '<button class="btn inverse sm" id="sair">Sair</button>'}
      </div>
    </div></header>
    ${sessao.modoLocal() ? `<div class="alert a-warning faixa-local"><b>Modo local de teste</b> · perfil <b>${esc(u.perfil_nome)}</b> (${esc(u.perfil)}) · sem Supabase, dados em SQLite.</div>` : ''}
    <main id="conteudo"></main>`;
  document.getElementById('trocar-perfil')?.addEventListener('change', (e) => {
    if (estado.abaAtual?.tela.sair && !estado.abaAtual.tela.sair()) { e.target.value = u.usuario_id; return; }
    estado.abaAtual = null;
    sessao.entrarLocal(e.target.value);
    iniciar();
  });
  document.getElementById('sair')?.addEventListener('click', async () => { await sessao.sair(); telaLogin(); });
  document.getElementById('conta')?.addEventListener('click', () => modal({
    titulo: 'Trocar senha',
    conteudo: `<div class="field" style="margin-top:16px"><label>Nova senha</label>
      <input type="password" name="nova" autocomplete="new-password" /><small>Mínimo de 8 caracteres</small></div>`,
    acoes: [{ rotulo: 'Salvar', classe: 'primary', ao: async (el) => {
      await sessao.definirSenha(el.querySelector('[name=nova]').value);
      toast('Senha alterada');
    } }],
  }));
  document.getElementById('data-base').onchange = (e) => { estado.dataBase = e.target.value || hojeIso(); renderizar(); };
}

async function renderizar() {
  const abas = abasVisiveis();
  const aba = abas.find((a) => a.id === location.hash.slice(1)) || abas[0];
  const conteudo = document.getElementById('conteudo');
  if (!aba) {
    conteudo.innerHTML = `<div class="card empty"><h3>Sem abas liberadas</h3>
      <p>Seu perfil ainda não tem acesso a nenhuma aba. Fale com a Controladoria.</p></div>`;
    return;
  }
  if (estado.abaAtual?.tela.sair && estado.abaAtual !== aba && !estado.abaAtual.tela.sair()) {
    location.hash = estado.abaAtual.id;       // alterações não salvas
    return;
  }
  estado.abaAtual = aba;
  document.querySelectorAll('header.app nav a').forEach((a) => a.classList.toggle('on', a.dataset.aba === aba.id));
  if (emBreve(aba)) {
    conteudo.innerHTML = `<div class="card empty fade"><span class="badge b-primary">Em breve</span>
      <h3>${esc(aba.titulo)} em construção</h3><p>Esta aba está sendo preparada e logo estará disponível.</p></div>`;
    return;
  }
  try {
    await aba.tela.render(conteudo, { usuario: estado.usuario, dataBase: estado.dataBase, recarregar: renderizar });
  } catch (erro) {
    if (erro.status === 401) return;
    conteudo.innerHTML = `<div class="alert a-error"><b>Erro ao carregar a aba</b><div>${esc(erro.message)}</div></div>`;
  }
}

async function iniciar() {
  if (sessao.precisaDefinirSenha()) return telaDefinirSenha();
  try {
    estado.usuario = await api('/api/eu');
  } catch (erro) {
    return telaLogin(erro.status === 401 && (await sessao.token()) ? 'Seu usuário ainda não tem perfil de acesso. Fale com a Controladoria.' : '');
  }
  montarShell();
  await renderizar();
}

window.addEventListener('hashchange', () => estado.usuario && renderizar());
window.addEventListener('sessao-expirada', () => { estado.usuario = null; telaLogin('Sua sessão expirou. Entre novamente.'); });
window.addEventListener('unhandledrejection', (e) => { if (e.reason?.status !== 401) erroToast(e.reason); });

sessao.iniciarSessao()
  .then(iniciar)
  .catch((erro) => { raiz.innerHTML = `<div class="alert a-error" style="margin:24px"><b>Não foi possível iniciar</b><div>${esc(erro.message)}</div></div>`; });
