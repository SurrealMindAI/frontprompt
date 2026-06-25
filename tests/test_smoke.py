"""Smoke tests — verifies the installed package is importable and foundation deps resolved."""


def test_version_exposed() -> None:
    import frontprompt

    assert frontprompt.__version__ == "0.0.4"


def test_cli_main_runs() -> None:
    """Raucht-Test: main() ist importierbar und --help exitiert sauber."""
    from click.testing import CliRunner

    from frontprompt.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0, f"exit {result.exit_code}: {result.output}"


def test_foundation_libs_resolved() -> None:
    # Smoke-import — verifies the runtime deps are installed
    import pydantic_zod_codegen  # noqa: F401
    import scrapling  # noqa: F401
