"""
CLI interface for flaky test detector
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

from .detector import FlakyDetector
from .analyzer import RootCauseAnalyzer
from .suggester import RepairSuggester


app = typer.Typer(
    name="flaky-detector",
    help="Automated detection and analysis of flaky tests in Python projects"
)
console = Console()


@app.command()
def detect(
    test_path: str = typer.Argument(..., help="Path to test file or directory"),
    runs: int = typer.Option(10, "--runs", "-n", help="Number of times to run each test"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    analyze: bool = typer.Option(True, "--analyze/--no-analyze", help="Analyze root causes"),
    suggest: bool = typer.Option(True, "--suggest/--no-suggest", help="Suggest repairs"),
):
    """
    Detect flaky tests by running them multiple times and analyzing inconsistent results.
    """
    console.print(Panel.fit(
        "[bold cyan]Flaky Test Detector[/bold cyan]\n"
        f"Running tests {runs} times to detect flakiness...",
        border_style="cyan"
    ))

    # Run detection
    detector = FlakyDetector(test_path, runs=runs, verbose=verbose)

    try:
        detector.run_detection()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    # Get results
    # Use the working directory pytest used (stored in detector)
    pytest_cwd = detector.pytest_cwd
    flaky_tests = detector.get_flaky_tests()
    stable_tests = detector.get_stable_tests()
    total_tests = len(flaky_tests) + len(stable_tests)

    # Summary statistics
    console.print()
    summary_table = Table(title="Detection Summary", box=box.ROUNDED)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="magenta")

    summary_table.add_row("Total Tests", str(total_tests))
    summary_table.add_row("Runs per Test", str(runs))
    summary_table.add_row("Stable Tests", f"[green]{len(stable_tests)}[/green]")
    summary_table.add_row("Flaky Tests", f"[red]{len(flaky_tests)}[/red]")

    if total_tests > 0:
        flaky_percentage = (len(flaky_tests) / total_tests) * 100
        summary_table.add_row("Flakiness Rate", f"{flaky_percentage:.1f}%")

    console.print(summary_table)

    # Show flaky tests
    if not flaky_tests:
        console.print("\n[bold green]✓ No flaky tests detected! All tests are stable.[/bold green]")
        return

    console.print(f"\n[bold red]⚠ {len(flaky_tests)} Flaky Test(s) Detected[/bold red]")

    for i, test in enumerate(flaky_tests, 1):
        # Test details
        console.print(f"\n[bold yellow]{i}. {test.test_function}[/bold yellow]")
        console.print(f"   [dim]File:[/dim] {test.test_file}")

        # Results table
        results_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        results_table.add_row("Flakiness Score:", f"[red]{test.flakiness_score:.1%}[/red]")
        results_table.add_row("Pattern:", f"[yellow]{test.failure_pattern}[/yellow]")
        results_table.add_row(
            "Results:",
            f"✓ {test.pass_count} / ✗ {test.fail_count} / ⊘ {test.skip_count}"
        )

        # Show outcome pattern
        outcome_symbols = []
        for outcome in test.outcomes[:20]:
            if outcome == 'passed':
                outcome_symbols.append('[green]✓[/green]')
            elif outcome == 'failed':
                outcome_symbols.append('[red]✗[/red]')
            else:
                outcome_symbols.append('[yellow]⊘[/yellow]')

        if len(test.outcomes) > 20:
            outcome_symbols.append('...')

        results_table.add_row("Sequence:", ' '.join(outcome_symbols))
        console.print(results_table)

        # Analyze root causes
        if analyze:
            # Resolve test file path relative to pytest's cwd
            test_file_path = pytest_cwd / test.test_file

            if test_file_path.exists():
                analyzer = RootCauseAnalyzer(test_file_path)
                causes = analyzer.analyze(test.test_function)

                if causes:
                    console.print("   [bold cyan]Root Causes:[/bold cyan]")
                    for cause in causes:
                        confidence_color = "green" if cause.confidence > 0.8 else "yellow" if cause.confidence > 0.5 else "red"
                        console.print(f"   • [{confidence_color}]{cause.type.value}[/{confidence_color}] "
                                      f"(confidence: {cause.confidence:.0%})")
                        console.print(f"     {cause.description}")

                        if cause.line_numbers:
                            console.print(f"     [dim]Lines: {', '.join(map(str, cause.line_numbers))}[/dim]")

                        # Show suggestions
                        if suggest:
                            suggester = RepairSuggester()
                            suggestions = suggester.suggest_repairs([cause])

                            if suggestions:
                                console.print("     [bold green]Suggested Fixes:[/bold green]")
                                for j, suggestion in enumerate(suggestions[:2], 1):  # Show top 2
                                    console.print(f"     {j}. {suggestion.title}")
                                    if verbose:
                                        console.print(f"        {suggestion.description}")

    # Detailed suggestions section
    if suggest and flaky_tests:
        console.print("\n" + "=" * 60)
        console.print("[bold cyan]Detailed Repair Suggestions[/bold cyan]\n")

        for i, test in enumerate(flaky_tests, 1):
            # Resolve test file path relative to pytest's cwd
            test_file_path = pytest_cwd / test.test_file
            if not test_file_path.exists():
                continue

            analyzer = RootCauseAnalyzer(test_file_path)
            causes = analyzer.analyze(test.test_function)

            if not causes:
                continue

            console.print(f"[bold yellow]{test.test_function}[/bold yellow]")

            suggester = RepairSuggester()
            all_suggestions = suggester.suggest_repairs(causes)

            for j, suggestion in enumerate(all_suggestions, 1):
                priority_color = "red" if suggestion.priority == 1 else "yellow" if suggestion.priority == 2 else "blue"
                console.print(f"\n[{priority_color}]Fix #{j} (Priority {suggestion.priority}):[/{priority_color}] "
                              f"[bold]{suggestion.title}[/bold]")
                console.print(f"{suggestion.description}\n")
                console.print(Panel(
                    suggestion.code_example,
                    border_style="dim",
                    padding=(0, 1)
                ))

            if i < len(flaky_tests):
                console.print()


@app.command()
def version():
    """Show version information"""
    from . import __version__
    console.print(f"Flaky Test Detector v{__version__}")


if __name__ == "__main__":
    app()
