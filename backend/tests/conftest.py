"""Configuração comum: cada sessão de testes usa uma pasta de trabalho temporária e sem API Claude."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _workspace(tmp_path_factory):
    home = tmp_path_factory.mktemp("mlstudio_home")
    os.environ["MLSTUDIO_HOME"] = str(home)
    os.environ["MLSTUDIO_MAX_ROWS"] = "20000"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    from mlstudio.config import get_settings
    from mlstudio.connectors import get_hub
    from mlstudio.core.orchestrator import get_orchestrator

    get_settings.cache_clear()
    get_hub.cache_clear()
    get_orchestrator.cache_clear()
    yield home


@pytest.fixture(scope="session")
def orch(_workspace):
    from mlstudio.core.orchestrator import get_orchestrator

    return get_orchestrator()
