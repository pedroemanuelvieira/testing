"""Integridade da base de conhecimento (glossário, casos de uso, modelos, guias)."""
from mlstudio.connectors import demo_data
from mlstudio.knowledge import KnowledgeBase, normalize


def test_knowledge_loads_and_has_no_integrity_errors():
    kb = KnowledgeBase()
    assert kb.validate() == []
    stats = kb.stats()
    assert stats["terms"] >= 200 and stats["use_cases"] >= 20 and stats["models"] >= 25
    assert stats["workflow_steps"] == 13


def test_every_area_has_use_cases_and_every_problem_type_is_covered():
    kb = KnowledgeBase()
    for area in kb.areas:
        assert kb.use_cases_by(area=area.id), area.id
    covered = {u.problem_type for u in kb.use_cases}
    assert covered == {p.id for p in kb.problem_types}


def test_demo_datasets_match_use_cases():
    kb = KnowledgeBase()
    for uc in kb.use_cases:
        demo = uc.demo
        assert demo, f"{uc.id} sem dados de demonstração"
        ds = demo_data.DEMO_CATALOG[demo["workspace"]]["datasets"][demo["dataset"]]
        assert demo["table"] in ds["tables"], uc.id
        cols = set(demo_data.get_table(demo["table"]).columns)
        for key in ("target", "time_column", "value_column", "transaction_column", "item_column", "label_column"):
            if demo.get(key) and not (key == "value_column" and demo.get("aggregation") == "count"):
                assert demo[key] in cols, f"{uc.id}: {key}={demo[key]} não existe"
        for c in demo.get("id_columns", []) + demo.get("exclude", []) + demo.get("features", []):
            assert c in cols, f"{uc.id}: coluna {c} não existe"


def test_terms_have_no_split_fragments_from_decimal_commas():
    """Listas YAML em linha partem '0,97' em dois itens — nenhum item deve começar por dígito."""
    kb = KnowledgeBase()
    for t in kb.terms:
        for item in t.pitfalls:
            assert not item[:1].isdigit(), f"{t.id}: '{item}'"


def test_search_and_term_lookup():
    kb = KnowledgeBase()
    assert kb.find_term("AUC").id == "auc_roc"
    assert kb.find_term("data leakage").id == "data_leakage"
    assert kb.find_term("precisão").id == "precisao"
    hits = kb.search("como escolho o limiar de decisão", k=5)
    assert any(h["id"] in ("limiar_decisao", "faq_4") for h in hits)
    assert normalize("Ação É") == "acao e"
