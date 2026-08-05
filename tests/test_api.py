import time
from unittest.mock import patch

API_KEY = "test-key"


def _fake_portrait(tag="x"):
    return {
        "url": f"https://example.com/{tag}.png",
        "original_url": f"https://example.com/{tag}.png",
        "sha256": tag, "mime_type": "image/png", "manifest_verified": True,
        "disclosure": "invisible", "quality": "draft", "cost_usd": 0.006,
        "model": "gpt-image-2",
    }


def _await_batch(client, batch_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/batches/{batch_id}").json()
        if job["status"] in ("done", "error", "cancelled"):
            return job
        time.sleep(0.02)
    return client.get(f"/batches/{batch_id}").json()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── Multitenancy ─────────────────────────────────────────────────────────

def test_requests_without_workspace_are_rejected():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as bare:
        assert bare.get("/characters").status_code == 401
        assert bare.post("/characters", json={"name": "X"}).status_code == 401
        # unknown workspace token is also rejected
        assert bare.get("/characters", headers={"X-Workspace-Id": "nope"}).status_code == 401


def test_workspace_create_and_validate(client):
    ws = client.post("/workspaces", json={"name": "My Space"}).json()
    assert ws["id"] and ws["name"] == "My Space"
    # the current-workspace check echoes the caller's own workspace
    current = client.get("/workspaces/current")
    assert current.status_code == 200
    assert current.json()["id"] == client.workspace_id


def test_characters_are_isolated_between_workspaces(client, other_client):
    mine = client.post("/characters", json={"name": "Mine"}).json()
    # the other tenant sees none of my characters
    assert other_client.get("/characters").json() == []
    assert any(c["id"] == mine["id"] for c in client.get("/characters").json())
    # cannot fetch, edit or delete across the tenant boundary, even with the id
    assert other_client.get(f"/characters/{mine['id']}").status_code == 404
    assert other_client.patch(f"/characters/{mine['id']}", json={"name": "Hijack"}).status_code == 404
    assert other_client.delete(f"/characters/{mine['id']}").status_code == 404
    # mine is untouched
    assert client.get(f"/characters/{mine['id']}").json()["name"] == "Mine"


def test_studio_and_audio_isolated(client, other_client):
    with patch("app.main.generate_studio_image", return_value={
        "url": "https://example.com/s.png", "original_url": "https://example.com/s.png",
        "sha256": "s", "mime_type": "image/png", "manifest_verified": True,
        "disclosure": "invisible", "quality": "draft", "cost_usd": 0.006,
        "model": "gpt-image-2", "kind": "photo-art",
    }):
        img = client.post("/studio", json={"kind": "photo-art", "prompt": "x"},
                          headers={"X-API-Key": API_KEY}).json()
    assert other_client.get("/studio").json() == []
    assert any(s["id"] == img["id"] for s in client.get("/studio").json())
    assert other_client.delete(f"/studio/{img['id']}").status_code == 404


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


def test_delete_character_with_batch_job(client):
    """A character that has ever been batched must still be deletable.

    batch_jobs holds a NOT NULL foreign key onto characters and foreign keys are
    enforced, so leaving its rows behind turned the DELETE into a 500 and left
    the character stuck in the workspace for good."""
    from app import db

    char_id = client.post("/characters", json={"name": "Batched"}).json()["id"]
    db.create_batch(
        workspace_id=client.workspace_id,
        character_id=char_id,
        mode="photo-art",
        prompt="four portraits",
        requested=4,
        quality="draft",
        model="gpt-image-2",
        disclosure="invisible",
        cost_estimate=0.044,
    )

    assert client.delete(f"/characters/{char_id}").status_code == 204
    assert client.get(f"/characters/{char_id}").status_code == 404


def test_delete_character_clears_video_reference(client):
    """videos.character_id has no foreign key, so it never blocked the delete —
    it would just dangle. The clip keeps its character_name and stays listed."""
    from app import db

    char_id = client.post("/characters", json={"name": "Filmed"}).json()["id"]
    video = db.create_video(
        workspace_id=client.workspace_id,
        character_id=char_id,
        character_name="Filmed",
        kind="image2video",
        prompt="a slow zoom",
        model="Kling-Image2Video-V2.1-Master",
        duration=5,
        aspect_ratio="16:9",
    )

    assert client.delete(f"/characters/{char_id}").status_code == 204
    assert db.get_video(client.workspace_id, video["id"])["character_id"] is None


def test_delete_character_not_found(client):
    resp = client.delete("/characters/999999")
    assert resp.status_code == 404


def test_character_name_validation(client):
    resp = client.post("/characters", json={"name": ""})
    assert resp.status_code == 422

    resp = client.post("/characters", json={"name": "x" * 200})
    assert resp.status_code == 422


def test_keyless_generation_rate_limited_and_owner_bypass(client):
    from app.main import rate_limiter
    import app.main as m
    rate_limiter.reset()
    char_id = client.post("/characters", json={"name": "Keyless"}).json()["id"]

    with patch("app.main.generate_character_portrait", return_value=_fake_portrait("k")):
        # keyless works (no X-API-Key) up to the per-IP hourly cap...
        with patch.object(m, "RATE_IP_PER_HOUR", 2):
            a = client.post(f"/characters/{char_id}/generate/image", json={"prompt": "x"})
            b = client.post(f"/characters/{char_id}/generate/image", json={"prompt": "y"})
            c = client.post(f"/characters/{char_id}/generate/image", json={"prompt": "z"})
            assert a.status_code == 200 and b.status_code == 200
            assert c.status_code == 429  # limit reached
            # the owner key bypasses the limit
            owner = client.post(f"/characters/{char_id}/generate/image",
                                json={"prompt": "w"}, headers={"X-API-Key": API_KEY})
            assert owner.status_code == 200
    rate_limiter.reset()


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
    mock_gen.assert_called_once_with(char_id, "a friendly robot", "visible", [], "draft", "gpt-image-2", None, None)

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
    mock_gen.assert_called_once_with(char_id, "a quiet librarian", "invisible", [], "draft", "gpt-image-2", None, None)


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


def test_generate_image_quality_and_cost_persisted(client):
    resp = client.post("/characters", json={"name": "CostChar"})
    char_id = resp.json()["id"]

    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/d.png",
            "original_url": "https://example.com/d-orig.png",
            "sha256": "cost1",
            "mime_type": "image/png",
            "manifest_verified": True,
            "disclosure": "invisible",
            "quality": "final",
            "cost_usd": 0.211,
        }
        resp = client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "a portrait", "quality": "final"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["quality"] == "final"
    assert data["cost_usd"] == 0.211
    assert mock_gen.call_args.args[4] == "final"


def test_capabilities_lists_available_models(client):
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    slugs = {m["slug"] for m in resp.json()["image_models"]}
    # gpt-image-2 is always available; GMI models only if GMI_API_KEY is set
    assert "gpt-image-2" in slugs


def test_generate_image_rejects_unavailable_model(client):
    resp = client.post("/characters", json={"name": "ModelChar"})
    char_id = resp.json()["id"]
    resp = client.post(
        f"/characters/{char_id}/generate/image",
        json={"prompt": "a robot", "model": "flux-kontext-pro"},
        headers={"X-API-Key": API_KEY},
    )
    # GMI_API_KEY not set in tests → model unavailable → 400
    assert resp.status_code == 400


def test_generate_image_rejects_unknown_quality(client):
    resp = client.post("/characters", json={"name": "BadQuality"})
    char_id = resp.json()["id"]

    resp = client.post(
        f"/characters/{char_id}/generate/image",
        json={"prompt": "a robot", "quality": "ultra"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 422


def test_generation_slot_rejects_concurrent_duplicate(client):
    from app.main import generation_slot
    from fastapi import HTTPException
    import pytest

    with generation_slot(42, "image"):
        with pytest.raises(HTTPException) as excinfo:
            with generation_slot(42, "image"):
                pass
        assert excinfo.value.status_code == 409
        # a different character is unaffected
        with generation_slot(43, "image"):
            pass
    # slot is released afterwards
    with generation_slot(42, "image"):
        pass


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

        # second portrait: the first one is passed as identity reference (original url + sha)
        client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "second portrait"},
            headers={"X-API-Key": API_KEY},
        )
        assert mock_gen.call_args.args[3] == [
            {"url": "https://example.com/ref.png", "sha256": "ref111"}
        ]

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


def test_voices_lists_openai(client):
    resp = client.get("/voices")
    assert resp.status_code == 200
    body = resp.json()
    assert "openai" in body
    ids = {v["id"] for v in body["openai"]}
    assert {"onyx", "nova", "shimmer"} <= ids


def test_assign_and_use_character_voice(client):
    char_id = client.post("/characters", json={"name": "VoiceChar"}).json()["id"]

    assign = client.put(
        f"/characters/{char_id}/voice",
        json={"voice_provider": "openai", "voice_id": "nova"},
    )
    assert assign.status_code == 200
    assert assign.json()["voice_provider"] == "openai"
    assert assign.json()["voice_id"] == "nova"

    with patch("app.main.generate_character_voice_line") as mock_voice:
        mock_voice.return_value = {
            "url": "https://example.com/v.mp3",
            "sha256": "voice1",
            "mime_type": "audio/mpeg",
            "manifest_verified": True,
            "cost_usd": 0.0006,
            "voice": "openai:nova",
        }
        resp = client.post(
            f"/characters/{char_id}/generate/voice",
            json={"text": "hello there"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    assert resp.json()["model"] == "openai:nova"
    # the character's assigned voice is passed through to the pipeline
    mock_voice.assert_called_once_with(char_id, "hello there", "openai", "nova")


def test_create_character_with_profile_fields(client):
    resp = client.post("/characters", json={
        "name": "Aria", "description": "hero",
        "personality": "strong, confident, charismatic",
        "purpose": "marketing campaigns", "seed": 4242,
    })
    assert resp.status_code == 200
    c = resp.json()
    assert c["personality"] == "strong, confident, charismatic"
    assert c["purpose"] == "marketing campaigns"
    assert c["seed"] == 4242


def test_update_character_profile(client):
    cid = client.post("/characters", json={"name": "Edit Me"}).json()["id"]
    resp = client.patch(f"/characters/{cid}", json={"personality": "shy and reserved", "seed": 7})
    assert resp.status_code == 200
    assert resp.json()["personality"] == "shy and reserved"
    assert resp.json()["seed"] == 7
    # unchanged fields stay
    assert resp.json()["name"] == "Edit Me"


def test_personality_and_seed_flow_into_generation(client):
    cid = client.post("/characters", json={
        "name": "Vivid", "personality": "playful and bold", "seed": 99,
    }).json()["id"]
    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/v.png", "original_url": "https://example.com/v.png",
            "sha256": "s", "mime_type": "image/png", "manifest_verified": True,
            "disclosure": "invisible", "quality": "draft", "cost_usd": 0.006, "model": "gpt-image-2",
        }
        client.post(f"/characters/{cid}/generate/image",
                    json={"prompt": "a portrait"}, headers={"X-API-Key": API_KEY})
    # personality + seed are passed through (positions 7 and 8)
    assert mock_gen.call_args.args[6] == "playful and bold"
    assert mock_gen.call_args.args[7] == 99


def test_scene_requires_two_characters_with_portraits(client):
    c1 = client.post("/characters", json={"name": "Solo"}).json()["id"]
    # only one participant → 422 (min_length=2)
    resp = client.post(
        "/scenes",
        json={"character_ids": [c1], "prompt": "together"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 422


def test_scene_generation_stores_participants(client):
    a = client.post("/characters", json={"name": "Aoi"}).json()["id"]
    b = client.post("/characters", json={"name": "Ren"}).json()["id"]

    # give each a portrait so scene_reference finds an anchor
    with patch("app.main.generate_character_portrait") as mock_gen:
        for cid in (a, b):
            mock_gen.return_value = {
                "url": f"https://s3.eu-central-003.backblazeb2.com/{__import__('app.config', fromlist=['B2_BUCKET_NAME']).B2_BUCKET_NAME}/x{cid}.png",
                "original_url": f"https://s3.eu-central-003.backblazeb2.com/{__import__('app.config', fromlist=['B2_BUCKET_NAME']).B2_BUCKET_NAME}/x{cid}.png",
                "sha256": f"sha{cid}", "mime_type": "image/png",
                "manifest_verified": True, "disclosure": "invisible",
                "quality": "draft", "cost_usd": 0.006, "model": "gpt-image-2",
            }
            client.post(f"/characters/{cid}/generate/image",
                        json={"prompt": "p"}, headers={"X-API-Key": API_KEY})

    with patch("app.main.generate_scene") as mock_scene, \
         patch("app.main.available_image_models", return_value=[{"slug": "gemini-2.5-flash-image"}]):
        mock_scene.return_value = {
            "url": "https://example.com/scene.png",
            "original_url": "https://example.com/scene-orig.png",
            "sha256": "scenesha", "manifest_verified": True,
            "disclosure": "invisible", "cost_usd": 0.039, "model": "gemini-2.5-flash-image",
        }
        resp = client.post(
            "/scenes",
            json={"character_ids": [a, b], "prompt": "the two of them in a classroom"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    scene = resp.json()
    assert scene["participant_ids"] == [a, b]
    assert scene["participant_names"] == ["Aoi", "Ren"]
    # references passed = one anchor per character
    passed_refs = mock_scene.call_args.args[1]
    assert len(passed_refs) == 2

    assert any(s["id"] == scene["id"] for s in client.get("/scenes").json())


def test_dialogue_requires_two_distinct_characters(client):
    a = client.post("/characters", json={
        "name": "Solo", "voice_provider": "openai", "voice_id": "nova",
    }).json()["id"]
    # both turns are the same speaker → only one distinct character
    resp = client.post(
        "/audio/dialogue",
        json={"turns": [{"character_id": a, "text": "hi"}, {"character_id": a, "text": "hi again"}]},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 400


def test_dialogue_requires_voice_on_each_character(client):
    a = client.post("/characters", json={
        "name": "HasVoice", "voice_provider": "openai", "voice_id": "nova",
    }).json()["id"]
    b = client.post("/characters", json={"name": "NoVoice"}).json()["id"]
    resp = client.post(
        "/audio/dialogue",
        json={"turns": [{"character_id": a, "text": "hi"}, {"character_id": b, "text": "hi back"}]},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 400


def test_dialogue_generation_stores_script_and_participants(client, monkeypatch):
    monkeypatch.setattr("app.pipelines.GMI_API_KEY", "test-gmi-key")
    a = client.post("/characters", json={
        "name": "Kaede", "voice_provider": "gmi", "voice_id": "Hana",
    }).json()["id"]
    b = client.post("/characters", json={
        "name": "Ren", "voice_provider": "openai", "voice_id": "nova",
    }).json()["id"]

    with patch("app.main.generate_dialogue_audio") as mock_dlg:
        mock_dlg.return_value = {
            "url": "https://example.com/dialogue.mp3", "sha256": "dlgsha",
            "mime_type": "audio/mpeg", "manifest_verified": True, "cost_usd": 0.002,
            "script": [
                {"character_id": a, "character_name": "Kaede", "text": "Hey Ren!"},
                {"character_id": b, "character_name": "Ren", "text": "Hey Kaede."},
                {"character_id": a, "character_name": "Kaede", "text": "How's it going?"},
            ],
        }
        resp = client.post(
            "/audio/dialogue",
            json={"turns": [
                {"character_id": a, "text": "Hey Ren!"},
                {"character_id": b, "text": "Hey Kaede."},
                {"character_id": a, "text": "How's it going?"},
            ]},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    dialogue = resp.json()
    # participant order = first appearance, deduped (Kaede speaks twice)
    assert dialogue["participant_ids"] == [a, b]
    assert dialogue["participant_names"] == ["Kaede", "Ren"]
    assert len(dialogue["script"]) == 3
    passed_turns = mock_dlg.call_args.args[0]
    assert len(passed_turns) == 3
    assert passed_turns[0]["voice_provider"] == "gmi" and passed_turns[0]["voice_id"] == "Hana"

    assert any(d["id"] == dialogue["id"] for d in client.get("/audio/dialogue").json())
    assert client.delete(f"/audio/dialogue/{dialogue['id']}").status_code == 204
    assert client.delete(f"/audio/dialogue/{dialogue['id']}").status_code == 404


def test_motion_comic_requires_voice_on_character(client):
    from app import db

    scene = db.create_scene(
        workspace_id=client.workspace_id, prompt="p", url="https://example.com/s.png",
        original_url="https://example.com/s.png", sha256="s", model="gemini-2.5-flash-image",
        disclosure="invisible", cost_usd=0.039, manifest_verified=True,
        participant_ids=[1, 2], participant_names=["A", "B"],
    )
    no_voice = client.post("/characters", json={"name": "Mute"}).json()["id"]
    resp = client.post(
        "/videos/motion-comic",
        json={"panels": [
            {"scene_id": scene["id"], "character_id": no_voice, "text": "hi"},
            {"scene_id": scene["id"], "character_id": no_voice, "text": "hi again"},
        ]},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 400


def test_motion_comic_generation_stores_script_and_duration(client, monkeypatch):
    from app import db

    monkeypatch.setattr("app.pipelines.GMI_API_KEY", "test-gmi-key")

    scene = db.create_scene(
        workspace_id=client.workspace_id, prompt="p", url="https://example.com/s.png",
        original_url="https://example.com/s.png", sha256="s", model="gemini-2.5-flash-image",
        disclosure="invisible", cost_usd=0.039, manifest_verified=True,
        participant_ids=[1, 2], participant_names=["A", "B"],
    )
    a = client.post("/characters", json={
        "name": "Kaede", "voice_provider": "gmi", "voice_id": "Hana",
    }).json()["id"]
    b = client.post("/characters", json={
        "name": "Ren", "voice_provider": "openai", "voice_id": "nova",
    }).json()["id"]

    with patch("app.main.generate_motion_comic") as mock_mc:
        mock_mc.return_value = {
            "url": "https://example.com/comic.mp4", "sha256": "mcsha",
            "mime_type": "video/mp4", "manifest_verified": True, "cost_usd": 0.001,
            "duration": 7.4,
            "script": [
                {"character_id": a, "character_name": "Kaede", "text": "Hey Ren!"},
                {"character_id": b, "character_name": "Ren", "text": "Hey Kaede."},
            ],
        }
        resp = client.post(
            "/videos/motion-comic",
            json={"panels": [
                {"scene_id": scene["id"], "character_id": a, "text": "Hey Ren!", "caption": "Visit us today!"},
                {"scene_id": scene["id"], "character_id": b, "text": "Hey Kaede."},
            ], "music_url": "https://example.com/music.mp3"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    video = resp.json()
    assert video["status"] == "done"
    assert video["duration"] == 7
    assert video["script"] == mock_mc.return_value["script"]
    passed_panels = mock_mc.call_args.args[0]
    assert len(passed_panels) == 2
    assert passed_panels[0]["voice_provider"] == "gmi" and passed_panels[0]["voice_id"] == "Hana"
    assert passed_panels[0]["caption"] == "Visit us today!"
    assert passed_panels[1]["caption"] is None
    assert mock_mc.call_args.kwargs["music_url"] == "https://example.com/music.mp3"

    assert any(v["id"] == video["id"] for v in client.get("/videos").json())
    assert client.delete(f"/videos/{video['id']}").status_code == 204


def test_upload_music_rejects_bad_type(client):
    resp = client.post(
        "/uploads/music",
        files={"file": ("song.txt", b"not audio", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_music_stores_and_returns_url(client):
    with patch("app.main.upload_bytes", return_value=("https://example.com/uploads/music/x.mp3", "sha")) as mock_up:
        resp = client.post(
            "/uploads/music",
            files={"file": ("song.mp3", b"fake mp3 bytes", "audio/mpeg")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == "https://example.com/uploads/music/x.mp3"
    assert body["sha256"] == "sha"
    assert mock_up.call_args.args[0].endswith(".mp3")


def test_build_batch_prompts_strategies():
    from app.pipelines import build_batch_prompts

    assert build_batch_prompts("single", "a knight", 5) == ["a knight"]

    variation = build_batch_prompts("variation", "a knight", 4)
    assert len(variation) == 4
    assert all(p.startswith("a knight. Variation") for p in variation)
    assert len(set(variation)) == 4  # each frame genuinely differs

    shoot = build_batch_prompts("photoshoot", "a knight", 3)
    assert len(shoot) == 3
    assert all("keep the EXACT same outfit" in p for p in shoot)

    story = build_batch_prompts("story", "She wakes.\nShe leaves.\nShe returns.", 60)
    assert len(story) == 3
    assert "She wakes." in story[0]


def test_batch_variation_generates_all_frames(client):
    cid = client.post("/characters", json={"name": "BatchChar"}).json()["id"]
    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.side_effect = lambda *a, **k: _fake_portrait("f")
        resp = client.post(
            f"/characters/{cid}/generate/batch",
            json={"mode": "variation", "prompt": "a knight", "count": 3},
            headers={"X-API-Key": API_KEY},
        )
        assert resp.status_code == 200
        job = resp.json()
        assert job["status"] == "running"
        assert job["requested"] == 3
        assert job["cost_estimate"] is not None
        job = _await_batch(client, job["id"])
    assert job["status"] == "done"
    assert job["completed"] == 3

    character = client.get(f"/characters/{cid}").json()
    imgs = [a for a in character["assets"] if a["kind"] == "image"]
    assert len(imgs) == 3
    assert all(a["batch_id"] == job["id"] for a in imgs)


def test_batch_story_derives_count_from_script(client):
    cid = client.post("/characters", json={"name": "StoryChar"}).json()["id"]
    with patch("app.main.generate_character_portrait") as mock_gen:
        mock_gen.side_effect = lambda *a, **k: _fake_portrait("s")
        resp = client.post(
            f"/characters/{cid}/generate/batch",
            json={"mode": "story", "prompt": "Beat one.\nBeat two.\nBeat three.\nBeat four.", "count": 1},
            headers={"X-API-Key": API_KEY},
        )
        job = resp.json()
        assert job["requested"] == 4  # one frame per beat, not the count field
        job = _await_batch(client, job["id"])
    assert job["status"] == "done"
    assert job["completed"] == 4


def test_batch_keyless_allowed(client):
    from app.main import rate_limiter
    rate_limiter.reset()
    cid = client.post("/characters", json={"name": "NoKeyBatch"}).json()["id"]
    with patch("app.main.generate_character_portrait", return_value=_fake_portrait("b")):
        resp = client.post(
            f"/characters/{cid}/generate/batch",
            json={"mode": "variation", "prompt": "a knight", "count": 2},
        )
    assert resp.status_code == 200  # no key needed anymore
    _await_batch(client, resp.json()["id"])
    rate_limiter.reset()

def test_batch_rejects_bad_count(client):
    cid = client.post("/characters", json={"name": "BadCount"}).json()["id"]
    resp = client.post(
        f"/characters/{cid}/generate/batch",
        json={"mode": "variation", "prompt": "a knight", "count": 500},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 422


def test_batch_records_partial_failure(client):
    cid = client.post("/characters", json={"name": "PartialFail"}).json()["id"]
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("provider hiccup")
        return _fake_portrait("p")

    with patch("app.main.generate_character_portrait", side_effect=flaky):
        resp = client.post(
            f"/characters/{cid}/generate/batch",
            json={"mode": "variation", "prompt": "a knight", "count": 3},
            headers={"X-API-Key": API_KEY},
        )
        job = _await_batch(client, resp.json()["id"])
    assert job["status"] == "done"  # partial success still completes
    assert job["completed"] == 2
    assert job["failed"] == 1


def test_studio_generation_and_listing(client):
    with patch("app.main.generate_studio_image") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/art.png",
            "original_url": "https://example.com/art.png",
            "sha256": "artsha", "mime_type": "image/png", "manifest_verified": True,
            "disclosure": "invisible", "quality": "draft", "cost_usd": 0.006,
            "model": "gpt-image-2", "kind": "photo-art",
        }
        resp = client.post(
            "/studio",
            json={"kind": "photo-art", "prompt": "a surreal floating island"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    img = resp.json()
    assert img["kind"] == "photo-art"
    assert img["prompt"] == "a surreal floating island"
    # mode + prompt reach the pipeline
    assert mock_gen.call_args.args[0] == "a surreal floating island"
    assert mock_gen.call_args.args[1] == "photo-art"

    listed = client.get("/studio?kind=photo-art").json()
    assert any(s["id"] == img["id"] for s in listed)

    assert client.delete(f"/studio/{img['id']}").status_code == 204
    assert client.delete(f"/studio/{img['id']}").status_code == 404


def test_studio_keyless_allowed(client):
    from app.main import rate_limiter
    rate_limiter.reset()
    with patch("app.main.generate_studio_image", return_value={
        "url": "https://example.com/s.png", "original_url": "https://example.com/s.png",
        "sha256": "s", "mime_type": "image/png", "manifest_verified": True,
        "disclosure": "invisible", "quality": "draft", "cost_usd": 0.006,
        "model": "gpt-image-2", "kind": "background",
    }):
        resp = client.post("/studio", json={"kind": "background", "prompt": "a forest"})
    assert resp.status_code == 200
    rate_limiter.reset()

def test_studio_rejects_unknown_kind(client):
    resp = client.post(
        "/studio",
        json={"kind": "hologram", "prompt": "a forest"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 422


def test_studio_background_mode_prepends_no_people(client):
    from app.pipelines import STUDIO_MODES
    assert "no people" in STUDIO_MODES["background"]
    assert STUDIO_MODES["photo-art"] == ""


def _tiny_png_data_url():
    import base64
    import io
    from PIL import Image

    img = Image.new("RGB", (10, 10), color=(200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_canvas_export_stores_studio_asset(client):
    with patch("app.main.upload_bytes", return_value=("https://example.com/canvas/x.png", "sha")) as mock_up:
        resp = client.post(
            "/canvas/export",
            json={"image_base64": _tiny_png_data_url(), "visible_badge": False},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "canvas"
    assert body["manifest_verified"] == 0
    assert body["cost_usd"] == 0.0
    assert body["disclosure"] is None
    assert body["model"] == "canvas-editor"
    assert mock_up.call_args.args[0].startswith("canvas/")
    assert mock_up.call_args.args[2] == "image/png"

    assert any(a["id"] == body["id"] for a in client.get("/studio").json())


def test_canvas_export_with_visible_badge_sets_disclosure(client):
    with patch("app.main.upload_bytes", return_value=("https://example.com/canvas/y.png", "sha2")):
        resp = client.post(
            "/canvas/export",
            json={"image_base64": _tiny_png_data_url(), "visible_badge": True},
        )
    assert resp.status_code == 200
    assert resp.json()["disclosure"] == "visible"


def test_canvas_export_rejects_bad_base64(client):
    resp = client.post(
        "/canvas/export",
        json={"image_base64": "data:image/png;base64,not-valid-base64!!!", "visible_badge": False},
    )
    assert resp.status_code == 400


def test_canvas_export_rejects_non_data_url(client):
    resp = client.post(
        "/canvas/export",
        json={"image_base64": "https://example.com/not-a-data-url.png", "visible_badge": False},
    )
    assert resp.status_code == 400


def test_canvas_export_isolated_between_workspaces(client, other_client):
    with patch("app.main.upload_bytes", return_value=("https://example.com/canvas/z.png", "sha3")):
        client.post("/canvas/export", json={"image_base64": _tiny_png_data_url(), "visible_badge": False})
    assert other_client.get("/studio").json() == []


def test_assets_proxy_rejects_non_bucket_url(client):
    resp = client.get("/assets/proxy", params={"url": "https://evil.example.com/x.png"})
    assert resp.status_code == 400


def test_canvas_template_crud(client):
    resp = client.post(
        "/canvas/templates",
        json={"name": "Manga page 1", "category": "manga-page", "layout_json": '{"objects":[]}'},
    )
    assert resp.status_code == 200
    template = resp.json()
    assert template["name"] == "Manga page 1"
    assert template["category"] == "manga-page"
    assert "layout_json" in template
    assert template["signed_thumbnail_url"] is None

    listed = client.get("/canvas/templates").json()
    assert any(t["id"] == template["id"] for t in listed)
    # the list view is thumbnail-only — no layout_json, to keep it light
    assert "layout_json" not in listed[0]

    fetched = client.get(f"/canvas/templates/{template['id']}").json()
    assert fetched["layout_json"] == '{"objects":[]}'

    updated = client.put(
        f"/canvas/templates/{template['id']}",
        json={"name": "Manga page 1 v2", "category": "manga-page", "layout_json": '{"objects":[1]}'},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Manga page 1 v2"
    assert updated.json()["layout_json"] == '{"objects":[1]}'

    assert client.delete(f"/canvas/templates/{template['id']}").status_code == 204
    assert client.get(f"/canvas/templates/{template['id']}").status_code == 404
    assert client.delete(f"/canvas/templates/{template['id']}").status_code == 404


def test_canvas_template_with_thumbnail(client):
    with patch("app.main.upload_bytes", return_value=("https://example.com/canvas/thumbs/x.png", "shathumb")) as mock_up:
        resp = client.post(
            "/canvas/templates",
            json={
                "name": "With thumb", "category": None,
                "layout_json": '{"objects":[]}', "thumbnail_base64": _tiny_png_data_url(),
            },
        )
    assert resp.status_code == 200
    assert resp.json()["thumbnail_url"] == "https://example.com/canvas/thumbs/x.png"
    assert mock_up.call_args.args[0].startswith("canvas/thumbnails/")


def test_canvas_template_update_not_found(client):
    resp = client.put(
        "/canvas/templates/999999",
        json={"name": "x", "category": None, "layout_json": "{}"},
    )
    assert resp.status_code == 404


def test_canvas_templates_isolated_between_workspaces(client, other_client):
    client.post(
        "/canvas/templates",
        json={"name": "Mine", "category": None, "layout_json": "{}"},
    )
    assert other_client.get("/canvas/templates").json() == []


def _done_video(workspace_id):
    from app import db

    video = db.create_video(
        workspace_id=workspace_id, character_id=None, character_name="Mara",
        kind="character", prompt="a windswept portrait", model="Veo3-Fast",
        duration=5, aspect_ratio="16:9",
    )
    db.finish_video(
        video["id"], status="done", url="https://example.com/v.mp4",
        original_url="https://example.com/v.mp4", sha256="vsha",
        mime_type="video/mp4", cost_usd=0.2, manifest_verified=True,
    )
    return video["id"]


def test_video_poster_returns_frame_and_dimensions(client):
    video_id = _done_video(client.workspace_id)
    with patch("app.main.extract_poster_frame") as mock_poster, \
         patch("app.main.presign_asset_url", return_value="https://signed.example.com/p.png"):
        mock_poster.return_value = {
            "url": "https://example.com/p.png", "sha256": "psha",
            "width": 1280, "height": 720,
        }
        resp = client.get(f"/videos/{video_id}/poster")
    assert resp.status_code == 200
    body = resp.json()
    assert body["width"] == 1280 and body["height"] == 720
    assert body["signed_url"] == "https://signed.example.com/p.png"
    mock_poster.assert_called_once_with("https://example.com/v.mp4")


def test_video_poster_unfinished_video_rejected(client):
    from app import db

    video = db.create_video(
        workspace_id=client.workspace_id, character_id=None, character_name=None,
        kind="text", prompt="still running", model="Veo3-Fast", duration=5, aspect_ratio="16:9",
    )
    assert client.get(f"/videos/{video['id']}/poster").status_code == 400
    assert client.get("/videos/999999/poster").status_code == 404


def test_video_overlay_creates_new_video_row(client):
    video_id = _done_video(client.workspace_id)
    with patch("app.main.overlay_video") as mock_overlay:
        mock_overlay.return_value = {
            "url": "https://example.com/ov.mp4", "sha256": "ovsha", "mime_type": "video/mp4",
        }
        resp = client.post(
            f"/videos/{video_id}/overlay",
            json={"overlay_base64": _tiny_png_data_url()},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] != video_id
    assert body["kind"] == "overlay"
    assert body["model"] == "canvas-overlay"
    assert body["status"] == "done"
    assert body["cost_usd"] == 0.0
    # local ffmpeg compositing — no genblaze Pipeline, so no manifest to verify
    assert body["manifest_verified"] == 0
    assert body["prompt"].startswith("Overlay on: ")
    assert mock_overlay.call_args.args[0] == "https://example.com/v.mp4"

    assert any(v["id"] == body["id"] for v in client.get("/videos").json())


def test_video_overlay_rejects_bad_data_url(client):
    video_id = _done_video(client.workspace_id)
    resp = client.post(
        f"/videos/{video_id}/overlay",
        json={"overlay_base64": "https://example.com/not-a-data-url.png"},
    )
    assert resp.status_code == 400


def test_video_overlay_isolated_between_workspaces(client, other_client):
    video_id = _done_video(client.workspace_id)
    resp = other_client.post(
        f"/videos/{video_id}/overlay",
        json={"overlay_base64": _tiny_png_data_url()},
    )
    assert resp.status_code == 404


def test_audio_generation_with_catalog_voice(client):
    with patch("app.main.generate_audio") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/a.mp3", "sha256": "aud1",
            "mime_type": "audio/mpeg", "manifest_verified": True,
            "cost_usd": 0.0006, "voice": "openai:nova",
        }
        resp = client.post(
            "/audio",
            json={"text": "Hello world", "voice_provider": "openai", "voice_id": "nova"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    clip = resp.json()
    assert clip["text"] == "Hello world"
    assert clip["voice"] == "openai:nova"
    mock_gen.assert_called_once_with("Hello world", "openai", "nova")

    assert any(c["id"] == clip["id"] for c in client.get("/audio").json())
    assert client.delete(f"/audio/{clip['id']}").status_code == 204
    assert client.delete(f"/audio/{clip['id']}").status_code == 404


def test_audio_generation_with_gmi_catalog_voice(client, monkeypatch):
    monkeypatch.setattr("app.pipelines.GMI_API_KEY", "test-gmi-key")
    with patch("app.main.generate_audio") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/b.mp3", "sha256": "aud2",
            "mime_type": "audio/mpeg", "manifest_verified": True,
            "cost_usd": None, "voice": "gmi:Craig",
        }
        resp = client.post(
            "/audio",
            json={"text": "GMI voice", "voice_provider": "gmi", "voice_id": "Craig"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    mock_gen.assert_called_once_with("GMI voice", "gmi", "Craig")


def test_audio_rejects_unknown_openai_voice(client):
    resp = client.post(
        "/audio",
        json={"text": "hi", "voice_provider": "openai", "voice_id": "not-a-voice"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 400


def test_audio_rejects_unknown_gmi_voice(client):
    # GMI voices are a fixed catalog now too — no more arbitrary voice-id import.
    resp = client.post(
        "/audio",
        json={"text": "hi", "voice_provider": "gmi", "voice_id": "not-a-voice"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 400


def test_audio_keyless_allowed(client):
    from app.main import rate_limiter
    rate_limiter.reset()
    with patch("app.main.generate_audio", return_value={
        "url": "https://example.com/a.mp3", "sha256": "a", "mime_type": "audio/mpeg",
        "manifest_verified": True, "cost_usd": 0.0006, "voice": "openai:nova",
    }):
        resp = client.post("/audio", json={"text": "hi", "voice_provider": "openai", "voice_id": "nova"})
    assert resp.status_code == 200
    rate_limiter.reset()

def _await_video(client, video_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = client.get(f"/videos/{video_id}").json()
        if v["status"] in ("done", "error"):
            return v
        time.sleep(0.02)
    return client.get(f"/videos/{video_id}").json()


def test_video_character_mode_generates(client):
    # give a character a portrait so identity_references finds an anchor
    cid = client.post("/characters", json={"name": "VidChar"}).json()["id"]
    with patch("app.main.generate_character_portrait") as mock_img:
        mock_img.return_value = _fake_portrait("v")
        client.post(f"/characters/{cid}/generate/image",
                    json={"prompt": "p"}, headers={"X-API-Key": API_KEY})

    with patch("app.main.available_video_models",
               return_value=[{"slug": "Kling-Image2Video-V2.1-Master", "needs_image": True}]), \
         patch.dict("app.main.VIDEO_MODELS",
                    {"Kling-Image2Video-V2.1-Master": {"label": "k", "needs_image": True, "audio": False}}, clear=True), \
         patch("app.main.generate_video") as mock_vid:
        mock_vid.return_value = {
            "url": "https://example.com/clip.mp4", "original_url": "https://example.com/clip.mp4",
            "sha256": "vid1", "mime_type": "video/mp4", "manifest_verified": True, "cost_usd": None,
        }
        resp = client.post(
            "/videos",
            json={"prompt": "she smiles", "model": "Kling-Image2Video-V2.1-Master", "character_id": cid},
            headers={"X-API-Key": API_KEY},
        )
        assert resp.status_code == 200
        job = resp.json()
        assert job["status"] == "running"
        assert job["kind"] == "character"
        assert job["character_name"] == "VidChar"
        job = _await_video(client, job["id"])
    assert job["status"] == "done"
    assert job["url"] == "https://example.com/clip.mp4"
    # a reference (the portrait) was passed to the pipeline
    assert mock_vid.call_args.args[2] is not None

    assert any(v["id"] == job["id"] for v in client.get("/videos").json())
    assert client.delete(f"/videos/{job['id']}").status_code == 204


def test_video_character_mode_requires_portrait(client):
    cid = client.post("/characters", json={"name": "NoPortrait"}).json()["id"]
    with patch("app.main.available_video_models",
               return_value=[{"slug": "Kling-Image2Video-V2.1-Master", "needs_image": True}]), \
         patch.dict("app.main.VIDEO_MODELS",
                    {"Kling-Image2Video-V2.1-Master": {"label": "k", "needs_image": True, "audio": False}}, clear=True):
        resp = client.post(
            "/videos",
            json={"prompt": "move", "model": "Kling-Image2Video-V2.1-Master", "character_id": cid},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 400


def test_video_keyless_no_wall(client):
    from app.main import rate_limiter
    rate_limiter.reset()
    # No key wall: without GMI configured the model is simply unavailable (400),
    # not an auth rejection (401).
    resp = client.post("/videos", json={"prompt": "x", "model": "Veo3-Fast"})
    assert resp.status_code == 400
    rate_limiter.reset()

def test_video_models_carry_descriptions(client):
    from app.pipelines import VIDEO_MODELS, available_video_models
    # every model has a short strength blurb + a "best for" tag
    for slug, meta in VIDEO_MODELS.items():
        assert meta.get("description"), f"{slug} missing description"
        assert meta.get("best_for"), f"{slug} missing best_for"
    # available_video_models surfaces them when GMI is configured
    with patch("app.pipelines.GMI_API_KEY", "fake-key"):
        models = available_video_models()
    assert models and all(m["description"] and m["best_for"] for m in models)


def test_video_rejects_unavailable_model(client):
    # GMI not configured in tests → no video models → 400
    resp = client.post(
        "/videos",
        json={"prompt": "x", "model": "Kling-Text2Video-V2.1-Master"},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 400


def test_video_rejects_bad_duration(client):
    resp = client.post(
        "/videos",
        json={"prompt": "x", "model": "Veo3-Fast", "duration": 60},
        headers={"X-API-Key": API_KEY},
    )
    assert resp.status_code == 422


def test_script_generation_and_isolation(client, other_client):
    with patch("app.main.generate_script", return_value="Line one.\nLine two.\nLine three.") as mock:
        resp = client.post(
            "/scripts",
            json={"idea": "a lighthouse keeper", "format": "story", "length": "short"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    script = resp.json()
    assert script["format"] == "story"
    assert "Line two." in script["content"]
    mock.assert_called_once_with("a lighthouse keeper", "story", "short", None)

    assert any(s["id"] == script["id"] for s in client.get("/scripts").json())
    # another workspace can't see or delete it
    assert other_client.get("/scripts").json() == []
    assert other_client.delete(f"/scripts/{script['id']}").status_code == 404
    assert client.delete(f"/scripts/{script['id']}").status_code == 204


def test_script_passes_character_names(client):
    cid = client.post("/characters", json={"name": "Mira"}).json()["id"]
    with patch("app.main.generate_script", return_value="x") as mock:
        client.post(
            "/scripts",
            json={"idea": "adventure", "format": "video", "character_ids": [cid]},
            headers={"X-API-Key": API_KEY},
        )
    assert mock.call_args.args[3] == ["Mira"]


def test_script_keyless_allowed(client):
    from app.main import rate_limiter
    rate_limiter.reset()
    with patch("app.main.generate_script", return_value="A line."):
        resp = client.post("/scripts", json={"idea": "x"})
    assert resp.status_code == 200
    rate_limiter.reset()

def test_voice_fixed_on_character(client):
    # voice chosen at creation, stored on the character
    c = client.post("/characters", json={
        "name": "Voxy", "voice_provider": "openai", "voice_id": "nova"}).json()
    assert c["voice_provider"] == "openai" and c["voice_id"] == "nova"
    # editable via the profile (PATCH)
    r = client.patch(f"/characters/{c['id']}",
                     json={"voice_provider": "openai", "voice_id": "shimmer"}).json()
    assert r["voice_id"] == "shimmer"
    # an unknown OpenAI voice is rejected
    bad = client.post("/characters", json={
        "name": "Bad", "voice_provider": "openai", "voice_id": "nope"})
    assert bad.status_code == 400


def test_talking_video_prefers_lipsync(client):
    """The talking path uses lip-sync first; mux is only the fallback."""
    from app.main import rate_limiter
    rate_limiter.reset()
    cid = client.post("/characters", json={
        "name": "Lippy", "voice_provider": "openai", "voice_id": "nova"}).json()["id"]
    with patch("app.main.generate_character_portrait", return_value=_fake_portrait("l")):
        client.post(f"/characters/{cid}/generate/image",
                    json={"prompt": "p"}, headers={"X-API-Key": API_KEY})
    with patch("app.main.available_video_models",
               return_value=[{"slug": "Kling-Image2Video-V2.1-Master", "needs_image": True}]), \
         patch.dict("app.main.VIDEO_MODELS",
                    {"Kling-Image2Video-V2.1-Master": {"label": "k", "needs_image": True, "audio": False}}, clear=True), \
         patch("app.main.generate_video", return_value={
             "url": "https://ex/v.mp4", "original_url": "https://ex/v.mp4", "sha256": "v",
             "mime_type": "video/mp4", "manifest_verified": True, "cost_usd": None}), \
         patch("app.main.generate_character_voice_line", return_value={
             "url": "https://ex/a.mp3", "sha256": "a", "mime_type": "audio/mpeg",
             "manifest_verified": True, "cost_usd": 0.0006, "voice": "openai:nova"}), \
         patch("app.main.generate_lipsync", return_value={
             "url": "https://ex/lipsync.mp4", "sha256": "ls", "mime_type": "video/mp4"}) as mock_ls, \
         patch("app.main.mux_video_with_audio") as mock_mux:
        resp = client.post("/videos", json={
            "prompt": "she talks", "model": "Kling-Image2Video-V2.1-Master",
            "character_id": cid, "speech": "Hi there."}, headers={"X-API-Key": API_KEY})
        job = _await_video(client, resp.json()["id"])
    assert job["status"] == "done"
    assert job["url"] == "https://ex/lipsync.mp4"  # lip-synced, not muxed
    mock_ls.assert_called_once_with("https://ex/v.mp4", "https://ex/a.mp3")
    mock_mux.assert_not_called()
    rate_limiter.reset()


def test_talking_video_falls_back_to_mux(client):
    """If lip-sync fails, the mux fallback keeps the talking feature working."""
    from app.main import rate_limiter
    rate_limiter.reset()
    cid = client.post("/characters", json={
        "name": "Fally", "voice_provider": "openai", "voice_id": "nova"}).json()["id"]
    with patch("app.main.generate_character_portrait", return_value=_fake_portrait("f")):
        client.post(f"/characters/{cid}/generate/image",
                    json={"prompt": "p"}, headers={"X-API-Key": API_KEY})
    with patch("app.main.available_video_models",
               return_value=[{"slug": "Kling-Image2Video-V2.1-Master", "needs_image": True}]), \
         patch.dict("app.main.VIDEO_MODELS",
                    {"Kling-Image2Video-V2.1-Master": {"label": "k", "needs_image": True, "audio": False}}, clear=True), \
         patch("app.main.generate_video", return_value={
             "url": "https://ex/v.mp4", "original_url": "https://ex/v.mp4", "sha256": "v",
             "mime_type": "video/mp4", "manifest_verified": True, "cost_usd": None}), \
         patch("app.main.generate_character_voice_line", return_value={
             "url": "https://ex/a.mp3", "sha256": "a", "mime_type": "audio/mpeg",
             "manifest_verified": True, "cost_usd": 0.0006, "voice": "openai:nova"}), \
         patch("app.main.generate_lipsync", side_effect=RuntimeError("lipsync down")), \
         patch("app.main.mux_video_with_audio", return_value={
             "url": "https://ex/muxed.mp4", "sha256": "mx", "mime_type": "video/mp4"}) as mock_mux:
        resp = client.post("/videos", json={
            "prompt": "she talks", "model": "Kling-Image2Video-V2.1-Master",
            "character_id": cid, "speech": "Hi there."}, headers={"X-API-Key": API_KEY})
        job = _await_video(client, resp.json()["id"])
    assert job["status"] == "done"
    assert job["url"] == "https://ex/muxed.mp4"  # fell back to mux
    mock_mux.assert_called_once()
    rate_limiter.reset()


def test_talking_video_muxes_speech(client):
    from app.main import rate_limiter
    rate_limiter.reset()
    cid = client.post("/characters", json={
        "name": "Talky", "voice_provider": "openai", "voice_id": "nova"}).json()["id"]
    with patch("app.main.generate_character_portrait", return_value=_fake_portrait("t")):
        client.post(f"/characters/{cid}/generate/image",
                    json={"prompt": "p"}, headers={"X-API-Key": API_KEY})

    with patch("app.main.available_video_models",
               return_value=[{"slug": "Kling-Image2Video-V2.1-Master", "needs_image": True}]), \
         patch.dict("app.main.VIDEO_MODELS",
                    {"Kling-Image2Video-V2.1-Master": {"label": "k", "needs_image": True, "audio": False}}, clear=True), \
         patch("app.main.generate_video", return_value={
             "url": "https://ex/v.mp4", "original_url": "https://ex/v.mp4", "sha256": "v",
             "mime_type": "video/mp4", "manifest_verified": True, "cost_usd": None}), \
         patch("app.main.generate_character_voice_line", return_value={
             "url": "https://ex/a.mp3", "sha256": "a", "mime_type": "audio/mpeg",
             "manifest_verified": True, "cost_usd": 0.0006, "voice": "openai:nova"}) as mock_voice, \
         patch("app.main.mux_video_with_audio", return_value={
             "url": "https://ex/talking.mp4", "sha256": "tk", "mime_type": "video/mp4"}) as mock_mux:
        resp = client.post("/videos", json={
            "prompt": "she waves", "model": "Kling-Image2Video-V2.1-Master",
            "character_id": cid, "speech": "Hi. Nice to meet you."},
            headers={"X-API-Key": API_KEY})
        job = _await_video(client, resp.json()["id"])
    assert job["status"] == "done"
    assert job["url"] == "https://ex/talking.mp4"  # the muxed talking clip
    assert mock_voice.call_args.args[1] == "Hi. Nice to meet you."
    mock_mux.assert_called_once_with("https://ex/v.mp4", "https://ex/a.mp3")
    rate_limiter.reset()


def test_assign_voice_rejects_unknown_id(client):
    char_id = client.post("/characters", json={"name": "BadVoice"}).json()["id"]
    resp = client.put(
        f"/characters/{char_id}/voice",
        json={"voice_provider": "openai", "voice_id": "not-a-voice"},
    )
    assert resp.status_code == 400


# ── Portfolio mode: per-workspace budget & per-IP workspace cap ───────────

def _set_budget(workspace_id: str, quota: int, used: int = 0) -> None:
    """Give a workspace an exact budget, independent of the suite-wide caps."""
    from app import db
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE workspaces SET units_used = ?, units_quota = ? WHERE id = ?",
            (used, quota, workspace_id),
        )


def test_budget_is_reported_and_spent_per_generation(client):
    from app.main import rate_limiter
    rate_limiter.reset()
    _set_budget(client.workspace_id, quota=5)
    assert client.get("/workspaces/current").json()["units_remaining"] == 5

    char_id = client.post("/characters", json={"name": "Budget"}).json()["id"]
    with patch("app.main.generate_character_portrait", return_value=_fake_portrait("q")):
        assert client.post(f"/characters/{char_id}/generate/image",
                           json={"prompt": "one"}).status_code == 200
    # One image costs one unit, and the counter is visible to the UI.
    assert client.get("/workspaces/current").json()["units_remaining"] == 4
    rate_limiter.reset()


def test_generation_is_refused_once_the_budget_is_gone(client):
    from app.main import rate_limiter
    rate_limiter.reset()
    _set_budget(client.workspace_id, quota=1)
    char_id = client.post("/characters", json={"name": "Exhausted"}).json()["id"]
    with patch("app.main.generate_character_portrait", return_value=_fake_portrait("e")) as gen:
        first = client.post(f"/characters/{char_id}/generate/image", json={"prompt": "a"})
        second = client.post(f"/characters/{char_id}/generate/image", json={"prompt": "b"})
    assert first.status_code == 200
    assert second.status_code == 429
    # The refused run must not reach the paid provider at all.
    assert gen.call_count == 1
    rate_limiter.reset()


def test_failed_generation_hands_the_budget_back(client):
    """A provider outage must not cost a visitor part of their one-run budget."""
    from app.main import rate_limiter
    rate_limiter.reset()
    _set_budget(client.workspace_id, quota=3)
    char_id = client.post("/characters", json={"name": "Refunded"}).json()["id"]
    with patch("app.main.generate_character_portrait", side_effect=RuntimeError("provider down")):
        resp = client.post(f"/characters/{char_id}/generate/image", json={"prompt": "x"})
    assert resp.status_code == 502
    assert client.get("/workspaces/current").json()["units_remaining"] == 3
    rate_limiter.reset()


def test_batch_draws_and_refunds_per_frame(client):
    """Batch bypasses generation_guard, so it must charge the budget itself —
    and give back every frame that never became an image."""
    from app.main import rate_limiter
    rate_limiter.reset()
    _set_budget(client.workspace_id, quota=10)
    char_id = client.post("/characters", json={"name": "Batch"}).json()["id"]

    calls = {"n": 0}

    def half_failing(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 2:
            raise RuntimeError("provider down")
        return _fake_portrait(f"b{calls['n']}")

    with patch("app.main.generate_character_portrait", side_effect=half_failing):
        job = client.post(f"/characters/{char_id}/generate/batch",
                          json={"mode": "variation", "prompt": "p", "count": 4}).json()
        _await_batch(client, job["id"])
    # 4 frames charged, 2 produced an image → 2 units come back.
    assert client.get("/workspaces/current").json()["units_remaining"] == 10 - 2
    rate_limiter.reset()


def test_one_ip_can_only_mint_a_few_workspaces():
    from fastapi.testclient import TestClient
    import app.main as m
    from app.main import app as fastapi_app
    # A dedicated caller IP: every other test in the suite shares TestClient's
    # own host, which by now has minted plenty of workspaces.
    caller = {"X-Forwarded-For": "198.51.100.42"}
    with patch.object(m, "MAX_WORKSPACES_PER_IP", 2), TestClient(fastapi_app) as c:
        assert c.post("/workspaces", json={"name": "A"}, headers=caller).status_code == 200
        assert c.post("/workspaces", json={"name": "B"}, headers=caller).status_code == 200
        # Third one from that same network is over the cap.
        assert c.post("/workspaces", json={"name": "C"}, headers=caller).status_code == 429
        # A different network is unaffected — one visitor can't lock out others.
        assert c.post("/workspaces", json={"name": "E"},
                      headers={"X-Forwarded-For": "198.51.100.99"}).status_code == 200
        # The owner key is not subject to the cap.
        assert c.post("/workspaces", json={"name": "D"},
                      headers={**caller, "X-API-Key": API_KEY}).status_code == 200


def test_workspace_response_does_not_leak_the_creating_ip():
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app
    with TestClient(fastapi_app) as c:
        body = c.post("/workspaces", json={"name": "Private"}).json()
    assert "created_ip" not in body
    assert body["units_remaining"] == body["units_quota"]
