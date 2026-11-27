// Aba Resumo: reproduz a aba Resumo da planilha — tabela de custos e despesas por rubrica
// (à esquerda) e o Relatório de Aporte (à direita). Tudo segue o mês da data-base.
// Os gráficos ficam na aba Dashboards.
import { abrirRubrica } from './rubrica_card.js';
import { editarViabilidade } from './viabilidade.js';
import { gerarPdfBase64 } from '../pdf.js';
import { api, carregando, ehNumero, esc, fmt, lerNumero, modal, toast } from '../util.js';

const GRUPOS = [
  { id: 'despesa', total: 24, titulo: 'Total de Despesas' },
  { id: 'custo', total: 43, titulo: 'Total de Custos' },
  { id: 'aporte' },
];
const CAMPOS = ['pago_ate', 'pago_mes', 'a_pagar', 'projetado_mes', 'projetado_proximo', 'total_mes'];

// ------------------------------------------------------------------ tabela (colunas B:U)
// Como o formato contábil da planilha: zero aparece como "-".
const zero = (v) => !ehNumero(v) || Math.abs(v) < 0.005;
const numero = (v) => (zero(v) ? '-' : fmt.numero(v));
const celula = (l, campo) => (campo in l ? numero(l[campo]) : '');

function linhaTabela(l, classe = '') {
  const pct = !ehNumero(l.pct_consumido) ? '' : Math.abs(l.pct_consumido) < 0.0005 ? '-' : fmt.pct(l.pct_consumido);
  const acima = ehNumero(l.pct_consumido) && l.pct_consumido > 1;
  // Rubricas de custo e despesa abrem o card com os lançamentos classificados nelas.
  const abre = (l.grupo === 'custo' || l.grupo === 'despesa') && classe === '';
  const nome = abre ? `<button class="segmentador" data-rubrica="${esc(l.rubrica)}" aria-haspopup="dialog"
      title="Analisar os lançamentos desta rubrica"><span class="seta">▸</span>${esc(l.rubrica)}</button>` : esc(l.rubrica);
  return `<tr class="${classe}${abre ? ' linha-segmentador' : ''}"><td class="first">${nome}</td>
    <td>${'viabilidade' in l ? numero(l.viabilidade) : ''}</td>
    <td class="${acima ? 'alerta' : ''}">${pct}</td>
    ${CAMPOS.map((c) => `<td class="${c.startsWith('projetado') ? 'proj' : ''}">${celula(l, c)}</td>`).join('')}</tr>`;
}

function somaGrupo(linhas) {
  const soma = (campo) => linhas.reduce((a, l) => a + (l[campo] || 0), 0);
  return Object.fromEntries(['viabilidade', ...CAMPOS].map((c) => [c, soma(c)]));
}

// Títulos da planilha terminam na data de referência ("Pago Total até 30/09/2026"): ela vai
// para a segunda linha, para o cabeçalho caber em colunas estreitas.
function titulo(texto) {
  const t = texto.replace(/\s+/g, ' ').trim();
  const m = t.match(/^(.*?)\s+((?:até\s+)?\S*\d{4})$/i);
  return m ? `${esc(m[1])} <small>${esc(m[2])}</small>` : esc(t);
}

function tabela(d) {
  const t = d.titulos;
  let corpo = linhaTabela({ ...d.total, rubrica: 'Total' }, 'grande');
  for (const g of GRUPOS) {
    const linhas = d.linhas.filter((l) => l.grupo === g.id && l.linha_excel !== g.total);
    corpo += linhas.map((l) => linhaTabela(l)).join('');
    if (g.total) {
      const total = somaGrupo(linhas);
      total.pct_consumido = total.viabilidade ? (total.pago_ate + total.pago_mes) / total.viabilidade : null;
      corpo += linhaTabela({ ...total, rubrica: g.titulo }, 'total');
    }
  }
  return `<div class="sheet tabela-resumo"><table>
    <colgroup><col class="c-rubrica" /><col class="c-viab" /><col class="c-pct" />${'<col />'.repeat(6)}</colgroup><thead><tr>
      <th class="first">Rubricas</th><th>Valor Viabilidade</th><th>% Consumido</th>
      <th>${titulo(t.pago_ate)}</th><th>${titulo(t.pago_mes)}</th><th>${titulo(t.a_pagar)}</th>
      <th>Projetado Mês</th><th>${titulo(t.projetado_proximo)}</th>
      <th title="Pago no mês + contas a pagar">Total Mês <small>(Pago + A Pagar)</small></th></tr></thead>
    <tbody>${corpo}</tbody></table></div>`;
}

// ------------------------------------------------------------------ Relatório de Aporte (colunas Y:Z)
// Explicações ficam num "i" clicável que abre um card de texto (não ocupam espaço na tela nem no PDF).
const info = (texto) => `<button type="button" class="info-i sem-impressao" data-info="${esc(texto)}"
  aria-label="Explicação" title="Explicação">i</button>`;
let cardInfo = null;
function fecharInfo() { cardInfo?.remove(); cardInfo = null; }
function abrirInfo(botao) {
  const mesmo = cardInfo?.dono === botao;
  fecharInfo();
  if (mesmo) return;                                  // segundo clique no mesmo "i" fecha
  cardInfo = document.createElement('div');
  cardInfo.className = 'card card-info';
  cardInfo.setAttribute('role', 'dialog');
  cardInfo.dono = botao;
  cardInfo.innerHTML = `<p>${esc(botao.dataset.info)}</p>`;
  document.body.append(cardInfo);
  const r = botao.getBoundingClientRect();
  const largura = cardInfo.offsetWidth;
  cardInfo.style.top = `${window.scrollY + r.bottom + 6}px`;
  cardInfo.style.left = `${Math.max(8, Math.min(window.scrollX + r.left - largura / 2, window.scrollX + innerWidth - largura - 8))}px`;
}
document.addEventListener('click', (e) => {
  if (cardInfo && !cardInfo.contains(e.target) && !e.target.closest('[data-info]')) fecharInfo();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharInfo(); });
window.addEventListener('hashchange', fecharInfo);

const par = (rotulo, valor, classe = '') =>
  `<div class="par ${classe}"><span>${rotulo}</span><b>${valor}</b></div>`;
const moeda = (v) => fmt.moeda(v);
const valorAporte = (v) => (v > 0 ? fmt.moeda(v) : 'Sem aporte');

/** Rótulo da divisão do aporte da obra: "Investidor 85% · Joy+ 15%" ou "100% Joy+ (obra sem investidor)". */
const rotuloDivisao = (p) => (p.com_investidor
  ? `Investidor ${fmt.pct(p.investidor)} · Joy+ ${fmt.pct(p.joy)}` : '100% Joy+ · obra sem investidor');

function divisao(a, p) {
  if (!(a.aporte_total > 0)) return '';
  if (!p.com_investidor) {
    return `<div class="divisao-aporte"><div><span>Joy+ (100% · obra sem investidor)</span><b>${moeda(a.joy)}</b></div></div>`;
  }
  return `<div class="divisao-aporte"><div><span>Investidor (${fmt.pct(p.investidor)})</span><b>${moeda(a.investidor)}</b></div>
    <div><span>Joy+ (${fmt.pct(p.joy)})</span><b>${moeda(a.joy)}</b></div></div>`;
}

function blocoAporteMes(d) {
  const a = d.aporte_mes;
  return `<section class="card bloco-aporte destaque-aporte">
    <header class="bloco-topo"><p class="sub">Aporte necessário no mês · ${fmt.mesLongo(d.datas.mes_atual)}</p>
      ${info(`Aporte = custo do mês + caixa mínimo − saldo − receitas do mês. Receitas = tudo o que a aba Recebidas registra no mês (hoje, os aportes do investidor), então o valor acima é o que ainda falta aportar. Cobre as contas do mês e mantém ${moeda(a.caixa_minimo)} em caixa.`)}</header>
    <div class="heroi-linha"><p class="numero-heroi">${valorAporte(a.aporte_total)}</p>
    ${divisao(a, d.participacao)}</div>
    <div class="extrato">
      ${par(esc(d.titulos.saldo_anterior), moeda(a.saldo_anterior))}
      ${par('Receitas do mês (Recebidas)', moeda(a.receita_mes))}
      ${par(esc(d.titulos.custo_mes), moeda(a.custo_mes))}
      ${par('Caixa mínimo', moeda(a.caixa_minimo))}
    </div>
  </section>`;
}

function blocoConta(d) {
  const c = d.conta;
  return `<section class="card bloco-aporte bloco-conta">
    <p class="sub">Conta da SPE · ${fmt.mesLongo(d.datas.mes_atual)}</p>
    <div class="extrato">
      ${par('Saldo inicial (fim do mês anterior)', moeda(c.saldo_inicial))}
      ${par('(+) Receitas do mês (Recebidas)', moeda(c.receitas))}
      ${c.receitas_investidor ? par('dos quais aporte do investidor', moeda(c.receitas_investidor), 'sub-par') : ''}
      ${par('(+) Aporte necessário', moeda(c.aporte))}
      ${par('(−) Custos do mês (pago + a pagar + projetado)', moeda(-c.custos))}
      ${par('Saldo projetado no fim do mês', moeda(c.saldo_final), 'forte destaque')}
      ${par('Transferências da holding no mês', moeda(c.transferencias_holding))}
      ${par('Aporte a receber', moeda(c.aporte_a_receber), 'forte')}
    </div></section>`;
}

function blocoProximo(d) {
  const p = d.aporte_proximo;
  return `<section class="card bloco-aporte">
    <header class="bloco-topo"><p class="sub">Aporte do próximo mês · ${fmt.mesLongo(d.datas.proximo_mes)}</p>
      ${info('Custo projetado = projeção dos setores + contas a pagar com vencimento no próximo mês.')}</header>
    <p class="numero-heroi menor">${valorAporte(p.aporte_total)}</p>
    ${divisao(p, d.participacao)}
    <div class="extrato">
      ${par(esc(d.titulos.saldo_proximo), moeda(p.saldo_anterior))}
      ${par('Receita projetada', moeda(p.receita_projetada))}
      ${par(`${esc(d.titulos.custo_proximo)}${p.custo_automatico ? ' <span class="badge b-primary">automático</span>' : ''}`, moeda(p.custo_projetado))}
      ${par('Caixa mínimo', moeda(p.caixa_minimo))}
    </div>
  </section>`;
}

const STATUS_PARCELA = { recebido: ['b-success', 'Recebido'], parcial: ['b-warning', 'Parcial'], 'a receber': ['b-neutral', 'A receber'] };

function blocoCronograma(d, podeEditar) {
  const c = d.cronograma_aporte;
  const semAporte = !(c.total > 0);
  const parcelas = c.parcelas.map((p) => {
    const [classe, rotulo] = STATUS_PARCELA[p.status] || [];
    return `<div class="parcela">
      <div class="parcela-topo"><span><b>${p.parcela}ª parcela</b> · ${fmt.data(p.data)}</span>
        ${rotulo ? `<span class="badge ${classe}">${rotulo}</span>` : ''}</div>
      <div class="parcela-valor"><b>${moeda(p.valor)}</b><span class="muted">${fmt.pct(p.percentual / 100)} do aporte</span></div>
      <div class="par sub-par"><span>${rotuloDivisao(d.participacao)}</span><b>${d.participacao.com_investidor
        ? `${fmt.numero(p.investidor)} · ${fmt.numero(p.joy)}` : fmt.numero(p.joy)}</b></div>
    </div>`;
  }).join('');
  return `<section class="card bloco-aporte">
    <header class="bloco-topo"><p class="sub">Cronograma do aporte · ${fmt.mesLongo(d.datas.mes_atual)}
        ${!semAporte && !c.programado ? '<span class="badge b-neutral">não programado</span>' : ''}</p>
      <span class="row-flex" style="gap:6px">${!semAporte && !c.programado ? info('Ainda não programado: parcela única no dia 1.') : ''}
      ${podeEditar && !semAporte ? '<button class="btn secondary sm sem-impressao" id="cronograma">Programar</button>' : ''}</span></header>
    ${semAporte ? '<p class="muted" style="margin:0">Sem aporte necessário neste mês.</p>' : `
      <div class="parcelas">${parcelas}</div>
      <div class="extrato">
        ${par('Aporte necessário', moeda(c.total), 'forte destaque')}
        ${par('Já recebido da holding no mês', moeda(c.recebido))}
      </div>`}
  </section>`;
}

function editarCronograma(d, recarregar) {
  const c = d.cronograma_aporte;
  const mes = d.datas.mes_atual;
  const inicio = `${mes.slice(0, 8)}01`;
  const linhas = c.parcelas.map((p) => ({ data: p.data, percentual: p.percentual }));
  const dividir = () => {
    const n = linhas.length;
    const base = Math.floor((100 / n) * 10000) / 10000;
    linhas.forEach((l, i) => { l.percentual = i === n - 1 ? 100 - base * (n - 1) : base; });
  };
  const valorDe = (pct) => (c.total * pct) / 100;
  // A última parcela fica com o restante: as parcelas sempre fecham 100% do aporte.
  const completar = () => {
    const outras = linhas.slice(0, -1).reduce((a, l) => a + l.percentual, 0);
    linhas.at(-1).percentual = 100 - outras;
  };
  const html = () => {
    completar();
    const ultima = linhas.at(-1).percentual;
    const ok = ultima > 0.0001;
    return `<p>Aporte necessário de ${fmt.mesLongo(mes)}: <b>${moeda(c.total)}</b>. Defina em quantas vezes e em que datas
      ele será feito. As parcelas sempre somam o aporte do mês, mesmo que ele mude.</p>
      <div class="cronograma-edicao">
        <div class="cronograma-cab"><span>Data</span><span>Valor (R$)</span><span>% do aporte</span><span></span></div>
        ${linhas.map((l, i) => {
          const resto = i === linhas.length - 1;
          const trava = resto ? 'readonly tabindex="-1" title="Restante do aporte"' : '';
          const valor = resto ? c.total - linhas.slice(0, -1).reduce((a, x) => a + valorDe(x.percentual), 0) : valorDe(l.percentual);
          return `<div class="cronograma-linha ${resto ? 'restante' : ''}" data-i="${i}">
          <input type="date" class="campo" name="data" value="${esc(l.data)}" min="${inicio}" max="${mes}" />
          <input class="campo" name="valor" inputmode="decimal" value="${fmt.numero(valor)}" ${trava} />
          <input class="campo" name="percentual" inputmode="decimal" value="${fmt.numero(l.percentual)}" ${trava} />
          <button class="btn ghost sm" name="remover" ${linhas.length === 1 ? 'disabled' : ''} title="Remover parcela">✕</button>
        </div>`;
        }).join('')}
      </div>
      <div class="row-flex" style="margin-top:12px">
        <button class="btn secondary sm" name="adicionar" ${linhas.length >= 12 ? 'disabled' : ''}>+ Parcela</button>
        <button class="btn secondary sm" name="dividir">Dividir igualmente</button>
        <span class="${ok ? 'muted' : 'err'}" style="margin-left:auto">${ok
          ? `Última parcela = restante · total ${moeda(c.total)}`
          : 'As primeiras parcelas passam do aporte do mês: reduza algum valor.'}</span>
      </div>`;
  };
  const overlay = modal({
    titulo: 'Cronograma do aporte',
    conteudo: '<div class="cronograma"></div>',
    acoes: [
      { rotulo: 'Parcela única', classe: 'secondary', ao: async () => {
        await api('/obra/parametros/cronograma', { metodo: 'PUT', corpo: { mes, parcelas: [] } });
        toast('Cronograma removido', { texto: 'Volta a ser parcela única no dia 1.' });
        recarregar();
      } },
      { rotulo: 'Salvar cronograma', classe: 'primary', ao: async () => {
        if (linhas.some((l) => !l.data || l.data < inicio || l.data > mes)) throw new Error('Todas as datas precisam estar dentro do mês.');
        completar();
        if (linhas.at(-1).percentual <= 0.0001) throw new Error('As primeiras parcelas passam do aporte do mês.');
        await api('/obra/parametros/cronograma', { metodo: 'PUT', corpo: { mes, parcelas: linhas } });
        toast('Cronograma salvo', { texto: `${linhas.length} parcela(s).` });
        recarregar();
      } },
    ],
  });
  const area = overlay.querySelector('.cronograma');
  const desenhar = () => { area.innerHTML = html(); };
  area.addEventListener('change', (e) => {
    const linha = e.target.closest('[data-i]');
    if (!linha) return;
    const l = linhas[Number(linha.dataset.i)];
    if (e.target.name === 'data') l.data = e.target.value;
    if (e.target.name === 'valor') {
      const v = lerNumero(e.target.value);
      if (!Number.isNaN(v) && c.total > 0) l.percentual = (v / c.total) * 100;
    }
    if (e.target.name === 'percentual') {
      const v = lerNumero(e.target.value);
      if (!Number.isNaN(v)) l.percentual = v;
    }
    desenhar();
  });
  area.addEventListener('click', (e) => {
    const botao = e.target.closest('button');
    if (!botao) return;
    e.preventDefault();
    if (botao.name === 'remover') { linhas.splice(Number(botao.closest('[data-i]').dataset.i), 1); dividir(); }
    if (botao.name === 'adicionar') { linhas.push({ data: linhas.at(-1)?.data || inicio, percentual: 0 }); dividir(); }
    if (botao.name === 'dividir') dividir();
    desenhar();
  });
  desenhar();
}

// ------------------------------------------------------------------ premissas
async function editarPremissas(recarregar) {
  const { premissas: p } = await api('/obra/parametros');
  const campo = (nome, rotulo, ajuda = '') => `<div class="field"><label>${rotulo}</label>
    <input name="${nome}" value="${fmt.numero(p[nome])}" inputmode="decimal" />${ajuda ? `<small>${ajuda}</small>` : ''}</div>`;
  const numericos = ['caixa_minimo', 'caixa_minimo_proximo', 'receita_projetada_proximo', 'ajuste_saldo_banco'];
  const comInvestidor = p.participacao_investidor > 0;
  const pctTexto = (v) => fmt.numero(v * 100).replace(/,00$/, '');
  const caixa = modal({
    titulo: 'Premissas do aporte',
    fecharFora: false,
    conteudo: `<p>Valores informados manualmente. Custos, saldos e receitas do mês vêm das fontes.</p>
      <div class="grid" style="margin-top:16px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
        ${campo('caixa_minimo', 'Caixa mínimo (mês)')}${campo('caixa_minimo_proximo', 'Caixa mínimo (próximo)')}
        ${campo('receita_projetada_proximo', 'Receita projetada (próximo)')}
        ${campo('ajuste_saldo_banco', 'Ajuste do saldo banco', 'Painel H119')}
      </div>
      <fieldset class="grupo-viab" style="margin-top:16px"><legend>Divisão do aporte</legend>
        <label class="row-flex" style="gap:8px"><input type="checkbox" name="com_investidor" ${comInvestidor ? 'checked' : ''} />
          Obra com investidor</label>
        <div class="grid divisao-campos" style="margin-top:10px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr))" ${comInvestidor ? '' : 'hidden'}>
          <div class="field"><label>Investidor (%)</label><input name="pct_investidor" inputmode="decimal" value="${pctTexto(p.participacao_investidor)}" /></div>
          <div class="field"><label>Joy+ (%)</label><input name="pct_joy" value="${pctTexto(p.participacao_joy)}" disabled /></div>
        </div>
        <p class="nota" data-sem-investidor ${comInvestidor ? 'hidden' : ''}>Sem investidor, todo o aporte necessário fica com a Joy+ (100%).</p>
      </fieldset>
      <p class="nota" style="margin-top:16px">O cronograma do aporte (parcelas e datas) fica no bloco "Cronograma do aporte".</p>`,
    acoes: [{ rotulo: 'Salvar premissas', classe: 'primary', ao: async (el) => {
      const ler = (nome) => lerNumero(el.querySelector(`[name=${nome}]`).value);
      const corpo = Object.fromEntries(numericos.map((k) => [k, ler(k)]));
      if (Object.values(corpo).some((v) => Number.isNaN(v))) {
        throw new Error('Há valores inválidos.');
      }
      const pct = el.querySelector('[name=com_investidor]').checked ? ler('pct_investidor') : 0;
      if (Number.isNaN(pct) || pct < 0 || pct > 100) throw new Error('Participação do investidor: informe de 0 a 100%.');
      Object.assign(corpo, { participacao_investidor: pct / 100, participacao_joy: 1 - pct / 100 });
      await api('/obra/parametros/premissas', { metodo: 'PUT', corpo });
      toast('Premissas salvas');
      recarregar();
    } }],
  });
  const marcar = caixa.querySelector('[name=com_investidor]');
  const pctInv = caixa.querySelector('[name=pct_investidor]');
  marcar.onchange = () => {
    caixa.querySelector('.divisao-campos').hidden = !marcar.checked;
    caixa.querySelector('[data-sem-investidor]').hidden = marcar.checked;
    if (marcar.checked && !(lerNumero(pctInv.value) > 0)) { pctInv.value = '85'; pctInv.dispatchEvent(new Event('input')); }
  };
  pctInv.oninput = () => {
    const v = lerNumero(pctInv.value);
    caixa.querySelector('[name=pct_joy]').value = Number.isNaN(v) ? '' : fmt.numero(100 - v).replace(/,00$/, '');
  };
}

// ------------------------------------------------------------------ envio por e-mail
const separarEmails = (texto) => String(texto || '').split(/[\s,;]+/).map((e) => e.trim().toLowerCase()).filter(Boolean);
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** PDF do Resumo (o mesmo da impressão) pela conta Microsoft de quem está logado. */
async function enviarPorEmail(relatorio, ctx, d) {
  const { usuario, obra } = ctx;
  const destinatarios = await api('/obra/email/destinatarios');
  const mes = fmt.mesLongo(d.datas.mes_atual);
  const assunto = `Relatório de Aporte · ${obra.nome} · ${mes}`;
  const mensagem = `Olá,

Segue em anexo o Relatório de Aporte da obra ${obra.nome} referente a ${mes}.

Atenciosamente,
${usuario.nome || ''}`;
  const salvos = () => (destinatarios.length
    ? destinatarios.map((x) => `<label class="destinatario"><input type="checkbox" name="salvo" value="${esc(x.email)}" />
        <span>${esc(x.email)}</span>${x.ultimo_envio ? `<small>último envio ${fmt.data(x.ultimo_envio)}</small>` : ''}
        <button type="button" class="btn ghost sm remover" data-id="${x.id}" title="Tirar da lista" aria-label="Tirar ${esc(x.email)} da lista">×</button></label>`).join('')
    : '<small>Nenhum destinatário salvo ainda nesta obra.</small>');
  const caixa = modal({
    titulo: 'Enviar Resumo por e-mail',
    fecharFora: false,
    conteudo: `<div class="grid envio-email">
      <div class="field"><label>Destinatários salvos</label><div class="lista-destinatarios">${salvos()}</div></div>
      <div class="field"><label for="novos-dest">Novos destinatários</label>
        <input id="novos-dest" name="novos" type="text" placeholder="nome@empresa.com.br; outro@empresa.com.br" autocomplete="off" />
        <small>Separe por ponto e vírgula. Ficam salvos nesta obra para os próximos envios.</small></div>
      <div class="field"><label for="assunto-email">Assunto</label><input id="assunto-email" name="assunto" value="${esc(assunto)}" /></div>
      <div class="field"><label for="mensagem-email">Mensagem</label><textarea id="mensagem-email" name="mensagem" rows="6">${esc(mensagem)}</textarea></div>
      <small class="nota-envio">Sai da sua conta (${esc(usuario.email)}) e fica nos seus Itens Enviados. O anexo é o PDF do Resumo, igual ao da impressão.</small>
    </div>`,
    acoes: [{ rotulo: 'Enviar', classe: 'primary', ao: async (el) => {
      const para = [...el.querySelectorAll('[name=salvo]:checked')].map((c) => c.value)
        .concat(separarEmails(el.querySelector('[name=novos]').value));
      const invalidos = para.filter((e) => !EMAIL.test(e));
      if (invalidos.length) throw new Error(`E-mail inválido: ${invalidos.join(', ')}`);
      if (!para.length) throw new Error('Marque ou digite ao menos um destinatário.');
      const botao = el.querySelector('.foot .primary');
      botao.innerHTML = '<span class="spin"></span>Gerando PDF';
      try {
        const pdf = await gerarPdfBase64(relatorio);
        botao.innerHTML = '<span class="spin"></span>Enviando';
        const r = await api('/obra/resumo/enviar', { metodo: 'POST', corpo: {
          para, assunto: el.querySelector('[name=assunto]').value, mensagem: el.querySelector('[name=mensagem]').value,
          nome_arquivo: `Relatório de Aporte - ${obra.nome} - ${mes.replace('/', '-')}.pdf`, pdf_base64: pdf,
        } });
        toast('E-mail enviado', { texto: `Para ${r.enviado_para.join(', ')}` });
      } finally { botao.textContent = 'Enviar'; }
    } }],
  });
  caixa.querySelector('.lista-destinatarios').addEventListener('click', async (e) => {
    const botao = e.target.closest('.remover');
    if (!botao) return;
    e.preventDefault();
    botao.disabled = true;
    try {
      await api(`/obra/email/destinatarios/${botao.dataset.id}`, { metodo: 'DELETE' });
      destinatarios.splice(destinatarios.findIndex((x) => String(x.id) === botao.dataset.id), 1);
      caixa.querySelector('.lista-destinatarios').innerHTML = salvos();
    } catch (erro) { botao.disabled = false; toast('Não foi possível tirar da lista', { tipo: 'error', texto: erro.message }); }
  });
}

// ------------------------------------------------------------------ tela
export async function render(el, ctx) {
  const { usuario, dataBase, recarregar, obra } = ctx;
  el.innerHTML = carregando(10);
  const d = await api(`/obra/resumo?data=${dataBase}`);
  el.innerHTML = `<div class="fade">
    <div class="cabecalho"><div>
      <div class="eyebrow">Relatório de Aporte · ${esc(obra.nome)}</div><h2>Resumo de Custos e Despesas</h2>
      <p>Mês corrente <b>${fmt.mesLongo(d.datas.mes_atual)}</b> · mês de análise ${fmt.mesLongo(d.datas.mes_analise)} · última atualização ${fmt.dataHora(d.ultima_atualizacao)}</p>
    </div><div class="row-flex sem-impressao">
      ${usuario.permissoes['premissas.editar'] ? `<button class="btn secondary sm" id="viabilidade" title="Viabilidade (EVE) por rubrica de ${esc(obra.nome)}">Viabilidade</button>
        <button class="btn secondary sm" id="premissas">Premissas</button>` : ''}
      ${usuario.permissoes['resumo.enviar'] ? '<button class="btn secondary sm" id="enviar-email">Enviar por e-mail</button>' : ''}
      <button class="btn secondary sm" onclick="window.print()">Imprimir</button></div></div>
    <div class="resumo-planilha">
      <section class="relatorio-aporte" aria-label="Relatório de Aporte">
        ${blocoAporteMes(d)}${blocoCronograma(d, usuario.permissoes['premissas.editar'])}${blocoConta(d)}
      </section>
      <div class="resumo-tabela">${tabela(d)}</div>
    </div>
  </div>`;
  el.querySelector('#premissas')?.addEventListener('click', () => editarPremissas(recarregar));
  el.querySelector('#enviar-email')?.addEventListener('click', () => enviarPorEmail(el.querySelector('.fade'), ctx, d));
  el.querySelector('.relatorio-aporte').addEventListener('click', (e) => {
    const botao = e.target.closest('[data-info]');
    if (botao) abrirInfo(botao);
  });
  // Cabeçalho da tabela congelado logo abaixo da barra do app (que também fica fixa no topo).
  const topoFixo = () => document.documentElement.style.setProperty('--topo-fixo',
    `${document.querySelector('header.app')?.offsetHeight || 0}px`);
  topoFixo();
  window.addEventListener('resize', topoFixo);
  el.querySelector('.tabela-resumo').addEventListener('click', (e) => {
    const botao = e.target.closest('.segmentador');
    if (!botao) return;
    const linha = d.linhas.find((l) => l.rubrica === botao.dataset.rubrica);
    if (linha) abrirRubrica({ linha, dataBase, mesAtual: d.datas.mes_atual });
  });
  el.querySelector('#viabilidade')?.addEventListener('click', () => editarViabilidade(ctx));
  el.querySelector('#cronograma')?.addEventListener('click', () => editarCronograma(d, recarregar));
}
