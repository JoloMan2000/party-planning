"""SQLite-Persistenz für den Social-Profile-/Onboarding-Layer (Onboarding-
Spec, Phase 6 des Account-basierten Pivots).

Mirrort exakt das etablierte Muster aus ``accounts/user_storage.py``:
kurzlebige ``with sqlite3.connect(db_path) as conn:``-Blöcke,
``CREATE TABLE IF NOT EXISTS``, ein ``init_*(db_path)`` pro Modul,
ausführbarer ``__main__``-Selbsttest.

``birth_date`` ist bewusst NICHT über ``upsert_user_profile`` änderbar,
sobald ein Profil existiert - der einzige Weg, ein bestehendes
``birth_date`` zu ändern, ist ``apply_birth_date_correction`` (kontrollierter
Flow, siehe Onboarding-Spec: "Birth date is protected"). ``upsert_user_profile``
darf ``birth_date`` nur beim initialen Anlegen (Onboarding) setzen."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

from accounts.domain import BirthDateCorrection, UserProfile


def init_profile_storage(db_path: str | Path) -> None:
    """Legt ``user_profiles``/``birth_date_corrections`` an, falls nicht
    vorhanden. Idempotent, sicher bei jedem App-Start aufrufbar."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                birth_date TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL DEFAULT '',
                onboarding_completed_at TEXT,
                profile_completion_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS birth_date_corrections (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                previous_birth_date TEXT,
                new_birth_date TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_birth_date_corrections_user ON birth_date_corrections(user_id)"
        )


def _row_to_profile(row: sqlite3.Row) -> UserProfile:
    return UserProfile(
        user_id=row["user_id"],
        birth_date=date.fromisoformat(row["birth_date"]),
        gender=row["gender"] or "",
        bio=row["bio"] or "",
        onboarding_completed_at=(
            datetime.fromisoformat(row["onboarding_completed_at"]) if row["onboarding_completed_at"] else None
        ),
        profile_completion_version=row["profile_completion_version"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def get_user_profile(db_path: str | Path, user_id: str) -> UserProfile | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_profile(row) if row is not None else None


def upsert_user_profile(
    db_path: str | Path,
    user_id: str,
    *,
    birth_date: date | None = None,
    gender: str | None = None,
    bio: str | None = None,
) -> UserProfile:
    """Legt das Profil beim ersten Aufruf an (``birth_date`` dann Pflicht) oder
    aktualisiert ``gender``/``bio`` eines bestehenden Profils. ``birth_date``
    wird bei einem bereits existierenden Profil IGNORIERT (geschützt - siehe
    Moduldoku), auch wenn hier übergeben - Aufrufer (Router) darf ``birth_date``
    auf einem Update-Request ohnehin gar nicht erst entgegennehmen."""
    now = datetime.now().isoformat()
    existing = get_user_profile(db_path, user_id)
    with sqlite3.connect(db_path) as conn:
        if existing is None:
            if birth_date is None:
                raise ValueError("birth_date ist beim initialen Anlegen eines Profils Pflicht.")
            conn.execute(
                """
                INSERT INTO user_profiles
                    (user_id, birth_date, gender, bio, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, birth_date.isoformat(), gender or "", bio or "", now, now),
            )
        else:
            new_gender = gender if gender is not None else existing.gender
            new_bio = bio if bio is not None else existing.bio
            conn.execute(
                "UPDATE user_profiles SET gender = ?, bio = ?, updated_at = ? WHERE user_id = ?",
                (new_gender, new_bio, now, user_id),
            )
    profile = get_user_profile(db_path, user_id)
    assert profile is not None
    return profile


def apply_birth_date_correction(
    db_path: str | Path, user_id: str, new_birth_date: date, reason: str = ""
) -> UserProfile:
    """Einziger Weg, ein bereits gesetztes ``birth_date`` zu ändern - schreibt
    zusätzlich einen Audit-Eintrag in ``birth_date_corrections`` (gleiche
    Transaktion)."""
    existing = get_user_profile(db_path, user_id)
    previous_birth_date = existing.birth_date if existing is not None else None
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO birth_date_corrections
                (id, user_id, previous_birth_date, new_birth_date, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                user_id,
                previous_birth_date.isoformat() if previous_birth_date else None,
                new_birth_date.isoformat(),
                reason,
                now,
            ),
        )
        if existing is None:
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, birth_date, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, new_birth_date.isoformat(), now, now),
            )
        else:
            conn.execute(
                "UPDATE user_profiles SET birth_date = ?, updated_at = ? WHERE user_id = ?",
                (new_birth_date.isoformat(), now, user_id),
            )
    profile = get_user_profile(db_path, user_id)
    assert profile is not None
    return profile


def mark_onboarding_completed(db_path: str | Path, user_id: str, profile_completion_version: int) -> UserProfile:
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE user_profiles SET onboarding_completed_at = ?, profile_completion_version = ?, updated_at = ? "
            "WHERE user_id = ?",
            (now, profile_completion_version, now, user_id),
        )
    profile = get_user_profile(db_path, user_id)
    assert profile is not None
    return profile


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_profile_storage.db"
        user_id = "user-1"
        init_profile_storage(db_path)
        init_profile_storage(db_path)  # idempotent, darf nicht crashen

        assert get_user_profile(db_path, user_id) is None

        profile = upsert_user_profile(db_path, user_id, birth_date=date(1995, 6, 15), gender="", bio="")
        assert profile.birth_date == date(1995, 6, 15)
        assert profile.onboarding_completed_at is None

        # Update ignoriert birth_date, aendert nur gender/bio.
        updated = upsert_user_profile(db_path, user_id, gender="non-binary", bio="Loves techno.")
        assert updated.birth_date == date(1995, 6, 15)
        assert updated.gender == "non-binary"
        assert updated.bio == "Loves techno."

        corrected = apply_birth_date_correction(db_path, user_id, date(1994, 1, 1), reason="Typo bei Signup.")
        assert corrected.birth_date == date(1994, 1, 1)
        assert corrected.gender == "non-binary"  # unveraendert

        completed = mark_onboarding_completed(db_path, user_id, profile_completion_version=1)
        assert completed.onboarding_completed_at is not None
        assert completed.profile_completion_version == 1

        print("accounts/profile_storage.py sanity check OK.")
