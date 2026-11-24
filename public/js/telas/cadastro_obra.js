// Cadastro de obra em 3 passos: dados principais, viabilidade por rubrica e linhas de projeção.
// A obra nova recebe o mesmo relatório das demais (mesmas fórmulas); só os dados são dela.
// Em modo edição (obra existente) abre apenas os dados principais.
import { api, erroToast, esc, fmt, lerNumero, toast } from '../util.js';

const PASSOS = ['Dados principais', 'Viabilidade', 'Linhas de projeção'];

/** "Joy+ Brooklin" → "joy-brooklin" (código da obra na URL e no banco). */
const codigoDe = (nome) => nome.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
  .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 31);

export function abrirCadastro({ obra = null, obras = [], aoSalvar }) {
  const edicao = Boolean(obra);
  const base = obras[0];                                  // referência para rubricas e abas padrão
  const estado = {
    passo: 0,
    dados: {
      nome: obra?.nome || '', codigo: obra?.codigo || '', empresa_spe: obra?.empresa_spe ?? '',
      cliente_investidor: obra?.cliente_investidor ?? '', historico_aporte_investidor: obra?.historico_aporte_investidor || '',
      graph_item_id: obra?.graph_item_id || '', arquivo_excel: obra?.arquivo_excel || '',
      abas: { ...(obra?.abas || {}) }, ordem: obra?.ordem ?? obras.length, ativo: obra?.ativo !== false,
    },
    codigoManual: edicao,
    viabilidade: null,                                     // rubrica → valor (carregado no passo 2)
    linhasDe: 'padrao',
    arquivos: null,
  };

  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `<div class="card modal modal-largo" role="dialog" aria-modal="true">
    <div class="body"><h3>${edicao ? `Configurar ${esc(obra.nome)}` : 'Nova obra'}</h3>
      ${edicao ? '' : `<ol class="passos">${PASSOS.map((p, i) => `<li data-passo="${i}">${i + 1}. ${p}</li>`).join('')}</ol>`}
      <div class="conteudo-passo"></div></div>
    <div class="foot"><button class="btn ghost" data-acao="cancelar">Cancelar</button>
      <button class="btn secondary" data-acao="voltar">Voltar</button>
      <button class="btn primary" data-acao="avancar"></button></div></div>`;
  document.body.append(overlay);
  const fechar = () => overlay.remove();
  const corpo = overlay.querySelector('.conteudo-passo');
  const botao = (acao) => overlay.querySelector(`[data-acao=${acao}]`);

  // ---------------------------------------------------------------- passo 1: dados principais
  async function passoDados() {
    const d = estado.dados;
    const campo = (nome, rotulo, valor, extra = '', ajuda = '') => `<div class="field"><label>${rotulo}</label>
      <input name="${nome}" value="${esc(valor ?? '')}" ${extra} />${ajuda ? `<small>${ajuda}</small>` : ''}</div>`;
    corpo.innerHTML = `<div class="grid form-obra">
        ${campo('nome', 'Nome da obra', d.nome, 'placeholder="Ex.: Brooklin" required')}
        ${campo('codigo', 'Código (na URL e no banco)', d.codigo, edicao ? 'disabled' : 'placeholder="gerado a partir do nome"',
          edicao ? 'Não muda depois de criado' : 'Letras minúsculas, números e hífen')}
        <div class="field campo-largo"><label>Arquivo de dados no SharePoint (pasta 06 - API)</label>
          <select name="graph_item_id"><option value="">Carregando arquivos…</option></select>
          <small>Mesmo modelo do arquivo da Evans (BD´s_JOY_&lt;OBRA&gt;).</small></div>
        ${campo('empresa_spe', 'Empresa SPE (código no UAU)', d.empresa_spe, 'inputmode="numeric" placeholder="Ex.: 67"')}
        ${campo('cliente_investidor', 'Cliente investidor (Recebidas)', d.cliente_investidor, 'inputmode="numeric"', 'Código do cliente cujos recebimentos são aporte')}
        ${campo('historico_aporte_investidor', 'Histórico do aporte (Controle Entradas)', d.historico_aporte_investidor, '', 'Texto exato do lançamento de aporte do investidor')}
      </div>
      <details class="avancado"><summary>Opções avançadas</summary>
        <div class="grid form-obra" style="margin-top:12px">
          ${campo('arquivo_excel', 'Planilha de controle local', d.arquivo_excel, 'placeholder="Controle - Joy+ <Obra>.xlsm"', 'Só para carga inicial e conferência local')}
          ${campo('ordem', 'Ordem na tela inicial', d.ordem, 'inputmode="numeric"')}
          ${edicao ? `<label class="row-flex muted" style="gap:6px"><input type="checkbox" name="ativo" ${d.ativo ? 'checked' : ''} /> Obra ativa</label>` : ''}
        </div>
        <p class="sub" style="margin-top:16px">Nome das abas no arquivo (só se for diferente do padrão)</p>
        <div class="grid form-obra">${(base?.fontes || []).map((f) => campo(`aba_${f.codigo}`, esc(f.titulo),
          d.abas[f.codigo] || '', `placeholder="${esc(f.aba_padrao)}"`)).join('')}</div>
      </details>`;
    const nome = corpo.querySelector('[name=nome]');
    const codigo = corpo.querySelector('[name=codigo]');
    nome.addEventListener('input', () => { if (!estado.codigoManual) codigo.value = codigoDe(nome.value); });
    codigo.addEventListener('input', () => { estado.codigoManual = true; });
    nome.focus();

    const seletor = corpo.querySelector('[name=graph_item_id]');
    try {
      estado.arquivos ??= await api('/api/sharepoint/arquivos');
      const atual = d.graph_item_id;
      seletor.innerHTML = '<option value="">Escolha o arquivo…</option>' + estado.arquivos.map((a) => {
        const deOutra = a.obra && a.id !== obra?.graph_item_id;
        return `<option value="${esc(a.id)}" ${a.id === atual ? 'selected' : ''}>${esc(a.nome)}${deOutra ? ` · já usado por ${esc(a.obra)}` : ''}</option>`;
      }).join('') + (atual && !estado.arquivos.some((a) => a.id === atual) ? `<option value="${esc(atual)}" selected>${esc(atual)} (fora da pasta)</option>` : '');
    } catch (erro) {
      seletor.outerHTML = `<input name="graph_item_id" value="${esc(d.graph_item_id)}" placeholder="item id do arquivo" />`;
      toast('Não foi possível listar a pasta do SharePoint', { tipo: 'warning', texto: `${erro.message} Informe o item id do arquivo.` });
    }
  }

  function lerDados() {
    const v = (nome) => corpo.querySelector(`[name=${nome}]`)?.value.trim() ?? '';
    const d = estado.dados;
    Object.assign(d, {
      nome: v('nome'), codigo: edicao ? d.codigo : v('codigo'), graph_item_id: v('graph_item_id'),
      empresa_spe: v('empresa_spe'), cliente_investidor: v('cliente_investidor'),
      historico_aporte_investidor: v('historico_aporte_investidor'), arquivo_excel: v('arquivo_excel'),
      ordem: Number(v('ordem') || 0), ativo: edicao ? corpo.querySelector('[name=ativo]')?.checked !== false : true,
      abas: Object.fromEntries((base?.fontes || []).map((f) => [f.codigo, v(`aba_${f.codigo}`)]).filter(([, a]) => a)),
    });
    if (!d.nome) throw new Error('Informe o nome da obra.');
    if (!/^[a-z0-9][a-z0-9-]{1,30}$/.test(d.codigo)) throw new Error('Código inválido: use letras minúsculas, números e hífen.');
    if (!edicao && obras.some((o) => o.codigo === d.codigo)) throw new Error(`Já existe uma obra com o código "${d.codigo}".`);
    if (d.empresa_spe && !/^\d+$/.test(String(d.empresa_spe))) throw new Error('Empresa SPE precisa ser um número.');
    if (d.cliente_investidor && !/^\d+$/.test(String(d.cliente_investidor))) throw new Error('Cliente investidor precisa ser um número.');
  }

  // ---------------------------------------------------------------- passo 2: viabilidade
  /** Valor do campo; se o texto não foi alterado, usa o valor completo guardado (sem perder casas). */
  const valorDoCampo = (input) => {
    const exato = Number(input.dataset.exato || 0);
    const mostrado = exato ? fmt.numero(exato) : '';
    return input.value.trim() === mostrado ? exato : lerNumero(input.value);
  };

  async function passoViabilidade() {
    if (!estado.viabilidade) {
      const referencia = base ? (await api(`/api/obras/${encodeURIComponent(base.codigo)}/parametros`)).viabilidade : {};
      estado.viabilidade = Object.fromEntries(Object.keys(referencia).map((r) => [r, 0]));
    }
    const rubricas = Object.keys(estado.viabilidade);
    corpo.innerHTML = `<p>Valor previsto na viabilidade (EVE) para cada rubrica. Pode ajustar depois em API's › Viabilidade.</p>
      <div class="row-flex" style="margin:12px 0">
        <label class="row-flex muted" style="gap:6px">Copiar de
          <select class="campo" id="copiar-viab" style="width:auto">${obras.map((o) => `<option value="${esc(o.codigo)}">${esc(o.nome)}</option>`).join('')}</select></label>
        <button class="btn secondary sm" id="aplicar-copia">Copiar valores</button>
        <button class="btn ghost sm" id="zerar">Zerar</button>
        <span class="total-viab">Total <b id="total-viab"></b></span>
      </div>
      <div class="grid form-viab">${rubricas.map((r) => `<div class="field"><label>${esc(r)}</label>
        <input data-rubrica="${esc(r)}" data-exato="${estado.viabilidade[r] || 0}" value="${estado.viabilidade[r] ? fmt.numero(estado.viabilidade[r]) : ''}" inputmode="decimal" placeholder="0,00" /></div>`).join('')}</div>`;
    const somar = () => {
      const total = [...corpo.querySelectorAll('[data-rubrica]')].reduce((a, i) => a + (valorDoCampo(i) || 0), 0);
      corpo.querySelector('#total-viab').textContent = fmt.moeda(total);
    };
    corpo.addEventListener('input', somar);
    corpo.querySelector('#zerar').onclick = () => { corpo.querySelectorAll('[data-rubrica]').forEach((i) => { i.value = ''; i.dataset.exato = 0; }); somar(); };
    corpo.querySelector('#aplicar-copia').onclick = async () => {
      try {
        const { viabilidade } = await api(`/api/obras/${encodeURIComponent(corpo.querySelector('#copiar-viab').value)}/parametros`);
        corpo.querySelectorAll('[data-rubrica]').forEach((i) => {
          const v = viabilidade[i.dataset.rubrica];
          i.value = v ? fmt.numero(v) : '';
          i.dataset.exato = v || 0;                 // valor completo (o campo mostra 2 casas)
        });
        somar();
      } catch (erro) { erroToast(erro); }
    };
    somar();
  }

  function lerViabilidade() {
    if (!corpo.querySelector('[data-rubrica]')) return;
    for (const input of corpo.querySelectorAll('[data-rubrica]')) {
      const valor = valorDoCampo(input);
      if (Number.isNaN(valor)) throw new Error(`Valor inválido em "${input.dataset.rubrica}".`);
      estado.viabilidade[input.dataset.rubrica] = valor || 0;
    }
  }

  // ---------------------------------------------------------------- passo 3: linhas de projeção
  async function passoLinhas() {
    corpo.innerHTML = `<p>Setores e linhas de projeção da obra (cada linha soma em uma rubrica do relatório).
        Podem ser ajustados depois em Projeção › Setores e linhas.</p>
      <div class="opcoes-linhas">
        <label class="opcao"><input type="radio" name="linhas" value="padrao" ${estado.linhasDe === 'padrao' ? 'checked' : ''} />
          <span><b>Modelo padrão</b><small>Marketing, Projetos e Incorporação, com as linhas definidas para a Evans</small></span></label>
        ${obras.map((o) => `<label class="opcao"><input type="radio" name="linhas" value="${esc(o.codigo)}" ${estado.linhasDe === o.codigo ? 'checked' : ''} />
          <span><b>Copiar de ${esc(o.nome)}</b><small>Mesmos setores e linhas, sem os valores projetados</small></span></label>`).join('')}
      </div>
      <div class="previa-linhas" id="previa"></div>`;
    const previa = async () => {
      const origem = corpo.querySelector('[name=linhas]:checked').value;
      estado.linhasDe = origem;
      const alvo = corpo.querySelector('#previa');
      if (origem === 'padrao') { alvo.innerHTML = ''; return; }
      try {
        const setores = (await api(`/api/obras/${encodeURIComponent(origem)}/setores`)).filter((s) => s.ativo);
        alvo.innerHTML = setores.map((s) => `<div><b>${esc(s.nome)}</b> <span class="muted">· ${s.linhas.filter((l) => l.ativo).length} linhas</span></div>`).join('');
      } catch (erro) { alvo.innerHTML = ''; erroToast(erro); }
    };
    corpo.querySelectorAll('[name=linhas]').forEach((r) => r.addEventListener('change', previa));
    previa();
  }

  // ---------------------------------------------------------------- salvar e primeira carga
  async function salvar() {
    const d = estado.dados;
    const corpoPedido = { ...d, empresa_spe: d.empresa_spe || null, cliente_investidor: d.cliente_investidor || null,
      historico_aporte_investidor: d.historico_aporte_investidor || null, graph_item_id: d.graph_item_id || null,
      arquivo_excel: d.arquivo_excel || null };
    if (!edicao) Object.assign(corpoPedido, { viabilidade: estado.viabilidade, linhas_de: estado.linhasDe });
    await api('/api/obras', { metodo: 'POST', corpo: corpoPedido });
    if (edicao || !d.graph_item_id) {
      toast(edicao ? 'Obra atualizada' : 'Obra criada', { texto: d.graph_item_id ? '' : 'Escolha o arquivo de dados para carregar a obra.' });
      fechar();
      aoSalvar(edicao ? null : d.codigo);
      return;
    }
    await primeiraCarga(d.codigo);
  }

  async function primeiraCarga(codigo) {
    const fontes = base?.fontes || [];
    corpo.innerHTML = `<div class="alert a-success"><b>Obra ${esc(estado.dados.nome)} criada</b>
      <div>Agora vou buscar os dados no SharePoint (uma tabela por vez).</div></div>
      <ul class="progresso-carga">${fontes.map((f) => `<li data-fonte="${f.codigo}"><span class="spin"></span> ${esc(f.titulo)}</li>`).join('')}</ul>`;
    overlay.querySelector('.foot').innerHTML = '<button class="btn primary" disabled>Carregando…</button>';
    let erros = 0;
    for (const f of fontes) {
      const item = corpo.querySelector(`[data-fonte=${f.codigo}]`);
      try {
        const [r] = await api(`/api/obras/${encodeURIComponent(codigo)}/fontes/atualizar`, { metodo: 'POST', corpo: { origem: 'graph', fontes: [f.codigo] } });
        erros += r.status === 'ok' ? 0 : 1;
        item.innerHTML = `${r.status === 'ok' ? '<span class="badge b-success">OK</span>' : '<span class="badge b-error">Erro</span>'} ${esc(f.titulo)}${r.mensagem ? ` <small class="muted">${esc(r.mensagem)}</small>` : ''}`;
      } catch (erro) {
        erros += 1;
        item.innerHTML = `<span class="badge b-error">Erro</span> ${esc(f.titulo)} <small class="muted">${esc(erro.message)}</small>`;
      }
    }
    overlay.querySelector('.foot').innerHTML = '<button class="btn primary" data-acao="abrir">Abrir a obra</button>';
    overlay.querySelector('[data-acao=abrir]').onclick = () => { fechar(); aoSalvar(codigo); };
    if (erros) toast(`${erros} tabela(s) com erro`, { tipo: 'warning', texto: 'Confira em API\'s › Fontes da obra.' });
  }

  // ---------------------------------------------------------------- navegação entre passos
  const telas = [passoDados, passoViabilidade, passoLinhas];
  const leituras = [lerDados, lerViabilidade, () => {}];
  const ultimo = () => (edicao ? 0 : PASSOS.length - 1);

  async function mostrar() {
    overlay.querySelectorAll('[data-passo]').forEach((li) => {
      const i = Number(li.dataset.passo);
      li.classList.toggle('on', i === estado.passo);
      li.classList.toggle('feito', i < estado.passo);
    });
    botao('voltar').hidden = estado.passo === 0;
    botao('avancar').textContent = estado.passo === ultimo() ? (edicao ? 'Salvar' : 'Criar obra') : 'Próximo';
    try { await telas[estado.passo](); } catch (erro) { erroToast(erro); }
  }

  botao('cancelar').onclick = fechar;
  botao('voltar').onclick = () => { try { leituras[estado.passo](); } catch { /* volta sem validar */ } estado.passo -= 1; mostrar(); };
  botao('avancar').onclick = async () => {
    const b = botao('avancar');
    try {
      leituras[estado.passo]();
      if (estado.passo < ultimo()) { estado.passo += 1; await mostrar(); return; }
      b.disabled = true;
      b.innerHTML = '<span class="spin"></span>Salvando';
      await salvar();
    } catch (erro) {
      erroToast(erro);
      if (b.isConnected) { b.disabled = false; b.textContent = estado.passo === ultimo() ? (edicao ? 'Salvar' : 'Criar obra') : 'Próximo'; }
    }
  };
  overlay.addEventListener('keydown', (e) => { if (e.key === 'Escape') fechar(); });
  mostrar();
}
