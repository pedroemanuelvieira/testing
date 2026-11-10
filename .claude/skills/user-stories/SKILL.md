---
name: user-stories
description: "Transforma um pedido em epico, user story, bug ou tarefa com criterios de aceitacao verificaveis, estimativa relativa e dependencias. Usar para preparar o backlog ou o sprint a partir de pedidos triados."
---

# User stories

1. **Origem.** O pedido (texto, ficheiro de `out/triagem/` ou tarefas pendentes: `python3 -m foundry tarefa listar`).
2. **Classifica:** épico (vários entregáveis), user story (um resultado para alguém), bug (comportamento errado face ao esperado), tarefa técnica.
3. **Escreve** cada item:

   | Campo | Conteúdo |
   |---|---|
   | Tipo | Épico / User story / Bug / Tarefa |
   | Título | Curto e específico |
   | Descrição | Como <papel>, quero <objetivo>, para <valor> |
   | Critérios de aceitação | Lista dado / quando / então, cada um testável |
   | Dependências | Fontes, modelos, pessoas, outros itens |
   | Esforço | XS a XL, com o porquê |
   | Perguntas em aberto | O que não se sabe |

4. **Critérios com números.** "Abre em menos de 3 segundos", "mostra só os clientes do próprio comercial", "o total coincide com a fonte ao cêntimo". Nunca "funcionar bem" ou "ser rápido".
5. **Para BI, inclui sempre** um critério de dados (reconciliação com a fonte), um de acesso (quem vê o quê) e um de atualização (frequência e hora).
6. **Sprint:** agrupa por tema, soma o esforço, assinala dependências cruzadas e propõe o âmbito. Quem decide é a equipa.
7. **Guarda** em `out/stories/<AAAA-MM-DD>/`, um ficheiro por épico, pronto a colar na ferramenta de trabalho da equipa.

Não inventes requisitos: o que não souberes vai para "Perguntas em aberto".
