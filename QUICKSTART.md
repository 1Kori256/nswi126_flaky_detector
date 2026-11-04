# Quick start

```sh
uv sync
uv run flaky-detector detect example_project/tests/test_demo.py --runs 4
```

Expected: **1 flaky, 1 failing, 1 passed**. The demo deliberately exits with code 1.

For a project that already has its test dependencies installed:

```sh
python -m pip install -e /path/to/nswi126_flaky_detector
flaky-detector detect tests/ --runs 10 --json --output report.json
```

See [README.md](README.md) for exit codes, limitations, and CI history commands.
