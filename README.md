# Creative Dashboard — G4

Dashboard de performance do time Creative com dados em tempo real do Notion.

🔗 **[Ver dashboard](https://DavidChavesG4.github.io/creative-dashboard)**

## O que mostra
- KPIs gerais: total, atrasadas, canceladas, fora de SLA
- Volume por status, tipo de demanda e área solicitante
- Performance individual por designer
- Tabela de atrasos com drill-down

## Atualização automática
O dashboard atualiza automaticamente às **9h e 18h** em dias úteis via GitHub Actions.
Para atualizar manualmente: Actions → Update Creative Dashboard → Run workflow.

## Setup inicial
1. Vá em **Settings → Secrets → Actions**
2. Adicione o secret `NOTION_TOKEN` com o valor do token do Notion
3. Vá em **Settings → Pages** e selecione branch `main`, pasta `/` (root)
4. Aguarde ~2 minutos — o site estará disponível em `https://DavidChavesG4.github.io/creative-dashboard`
