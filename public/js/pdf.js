// PDF de uma tela gerado no navegador, com as mesmas regras de @media print do app.css
// (A4 paisagem, margens da página "resumo"), para anexar no e-mail sem abrir a impressão.
const HTML2CANVAS = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
const JSPDF = 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js';

const PAGINA = { largura: 297, altura: 210, lado: 9, topo: 7, base: 9 };   // mm
const PX_POR_MM = 96 / 25.4;
const RODAPE = 'Relatório de Aporte · Joy+';

const carregados = {};
function carregarScript(url) {
  carregados[url] ??= new Promise((ok, falha) => {
    const script = document.createElement('script');
    script.src = url;
    script.onload = ok;
    script.onerror = () => { delete carregados[url]; falha(new Error('Não foi possível carregar o gerador de PDF.')); };
    document.head.append(script);
  });
  return carregados[url];
}

/** Texto das regras de @media print das folhas do próprio app (as do Google Fonts não são legíveis). */
function regrasDeImpressao() {
  const regras = [];
  for (const folha of document.styleSheets) {
    let lista;
    try { lista = folha.cssRules; } catch { continue; }
    for (const regra of lista) {
      if (regra instanceof CSSMediaRule && /\bprint\b/.test(regra.media.mediaText)) {
        regras.push(...Array.from(regra.cssRules, (r) => r.cssText));
      }
    }
  }
  return regras.join('\n');
}

/** Gera o PDF de `elemento` e devolve o conteúdo em base64 (sem o prefixo data:). */
export async function gerarPdfBase64(elemento) {
  await Promise.all([carregarScript(HTML2CANVAS), carregarScript(JSPDF)]);
  const larguraUtil = PAGINA.largura - 2 * PAGINA.lado;
  const alturaUtil = PAGINA.altura - PAGINA.topo - PAGINA.base;
  const larguraPx = Math.round(larguraUtil * PX_POR_MM);
  const marca = `pdf-${Date.now()}`;
  elemento.dataset.pdf = marca;
  let tela;
  try {
    tela = await window.html2canvas(elemento, {
      scale: 2, backgroundColor: '#ffffff', useCORS: true, logging: false, windowWidth: larguraPx,
      onclone: (doc) => {
        const estilo = doc.createElement('style');
        estilo.textContent = regrasDeImpressao();
        doc.head.append(estilo);
        const alvo = doc.querySelector(`[data-pdf="${marca}"]`);
        if (alvo) Object.assign(alvo.style, { width: `${larguraPx}px`, maxWidth: 'none' });
      },
    });
  } finally {
    delete elemento.dataset.pdf;
  }

  const { jsPDF } = window.jspdf;
  const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4', compress: true });
  const pxPorMmTela = tela.width / larguraUtil;
  const alturaPaginaPx = Math.floor(alturaUtil * pxPorMmTela);
  const paginas = Math.max(1, Math.ceil(tela.height / alturaPaginaPx));
  for (let i = 0; i < paginas; i += 1) {
    const recorte = document.createElement('canvas');
    recorte.width = tela.width;
    recorte.height = Math.min(alturaPaginaPx, tela.height - i * alturaPaginaPx);
    const ctx = recorte.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, recorte.width, recorte.height);
    ctx.drawImage(tela, 0, i * alturaPaginaPx, tela.width, recorte.height, 0, 0, tela.width, recorte.height);
    if (i) pdf.addPage();
    pdf.addImage(recorte.toDataURL('image/jpeg', 0.9), 'JPEG', PAGINA.lado, PAGINA.topo, larguraUtil,
      recorte.height / pxPorMmTela);
    pdf.setFontSize(7.5);
    pdf.setTextColor(138, 135, 151);
    pdf.text(RODAPE, PAGINA.lado, PAGINA.altura - 4);
    pdf.text(`Página ${i + 1} de ${paginas}`, PAGINA.largura - PAGINA.lado, PAGINA.altura - 4, { align: 'right' });
  }
  return pdf.output('datauristring').split(',')[1];
}
