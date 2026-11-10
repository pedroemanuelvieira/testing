---
name: ata-reuniao
description: "Transforma notas soltas de uma reuniao numa ata com decisoes, acoes com dono e prazo, e perguntas em aberto. Usar quando ha notas em inbox/reunioes ou alguem cola notas e pede a ata."
---

# Ata de reunião

1. **Lê as notas** em `inbox/reunioes/` (ou coladas na conversa).
2. **Escreve** `out/atas/<AAAA-MM-DD>/ata.md`:
   - **Reunião:** tema, data, presentes (como vierem nas notas).
   - **Decisões:** o que ficou decidido, uma linha cada.
   - **Ações:** tabela ação, dono, prazo. Se as notas não disserem o dono ou o prazo, escreve "sem dono" ou "sem prazo": não atribuas.
   - **Em aberto:** perguntas e temas adiados.
   - **Próxima reunião**, se referida.
3. **Regras duradouras.** Uma decisão do tipo "a partir de agora…" é candidata a `cerebro/regras.md` ou `cerebro/decisoes.md`: lista-a numa secção "Para o cérebro partilhado" e pergunta se é para gravar.
4. **Ações para o escritório.** Uma ação que é trabalho de um funcionário (rever um modelo, preparar um extrato) pode virar tarefa:
   `python3 -m foundry tarefa criar --titulo "…" --agente <id> --fase <fase> --origem ata`
5. **Arquiva** as notas tratadas: `python3 -m foundry arquivar inbox/reunioes/<ficheiro>`.

Fiel às notas: não acrescentes decisões, não suavizes desacordos, não inventes presenças. O que for ambíguo vai para "Em aberto".
