import time
from unittest.mock import patch

API_KEY = "test-key"


def _fake_portrait(tag="x"):
    return {
        "url": f"https://example.com/{tag}.png",
        "original_url": f"https://example.com/{tag}.png",
        "sha256": tag, "mime_type": "image/png", "manifest_verified": True,
        "disclosure": "invisible", "quality": "draft", "cost_usd": 0.011,
        "model": "gpt-image-1",
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
        "disclosure": "invisible", "quality": "draft", "cost_usd": 0.011,
        "model": "gpt-image-1", "kind": "photo-art",
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
    mock_gen.assert_called_once_with(char_id, "a friendly robot", "visible", [], "draft", "gpt-image-1", None, None)

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
    mock_gen.assert_called_once_with(char_id, "a quiet librarian", "invisible", [], "draft", "gpt-image-1", None, None)


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
            "cost_usd": 0.167,
        }
        resp = client.post(
            f"/characters/{char_id}/generate/image",
            json={"prompt": "a portrait", "quality": "final"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["quality"] == "final"
    assert data["cost_usd"] == 0.167
    assert mock_gen.call_args.args[4] == "final"


def test_capabilities_lists_available_models(client):
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    slugs = {m["slug"] for m in resp.json()["image_models"]}
    # gpt-image-1 is always available; GMI models only if GMI_API_KEY is set
    assert "gpt-image-1" in slugs


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
            "disclosure": "invisible", "quality": "draft", "cost_usd": 0.011, "model": "gpt-image-1",
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
                "quality": "draft", "cost_usd": 0.011, "model": "gpt-image-1",
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
            "disclosure": "invisible", "quality": "draft", "cost_usd": 0.011,
            "model": "gpt-image-1", "kind": "photo-art",
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
        "disclosure": "invisible", "quality": "draft", "cost_usd": 0.011,
        "model": "gpt-image-1", "kind": "background",
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


def test_audio_accepts_custom_elevenlabs_voice_id(client):
    # a custom (non-catalog) ElevenLabs id is allowed — that's the import path
    with patch("app.main.generate_audio") as mock_gen:
        mock_gen.return_value = {
            "url": "https://example.com/b.mp3", "sha256": "aud2",
            "mime_type": "audio/mpeg", "manifest_verified": True,
            "cost_usd": None, "voice": "elevenlabs:MYOWNVOICE123",
        }
        resp = client.post(
            "/audio",
            json={"text": "Custom voice", "voice_provider": "elevenlabs", "voice_id": "MYOWNVOICE123"},
            headers={"X-API-Key": API_KEY},
        )
    assert resp.status_code == 200
    mock_gen.assert_called_once_with("Custom voice", "elevenlabs", "MYOWNVOICE123")


def test_audio_rejects_unknown_openai_voice(client):
    resp = client.post(
        "/audio",
        json={"text": "hi", "voice_provider": "openai", "voice_id": "not-a-voice"},
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

def test_assign_voice_rejects_unknown_id(client):
    char_id = client.post("/characters", json={"name": "BadVoice"}).json()["id"]
    resp = client.put(
        f"/characters/{char_id}/voice",
        json={"voice_provider": "openai", "voice_id": "not-a-voice"},
    )
    assert resp.status_code == 400
