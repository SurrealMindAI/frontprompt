"""Smoke tests — verifies the installed package is importable and foundation deps resolved."""


def test_version_exposed() -> None:
    import re

    import frontprompt

    # Smoke: __version__ is exposed as a semver string. We deliberately do NOT hardcode
    # the number — the SSoT is pyproject.toml and scripts/check_versions.py enforces that
    # __version__ equals it, so asserting a literal here only broke CI on every bump.
    assert isinstance(frontprompt.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", frontprompt.__version__), frontprompt.__version__


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
