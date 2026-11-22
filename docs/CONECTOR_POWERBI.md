# Ligar o BI ML Studio ao Power BI Service

A plataforma fala com os dados através de uma interface única (`DataConnector`). Há quatro implementações:

| Conector | Quando usar | Configuração |
|---|---|---|
| **Interno** (`internal`) | Produção — usa o conector Power BI já desenvolvido pela equipa | `MLSTUDIO_INTERNAL_CONNECTOR` |
| **API REST oficial** (`rest`) | Alternativa quando o conector interno não está disponível | Service principal (`PBI_*`) |
| **Demonstração** (`demo`) | Formação e testes — 16 tabelas sintéticas realistas | Ativo por omissão (`MLSTUDIO_DEMO=0` desativa) |
| **Ficheiros** (`files`) | CSV/Excel/Parquet exportados | Sempre ativo |

Quando o conector interno está configurado, passa a ser o conector por omissão.

---

## 1. Conector interno (recomendado)

### 1.1 Configuração mínima

```bash
# módulo Python e classe (ou função-fábrica) do vosso conector
export MLSTUDIO_INTERNAL_CONNECTOR="empresa_pbi.conector:PowerBIClient"
# opcional: pasta a acrescentar ao PYTHONPATH (se o pacote não estiver instalado)
export MLSTUDIO_INTERNAL_CONNECTOR_PATH="/opt/empresa/libs"
# opcional: argumentos do construtor (JSON)
export MLSTUDIO_INTERNAL_CONNECTOR_KWARGS='{"ambiente": "producao"}'
```

Ou, em ficheiro (`MLSTUDIO_CONFIG=mlstudio.yaml`) — ver `mlstudio.example.yaml`.

### 1.2 Como o adaptador encontra os métodos

O adaptador (`backend/mlstudio/connectors/internal.py`) procura, para cada operação, o primeiro método existente:

| Operação | Nomes procurados (por ordem) | Obrigatório |
|---|---|---|
| listar workspaces | `list_workspaces`, `get_workspaces`, `workspaces`, `list_groups`, `get_groups`, `listar_workspaces`, `obter_workspaces` | sim |
| listar modelos semânticos | `list_datasets`, `get_datasets`, `datasets`, `list_semantic_models`, `get_semantic_models`, `listar_datasets`, … | sim |
| listar tabelas | `list_tables`, `get_tables`, `tables`, `listar_tabelas`, `obter_tabelas` | não (usa `INFO.VIEW.TABLES()`) |
| executar DAX | `execute_dax`, `run_dax`, `execute_query`, `execute_queries`, `run_query`, `query`, `dax_query`, `executar_dax`, `executar_consulta` | DAX **ou** leitura de tabela |
| ler tabela | `read_table`, `get_table`, `get_table_data`, `fetch_table`, `table_to_dataframe`, `ler_tabela`, `obter_tabela` | — |
| escrever tabela | `write_table`, `push_table`, `push_dataframe`, `upload_dataframe`, `write_dataframe`, `push_rows`, `escrever_tabela`, `publicar_tabela` | não (exporta ficheiros) |
| testar ligação | `test_connection`, `ping`, `health_check`, `check_connection`, `testar_ligacao` | não |

Se os nomes forem outros, fixe-os:

```bash
export MLSTUDIO_INTERNAL_CONNECTOR_METHODS='{"list_workspaces": "obter_areas", "execute_dax": "correr_consulta"}'
```

**Argumentos.** Os valores são passados pelo nome quando os parâmetros do método usam nomes conhecidos
(`workspace_id`/`group_id`/`workspace`, `dataset_id`/`semantic_model_id`/`dataset`, `query`/`dax`/`consulta`,
`table`/`tabela`, `df`/`dataframe`/`dados`, …). Parâmetros obrigatórios com nomes desconhecidos recebem os valores pela
ordem `workspace → dataset → (nome do dataset) → tabela → consulta → dados → modo`.

**Respostas aceites.** `pandas.DataFrame`, lista de dicionários, JSON da API REST (`{"value": [...]}` e
`{"results": [{"tables": [{"rows": [...]}]}]}`), objetos com atributos `id`/`name`, ou objetos com `to_pandas()`.
Colunas no formato `Tabela[coluna]` são limpas automaticamente; datas ISO são convertidas.

### 1.3 Verificar

1. Arranque a aplicação e abra **Dados (Power BI)** → escolha "Power BI (conector interno)".
2. O cartão de teste mostra "Ligação OK" e os métodos resolvidos estão em `GET /api/connectors`.
3. Se algo falhar, a mensagem indica o método/operação em falta.

Um modelo de camada fina está em [`examples/internal_connector_template.py`](../examples/internal_connector_template.py)
e há um teste automático com um conector "estranho" em `backend/tests/test_connectors.py`.

---

## 2. API REST oficial (alternativa)

Requisitos no Power BI / Entra ID:

1. Registo de aplicação (service principal) com segredo.
2. Definição de tenant **"Permitir que service principals usem APIs do Power BI"** e
   **"Dataset Execute Queries REST API"** ativas.
3. O service principal é **Membro** (ou Contribuidor) dos workspaces.

```bash
export PBI_TENANT_ID="..."
export PBI_CLIENT_ID="..."
export PBI_CLIENT_SECRET="..."     # apenas via ambiente/cofre, nunca em ficheiros
```

Limites da API `executeQueries`: 100 000 linhas ou 1 000 000 de valores por consulta e 120 consultas/minuto por
utilizador. Para tabelas maiores use filtros (por exemplo por período) ou o conector interno.

A escrita de resultados usa **push datasets** (blocos de 10 000 linhas, modo `replace` apaga as linhas anteriores).

---

## 3. Extração de dados para ML — boas práticas

- **Granularidade = unidade de decisão.** Para churn, uma linha por cliente; para atrasos, uma linha por fatura.
- **Data de corte.** As features devem usar só informação anterior ao momento da previsão (evita *data leakage*).
- **Prefira o modelo semântico certificado** — as medidas e colunas calculadas garantem as mesmas definições dos relatórios.
- **DAX recomendado** para tabelas de treino:

```dax
EVALUATE
SUMMARIZECOLUMNS(
    'Cliente'[ClienteID], 'Cliente'[Segmento], 'Cliente'[Antiguidade],
    "Compras_12m", [Nº Compras 12M],
    "Valor_12m", [Vendas 12M],
    "Reclamacoes_6m", [Reclamações 6M],
    "Churn", [Churn 90D]
)
```

- O snapshot de cada projeto é guardado em Parquet — o treino é reproduzível mesmo que o modelo semântico mude.

## 4. Devolver previsões ao Power BI

O **Agente de Implementação**:

1. Promove o modelo a produção no registo.
2. Extrai a população atual pelo conector (ou usa o snapshot).
3. Gera a tabela (ID, probabilidade/valor, banda de risco, decisão, **3 principais motivos**, versão, data).
4. Publica: `write_table` do conector (modelo semântico "Resultados ML") e/ou ficheiros CSV (`;` e `,` decimais), Excel e Parquet.
5. Entrega as **medidas DAX** e os **visuais recomendados** do caso de uso.

No relatório, relacione a tabela de previsões com a dimensão (ex.: `Clientes[cliente_id]`) e agende o scoring com a
mesma periodicidade da atualização do modelo semântico (`POST /api/projects/{id}/agents/deployment/run`).
