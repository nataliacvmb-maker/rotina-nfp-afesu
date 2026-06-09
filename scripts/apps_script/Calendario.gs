// ============================================================
// SERVIDOR DO CALENDÁRIO HTML
// ============================================================

function servirCalendario(clienteSlug, mesParam) {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CAMPANHAS);

  // Determina o mês a exibir (formato YYYY-MM, default = mês atual)
  let ano, mes;
  if (mesParam && /^\d{4}-\d{2}$/.test(mesParam)) {
    [ano, mes] = mesParam.split('-').map(Number);
  } else {
    const hoje = new Date();
    ano = hoje.getFullYear();
    mes = hoje.getMonth() + 1;
  }

  // Dados do cliente
  const infoCliente = clienteSlug ? getInfoCliente(clienteSlug) : null;
  const titulo = infoCliente ? infoCliente.nome : 'Todos os clientes';

  // Carrega campanhas do mês
  const campanhas = getCampanhasDoMes(sheet, clienteSlug, ano, mes);

  // Mês anterior e próximo (para navegação)
  const dtAtual = new Date(ano, mes - 1, 1);
  const dtPrev  = new Date(ano, mes - 2, 1);
  const dtNext  = new Date(ano, mes, 1);
  const mesPrev = `${dtPrev.getFullYear()}-${String(dtPrev.getMonth() + 1).padStart(2,'0')}`;
  const mesNext = `${dtNext.getFullYear()}-${String(dtNext.getMonth() + 1).padStart(2,'0')}`;

  const mesesNomes = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                      'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  const mesLabel = `${mesesNomes[mes - 1]} ${ano}`;

  // Gera células do calendário
  const diasHtml  = gerarDiasHtml(ano, mes, campanhas);
  const listaHtml = gerarListaHtml(campanhas);

  const template = HtmlService.createTemplateFromFile('Calendario');
  template.titulo     = titulo;
  template.clienteSlug = clienteSlug || '';
  template.mesLabel   = mesLabel;
  template.mesPrev    = mesPrev;
  template.mesNext    = mesNext;
  template.diasHtml   = diasHtml;
  template.listaHtml  = listaHtml;

  return template.evaluate()
    .setTitle(`${titulo} — Calendário`)
    .addMetaTag('viewport', 'width=device-width,initial-scale=1.0')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}


// ============================================================
// BUSCA CAMPANHAS DO MÊS NA PLANILHA
// ============================================================

function getCampanhasDoMes(sheet, clienteSlug, ano, mes) {
  const dados  = sheet.getDataRange().getValues();
  const result = [];

  for (let i = 1; i < dados.length; i++) {
    const linha   = dados[i];
    const cliente = linha[COL.CLIENTE - 1];
    const data    = linha[COL.DATA - 1];

    if (!cliente || !data) continue;
    if (clienteSlug && cliente.toString().toLowerCase() !== clienteSlug.toLowerCase()) continue;

    const dt = new Date(data);
    if (isNaN(dt.getTime())) continue;
    if (dt.getFullYear() !== ano || (dt.getMonth() + 1) !== mes) continue;

    const tipo   = (linha[COL.TIPO - 1] || 'outros').toString().toLowerCase();
    const status = linha[COL.STATUS - 1] || '';

    result.push({
      rowNum:    i + 1,
      dia:       dt.getDate(),
      dataStr:   Utilities.formatDate(dt, Session.getScriptTimeZone(), 'dd/MM/yyyy'),
      cliente:   cliente.toString(),
      tipo:      tipo,
      campanha:  linha[COL.CAMPANHA - 1] || '',
      copy:      linha[COL.COPY - 1] || '⏳',
      arte:      linha[COL.ARTE - 1] || '⏳',
      dados:     linha[COL.DADOS - 1] || '⏳',
      status:    status,
      linkDrive: linha[COL.LINK_DRIVE - 1] || '',
      linkHtml:  linha[COL.LINK_HTML - 1] || '',
      obs:       linha[COL.OBS - 1] || '',
    });
  }

  return result;
}


// ============================================================
// GERA HTML DAS CÉLULAS DA GRADE DO CALENDÁRIO
// ============================================================

function gerarDiasHtml(ano, mes, campanhas) {
  const hoje   = new Date();
  const primeiroDia = new Date(ano, mes - 1, 1);
  const ultimoDia   = new Date(ano, mes, 0);
  const totalDias   = ultimoDia.getDate();

  // Dia da semana do dia 1 (0=Dom)
  let dow = primeiroDia.getDay();

  // Mapeia campanhas por dia
  const porDia = {};
  campanhas.forEach(c => {
    if (!porDia[c.dia]) porDia[c.dia] = [];
    porDia[c.dia].push(c);
  });

  let html = '';

  // Células vazias antes do dia 1
  for (let i = 0; i < dow; i++) {
    html += '<div class="day-cell outro-mes"></div>';
  }

  for (let dia = 1; dia <= totalDias; dia++) {
    const eHoje = (hoje.getFullYear() === ano && (hoje.getMonth()+1) === mes && hoje.getDate() === dia);
    const diaSemana = (dow + dia - 1) % 7; // 0=dom, 6=sab
    const fimSemana = diaSemana === 0 || diaSemana === 6;

    const classes = ['day-cell', eHoje ? 'hoje' : '', fimSemana ? 'fim-semana' : ''].filter(Boolean).join(' ');
    html += `<div class="${classes}">`;
    html += `<div class="day-num">${dia}</div>`;

    if (porDia[dia]) {
      porDia[dia].forEach(c => {
        const tipoClass = `pill-${c.tipo.replace(/[^a-z]/g, '') || 'outros'}`;
        const emoji     = { email:'📧', instagram:'📸', whatsapp:'💬', sms:'📱', outros:'📌' }[c.tipo] || '📌';
        const stIcon    = c.status.includes('Pronto') ? '✅' : c.status.includes('Bloqueado') ? '🔴' : '⏳';
        const tooltip   = `${c.campanha}\nCopy: ${c.copy}  Arte: ${c.arte}  Dados: ${c.dados}`;
        const label     = c.campanha.length > 22 ? c.campanha.slice(0, 20) + '…' : c.campanha;

        html += `<div class="pill ${tipoClass}" data-tooltip="${escHtml(tooltip)}">${emoji} ${escHtml(label)} <span class="status-ic">${stIcon}</span></div>`;
      });
    }

    html += '</div>';
  }

  // Células restantes após o último dia
  const totalCelulas = dow + totalDias;
  const restante     = (7 - (totalCelulas % 7)) % 7;
  for (let i = 0; i < restante; i++) {
    html += '<div class="day-cell outro-mes"></div>';
  }

  return html;
}


// ============================================================
// GERA HTML DA LISTA DETALHADA ABAIXO DO CALENDÁRIO
// ============================================================

function gerarListaHtml(campanhas) {
  if (campanhas.length === 0) {
    return '<div class="lista-col" style="grid-column:1/-1;color:#aaa;padding:20px">Nenhuma campanha cadastrada para este mês.</div>';
  }

  const ordenadas = campanhas.slice().sort((a, b) => a.dia - b.dia);
  let html = '';

  ordenadas.forEach(c => {
    const tipoEmoji = { email:'📧', instagram:'📸', whatsapp:'💬', sms:'📱', outros:'📌' }[c.tipo] || '📌';

    let badgeClass, badgeLabel;
    if (c.status.includes('Pronto')) {
      badgeClass = 'badge-pronto'; badgeLabel = '🟢 Pronto';
    } else if (c.status.includes('andamento')) {
      badgeClass = 'badge-andamento'; badgeLabel = '🟡 Em andamento';
    } else {
      badgeClass = 'badge-aguardando'; badgeLabel = '🔴 Aguardando';
    }

    const linkDriveHtml = c.linkDrive
      ? `<a href="${escHtml(c.linkDrive)}" target="_blank" style="font-size:11px;color:#2980b9">📁 Drive</a>`
      : '';

    html += `
      <div class="lista-row">
        <div class="lista-col">Dia ${c.dia}</div>
        <div class="lista-col">${tipoEmoji} ${c.tipo}</div>
        <div class="lista-col" style="font-weight:600">${escHtml(c.campanha)} ${linkDriveHtml}</div>
        <div class="lista-col" style="text-align:center">${c.copy}</div>
        <div class="lista-col" style="text-align:center">${c.arte}</div>
        <div class="lista-col" style="text-align:center">${c.dados}</div>
        <div class="lista-col"><span class="status-badge ${badgeClass}">${badgeLabel}</span></div>
      </div>`;
  });

  return html;
}


// ============================================================
// UTILITÁRIOS
// ============================================================

function escHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
