---
name: instalar-rotinas
description: "Instala os agendamentos de escritorio/rotinas.json - motor local, crontab ou tarefas agendadas do Claude. Usar quando alguem quer por as rotinas a correr sozinhas ou pergunta como se automatiza o escritorio."
---

# Instalar as rotinas

As rotinas estão declaradas em `escritorio/rotinas.json`. Mostra-as primeiro: `python3 -m foundry agenda`. Depois pergunta qual das três formas a pessoa quer.

## A. Motor local (recomendado)
`python3 -m foundry servir` abre a interface em http://localhost:8765 e liga o escalonador: enquanto estiver a correr, as rotinas disparam à hora, uma de cada vez, usando o Claude Code CLI da máquina. Nada a instalar. Para arrancar com o computador: uma tarefa no arranque do sistema que execute esse comando na pasta do escritório (em Windows, no Agendador de Tarefas; em macOS ou Linux, um serviço de utilizador).

## B. Agendador do sistema, sem interface
`python3 -m foundry agenda --crontab` imprime uma linha por rotina, pronta para o `crontab -e`. Cada linha corre `python3 -m foundry correr <rotina>`. Mostra as linhas; quem as instala é a pessoa.

## C. Tarefas agendadas do Claude (sessões na nuvem ou na aplicação)
Só para rotinas que não dependem de ficheiros locais em `inbox/` (as que têm `requer` precisam de conectores de dados nesse ambiente).
1. Lista as tarefas agendadas que já existem, com a ferramenta de agendamento disponível nesta sessão, para não duplicar.
2. Mostra a tabela do que vais criar: nome, cadência (fuso Europe/Lisbon), funcionário e instrução. Espera pelo OK.
3. Cria uma tarefa por rotina. A instrução é: `No escritório Neo-Edo Data Foundry, atua como <funcionário> e: <prompt da rotina>`.
4. Confirma o que ficou criado, com a próxima execução de cada uma.
Se a sessão não tiver ferramenta de agendamento, diz isso e propõe A ou B.

Nunca cries agendamentos sem confirmação: cada um gasta utilização da conta de quem o cria. Para desligar uma rotina, `"ativa": false` em `escritorio/rotinas.json` ou o interruptor na interface (menu Escalonador).
