# Regras da casa

O que a equipa decidiu sobre como se trabalha aqui. Todos os funcionários leem este ficheiro antes de entregar.
Para acrescentar uma regra, diz ao Claude "a partir de agora…" ou edita o ficheiro e faz commit.

## Escrita e números
- Entregáveis em português europeu, frases curtas, sem jargão que o destinatário não use.
- Números com espaço nos milhares e vírgula decimal; percentagens com uma casa; moeda em EUR, sem imposto, salvo indicação.
- Cada número indica o período e a fonte. Períodos abertos nunca são comparados com períodos fechados.
- "Coincide com", não "foi causado por", quando não há evidência causal.

## Modelos Power BI
- Medidas com descrição (`///`), `formatString` e pasta de apresentação.
- Divisões com `DIVIDE`. Chaves ocultas e com `summarizeBy: none`.
- Relações de sentido único; uma bidirecional exige justificação escrita.
- Nada é publicado sem a revisão do Benkei e sem os casos de RLS executados por uma pessoa.

## ML
- Qualidade dos dados (910) antes de qualquer módulo. Baseline antes de modelo.
- Resultados sempre com intervalo e limites. Nenhuma decisão financeira é automática.

## Trabalho
- Pedidos entram por `inbox/pedidos/` e passam pela triagem. Prioridades são da equipa.
- Definição de feito: resultado em `out/`, verificado contra a fonte, limitações escritas, revisto por uma pessoa.

## Tempo manual por rotina (para estimar horas poupadas)
A equipa preenche esta tabela com o tempo que cada rotina demorava à mão. Sem valores, o resumo semanal não apresenta horas poupadas.

| Rotina | Minutos à mão | Fonte da estimativa |
|---|---:|---|
| morning-audit | | |
| monitor-refresh | | |
| triagem | | |
| kpis-semanais | | |
| revisao-modelos | | |
| documentacao-modelos | | |
