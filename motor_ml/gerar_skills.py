"""Gera as dez skills ML do escritório (.claude/skills/ml-*) a partir de SPECS em build_skills.py.

Uso: python motor_ml/gerar_skills.py
Uma única fonte de verdade: editar SPECS em build_skills.py, nunca os SKILL.md gerados.
Ao contrário de build_skills.py, não copia o pacote para cada skill: todas usam `python3 -m foundry ml`.
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from build_skills import SPECS  # noqa: E402

DESTINO = os.path.join(AQUI, "..", ".claude", "skills")
MAPA = {  # nome no pacote → (skill do escritório, número, id estável)
    "bi-ml-qualidade-dados": ("ml-qualidade", "910", "ml010-check"),
    "bi-ml-ciclo-vida-cliente": ("ml-ciclo-vida", "911", "ml010-lifecycle"),
    "bi-ml-churn": ("ml-churn", "912", "ml010-churn"),
    "bi-ml-previsao-procura": ("ml-procura", "913", "ml010-forecast"),
    "bi-ml-perda-ruptura": ("ml-ruturas", "914", "ml010-stockout"),
    "bi-ml-desvio-vendas": ("ml-desvios", "915", "ml010-variance"),
    "bi-ml-basket": ("ml-basket", "916", "ml010-basket"),
    "bi-ml-roi-incremental": ("ml-roi", "917", "ml010-roi-series"),
    "bi-ml-abc-xyz": ("ml-abc-xyz", "918", "ml010-abc-xyz"),
    "bi-ml-coortes": ("ml-coortes", "919", "ml010-cohorts"),
}

MODELO = """---
name: {skill}
description: "{desc}"
---
<!-- Gerado por motor_ml/gerar_skills.py a partir de build_skills.py (bi_ml 0.10.0). Nao editar a mao. -->
# {numero} · {skill} ({id})

Supervisor: Tetsuo (901). Motor: bi_ml 0.10.0 em `motor_ml/`, validado apenas com dados sinteticos.

## Entradas
{inputs}

Neste escritorio os extratos ficam em `inbox/dados/vendas/` (ou noutra pasta indicada no pedido).

## Como executar
{passo_check}`python3 -m foundry ml {cmd} --data PASTA --out out/ml/{pasta_saida}`
Em Windows usar `python`. Um comando por chamada. Codigo de saida 2 = erro de dados com mensagem: reportar a quem pediu, nao contornar. Codigo 3 = faltam dependencias (`python -m pip install -r motor_ml/requirements.txt`).

## Saidas
{outputs}

## Interpretacao
{interp}

## Acoes
{actions}

## Limites e abstencao
{limits}
Se os dados nao cumprirem o contrato ou o historico for curto, NAO responder com numeros: explicar o que falta. Todos os testes do pacote usam dados sinteticos; validar no historico real da equipa antes de decidir. Nada e publicado: os resultados ficam em `out/ml/` a espera de revisao humana.
"""


def gerar() -> list[str]:
    feitas = []
    for s in SPECS:
        skill, numero, ident = MAPA[s["name"]]
        desc = s["desc"].replace('"', "'")
        assert "<" not in desc and ">" not in desc and len(desc) <= 1024, skill
        cmd = s["cmd"]
        primeiro = "" if cmd == "check" else ("Primeiro `python3 -m foundry ml check --data PASTA --out out/ml/check` e ler "
                                              "`qualidade_dados.json` (skill ml-qualidade). Depois:\n")
        corpo = MODELO.format(skill=skill, numero=numero, id=ident, desc=desc, cmd=cmd, pasta_saida=cmd.split()[0],
                              passo_check=primeiro, inputs=s["inputs"], outputs=s["outputs"], interp=s["interp"],
                              actions=s["actions"], limits=s["limits"])
        pasta = os.path.join(DESTINO, skill)
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(corpo)
        feitas.append(skill)
    return feitas


if __name__ == "__main__":
    print(gerar())
