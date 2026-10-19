// Utilitários compartilhados: formatação pt-BR, API, toasts e modal.
import { token } from './sessao.js';

const moedaFmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const numeroFmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compactoFmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', notation: 'compact', maximumFractionDigits: 1 });
const pctFmt =new Intl.NumberFormat('pt-BR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
const MESES = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];

const vazio = (v) => v === null || v === undefined || v === '';
export const ehNumero = (v) => typeof v === 'number' && Number.isFinite(v);

const semZeroNegativo = (v, limite) => (Math.abs(v) < limite ? 0 : v);   // evita "-0,00"

export const fmt = {
  moeda: (v) => (ehNumero(v) ? moedaFmt.format(semZeroNegativo(v, 0.005)) : vazio(v) ? '—' : String(v)),
  numero: (v) => (ehNumero(v) ? numeroFmt.format(semZeroNegativo(v, 0.005)) : vazio(v) ? '—' : String(v)),
  compacto: (v) => (ehNumero(v) ? compactoFmt.format(semZeroNegativo(v, 0.005)) : '—'),
  pct: (v) => (ehNumero(v) ? pctFmt.format(semZeroNegativo(v, 0.0005)) : '—'),
  data: (iso) => (iso ? iso.slice(0, 10).split('-').reverse().join('/') : '—'),
  dataHora: (iso) => (iso ? `${fmt.data(iso)} ${iso.slice(11, 16)}` : '—'),
  mes: (iso) => (iso ? `${MESES[Number(iso.slice(5, 7)) - 1]}/${iso.slice(2, 4)}` : '—'),
  mesLongo: (iso) => (iso ? `${MESES[Number(iso.slice(5, 7)) - 1]}/${iso.slice(0, 4)}` : '—'),
};

/** Converte "1.234,56", "R$ 150.000" ou "-12,5" em número; '' vira 0. */
export function lerNumero(texto) {
  const limpo = String(texto ?? '').replace(/[R$\s]/g, '');
  if (!limpo) return 0;
  const normal = limpo.includes(',') ? limpo.replace(/\./g, '').replace(',', '.') : limpo;
  const n = Number(normal);
  return Number.isFinite(n) ? n : NaN;
}

const MAPA_ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => MAPA_ESC[c]);

export function fimDoMes(data = new Date()) {
  const d = new Date(data.getFullYear(), data.getMonth() + 1, 0);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// ------------------------------------------------------------------ API
export class ErroApi extends Error {
  constructor(status, mensagem) { super(mensagem); this.status = status; }
}

export async function api(caminho, { metodo = 'GET', corpo } = {}) {
  const cabecalhos = corpo === undefined ? {} : { 'Content-Type': 'application/json' };
  const acesso = await token();
  if (acesso) cabecalhos.Authorization = `Bearer ${acesso}`;
  const resposta = await fetch(caminho, {
    method: metodo,
    headers: cabecalhos,
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    const detalhe = Array.isArray(dados.detail) ? dados.detail.map((d) => d.msg).join('; ') : dados.detail;
    if (resposta.status === 401) window.dispatchEvent(new CustomEvent('sessao-expirada'));
    throw new ErroApi(resposta.status, detalhe || `Erro ${resposta.status}`);
  }
  return dados;
}

// ------------------------------------------------------------------ feedback
export function toast(titulo, { tipo = 'success', texto = '', duracao = 3500 } = {}) {
  const caixa = document.createElement('div');
  caixa.className = `alert a-${tipo} toast`;
  caixa.innerHTML = `<b>${esc(titulo)}</b>${texto ? `<div>${esc(texto)}</div>` : ''}`;
  document.getElementById('toasts').append(caixa);
  setTimeout(() => caixa.remove(), duracao);
}

export const erroToast = (erro) => toast('Não foi possível concluir', { tipo: 'error', texto: erro.message, duracao: 6000 });

/** Abre um modal; `acoes` = [{rotulo, classe, ao}] — `ao` pode devolver false para manter aberto. */
export function modal({ titulo, conteudo = '', acoes = [] }) {
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `<div class="card modal" role="dialog" aria-modal="true" aria-label="${esc(titulo)}">
    <div class="body"><h3>${esc(titulo)}</h3><div class="conteudo">${conteudo}</div></div>
    <div class="foot"></div></div>`;
  const fechar = () => overlay.remove();
  const rodape = overlay.querySelector('.foot');
  for (const acao of [{ rotulo: 'Cancelar', classe: 'ghost' }, ...acoes]) {
    const botao = document.createElement('button');
    botao.className = `btn ${acao.classe || 'secondary'}`;
    botao.textContent = acao.rotulo;
    botao.onclick = async () => {
      if (!acao.ao) return fechar();
      botao.disabled = true;
      try { if ((await acao.ao(overlay)) !== false) fechar(); }
      catch (erro) { erroToast(erro); }
      finally { botao.disabled = false; }
    };
    rodape.append(botao);
  }
  overlay.addEventListener('click', (e) => { if (e.target === overlay) fechar(); });
  overlay.addEventListener('keydown', (e) => { if (e.key === 'Escape') fechar(); });
  document.body.append(overlay);
  overlay.querySelector('input, select, button')?.focus();
  return overlay;
}

/** Rola a grade para deixar a coluna do mês corrente visível logo após a primeira coluna. */
export function focarMesCorrente(container) {
  const grade = container.querySelector('.sheet');
  const coluna = grade?.querySelector('thead th.cur');
  const primeira = grade?.querySelector('thead th.first');
  if (coluna && primeira) grade.scrollLeft = Math.max(0, coluna.offsetLeft - primeira.offsetWidth - 3 * coluna.offsetWidth);
}

export const carregando = (linhas = 6) =>
  `<div class="card pad grid" style="gap:12px">${'<div class="skel"></div>'.repeat(linhas)}</div>`;
