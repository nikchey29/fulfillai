from pathlib import Path

from src.fulfillai.ml import data
from src.fulfillai.ml.modeling import common_binary

ROOT = Path(__file__).resolve().parents[1]


def test_pretest_loader_exists_and_has_no_test_split_construction():
    source = Path(data.__file__).read_text(encoding="utf-8")
    start = source.index("def load_train_validation_dataset(")
    end = source.index("# ======================================================================\n# Full task loader", start)
    body = source[start:end]
    assert '"train"' in body
    assert '"validation"' in body
    assert '"test"' not in body


def test_demand_experiment_scripts_use_pretest_loader():
    for rel in [
        "src/fulfillai/ml/demand/baselines.py",
        "src/fulfillai/ml/demand/train_poisson.py",
        "src/fulfillai/ml/demand/train_hist_gradient_boosting.py",
        "src/fulfillai/ml/demand/tune_hist_gradient_boosting.py",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "load_train_validation_dataset" in text
        assert "load_task_dataset" not in text


def test_binary_final_refit_requires_clean_git():
    source = Path(common_binary.__file__).read_text(encoding="utf-8")
    start = source.index("def final_refit_task(")
    end = source.index("def evaluate_frozen_test_task(", start)
    body = source[start:end]
    assert "require_clean_git()" in body
    assert '"source_git_commit": source_commit' in body
