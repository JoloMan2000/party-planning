"""API-Tests für POST /me/profile-image (Account-basierter Pivot, Phase 5,
Teil D - lokales Disk-Storage, kein Cloud-Storage)."""

from __future__ import annotations

import io

from PIL import Image


def _make_image_bytes(fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(buf, format=fmt)
    return buf.getvalue()


def test_upload_profile_image_setzt_profile_image_pfad(api_client, auth_headers_factory):
    headers, user, _refresh_token = auth_headers_factory(email="avatar@example.com")
    files = {"file": ("avatar.png", _make_image_bytes("PNG"), "image/png")}
    resp = api_client.post("/api/v1/me/profile-image", headers=headers, files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == user["id"]
    assert body["profile_image"] == f"profile_images/{user['id']}.jpg"

    # bild ist tatsächlich unter dem festen serverseitigen Dateinamen gelandet
    media_dir = api_client.db_path.parent / "media" / "profile_images"
    saved_file = media_dir / f"{user['id']}.jpg"
    assert saved_file.exists()

    # GET /me spiegelt den neuen Pfad wider
    resp = api_client.get("/api/v1/me", headers=headers)
    assert resp.json()["profile_image"] == f"profile_images/{user['id']}.jpg"


def test_upload_profile_image_akzeptiert_jpeg_und_re_encoded_als_jpeg(api_client, auth_headers_factory):
    headers, user, _ = auth_headers_factory(email="avatar-jpeg@example.com")
    files = {"file": ("avatar.jpg", _make_image_bytes("JPEG"), "image/jpeg")}
    resp = api_client.post("/api/v1/me/profile-image", headers=headers, files=files)
    assert resp.status_code == 200, resp.text


def test_upload_profile_image_lehnt_nicht_bild_datei_ab(api_client, auth_headers_factory):
    headers, _user, _ = auth_headers_factory(email="avatar-bad@example.com")
    files = {"file": ("not-an-image.txt", b"this is definitely not an image", "text/plain")}
    resp = api_client.post("/api/v1/me/profile-image", headers=headers, files=files)
    assert resp.status_code == 400


def test_upload_profile_image_lehnt_als_bild_getarnte_datei_ab(api_client, auth_headers_factory):
    """Ein Content-Type von `image/png` allein darf nicht genügen - Pillow
    muss die Bytes tatsächlich dekodieren können (Payload ist hier reiner
    Text, nur der Content-Type täuscht ein Bild vor)."""
    headers, _user, _ = auth_headers_factory(email="avatar-disguised@example.com")
    files = {"file": ("fake.png", b"not actually png data", "image/png")}
    resp = api_client.post("/api/v1/me/profile-image", headers=headers, files=files)
    assert resp.status_code == 400


def test_upload_profile_image_ohne_token_gibt_401(api_client):
    files = {"file": ("avatar.png", _make_image_bytes("PNG"), "image/png")}
    resp = api_client.post("/api/v1/me/profile-image", files=files)
    assert resp.status_code == 401
