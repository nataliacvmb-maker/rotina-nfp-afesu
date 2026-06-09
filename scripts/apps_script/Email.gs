// ============================================================
// TEMPLATES DE EMAIL HTML
// ============================================================

function htmlBriefing(d) {
  const tipoLabel = (TIPOS_CONFIG[d.tipo] || TIPOS_CONFIG['outros']).label;

  const linkDriveHtml = d.linkDrive
    ? '<a href="' + d.linkDrive + '" style="color:#2563eb;font-weight:600">Abrir pasta no Drive &rarr;</a>'
    : '&mdash;';

  const obsHtml = d.obs
    ? '<div style="background:#fff9e6;border-left:4px solid #f1c40f;padding:10px 14px;margin-top:12px;border-radius:4px;color:#555;font-size:14px"><strong>Obs:</strong> ' + d.obs + '</div>'
    : '';

  const baseHtml = d.instrucaoBase
    ? '<div style="background:#e8f4fd;border-left:4px solid #2563eb;padding:12px 16px;border-radius:4px;margin-top:14px;font-size:14px;color:#1e3a5f"><strong>Base de dados:</strong> ' + d.instrucaoBase + '</div>'
    : '';

  const notaFinalHtml = d.linkDrive
    ? '<div style="background:#fef9ec;border:1px solid #fde68a;padding:12px 16px;border-radius:6px;margin-top:18px;font-size:13px;color:#78350f">'
      + '<strong>Importante:</strong> salve na pasta acima <strong>somente a versao final</strong>. '
      + 'O sistema fara a importacao automatica no RD Station a partir dos arquivos encontrados nessa pasta.'
      + '</div>'
    : '';

  return '<!DOCTYPE html>'
    + '<html><head><meta charset="UTF-8">'
    + '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"></head>'
    + '<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">'
    + '<div style="max-width:600px;margin:32px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">'

    + '<div style="background:#1e293b;padding:24px 32px">'
    + '<p style="margin:0;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px">Sistema Calendario Mkt</p>'
    + '<h1 style="margin:8px 0 0;color:#fff;font-size:21px">Novo briefing de campanha</h1>'
    + '</div>'

    + '<div style="padding:28px 32px">'
    + '<p style="margin:0 0 6px;color:#555;font-size:15px">Ola, <strong>' + d.nomeEquipe + '</strong>!</p>'
    + '<p style="margin:0 0 20px;color:#555;font-size:15px">Uma nova campanha foi cadastrada e precisa da sua entrega:</p>'

    + '<div style="background:#f8f9fa;border-radius:8px;padding:20px 24px;margin-bottom:20px">'
    + '<table style="width:100%;border-collapse:collapse;font-size:14px;color:#444">'
    + '<tr><td style="padding:6px 0;width:130px;color:#888;vertical-align:top">Cliente</td><td style="font-weight:bold;color:#1e293b">' + d.cliente + '</td></tr>'
    + '<tr><td style="padding:6px 0;color:#888;vertical-align:top">Campanha</td><td style="font-weight:bold">' + d.campanha + '</td></tr>'
    + '<tr><td style="padding:6px 0;color:#888">Tipo</td><td>' + tipoLabel + '</td></tr>'
    + '<tr><td style="padding:6px 0;color:#888">Mes</td><td>' + d.mesAno + '</td></tr>'
    + '<tr><td style="padding:6px 0;color:#888">Data</td><td><strong>' + d.dataFormatada + '</strong></td></tr>'
    + '<tr><td style="padding:6px 0;color:#888;vertical-align:top">Pasta</td><td>' + linkDriveHtml + '</td></tr>'
    + '</table>'
    + '</div>'

    + '<div style="background:#eaf4fb;border-left:4px solid #2980b9;padding:12px 16px;border-radius:4px;margin-bottom:16px">'
    + '<p style="margin:0;color:#1a5276;font-size:14px"><strong>Sua tarefa:</strong> ' + d.tarefa + '</p>'
    + '</div>'

    + baseHtml
    + obsHtml
    + notaFinalHtml

    + '<div style="text-align:center;margin-top:28px">'
    + '<p style="color:#555;font-size:13px;margin-bottom:12px">Quando sua entrega estiver na pasta do Drive, clique abaixo para confirmar:</p>'
    + '<a href="' + d.linkConfirmar + '" style="display:inline-block;background:#16a34a;color:#fff;padding:14px 36px;border-radius:6px;text-decoration:none;font-size:16px;font-weight:bold">Confirmar entrega</a>'
    + '<p style="color:#aaa;font-size:11px;margin-top:10px">Este link confirma apenas a entrega do ' + d.nomeEquipe + '.</p>'
    + '</div>'
    + '</div>'

    + '<div style="background:#f8f9fa;padding:14px 32px;border-top:1px solid #eee;text-align:center">'
    + '<p style="margin:0;color:#aaa;font-size:11px">Sistema Calendario Mkt &mdash; Time Captacao NFP</p>'
    + '</div>'
    + '</div></body></html>';
}


function htmlConfirmacaoSucesso(campo, cliente, campanha) {
  const nomes = { copy: 'Copy', arte: 'Arte', dados: 'Dados' };
  return `<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>body{font-family:Arial,sans-serif;background:#f4f4f4;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}</style>
</head>
<body>
<div style="background:#fff;border-radius:12px;padding:48px 56px;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.08);max-width:420px">
  <div style="font-size:64px;margin-bottom:16px">✅</div>
  <h2 style="color:#27ae60;margin:0 0 8px">Entrega confirmada!</h2>
  <p style="color:#555;font-size:15px;margin:0 0 4px"><strong>${nomes[campo] || campo}</strong> — ${cliente}</p>
  <p style="color:#888;font-size:14px;margin:0">${campanha}</p>
  <div style="margin-top:24px;padding:12px;background:#f0faf4;border-radius:6px">
    <p style="color:#555;font-size:13px;margin:0">O status foi atualizado na planilha automaticamente. Quando os três times confirmarem, o operador será notificado.</p>
  </div>
</div>
</body>
</html>`;
}


function htmlConfirmacaoJaFeita() {
  return `<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>body{font-family:Arial,sans-serif;background:#f4f4f4;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}</style>
</head>
<body>
<div style="background:#fff;border-radius:12px;padding:48px 56px;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.08);max-width:420px">
  <div style="font-size:64px;margin-bottom:16px">ℹ️</div>
  <h2 style="color:#2980b9;margin:0 0 8px">Já confirmado</h2>
  <p style="color:#888;font-size:14px;margin:0">Esta entrega já foi marcada como concluída anteriormente.</p>
</div>
</body>
</html>`;
}


function htmlCancelamento(d) {
  const motivoHtml = d.motivo
    ? '<div style="background:#fff9e6;border-left:4px solid #f1c40f;padding:10px 14px;margin-top:12px;border-radius:4px;color:#555;font-size:14px"><strong>Motivo:</strong> ' + d.motivo + '</div>'
    : '';

  return '<!DOCTYPE html>'
    + '<html><head><meta charset="UTF-8">'
    + '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"></head>'
    + '<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">'
    + '<div style="max-width:600px;margin:32px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">'

    + '<div style="background:#dc2626;padding:24px 32px">'
    + '<p style="margin:0;color:#fca5a5;font-size:11px;text-transform:uppercase;letter-spacing:1px">Sistema Calendario Mkt</p>'
    + '<h1 style="margin:8px 0 0;color:#fff;font-size:21px">Campanha cancelada</h1>'
    + '</div>'

    + '<div style="padding:28px 32px">'
    + '<p style="margin:0 0 20px;color:#555;font-size:15px">A seguinte campanha foi cancelada:</p>'

    + '<div style="background:#f8f9fa;border-radius:8px;padding:20px 24px;margin-bottom:16px">'
    + '<table style="width:100%;border-collapse:collapse;font-size:14px;color:#444">'
    + '<tr><td style="padding:6px 0;width:130px;color:#888">Cliente</td><td style="font-weight:bold;color:#1e293b">' + d.cliente + '</td></tr>'
    + '<tr><td style="padding:6px 0;color:#888">Campanha</td><td style="font-weight:bold">' + d.campanha + '</td></tr>'
    + '<tr><td style="padding:6px 0;color:#888">Mes</td><td>' + d.mesAno + '</td></tr>'
    + '<tr><td style="padding:6px 0;color:#888">Data</td><td>' + d.dataFormatada + '</td></tr>'
    + '</table>'
    + '</div>'

    + motivoHtml

    + '<p style="color:#555;font-size:14px;margin-top:16px">Nenhuma acao necessaria da sua parte. As entregas desta campanha foram suspensas.</p>'
    + '</div>'

    + '<div style="background:#f8f9fa;padding:14px 32px;border-top:1px solid #eee;text-align:center">'
    + '<p style="margin:0;color:#aaa;font-size:11px">Sistema Calendario Mkt &mdash; Time Captacao NFP</p>'
    + '</div>'
    + '</div></body></html>';
}


function htmlProntoParaDisparo(cliente, campanha, mesAno) {
  return `<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
<div style="max-width:520px;margin:32px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)">
  <div style="background:#27ae60;padding:24px 32px">
    <h1 style="margin:0;color:#fff;font-size:22px">🚀 Insumos prontos para disparo!</h1>
  </div>
  <div style="padding:28px 32px">
    <p style="color:#555;font-size:15px">Os três times confirmaram a entrega para a campanha:</p>
    <div style="background:#f8f9fa;border-radius:8px;padding:16px 20px;margin:16px 0">
      <p style="margin:0 0 4px;font-size:16px;font-weight:bold;color:#2c3e50">${campanha}</p>
      <p style="margin:0;color:#888;font-size:14px">${cliente} — ${mesAno}</p>
    </div>
    <p style="color:#555;font-size:14px">✅ Copy confirmado<br>✅ Arte confirmada<br>✅ Base de dados confirmada</p>
    <p style="color:#555;font-size:14px;margin-top:20px">A automação irá importar os contatos no RD Station e gerar o HTML do email. <strong>Acompanhe a campanha no painel.</strong></p>
  </div>
  <div style="background:#f8f9fa;padding:14px 32px;border-top:1px solid #eee;text-align:center">
    <p style="margin:0;color:#aaa;font-size:11px">Sistema automatizado — Time Captação NFP</p>
  </div>
</div>
</body>
</html>`;
}
