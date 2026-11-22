"""Conectores: demonstração, DAX local, adaptador do conector interno, API REST e ficheiros."""
import pandas as pd
import pytest

from mlstudio.connectors import ConnectorError, Filter, dax
from mlstudio.connectors.demo import DemoConnector
from mlstudio.connectors.files import FileConnector
from mlstudio.connectors.internal import InternalConnectorAdapter, to_dataframe
from mlstudio.connectors.rest import PowerBIRestConnector


def test_demo_connector_browse_and_query(tmp_path):
    c = DemoConnector(tmp_path)
    assert c.test_connection()["ok"]
    ws = {w.id for w in c.list_workspaces()}
    assert "ws-comercial" in ws
    tables = {t.name: t for t in c.list_tables("ws-comercial", "ds-crm")}
    assert tables["Clientes"].row_count > 5000
    df = c.read_table("ws-comercial", "ds-crm", "Clientes", columns=["cliente_id", "plano", "churn"], top=10,
                      filters=[Filter("plano", "=", "Premium"), Filter("antiguidade_meses", ">=", 12)])
    assert list(df.columns) == ["cliente_id", "plano", "churn"] and len(df) == 10
    assert (df["plano"] == "Premium").all()


def test_local_dax_engine_summarize_and_errors(tmp_path):
    c = DemoConnector(tmp_path)
    out = c.execute_dax("ws-comercial", "ds-crm",
                        "EVALUATE SUMMARIZECOLUMNS('Clientes'[plano], \"N\", COUNTROWS('Clientes'), \"Taxa\", AVERAGE('Clientes'[churn]))")
    assert set(out.columns) == {"plano", "N", "Taxa"} and out["N"].sum() > 5000
    with pytest.raises(ConnectorError):
        c.execute_dax("ws-comercial", "ds-crm", "EVALUATE FOO('Clientes')")


def test_dax_builder_quotes_and_literals():
    q = dax.build_table_query("Vendas Diárias", columns=["data"], top=5, filters=[Filter("loja", "in", ["A", "B's"])])
    assert "'Vendas Diárias'" in q and "TOPN(5" in q and '"B\'s"' in q
    assert dax.literal(pd.Timestamp("2024-03-01")) == "DATE(2024, 3, 1)"
    assert dax.clean_column_name("Clientes[churn]") == "churn"


def test_demo_write_creates_results_dataset(tmp_path):
    c = DemoConnector(tmp_path)
    res = c.write_table("ws-comercial", "Resultados ML", "Previsoes_X", pd.DataFrame({"id": [1, 2], "p": [0.1, 0.9]}))
    assert res["ok"]
    names = [d.name for d in c.list_datasets("ws-comercial")]
    assert "Resultados ML" in names
    back = c.read_table("ws-comercial", "ds-resultados-ml", "Previsoes_X")
    assert len(back) == 2


class OddConnector:
    """Conector 'interno' fictício com nomes e assinaturas diferentes das da plataforma."""

    def get_groups(self):
        return {"value": [{"id": "g1", "name": "Vendas"}]}

    def obter_datasets(self, grupo):
        return [{"id": "d1", "displayName": "Modelo Vendas", "grupo": grupo}]

    def run_query(self, group, ds, consulta):
        assert group == "g1" and ds == "d1" and consulta.startswith("EVALUATE")
        return {"results": [{"tables": [{"rows": [{"T[a]": 1, "T[b]": "x"}, {"T[a]": 2, "T[b]": "y"}]}]}]}

    def publicar_tabela(self, workspace, nome_dataset, tabela, dados, modo="replace"):
        return {"ok": True, "message": f"{len(dados)} linhas"}


def test_internal_adapter_resolves_methods_and_normalizes():
    a = InternalConnectorAdapter(OddConnector(), methods={"list_datasets": "obter_datasets"})
    assert a.resolved["list_workspaces"] == "get_groups"
    assert a.resolved["execute_dax"] == "run_query"
    assert a.resolved["write_table"] == "publicar_tabela"
    assert {"browse", "dax", "write"} <= set(a.capabilities)
    assert a.list_workspaces()[0].name == "Vendas"
    assert a.list_datasets("g1")[0].name == "Modelo Vendas"
    df = a.read_table("g1", "d1", "T", top=10)
    assert list(df.columns) == ["a", "b"] and len(df) == 2
    assert a.write_table("g1", "Resultados ML", "P", df)["ok"]


def test_internal_adapter_rejects_incomplete_connector():
    class Nothing:
        pass

    with pytest.raises(ConnectorError):
        InternalConnectorAdapter(Nothing())


def test_internal_adapter_loads_from_import_path(tmp_path, monkeypatch):
    (tmp_path / "empresa_pbi.py").write_text(
        "class Cliente:\n"
        "    def __init__(self, ambiente='dev'):\n        self.ambiente = ambiente\n"
        "    def list_workspaces(self):\n        return [{'id': 'w', 'name': self.ambiente}]\n"
        "    def list_datasets(self, workspace_id):\n        return [{'id': 'd', 'name': 'D'}]\n"
        "    def execute_dax(self, workspace_id, dataset_id, query):\n        return [{'x': 1}]\n")
    a = InternalConnectorAdapter("empresa_pbi:Cliente", path=str(tmp_path), kwargs={"ambiente": "prod"})
    assert a.list_workspaces()[0].name == "prod"
    assert to_dataframe([{"x": 1}]).shape == (1, 1)


class FakeResp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload
        self.content = b"{}"
        self.headers = {}
        self.text = str(payload)

    def json(self):
        return self._p


class FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, json=None):
        self.calls.append((method, url, json))
        if url.endswith("/groups"):
            return FakeResp(200, {"value": [{"id": "g", "name": "WS"}]})
        if url.endswith("/datasets") and method == "GET":
            return FakeResp(200, {"value": [{"id": "d", "name": "Modelo"}]})
        if url.endswith("/executeQueries"):
            return FakeResp(200, {"results": [{"tables": [{"rows": [{"Clientes[churn]": 1}, {"Clientes[churn]": 0}]}]}]})
        if "datasets?defaultRetentionPolicy" in url:
            return FakeResp(201, {"id": "newds"})
        if url.endswith("/rows"):
            return FakeResp(200, {})
        return FakeResp(404, {"error": {"message": "não encontrado"}})


def test_rest_connector_with_mocked_api():
    sess = FakeSession()
    c = PowerBIRestConnector("t", "c", "s", session=sess, token_provider=lambda: "token")
    assert c.test_connection()["ok"]
    df = c.execute_dax("g", "d", "EVALUATE 'Clientes'")
    assert list(df.columns) == ["churn"] and len(df) == 2
    big = pd.DataFrame({"a": range(25_000), "d": pd.Timestamp("2024-01-01")})
    res = c.write_table("g", "Resultados ML", "Prev", big)
    assert res["rows"] == 25_000
    posts = [x for x in sess.calls if x[1].endswith("/rows")]
    assert len(posts) == 3  # blocos de 10 000 linhas
    with pytest.raises(ConnectorError):
        c._request("GET", "/inexistente")


def test_file_connector_reads_portuguese_csv(tmp_path):
    c = FileConnector(tmp_path)
    csv = "id;valor;data\n1;1,5;2024-01-02\n2;2,25;2024-02-03\n".encode("utf-8")
    info = c.save_upload("vendas.csv", csv)
    assert info["rows"] == 2
    df = c.read_table("uploads", "ficheiros", "vendas")
    assert df["valor"].tolist() == [1.5, 2.25]
    assert pd.api.types.is_datetime64_any_dtype(df["data"])
