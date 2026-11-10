---
name: analise-adhoc
description: "Responde a uma pergunta de negocio com dados - enquadra, verifica a fonte, calcula e entrega uma leitura curta com numeros rastreaveis. Usar para perguntas pontuais como 'porque desceu', 'compara', 'quem sao os maiores'."
---

# Análise a pedido

1. **Enquadra.** Que decisão depende desta resposta? Que métrica (ver `cerebro/glossario.md`), que período, que população? Se algo essencial faltar, faz uma pergunta; senão declara o pressuposto.
2. **Fonte.** Usa a fonte ligada no ambiente, se existir, ou o ficheiro em `inbox/dados/`. Confirma primeiro que está em condições: `python3 -m foundry perfil <ficheiro> --data <col>` (frescura, nulos, duplicados).
3. **Calcula** com as ferramentas: `kpis` para comparações entre períodos e contributos, `drift anomalias` para "isto é normal?", os módulos `ml` (via Tetsuo) para previsão ou segmentação. Se o ambiente tiver as skills de análise de dados instaladas, podes usá-las para SQL, estatística e gráficos.
4. **Confere** um total contra a fonte antes de escrever. Rácios recalculados pelo numerador e denominador.
5. **Entrega** em `out/analises/<AAAA-MM-DD>/<tema>.md`:
   - a resposta em duas linhas, com o número;
   - a evidência (tabela pequena, de onde vem cada número);
   - o que limita a conclusão;
   - próximo passo sugerido.

Se os dados não permitirem responder, diz o que falta em vez de aproximar.
