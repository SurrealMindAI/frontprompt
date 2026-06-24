"""UserDataDirManager — per-(dns_domain, page_session_id) Chromium-user_data_dir.

Mitigiert die chromium user_data_dir thread-safety-Gefahr per Pfad-Isolation:
    ~/.frontprompt/browser-data/<sha256(dns_domain)[:16]>/<page_session_id>/

Zwei PageSession-Aggregate teilen sich NIEMALS denselben Pfad. SingletonLock-Races
sind damit strukturell ausgeschlossen.

LRU-Cleanup pro dns_domain-Subtree (Standard: keep_n=5) wird bei release() ausgelöst.
Verzeichnisse die allocate()d aber nicht release()d wurden gelten als "in use" und
werden durch LRU nicht gelöscht.

Dieses Modul ist synchron + reine stdlib/pathlib — kein scrapling-Import, kein anyio.
Async-Caller (PageSession.navigate()) rufen via anyio.to_thread.run_sync() auf wenn
nötig; allocate() ist schnell genug für synchronen Call im async-Kontext.

Naming-Konvention: alle Parameter-Namen sind explizit qualifiziert (dns_domain, page_session_id).
Single-writer: LRU-Mutation ist filelock-geschützt (Single-Writer pro dns_domain-Subtree).
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import filelock

from frontprompt.types import PageSessionId

#: Standard-Anzahl der zu behaltenden user_data_dirs pro dns_domain-Subtree.
DEFAULT_KEEP_N: int = 5

#: Standard-Root-Verzeichnis (user_data_dir-Isolation).
_DEFAULT_ROOT: Path = Path.home() / ".frontprompt" / "browser-data"


def _dns_domain_hash(dns_domain: str) -> str:
    """SHA256(dns_domain)[:16] — deterministischer Verzeichnisname-Anteil.

    Truncated auf 16 Hex-Zeichen (64 Bit). Kollisionsrisiko bei typischen
    Workloads (< 1000 dns_domains) ist astronomisch gering und bewusst
    akzeptiert (thread-safety mitigation design decision).
    """
    return hashlib.sha256(dns_domain.encode()).hexdigest()[:16]


class UserDataDirManager:
    """Verwaltet isolierte Chromium-user_data_dirs pro (dns_domain, page_session_id).

    Öffentliche API::

        mgr = UserDataDirManager()                        # Default: ~/.frontprompt/browser-data/
        path = mgr.allocate("example.com", ps_id)        # Verzeichnis erstellen + tracken
        mgr.release("example.com", ps_id)                # LRU-Cleanup triggern

    Thread-Safety: allocate() ist idempotent und thread-safe via os.makedirs(exist_ok=True).
    release() LRU-Mutation ist filelock-geschützt pro dns_domain-Subtree.
    """

    def __init__(self, root: Path | None = None, keep_n: int = DEFAULT_KEEP_N) -> None:
        """Initialisiert den Manager.

        Args:
            root: Root-Verzeichnis für alle user_data_dirs.
                  Default: ~/.frontprompt/browser-data/
            keep_n: Maximale Anzahl user_data_dirs pro dns_domain-Subtree.
                    Älteste (nach mtime) werden bei release() getrimmt.
                    Muss >= 1 sein.
        """
        if keep_n < 1:
            raise ValueError(f"keep_n muss >= 1 sein, got {keep_n!r}")
        self._root: Path = root if root is not None else _DEFAULT_ROOT
        self._keep_n: int = keep_n
        # Trackt active (allocated but not released) page_session_ids pro dns_domain_hash
        self._active: dict[str, set[str]] = {}

    @property
    def root(self) -> Path:
        """Konfiguriertes Root-Verzeichnis (lesbar für Tests)."""
        return self._root

    def allocate(self, dns_domain: str, page_session_id: PageSessionId) -> Path:
        """Erstellt und registriert das user_data_dir für (dns_domain, page_session_id).

        Idempotent: mehrfache Aufrufe mit denselben Parametern geben denselben
        Pfad zurück und legen das Verzeichnis ggf. mehrfach mit exist_ok=True an.

        Args:
            dns_domain: DNS-Hostname des Scraping-Targets.
                        z.B. "nowsecure.nl", "google.com"
            page_session_id: Stabile PageSession-Identity.

        Returns:
            Absoluter Pfad zum erstellten user_data_dir.
        """
        dns_hash = _dns_domain_hash(dns_domain)
        target = self._root / dns_hash / str(page_session_id)
        os.makedirs(target, exist_ok=True)

        # Als "in use" markieren — LRU überspringt dieses Verzeichnis
        if dns_hash not in self._active:
            self._active[dns_hash] = set()
        self._active[dns_hash].add(str(page_session_id))

        return target

    def release(self, dns_domain: str, page_session_id: PageSessionId) -> None:
        """Deregistriert das user_data_dir und triggert ggf. LRU-Cleanup.

        Der LRU-Cleanup entfernt die ältesten (nach mtime) Verzeichnisse im
        dns_domain-Subtree bis maximal keep_n übrig sind. Verzeichnisse die
        aktuell als "in use" (allocate()d, nicht release()d) gelten, werden
        beim Cleanup übersprungen.

        Args:
            dns_domain: DNS-Hostname — muss mit dem allocate()-Aufruf übereinstimmen.
            page_session_id: PageSession-Identity.
        """
        dns_hash = _dns_domain_hash(dns_domain)
        ps_str = str(page_session_id)

        # "in use" Tracking aufheben
        if dns_hash in self._active:
            self._active[dns_hash].discard(ps_str)

        self._lru_cleanup(dns_hash=dns_hash)

    def _lru_cleanup(self, dns_hash: str) -> None:
        """Trimmt den dns_domain-Subtree auf maximal keep_n Verzeichnisse.

        Sortierung nach mtime aufsteigend → älteste zuerst löschen.
        Verzeichnisse in self._active[dns_hash] werden übersprungen.

        filelock schützt die Mutation gegen konkurrierende release()-Aufrufe
        (Single-Writer-Invariante auf dem LRU-Mutations-Pfad).
        """
        subtree = self._root / dns_hash
        if not subtree.exists():
            return

        lock_path = subtree / ".lru.lock"
        active_set = self._active.get(dns_hash, set())

        def _do_cleanup() -> None:
            dirs = sorted(
                (d for d in subtree.iterdir() if d.is_dir() and not d.name.startswith(".")),
                key=lambda d: d.stat().st_mtime,
            )
            # Nur nicht-active Verzeichnisse sind LRU-Kandidaten
            candidates = [d for d in dirs if d.name not in active_set]
            excess = max(0, len(candidates) - self._keep_n)
            for d in candidates[:excess]:
                shutil.rmtree(d, ignore_errors=True)

        with filelock.FileLock(str(lock_path), timeout=5):
            _do_cleanup()
