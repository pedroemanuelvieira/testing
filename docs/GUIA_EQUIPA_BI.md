# Guia da equipa de BI

## Instalar

- **Windows:** instale o Python 3.12 (com *Add python.exe to PATH*) e o Node.js LTS. Na pasta do projeto faça duplo
  clique em `install.bat` (só na primeira vez) e depois em `run.bat`. O browser abre em http://localhost:8000.
- **Linux/macOS:** `make install` e `make run`.
- **Docker:** `docker compose up --build`.

## Em 5 minutos

1. **Casos de uso** → escolha, por exemplo, *Previsão de churn de clientes* → **Criar projeto**.
2. No projeto, clique **Piloto automático**. Os agentes executam o percurso (≈ 30 s com dados de demonstração).
3. Veja **Avaliação** (AUC, lift, limiar ótimo e valor em euros) e **Explicabilidade** (drivers e motivos).
4. Em **Configurar hiperparâmetros** altere valores e veja os avisos e o risco de overfitting em tempo real; use
   **Comparar com recomendado** para medir o efeito nos seus dados.
5. Em **Implementar no Power BI** publique a tabela de previsões e copie as medidas DAX sugeridas.

## O percurso de 13 passos

| Passo | O que decide | Onde olhar primeiro |
|---|---|---|
| 1. Enquadramento | Pergunta, alvo, decisão, custos de erro | Ficha do problema, baseline |
| 2. Dados | Tabela/consulta DAX e granularidade | Pré-visualização, tipos de colunas |
| 3. Perfil | Distribuições e relação com o alvo | Poder preditivo individual |
| 4. Qualidade | O que excluir/corrigir | Score e **suspeitas de leakage** |
| 5. Features | Transformações | Informação mútua |
| 6. Modelos | Candidatos | Justificação de cada modelo |
| 7. Hiperparâmetros | Complexidade | Avisos e risco de overfitting |
| 8. Treino | Campeão | Leaderboard e gap treino–CV |
| 9. Avaliação | Limiar e impacto | Lucro por limiar, lift, calibração |
| 10. Explicabilidade | Confiança no modelo | Drivers, PDP, motivos |
| 11. Governança | Conformidade | PII, equidade, AI Act, model card |
| 12. Implementação | Publicação | Tabela, medidas DAX, visuais |
| 13. Monitorização | Re-treino | PSI por variável e estado |

Cada passo mostra **objetivo, porquê, como fazer, checklist e erros comuns**, com os conceitos ligados ao glossário.

## Ler os resultados com espírito crítico

- **AUC > 0,97** num problema de negócio → quase sempre *data leakage*. Veja a importância das variáveis.
- **Accuracy** engana com classes desequilibradas — use PR-AUC, recall e o lift.
- **Limiar 0,5** raramente é o certo — use a matriz de custo-benefício ou a capacidade operacional.
- **Importância ≠ causalidade** — valide intervenções com testes A/B e grupo de controlo.
- **Previsão**: compare sempre com o **naive sazonal** (MASE < 1) e vigie o **bias**.
- **Segmentação**: 3–7 segmentos acionáveis valem mais do que a silhueta máxima.

## O assistente

O botão no canto inferior direito abre o assistente, que conhece o projeto em que está. Exemplos:

- "Qual é o próximo passo e porquê?"
- "Que parâmetros uso no XGBoost para fraude com 1% de positivos?"
- "Diferença entre precisão e recall"
- "Explica os resultados da avaliação deste projeto"

Com `ANTHROPIC_API_KEY` configurada o assistente usa IA (e pode executar agentes a pedido); sem chave responde em modo
offline com a base de conhecimento.

## Dados de demonstração

16 tabelas em 4 workspaces simulam modelos semânticos reais (CRM, vendas diárias, talões, stock, faturas, tesouraria,
despesas, crédito, transações, entregas, sensores, colaboradores, tickets, NPS…). Incluem sinal real, ruído,
valores em falta, duplicados, outliers e **armadilhas didáticas** (ex.: `dias_atraso` no caso de atrasos de pagamento
é leakage — o Agente de Qualidade deteta-o).
