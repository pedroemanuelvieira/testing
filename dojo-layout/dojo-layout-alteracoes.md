# Dojo · alterações propostas ao layout

Acompanha `dojo-layout-proposta.html` (protótipo estático, **só dados fictícios** do brief). Para aplicar ao portal verdadeiro do lado profissional.

**Ideia central:** o ecrã inicial passa a ser **«Hoje»**, com leitura do dia em 5 segundos: o que correu, o que falhou e o que precisa de mim. O mapa passa a vista secundária. O menu «⋯ Mais» fica com 4 grupos e tudo é acessível pela paleta (Ctrl K).

> **Nota sobre os dados de exemplo.** Os KPIs do brief (9 previstas · 4 registadas, 1 com avisos · 1 falhou · 4 por correr) só batem certo se «hoje» for uma **sexta** à tarde e a triagem 4×/dia correr às 08:04, 12:04, 16:04 e 20:04. O protótipo fixa o relógio em **sexta, 14:10** e usa essas horas. Os tempos relativos do diário foram ajustados a esse relógio (ex.: «910 OK» fica «há 5 h» em vez de «há 10 min»).

---

## 1. Tokens

| Token | Antes | Depois | Porquê |
|---|---|---|---|
| `--bg --panel --panel2 --line --ink --muted` | — | **iguais** | identidade mantida |
| `--wood --wood-d --tatami --tatami2` | — | iguais | idem |
| `--red --gold --green --blue` + **`--teal #4f9a8f`** (novo nome para o «Em produção» das Pontes) | — | iguais, só para **fundos, bordas e anéis** | têm ≥ 3:1, o que basta para elementos não textuais |
| **`--faint-ink`** | — | `#9a8b7b` | `--faint #76695c` dá **3,2:1** sobre `--panel` e falha AA para texto; a nova variante dá **5,2:1** |
| **`--red-ink`** | — | `#ec7a62` | `--red` como texto dá **3,5:1** (falha); a nova variante dá **6,1:1** |
| **`--blue-ink`** | — | `#86a7cf` | `--blue` como texto dá **4,1:1** sobre `--panel` (falha); a nova variante dá **6,9:1** |
| **`--green-ink` / `--teal-ink`** | — | `#8fbf7b` / `#6fbcb0` | margem para `--panel2` (as originais ficam abaixo de 4,9) |
| **`--focus`** | — | `#f0c46a` | anel de foco de 3 px, visível sobre madeira e tatami |
| **escala tipográfica** | 15px base, tamanhos soltos | `--fs-xs 12 · s 13.5 · m 15 · l 18 · xl 24 · 2xl 34` | mais hierarquia: números grandes em Shippori Mincho, texto em Zen Kaku |
| **espaço** | — | `--gap 16 · --gap-s 10 · --side 380 · --dock-h 64` | |
| **breakpoints** | 520, 640, 680, 760, 900 | **760 · 900 · 1100 · 1280 · 1560** | menos pontos de quebra; o cabeçalho comprime-se por etapas |
| **tema claro** | — | opcional, via `[data-theme="light"]` (botão Aparência) | pedido como opcional |

Contraste medido (WCAG 2.x) sobre `--panel #201b16`: `--ink` 13,8 · `--muted` 6,2 · `--faint-ink` 5,2 · `--red-ink` 6,1 · `--gold` 7,6 · `--green-ink` 8,1 · `--blue-ink` 6,9 · `--teal-ink` 7,7.
**Regra:** estado = **ícone + texto** sempre (✔ OK · ⚠ Com avisos · ✕ Falhou/Não correu · ⧗ À espera do registo · – Sem registo ainda · ○ Ainda por correr). A cor nunca é a única pista.

---

## 2. Estrutura nova

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [穂 Dojo] [Hoje|Mapa|Quadro|Pontes|Números] [⌘ Comandos] [âmbito][⚲][☆][♥][●][天][⋯] │  ← UMA linha
├─────────────────────────────────────────────────────────┬────────────────────┤
│ HOJE (#today, novo, vista por omissão)                  │ #pane (separadores) │
│ ┌ Resumo numa frase + 4 KPIs (previstas·registadas·     │ Tarefas · Atividade │
│ │  falhou/não correu·por correr) ─────────────────────┐ │ · Agentes · Projetos│
│ ├ Precisa de mim (≤3) ─────┬ ML em produção + resto ──┤ │                     │
│ ├ Linha do tempo 0h–24h (por agente, «agora») ────────┤ │                     │
│ └ Rotinas da equipa (problemas primeiro) ─────────────┘ │                     │
│  Mapa / Quadro / Pontes / Números = vistas alternativas │                     │
└─────────────────────────────────────────────────────────┴────────────────────┘
#ticker (linha fixa em baixo: últimas execuções)
Telemóvel (≤760): uma coluna; dock fixo [Hoje|Tarefas|Projetos|Agentes|Mapa]; «Agora» (captura) dentro do Hoje.
```

### O que entra, sai ou muda em cada ecrã

| Zona | Antes | Depois |
|---|---|---|
| **Header** | 2 linhas, 14+ controlos | **1 linha**. Os contadores `#stats` ficam visíveis só ≥ 1560 px (repetem o painel). `#worldBadge`, `#focusPill` e a tecla da paleta escondem-se < 1280. Em telemóvel fica só selo, paleta, ligado, lanterna e Mais |
| **Seletor de vistas `#seg`** | Mapa · Quadro · Pontes · Números | **Hoje** · Mapa · Quadro · Pontes · Números (Hoje por omissão) |
| **Mapa** | ~65 % do ecrã, sempre visível | vista secundária (mesmo `#map` e controlos). Zoom, minimapa e andares mantêm-se |
| **«Hoje no portal»** | dentro do separador Atividade | **sobe para o topo do ecrã principal**, com uma frase-resumo |
| **Precisa de mim** | não existia | **novo**: falhas e «não correu» de rotinas + tarefas bloqueadas + avisos, no máximo 3, cada um com uma ação |
| **Linha do tempo do dia** | não existia | **nova**: eixo 0h–24h, uma linha por agente com execuções hoje e marcador «agora» |
| **Rotinas da equipa** | lista no separador Atividade | no Hoje, ordenadas **problemas primeiro**. Cada linha tem 4 informações: quem/o quê · cadência · última+próxima · estado |
| **Projetos ML** | painel no separador Projetos | os **em produção** aparecem também no Hoje (linha compacta); os fora de produção ficam como chips com o próximo passo no `title` |
| **Separador Atividade** | Hoje no portal + rotinas + ML + lembretes + diário | fica com **Diário + Lembretes** (o resto subiu para o Hoje) |
| **Cartão de tarefa** | até 7 chips + 5 ações | título · agente · estado · projeto · prazo; **máx. 2 ações visíveis** (Iniciar/Concluir + Editar); o resto (Bloquear, Invocar…) passa ao diálogo |
| **Menu «⋯ Mais»** | 21 itens numa lista | **4 grupos** (abaixo) e todos na **paleta** |
| **Telemóvel** | header encolhido + dock + ecrã «Agora» | dock com **Hoje** no 1.º lugar; «Agora» (captura rápida) integrado no topo do Hoje |
| **Ticker** | — (o `#ticker` existia) | linha fixa discreta com as últimas execuções; não é a única fonte desta informação |

### Menu «⋯ Mais» em 4 grupos (21 itens)

| Trabalho (7) | Equipa (4) | Dados (5) | Sistema (5) |
|---|---|---|---|
| Morning `btnMorning` | Cockpit PRO `btnCockpit` | KPIs `btnKpis` | Aparência `btnLook` |
| Fecho do dia `btnFecho` | Fluxo `btnFluxo` | Biblioteca `btnBiblio` | Painel lateral `btnSide` |
| Ata de reunião `btnAta` | Resumos `btnResumos` | Integridade `btnIntegr` | Cópia de segurança `btnBackup` |
| Sprint `btnSprint` | Registos `btnRegistos` | Higiene `btnHig` | Atalhos `btnKeys` |
| Semana `btnWeek` | | Ciclos e versões `btnNotes` ⚠ | Guia rápido `btnAjuda` |
| Agenda `btnAgenda` | | | |
| Modelos `btnModelos` | | | |

⚠ **A confirmar:** o brief lista 21 itens mas só 20 ids `btn*` têm nome evidente; assumi que **«Ciclos e versões» = `btnNotes`**. Se não for, só muda o rótulo.

---

## 3. Contrato com o JavaScript

### Ids: **todos os 61 da secção 7 mantêm-se**, sem duplicados (verificado por script)

| Id | Onde está agora | Alteração |
|---|---|---|
| `stats` | header | visível só ≥ 1560 px (CSS) |
| `btnPalette`, `palScrim`, `palInput` | header / paleta | a paleta passa a listar também os 21 itens do menu e as vistas (pode gerar-se a partir de `#toolMenu button`) |
| `worldBadge`, `btnFilter`, `focusPill`, `btnHealth`, `liveDot`, `liveTxt`, `lanternBadge` | header | só CSS (compressão por largura) |
| `seg` | header | **ganha o botão `data-view="hoje"`** |
| `btnMenu`, `toolMenu` + 21 `btn*` | menu | itens agrupados em 4 `div[role=group]`, com `role=menuitem` |
| `map rooms agents minimap zoomctl zIn zOut zFit roomBar` | dentro de `section[data-viewbox="mapa"]` | o mapa deixa de estar sempre visível |
| `board`, `bpbar bpNew bpRetTpl bpboard`, `numview` | `section[data-viewbox=…]` | idem |
| `pane` | coluna direita | sem alterações de estrutura |
| `mobnow mobCap mobCapIn mobRem mobnowList` | **dentro de `#today`** (só em telemóvel) | o ecrã «Agora» passa a bloco do Hoje |
| `dock` | fixo em baixo (≤ 760 px) | ordem: eventos (rótulo **Hoje**), tarefas, projetos, agentes, mapa |
| `scrim dlg toast ticker` | iguais | `#dlg` como `<dialog>` com `showModal()` (foco e Esc nativos) |

### Ids **novos**

| Id novo | Para quê | Impacto no JS |
|---|---|---|
| `today` | contentor do ecrã Hoje | o router de vistas tem de reconhecer `hoje` |
| `needs`, `mlLive`, `mlRest`, `timeline`, `routines` | alvos de render dentro do Hoje | **funções de render novas** (o protótipo traz versões simples: `renderToday()`) |
| `paneBody`, `todayTitle`, `needTitle`, `mlTitle`, `tlTitle`, `rotTitle`, `dlgTitle`, `dlgBody`, `pal`, `palList`, `main` | estrutura e acessibilidade (`aria-labelledby`) | opcionais |

### Atributos de dados

| Atributo | Antes | Depois |
|---|---|---|
| `data-view` | `mapa\|quadro\|pontes\|numeros` | **+ `hoje`** (vista por omissão). As secções alternativas usam `data-viewbox="<vista>"` para mostrar/esconder |
| `data-tab` | `tarefas\|eventos\|agentes\|projetos` | **igual**. «eventos» continua a mostrar o texto «Atividade», mas agora contém Diário + Lembretes |
| `data-dock` | `mapa\|tarefas\|agentes\|projetos\|eventos` | **iguais valores**, nova ordem; `eventos` tem o rótulo **«Hoje»** e abre o Hoje (não o separador Atividade) |
| `data-floor` | `0\|1` | igual (dentro de `#roomBar`) |
| **novo** `body[data-m]` | — | `hoje\|painel\|mapa`: só em telemóvel, decide que coluna se vê |

### Classes (todas reutilizadas e estilizadas)

| Classe | Uso proposto |
|---|---|
| `portal` | cartão-cabeçalho do Hoje (resumo + KPIs) |
| `kpis` / `kpi` (+ `.ok .bad .soon .warn`) | grelha de 4 KPIs; o número grande em serif e a borda esquerda codificam o estado (com texto) |
| `chip` (+ `.ok .warn .bad .soon .stale .pro .link .on`) | **`.ok` e `.warn` são novas variantes** (antes só `.bad .soon .pro .link .on .stale`) |
| `arow` | linha de rotina (avatar · nome · últ./próx. · estado) |
| `av` (+ `.ok .bad .warn .soon`) | avatar com **anel colorido pelo estado** (diário, rotinas, linha do tempo) |
| `tx`, `when`, `mis`, `meta`, `sub`, `sub2` | texto principal, hora, nota secundária, metadados |
| `ml-live`, `mlpj`, `mlpj-row`, `mlpj-rest` | ML em produção (linha) e fora de produção (chips) |
| `task` (+ `em_curso bloqueada pendente concluida`) | cartão de tarefa com borda esquerda pelo estado |
| `group`, `toolbar`, `ev`, `prow`, `bar`, `kcard`, `bprow`, `numcard`, `row2`, `sec3`, `note`, `empty`, `foot`, `btn .small .primary`, `pill`, `dj-off` | iguais no papel; novo visual |
| **novas** | `need` (cartão «precisa de mim»), `tl`, `track`, `dot`, `now`, `axis` (linha do tempo), `kcol`, `kcols` (colunas kanban), `seal`, `brand`, `tabs`, `panebody`, `legend`, `summary`, `dayhead`, `kanji`, `agentrow` |

---

## 4. Acessibilidade (o que o protótipo garante)

- Foco visível de 3 px (`--focus`) em todos os controlos. Paleta com ↑/↓/Enter/Esc e devolução do foco; `#dlg` nativo.
- Botões só com ícone têm `aria-label` (filtro, saúde, lanterna, zoom). O menu usa `aria-expanded`/`aria-controls`/`role=menu`.
- Estados sempre com **ícone + texto**; a linha do tempo tem `aria-label` por ponto e uma legenda.
- `prefers-reduced-motion` desliga animações. Sem scroll horizontal em 390, 1100 e 1440 px (verificado).
- **Por fazer no portal real:** auditoria com leitor de ecrã; confirmar o contraste dos estados das **Pontes** com os novos `-ink`.

## 5. Ordem sugerida de aplicação

1. Tokens novos (só acrescentar; nada parte).
2. `data-view="hoje"` + `#today` + render das 5 secções a partir das coleções `rotina`/`evento` existentes (cálculo: previstas = slots de hoje; «não correu» = slot passado há mais de X sem registo).
3. Mover «Hoje no portal», rotinas e ML do separador Atividade para o Hoje; deixar Diário + Lembretes.
4. Menu em grupos + paleta a partir de `#toolMenu`.
5. Header compacto e dock reordenado; «Agora» dentro do Hoje.
6. Simplificar o cartão de tarefa (ações secundárias para o `#dlg`).
