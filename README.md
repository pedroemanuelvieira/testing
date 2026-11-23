# BI ML Studio

**Plataforma full stack de machine learning para a equipa de BI** — ligada ao Power BI Service, com um **agente
especializado para cada componente de ML**, especializada por **área e problema de negócio**, com **glossário
detalhado** que guia cada passo, **conselheiro interativo de hiperparâmetros** e **assistente (chatbot)** sempre
disponível.

```
Power BI Service ──► Agentes (enquadrar → dados → perfil → qualidade → features → modelos → parâmetros → treino
   (conector interno)           → avaliação → explicabilidade → governança → implementação → monitorização)
        ▲                                                                                     │
        └──────────────────── tabela de previsões + medidas DAX ◄──────────────────────────────┘
```

## O que inclui

| | |
|---|---|
| **20 agentes** | Enquadramento, Dados Power BI, Perfil (EDA), Qualidade (com deteção de *data leakage*), Features, Seleção de modelos, Conselheiro de hiperparâmetros, Treino, Previsão (séries temporais), Segmentação, Anomalias, Cabaz de compras, Avaliação, Explicabilidade, Governança & ética, Implementação no Power BI, Monitorização, Relatórios, Guia e Assistente. |
| **10 áreas de negócio · 25 casos de uso** | Churn, CLV, segmentação RFM, propensão a campanhas, previsão de vendas e procura, lead scoring, cross-sell, cabaz, atrasos de pagamento, tesouraria, anomalias em despesas, risco de crédito, fraude, ruturas de stock, atrasos e tempos de entrega, attrition, absentismo, volume de contactos, tempo de resolução, drivers de NPS, elasticidade de preço, manutenção preditiva, anomalias em sensores. Cada caso especializa os agentes (alvo, features, modelos, métricas, custos de erro, armadilhas, nível AI Act e tabela/medidas DAX para o Power BI). |
| **7 tipos de problema** | Classificação binária e multiclasse, regressão, previsão temporal, segmentação, deteção de anomalias e regras de associação. |
| **27 modelos** | Regressão logística/linear, Ridge/Lasso/Elastic Net, árvores, Random Forest, Extra Trees, HistGradientBoosting, LightGBM, XGBoost, KNN, SVM, Naive Bayes, MLP, naive sazonal, Holt-Winters, SARIMA, LightGBM global com lags e feriados PT, K-Means, GMM, hierárquico, DBSCAN, Isolation Forest, LOF, z-score robusto, Apriori. |
| **Conselheiro de hiperparâmetros** | Recomendação por modelo × caso de uso × perfil dos dados × objetivo, explicação de cada parâmetro (efeito de subir/descer), validação em tempo real, indicador de risco de overfitting/underfitting, comparação por validação cruzada nos dados do projeto e aplicação/bloqueio no projeto. |
| **Glossário** | 242 termos em 16 categorias (definição, exemplo em BI, fórmula, armadilhas, relacionados, passo do percurso, hiperparâmetros e casos onde aparece), percurso guiado de 13 passos, 8 guias e FAQ. Os termos aparecem como etiquetas com definição ao passar o rato em toda a plataforma. |
| **Assistente** | Claude com 11 ferramentas (glossário, casos, modelos, conselheiro, estado do projeto, execução de agentes) ou modo offline com a base de conhecimento. |
| **Power BI** | Adaptador para o conector interno (descoberta automática de métodos), API REST oficial (executeQueries + push datasets), demonstração com 16 tabelas realistas, ficheiros CSV/Excel. Escrita das previsões com motivos individuais e medidas DAX. |
| **MLOps** | Snapshots reprodutíveis, registo de modelos com versões e estados, campeão/challenger, scoring em lote e API REST, monitorização PSI/KS/χ² com simulação de drift, ficha do modelo, relatórios HTML. |

## Arranque rápido

### Docker

```bash
cp .env.example .env          # opcional: conector interno, service principal, ANTHROPIC_API_KEY
docker compose up --build
# http://localhost:8000
```

### Windows

Requisitos: [Python 3.12](https://www.python.org/downloads/windows/) (marcar *Add python.exe to PATH*) e
[Node.js LTS](https://nodejs.org/). Na pasta do projeto, duplo clique ou na linha de comandos:

```bat
install.bat                   :: cria .venv, instala dependências e compila a interface (só na 1.ª vez)
run.bat                       :: arranca em http://localhost:8000 e abre o browser
run.bat 8001                  :: outra porta, se a 8000 estiver ocupada
```

No PowerShell use `.\install.bat` e `.\run.bat`. Os dados de trabalho ficam na pasta `workspace`.

### Linux / macOS

```bash
make install                  # pip + npm
make run                      # compila o frontend e serve tudo em http://localhost:8000
# desenvolvimento: `make backend` (API com reload) + `make frontend` (Vite em :5173 com proxy)
```

Requisitos: Python ≥ 3.10 (recomendado 3.12), Node ≥ 18.

### Primeiro projeto (dados de demonstração)

1. **Casos de uso** → *Previsão de churn de clientes* → **Criar projeto**.
2. **Piloto automático** → em ~30 s os agentes percorrem enquadramento → governança.
3. Explore **Avaliação** (limiar ótimo em €), **Explicabilidade** e **Configurar hiperparâmetros**.
4. **Implementar no Power BI** publica a tabela `Previsoes_Churn` e mostra as medidas DAX.

Mais em [docs/GUIA_EQUIPA_BI.md](docs/GUIA_EQUIPA_BI.md).

## Ligar ao Power BI Service

```bash
export MLSTUDIO_INTERNAL_CONNECTOR="empresa_pbi.conector:PowerBIClient"
export MLSTUDIO_INTERNAL_CONNECTOR_KWARGS='{"ambiente": "producao"}'          # opcional
export MLSTUDIO_INTERNAL_CONNECTOR_METHODS='{"execute_dax": "correr_dax"}'     # só se os nomes forem diferentes
```

O adaptador descobre os métodos para listar workspaces/modelos semânticos/tabelas, executar DAX e escrever resultados,
aceitando DataFrames, listas, JSON da API REST ou objetos. Detalhes, alternativa REST e boas práticas de extração em
[docs/CONECTOR_POWERBI.md](docs/CONECTOR_POWERBI.md).

## Assistente com IA

```bash
export ANTHROPIC_API_KEY=...          # sem chave: modo offline (base de conhecimento)
export MLSTUDIO_CHAT_MODEL=claude-opus-5-5   # omissão
export MLSTUDIO_CHAT_EFFORT=medium           # low | medium | high
```

Usa a Messages API com ciclo de *tool use* no servidor, raciocínio adaptativo, *prompt caching* do system prompt e
fallback server-side em caso de recusa (`MLSTUDIO_CHAT_FALLBACKS=off` desativa). Em qualquer falha da API responde em
modo offline.

## Estrutura

```
backend/
  mlstudio/
    knowledge/      base de conhecimento (YAML) + pesquisa
    connectors/     interno, REST, demo, ficheiros, DAX
    ml/             features, fábrica de modelos, métricas, séries temporais, não supervisionado, drift, XAI
    advisor/        conselheiro de hiperparâmetros
    agents/         20 agentes especializados
    core/           projetos, registo de modelos, tarefas, orquestrador
    chat/           assistente (IA + offline)
    api/            FastAPI (serve também o frontend)
  tests/            62 testes (pytest)
frontend/           React + TypeScript + Vite + Recharts
docs/               arquitetura, conector Power BI, guia da equipa, extensão
examples/           modelo de conector interno
```

Arquitetura detalhada: [docs/ARQUITETURA.md](docs/ARQUITETURA.md). Como acrescentar casos de uso, termos, modelos
ou agentes: [docs/EXTENDER.md](docs/EXTENDER.md).

## API (principais rotas)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/knowledge/use-cases`, `/glossary`, `/models`, `/workflow`, `/guides`, `/search` | Base de conhecimento |
| GET | `/api/connectors/{id}/workspaces/…/tables` · POST `/api/connectors/{id}/query` | Power BI |
| POST | `/api/projects` · `/api/projects/{id}/agents/{agente}/run` · `/api/projects/{id}/autopilot` | Projetos e agentes (assíncrono) |
| GET | `/api/jobs/{id}` | Progresso de tarefas |
| POST | `/api/advisor/recommend` · `/validate` · `/compare` · `/apply` | Conselheiro |
| GET/POST | `/api/models` · `/api/models/{id}/promote` · `/api/models/{id}/predict` | Registo e scoring online |
| POST | `/api/chat` | Assistente |

Documentação interativa em `http://localhost:8000/docs`.

## Testes

```bash
make test     # pytest (conhecimento, conectores, DAX, conselheiro, agentes end-to-end, API, chatbot) + tsc
```
