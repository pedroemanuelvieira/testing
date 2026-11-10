---
name: higiene
description: "Higiene do escritorio e da fronteira de dados - procura dados sensiveis no que e partilhado por git, valida a configuracao e lista o que esta por arquivar. Usar a sexta-feira, antes de um commit ou de partilhar o repositorio."
---

# Higiene e fronteira de dados

1. **Fronteira:** `python3 -m foundry fronteira --out out/higiene/<AAAA-MM-DD>`
   Verifica `cerebro/`, `escritorio/`, `.claude/`, `README.md` e `CLAUDE.md`: emails, NIF, IBAN, telefones, credenciais, chaves e cadeias de ligação. Código de saída 1 significa que há achados.
2. **Para cada achado:** ficheiro, linha e tipo. Nunca repitas o valor por inteiro. Propõe o marcador a usar (`<CLIENTE_EXEMPLO>`, `<EMAIL_COMERCIAL>`) e não alteres o ficheiro sem OK.
3. **Configuração:** `python3 -m foundry validar`. Funcionários sem ficheiro, skills em falta, cron inválido.
4. **Arrumação:**
   - `ls inbox/pedidos`, `ls inbox/reunioes`: entradas com mais de uma semana por tratar.
   - `ls out`: pastas antigas que podem ser arquivadas pela equipa (lista, não movas).
   - `git status --short`: ficheiros de `inbox/`, `out/`, `done/` ou a base de dados nunca devem aparecer como versionados.
5. **Escreve** `out/higiene/<AAAA-MM-DD>/higiene.md`: estado da fronteira, da configuração e da arrumação, com as ações propostas.

O detetor é heurístico: pode falhar ou dar falsos positivos e não certifica anonimização. Antes de partilhar o repositório fora do ambiente aprovado, uma pessoa inspeciona o que vai sair.
