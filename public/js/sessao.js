// Sessão do usuário: Supabase Auth em produção; seletor de perfil no modo local de desenvolvimento.
const SUPABASE_JS = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/+esm';
const CHAVE_LOCAL = 'aporte_usuario_local';

let configuracao = null;
let cliente = null;
let definirSenhaPendente = false;

const lerLocal = () => { try { return localStorage.getItem(CHAVE_LOCAL); } catch { return null; } };
const gravarLocal = (valor) => {
  try { valor ? localStorage.setItem(CHAVE_LOCAL, valor) : localStorage.removeItem(CHAVE_LOCAL); } catch { /* sem storage */ }
};

export async function iniciarSessao() {
  configuracao = await fetch('/api/config').then((r) => r.json());
  if (configuracao.modo === 'supabase') {
    // Links de convite/recuperação chegam com type=invite|recovery no fragmento da URL.
    definirSenhaPendente = /type=(invite|recovery)/.test(location.hash);
    const { createClient } = await import(SUPABASE_JS);
    cliente = createClient(configuracao.supabase_url, configuracao.supabase_anon_key, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
    cliente.auth.onAuthStateChange((evento) => { if (evento === 'PASSWORD_RECOVERY') definirSenhaPendente = true; });
    await cliente.auth.getSession();
    if (definirSenhaPendente) history.replaceState(null, '', location.pathname);
  }
  return configuracao;
}

export const modoLocal = () => configuracao?.modo === 'local';
export const usuariosLocais = () => configuracao?.usuarios || [];
export const precisaDefinirSenha = () => definirSenhaPendente;

export async function token() {
  if (modoLocal()) {
    const id = lerLocal();
    return id ? `local:${id}` : null;
  }
  const { data } = await cliente.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function entrar(email, senha) {
  const { error } = await cliente.auth.signInWithPassword({ email, password: senha });
  if (error) throw new Error(error.message === 'Invalid login credentials' ? 'E-mail ou senha inválidos.' : error.message);
}

export function entrarLocal(usuarioId) { gravarLocal(usuarioId); }

export async function sair() {
  if (modoLocal()) return gravarLocal(null);
  await cliente.auth.signOut();
}

export async function definirSenha(nova) {
  if (nova.length < 8) throw new Error('A senha precisa ter ao menos 8 caracteres.');
  const { error } = await cliente.auth.updateUser({ password: nova });
  if (error) throw new Error(error.message);
  definirSenhaPendente = false;
}

export async function recuperarSenha(email) {
  const { error } = await cliente.auth.resetPasswordForEmail(email, { redirectTo: location.origin });
  if (error) throw new Error(error.message);
}
