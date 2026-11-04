"""Command-line reporting for repeated pytest runs and CI history."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from .detector import DetectionError, FlakyDetector
from .analyzer import RootCauseAnalyzer
from .suggester import RepairSuggester

app = typer.Typer(name='flaky-detector', help='Repeat pytest runs and inspect inconsistent outcomes.')
console = Console()


@app.command()
def detect(
    test_path: str = typer.Argument(..., help='Test file, directory, or pytest node ID'),
    runs: int = typer.Option(10, '--runs', '-n', min=2, help='Number of repeated pytest runs'),
    timeout: float = typer.Option(300, '--timeout', min=0.001, help='Timeout per pytest run, in seconds'),
    verbose: bool = typer.Option(False, '--verbose', '-v', help='Progress and repair examples'),
    analyze: bool = typer.Option(True, '--analyze/--no-analyze', help='Show static code hints'),
    suggest: bool = typer.Option(True, '--suggest/--no-suggest', help='Suggest investigation or repair steps'),
    json_output: bool = typer.Option(False, '--json', help='Write JSON to stdout'),
    output: Optional[Path] = typer.Option(None, '--output', '-o', help='Save the JSON report'),
):
    """Repeat tests; exit 1 for observed failures, or 2 for incomplete detection."""
    try:
        detector = FlakyDetector(test_path, runs=runs, verbose=verbose, timeout=timeout)
        detector.run_detection()
    except (DetectionError, ValueError) as error:
        if json_output:
            typer.echo(json.dumps({'schema_version': 1, 'status': 'error', 'message': str(error)}))
        else:
            typer.echo(f'Detection failed: {error}', err=True)
        raise typer.Exit(2)
    report = detector.to_report()
    if analyze:
        for entry in report['tests']:
            if entry['status'] != 'flaky':
                continue
            test = detector.results[entry['nodeid']]
            hints = RootCauseAnalyzer(Path(test.test_file)).analyze(test.test_function)
            entry['hints'] = [{'type': hint.type.value, 'description': hint.description,
                               'lines': hint.line_numbers} for hint in hints]
            if suggest:
                entry['suggestions'] = [{'title': fix.title, 'description': fix.description,
                                         'example': fix.code_example}
                                        for fix in RepairSuggester().suggest_repairs(hints)]
    encoded = json.dumps(report, indent=2, ensure_ascii=False)
    if output is not None:
        try:
            output.write_text(encoded + '\n', encoding='utf-8')
        except OSError as error:
            typer.echo(f'Could not write report: {error}', err=True)
            raise typer.Exit(2)
    if json_output:
        typer.echo(encoded)
    else:
        counts = report['summary']
        console.print(f"{counts['total']} tests, {detector.completed_runs} runs: "
                      f"{counts['flaky']} flaky, {counts['failing']} failing, "
                      f"{counts['passed']} passed, {counts['skipped']} skipped, "
                      f"{counts['incomplete']} incomplete.", markup=False)
        problems = [entry for entry in report['tests'] if entry['status'] not in ('passed', 'skipped')]
        if problems:
            table = Table(box=box.SIMPLE, padding=(0, 1))
            for heading in ('Test', 'Status', 'Pass', 'Fail', 'Error', 'Skip', 'Missing'):
                table.add_column(heading, overflow='fold', no_wrap=heading != 'Test')
            for entry in problems:
                table.add_row(Text(entry['nodeid']), entry['status'],
                              *[str(entry[key]) for key in ('passed', 'failed', 'errors', 'skipped', 'missing')])
            console.print(table)
            if verbose:
                for entry in problems:
                    if entry['failure_messages']:
                        console.print(entry['failure_messages'][0], markup=False)
        if counts['missing_observations']:
            console.print(f"Collection changed: {counts['missing_observations']} missing observations.", markup=False)
        if counts['flaky'] == 0:
            console.print('No mixed pass/fail outcomes observed. Repetition cannot prove stability.', markup=False)
        for entry in report['tests']:
            hints = entry.get('hints', [])
            if not hints:
                continue
            console.print(f"\nCode hints for {entry['nodeid']} (not confirmed causes):", markup=False)
            for hint in hints:
                console.print(f"  {hint['type']}: {hint['description']} Lines {hint['lines']}", markup=False)
            for fix in entry.get('suggestions', []):
                console.print(f"  Suggestion: {fix['title']}", markup=False)
                if verbose:
                    console.print(fix['example'], markup=False)
    if any(test.missing_count for test in detector.results.values()):
        raise typer.Exit(2)
    if any(test.fail_count + test.error_count for test in detector.results.values()):
        raise typer.Exit(1)


def _show_history(analyzer, days, branch, min_runs):
    from .ci_analyzer import CIAnalysisError, get_flaky_tests
    try:
        results = analyzer.analyze(days, branch)
    except (CIAnalysisError, ValueError) as error:
        typer.echo(f'CI analysis failed: {error}', err=True)
        raise typer.Exit(2)
    if not results:
        console.print('No usable per-test observations found. Use verbose pytest logs (-v).', markup=False)
        raise typer.Exit(2)
    candidates = get_flaky_tests(results, min_runs)
    console.print(f'{len(results)} test/commit groups; {len(candidates)} CI candidates.', markup=False)
    console.print('History is limited to 20 recent runs. Job/environment changes may explain differences.', markup=False)
    if candidates:
        table = Table(box=box.SIMPLE)
        for heading in ('Test', 'Commit', 'Pass', 'Fail', 'Skip'):
            table.add_column(heading)
        for test in candidates:
            table.add_row(Text(test.test_name), test.commit_sha[:8], str(test.pass_count),
                          str(test.fail_count), str(test.skip_count))
        console.print(table)
        raise typer.Exit(1)
    console.print('No same-commit mixed outcomes observed; this is not proof of stability.', markup=False)


@app.command()
def ci_github(
    repo: str = typer.Argument(..., help='owner/repo'),
    token: str = typer.Option(..., '--token', '-t', envvar='GITHUB_TOKEN', help='Prefer GITHUB_TOKEN'),
    days: int = typer.Option(30, '--days', '-d', min=1),
    branch: str = typer.Option('main', '--branch', '-b'),
    min_runs: int = typer.Option(3, '--min-runs', min=2),
):
    """Inspect same-commit changes in GitHub Actions pytest logs."""
    from .ci_analyzer import GitHubActionsAnalyzer
    try:
        analyzer = GitHubActionsAnalyzer(repo, token)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2)
    _show_history(analyzer, days, branch, min_runs)


@app.command()
def ci_gitlab(
    project: str = typer.Argument(..., help='Project ID or namespace/project'),
    token: str = typer.Option(..., '--token', '-t', envvar='GITLAB_TOKEN', help='Prefer GITLAB_TOKEN'),
    days: int = typer.Option(30, '--days', '-d', min=1),
    ref: str = typer.Option('main', '--ref', '-r'),
    gitlab_url: str = typer.Option('https://gitlab.com', '--url'),
    min_runs: int = typer.Option(3, '--min-runs', min=2),
):
    """Inspect same-commit changes in GitLab CI pytest logs."""
    from .ci_analyzer import GitLabCIAnalyzer
    _show_history(GitLabCIAnalyzer(project, token, gitlab_url), days, ref, min_runs)


if __name__ == '__main__':
    app()
