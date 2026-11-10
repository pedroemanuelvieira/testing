---
name: auditoria
description: "Auditoria independente de uma entrega, de uma promocao de estado ou do proprio escritorio - veredito, evidencia por ponto, riscos e plano de prova. Usar antes de promover ou publicar algo relevante e na revisao mensal."
---

# Auditoria independente

Trabalha em contexto limpo: lê o pedido original, a entrega e as fontes, não as conclusões de quem fez.

## Auditar uma entrega
1. **O que foi pedido** e o que foi entregue: cobre tudo? Há algo entregue que ninguém pediu?
2. **Refaz uma verificação** pelos teus meios: volta a correr a ferramenta que produziu um número, ou confere um total na fonte. Regista o comando e o resultado.
3. **Procura o que falha:** períodos abertos tratados como fechados, percentagens somadas, causalidade afirmada sem evidência, dados sintéticos apresentados como reais, limites do método omitidos, dados sensíveis expostos.
4. **Separa** o que verificaste do que apenas leste.

## Auditar o escritório (mensal)
1. `python3 -m foundry estado --json` e `python3 -m foundry validar`.
2. **Uso:** funcionários e rotinas sem execuções no mês; rotinas que falham ou são sempre ignoradas por falta de entradas.
3. **Estados:** para cada funcionário em `escritorio/equipa.json`, o estado tem evidência datada? Há algo declarado como instalado ou em produção sem prova?
4. **Fronteira:** `python3 -m foundry fronteira`.
5. **Valor:** horas poupadas declaradas contra o custo e o tempo das execuções. Um funcionário sem uso ou sem valor é candidato a ser desligado.

## Entrega
`out/auditoria/<AAAA-MM-DD>/auditoria.md`:
- **Veredito:** aprovado, aprovado com reservas ou reprovado, numa linha.
- **Evidência:** tabela ponto, o que verifiquei, como, resultado.
- **Riscos**, por gravidade.
- **Plano de prova:** o que falta demonstrar, por quem e como.
- **Não verificado:** o que não conseguiste confirmar e porquê.

Não corriges o que auditas e não mudas estados: recomendas.
