// Inicialização: sessão, app shell, tela inicial de obras, abas da obra e data-base.
// URL: #inicio (cards das obras) ou #<obra>/<aba> (ex.: #berrini/projecao).
import { api, definirObra, erroToast, esc, modal, toast } from './util.js';
import * as sessao from './sessao.js';
import * as inicio from './telas/inicio.js';
import * as resumo from './telas/resumo.js';
import * as aportes from './telas/aportes.js';
import * as dashboards from './telas/dashboards.js';
import * as painel from './telas/painel.js';
import * as projecao from './telas/projecao.js';
import * as apis from './telas/apis.js';

const ABAS = [
  { id: 'resumo', titulo: 'Resumo', tela: resumo, permissao: 'resumo.ver' },
  { id: 'aportes', titulo: 'Aportes', tela: aportes, permissao: 'resumo.ver' },
  { id: 'dashboards', titulo: 'Dashboards', tela: dashboards, permissao: 'dashboards.ver' },
  { id: 'painel', titulo: 'Painel', tela: painel, permissao: 'painel.ver' },
  { id: 'projecao', titulo: 'Projeção', tela: projecao, permissao: 'projecao.ver' },
  { id: 'apis', titulo: "API's", tela: apis, permissao: 'apis.ver' },
];
const raiz = document.getElementById('raiz');
const hojeIso = () => new Date().toLocaleDateString('sv-SE');
const estado = { usuario: null, dataBase: hojeIso(), abaAtual: null, obras: [], obra: null };

/** Rota da URL: { obra, aba } dentro de uma obra; { obra: null } na tela inicial. */
function lerRota() {
  const [obra, aba] = location.hash.slice(1).split('/');
  return estado.obras.some((o) => o.codigo === obra) ? { obra, aba } : { obra: null };
}
const rota = (aba, obra = estado.obra?.codigo) => `#${obra}/${aba}`;

const emBreve = (aba) => (estado.usuario.em_breve || []).includes(aba.id);
const abasVisiveis = () => ABAS.filter((a) => !a.permissao || estado.usuario.permissoes[a.permissao]);

// ------------------------------------------------------------------ telas de acesso
// Sorriso (a curva do "y" da marca) e o "+" azul, como grafismo do painel da marca.
const DESENHO_MARCA = `<svg class="login-desenho" viewBox="0 0 480 300" aria-hidden="true">
  <path class="sorriso" d="M40 40 A 200 200 0 0 0 440 40" />
  <path class="mais" d="M372 0h20v34h34v20h-34v34h-20v-34h-34v-20h34z" /></svg>`;

function cartaoAcesso(titulo, subtitulo, corpo) {
  raiz.innerHTML = `<div class="login">
    <aside class="login-marca">
      <img class="login-logo" src="/assets/logo-joy-tagline-branco.png" alt="Joy+ · a felicidade mora aqui" />
      <div class="login-marca-texto"><div class="eyebrow">Controladoria</div>
        <h2>Relatório de Aporte</h2>
        <p>Custos, despesas, projeção e aportes de cada obra, num só lugar.</p></div>
      ${DESENHO_MARCA}
    </aside>
    <section class="login-painel"><div class="login-card fade">
      <div class="eyebrow">Joy+ · Controladoria</div>
      <h1>${esc(titulo)}</h1><p>${esc(subtitulo)}</p>${corpo}</div>
      <div class="login-rodape">Unità Engenharia · uso interno</div></section></div>`;
  return raiz.querySelector('.login-card');
}

const LOGO_MICROSOFT = `<svg class="ms-logo" viewBox="0 0 21 21" aria-hidden="true"><path fill="#f25022" d="M0 0h10v10H0z"/>
  <path fill="#7fba00" d="M11 0h10v10H11z"/><path fill="#00a4ef" d="M0 11h10v10H0z"/><path fill="#ffb900" d="M11 11h10v10H11z"/></svg>`;

function aguardar(botao, texto) {
  botao.disabled = true;
  botao.innerHTML = `<span class="spin"></span>${esc(texto)}`;
}

function telaLogin(mensagem = '') {
  const alerta = mensagem ? `<div class="alert a-error"><b>${esc(mensagem)}</b></div>` : '';
  if (sessao.modoMicrosoft()) {
    const dominio = sessao.dominioMicrosoft();
    const cartao = cartaoAcesso('Bem-vindo', 'Entre com a sua conta corporativa para acessar o relatório.', `
      <div class="acesso">${alerta}
        <button class="btn primary btn-microsoft" type="button" id="entrar-microsoft">${LOGO_MICROSOFT}Entrar com Microsoft 365</button>
        ${dominio ? `<small class="nota-login">Use sua conta @${esc(dominio)}.</small>` : ''}</div>`);
    const botao = cartao.querySelector('#entrar-microsoft');
    botao.focus();
    botao.onclick = () => { aguardar(botao, 'Abrindo a Microsoft'); sessao.entrarMicrosoft(); };
    return;
  }
  if (sessao.modoLocal()) {
    const usuarios = sessao.usuariosLocais();
    const cartao = cartaoAcesso('Bem-vindo', 'Modo local de desenvolvimento: escolha um perfil.', `
      <form id="form-login" class="grid">
        <div class="field"><label for="usuario">Usuário</label><select id="usuario">
          ${usuarios.map((u) => `<option value="${esc(u.usuario_id)}">${esc(u.nome)} · ${esc(u.perfil)}</option>`).join('')}
        </select>${usuarios.length ? '' : '<small class="err">Nenhum perfil cadastrado. Rode: python -m backend.app.migrar admin</small>'}</div>
        ${alerta}<button class="btn primary" type="submit" ${usuarios.length ? '' : 'disabled'}>Entrar</button></form>`);
    cartao.querySelector('form').onsubmit = (e) => { e.preventDefault(); sessao.entrarLocal(cartao.querySelector('#usuario').value); iniciar(); };
    return;
  }
  const cartao = cartaoAcesso('Bem-vindo', 'Entre com seu e-mail e senha para acessar o relatório.', `
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
      <a href="#inicio" class="marca" title="Obras"><img class="logo" src="/assets/logo-joy.png" alt="Joy+" /></a>
      <div class="contexto" id="contexto"></div>
      <nav aria-label="Abas" id="abas"></nav>
      <div class="direita">
        <label class="data-base" title="Data usada como 'hoje' nos cálculos (a planilha usa HOJE())">
          <span>Data-base</span><input type="date" id="data-base" value="${estado.dataBase}" />
        </label>
        ${sessao.modoLocal() ? `<label class="troca-perfil" title="Modo local: troque de perfil para testar os acessos">
          <span>Perfil</span><select id="trocar-perfil">${sessao.usuariosLocais().map((l) => `<option value="${esc(l.usuario_id)}" ${l.usuario_id === u.usuario_id ? 'selected' : ''}>${esc(l.nome)}</option>`).join('')}</select></label>`
          : `<div class="u"><b>${esc(u.nome)}</b><span>${esc(u.perfil_nome)}</span></div>`}
        ${sessao.modoLocal() || sessao.semLogin() || sessao.modoMicrosoft() ? '' : '<button class="btn inverse sm" id="conta">Conta</button>'}
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

/** Topo: na tela inicial só "Obras"; dentro de uma obra, o caminho de volta, o nome e as abas. */
function atualizarCabecalho(aba) {
  const contexto = document.getElementById('contexto');
  const abas = document.getElementById('abas');
  if (!estado.obra) {
    contexto.innerHTML = '<span class="contexto-titulo">Obras</span>';
    abas.innerHTML = '';
    document.title = 'Obras · Relatório de Aporte · Joy+';
    return;
  }
  contexto.innerHTML = `<a href="#inicio" class="voltar" title="Voltar para as obras">‹ Obras</a>
    <span class="contexto-obra">${esc(estado.obra.nome)}</span>`;
  abas.innerHTML = abasVisiveis().map((a) => `<a href="${rota(a.id)}" data-aba="${a.id}" class="${a.id === aba.id ? 'on' : ''}">${esc(a.titulo)}${emBreve(a) ? ' <span class="badge b-neutral em-breve">Em breve</span>' : ''}</a>`).join('');
  document.title = `${estado.obra.nome} · Relatório de Aporte · Joy+`;
}

async function renderizar() {
  const conteudo = document.getElementById('conteudo');
  const { obra: codigoObra, aba: idAba } = lerRota();
  const abas = abasVisiveis();
  const aba = codigoObra ? abas.find((a) => a.id === idAba) || abas[0] : null;
  const saindo = estado.abaAtual && (estado.abaAtual !== aba || estado.obra?.codigo !== codigoObra);
  if (saindo && estado.abaAtual.tela.sair && !estado.abaAtual.tela.sair()) {
    history.replaceState(null, '', rota(estado.abaAtual.id));   // alterações não salvas: fica onde estava
    return;
  }
  estado.abaAtual = aba;
  estado.obra = codigoObra ? estado.obras.find((o) => o.codigo === codigoObra) : null;
  definirObra(estado.obra?.codigo || null);
  const destino = estado.obra ? rota(aba?.id || 'resumo') : '#inicio';
  if (location.hash !== destino) history.replaceState(null, '', destino);
  atualizarCabecalho(aba || {});
  const contexto = { usuario: estado.usuario, dataBase: estado.dataBase, recarregar: renderizar, obra: estado.obra,
                     obras: estado.obras };
  try {
    if (!estado.obra) {
      await inicio.render(conteudo, { ...contexto, aoMudarObras: recarregarObras });
      return;
    }
    if (!aba) {
      conteudo.innerHTML = `<div class="card empty"><h3>Sem abas liberadas</h3>
        <p>Seu perfil ainda não tem acesso a nenhuma aba. Fale com a Controladoria.</p></div>`;
      return;
    }
    if (emBreve(aba)) {
      conteudo.innerHTML = `<div class="card empty fade"><span class="badge b-primary">Em breve</span>
        <h3>${esc(aba.titulo)} em construção</h3><p>Esta aba está sendo preparada e logo estará disponível.</p></div>`;
      return;
    }
    await aba.tela.render(conteudo, contexto);
  } catch (erro) {
    if (erro.status === 401) return;
    conteudo.innerHTML = `<div class="alert a-error"><b>Erro ao carregar a tela</b><div>${esc(erro.message)}</div></div>`;
  }
}

/** Depois de cadastrar ou alterar uma obra: atualiza a lista e, se pedido, abre a obra. */
async function recarregarObras(abrir) {
  estado.obras = (await api('/api/obras')).filter((o) => o.ativo !== false);
  if (abrir) location.hash = rota('apis', abrir);
  else renderizar();
}

async function iniciar() {
  if (sessao.precisaDefinirSenha()) return telaDefinirSenha();
  const erroLogin = sessao.erroDoLogin();
  if (erroLogin) return telaLogin(erroLogin);
  try {
    [estado.usuario, estado.obras] = await Promise.all([api('/api/eu'), api('/api/obras')]);
    estado.obras = estado.obras.filter((o) => o.ativo !== false);
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
