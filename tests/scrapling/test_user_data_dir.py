"""Tests für UserDataDirManager — synchron, kein pytest-anyio.

Alle Disk-Operationen via tmp_path-Fixture (pytest-eingebaut) — keine Schreibzugriffe
auf ~/.frontprompt während der Test-Suite.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from frontprompt.scrapling.user_data_dir import UserDataDirManager
from frontprompt.types import PageSessionId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dns_hash(dns_domain: str) -> str:
    """Repliziert die erwartete Hash-Funktion des Moduls für Assertions."""
    return hashlib.sha256(dns_domain.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# allocate()
# ---------------------------------------------------------------------------


def test_allocate_creates_directory_tree(tmp_path: Path) -> None:
    """allocate() legt das vollständige Verzeichnis-Skelett an."""
    mgr = UserDataDirManager(root=tmp_path)
    dns_domain = "example.com"
    page_session_id = PageSessionId("ps-001")

    result = mgr.allocate(dns_domain=dns_domain, page_session_id=page_session_id)

    assert result.exists()
    assert result.is_dir()
    expected = tmp_path / _dns_hash(dns_domain) / "ps-001"
    assert result == expected


def test_allocate_idempotent_same_dns_domain_page_session_id(tmp_path: Path) -> None:
    """Zweimaliges allocate() mit denselben Parametern gibt denselben Pfad zurück
    und wirft keine Exception — os.makedirs(exist_ok=True) Semantik."""
    mgr = UserDataDirManager(root=tmp_path)
    ps_id = PageSessionId("ps-idem")

    path_first = mgr.allocate(dns_domain="idem.example.com", page_session_id=ps_id)
    path_second = mgr.allocate(dns_domain="idem.example.com", page_session_id=ps_id)

    assert path_first == path_second
    assert path_first.exists()


def test_allocate_different_page_session_ids_same_dns_domain_no_collision(tmp_path: Path) -> None:
    """Kern-Invariante der user_data_dir-Isolation: zwei page_session_ids auf derselben dns_domain
    bekommen disjunkte Pfade — niemals denselben user_data_dir."""
    mgr = UserDataDirManager(root=tmp_path)
    dns_domain = "shared.example.com"

    path_a = mgr.allocate(dns_domain=dns_domain, page_session_id=PageSessionId("ps-A"))
    path_b = mgr.allocate(dns_domain=dns_domain, page_session_id=PageSessionId("ps-B"))

    assert path_a != path_b
    assert path_a.exists()
    assert path_b.exists()
    # beide liegen im selben dns_domain-Subtree
    assert path_a.parent == path_b.parent


def test_allocate_different_dns_domains_no_collision(tmp_path: Path) -> None:
    """Verschiedene dns_domains landen in verschiedenen Subtrees."""
    mgr = UserDataDirManager(root=tmp_path)
    ps_id = PageSessionId("ps-shared")

    path_a = mgr.allocate(dns_domain="alpha.example.com", page_session_id=ps_id)
    path_b = mgr.allocate(dns_domain="beta.example.com", page_session_id=ps_id)

    assert path_a != path_b
    assert path_a.parent != path_b.parent


# ---------------------------------------------------------------------------
# release() + LRU
# ---------------------------------------------------------------------------


def test_release_triggers_lru_at_keep_n_plus_1(tmp_path: Path) -> None:
    """Nach keep_n+1 allocate()+release()-Zyklen existieren genau keep_n Verzeichnisse."""
    keep_n = 3
    mgr = UserDataDirManager(root=tmp_path, keep_n=keep_n)
    dns_domain = "lru.example.com"
    dns_hash = _dns_hash(dns_domain)

    for i in range(keep_n + 1):
        ps_id = PageSessionId(f"ps-lru-{i:03d}")
        mgr.allocate(dns_domain=dns_domain, page_session_id=ps_id)
        # mtime-Abstand sicherstellen damit LRU deterministisch ist
        time.sleep(0.01)
        mgr.release(dns_domain=dns_domain, page_session_id=ps_id)

    subtree = tmp_path / dns_hash
    remaining = [d for d in subtree.iterdir() if d.is_dir()]
    assert len(remaining) == keep_n


def test_release_keeps_n_most_recent(tmp_path: Path) -> None:
    """LRU behält die N jüngsten (mtime) RELEASED Verzeichnisse — ältestes wird gelöscht.

    Hinweis: Ein früherer Test war mit
    `test_directory_in_use_not_deleted_during_lru` nicht kompatibel — nur RELEASED Sessions
    sind LRU-Kandidaten (sonst würde aktiv genutztes user_data_dir mitten in der
    Browser-Operation gelöscht). Fix: alle 3 Sessions releasen, dann LRU-trigger.
    """
    keep_n = 2
    mgr = UserDataDirManager(root=tmp_path, keep_n=keep_n)
    dns_domain = "recent.example.com"

    paths: list[Path] = []
    ps_ids: list[PageSessionId] = []
    for i in range(keep_n + 1):
        ps_id = PageSessionId(f"ps-recent-{i:03d}")
        p = mgr.allocate(dns_domain=dns_domain, page_session_id=ps_id)
        time.sleep(0.01)  # garantierter mtime-Abstand
        paths.append(p)
        ps_ids.append(ps_id)

    # Alle 3 releasen → alle 3 sind LRU-Kandidaten. Letzter release triggert cleanup.
    for ps_id in ps_ids:
        mgr.release(dns_domain=dns_domain, page_session_id=ps_id)

    # ältestes (paths[0]) muss weg sein, jüngere bleiben
    assert not paths[0].exists(), "ältestes Verzeichnis muss durch LRU entfernt worden sein"
    assert paths[1].exists(), "zweitjüngstes Verzeichnis muss erhalten bleiben"
    assert paths[2].exists(), "jüngstes Verzeichnis muss erhalten bleiben"


# ---------------------------------------------------------------------------
# Hash-Determinismus
# ---------------------------------------------------------------------------


def test_dns_domain_hash_deterministic_truncated_16_hex(tmp_path: Path) -> None:
    """SHA256(dns_domain)[:16] ist deterministisch und hat genau 16 Hex-Zeichen."""
    mgr = UserDataDirManager(root=tmp_path)
    dns_domain = "hash-check.example.com"

    path = mgr.allocate(dns_domain=dns_domain, page_session_id=PageSessionId("ps-hash"))

    dns_hash_dir = path.parent.name
    expected_hash = hashlib.sha256(dns_domain.encode()).hexdigest()[:16]
    assert dns_hash_dir == expected_hash
    assert len(dns_hash_dir) == 16
    assert all(c in "0123456789abcdef" for c in dns_hash_dir)


# ---------------------------------------------------------------------------
# Default root
# ---------------------------------------------------------------------------


def test_default_root_is_home_frontprompt_browser_data() -> None:
    """Ohne explizites root liegt der Default unter ~/.frontprompt/browser-data/."""
    mgr = UserDataDirManager()  # kein root-Argument

    # Wir rufen allocate() NICHT auf (würde ~/.frontprompt/ auf CI beschreiben).
    # Stattdessen testen wir den intern berechneten root-Pfad direkt.
    expected_root = Path.home() / ".frontprompt" / "browser-data"
    assert mgr.root == expected_root


# ---------------------------------------------------------------------------
# Safety guard: in-use directory survives LRU
# ---------------------------------------------------------------------------


def test_directory_in_use_not_deleted_during_lru(tmp_path: Path) -> None:
    """Ein Verzeichnis das per allocate() geöffnet aber noch NICHT released wurde
    gilt als 'in use' und darf nicht durch LRU gelöscht werden — auch wenn der
    dns_domain-Subtree > keep_n Einträge hat.

    Implementierungshinweis: 'in use' = allocate() wurde aufgerufen, aber release()
    noch nicht. Der Manager verfolgt active_sessions intern. LRU darf nur auf
    released sessions arbeiten.
    """
    keep_n = 2
    mgr = UserDataDirManager(root=tmp_path, keep_n=keep_n)
    dns_domain = "inuse.example.com"

    # ps-active wird allocate()d aber NIEMALS release()d
    active_path = mgr.allocate(dns_domain=dns_domain, page_session_id=PageSessionId("ps-active"))

    # keep_n weitere Einträge alloc+release → triggert LRU
    for i in range(keep_n + 1):
        ps_id = PageSessionId(f"ps-filler-{i:03d}")
        time.sleep(0.01)
        mgr.allocate(dns_domain=dns_domain, page_session_id=ps_id)
        mgr.release(dns_domain=dns_domain, page_session_id=ps_id)

    assert active_path.exists(), "in-use Verzeichnis darf nicht durch LRU gelöscht werden"
