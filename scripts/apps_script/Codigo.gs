// ============================================================
// CONFIGURAÇÕES GLOBAIS
// ============================================================

const SHEET_CAMPANHAS = 'CAMPANHAS';
const SHEET_CLIENTES  = 'CLIENTES';
const SHEET_LINKS     = 'LINKS CALENDÁRIOS';

const STATUS_PENDENTE = '⏳';
const STATUS_OK       = '✅';
const STATUS_BLOQUEIO = '❌';

// Colunas da aba CAMPANHAS (índice 1-based)
const COL = {
  CLIENTE:    1,  // A
  TIPO:       2,  // B
  MES_ANO:    3,  // C
  DATA:       4,  // D — data planejada do disparo
  CAMPANHA:   5,  // E — assunto / nome da campanha
  COPY:       6,  // F — status copy
  ARTE:       7,  // G — status arte
  DADOS:      8,  // H — status dados
  STATUS:     9,  // I — status geral (calculado)
  LINK_DRIVE: 10, // J — link da pasta no Drive (insumos)
  LINK_HTML:  11, // K — link do HTML gerado para o RD Station
  OBS:        12, // L — observações
};

const TIPOS_CONFIG = {
  'email':     { cor: '#FFB3B3', texto: '#8B0000', emoji: '📧' },
  'instagram': { cor: '#B3C6FF', texto: '#1A3399', emoji: '📸' },
  'whatsapp':  { cor: '#B3F0C8', texto: '#145A32', emoji: '💬' },
  'sms':       { cor: '#FFE8A3', texto: '#7D5500', emoji: '📱' },
  'outros':    { cor: '#E0E0E0', texto: '#333333', emoji: '📌' },
};


// ============================================================
// TRIGGER: nova linha ou mudança de status
// ============================================================

function onEdit(e) {
  const sheet = e.range.getSheet();
  if (sheet.getName() !== SHEET_CAMPANHAS) return;

  const row    = e.range.getRow();
  const col    = e.range.getColumn();
  const sheet_ = sheet;

  if (row <= 1) return; // ignora cabeçalho

  // Nova linha: se preencheu a coluna CLIENTE e status está vazio → briefing
  if (col === COL.CLIENTE) {
    const clienteVal = sheet_.getRange(row, COL.CLIENTE).getValue();
    const statusVal  = sheet_.getRange(row, COL.COPY).getValue();
    if (clienteVal && !statusVal) {
      Utilities.sleep(500); // aguarda outros campos serem preenchidos
      inicializarStatusLinha(sheet_, row);
      SpreadsheetApp.flush();
      enviarBriefing(row);
    }
  }

  // Mudança de status (copy/arte/dados) → recalcula status geral
  if ([COL.COPY, COL.ARTE, COL.DADOS].includes(col)) {
    atualizarStatusGeral(sheet_, row);
  }
}


// ============================================================
// INICIALIZA STATUS DE UMA NOVA LINHA
// ============================================================

function inicializarStatusLinha(sheet, row) {
  sheet.getRange(row, COL.COPY).setValue(STATUS_PENDENTE);
  sheet.getRange(row, COL.ARTE).setValue(STATUS_PENDENTE);
  sheet.getRange(row, COL.DADOS).setValue(STATUS_PENDENTE);
  sheet.getRange(row, COL.STATUS).setValue('🔴 Aguardando insumos');
}


// ============================================================
// RECALCULA STATUS GERAL
// ============================================================

function atualizarStatusGeral(sheet, row) {
  const copy  = sheet.getRange(row, COL.COPY).getValue();
  const arte  = sheet.getRange(row, COL.ARTE).getValue();
  const dados = sheet.getRange(row, COL.DADOS).getValue();

  let status;
  if (copy === STATUS_OK && arte === STATUS_OK && dados === STATUS_OK) {
    status = '🟢 Pronto para disparo';
    notificarOperadorPronto(row);
  } else if ([copy, arte, dados].includes(STATUS_BLOQUEIO)) {
    status = '🔴 Bloqueado';
  } else if ([copy, arte, dados].some(s => s === STATUS_OK)) {
    status = '🟡 Em andamento';
  } else {
    status = '🔴 Aguardando insumos';
  }

  sheet.getRange(row, COL.STATUS).setValue(status);
}


// ============================================================
// ENVIA EMAIL DE BRIEFING PARA COPY + ARTE + DADOS
// ============================================================

function enviarBriefing(row) {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CAMPANHAS);
  const dados = sheet.getRange(row, 1, 1, COL.OBS).getValues()[0];

  const cliente   = dados[COL.CLIENTE - 1];
  const tipo      = dados[COL.TIPO - 1];
  const mesAno    = dados[COL.MES_ANO - 1];
  const data      = dados[COL.DATA - 1];
  const campanha  = dados[COL.CAMPANHA - 1];
  const obs       = dados[COL.OBS - 1];
  const linkDrive = dados[COL.LINK_DRIVE - 1];

  const infoCliente = getInfoCliente(cliente);
  if (!infoCliente) {
    console.log('Cliente não encontrado:', cliente);
    return;
  }

  const scriptUrl = ScriptApp.getService().getUrl();
  const dataFormatada = data ? Utilities.formatDate(new Date(data), 'America/Sao_Paulo', 'dd/MM/yyyy') : '—';

  const equipes = [
    { campo: 'copy',  email: infoCliente.email_copy,  nome: 'Time de Copy',  tarefa: 'Redação do roteiro (texto + assunto + CTA)' },
    { campo: 'arte',  email: infoCliente.email_arte,  nome: 'Time de Arte',  tarefa: 'Criação das imagens (logo, header, campanha, final)' },
    { campo: 'dados', email: infoCliente.email_dados, nome: 'Time de Dados', tarefa: 'Preparação da base de emails (.xlsx)' },
  ];

  for (const equipe of equipes) {
    if (!equipe.email) continue;

    const linkConfirmar = `${scriptUrl}?action=confirmar&row=${row}&campo=${equipe.campo}&token=${gerarToken(row, equipe.campo)}`;

    const html = htmlBriefing({
      nomeEquipe:      equipe.nome,
      tarefa:          equipe.tarefa,
      cliente:         cliente,
      tipo:            tipo,
      campanha:        campanha,
      mesAno:          mesAno,
      dataFormatada:   dataFormatada,
      obs:             obs,
      linkDrive:       linkDrive,
      linkConfirmar:   linkConfirmar,
    });

    GmailApp.sendEmail(equipe.email, `[${cliente}] Novo disparo: ${campanha} — ${mesAno}`, '', {
      htmlBody: html,
      name: 'Sistema de Campanhas NFP',
    });
  }
}


// ============================================================
// WEBHOOK: confirmação de entrega via link no email
// ============================================================

function doGet(e) {
  const params = e.parameter;

  if (params.action === 'confirmar') {
    return confirmarEntrega(params);
  }

  return HtmlService.createHtmlOutputFromFile('Portal')
    .setTitle('Portal de Campanhas NFP')
    .addMetaTag('viewport', 'width=device-width,initial-scale=1.0')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}


// ============================================================
// PORTAL: funções chamadas pelo cliente via google.script.run
// ============================================================

function getDadosPortal(clienteSlug, mesParam) {
  let ano, mes;
  if (mesParam && /^\d{4}-\d{2}$/.test(mesParam)) {
    [ano, mes] = mesParam.split('-').map(Number);
  } else {
    const hoje = new Date();
    ano = hoje.getFullYear();
    mes = hoje.getMonth() + 1;
  }
  const ss     = SpreadsheetApp.getActiveSpreadsheet();
  const sheet  = ss.getSheetByName(SHEET_CAMPANHAS);
  const clientes  = getListaClientes();
  const campanhas = getCampanhasDoMes(sheet, clienteSlug || null, ano, mes);
  return { clientes, campanhas, ano, mes };
}

function getListaClientes() {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CLIENTES);
  const dados = sheet.getDataRange().getValues();
  const lista = [];
  for (let i = 1; i < dados.length; i++) {
    if (dados[i][0]) lista.push({ slug: String(dados[i][0]), nome: String(dados[i][1] || dados[i][0]) });
  }
  return lista;
}

function criarCampanhaPortal(dados) {
  try {
    if (!dados.cliente || !dados.tipo || !dados.data || !dados.campanha) {
      return { ok: false, erro: 'Campos obrigatórios faltando.' };
    }
    const ss    = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_CAMPANHAS);

    const dt     = new Date(dados.data + 'T12:00:00');
    const mesAno = `${String(dt.getMonth() + 1).padStart(2,'0')}/${dt.getFullYear()}`;

    sheet.appendRow([
      dados.cliente, dados.tipo, mesAno, dt,
      dados.campanha, STATUS_PENDENTE, STATUS_PENDENTE, STATUS_PENDENTE,
      '🔴 Aguardando insumos', dados.linkDrive || '', '', dados.obs || '',
    ]);

    const newRow = sheet.getLastRow();
    sheet.getRange(newRow, COL.DATA).setNumberFormat('dd/MM/yyyy');

    try { enviarBriefing(newRow); } catch(e) { console.error('Briefing erro:', e); }

    return { ok: true, row: newRow };
  } catch(e) {
    return { ok: false, erro: e.message };
  }
}

function confirmarEntrega(params) {
  const row    = parseInt(params.row);
  const campo  = params.campo;
  const token  = params.token;

  if (!row || !campo || token !== gerarToken(row, campo)) {
    return HtmlService.createHtmlOutput('<h2>❌ Link inválido ou expirado.</h2>');
  }

  const colIdx = { copy: COL.COPY, arte: COL.ARTE, dados: COL.DADOS }[campo];
  if (!colIdx) return HtmlService.createHtmlOutput('<h2>❌ Campo inválido.</h2>');

  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CAMPANHAS);

  const atual = sheet.getRange(row, colIdx).getValue();
  if (atual === STATUS_OK) {
    return HtmlService.createHtmlOutput(htmlConfirmacaoJaFeita());
  }

  sheet.getRange(row, colIdx).setValue(STATUS_OK);
  atualizarStatusGeral(sheet, row);

  const campanha = sheet.getRange(row, COL.CAMPANHA).getValue();
  const cliente  = sheet.getRange(row, COL.CLIENTE).getValue();

  return HtmlService.createHtmlOutput(htmlConfirmacaoSucesso(campo, cliente, campanha));
}


// ============================================================
// NOTIFICA OPERADOR QUANDO TUDO ESTÁ PRONTO
// ============================================================

function notificarOperadorPronto(row) {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CAMPANHAS);
  const dados = sheet.getRange(row, 1, 1, COL.OBS).getValues()[0];

  const cliente  = dados[COL.CLIENTE - 1];
  const campanha = dados[COL.CAMPANHA - 1];
  const mesAno   = dados[COL.MES_ANO - 1];

  const infoCliente = getInfoCliente(cliente);
  if (!infoCliente || !infoCliente.email_operador) return;

  const html = htmlProntoParaDisparo(cliente, campanha, mesAno);
  GmailApp.sendEmail(
    infoCliente.email_operador,
    `[${cliente}] ✅ Insumos prontos — ${campanha}`,
    '',
    { htmlBody: html, name: 'Sistema de Campanhas NFP' }
  );
}


// ============================================================
// UTILIDADES
// ============================================================

function getInfoCliente(clienteSlug) {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CLIENTES);
  const dados = sheet.getDataRange().getValues();

  for (let i = 1; i < dados.length; i++) {
    if (dados[i][0].toString().toLowerCase() === clienteSlug.toString().toLowerCase()) {
      return {
        slug:           dados[i][0],
        nome:           dados[i][1],
        email_operador: dados[i][2],
        email_copy:     dados[i][3],
        email_arte:     dados[i][4],
        email_dados:    dados[i][5],
        email_aprovador:dados[i][6],
      };
    }
  }
  return null;
}

function gerarToken(row, campo) {
  const ss  = SpreadsheetApp.getActiveSpreadsheet();
  const key = ss.getId() + row + campo + 'nfp2026';
  return Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, key)
    .map(b => ('0' + (b & 0xFF).toString(16)).slice(-2)).join('').slice(0, 12);
}


