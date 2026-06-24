"""Codegen-Subprocess-Wrapper: Pydantic-Messages → Zod-Schemas + TS-Types.

Schneidet die ``pydantic-zod-codegen`` CLI an, schreibt das output ins
``frontend/src/_generated/schemas.ts``. Wird vom :mod:`frontprompt.build`
modul aufgerufen, NICHT vom CLI-show-pfad.

Canonical Build Pipeline (see ARCHITECTURE.md): Codegen läuft VOR ``bun run build``.

Hard-fail-Verhalten:
    - ``pydantic-zod-codegen`` CLI muss verfügbar sein (in der venv).
    - ``bun`` muss auf PATH sein (codegen ruft intern ``bunx json-schema-to-typescript``).
    - Beide Fehler werden mit klaren Hinweis-Messages reportet.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import structlog

_LOG = structlog.get_logger(__name__)

# pydantic-zod-codegen bug-workaround: wenn ein Pydantic-Modell-Feld als $ref
# auf einen anderen-Root verweist UND derselbe nested-type bereits inline in
# einem anderen Root vorkommt, emittiert die Zod-augmentation-stage einen
# numbered-suffix-Duplikat (``ElementRect1``) mit broken-syntax
# ``number.optional()`` statt ``z.number().optional()``. Der Block ist tot
# (keine importer), aber TypeScript bricht den compile. Wir strippen ihn
# post-codegen. TODO: upstream fix in pydantic-zod-codegen
# ([feedback_lib_first_when_pattern_recurs]).
# Interface-block + optionaler vorangestellter JSDoc.
_DEAD_INTERFACE_RE = re.compile(
    r"\n(?:/\*\*\n(?:[^*]|\*(?!/))*?\*/\n)?export interface \w+\d+ \{[^}]*\}\n",
    re.DOTALL,
)
# Broken const-block: ``export const Foo1 = z.object({ x: number.optional(), ... });``.
# Wir matchen über die kaputte syntax (``number.optional()`` ohne ``z.``-prefix).
_DEAD_CONST_RE = re.compile(
    r"\nexport const \w+\d+ = z\.object\(\{\n(?:\s+\w+: \w+\.optional\(\),\n)+\}\);\n",
    re.DOTALL,
)


def _strip_dead_duplicates(path: Path) -> int:
    """Remove broken numbered-duplicate blocks from a generated .ts file.

    Returns the number of duplicate-blocks stripped (interface + const).
    """
    content = path.read_text(encoding="utf-8")
    content, n_interface = _DEAD_INTERFACE_RE.subn("\n", content)
    content, n_const = _DEAD_CONST_RE.subn("\n", content)
    total = n_interface + n_const
    if total > 0:
        path.write_text(content, encoding="utf-8")
    return total


#: Project-Root — codegen.py liegt bei src/frontprompt/bridge/, also parents[3].
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

#: Module-Pfade der Pydantic-Modelle die in TS landen sollen.
#: Reihenfolge: messages danach state (damit state-types vor messages-types die sie referenzieren landen).
MESSAGES_MODULE: str = "frontprompt.bridge.messages"
STATE_MODULE: str = "frontprompt.state.state"

#: Output-Pfade für die generierten Zod-Schemas.
GENERATED_SCHEMAS_PATH: Path = _PROJECT_ROOT / "frontend" / "src" / "_generated" / "schemas.ts"
GENERATED_STATE_PATH: Path = _PROJECT_ROOT / "frontend" / "src" / "_generated" / "state.ts"


class CodegenError(RuntimeError):
    """Codegen-CLI ist fehlgeschlagen — entweder dependency-issue oder schema-problem."""


def _run_one(module: str, output_path: Path) -> Path:
    """Run pydantic-zod-codegen generate für ein einzelnes module."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _LOG.info("bridge.codegen.start", module=module, output_path=str(output_path))

    result = subprocess.run(
        ["pydantic-zod-codegen", "generate", module, "-o", str(output_path)],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        _LOG.error(
            "bridge.codegen.failed",
            module=module,
            returncode=result.returncode,
            stderr=result.stderr[-1000:],
            stdout=result.stdout[-500:],
        )
        raise CodegenError(
            f"pydantic-zod-codegen generate ({module}) failed (exit {result.returncode}):\n"
            f"--- stderr ---\n{result.stderr[-1000:]}\n"
            f"--- stdout ---\n{result.stdout[-500:]}"
        )

    if not output_path.is_file():
        raise CodegenError(f"pydantic-zod-codegen exited 0 but {output_path} was not written.")

    stripped = _strip_dead_duplicates(output_path)
    _LOG.info(
        "bridge.codegen.done",
        module=module,
        output_path=str(output_path),
        bytes_written=output_path.stat().st_size,
        dead_duplicates_stripped=stripped,
    )
    return output_path


def run_codegen() -> list[Path]:
    """Run codegen für alle Pydantic-modules (messages + state).

    Returns:
        Liste der geschriebenen Pfade.

    Raises:
        CodegenError: bun fehlt, CLI fehlt, oder generate-step failed.
    """
    if shutil.which("bun") is None:
        raise CodegenError(
            "`bun` not on PATH — pydantic-zod-codegen needs it for "
            "`bunx json-schema-to-typescript`. Install: `brew install bun` "
            "or `curl -fsSL https://bun.sh/install | bash`."
        )

    if shutil.which("pydantic-zod-codegen") is None:
        raise CodegenError(
            "`pydantic-zod-codegen` CLI not found. Run `uv sync` to install "
            "the dependency (git-URL pinned in pyproject.toml)."
        )

    # State module zuerst — messages referenzieren state-types
    return [
        _run_one(STATE_MODULE, GENERATED_STATE_PATH),
        _run_one(MESSAGES_MODULE, GENERATED_SCHEMAS_PATH),
    ]


def write_build_info(
    *,
    build_session: str,
    build_version: str,
    build_git_sha: str,
) -> Path:
    """Schreibe ``_generated/build-info.ts`` mit constants die der Overlay liest.

    Wird vom :mod:`frontprompt.build` modul aufgerufen (NICHT vom codegen-step
    selber — separation of concerns: codegen.py handelt schemas, build-info ist
    deployment-metadata).
    """
    output_path = GENERATED_SCHEMAS_PATH.parent / "build-info.ts"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""\
// AUTO-GENERATED by python -m frontprompt.build — DO NOT EDIT.
// Canonical Build Pipeline.

export const BUILD_SESSION = {build_session!r} as const;
export const BUILD_VERSION = {build_version!r} as const;
export const BUILD_GIT_SHA = {build_git_sha!r} as const;
"""
    output_path.write_text(content, encoding="utf-8")
    _LOG.info(
        "bridge.codegen.build_info_written",
        output_path=str(output_path),
        build_session=build_session,
    )
    return output_path


if __name__ == "__main__":
    # Auch standalone aufrufbar via `python -m frontprompt.bridge.codegen`
    run_codegen()
