# Setup do Calendário de Comunicação NFP

## O que este sistema faz

1. **Planilha Google Sheets** com visual de calendário + lista detalhada por mês
2. **Disparo automático de briefing** para equipes (copy, arte, dados) quando nova campanha é cadastrada  
3. **Confirmação por email** — equipe clica um botão → planilha atualiza ✅ automaticamente
4. **Quando todos confirmam** → operador recebe email para criar a campanha no RD Station
5. **Links consolidados** — HTML gerado + pasta Drive ficam na planilha

---

## Passo a passo de instalação

### 1. Criar a planilha

1. Acesse [sheets.new](https://sheets.new) para criar uma nova planilha
2. Renomeie para **"Calendário NFP — Comunicação"**

### 2. Abrir o Apps Script

1. Na planilha: **Extensões → Apps Script**
2. Exclua o código padrão (`function myFunction() {}`)

### 3. Criar os arquivos de código

No editor do Apps Script, crie os seguintes arquivos:

| Nome do arquivo | Conteúdo |
|-----------------|---------|
| `Codigo.gs`     | Cole o conteúdo de `Codigo.gs` |
| `Email.gs`      | Cole o conteúdo de `Email.gs` |
| `Calendario.gs` | Cole o conteúdo de `Calendario.gs` |
| `Setup.gs`      | Cole o conteúdo de `Setup.gs` |
| `Calendario.html` | **HTML file** → Novo → HTML → cole o conteúdo de `Calendario.html` |

### 4. Configurar e formatar a planilha

1. No Apps Script: **Executar → `configurarPlanilha`**
2. Autorize as permissões solicitadas (Gmail, Sheets, Drive)
3. A planilha agora terá 3 abas: CAMPANHAS, CLIENTES, LINKS CALENDÁRIOS

### 5. Preencher a aba CLIENTES

Preencha os emails de cada cliente:

| Slug | Nome | Email Operador | Email Copy | Email Arte | Email Dados | Email Aprovador |
|------|------|---------------|-----------|-----------|------------|----------------|
| afesu | AFESU | barbara@... | copy@... | arte@... | dados@... | aprovador@... |

### 6. Publicar o webapp (calendário público)

1. Apps Script → **Implantar → Nova implantação**
2. Tipo: **Aplicativo da Web**
3. Executar como: **Eu (sua conta)**
4. Acesso: **Qualquer pessoa** (para que o link seja acessível sem login)
5. Clique em **Implantar** e copie a URL

A URL do calendário de um cliente específico será:
```
https://script.google.com/macros/s/SEU_ID/exec?cliente=afesu
```

### 7. Configurar o trigger de edição

1. Apps Script → **Gatilhos (ícone de relógio)**
2. Adicionar gatilho:
   - Função: `onEdit`
   - Evento: **Da planilha → Ao editar**

### 8. Preencher a aba LINKS CALENDÁRIOS

Para cada cliente, cole a URL no formato:
```
https://script.google.com/macros/s/SEU_ID/exec?cliente=SLUG_DO_CLIENTE
```

### 9. Adicionar `spreadsheet_id` no `clients.yaml`

No repositório, edite `config/clients.yaml` e adicione o ID da planilha para cada cliente:

```yaml
clients:
  - name: AFESU
    slug: afesu
    drive_folder_id: "..."
    rdstation_list_id: "..."
    spreadsheet_id: "ID_DA_SUA_PLANILHA"   ← adicionar esta linha
    operador_email: "..."
```

O ID da planilha está na URL: `https://docs.google.com/spreadsheets/d/ID_AQUI/edit`

---

## Como usar no dia a dia

### Cadastrar nova campanha

1. Abra a aba **CAMPANHAS**
2. Preencha uma nova linha: Cliente, Tipo, Mês-Ano, Data Planejada, Campanha
3. **Ao preencher o campo "Cliente"**, o sistema automaticamente:
   - Cria os status ⏳ para Copy, Arte e Dados
   - Envia email de briefing para cada equipe

### Acompanhar status

- ⏳ = Aguardando entrega
- ✅ = Entregue (confirmado via email ou manualmente)
- 🔴 = Bloqueado

### Ver o calendário visual

Acesse o link de cada cliente na aba **LINKS CALENDÁRIOS**

### Quando o HTML é gerado automaticamente

Após o `email_flow.py` rodar (GitHub Actions), a coluna **K — Link HTML** é preenchida automaticamente com o link para o arquivo HTML no Drive, pronto para ser colado no RD Station.

---

## Estrutura das colunas (aba CAMPANHAS)

| Col | Campo | Preenchido por |
|-----|-------|---------------|
| A | Cliente (slug) | Operador |
| B | Tipo | Operador |
| C | Mês-Ano | Operador |
| D | Data Planejada | Operador |
| E | Campanha / Assunto | Operador |
| F | Copy ✅/⏳ | Auto (via email) |
| G | Arte ✅/⏳ | Auto (via email) |
| H | Dados ✅/⏳ | Auto (via email) |
| I | Status Geral | Auto (calculado) |
| J | Link Drive (insumos) | Auto (email_flow.py) |
| K | Link HTML RD Station | Auto (email_flow.py) |
| L | Observações | Operador |
