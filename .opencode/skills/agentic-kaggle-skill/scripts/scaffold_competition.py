#!/usr/bin/env python3
"""Create a compact Kaggle competition project layout."""

from __future__ import annotations

import argparse
from pathlib import Path


DIRS = [
    "input",
    "notebooks",
    "src",
    "models",
    "oof",
    "submissions",
    "logs",
    "configs",
    "kaggle_kernels",
    "kaggle_datasets",
    "remote_outputs",
]


FILES = {
    ".gitignore": """# Local secrets
.env
kaggle.json

# Kaggle competition inputs and generated artifacts
input/
models/
oof/
submissions/
logs/
remote_outputs/
kaggle_datasets/

# Python and notebook noise
__pycache__/
*.py[cod]
.ipynb_checkpoints/
""",
    "src/config.py": '''"""Shared competition paths and constants."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "input"
MODEL_DIR = ROOT / "models"
OOF_DIR = ROOT / "oof"
SUBMISSION_DIR = ROOT / "submissions"
LOG_DIR = ROOT / "logs"
CONFIG_DIR = ROOT / "configs"
KAGGLE_KERNEL_DIR = ROOT / "kaggle_kernels"
KAGGLE_DATASET_DIR = ROOT / "kaggle_datasets"
REMOTE_OUTPUT_DIR = ROOT / "remote_outputs"

SEED = 42
FOLD_COL = "fold"
TARGET_COL = "target"
ID_COL = "id"
''',
    "src/model_dispatcher.py": '''"""Register model constructors here."""

MODELS = {
    # "lgbm": lambda params: lightgbm.LGBMClassifier(**params),
}
''',
    "src/train.py": '''"""Training entry point placeholder.

Fill in data loading, fold selection, metric computation, model training,
OOF prediction saving, and test prediction saving for this competition.
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fold", type=int, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    raise NotImplementedError(f"Implement training for fold={args.fold}, model={args.model}")


if __name__ == "__main__":
    main()
''',
    "configs/baseline.yaml": """seed: 42
n_splits: 5
target_col: target
id_col: id
metric: competition_metric
""",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Competition root directory")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite template files if they already exist",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    for dirname in DIRS:
        (root / dirname).mkdir(parents=True, exist_ok=True)

    for rel_path, content in FILES.items():
        path = root / rel_path
        if path.exists() and not args.overwrite:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(f"Created Kaggle project scaffold at {root}")


if __name__ == "__main__":
    main()
