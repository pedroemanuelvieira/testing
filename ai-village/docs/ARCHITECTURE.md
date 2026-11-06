# AI Village — Arquitetura

> Fonte de verdade: a pasta **Source_of_truth** do Drive do Pedro — `06_Arquitetura_de_agentes` (HIERARQUIA_E_PAPEIS, Plano do Orquestrador v2.2) e `11_AI_Village_App` (REQUISITOS.md, CRITERIOS_ACEITACAO.md, 06-11-2026).
> Este documento regista **como** essas decisões foram implementadas e onde a implementação se afasta delas.

## 1. Decisões herdadas do Drive (não reabertas aqui)

| ID | Decisão | Onde está na app |
|---|---|---|
| D1 | Pessoal só com dados fictícios; nada de dados reais de empresa | `server/modules/d1.js` — guarda antes da ingestão (chat, CSV, notas, payloads) |
| D2 | **Um orquestrador por mundo** | índice único parcial `one_active_orchestrator` na BD |
| D3 | Kai Pessoal e Kai Profissional; CEO/diretores são **cargos da app**, não orquestradores nem renomeações dos bots | `server/seed.js` (`orchestrator_flag` só no Kai; cargos CEO/CDO/CTO/COO/CCO são agentes novos) |
| D5/D6 | Pedro decide destinos de blueprint e **aprova** prioridades; o orquestrador só propõe | `proposed_priority` vs `approved_priority`; só o dono aprova |
| H02 | Monólito modular + worker | secção 2 |
| H03 | 4 destinos: Vila, Trabalho, Ligações, Configuração | `web/js/app.js` |
| H05 | Conversa demo determinística, claramente marcada | `server/adapters/demo.js`, rótulo `DEMO` em cada mensagem |
| H06–H08 | Limites de CSV, metas de latência, retenção | `settings.js` (valores editáveis), `scripts/measure-latency.js` |
| H09 | Sem saída de rede em ações consequentes; aprovação só de simulação | `approvals.js` — destinos só `simulado://…`, `external_calls = 0` |
| H10 | Mundo = fronteira de execução/dados/política | **uma BD SQLite por mundo** (`data/worlds/<mundo>.db`) |

As fichas do ecossistema (Ponte, Oráculo, Apolo, Feynman, Sócrates, Auditor 800 e o esquadrão 9xx) existem na app como **entidades da app** (`origin = 'ecosystem_ref'`) e dizem-no na descrição: não instalam nem alteram os bots originais.

## 2. Decisão de arquitetura (ADR-001)

**Escolha: A — monólito modular + worker.** (H02 do REQUISITOS §10.)

```
 Browser (JS puro, SVG)                       Processo 1: servidor HTTP                 Processo 2: worker
 ┌──────────────────────┐   JSON/HTTPS   ┌──────────────────────────────────┐        ┌──────────────────────┐
 │ Vila · Trabalho ·    │ ─────────────► │ http.js  (sessão, CSRF, CSP)     │        │ worker-main.js       │
 │ Ligações · Config    │ ◄───────────── │ ├─ org · tasks · chat · approvals │        │ claim → execute →    │
 │ (só mostra; não      │                │ ├─ connections · policy · bi      │        │ evidence (1 tx)      │
 │  decide nada)        │                │ ├─ d1 · audit · retention         │        │ lease · heartbeat    │
 └──────────────────────┘                │ └─ adapters: demo | anthropic     │        │ recoverExpired       │
                                         └───────────────┬──────────────────┘        └──────────┬───────────┘
                                                         │   node:sqlite (WAL, FKs, triggers)   │
                          ┌──────────────────────────────┴───────────────┬──────────────────────┘
                          ▼                                              ▼
                data/worlds/personal.db                      data/worlds/professional.db        data/village.db
                (domínio, auditoria, artefactos)             (idem — só desenho nesta conta)    (sessões, registo de mundos)
```

**Porquê A:** as invariantes mais críticas (aprovação de uso único, intenção idempotente, conclusão só com prova, orquestrador único) são *transações locais* — simples e verificáveis. B (serviços + eventos) traria consistência eventual e reconciliação sem carga, equipas ou SLAs que o justifiquem.

**Alternativa rejeitada — B (serviços orientados a eventos).** Gatilhos medidos para a reconsiderar: (1) o worker passa a competir por recursos com o servidor em carga real; (2) mais do que uma equipa a evoluir módulos de forma autónoma; (3) requisito de isolamento que um deployment separado por mundo não resolva. Antes de B: testes de contrato, autorização entre serviços, idempotência, ordenação/reconciliação e observabilidade.

**Stack:** Node ≥ 22.13, `node:sqlite` (SQLite embutido), HTTP nativo, frontend em ES modules **sem dependências e sem build**. Zero pacotes de terceiros ⇒ superfície de supply-chain nula e reprodução trivial (CA30). Custo: `node:sqlite` ainda é marcado *experimental* pelo Node — ver §9.

## 3. Mapa de módulos

| Módulo | Responsabilidade |
|---|---|
| `lib/util.js` | ids opacos, digests canónicos, relógio injetável (testes de retenção/leases), erros, redação de segredos |
| `lib/db.js` | transações imediatas, **migrações versionadas** (transação por migração + cópia prévia) |
| `modules/org.js` | OrgUnit/Role/Agent: CRUD, ciclos, arquivo seguro, **estado de atividade derivado** |
| `modules/policy.js` | Permission (deny-by-default), `authorizeDelegation` |
| `modules/tasks.js` | máquina de estados, delegação, idempotência, tentativas, trabalho manual |
| `modules/worker.js` | claim com lease, execução, recuperação, prova atómica |
| `modules/capabilities.js` | **registo de capacidades** (onde se acrescentam funções com execução automática) |
| `modules/csv.js` | motor CSV determinístico; fórmulas nunca executadas |
| `modules/approvals.js` | ActionIntent → Approval → execução **simulada** |
| `modules/chat.js` + `adapters/` | conversas persistentes; demo determinístico; Claude API real (G2) |
| `modules/connections.js` | inventário honesto de ligações, verificação com prova, revogação |
| `modules/artifacts.js` | artefactos com digest, Evidence |
| `modules/audit.js` | auditoria append-only com **cadeia de hashes** |
| `modules/retention.js` | expurgo, tombstones, ficheiro lateral fora dos backups |
| `modules/bi.js` | KPIs + export CSV das vistas em estrela |
| `backup.js` | backup AES-256-GCM e restauro isolado |

## 4. Modelo de dados (por mundo)

Entidades do REQUISITOS §6 → tabelas: `accounts`, `org_units`, `roles`, `agents`(+`agent_roles`), `permissions`, `conversations`, `messages`, `tasks`, `execution_attempts`, `artifacts`, `evidence`, `connections`, `action_intents`, `approvals`, `action_effects`, `audit_events`, `tombstones`. Todas têm `id` opaco, `world_id`, `created_at/updated_at`, `schema_version` e `record_version` (concorrência otimista: `PATCH` exige `expected_version`).

**Invariantes garantidas pela própria BD** (não só pelo código):

| Invariante | Mecanismo |
|---|---|
| No máximo 1 orquestrador ativo por mundo | `UNIQUE INDEX … WHERE orchestrator_flag=1 AND lifecycle_status='active'` |
| No máximo 1 tentativa ativa por tarefa | `UNIQUE INDEX one_running_attempt … WHERE state='running'` |
| No máximo 1 efeito por intenção (CA11) | `action_effects.intent_id UNIQUE` |
| Idempotência de tarefas e intenções | `UNIQUE (account_id, idempotency_key)` / `(account_id, operation, idempotency_key)` |
| Auditoria append-only | triggers `BEFORE UPDATE/DELETE` (só o expurgo de retenção, com flag explícita, apaga) |
| Estados válidos | `CHECK (state IN (…))` em todas as máquinas de estado |

## 5. Máquinas de estado (validadas no servidor)

```
Tarefa:   draft → pending → assigned → running → completed
                              │   ▲        │  └─► awaiting_approval ⇄ running
                              │   │        ├─► failed ─► assigned (retry: nova tentativa; a falha fica)
                              ▼   │        └─► blocked ─► pending (nota obrigatória)
                           blocked/cancelled (terminais: completed, cancelled)
Aprovação: pending → approved → consumed          pending → denied | expired | revoked
Ligação:   planned → (verificação com prova) → connected → degraded (prova velha) → revoked/disconnected
Agente:    atividade DERIVADA: ocupado = existe tentativa 'running'; bloqueado = tem falhadas/bloqueadas; nunca guardada, nunca simulada
```

`running`, `completed` e `failed` **não** são aceites pela API pública: só nascem de uma tentativa real (worker) ou de «concluir manualmente com nota» (que cria Evidence). Concluir exige Evidence.

## 6. Segurança

- **Sessão** de utilizador único (H01): passcode (scrypt) → cookie `HttpOnly; SameSite=Strict` + token **CSRF** + verificação de `Origin`; rate-limit de login; TTL 12 h. Servidor liga a `127.0.0.1` por defeito.
- **CSP** restritiva (`default-src 'self'`), `nosniff`, `X-Frame-Options: DENY`; o DOM é construído com `h()` (texto nunca vira HTML). O único `innerHTML` é o SVG gerado localmente (mapa e retratos), onde todo o texto passa por `esc()` e cores/ficheiros/ids são validados por regex ou vêm de ids opacos do servidor.
- **Deny by default:** delegar exige `Permission` explícita (escopo `*`/`unit:`/`agent:` + profundidade). Cargo ≠ acesso. Negações ficam auditadas mesmo com *rollback* (`denial()` + `runWithDenials`).
- **Isolamento:** BD por mundo (CA17); objetos de dados/execução escopados por **conta** dentro do mundo (CA18); `world_id` vindo do cliente é ignorado.
- **Segredos:** só referências opacas (`env:NOME`) resolvidas no servidor; redação defensiva em erros/logs (CA21). Nunca viajam para UI, domínio, prompts, evidência ou exportações.
- **Conteúdo é dado:** CSV, mensagens e fontes nunca concedem ferramentas nem permissões; fórmulas tratadas como texto; exportação CSV neutraliza `= + - @`.
- **D1:** o classificador *auxilia* (emails reais, IBAN, NIF/telefone rotulados, cartões com Luhn, credenciais, canários); **não prova** anonimização. Ao detetar: pára o ramo, **não guarda, não resume, não reformula**; a auditoria guarda só a categoria.

## 7. Durabilidade e recuperação

SQLite em WAL com FKs; escritor único via `BEGIN IMMEDIATE`. **Worker durável:** lease + heartbeat; tentativa perdida → `abandoned` e a tarefa volta à fila (as capacidades automáticas são determinísticas e sem efeitos externos) ou **bloqueia para reconciliação** ao exceder `max_attempts` — nunca retry cego. **Backup** cifrado (AES-256-GCM, scrypt) das BDs dos mundos (sem sessões/passcode); **restauro** só em pasta vazia: verifica digests e cadeia de auditoria, **suspende os jobs** e reaplica tombstones/revogações posteriores ao backup (ficheiro lateral `data/tombstones/*.jsonl`, fora do backup). **Migrações:** uma transação por migração; falha ⇒ nada parcial; cópia do ficheiro antes de migrar.

## 8. Camada BI

Vistas em estrela `dim_*`/`fact_*` (migração 002), só metadados. Export em `Configuração`/`Trabalho → Painel BI` (UTF-8 com BOM) para Power BI/Fabric («Obter dados → Texto/CSV»). Chaves: `agent_id`, `unit_id`, `role_id`, `task_id`, `attempt_id`, `approval_id`. Nunca exporta mensagens, notas ou ficheiros.

## 9. Limitações e riscos conhecidos (honestos)

1. **Retratos provisórios.** O estilo «realista» pedido exige assets humanos licenciados/gerados que esta entrega não inclui. Os retratos são procedurais (rosto, cabelo, olhos, roupa, luz de contorno) e **marcados como provisórios**; cada agente aceita uma fotografia/ilustração real (PNG/JPEG/WEBP ≤ 2 MB) que substitui o provisório. A cena da vila é arte vetorial própria, não 3D/fotorrealista (REQUISITOS §8: «não exigir fotorrealismo antes de provar backend»).
2. **Sem ligações reais a contas.** Nenhum conector externo está implementado; o inventário diz «planeada · não verificada». Só existe adaptador para a API Claude (G2), **testado com `fetch` simulado** — a chamada real não foi verificada por falta de chave neste ambiente.
3. **Conversa demo ≠ AI.** Responde por regras fixas com dados reais da BD; sugere encaminhamentos e cria tarefas. Em modo real, depende de G2.
4. `node:sqlite` é *experimental* no Node 22 (a API pode mudar); mitigação: acesso concentrado em `lib/db.js` e testes de contrato.
5. Utilizador único (H01) e um deployment; multiutilizador exige revisão de segurança. Sem TLS embutido: pôr atrás de um proxy HTTPS se sair de `127.0.0.1`.
6. Auditoria de acessibilidade WCAG 2.2 AA **por fazer** (foco, rótulos, `prefers-reduced-motion` e 390 px estão tratados/verificados; falta auditoria automática+leitor de ecrã).
7. O worker faz *polling* a 700 ms (simples e robusto); não há fila externa.

## 10. Como estender (sem tocar no núcleo)

| Quero… | Faço… |
|---|---|
| Nova **função/cargo** | Configuração → Organização → «＋ Função» |
| Novo **agente** | «＋ Agente» (retrato editável, capacidades, superior, unidade) |
| Nova **unidade** (edifício na vila) | «＋ Unidade» (escolhe o edifício; aparece no mapa) |
| Capacidade **manual** | já funciona: tarefa + nota + prova manual |
| Capacidade com **execução automática** | uma entrada em `capabilities.js` com `executor` determinístico + teste; o worker passa a executá-la |
| Novo **fornecedor/ligação** | entrada em `PROVIDERS` (`connections.js`) + adaptador com `verify()` — ver `CONNECTORS.md` |
| Novo **mundo** | entrada em `WORLD_DEFS` (`app.js`) com política e seed |
