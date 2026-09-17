"""AC28: Live model evaluation dataset, baseline comparisons, and gate validation.

Validates that:
1. Frozen 20-case holdout and 10 development cases are defined with full provenance:
   - 15 diagnostic cases (10 holdout, 5 dev).
   - 9 verification cases (6 holdout, 3 dev).
   - 6 robustness cases (4 holdout, 2 dev).
2. Ground-truth labels are stored separately in evals/labels/ground_truth.json
   and are not accessible to agent-readable scenario inputs.
3. Baselines exist:
   - Deterministic sales/stock baseline.
   - Image-only baseline.
4. Evaluation runner detects missing/invalid credentials and fails fast with [BLOCKED]
   per AGENTS.md (no fake pass or silent bypass).
"""

import json
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
EVALS_DIR = ROOT_DIR / "evals"


def test_ac28_eval_dataset_structure_and_splits():
    """AC28: 30 independent cases with 10 development and 20 frozen holdout cases."""
    splits_file = EVALS_DIR / "data" / "splits.json"
    assert splits_file.exists(), "evals/data/splits.json must exist"

    with open(splits_file, "r", encoding="utf-8") as f:
        splits = json.load(f)

    dev_cases = splits.get("dev", [])
    holdout_cases = splits.get("holdout", [])

    # Split sizes
    assert len(dev_cases) == 10, f"Expected 10 dev cases, got {len(dev_cases)}"
    assert len(holdout_cases) == 20, f"Expected 20 holdout cases, got {len(holdout_cases)}"

    # Strict isolation: No case in both dev and holdout
    overlap = set(dev_cases).intersection(set(holdout_cases))
    assert len(overlap) == 0, f"Overlap between dev and holdout: {overlap}"

    # Total 30 unique cases
    all_cases = set(dev_cases).union(set(holdout_cases))
    assert len(all_cases) == 30

    # Categorical breakdown of holdout cases (10 diagnostic, 6 verification, 4 robustness)
    diagnostic = [c for c in holdout_cases if c.startswith("D")]
    verification = [c for c in holdout_cases if c.startswith("V")]
    robustness = [c for c in holdout_cases if c.startswith("R")]

    assert len(diagnostic) == 10, f"Expected 10 holdout diagnostic cases, got {len(diagnostic)}"
    assert len(verification) == 6, f"Expected 6 holdout verification cases, got {len(verification)}"
    assert len(robustness) == 4, f"Expected 4 holdout robustness cases, got {len(robustness)}"


def test_ac28_labels_protected_from_inputs():
    """AC28: Scenario inputs in evals/data/scenarios/ must NOT contain target labels."""
    scenarios_dir = EVALS_DIR / "data" / "scenarios"
    assert scenarios_dir.exists(), "evals/data/scenarios/ directory must exist"

    labels_file = EVALS_DIR / "labels" / "ground_truth.json"
    assert labels_file.exists(), "evals/labels/ground_truth.json must exist"

    with open(labels_file, "r", encoding="utf-8") as f:
        labels = json.load(f)

    assert len(labels) == 30, f"Ground truth must cover all 30 scenarios, found {len(labels)}"

    # Check each scenario input file to ensure it is unlabeled
    for scenario_file in scenarios_dir.glob("*.json"):
        with open(scenario_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Unlabeled inputs must not contain ground truth labels or evaluation targets
        assert "expected_diagnosis" not in data, f"{scenario_file.name} leaks expected_diagnosis"
        assert "expected_verification" not in data, f"{scenario_file.name} leaks expected_verification"
        assert "ground_truth" not in data, f"{scenario_file.name} leaks ground_truth"
        assert "label" not in data, f"{scenario_file.name} leaks label"


def test_ac28_eval_runner_fails_on_missing_or_invalid_credentials():
    """AC28: evals/run_evals.py must return exit code 2 and [BLOCKED] when credentials are missing or invalid."""
    import subprocess
    import sys

    run_evals_py = EVALS_DIR / "run_evals.py"
    assert run_evals_py.exists(), "evals/run_evals.py must exist"

    # Run with explicitly bad credentials
    env = {"PATH": os.environ.get("PATH", ""), "GOOGLE_AI_API_KEY": "invalid-dummy-key-for-test"}
    proc = subprocess.run(
        [sys.executable, str(run_evals_py), "--mode", "live"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    # Must exit with code 2 (BLOCKED)
    assert proc.returncode == 2
    assert "[BLOCKED]" in proc.stdout or "[BLOCKED]" in proc.stderr
    assert "Missing credentials produce a blocked live gate" in (proc.stdout + proc.stderr)


def test_ac28_eval_runner_dry_run_and_baselines():
    """AC28: evals/run_evals.py supports deterministic baselines and dry-run validation."""
    import subprocess
    import sys

    run_evals_py = EVALS_DIR / "run_evals.py"

    # Run baseline heuristic
    proc = subprocess.run(
        [sys.executable, str(run_evals_py), "--mode", "baseline-heuristic"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "Deterministic Sales/Stock Baseline" in proc.stdout
    assert "Holdout Cases Evaluated: 20" in proc.stdout

    # Run dry-run validation
    proc_dry = subprocess.run(
        [sys.executable, str(run_evals_py), "--mode", "dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_dry.returncode == 0
    assert "Evaluation Harness Dry-Run Validation Passed" in proc_dry.stdout
