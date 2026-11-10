---
name: novo-funcionario
description: "Cria ou altera um funcionario ou uma skill do escritorio a partir de uma necessidade - blueprint em 8 seccoes, ficheiros, registo em equipa.json, casos de teste e estado inicial. Usar quando a equipa quer um agente novo, uma skill nova ou promover um existente."
---

# Novo funcionário ou skill

Skills primeiro: só se cria um funcionário novo quando há uma função com dono próprio. Um procedimento novo para um funcionário que já existe é uma skill.

1. **Blueprint em 8 secções** (`out/blueprints/BP_<nome>_v<X.Y>.md`): objetivo; dono e utilizadores; entradas; lógica; saída; critério de sucesso (com métrica); onde deve correr; versão e estado. Sem dados reais: marcadores como `<CLIENTE_EXEMPLO>`.
2. **Pontua** a ideia: valor × viabilidade ÷ risco, e compara com o que já existe em `escritorio/equipa.json`. Se uma skill existente resolve, diz isso.
3. **Mostra o blueprint e espera pelo OK** antes de criar ficheiros.
4. **Skill:** `.claude/skills/<nome>/SKILL.md` com `name` e `description` (o que faz e quando usar, até 1024 caracteres) e os passos numerados. Código determinístico entra como ferramenta em `foundry/tools/`, com teste em `testes/`.
5. **Funcionário:** `.claude/agents/<id>.md` (perfil, quando é usado, como trabalha, o que entrega, o que nunca faz, regras da casa) e a entrada em `escritorio/equipa.json` com `estado: "configurado"`, dono e `perfil_origem`.
6. **Rotina**, se for recorrente: entrada em `escritorio/rotinas.json` com `cron`, `requer` e `prompt`.
7. **Valida:** `python3 -m foundry validar`.
8. **Testa** com 3 a 5 casos fictícios, incluindo um que deve recusar ou escalar. Regista os resultados no blueprint.
9. **Promoção:** segue `escritorio/PROMOCAO.md`. O estado só sobe com evidência datada e aprovação de uma pessoa.

Alterações a `.claude/` e `escritorio/` pedem sempre confirmação. Lembra que é preciso commit e revisão por outra pessoa da equipa.
