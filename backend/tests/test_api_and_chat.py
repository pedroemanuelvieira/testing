"""API REST e assistente (modo offline e ciclo de tool use com um cliente Claude simulado)."""
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(orch):
    from mlstudio.api.main import app

    return TestClient(app)


def wait(client, job_id, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.5)
    raise TimeoutError(job_id)


def test_meta_and_knowledge_endpoints(client):
    m = client.get("/api/meta").json()
    assert m["assistant"]["mode"] == "offline"
    assert client.get("/api/knowledge/use-cases?area=risco").json()
    assert client.get("/api/knowledge/glossary/auc").json()["id"] == "auc_roc"
    assert client.get("/api/knowledge/glossary?q=psi").json()[0]["id"] == "psi"
    assert len(client.get("/api/knowledge/workflow").json()) == 13
    assert client.get("/api/knowledge/use-cases/inexistente").status_code == 404


def test_project_lifecycle_via_api(client):
    v = client.post("/api/projects", json={"use_case_id": "atraso_entregas"}).json()
    pid = v["project"]["id"]
    assert pid.isascii()
    job = client.post(f"/api/projects/{pid}/autopilot", json={"until": "training"}).json()["job"]
    assert wait(client, job["id"])["status"] == "done"
    view = client.get(f"/api/projects/{pid}").json()
    assert view["champion"] and view["progress"] > 0.5
    assert client.patch(f"/api/projects/{pid}", json={"nao_existe": 1}).status_code == 400
    # conselheiro com perfil real + comparação + aplicação
    rec = client.post("/api/advisor/recommend", json={"model_id": "random_forest", "project_id": pid}).json()
    assert rec["profile"]["n_rows"] > 1000
    cmp_job = client.post("/api/advisor/compare", json={"model_id": "random_forest", "project_id": pid,
                                                        "params": {"n_estimators": 50}}).json()["job"]
    res = wait(client, cmp_job["id"])["result"]
    assert {"recommended", "custom"} <= set(res)
    ok = client.post("/api/advisor/apply", json={"project_id": pid, "model_id": "random_forest",
                                                 "params": {**rec["params"], "n_estimators": 150}, "lock": True}).json()
    assert ok["locked"]
    p = client.get(f"/api/projects/{pid}").json()["project"]
    assert "random_forest" in p["params_locked"] and p["model_params"]["random_forest"]["n_estimators"] == 150
    bad = client.post("/api/advisor/apply", json={"project_id": pid, "model_id": "random_forest", "params": {"max_features": "x"}})
    assert bad.status_code == 400
    # scoring online
    vid = view["champion"]["id"]
    pred = client.post(f"/api/models/{vid}/predict", json={"rows": [{"transportadora": "ExpressoSul", "zona_destino": "Rural"}]}).json()
    assert "probabilidade" in pred["predictions"][0]


def test_connector_endpoints_and_upload(client):
    q = client.post("/api/connectors/demo/query", json={"workspace_id": "ws-financas", "dataset_id": "ds-risco",
                                                        "query": "EVALUATE TOPN(3, 'Credito')"}).json()
    assert q["row_count"] == 3
    r = client.post("/api/connectors/files/upload", files={"file": ("teste.csv", b"a;b\n1;2,5\n", "text/csv")}).json()
    assert r["rows"] == 1
    assert any(t["name"] == "teste" for t in client.get("/api/connectors/files/workspaces/uploads/datasets/ficheiros/tables").json())


def test_offline_chat_answers(client):
    r = client.post("/api/chat", json={"message": "o que é a AUC?"}).json()
    assert r["mode"] == "offline" and "AUC-ROC" in r["reply"]
    cid = r["conversation_id"]
    r2 = client.post("/api/chat", json={"message": "que parâmetros uso no LightGBM para fraude com 1% de positivos?",
                                        "conversation_id": cid}).json()
    assert "LightGBM" in r2["reply"] and "fraude" in r2["reply"].lower() and "num_leaves" in r2["reply"]
    assert len(client.get(f"/api/chat/{cid}").json()["messages"]) == 4


# ------------------------------------------------------------------ ciclo de tool use (cliente simulado)
class _Block(SimpleNamespace):
    pass


class _Resp:
    def __init__(self, blocks, stop):
        self.content = [_Block(**b) for b in blocks]
        self.stop_reason = stop
        self._blocks = blocks

    def to_dict(self):
        return {"content": self._blocks, "stop_reason": self.stop_reason}


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            return _Resp([{"type": "thinking", "thinking": "", "signature": "sig"},
                          {"type": "tool_use", "id": "tu_1", "name": "obter_termo_glossario", "input": {"termo": "psi"}}], "tool_use")
        return _Resp([{"type": "text", "text": "O **PSI** mede a mudança de distribuição."}], "end_turn")


def test_llm_tool_loop_with_fake_client(orch, monkeypatch):
    from mlstudio.chat import assistant as A

    asst = A.Assistant(orch)
    fake = FakeMessages()
    client = SimpleNamespace(messages=fake, beta=SimpleNamespace(messages=fake))
    monkeypatch.setattr(A, "llm_available", lambda s: (True, "teste"))
    monkeypatch.setattr(asst, "_get_client", lambda: client)
    out = asst.chat("O que é o PSI?", page="/glossario")
    assert out["mode"] == "llm" and "PSI" in out["reply"]
    assert out["tools"][0]["name"] == "obter_termo_glossario"
    assert out["sources"]["terms"][0]["id"] == "psi"
    first, second = fake.calls
    assert first["betas"] == ["server-side-fallback-2026-07-01"] and first["fallbacks"] == "default"
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    # histórico só-de-acréscimo: o 2.º pedido contém o 1.º intacto + o resultado da ferramenta
    msgs = second["messages"]
    assert msgs[1]["content"][0]["type"] == "thinking" and msgs[2]["content"][0]["type"] == "tool_result"
    conv = asst.store.get(out["conversation_id"])
    assert len(conv["api_messages"]) == 4
    # um 2.º turno reenvia o histórico anterior sem alterações
    fake.calls.clear()
    asst.chat("E o KS?", conversation_id=out["conversation_id"])
    assert fake.calls[0]["messages"][:4] == conv["api_messages"]


def test_llm_errors_fall_back_to_offline(orch, monkeypatch):
    from mlstudio.chat import assistant as A

    asst = A.Assistant(orch)

    class Boom:
        def create(self, **kw):
            raise RuntimeError("sem rede")

    monkeypatch.setattr(A, "llm_available", lambda s: (True, "teste"))
    monkeypatch.setattr(asst, "_get_client", lambda: SimpleNamespace(messages=Boom(), beta=SimpleNamespace(messages=Boom())))
    out = asst.chat("o que é o recall?")
    assert out["mode"] == "offline" and "offline" in out["reply"]
