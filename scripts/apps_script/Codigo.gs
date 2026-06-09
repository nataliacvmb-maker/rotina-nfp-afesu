// ============================================================
// CONFIGURAÇÕES GLOBAIS
// ============================================================

const SHEET_CAMPANHAS = 'CAMPANHAS';
const SHEET_CLIENTES  = 'CLIENTES';
const SHEET_LINKS     = 'LINKS CALENDÁRIOS';

const STATUS_PENDENTE        = 'Pendente';
const STATUS_OK              = 'Entregue';
const STATUS_BLOQUEIO        = 'Bloqueado';
const STATUS_AGUARDANDO_COPY = 'Aguardando Copy';

// Colunas da aba CAMPANHAS (índice 1-based)
const COL = {
  CLIENTE:     1,  // A
  TIPO:        2,  // B
  MES_ANO:     3,  // C
  DATA:        4,  // D
  CAMPANHA:    5,  // E
  COPY:        6,  // F
  ARTE:        7,  // G
  DADOS:       8,  // H
  STATUS:      9,  // I
  LINK_DRIVE:  10, // J
  LINK_HTML:   11, // K
  OBS:         12, // L
  PRAZO_COPY:  13, // M
  PRAZO_ARTE:  14, // N
  PRAZO_DADOS: 15, // O
};

const TIPOS_CONFIG = {
  'email':     { cor: '#FFB3B3', texto: '#8B0000', label: 'Email' },
  'instagram': { cor: '#B3C6FF', texto: '#1A3399', label: 'Instagram' },
  'whatsapp':  { cor: '#B3F0C8', texto: '#145A32', label: 'WhatsApp' },
  'sms':       { cor: '#FFE8A3', texto: '#7D5500', label: 'SMS' },
  'outros':    { cor: '#E0E0E0', texto: '#333333', label: 'Outros' },
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
  sheet.getRange(row, COL.ARTE).setValue(STATUS_AGUARDANDO_COPY);
  sheet.getRange(row, COL.DADOS).setValue(STATUS_PENDENTE);
  sheet.getRange(row, COL.STATUS).setValue('Aguardando insumos');
}


// ============================================================
// RECALCULA STATUS GERAL
// ============================================================

function atualizarStatusGeral(sheet, row) {
  const copy  = sheet.getRange(row, COL.COPY).getValue();
  const arte  = sheet.getRange(row, COL.ARTE).getValue();
  const dados = sheet.getRange(row, COL.DADOS).getValue();

  // "Aguardando Copy" conta como Pendente para o status geral
  const arteEf = (arte === STATUS_AGUARDANDO_COPY) ? STATUS_PENDENTE : arte;

  let status;
  if (copy === STATUS_OK && arteEf === STATUS_OK && dados === STATUS_OK) {
    status = 'Pronto para disparo';
    notificarOperadorPronto(row);
  } else if ([copy, arteEf, dados].includes(STATUS_BLOQUEIO)) {
    status = 'Bloqueado';
  } else if ([copy, arteEf, dados].some(s => s === STATUS_OK)) {
    status = 'Em andamento';
  } else {
    status = 'Aguardando insumos';
  }

  sheet.getRange(row, COL.STATUS).setValue(status);
}


// ============================================================
// FLUXO SEQUENCIAL DE BRIEFING
// Copy + Dados → Copy confirma → Arte → Arte + Dados confirmam → Aprovador
// ============================================================

function enviarBriefing(row, pastaLinks, instrucaoBase) {
  // Chamada inicial: envia apenas para Copy e Dados
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CAMPANHAS);
  const linha = sheet.getRange(row, 1, 1, COL.OBS).getValues()[0];

  const cliente   = linha[COL.CLIENTE - 1];
  const tipo      = linha[COL.TIPO - 1];
  const mesAno    = linha[COL.MES_ANO - 1];
  const data      = linha[COL.DATA - 1];
  const campanha  = linha[COL.CAMPANHA - 1];
  const obs       = linha[COL.OBS - 1];
  const linkDrive = linha[COL.LINK_DRIVE - 1];

  const infoCliente = getInfoCliente(cliente);
  if (!infoCliente) return;

  const scriptUrl     = ScriptApp.getService().getUrl();
  const dataFormatada = data ? Utilities.formatDate(new Date(data), 'America/Sao_Paulo', 'dd/MM/yyyy') : '—';
  const tipoNorm      = (tipo || '').toString().toLowerCase();

  const equipes = [];
  equipes.push({
    campo: 'copy', email: infoCliente.email_copy, nome: 'Time de Copy',
    tarefa: tipoNorm === 'email'
      ? 'Redação do roteiro, assunto e CTA do email.'
      : tipoNorm === 'instagram'
        ? 'Redação da legenda, hashtags e CTA do post.'
        : 'Redação do conteúdo.',
    linkPasta: pastaLinks ? pastaLinks.copy : linkDrive,
  });
  if (tipoNorm === 'email') {
    equipes.push({
      campo: 'dados', email: infoCliente.email_dados, nome: 'Time de Dados',
      tarefa: 'Preparação e entrega da base de contatos (.xlsx).',
      linkPasta: pastaLinks ? pastaLinks.base : linkDrive,
      instrucaoBase: instrucaoBase || '',
    });
  }

  for (const equipe of equipes) {
    if (!equipe.email) continue;
    const linkConfirmar = scriptUrl + '?action=confirmar&row=' + row + '&campo=' + equipe.campo + '&token=' + gerarToken(row, equipe.campo);
    const html = htmlBriefing({
      nomeEquipe: equipe.nome, tarefa: equipe.tarefa, cliente, tipo, campanha,
      mesAno, dataFormatada, obs, linkDrive: equipe.linkPasta || linkDrive,
      instrucaoBase: equipe.instrucaoBase || '', linkConfirmar,
    });
    GmailApp.sendEmail(equipe.email, '[' + cliente + '] Novo briefing: ' + campanha + ' — ' + mesAno, '', {
      htmlBody: html, name: 'Sistema Calendario Mkt',
    });
  }
}

function _getSubpastaLink(disparoUrl, nomePasta) {
  if (!disparoUrl) return disparoUrl;
  const m = disparoUrl.match(/\/folders\/([-\w]+)/);
  if (!m) return disparoUrl;
  try {
    const pai  = DriveApp.getFolderById(m[1]);
    const iter = pai.searchFolders('title = "' + nomePasta + '" and trashed = false');
    if (iter.hasNext()) return iter.next().getUrl();
  } catch(e) { console.error('_getSubpastaLink:', e); }
  return disparoUrl;
}

function enviarBriefingArte(row) {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CAMPANHAS);
  const linha = sheet.getRange(row, 1, 1, COL.OBS).getValues()[0];

  const cliente       = linha[COL.CLIENTE - 1];
  const tipo          = linha[COL.TIPO - 1];
  const campanha      = linha[COL.CAMPANHA - 1];
  const mesAno        = linha[COL.MES_ANO - 1];
  const data          = linha[COL.DATA - 1];
  const obs           = linha[COL.OBS - 1];
  const linkDrive     = linha[COL.LINK_DRIVE - 1];
  const dataFormatada = data ? Utilities.formatDate(new Date(data), 'America/Sao_Paulo', 'dd/MM/yyyy') : '—';
  const tipoNorm      = (tipo || '').toString().toLowerCase();

  const infoCliente = getInfoCliente(cliente);
  if (!infoCliente || !infoCliente.email_arte) return;

  const linkArte     = _getSubpastaLink(linkDrive, 'Arte');
  const scriptUrl    = ScriptApp.getService().getUrl();
  const linkConfirmar = scriptUrl + '?action=confirmar&row=' + row + '&campo=arte&token=' + gerarToken(row, 'arte');
  const tarefa       = tipoNorm === 'email'
    ? 'Criação dos banners (header, corpo e rodapé).'
    : 'Criação das artes (feed e/ou stories).';

  const html = htmlBriefing({
    nomeEquipe: 'Time de Arte', tarefa, cliente, tipo, campanha,
    mesAno, dataFormatada, obs, linkDrive: linkArte || linkDrive,
    instrucaoBase: '', linkConfirmar,
  });
  GmailApp.sendEmail(infoCliente.email_arte, '[' + cliente + '] Briefing Arte: ' + campanha + ' — ' + mesAno, '', {
    htmlBody: html, name: 'Sistema Calendario Mkt',
  });
}

function notificarAprovador(row) {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CAMPANHAS);
  const linha = sheet.getRange(row, 1, 1, COL.OBS).getValues()[0];

  const cliente   = linha[COL.CLIENTE - 1];
  const campanha  = linha[COL.CAMPANHA - 1];
  const mesAno    = linha[COL.MES_ANO - 1];
  const linkDrive = linha[COL.LINK_DRIVE - 1];

  const infoCliente = getInfoCliente(cliente);
  if (!infoCliente || !infoCliente.email_aprovador) return;

  const html = htmlProntoParaAprovacao(cliente, campanha, mesAno, linkDrive);
  GmailApp.sendEmail(infoCliente.email_aprovador, '[' + cliente + '] Aguardando aprovacao: ' + campanha, '', {
    htmlBody: html, name: 'Sistema Calendario Mkt',
  });
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

    const dt      = new Date(dados.data + 'T12:00:00');
    const mesAno  = String(dt.getMonth() + 1).padStart(2,'0') + '/' + dt.getFullYear();
    const tipoNorm = (dados.tipo || '').toLowerCase();

    const infoCliente = getInfoCliente(dados.cliente);

    // Cria estrutura de pastas no Drive
    let pastaLinks = null;
    let linkDrive  = dados.linkDrive || '';
    if (!linkDrive) {
      if (tipoNorm === 'email') {
        pastaLinks = criarEstruturaEmail(infoCliente, dados.campanha, mesAno);
      } else if (tipoNorm === 'instagram') {
        pastaLinks = criarEstruturaInstagram(infoCliente, dados.campanha, mesAno);
      }
      linkDrive = pastaLinks ? pastaLinks.disparo : '';
    }

    // Reserva linha e define formatos ANTES de gravar
    const newRow = sheet.getLastRow() + 1;
    sheet.getRange(newRow, COL.MES_ANO).setNumberFormat('@');
    sheet.getRange(newRow, COL.DATA).setNumberFormat('dd/MM/yyyy');

    const obs          = [dados.obs || '', dados.instrucaoBase ? 'Base: ' + dados.instrucaoBase : ''].filter(Boolean).join(' | ');
    const arteInicial  = STATUS_AGUARDANDO_COPY;
    const dadosInicial = tipoNorm === 'email' ? STATUS_PENDENTE : STATUS_OK;

    // Prazos (opcionais, recebidos do portal)
    const prazoCopy  = dados.prazoCopy  ? new Date(dados.prazoCopy  + 'T12:00:00') : '';
    const prazoArte  = dados.prazoArte  ? new Date(dados.prazoArte  + 'T12:00:00') : '';
    const prazoDados = dados.prazoDados ? new Date(dados.prazoDados + 'T12:00:00') : '';

    sheet.getRange(newRow, COL.PRAZO_COPY).setNumberFormat('dd/MM/yyyy');
    sheet.getRange(newRow, COL.PRAZO_ARTE).setNumberFormat('dd/MM/yyyy');
    sheet.getRange(newRow, COL.PRAZO_DADOS).setNumberFormat('dd/MM/yyyy');

    sheet.getRange(newRow, 1, 1, 12).setValues([[
      dados.cliente, dados.tipo, mesAno, dt,
      dados.campanha, STATUS_PENDENTE, arteInicial, dadosInicial,
      'Aguardando insumos', linkDrive, '', obs,
    ]]);

    if (prazoCopy)  sheet.getRange(newRow, COL.PRAZO_COPY).setValue(prazoCopy);
    if (prazoArte)  sheet.getRange(newRow, COL.PRAZO_ARTE).setValue(prazoArte);
    if (prazoDados) sheet.getRange(newRow, COL.PRAZO_DADOS).setValue(prazoDados);

    try { enviarBriefing(newRow, pastaLinks, dados.instrucaoBase || ''); } catch(e) { console.error('Briefing erro:', e); }

    return { ok: true, row: newRow, linkDrive: linkDrive };
  } catch(e) {
    return { ok: false, erro: e.message };
  }
}


// ============================================================
// DIAGNÓSTICO / AUTORIZAÇÃO
// ============================================================

function testarDrive() {
  // Execute esta função UMA VEZ no editor para autorizar acesso ao Drive
  const ss     = SpreadsheetApp.getActiveSpreadsheet();
  const sheet  = ss.getSheetByName(SHEET_CLIENTES);
  const dados  = sheet.getDataRange().getValues();
  const result = [];
  for (let i = 1; i < dados.length; i++) {
    const folderId = dados[i][7] ? String(dados[i][7]).trim() : '';
    if (!folderId) { result.push(dados[i][0] + ': sem ID'); continue; }
    try {
      const f = DriveApp.getFolderById(folderId);
      result.push(dados[i][0] + ': OK — ' + f.getName());
    } catch(e) {
      result.push(dados[i][0] + ': ERRO — ' + e.message);
    }
  }
  Logger.log(result.join('\n'));
  // Ver resultado: clique em "Registro de execução" após rodar
}


// ============================================================
// EDITA CAMPANHA EXISTENTE
// ============================================================

function editarCampanhaPortal(dados) {
  try {
    const rowNum = parseInt(dados.rowNum);
    if (!rowNum || rowNum < 2) return { ok: false, erro: 'Linha inválida.' };

    const ss    = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_CAMPANHAS);

    const dt     = new Date(dados.data + 'T12:00:00');
    const mesAno = String(dt.getMonth() + 1).padStart(2,'0') + '/' + dt.getFullYear();

    sheet.getRange(rowNum, COL.MES_ANO).setNumberFormat('@');
    sheet.getRange(rowNum, COL.DATA).setNumberFormat('dd/MM/yyyy');

    sheet.getRange(rowNum, COL.TIPO).setValue(dados.tipo);
    sheet.getRange(rowNum, COL.MES_ANO).setValue(mesAno);
    sheet.getRange(rowNum, COL.DATA).setValue(dt);
    sheet.getRange(rowNum, COL.CAMPANHA).setValue(dados.campanha);

    const obs = [dados.obs || '', dados.instrucaoBase ? 'Base: ' + dados.instrucaoBase : ''].filter(Boolean).join(' | ');
    sheet.getRange(rowNum, COL.OBS).setValue(obs);

    if (dados.prazoCopy) {
      sheet.getRange(rowNum, COL.PRAZO_COPY).setNumberFormat('dd/MM/yyyy').setValue(new Date(dados.prazoCopy + 'T12:00:00'));
    }
    if (dados.prazoArte) {
      sheet.getRange(rowNum, COL.PRAZO_ARTE).setNumberFormat('dd/MM/yyyy').setValue(new Date(dados.prazoArte + 'T12:00:00'));
    }
    if (dados.prazoDados) {
      sheet.getRange(rowNum, COL.PRAZO_DADOS).setNumberFormat('dd/MM/yyyy').setValue(new Date(dados.prazoDados + 'T12:00:00'));
    }

    return { ok: true };
  } catch(e) {
    return { ok: false, erro: e.message };
  }
}


// ============================================================
// CANCELA CAMPANHA E NOTIFICA EQUIPES
// ============================================================

function cancelarCampanhaPortal(dados) {
  try {
    const rowNum = parseInt(dados.rowNum);
    if (!rowNum || rowNum < 2) return { ok: false, erro: 'Linha inválida.' };

    const ss    = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_CAMPANHAS);

    sheet.getRange(rowNum, COL.STATUS).setValue('Cancelada');

    try { enviarCancelamento(rowNum, dados.motivo || ''); } catch(e) { console.error('Cancelamento email erro:', e); }

    return { ok: true };
  } catch(e) {
    return { ok: false, erro: e.message };
  }
}

function enviarCancelamento(row, motivo) {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_CAMPANHAS);
  const linha = sheet.getRange(row, 1, 1, COL.OBS).getValues()[0];

  const cliente       = linha[COL.CLIENTE - 1];
  const tipo          = linha[COL.TIPO - 1];
  const campanha      = linha[COL.CAMPANHA - 1];
  const mesAno        = linha[COL.MES_ANO - 1];
  const data          = linha[COL.DATA - 1];
  const dataFormatada = data ? Utilities.formatDate(new Date(data), 'America/Sao_Paulo', 'dd/MM/yyyy') : '—';

  const infoCliente = getInfoCliente(cliente);
  if (!infoCliente) return;

  const tipoNorm = (tipo || '').toString().toLowerCase();
  const emails = [];
  if (infoCliente.email_copy)     emails.push(infoCliente.email_copy);
  if (infoCliente.email_arte)     emails.push(infoCliente.email_arte);
  if (tipoNorm === 'email' && infoCliente.email_dados) emails.push(infoCliente.email_dados);
  if (infoCliente.email_operador) emails.push(infoCliente.email_operador);

  const uniqueEmails = emails.filter(function(v, i, a){ return a.indexOf(v) === i; });
  const html = htmlCancelamento({ cliente: cliente, campanha: campanha, mesAno: mesAno, dataFormatada: dataFormatada, motivo: motivo });

  for (var i = 0; i < uniqueEmails.length; i++) {
    GmailApp.sendEmail(uniqueEmails[i], '[' + cliente + '] Campanha cancelada: ' + campanha, '', {
      htmlBody: html,
      name: 'Sistema Calendario Mkt',
    });
  }
}


// ============================================================
// CRIA ESTRUTURA DE PASTAS NO DRIVE
// ============================================================

function _abrirPastaBase(folderId, nomeFallback) {
  if (folderId) {
    try { return DriveApp.getFolderById(folderId); } catch(e) {}
  }
  const iter = DriveApp.searchFolders('title = "' + nomeFallback + '" and trashed = false');
  return iter.hasNext() ? iter.next() : DriveApp.createFolder(nomeFallback);
}

function _contarSubpastas(pasta) {
  const iter = pasta.getFolders();
  let c = 0;
  while (iter.hasNext()) { iter.next(); c++; }
  return c;
}

function _obterOuCriarSubpasta(pai, nome) {
  const iter = pai.searchFolders('title = "' + nome + '" and trashed = false');
  return iter.hasNext() ? iter.next() : pai.createFolder(nome);
}

function criarEstruturaEmail(infoCliente, campanha, mesAno) {
  try {
    const folderId  = infoCliente ? infoCliente.id_pasta_email : '';
    const nomeMes   = mesAno.replace('/', '-');
    const pastaBase = _abrirPastaBase(folderId, 'Campanhas NFP');
    const pastaMes  = _obterOuCriarSubpasta(pastaBase, nomeMes);
    const numDisp   = _contarSubpastas(pastaMes) + 1;
    const pastaDisp = pastaMes.createFolder('Disparo ' + numDisp + ' — ' + campanha);
    const pastaCopy = pastaDisp.createFolder('Copy');
    const pastaArte = pastaDisp.createFolder('Arte');
    const pastaBase2= pastaDisp.createFolder('Base');
    return {
      disparo: pastaDisp.getUrl(),
      copy:    pastaCopy.getUrl(),
      arte:    pastaArte.getUrl(),
      base:    pastaBase2.getUrl(),
    };
  } catch(e) {
    console.error('Erro criarEstruturaEmail:', e);
    return { disparo: '', copy: '', arte: '', base: '' };
  }
}

function criarEstruturaInstagram(infoCliente, campanha, mesAno) {
  try {
    const folderId  = infoCliente ? infoCliente.id_pasta_instagram : '';
    const nomeMes   = mesAno.replace('/', '-');
    const pastaBase = _abrirPastaBase(folderId, 'Campanhas NFP');
    const pastaMes  = _obterOuCriarSubpasta(pastaBase, nomeMes);
    const numPost   = _contarSubpastas(pastaMes) + 1;
    const pastaPost = pastaMes.createFolder('Post ' + numPost + ' — ' + campanha);
    const pastaArte = pastaPost.createFolder('Arte');
    return {
      disparo: pastaPost.getUrl(),
      arte:    pastaArte.getUrl(),
    };
  } catch(e) {
    console.error('Erro criarEstruturaInstagram:', e);
    return { disparo: '', arte: '' };
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

  // Fluxo sequencial
  if (campo === 'copy') {
    // Copy entregue → libera Arte
    sheet.getRange(row, COL.ARTE).setValue(STATUS_PENDENTE);
    try { enviarBriefingArte(row); } catch(e) { console.error('enviarBriefingArte:', e); }
  }

  if (campo === 'arte' || campo === 'dados') {
    // Arte + Dados ambos entregues → notifica Aprovador
    const arte  = sheet.getRange(row, COL.ARTE).getValue();
    const dados = sheet.getRange(row, COL.DADOS).getValue();
    if (arte === STATUS_OK && dados === STATUS_OK) {
      try { notificarAprovador(row); } catch(e) { console.error('notificarAprovador:', e); }
    }
  }

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
    { htmlBody: html, name: 'Sistema Calendario Mkt' }
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
        slug:               dados[i][0],
        nome:               dados[i][1],
        email_operador:     dados[i][2],
        email_copy:         dados[i][3],
        email_arte:         dados[i][4],
        email_dados:        dados[i][5],
        email_aprovador:    dados[i][6],
        id_pasta_email:     dados[i][7] ? String(dados[i][7]).trim() : '',
        id_pasta_instagram: dados[i][8] ? String(dados[i][8]).trim() : '',
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


