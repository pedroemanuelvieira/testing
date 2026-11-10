# Fronteira de dados

## Dois ambientes, um sentido

| Ambiente | O que contém | Dados reais |
|---|---|---|
| **Modelo** (este repositório tal como é publicado) | Estrutura, agentes, skills, motor, dados fictícios em `exemplos/` | Proibidos |
| **Profissional** (cópia no repositório interno da organização, usada com as contas Claude da equipa) | O mesmo, mais o cérebro da equipa e o trabalho em `inbox/`, `out/`, `done/` | Permitidos, sempre dentro da organização |

O conteúdo só passa do modelo para o ambiente profissional. Nada do ambiente profissional volta para o repositório-modelo, para contas pessoais ou para serviços não aprovados. A única exceção é uma nota de retorno higienizada (sem dados reais), levada por uma pessoa.

Antes de usar o escritório com dados reais: copiar o repositório para o controlo de versões interno da organização e confirmar a política de IA da empresa.

## O que nunca é versionado

`inbox/`, `out/`, `done/` e a base de dados local (`dojo_storage.db`) estão no `.gitignore`. O que a equipa partilha por git é a estrutura (`.claude/`, `escritorio/`, `foundry/`) e o cérebro (`cerebro/`), que deve conter definições e regras, não dados operacionais.

## Kill-switch

Qualquer funcionário que encontre dados reais onde não deviam estar (num ficheiro versionado, num exemplo, num pedido para o ambiente-modelo):

1. Interrompe o processamento.
2. Diz numa linha que tipo de dado detetou, sem o repetir.
3. Pede a versão com marcadores (`<CLIENTE_EXEMPLO>`, `<EMAIL_COMERCIAL>`).
4. Não guarda, não resume e não reformula o conteúdo detetado.

## Controlo automático

- `python3 -m foundry fronteira` procura emails, NIF, IBAN, telefones, credenciais, chaves e cadeias de ligação no que é partilhado por git.
- `python3 -m foundry preparar` instala um gancho `pre-commit` que bloqueia commits com achados.
- A Kioku corre a verificação todas as sextas-feiras (rotina `higiene`).

O detetor é heurístico: pode falhar ou dar falsos positivos e não certifica anonimização. Antes de partilhar o repositório para fora, uma pessoa inspeciona o que vai sair.

## Permissões dos funcionários

Definidas em `.claude/settings.json`:

- **Sem pedir:** ler, correr as ferramentas `python3 -m foundry …`, escrever em `out/`.
- **Pede confirmação:** alterar `.claude/`, `escritorio/`, `cerebro/` ou `foundry/`; `git commit`; `git push`.
- **Bloqueado:** apagar ficheiros, `curl` e `wget`, ler `.env`, alterar o motor ML, lançar outras execuções do escritório.

Em execuções automáticas (rotinas), o que pede confirmação é recusado: uma rotina só consegue ler, correr ferramentas e escrever em `out/`.

## Ligações a dados

O escritório não traz nenhuma ligação configurada. Cada fonte (DWH, Power BI, Microsoft 365, ferramenta de trabalho) é ligada pela equipa através de conectores aprovados, só em leitura e com o menor privilégio. `.mcp.exemplo.json` mostra o formato. Credenciais nunca entram no repositório.
