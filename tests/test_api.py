from unittest.mock import patch

API_KEY = "test-key"


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_and_get_character(client):
    resp = client.post("/characters", json={"name": "Test", "description": "desc"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test"
    assert data["assets"] == []

    resp2 = client.get(f"/characters/{data['id']}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == data["id"]


def test_get_character_not_found(client):
    resp = client.get("/characters/999999")
    assert resp.status_code == 404


def test_list_characters(client):
    client.post("/characters", json={"name": "A"})
    client.post("/characters", json={"name": "B"})
    resp = client.get("/characters")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "A" in names and "B" in names


def test_delete_character(client):
    resp = client.post("/characters", json={"name": "ToDelete"})
    char_id = resp.json()["id"]
    del_resp = client.delete(f"/characters/{char_id}")
    assert del_resp.status_code == 204
    assert client.get(f"/characters/{char_id}").status_code == 404


def test_delete_character_not_found(client):
    resp = client.delete("/characters/999999")
    assert resp.status_code == 404


def test_character_name_validation(client):
    resp = client.post("/characters", json={"name": ""})
    assert resp.status_code == 422

    resp = client.post("/characters", json={"name": "x" * 200})
    assert resp.status_code == 422


def test_generate_image_requires_api_key(client):
    resp = client.post("/characters", json={"name": "NeedsAuth"})
    char_id = resp.json()["id"]

    no_key = client.post(f"/characters/{char_id}/generate/image", json={"prompt": "a robot"})
    assert no_key.status_code == 401

    wrong_key = client.post(
        f"/characters/{char_id}/generate/image",
        json={"prompt": "a robot"},
        headers={"X-API-Key": "wrong"},
    )
    assert wrong_key.status_code == 401


def test_generate_image_success(client):
    resp = client.post("/characters", json={"name": "ImgChar"})
    char_id = resp.json()["id"]

    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/a.visible.png",
            "original_url": "https://example.com/a.png",
            "sha256": "abc123",
            "mime_type": "image/png",
            "manifest_verified": True,
            "disclosure": "visible",
        }
        resp = client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "a friendly robot", "disclosure": "visible"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "image"
    assert data["url"] == "https://example.com/a.visible.png"
    assert data["disclosure"] == "visible"
    assert data["original_url"] == "https://example.com/a.png"
    mock_gen.assert_called_once_with(char_id, "a friendly robot", "visible", [])

    character = client.get(f"/characters/{char_id}").json()
    assert len(character["assets"]) == 1


def test_generate_image_disclosure_defaults_to_invisible(client):
    resp = client.post("/characters", json={"name": "DefaultDisclosure"})
    char_id = resp.json()["id"]

    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/b.invisible.png",
            "original_url": "https://example.com/b.png",
            "sha256": "def456",
            "mime_type": "image/png",
            "manifest_verified": True,
            "disclosure": "invisible",
        }
        resp = client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "a quiet librarian"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    mock_gen.assert_called_once_with(char_id, "a quiet librarian", "invisible", [])


def test_generate_image_rejects_unknown_disclosure(client):
    resp = client.post("/characters", json={"name": "BadDisclosure"})
    char_id = resp.json()["id"]

    resp = client.post(
        f"/characters/{char_id}/generate/image",
        json={"prompt": "a robot", "disclosure": "sneaky"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 422


def test_generate_image_prompt_validation(client):
    resp = client.post("/characters", json={"name": "ValidateChar"})
    char_id = resp.json()["id"]

    resp = client.post(
        f"/characters/{char_id}/generate/image",
        json={"prompt": ""},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 422


def test_generate_image_provider_failure_returns_clean_502(client):
    resp = client.post("/characters", json={"name": "FailChar"})
    char_id = resp.json()["id"]

    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.side_effect = RuntimeError("upstream exploded with secret header dump")
        resp = client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "a robot"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 502
    assert "secret header dump" not in resp.text


def test_generate_image_uses_identity_references(client):
    resp = client.post("/characters", json={"name": "IdentityChar"})
    char_id = resp.json()["id"]

    mock_result = {
        "url": "https://example.com/ref.invisible.png",
        "original_url": "https://example.com/ref.png",
        "sha256": "ref111",
        "mime_type": "image/png",
        "manifest_verified": True,
        "disclosure": "invisible",
    }
    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.return_value = mock_result
        # first portrait: no references exist yet
        client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "first portrait"},
            headers={"X-API-Key": API_KEY},
        )
        assert mock_gen.call_args.args[3] == []

        # second portrait: the first one is passed as identity reference (original url)
        client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "second portrait"},
            headers={"X-API-Key": API_KEY},
        )
        assert mock_gen.call_args.args[3] == ["https://example.com/ref.png"]

        # use_identity=false skips references entirely
        client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "free portrait", "use_identity": False},
            headers={"X-API-Key": API_KEY},
        )
        assert mock_gen.call_args.args[3] == []


def test_delete_asset(client):
    resp = client.post("/characters", json={"name": "AssetDeleteChar"})
    char_id = resp.json()["id"]

    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/c.png",
            "original_url": "https://example.com/c-orig.png",
            "sha256": "ghi789",
            "mime_type": "image/png",
            "manifest_verified": True,
            "disclosure": "invisible",
        }
        asset = client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "a robot"},
            headers={"X-API-Key": API_KEY},
        ).json()

    del_resp = client.delete(f"/assets/{asset['id']}")
    assert del_resp.status_code == 204
    character = client.get(f"/characters/{char_id}").json()
    assert character["assets"] == []

    assert client.delete(f"/assets/{asset['id']}").status_code == 404


def test_list_assets_by_kind(client):
    resp = client.post("/characters", json={"name": "AssetChar"})
    char_id = resp.json()["id"]

    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/b.png",
            "sha256": "def456",
            "mime_type": "image/png",
            "manifest_verified": True,
        }
        client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "a robot"},
            headers={"X-API-Key": API_KEY},
        )

    resp = client.get("/assets?kind=image")
    assert resp.status_code == 200
    assert any(a["character_id"] == char_id for a in resp.json())

    resp = client.get("/assets?kind=voice")
    assert all(a["kind"] == "voice" for a in resp.json())
