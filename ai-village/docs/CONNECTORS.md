# Ligações: contas pessoais, profissionais e modelos

## O que o Pedro pediu e o que a Source_of_truth permite

O pedido foi «puxar informação das minhas contas profissionais e pessoais». O documento de requisitos (REQUISITOS §2, §7, §9) é explícito e esta app **cumpre-o**:

| Mundo | Regra | Consequência na app |
|---|---|---|
| **Pessoal** | só dados **fictícios/sintéticos** (D1); sem sincronização automática de contas reais | Entrada de dados por **ficheiro sintético carregado** (CSV) ou colado. A guarda D1 recusa emails reais, IBAN, NIF/telefone rotulados, cartões, credenciais |
| **Profissional** | **só desenho** nesta conta; dados, segredos e contas reais ficam no ambiente profissional aprovado (G3) | Mundo `professional` não aceita ficheiros, execução nem ligações reais. Só o *blueprint higienizado* atravessa mundos (pela Ponte) |

**Estado das ligações (honesto):**

| Ligação | Estado na app | Porquê |
|---|---|---|
| Conversa demo | `demo` | Local, determinística — não é AI |
| **Claude API (Anthropic)** | **adaptador implementado** → «planeada» até verificares | G2: precisa de chave de API (a subscrição de chat **não** dá API) |
| Google Drive (Source_of_truth), Gmail, Calendário, NotebookLM | `planeada · não verificada` | Sem adaptador. O conector do ambiente de conceção **não é transportável** (REQUISITOS §9) |
| M365/SharePoint, Power BI/Fabric, Azure DevOps, Copilot Studio | `planeada` (só desenho) | G3, ambiente profissional |

«Ligada» só aparece depois de um **diagnóstico read-only bem-sucedido, com prova datada nesta app**. A prova envelhece (`freshness_seconds`, 24 h por defeito) → «degradada».

## Ligar a Claude API (G2) — passo a passo

1. No **servidor**: `export ANTHROPIC_API_KEY=…` e arranca com `npm start`. A chave **nunca** passa por UI, BD, logs ou prompts; a app só guarda a referência `env:ANTHROPIC_API_KEY`.
2. **Ligações → Claude API → «Verificar ligação»**: faz um pedido read-only (`GET /v1/models`) e regista a prova (HTTP, hora). Falha ⇒ fica «pendente/degradada» com o código do erro (sem segredo).
3. Concede o âmbito **«conversa (chat)»** (uso aprovado por ti).
4. Abre um agente → **Nova conversa → Real**. O modelo por defeito é `claude-sonnet-5-5`; muda-o em `connections.config.model` (PATCH `/connections/:id` com `config: { model }`).
5. Em modo real, falhas (timeout, 429, auth) aparecem como **erro visível**; **nunca** caem para demo em silêncio. Desligar/revogar a ligação trava a conversa real.

> Esta chamada foi testada com `fetch` simulado (contrato, timeout, 429, revogação). **Ainda não foi exercida contra a API real** — faz o passo 2 e diz o resultado antes de contares com ela (CA26).

## Implementar um novo adaptador (contrato)

Em `server/modules/connections.js`, acrescenta a `PROVIDERS`:

```js
'meu-fornecedor': {
  label: 'Meu Fornecedor', category: 'source' /* ou 'model' */, scopes: ['read'],
  secretEnv: 'MEU_FORNECEDOR_TOKEN',        // referência; o valor fica no servidor
  note: 'O que faz e o que NÃO faz.',
  async verify(conn, deps) {                 // diagnóstico READ-ONLY; lança HttpError se falhar
    // devolve uma prova mínima e SEM segredos: { http_status, detail, … }
  },
  resultingStatus: 'connected',
}
```

Requisitos do contrato (REQUISITOS §9): âmbitos mínimos; OAuth mínimo quando suportado, chaves só no servidor; diagnóstico, prova e frescura; paginação/limites/proveniência/erros; **desconexão/revogação** (a app já bloqueia jobs dependentes, apaga a referência do segredo e regista tombstone). Importação de dados passa **sempre** pela guarda D1 e conserva a origem e o modo.

**Adaptador do Google Drive (próximo passo natural):** OAuth com âmbito `drive.readonly`, restrito à pasta `Source_of_truth` e só a ficheiros sintéticos; cada ficheiro importado vira um `artifact` (digest, retenção) depois de passar a D1. Fica por implementar: exige consentimento OAuth e credenciais teus — não foi feito sem eles.

## Segredos e revogação

- Revogar = remove `secret_ref`, prova e âmbitos; bloqueia tarefas com `config.connection_id`; cancela tentativas; desassocia conversas reais; escreve tombstone (para um restauro não ressuscitar o acesso).
- A revogação **no fornecedor** (apagar a chave/consentimento lá) é manual: a app avisa-o e mantém o bloqueio local.
