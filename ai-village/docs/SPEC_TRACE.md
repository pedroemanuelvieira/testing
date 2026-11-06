# Rastreabilidade — Critérios de Aceitação (Drive: 11_AI_Village_App/CRITERIOS_ACEITACAO.md)

Legenda: **✔ automatizado** = teste que corre com `npm test` · **◐ parcial** = verificado só em parte (diz-se o quê) · **○ por fazer** · **n/a** = fora do âmbito desta fase (diz-se porquê).
Protocolo do documento: *ausência de prova nunca equivale a sucesso* e *screenshot não prova execução backend*. Por isso nada abaixo é «aceite»: **a aceitação do produto pertence ao Pedro** após relatório verificável.

| CA | Resumo | Estado | Prova |
|---|---|---|---|
| CA01 | CRUD de unidade/função/agente sem código; arquivar com tarefa ativa | ✔ | `core.test.js` — «CA01 · criar/editar…», «CA01 · arquivar agente…» |
| CA02 | Ciclos e 2.º orquestrador rejeitados; cargo não concede permissões | ✔ | `core.test.js` — «CA02» |
| CA03 | Delegação só no escopo; prioridade proposta vs aprovada | ✔ | `core.test.js` — «CA03» |
| CA04 | Conversa demo persiste no backend, ordem, rótulo demo, sem rede | ✔ | `chat.test.js` — «CA04» (×2) |
| CA05 | «Ocupado» só com tentativa real; sem timers fictícios | ✔ | `worker.test.js` — «CA05» |
| CA06 | F01 → 4/3/1/1/soma 8 no worker; alterar input altera resultado | ✔ | `worker.test.js` — «CA06»; E2E no browser |
| CA07 | CSV malformado, > limite, fórmulas, instruções maliciosas | ✔ | `worker.test.js` — «CA07» |
| CA08 | Detalhe com resultado, digests, executor, passos reais, limitações | ✔ | `worker.test.js` — «CA08» |
| CA09 | Pré-visualização exata, uso único, rótulo de simulação, zero saída | ✔ | `approvals.test.js` — «CA09» |
| CA10 | Negar/revogar/expirar/alterar payload → nada executa | ✔ | `approvals.test.js` — «CA10» + «Tarefa ↔ aprovação» |
| CA11 | Concorrência/retry: ≤ 1 efeito; chave com digest distinto rejeitada | ✔ | `approvals.test.js` — «CA11» (+ UNIQUE na BD) |
| CA12 | Transições inválidas, concluir sem prova, retry conserva falha | ✔ | `core.test.js` — «CA12»; `worker.test.js` — «CA07» (retry) |
| CA13 | Reinício preserva o domínio; storage do browser não é domínio | ✔ | `durability.test.js` — «CA13» (localStorage só guarda preferências de UI) |
| CA14 | Worker interrompido: lease/recuperação/reconciliação, sem duplicar | ✔ | `worker.test.js` — «CA14» (injeção de falha) |
| CA15 | Backup cifrado → restauro isolado; jobs suspensos; tombstones | ✔ | `durability.test.js` — «CA15»; CLI testado à mão |
| CA16 | Migração: sucesso preserva; falha não deixa estado parcial | ✔ | `durability.test.js` — «CA16» |
| CA17 | Isolamento entre mundos (IDs, pesquisa, artefactos, auditoria, BI, export) | ✔ | `security.test.js` — «CA17» (BD por mundo) |
| CA18 | Isolamento entre contas do mesmo mundo | ✔ | `security.test.js` — «CA18» (módulos; a API expõe 1 conta/mundo, H01) |
| CA19 | Catálogo honesto: planeada ≠ ligada; só prova datada promove | ✔ | `connections.test.js` — «CA19» |
| CA20 | Desligar/revogar: bloqueia jobs, invalida segredo/prova, tombstone | ✔ | `connections.test.js` — «CA20» |
| CA21 | Segredo-canário não vaza (respostas, BD, logs); rotação | ◐ | `connections.test.js` — «CA21». Cobre respostas HTTP, BD, auditoria e logs do processo; **não** inspeciona tráfego de rede real nem backups |
| CA22 | Conteúdo proibido (canários) bloqueado, nada persistido | ✔ | `chat.test.js` — «CA22» (chat, CSV, nota, payload) |
| CA23 | Desktop e 390 px: mapa/lista equivalentes, sem scroll horizontal | ◐ | E2E (`npm run e2e`): 390 px sem scroll horizontal; lista = mesmas ações do mapa. Revisão visual feita por capturas; **sem matriz de viewports/dispositivos** |
| CA24 | Teclado/leitor de ecrã/reduced motion | ◐ | Verificado: foco visível e **restaurado** ao fechar gaveta/modal, armadilha de foco, `role`/`aria-label`/`aria-live`, `prefers-reduced-motion`. **Por fazer:** auditoria WCAG 2.2 AA automática + leitor de ecrã real |
| CA25 | Direção visual coerente; assets identificados | ◐ | Vila em SVG próprio (sem assets de terceiros ⇒ sem licenças a inventariar). Retratos **provisórios** e identificados como tal; fotografia real por carregar. **Não** se alega fotorrealismo |
| CA26 | Modelo real: API comprovada, request_id, erros visíveis, sem demo silenciosa | ◐ | `chat.test.js` — «CA26» com **`fetch` simulado** (contrato, timeout, 429, desligar). **Chamada real à API não verificada** (sem chave neste ambiente) |
| CA27 | Promoção ao profissional | n/a | Mundo profissional é só desenho (G3). Bloqueio de execução/ficheiros/ligações testado em `worker.test.js` |
| CA28 | Retenção: conteúdo, mensagens, auditoria, backups vencidos | ✔ | `durability.test.js` — «CA28» (relógio controlado) |
| CA29 | 30 execuções sequenciais, p95 vs H07 | ✔ | `npm run measure`. Amostra desta máquina: feedback p95 ≈ 10 ms, conclusão p95 ≈ 18 ms (in-process, sem rede) — **amostra, não SLA** |
| CA30 | Outro implementador reproduz a demo sem credenciais | ◐ | `README.md` + `npm run e2e` reproduzem a jornada num servidor limpo; **ninguém além do autor a seguiu ainda** |

## Gates (REQUISITOS §11)

| Gate | Situação |
|---|---|
| **G1 — utilizável em demo** | **Candidato, não declarado.** CA01–CA22, CA28, CA29 verificados; CA21, CA23–CA26, CA30 parciais (acima). Aceitação é do Pedro. |
| G2 — AI real | Adaptador implementado e testado com mock; **por verificar com chave real** (CA26) e repetir CA17–CA22 nesse adaptador. |
| G3 — profissional | Não iniciado (por desenho). |
| G4 — release | Não aplicável ainda. |

## Hipóteses (REQUISITOS §3.2) — estado

H01 utilizador único ✔ · H02 monólito+worker ✔ (ADR-001) · H03 4 destinos ✔ · H04 organograma editável ✔ · H05 demo marcada ✔ · H06 CSV 1 MB/10 000 linhas ✔ (limites testados) · H07 metas medidas por amostra (`npm run measure`) · H08 retenção 30/90/7 dias ✔ (editável) · H09 sem saída de rede ✔ · H10 mundo = fronteira ✔ (BD por mundo).
**Por confirmar pelo Pedro:** H07/H08 antes de qualquer release; CF01 (reconciliação de nomes do ecossistema) — a app preserva D2/D3 e **não** altera fontes nem bots.
