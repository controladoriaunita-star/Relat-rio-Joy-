// Aba Resumo: reproduz a aba Resumo da planilha — tabela de custos e despesas por rubrica
// (à esquerda) e o Relatório de Aporte (à direita). Tudo segue o mês da data-base.
// Os gráficos ficam na aba Dashboards.
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
  return `<tr class="${classe}"><td class="first">${esc(l.rubrica)}</td>
    <td>${'viabilidade' in l ? numero(l.viabilidade) : ''}</td>
    <td class="${acima ? 'alerta' : ''}">${pct}</td>
    ${CAMPOS.map((c) => `<td class="${c.startsWith('projetado') ? 'proj' : ''}">${celula(l, c)}</td>`).join('')}</tr>`;
}

function somaGrupo(linhas) {
  const soma = (campo) => linhas.reduce((a, l) => a + (l[campo] || 0), 0);
  return Object.fromEntries(['viabilidade', ...CAMPOS].map((c) => [c, soma(c)]));
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
  return `<div class="sheet tabela-resumo"><table><thead><tr>
      <th class="first">Rubricas</th><th>Valor Viabilidade</th><th>% Consumido</th>
      <th>${esc(t.pago_ate)}</th><th>${esc(t.pago_mes)}</th><th>${esc(t.a_pagar.replace('  ', ' '))}</th>
      <th>Projetado Mês</th><th>${esc(t.projetado_proximo.replace('  ', ' '))}</th>
      <th title="Pago no mês + contas a pagar">Total Mês (Pago + A Pagar)</th></tr></thead>
    <tbody>${corpo}</tbody></table></div>`;
}

// ------------------------------------------------------------------ Relatório de Aporte (colunas Y:Z)
const par = (rotulo, valor, classe = '') =>
  `<div class="par ${classe}"><span>${rotulo}</span><b>${valor}</b></div>`;
const moeda = (v) => fmt.moeda(v);
const valorAporte = (v) => (v > 0 ? fmt.moeda(v) : 'Sem aporte');

function divisao(a) {
  if (!(a.aporte_total > 0)) return '';
  return `<div class="divisao-aporte"><div><span>Investidor (85%)</span><b>${moeda(a.investidor)}</b></div>
    <div><span>Joy+ (15%)</span><b>${moeda(a.joy)}</b></div></div>`;
}

function blocoAporteMes(d) {
  const a = d.aporte_mes;
  return `<section class="card bloco-aporte destaque-aporte">
    <p class="sub">Aporte do mês · ${fmt.mesLongo(d.datas.mes_atual)}</p>
    <p class="numero-heroi">${valorAporte(a.aporte_total)}</p>
    ${divisao(a)}
    <div class="extrato">
      ${par(esc(d.titulos.saldo_anterior), moeda(a.saldo_anterior))}
      ${par('Receita do mês', moeda(a.receita_projetada))}
      ${par(esc(d.titulos.custo_mes), moeda(a.custo_mes))}
      ${par('Caixa mínimo', moeda(a.caixa_minimo))}
    </div>
    <p class="nota">Aporte = custo do mês + caixa mínimo − saldo − receita. Cobre as contas do mês e mantém ${moeda(a.caixa_minimo)} em caixa.</p>
  </section>`;
}

function blocoConta(d) {
  const c = d.conta;
  return `<section class="card bloco-aporte">
    <p class="sub">Conta da SPE · ${fmt.mesLongo(d.datas.mes_atual)}</p>
    <div class="extrato">
      ${par('Saldo inicial (fim do mês anterior)', moeda(c.saldo_inicial))}
      ${par('(+) Receitas do mês', moeda(c.receitas))}
      ${par('(+) Aporte do mês', moeda(c.aporte))}
      ${par('(−) Custos do mês (pago + a pagar + projetado)', moeda(-c.custos))}
      ${par('Saldo projetado no fim do mês', moeda(c.saldo_final), 'forte destaque')}
      ${par('Aportes já recebidos no mês', moeda(c.aportes_recebidos))}
      ${par('Aporte a receber', moeda(c.aporte_a_receber), 'forte')}
    </div></section>`;
}

function blocoProximo(d) {
  const p = d.aporte_proximo;
  return `<section class="card bloco-aporte">
    <p class="sub">Aporte do próximo mês · ${fmt.mesLongo(d.datas.proximo_mes)}</p>
    <p class="numero-heroi menor">${valorAporte(p.aporte_total)}</p>
    ${divisao(p)}
    <div class="extrato">
      ${par(esc(d.titulos.saldo_proximo), moeda(p.saldo_anterior))}
      ${par('Receita projetada', moeda(p.receita_projetada))}
      ${par(`${esc(d.titulos.custo_proximo)}${p.custo_automatico ? ' <span class="badge b-primary">automático</span>' : ''}`, moeda(p.custo_projetado))}
      ${par('Caixa mínimo', moeda(p.caixa_minimo))}
    </div>
    <p class="nota">Custo projetado = projeção dos setores + contas a pagar com vencimento no próximo mês.</p>
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
      <div class="par sub-par"><span>Investidor 85% · Joy+ 15%</span><b>${fmt.numero(p.investidor)} · ${fmt.numero(p.joy)}</b></div>
    </div>`;
  }).join('');
  return `<section class="card bloco-aporte">
    <header class="bloco-topo"><p class="sub">Cronograma do aporte · ${fmt.mesLongo(d.datas.mes_atual)}</p>
      ${podeEditar && !semAporte ? '<button class="btn secondary sm sem-impressao" id="cronograma">Programar</button>' : ''}</header>
    ${semAporte ? '<p class="muted" style="margin:0">Sem aporte necessário neste mês.</p>' : `
      ${c.programado ? '' : '<p class="nota">Ainda não programado: parcela única no dia 1.</p>'}
      <div class="parcelas">${parcelas}</div>
      <div class="extrato">
        ${par('Aporte do mês', moeda(c.total), 'forte destaque')}
        ${par('Já recebido no mês', moeda(c.recebido))}
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
        await api('/api/parametros/cronograma', { metodo: 'PUT', corpo: { mes, parcelas: [] } });
        toast('Cronograma removido', { texto: 'Volta a ser parcela única no dia 1.' });
        recarregar();
      } },
      { rotulo: 'Salvar cronograma', classe: 'primary', ao: async () => {
        if (linhas.some((l) => !l.data || l.data < inicio || l.data > mes)) throw new Error('Todas as datas precisam estar dentro do mês.');
        completar();
        if (linhas.at(-1).percentual <= 0.0001) throw new Error('As primeiras parcelas passam do aporte do mês.');
        await api('/api/parametros/cronograma', { metodo: 'PUT', corpo: { mes, parcelas: linhas } });
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
  const { premissas: p } = await api('/api/parametros');
  const campo = (nome, rotulo, ajuda = '') => `<div class="field"><label>${rotulo}</label>
    <input name="${nome}" value="${fmt.numero(p[nome])}" inputmode="decimal" />${ajuda ? `<small>${ajuda}</small>` : ''}</div>`;
  const numericos = ['caixa_minimo', 'caixa_minimo_proximo', 'receita_projetada_proximo', 'ajuste_saldo_banco'];
  modal({
    titulo: 'Premissas do aporte',
    conteudo: `<p>Valores informados manualmente. Custos, saldos e receitas do mês vêm das fontes.</p>
      <div class="grid" style="margin-top:16px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
        ${campo('caixa_minimo', 'Caixa mínimo (mês)')}${campo('caixa_minimo_proximo', 'Caixa mínimo (próximo)')}
        ${campo('receita_projetada_proximo', 'Receita projetada (próximo)')}
        ${campo('ajuste_saldo_banco', 'Ajuste do saldo banco', 'Painel H119')}
      </div><p class="nota" style="margin-top:16px">O cronograma do aporte (parcelas e datas) fica no bloco "Cronograma do aporte".</p>`,
    acoes: [{ rotulo: 'Salvar premissas', classe: 'primary', ao: async (el) => {
      const ler = (nome) => lerNumero(el.querySelector(`[name=${nome}]`).value);
      const corpo = Object.fromEntries(numericos.map((k) => [k, ler(k)]));
      if (Object.values(corpo).some((v) => Number.isNaN(v))) {
        throw new Error('Há valores inválidos.');
      }
      await api('/api/parametros/premissas', { metodo: 'PUT', corpo });
      toast('Premissas salvas');
      recarregar();
    } }],
  });
}

// ------------------------------------------------------------------ tela
export async function render(el, { usuario, dataBase, recarregar }) {
  el.innerHTML = carregando(10);
  const d = await api(`/api/resumo?data=${dataBase}`);
  el.innerHTML = `<div class="fade">
    <div class="cabecalho"><div>
      <div class="eyebrow">Relatório de Aporte · Evans</div><h2>Resumo de Custos e Despesas</h2>
      <p>Mês corrente <b>${fmt.mesLongo(d.datas.mes_atual)}</b> · mês de análise ${fmt.mesLongo(d.datas.mes_analise)} · última atualização ${fmt.dataHora(d.ultima_atualizacao)}</p>
    </div><div class="row-flex sem-impressao">
      ${usuario.permissoes['premissas.editar'] ? '<button class="btn secondary sm" id="premissas">Premissas</button>' : ''}
      <button class="btn secondary sm" onclick="window.print()">Imprimir</button></div></div>
    <div class="resumo-planilha">
      <div class="resumo-tabela">${tabela(d)}</div>
      <aside class="relatorio-aporte" aria-label="Relatório de Aporte">
        ${blocoAporteMes(d)}${blocoCronograma(d, usuario.permissoes['premissas.editar'])}${blocoConta(d)}${blocoProximo(d)}
      </aside>
    </div>
  </div>`;
  el.querySelector('#premissas')?.addEventListener('click', () => editarPremissas(recarregar));
  el.querySelector('#cronograma')?.addEventListener('click', () => editarCronograma(d, recarregar));
}
