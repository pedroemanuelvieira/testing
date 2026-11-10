---
name: kpis-semanais
description: "Consolidacao semanal ou mensal de KPIs - periodo completo contra o anterior e o homologo, com os maiores contributos por dimensao. Usar a segunda-feira ou quando pedem o ponto de situacao dos indicadores."
---

# KPIs da semana

1. **Fontes e definições.** `cerebro/fontes.md` diz que ficheiros têm KPIs; `cerebro/glossario.md` define cada métrica (fórmula, unidade, base fiscal). Uma métrica sem definição é reportada com a nota "definição por confirmar".
2. **Calcula:**
   `python3 -m foundry kpis inbox/dados/<ficheiro> --data <col> --valor <métrica1,métrica2> --dim <dim1,dim2> --periodo semana --out out/kpis/<AAAA-MM-DD>/<fonte>`
   Compara o último período completo com o anterior e com o homólogo. Períodos abertos não entram. `--periodo mes` para a leitura mensal.
3. **Lê o resultado** (`kpis.md`): para cada métrica, a variação e os contributos por dimensão. Se a ferramenta avisar que o período está fora do habitual, pede ao Susanoo a verificação antes de explicar.
4. **Escreve** `out/kpis/<AAAA-MM-DD>/leitura.md`, uma página:
   - **Em três linhas:** o que subiu, o que desceu, o que exige atenção.
   - **Tabela** de métricas: atual, anterior, variação, homólogo, variação.
   - **Porquê:** os dois ou três contributos que explicam cada variação relevante, com valores.
   - **O que não sabemos:** dados em falta, definições por confirmar.
5. **Rácios e médias** (margem %, ticket médio): recalcula pelo numerador e denominador do período. Nunca somes percentagens nem faças média de médias.

Escreve "coincide com", não "foi causado por". Números com separador de milhares e vírgula decimal; percentagens com uma casa.
