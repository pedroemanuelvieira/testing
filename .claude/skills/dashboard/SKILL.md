---
name: dashboard
description: "Reconstroi um relatorio Power BI como dashboard interativo, com inventario, contrato das metricas, mapa de conversao e validacao contra a origem. Usar para converter um relatorio ou criar um prototipo de dashboard a partir de dados exportados."
---

# Dashboard a partir de um relatório

1. **Material disponível** e o que permite:
   - PBIP com TMDL: estrutura, medidas e relações (usa `python3 -m foundry tmdl doc`).
   - CSV ou Excel exportado mais definições das medidas: interatividade sobre os dados exportados; falta confirmar grão e contexto da exportação.
   - PDF ou capturas: só reconstrução visual; a lógica e os filtros ficam por validar. Diz isso logo.
2. **Inventário:** páginas, visuais, campos, medidas, filtros, segmentadores, ordenação, drill.
3. **Contrato das métricas:** para cada KPI, fórmula, unidade, moeda, grão, agregação, calendário, filtros, tratamento de nulos e denominador, com um valor de referência da origem.
4. **Mapa de conversão:** `visual de origem → componente de destino → medida → interações → estado → limitação`. Regista equivalências parciais antes de as dar como concluídas.
5. **Constrói** um único ficheiro HTML autónomo em `out/dashboards/<nome>/index.html`, com os dados embutidos ou lidos de um CSV ao lado. Filtros funcionais, limpar filtros, estados de carregamento, erro e sem dados, unidade e data de atualização visíveis, legível no telemóvel. Se o ambiente tiver skills de visualização ou de dashboards instaladas, segue-as.
6. **Valida** origem contra destino: total geral, um período, um segmento e pelo menos uma combinação de filtros. Rácios e totais não aditivos recalculados pelo contrato, nunca somados. Define a tolerância de arredondamento e justifica-a.
7. **Entrega:** o dashboard, o mapa de conversão, o contrato e a evidência de validação. Se for maquete, diz que é maquete e o que falta para ligar dados reais.

Segurança: um filtro no navegador não é controlo de acesso. Não ponhas no HTML linhas que o destinatário não pode ver, nem credenciais ou tokens. A passagem a produção (publicação, permissões) é do Kenshin, com aprovação.
