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


class UsernameAlreadyTakenError(Exception):
    pass


def init_profile_storage(db_path: str | Path) -> None:
    """Legt ``user_profiles``/``birth_date_corrections`` an, falls nicht
    vorhanden. Idempotent, sicher bei jedem App-Start aufrufbar.

    Migriert zusätzlich ``username`` auf eine bereits existierende
    ``user_profiles``-Tabelle (Social-Graph-Phase-1) - mirrort exakt die
    ``user_migrations``-Technik aus ``accounts/user_storage.py::init_user_storage``.
    SQLite kann per ``ALTER TABLE ADD COLUMN`` keine ``UNIQUE``-Constraint
    anhängen, daher die Eindeutigkeit stattdessen über einen separaten
    partiellen Unique-Index (``WHERE username IS NOT NULL``, damit bestehende
    User ohne Username die Migration klaglos überstehen)."""
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
        existing_profile_cols = {row[1] for row in conn.execute("PRAGMA table_info(user_profiles)")}
        profile_migrations = {
            "username": "ALTER TABLE user_profiles ADD COLUMN username TEXT",
            # Social-Graph-Phase-3: Verhaltens-Policies (siehe UserProfile-Docstring
            # in accounts/domain.py) - SQLite erlaubt eine Konstante als DEFAULT bei
            # ALTER TABLE ADD COLUMN, bestehende Zeilen bekommen sie automatisch,
            # kein Backfill-Script nötig.
            "friend_list_visibility": "ALTER TABLE user_profiles ADD COLUMN friend_list_visibility TEXT NOT NULL DEFAULT 'friends'",
            "friend_request_privacy": "ALTER TABLE user_profiles ADD COLUMN friend_request_privacy TEXT NOT NULL DEFAULT 'everyone'",
            "discoverable_by_username": "ALTER TABLE user_profiles ADD COLUMN discoverable_by_username INTEGER NOT NULL DEFAULT 1",
            "discoverable_by_name": "ALTER TABLE user_profiles ADD COLUMN discoverable_by_name INTEGER NOT NULL DEFAULT 1",
        }
        for column, ddl in profile_migrations.items():
            if column not in existing_profile_cols:
                conn.execute(ddl)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_username "
            "ON user_profiles(username COLLATE NOCASE) WHERE username IS NOT NULL"
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
        username=(row["username"] if "username" in row.keys() else None) or "",
        friend_list_visibility=row["friend_list_visibility"] if "friend_list_visibility" in row.keys() else "friends",
        friend_request_privacy=row["friend_request_privacy"] if "friend_request_privacy" in row.keys() else "everyone",
        discoverable_by_username=(
            bool(row["discoverable_by_username"]) if "discoverable_by_username" in row.keys() else True
        ),
        discoverable_by_name=bool(row["discoverable_by_name"]) if "discoverable_by_name" in row.keys() else True,
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


def is_username_available(db_path: str | Path, username: str) -> bool:
    """Case-insensitiver Verfügbarkeits-Check (Spec §5: 'MaxM'/'maxm'/'MAXM'
    = derselbe Handle) - liest denselben ``COLLATE NOCASE``-Index, den
    ``upsert_user_profile`` zur Durchsetzung nutzt, daher niemals
    inkonsistent mit dem tatsächlichen Insert/Update-Ergebnis."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM user_profiles WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
    return row is None


def upsert_user_profile(
    db_path: str | Path,
    user_id: str,
    *,
    birth_date: date | None = None,
    gender: str | None = None,
    bio: str | None = None,
    username: str | None = None,
    friend_list_visibility: str | None = None,
    friend_request_privacy: str | None = None,
    discoverable_by_username: bool | None = None,
    discoverable_by_name: bool | None = None,
) -> UserProfile:
    """Legt das Profil beim ersten Aufruf an (``birth_date`` dann Pflicht) oder
    aktualisiert ``gender``/``bio``/``username``/die vier Social-Graph-Phase-3-
    Privacy-Felder eines bestehenden Profils. ``birth_date`` wird bei einem
    bereits existierenden Profil IGNORIERT (geschützt - siehe Moduldoku),
    auch wenn hier übergeben - Aufrufer (Router) darf ``birth_date`` auf
    einem Update-Request ohnehin gar nicht erst entgegennehmen.
    ``username=None``/jedes neue Feld ``=None`` bedeutet jeweils "unverändert
    lassen" (gleiche Konvention wie ``gender``/``bio``). Diese eine Funktion
    bedient sowohl ``PATCH /me/profile`` (übergibt nur ``gender``/``bio``/
    ``username``) als auch ``PUT /me/social-privacy`` (übergibt nur die vier
    neuen Felder) - kein zweiter Storage-Pfad nötig. Ein Verstoß gegen den
    ``idx_user_profiles_username``-Unique-Index wirft
    ``UsernameAlreadyTakenError`` statt der rohen ``sqlite3.IntegrityError``
    (mirrort ``EmailAlreadyRegisteredError`` in ``accounts/user_storage.py``)."""
    now = datetime.now().isoformat()
    existing = get_user_profile(db_path, user_id)
    try:
        with sqlite3.connect(db_path) as conn:
            if existing is None:
                if birth_date is None:
                    raise ValueError("birth_date ist beim initialen Anlegen eines Profils Pflicht.")
                conn.execute(
                    """
                    INSERT INTO user_profiles
                        (user_id, birth_date, gender, bio, username, friend_list_visibility,
                         friend_request_privacy, discoverable_by_username, discoverable_by_name,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, birth_date.isoformat(), gender or "", bio or "", username or None,
                        friend_list_visibility or "friends", friend_request_privacy or "everyone",
                        1 if discoverable_by_username is None or discoverable_by_username else 0,
                        1 if discoverable_by_name is None or discoverable_by_name else 0,
                        now, now,
                    ),
                )
            else:
                new_gender = gender if gender is not None else existing.gender
                new_bio = bio if bio is not None else existing.bio
                new_username = username if username is not None else (existing.username or None)
                new_friend_list_visibility = (
                    friend_list_visibility if friend_list_visibility is not None else existing.friend_list_visibility
                )
                new_friend_request_privacy = (
                    friend_request_privacy if friend_request_privacy is not None else existing.friend_request_privacy
                )
                new_discoverable_by_username = (
                    discoverable_by_username if discoverable_by_username is not None else existing.discoverable_by_username
                )
                new_discoverable_by_name = (
                    discoverable_by_name if discoverable_by_name is not None else existing.discoverable_by_name
                )
                conn.execute(
                    """
                    UPDATE user_profiles SET gender = ?, bio = ?, username = ?, friend_list_visibility = ?,
                        friend_request_privacy = ?, discoverable_by_username = ?, discoverable_by_name = ?,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        new_gender, new_bio, new_username, new_friend_list_visibility, new_friend_request_privacy,
                        1 if new_discoverable_by_username else 0, 1 if new_discoverable_by_name else 0,
                        now, user_id,
                    ),
                )
    except sqlite3.IntegrityError as exc:
        raise UsernameAlreadyTakenError(username) from exc
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

        # Username: unset by default, settable, case-insensitiv eindeutig.
        assert completed.username == ""
        assert is_username_available(db_path, "maxm") is True
        with_username = upsert_user_profile(db_path, user_id, username="MaxM")
        assert with_username.username == "MaxM"
        assert is_username_available(db_path, "maxm") is False  # case-insensitiv belegt

        user_id_2 = "user-2"
        upsert_user_profile(db_path, user_id_2, birth_date=date(1990, 1, 1))
        try:
            upsert_user_profile(db_path, user_id_2, username="maxm")
            assert False, "sollte UsernameAlreadyTakenError werfen"
        except UsernameAlreadyTakenError:
            pass

        # username=None auf einem Update laesst den bestehenden Wert unveraendert.
        unchanged = upsert_user_profile(db_path, user_id, gender="non-binary")
        assert unchanged.username == "MaxM"

        # Social-Graph-Phase-3: Privacy-Defaults bei Neuanlage.
        assert with_username.friend_list_visibility == "friends"
        assert with_username.friend_request_privacy == "everyone"
        assert with_username.discoverable_by_username is True
        assert with_username.discoverable_by_name is True

        # Jedes Feld unabhaengig setzbar, uebrige bleiben unveraendert.
        privacy_updated = upsert_user_profile(db_path, user_id, friend_list_visibility="nobody")
        assert privacy_updated.friend_list_visibility == "nobody"
        assert privacy_updated.friend_request_privacy == "everyone"  # unveraendert

        privacy_updated2 = upsert_user_profile(db_path, user_id, discoverable_by_username=False)
        assert privacy_updated2.discoverable_by_username is False
        assert privacy_updated2.discoverable_by_name is True  # unveraendert
        assert privacy_updated2.friend_list_visibility == "nobody"  # unveraendert vom vorigen Aufruf

        # Migrations-Idempotenz: init nochmal aufrufen, bereits gesetzte Werte ueberleben.
        init_profile_storage(db_path)
        survived = get_user_profile(db_path, user_id)
        assert survived.friend_list_visibility == "nobody"
        assert survived.discoverable_by_username is False

        print("accounts/profile_storage.py sanity check OK.")
