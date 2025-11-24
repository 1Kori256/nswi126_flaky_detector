# Quick Start Guide

## Installation

```bash
# Clone or navigate to the project
cd challenge

# Install dependencies (using uv)
~/.local/bin/uv sync
```

## Run the Detector

### On Example Project

```bash
# Basic run (10 iterations)
~/.local/bin/uv run flaky-detector detect example_project/tests/test_flaky.py

# More thorough run (25 iterations)
~/.local/bin/uv run flaky-detector detect example_project/tests/test_flaky.py --runs 25

# With verbose output
~/.local/bin/uv run flaky-detector detect example_project/tests/test_flaky.py --runs 15 --verbose
```

### On Your Own Tests

```bash
# Single test file
~/.local/bin/uv run flaky-detector detect path/to/your/test_file.py --runs 20

# Entire test directory
~/.local/bin/uv run flaky-detector detect path/to/tests/ --runs 15

# Quick check (fewer runs)
~/.local/bin/uv run flaky-detector detect path/to/tests/ --runs 5
```

## Understanding the Output

### Detection Summary
Shows:
- Total tests analyzed
- Number of runs per test
- Count of stable vs flaky tests
- Overall flakiness rate

### Flaky Test Details
For each flaky test:
- **Flakiness Score**: 0-100%, higher = more flaky
- **Pattern**: How it fails (initially_failing, intermittent, etc.)
- **Results**: Pass/Fail/Skip counts
- **Sequence**: Visual representation (✓ = pass, ✗ = fail)

### Root Causes
Identified patterns:
- **time_dependent**: Uses datetime.now() or similar
- **random_dependent**: Uses random without seed
- **concurrency**: Threading/async issues
- **order_dependent**: Unordered collections
- **floating_point**: Exact float comparisons
- **global_state**: Global state modifications
- **external_dependency**: Network, file I/O

### Repair Suggestions
Actionable fixes with:
- Priority level (1 = highest)
- Code examples
- Multiple approaches

## Command Options

```bash
--runs, -n <number>           # Number of test runs (default: 10)
--verbose, -v                 # Show detailed output
--analyze / --no-analyze      # Enable/disable analysis (default: on)
--suggest / --no-suggest      # Enable/disable suggestions (default: on)
```

## Examples

```bash
# Recommended for production use
~/.local/bin/uv run flaky-detector detect tests/ --runs 20

# Quick development check
~/.local/bin/uv run flaky-detector detect tests/ --runs 5 --verbose

# Just detection, no analysis
~/.local/bin/uv run flaky-detector detect tests/ --no-analyze --no-suggest
```

## Expected Results on Example Project

The example project should detect **3 flaky tests**:

1. **test_timing_dependent** (~96% flakiness)
   - Randomly passes/fails due to timing precision

2. **test_random_user_id** (~88% flakiness)
   - 50/50 chance based on random number

3. **test_random_without_seed** (~72% flakiness)
   - ~40% pass rate with random choices

And **11 stable tests** that consistently pass.

## Troubleshooting

### "No such command 'detect'"
Make sure to include `detect` after `flaky-detector`:
```bash
~/.local/bin/uv run flaky-detector detect path/to/tests
```

### "Could not read report"
The tool creates temporary JSON files. Make sure `/tmp` is writable.

### No flaky tests detected
- Try more runs: `--runs 30`
- Your tests might actually be stable (good!)
- Check if tests are deterministic

### Too many false positives
- Increase runs for more confidence
- Some tests may have genuine environmental dependencies

## Next Steps

1. Run on your actual test suite
2. Review detected flaky tests
3. Apply suggested fixes
4. Re-run to verify fixes work
5. Consider integrating into CI/CD

## Need Help?

- Check `README.md` for full documentation
- See `SOLUTION.md` for technical details
- Look at `example_project/tests/test_flaky.py` for flaky test examples
