"""ReplayPlayer — daemon-side replay engine.

Walks a Recording's timeline in seq order, dispatches each TimelineEntry to
the appropriate page-controller action, and produces a ReplayReport.

Design decisions:
- Calls page_controller methods (navigate, click_selector, keyboard_type,
  keyboard_press, evaluate_assertion) — not browser_actions directly.
- Per-step exceptions (Exception subclasses) → step fails, replay continues.
- Unrecoverable BaseException (e.g. CancelledError) → status='failed', returned (not re-raised).
- Cross-origin navigation: structlog.warning emitted, not blocked.
- Parameter substitution: {{name}} replaced from provided dict before execution.
  Missing parameter → step fails with error='missing parameter: <name>'.
- dry_run=True: all steps skipped with skipped_reason='dry_run', no browser calls.
- real_time=True: anyio.sleep between steps per inter-event timestamp delta.
- Forward-compat: unknown/unhandled entry kinds → skipped=True.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
import structlog

from frontprompt.state.state import (
    AssertionEntry,
    NavigationEntry,
    PageEventEntry,
    PickRefEntry,
    Recording,
    RegionRefEntry,
    RelationRefEntry,
    ReplayProgress,
    ReplayReport,
    ReplayStepResult,
)

if TYPE_CHECKING:
    pass

_LOG = structlog.get_logger(__name__)

# Keys that are treated as named control keys (route to keyboard_press)
# Single-character keys are typed via keyboard_type.
_CONTROL_KEY_PREFIXES = ("Arrow", "Page", "Home", "End", "Insert", "Delete", "Backspace", "Tab")
_CONTROL_KEYS = frozenset(
    {
        "Enter",
        "Escape",
        "Tab",
        "Backspace",
        "Delete",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
        "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
    }
)

_PARAM_RE = re.compile(r"\{\{(\w+)\}\}")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_control_key(key: str) -> bool:
    """Return True if key should use keyboard_press (not keyboard_type).

    Only named control keys (Enter, Escape, Tab, Arrow*, etc.) use keyboard_press.
    Everything else — including single characters and substituted multi-char strings —
    uses keyboard_type.
    """
    if key in _CONTROL_KEYS:
        return True
    for prefix in _CONTROL_KEY_PREFIXES:
        if key.startswith(prefix):
            return True
    return False


def _bind_params(text: str, params: dict[str, str]) -> str:
    """Substitute {{name}} placeholders with values from params.

    Returns the substituted string, or raises ValueError with
    'missing parameter: <name>' if a placeholder has no value.
    """

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in params:
            raise ValueError(f"missing parameter: {name}")
        return params[name]

    return _PARAM_RE.sub(_replace, text)


class ReplayPlayer:
    """Executes a stored Recording as a sequence of browser actions.

    Args:
        recording: The Recording aggregate to replay.
        parameters: Bound parameter values for {{name}} substitution.
        page_controller: Controller with navigate/click_selector/keyboard_type/
            keyboard_press/evaluate_assertion methods.
        state_manager: StateManager for progress + report persistence.
        dry_run: If True, log all intended actions without executing them.
        real_time: If True, honor inter-event timestamp deltas as sleep intervals.
    """

    def __init__(
        self,
        recording: Recording,
        parameters: dict[str, str],
        page_controller: Any,
        state_manager: Any,
        dry_run: bool = False,
        real_time: bool = False,
    ) -> None:
        self._recording = recording
        self._parameters = dict(parameters)
        self._page_controller = page_controller
        self._state_manager = state_manager
        self._dry_run = dry_run
        self._real_time = real_time

    async def run(self) -> ReplayReport:
        """Execute the replay and return a ReplayReport.

        Always returns — catches BaseException (CancelledError) and returns
        status='failed'. Individual step failures do not abort the replay.
        """
        replay_id = str(uuid4())
        started_at = _now_ms()
        recording_id = self._recording.recording_id
        results: list[ReplayStepResult] = []

        # Fill parameter defaults from ParameterDeclaration
        merged_params: dict[str, str] = {}
        for decl in self._recording.parameters:
            if decl.default_value is not None:
                merged_params[decl.name] = decl.default_value
        merged_params.update(self._parameters)  # provided values override defaults

        entries = sorted(self._recording.entries, key=lambda e: e.seq)
        total_steps = len(entries)

        _LOG.info(
            "replay_player.run.start",
            replay_id=replay_id,
            recording_id=recording_id,
            total_steps=total_steps,
            dry_run=self._dry_run,
            real_time=self._real_time,
        )

        try:
            prev_ts: int | None = None

            for entry in entries:
                # Honor inter-event timing in real_time mode
                if self._real_time and prev_ts is not None:
                    delta_ms = entry.timestamp_ms - prev_ts
                    if delta_ms > 0:
                        await anyio.sleep(delta_ms / 1000.0)

                # Update progress before step
                passed = sum(1 for r in results if r.assertion_passed is True)
                failed = sum(1 for r in results if r.assertion_passed is False)
                await self._state_manager.set_active_replay_progress(
                    ReplayProgress(
                        replay_id=replay_id,
                        recording_id=recording_id,
                        current_seq=entry.seq,
                        total_steps=total_steps,
                        passed_assertions=passed,
                        failed_assertions=failed,
                    )
                )

                step = await self._run_step(entry, merged_params)
                results.append(step)
                prev_ts = entry.timestamp_ms

        except BaseException as exc:
            _LOG.warning(
                "replay_player.run.fatal",
                replay_id=replay_id,
                error=str(exc),
                exc_type=type(exc).__name__,
            )
            await self._state_manager.set_active_replay_progress(None)
            report = ReplayReport(
                replay_id=replay_id,
                recording_id=recording_id,
                parameters=merged_params,
                status="failed",
                started_at_ms=started_at,
                ended_at_ms=_now_ms(),
                step_results=results,
                error=str(exc),
            )
            await self._state_manager.save_replay_report(report)
            return report

        # Normal completion
        await self._state_manager.set_active_replay_progress(None)

        all_ok = all(r.ok for r in results)
        status: str = "completed" if all_ok else "completed"
        # status="completed" even if some steps failed (assertion failures or step errors)
        # status="failed" only on unrecoverable abort (handled above)

        report = ReplayReport(
            replay_id=replay_id,
            recording_id=recording_id,
            parameters=merged_params,
            status="completed",  # type: ignore[arg-type]
            started_at_ms=started_at,
            ended_at_ms=_now_ms(),
            step_results=results,
        )
        await self._state_manager.save_replay_report(report)

        _LOG.info(
            "replay_player.run.done",
            replay_id=replay_id,
            total_steps=total_steps,
            passed=len([r for r in results if r.ok]),
        )
        return report

    async def _run_step(self, entry: Any, params: dict[str, str]) -> ReplayStepResult:
        """Dispatch a single TimelineEntry and return its ReplayStepResult."""
        seq: int = entry.seq
        kind: str = entry.kind
        step_start = _now_ms()

        if self._dry_run:
            _LOG.info("replay_player.step.dry_run", seq=seq, kind=kind)
            return ReplayStepResult(
                seq=seq,
                kind=kind,
                ok=True,
                skipped=True,
                skipped_reason="dry_run",
                duration_ms=_now_ms() - step_start,
            )

        try:
            return await self._dispatch_entry(entry, params, seq, kind, step_start)
        except Exception as exc:
            _LOG.warning("replay_player.step.error", seq=seq, kind=kind, error=str(exc))
            return ReplayStepResult(
                seq=seq,
                kind=kind,
                ok=False,
                skipped=False,
                error=str(exc),
                duration_ms=_now_ms() - step_start,
            )

    async def _dispatch_entry(
        self,
        entry: Any,
        params: dict[str, str],
        seq: int,
        kind: str,
        step_start: int,
    ) -> ReplayStepResult:
        """Dispatch to the appropriate replay handler by kind."""

        if isinstance(entry, NavigationEntry):
            return await self._replay_navigation(entry, params, seq, step_start)

        elif isinstance(entry, PageEventEntry):
            return await self._replay_page_event(entry, params, seq, step_start)

        elif isinstance(entry, AssertionEntry):
            return await self._replay_assertion(entry, seq, step_start)

        elif isinstance(entry, (PickRefEntry, RegionRefEntry, RelationRefEntry)):
            skipped_reason = f"{kind}_skipped_mvp"
            _LOG.info("replay_player.step.skipped", seq=seq, kind=kind, reason=skipped_reason)
            return ReplayStepResult(
                seq=seq,
                kind=kind,
                ok=True,
                skipped=True,
                skipped_reason=skipped_reason,
                duration_ms=_now_ms() - step_start,
            )

        else:
            # Unknown/forward-compat kind (e.g. transcript_segment from voice-over)
            unknown_reason = f"{kind}_skipped_unknown"
            _LOG.info("replay_player.step.skipped_unknown", seq=seq, kind=kind)
            return ReplayStepResult(
                seq=seq,
                kind=kind,
                ok=True,
                skipped=True,
                skipped_reason=unknown_reason,
                duration_ms=_now_ms() - step_start,
            )

    async def _replay_navigation(
        self, entry: NavigationEntry, params: dict[str, str], seq: int, step_start: int
    ) -> ReplayStepResult:
        """Replay a navigation entry — navigate to to_url with param substitution."""
        to_url = _bind_params(entry.to_url, params)

        # Cross-origin detection (soft warning — never blocks)
        try:
            current_netloc = urlsplit(self._page_controller.page.url).netloc
            target_netloc = urlsplit(to_url).netloc
            if current_netloc and target_netloc and current_netloc != target_netloc:
                _LOG.warning(
                    "replay_player.navigation.cross_origin",
                    seq=seq,
                    from_netloc=current_netloc,
                    to_netloc=target_netloc,
                )
        except Exception:
            pass  # non-critical — never block navigation

        result = await self._page_controller.navigate(to_url)
        ok: bool = result.get("ok", True) if isinstance(result, dict) else True

        return ReplayStepResult(
            seq=seq,
            kind="navigation",
            ok=ok,
            skipped=False,
            error=result.get("error") if isinstance(result, dict) else None,
            duration_ms=_now_ms() - step_start,
        )

    async def _replay_page_event(
        self, entry: PageEventEntry, params: dict[str, str], seq: int, step_start: int
    ) -> ReplayStepResult:
        """Replay a page_event entry (click, keydown, pointerdown)."""

        if entry.event_type == "click":
            target = _bind_params(entry.target, params)
            result = await self._page_controller.click_selector(target)
            ok: bool = result.get("ok", True) if isinstance(result, dict) else True
            return ReplayStepResult(
                seq=seq,
                kind="page_event",
                ok=ok,
                skipped=False,
                error=result.get("error") if isinstance(result, dict) else None,
                duration_ms=_now_ms() - step_start,
            )

        elif entry.event_type == "keydown":
            key = entry.key or ""
            key = _bind_params(key, params)

            if _is_control_key(key):
                result = await self._page_controller.keyboard_press(key)
            else:
                result = await self._page_controller.keyboard_type(key)

            ok = result.get("ok", True) if isinstance(result, dict) else True
            return ReplayStepResult(
                seq=seq,
                kind="page_event",
                ok=ok,
                skipped=False,
                error=result.get("error") if isinstance(result, dict) else None,
                duration_ms=_now_ms() - step_start,
            )

        else:
            # pointerdown and other event types → skip in MVP
            skipped_reason = f"{entry.event_type}_skipped_mvp"
            _LOG.info("replay_player.step.skipped", seq=seq, event_type=entry.event_type)
            return ReplayStepResult(
                seq=seq,
                kind="page_event",
                ok=True,
                skipped=True,
                skipped_reason=skipped_reason,
                duration_ms=_now_ms() - step_start,
            )

    async def _replay_assertion(
        self, entry: AssertionEntry, seq: int, step_start: int
    ) -> ReplayStepResult:
        """Evaluate an assertion against the live DOM."""
        result = await self._page_controller.evaluate_assertion(entry)

        ok: bool = result.get("ok", True) if isinstance(result, dict) else True
        passed: bool | None = result.get("assertion_passed") if ok else None
        actual: str | None = result.get("assertion_actual")

        return ReplayStepResult(
            seq=seq,
            kind="assertion",
            ok=ok,
            skipped=False,
            error=result.get("error") if isinstance(result, dict) else None,
            assertion_passed=passed,
            assertion_actual=actual,
            duration_ms=_now_ms() - step_start,
        )


__all__ = ["ReplayPlayer"]
