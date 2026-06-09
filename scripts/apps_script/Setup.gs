// ============================================================
// SETUP: cria e formata a planilha inteira
// Execute esta função UMA VEZ após criar a planilha
// ============================================================

function configurarPlanilha() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  criarAbaSeNaoExiste(ss, SHEET_CAMPANHAS,  configurarAbaCampanhas);
  criarAbaSeNaoExiste(ss, SHEET_CLIENTES,   configurarAbaClientes);
  criarAbaSeNaoExiste(ss, SHEET_LINKS,      configurarAbaLinks);
  SpreadsheetApp.getUi().alert('✅ Planilha configurada com sucesso!');
}

function criarAbaSeNaoExiste(ss, nome, configurador) {
  let sheet = ss.getSheetByName(nome);
  if (!sheet) sheet = ss.insertSheet(nome);
  configurador(sheet);
}

// Colunas da aba CAMPANHAS:
// A  B     C        D               E                 F     G     H     I             J           K            L
// Cl Tipo  Mês-Ano  Data Planejada  Campanha/Assunto  Copy  Arte  Dados Status Geral  Link Drive  Link HTML RD  Obs

function configurarAbaCampanhas(sheet) {
  sheet.clearContents();

  const headers = [
    'Cliente', 'Tipo', 'Mês-Ano', 'Data Planejada',
    'Campanha / Assunto',
    'Copy', 'Arte', 'Dados', 'Status Geral',
    'Link Drive (insumos)', 'Link HTML (RD Station)', 'Observações'
  ];

  const hrng = sheet.getRange(1, 1, 1, headers.length);
  hrng.setValues([headers]);
  hrng.setBackground('#2C3E50')
      .setFontColor('#FFFFFF')
      .setFontWeight('bold')
      .setFontSize(11)
      .setVerticalAlignment('middle');
  sheet.setRowHeight(1, 36);

  // Larguras das colunas
  const larguras = [100, 110, 90, 120, 260, 60, 60, 60, 180, 200, 200, 200];
  larguras.forEach((w, i) => sheet.setColumnWidth(i + 1, w));

  // Validação: coluna Tipo (B)
  const tiposValidos = ['email', 'instagram', 'whatsapp', 'sms', 'outros'];
  const regra = SpreadsheetApp.newDataValidation()
    .requireValueInList(tiposValidos, true)
    .setAllowInvalid(false).build();
  sheet.getRange(2, 2, 500).setDataValidation(regra);

  // Centraliza colunas de status (F, G, H, I)
  sheet.getRange(1, 6, 500, 4).setHorizontalAlignment('center');

  // Formata coluna Data (D) como data
  sheet.getRange(2, 4, 500).setNumberFormat('dd/MM/yyyy');

  // Cor alternada nas linhas
  const regrasFormatacao = [
    SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=AND(ROW()>1,MOD(ROW(),2)=0)')
      .setBackground('#F8F9FA')
      .setRanges([sheet.getRange(2, 1, 500, headers.length)])
      .build(),
    // Status "Pronto" → verde
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains('Pronto')
      .setBackground('#D1FAE5').setFontColor('#065F46')
      .setRanges([sheet.getRange(2, 9, 500, 1)])
      .build(),
    // Status "Bloqueado" → vermelho
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains('Bloqueado')
      .setBackground('#FEE2E2').setFontColor('#991B1B')
      .setRanges([sheet.getRange(2, 9, 500, 1)])
      .build(),
    // Status "andamento" → amarelo
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextContains('andamento')
      .setBackground('#FEF3C7').setFontColor('#92400E')
      .setRanges([sheet.getRange(2, 9, 500, 1)])
      .build(),
  ];
  sheet.setConditionalFormatRules(regrasFormatacao);

  sheet.setFrozenRows(1);
  sheet.setFrozenColumns(1);
}

function configurarAbaClientes(sheet) {
  sheet.clearContents();

  const headers = [
    'Slug', 'Nome Completo', 'Email Operador',
    'Email Copy', 'Email Arte', 'Email Dados', 'Email Aprovador'
  ];
  const hrng = sheet.getRange(1, 1, 1, headers.length);
  hrng.setValues([headers]);
  hrng.setBackground('#2C3E50').setFontColor('#FFFFFF').setFontWeight('bold');

  // Exemplos
  const exemplos = [
    ['afesu',    'AFESU',              'barbara.aquino@timecaptacao.com.br', '', '', '', ''],
    ['leao',     'Instituto Leão',     '', '', '', '', ''],
    ['salesians','Salesianos',         '', '', '', '', ''],
    ['sagrada',  'Sagrada Família',    '', '', '', '', ''],
  ];
  sheet.getRange(2, 1, exemplos.length, exemplos[0].length).setValues(exemplos);

  const larguras = [110, 200, 240, 230, 230, 230, 230];
  larguras.forEach((w, i) => sheet.setColumnWidth(i + 1, w));
  sheet.setFrozenRows(1);
}

function configurarAbaLinks(sheet) {
  sheet.clearContents();

  const headers = [
    'Cliente (slug)', 'Nome Completo',
    'Link Calendário HTML', 'Link Pasta Drive', 'Observações'
  ];
  const hrng = sheet.getRange(1, 1, 1, headers.length);
  hrng.setValues([headers]);
  hrng.setBackground('#2C3E50').setFontColor('#FFFFFF').setFontWeight('bold');

  const instrucao = [
    ['afesu',    'AFESU',              '← cole aqui a URL do webapp para este cliente', 'https://drive.google.com/drive/...', ''],
    ['leao',     'Instituto Leão',     '', '', ''],
    ['salesians','Salesianos',         '', '', ''],
    ['sagrada',  'Sagrada Família',    '', '', ''],
  ];
  sheet.getRange(2, 1, instrucao.length, instrucao[0].length).setValues(instrucao);
  sheet.getRange(2, 3, instrucao.length, 1).setFontColor('#aaa').setFontStyle('italic');

  const larguras = [120, 200, 380, 300, 200];
  larguras.forEach((w, i) => sheet.setColumnWidth(i + 1, w));
  sheet.setFrozenRows(1);
}
