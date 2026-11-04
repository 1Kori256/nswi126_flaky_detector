# Flaky Test Detector

Repeat pytest runs and find tests with both passing and failing outcomes. Persistent
failures, setup/teardown errors, skipped tests, and missing observations are reported
separately. Static code hints can help investigate a failure; they do not establish
its cause.

## Run

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/1Kori256/nswi126_flaky_detector.git
cd nswi126_flaky_detector
uv sync
uv run flaky-detector detect example_project/tests/test_demo.py --runs 4
```

The controlled demo produces one flaky test (pass/fail/pass/fail), one persistent
failure, and one passing test. It uses `FLAKY_DETECTOR_RUN`, which the detector sets
for each child process. **Exit code 1 is expected for this demo.**

Alternatively, install into an existing virtual environment with
`python -m pip install -e .`. The CLI also works as `python -m flaky_test_detector`.

## Your tests

Install this tool in the environment containing your project's test dependencies.
Run it from your project's directory so its pytest configuration applies.

```sh
flaky-detector detect tests/ --runs 10 --timeout 300
flaky-detector detect 'tests/test_api.py::TestAPI::test_create' --runs 5
flaky-detector detect tests/ --runs 10 --json --output report.json
```

`--timeout` limits each pytest process, in seconds. `--json` writes a machine-readable
report to stdout; `--output` saves the same report. `--verbose` adds progress on stderr
and failure/repair examples. Use `--no-analyze` or `--no-suggest` to omit code hints
or suggestions.

| Exit | Meaning |
| --- | --- |
| 0 | Complete run with no observed failures or errors |
| 1 | Mixed outcomes or persistent failures/errors observed |
| 2 | Invalid input, execution/report error, or changing test collection |

Each repetition uses a fresh Python process. Expected failures count as skipped;
unexpected passes count as passed. The JSON `balance_score` is
`2 × min(passes, failures + errors) / (passes + failures + errors)`. It describes
the observed split, not the probability that a test is flaky.

## CI history

```sh
# Set GITHUB_TOKEN or GITLAB_TOKEN in your environment.
flaky-detector ci-github owner/repo --days 30 --branch main
flaky-detector ci-gitlab group/project --days 30 --ref main
```

These commands inspect verbose pytest logs from up to 20 recent completed runs.
Candidates must share a full test ID and commit SHA. Duplicate log entries are
collapsed; conflicting outcomes within one CI run are omitted because they may
come from different matrix jobs. Candidates still need investigation: job and
environment changes can explain differing outcomes at the same commit.

The manual GitHub workflow and optional GitLab template save reports. They do not
create issues or request reviews.

## Limits and development

Repetition cannot prove stability. The local detector preserves test order and does
not simulate changing time, randomize test order, or follow fixtures and helper
functions during static analysis. Hints inspect the selected test body and can miss
indirect dependencies. Tests must emit a complete pytest-json-report; options such
as `--maxfail` can leave missing observations.

```sh
uv run pytest
```

The deterministic test suite is separate from `example_project/tests`, which contains
intentional failures and older stochastic examples. Developed for the NSWI126 Tools
course.
