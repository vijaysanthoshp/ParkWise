"""
verify_setup.py — Pre-flight check before running the pipeline.
Run this from the backend/ directory to confirm:
  1. Dataset is present and has the expected columns
  2. All required Python packages are installed
  3. Output directories exist

Usage:
    python verify_setup.py
"""

import sys
from pathlib import Path


def check(label, ok, detail=''):
    symbol = '✓' if ok else '✗'
    color  = '\033[92m' if ok else '\033[91m'
    reset  = '\033[0m'
    line   = f"  {color}{symbol}{reset}  {label}"
    if detail: line += f"  — {detail}"
    print(line)
    return ok


def main():
    all_ok = True
    print("\n── Dataset ─────────────────────────────────────────────")

    csv_path = Path("data/raw/incidents.csv")
    exists   = csv_path.exists()
    all_ok  &= check("incidents.csv present", exists,
                     str(csv_path) if not exists else '')

    if exists:
        import csv
        with open(csv_path, newline='', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            header = next(reader, [])

        required_cols = [
            'id', 'event_type', 'latitude', 'longitude',
            'start_datetime', 'event_cause',
        ]
        missing = [c for c in required_cols if c not in header]
        all_ok &= check(
            f"Required columns present ({len(header)} total cols)",
            len(missing) == 0,
            f"Missing: {missing}" if missing else '',
        )

        # Row count estimate
        with open(csv_path, 'rb') as f:
            n_lines = sum(1 for _ in f)
        check(f"Row count (estimate)", True, f"~{n_lines:,} lines")

    print("\n── Python packages ─────────────────────────────────────")

    packages = [
        ('pandas',      'pandas'),
        ('numpy',       'numpy'),
        ('pyarrow',     'pyarrow'),
        ('sklearn',     'scikit-learn'),
        ('lightgbm',    'lightgbm'),
        ('xgboost',     'xgboost'),
        ('shap',        'shap'),
        ('h3',          'h3'),
        ('geopandas',   'geopandas'),
        ('fastapi',     'fastapi'),
        ('uvicorn',     'uvicorn'),
        ('joblib',      'joblib'),
        ('anthropic',   'anthropic'),
    ]

    for import_name, pip_name in packages:
        try:
            mod = __import__(import_name)
            ver = getattr(mod, '__version__', '?')
            check(f"{pip_name}", True, f"v{ver}")
        except ImportError:
            check(f"{pip_name}", False, f"pip install {pip_name}")
            all_ok = False

    print("\n── Directories ─────────────────────────────────────────")
    dirs = [
        'data/raw', 'data/processed', 'data/outputs', 'models',
    ]
    for d in dirs:
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        check(d, True, 'created' if not p.exists() else 'ok')

    print("\n── Summary ─────────────────────────────────────────────")
    if all_ok:
        print("  \033[92mAll checks passed. Ready to run: python pipeline/run_all.py\033[0m\n")
    else:
        print("  \033[91mSome checks failed. Fix the issues above before running the pipeline.\033[0m\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
