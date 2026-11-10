#!/usr/bin/env bash
# Preparação única do escritório (macOS, Linux, Git Bash). Em Windows sem bash: python -m foundry preparar
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python) || { echo "Instala primeiro o Python 3.10 ou superior."; exit 1; }
command -v claude >/dev/null || echo "Aviso: Claude Code CLI não encontrado (https://claude.com/claude-code). A interface abre, mas os funcionários não correm."
"$PY" -m foundry preparar
