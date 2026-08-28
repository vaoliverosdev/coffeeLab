import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ["DATABASE_URL"] = "sqlite:///./test_google_auth.db"
os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-google-auth-secret"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["GOOGLE_CLIENT_ID"] = "coffee-lab-google-client"

TEST_DB = Path("test_google_auth.db")
if TEST_DB.exists():
    TEST_DB.unlink()

from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from core import SessionLocal, User


PROFILES = {
    "new-a": {
        "aud": "coffee-lab-google-client",
        "email_verified": "true",
        "email": "google-a@example.com",
        "sub": "sub-a",
        "name": "Google A",
        "picture": "https://example.com/a.png",
    },
    "new-b": {
        "aud": "coffee-lab-google-client",
        "email_verified": True,
        "email": "google-b@example.com",
        "sub": "sub-b",
        "name": "Google B",
        "picture": "https://example.com/b.png",
    },
    "existing": {
        "aud": "coffee-lab-google-client",
        "email_verified": "true",
        "email": "manual@example.com",
        "sub": "sub-manual",
        "name": "Google Manual",
        "picture": "https://example.com/manual.png",
    },
    "same-sub-other-email": {
        "aud": "coffee-lab-google-client",
        "email_verified": "true",
        "email": "other@example.com",
        "sub": "sub-manual",
        "name": "Conflict",
        "picture": "https://example.com/conflict.png",
    },
    "unverified": {
        "aud": "coffee-lab-google-client",
        "email_verified": "false",
        "email": "noverify@example.com",
        "sub": "sub-noverify",
        "name": "No Verify",
    },
    "bad-aud": {
        "aud": "another-client",
        "email_verified": "true",
        "email": "bad-aud@example.com",
        "sub": "sub-bad",
    },
}


async def fake_fetch_google_profile(credential: str):
    if credential == "invalid":
        raise HTTPException(status_code=401, detail="Credencial do Google inválida.")
    return PROFILES[credential]


def token_from_dev_url(url: str) -> str:
    fragment = urlparse(url).fragment
    query = fragment.split("?", 1)[1] if "?" in fragment else ""
    token = parse_qs(query).get("token", [None])[0]
    assert token
    return token


def assert_status(response, *codes):
    assert response.status_code in codes, response.text
    return response


def test_google_auth_flow(monkeypatch):
    monkeypatch.setattr(main, "fetch_google_profile", fake_fetch_google_profile)

    with TestClient(main.app) as client:
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
        main.get_settings.cache_clear()
        assert_status(client.post("/api/auth/google", json={"credential": "new-a"}), 400)

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "coffee-lab-google-client")
        main.get_settings.cache_clear()

        assert_status(client.post("/api/auth/google", json={"credential": "invalid"}), 401)
        assert_status(client.post("/api/auth/google", json={"credential": "bad-aud"}), 401)
        assert_status(client.post("/api/auth/google", json={"credential": "unverified"}), 401)

        login_a = assert_status(
            client.post("/api/auth/google", json={"credential": "new-a"}), 200
        ).json()
        assert login_a["user"]["email"] == "google-a@example.com"
        assert login_a["user"]["username"] == "googlea"
        assert login_a["user"]["email_verified"] is True
        assert login_a["user"]["google_connected"] is True
        assert login_a["user"]["password_login_enabled"] is False
        headers_a = {"Authorization": f"Bearer {login_a['access_token']}"}

        profile_a = assert_status(
            client.put(
                "/api/auth/me",
                headers=headers_a,
                json={
                    "username": "brew.lab",
                    "city": "Curitiba",
                    "country": "Brasil",
                    "bio": "Explorando cafés naturais e fermentados.",
                    "favorite_methods": ["V60", "Aeropress", "V60"],
                    "favorite_roasteries": ["Coffee Lab"],
                    "sensory_preferences": ["frutas vermelhas", "caramelo"],
                    "mastered_methods": ["V60", "Espresso"],
                    "diary_visibility": "public",
                    "barista_setup": {
                        "grinder": "Timemore C3",
                        "kettle": "Pescoço de ganso",
                        "scale": "Balança com timer",
                        "brewers": "V60, Aeropress",
                    },
                    "is_public_profile": True,
                    "profile_visibility": "public",
                },
            ),
            200,
        ).json()
        assert profile_a["username"] == "brew.lab"
        assert profile_a["profile_visibility"] == "public"
        assert profile_a["diary_visibility"] == "public"
        assert profile_a["favorite_methods"] == ["V60", "Aeropress"]
        assert profile_a["mastered_methods"] == ["V60", "Espresso"]
        assert profile_a["barista_setup"]["grinder"] == "Timemore C3"
        public_profile = assert_status(client.get("/api/users/brew.lab/profile"), 200).json()
        assert public_profile["username"] == "brew.lab"
        assert public_profile["mastered_methods"] == ["V60", "Espresso"]
        assert public_profile["barista_setup"]["scale"] == "Balança com timer"
        assert public_profile["stats"]["coffees"] == 0

        coffee_a = assert_status(
            client.post(
                "/api/coffees",
                headers=headers_a,
                json={"name": "A", "roastery": "R", "origin": "BR"},
            ),
            200,
            201,
        ).json()

        login_b = assert_status(
            client.post("/api/auth/google", json={"credential": "new-b"}), 200
        ).json()
        headers_b = {"Authorization": f"Bearer {login_b['access_token']}"}
        assert assert_status(client.get("/api/coffees", headers=headers_b), 200).json() == []
        assert_status(
            client.put(
                "/api/auth/me",
                headers=headers_b,
                json={"username": "googleb", "is_public_profile": True},
            ),
            200,
        )
        assert_status(
            client.put(
                "/api/auth/me",
                headers=headers_b,
                json={"username": "brew.lab"},
            ),
            400,
        )

        post = assert_status(
            client.post(
                "/api/social/posts",
                headers=headers_a,
                json={"content": "V60 com notas de caramelo hoje."},
            ),
            201,
        ).json()
        assert post["content"].startswith("V60")

        feed = assert_status(client.get("/api/social/feed", headers=headers_a), 200).json()
        assert any(item["target_type"] == "post" for item in feed)

        recipe = assert_status(
            client.post(
                "/api/recipes",
                headers=headers_a,
                json={
                    "coffee_id": coffee_a["id"],
                    "name": "V60 Social",
                    "method": "V60",
                    "coffee_weight": 15,
                    "water_weight": 240,
                    "steps": ["Pré-infusão", "Despejo final"],
                },
            ),
            201,
        ).json()
        extraction = assert_status(
            client.post(
                "/api/extractions",
                headers=headers_a,
                json={"recipe_id": recipe["id"], "coffee_id": coffee_a["id"], "total_time": 210, "rating": 5},
            ),
            200,
        ).json()
        assert extraction["total_time"] == 210
        assert_status(
            client.post(
                "/api/sensory-logs",
                headers=headers_a,
                json={
                    "coffee_id": coffee_a["id"],
                    "extraction_id": extraction["id"],
                    "aroma_score": 8,
                    "acidity_score": 7,
                    "body_score": 8,
                    "sweetness_score": 9,
                    "aftertaste_score": 8,
                    "perceived_notes": "caramelo, frutas vermelhas",
                },
            ),
            200,
        )
        public_recipe = assert_status(
            client.post(f"/api/social/recipes/{recipe['id']}/share", headers=headers_a),
            200,
        ).json()
        assert public_recipe["title"] == "V60 Social"
        copied = assert_status(
            client.post(f"/api/social/public-recipes/{public_recipe['id']}/copy", headers=headers_b),
            201,
        ).json()
        assert copied["name"].endswith("(copiada)")

        assert_status(
            client.post(
                "/api/social/wishlist",
                headers=headers_a,
                json={"coffee_name": "Geisha Natural", "roastery": "Fazenda Beta"},
            ),
            201,
        )
        assert_status(
            client.post(
                "/api/social/tried",
                headers=headers_a,
                json={"coffee_id": coffee_a["id"], "coffee_name": "fallback", "rating": 4.5},
            ),
            201,
        )
        rating = assert_status(
            client.post(
                "/api/social/ratings",
                headers=headers_a,
                json={"coffee_id": coffee_a["id"], "coffee_name": "fallback", "rating": 92, "scale": "hundred"},
            ),
            201,
        ).json()
        assert rating["coffee_name"] == "A"
        assert rating["scale"] == "hundred"
        assert_status(
            client.post(
                "/api/social/goals",
                headers=headers_a,
                json={"title": "20 extrações no mês", "goal_type": "extractions", "target_value": 20},
            ),
            201,
        )
        assert_status(client.post("/api/social/follow/brew.lab", headers=headers_b), 200)
        assert_status(client.post("/api/social/follow/googleb", headers=headers_a), 200)
        followers = assert_status(client.get("/api/social/users/brew.lab/followers", headers=headers_a), 200).json()
        following = assert_status(client.get("/api/social/users/brew.lab/following", headers=headers_a), 200).json()
        assert followers[0]["username"] == "googleb"
        assert following[0]["username"] == "googleb"
        user_activities = assert_status(client.get("/api/social/users/brew.lab/activities?limit=5&offset=0", headers=headers_a), 200).json()
        assert len(user_activities) <= 5
        like = assert_status(client.post(f"/api/social/activity/{feed[0]['id']}/like", headers=headers_b), 200).json()
        assert like["liked"] is True
        unlike = assert_status(client.post(f"/api/social/activity/{feed[0]['id']}/like", headers=headers_b), 200).json()
        assert unlike["liked"] is False
        comment = assert_status(
            client.post(
                f"/api/social/activity/{feed[0]['id']}/comments",
                headers=headers_b,
                json={"body": "Essa receita parece ótima."},
            ),
            201,
        ).json()
        assert comment["body"].startswith("Essa")
        listed_comments = assert_status(client.get(f"/api/social/activity/{feed[0]['id']}/comments?limit=10", headers=headers_a), 200).json()
        assert listed_comments[0]["id"] == comment["id"]
        assert_status(client.delete(f"/api/social/comments/{comment['id']}", headers=headers_b), 200)
        assert_status(client.get(f"/api/social/activity/{feed[0]['id']}/comments", headers=headers_a), 200).json() == []
        mark_wishlist = assert_status(client.post(f"/api/social/coffees/{coffee_a['id']}/wishlist", headers=headers_b), 201).json()
        assert mark_wishlist["coffee_name"] == "A"
        mark_tried = assert_status(
            client.post(
                f"/api/social/coffees/{coffee_a['id']}/tried",
                headers=headers_b,
                json={"rating": 4.2, "notes": "Boa doçura."},
            ),
            201,
        ).json()
        assert mark_tried["coffee_name"] == "A"
        explore = assert_status(client.get("/api/social/explore", headers=headers_a), 200).json()
        assert "popular_methods" in explore
        assert_status(client.get("/api/social/trends", headers=headers_a), 200)
        assert_status(client.get("/api/public/landing"), 200)
        assert_status(client.get("/api/public/feed?limit=2&offset=0"), 200)
        public_explore = assert_status(client.get("/api/public/explore"), 200).json()
        assert "popular_roasteries" in public_explore
        trends = assert_status(client.get("/api/public/trends"), 200).json()
        assert "active_baristas" in trends
        coffee_page = assert_status(client.get(f"/api/public/coffees/{coffee_a['id']}"), 200).json()
        assert coffee_page["coffee"]["name"] == "A"
        recipe_page = assert_status(client.get(f"/api/public/recipes/{public_recipe['id']}"), 200).json()
        assert recipe_page["title"] == "V60 Social"
        roastery_page = assert_status(client.get("/api/public/roasteries/R"), 200).json()
        assert roastery_page["name"] == "R"
        method_page = assert_status(client.get("/api/public/methods/V60"), 200).json()
        assert method_page["recipes_count"] >= 1
        assert_status(client.delete(f"/api/social/public-recipes/{public_recipe['id']}", headers=headers_b), 404)
        assert_status(client.delete(f"/api/social/public-recipes/{public_recipe['id']}", headers=headers_a), 200)
        assert_status(client.get(f"/api/public/recipes/{public_recipe['id']}"), 404)
        onboarding = assert_status(client.get("/api/onboarding/status", headers=headers_a), 200).json()
        assert onboarding["completed"]["first_coffee"] is True
        assert onboarding["completed"]["sensory"] is True
        privacy = assert_status(client.get("/api/auth/me/privacy", headers=headers_a), 200).json()
        assert privacy["profile_visibility"] == "public"
        updated_privacy = assert_status(
            client.put(
                "/api/auth/me/privacy",
                headers=headers_a,
                json={"profile_visibility": "public", "diary_visibility": "private"},
            ),
            200,
        ).json()
        assert updated_privacy["diary_visibility"] == "private"
        public_profile = assert_status(client.get("/api/users/brew.lab/profile"), 200).json()
        assert public_profile["stats"]["cafes_tried"] == 1
        assert public_profile["stats"]["followers"] == 1
        assert public_profile["stats"]["cups_this_month"] == 1
        assert public_profile["stats"]["roasteries_explored"] == 1
        assert public_profile["tabs"]["sensory"] == []
        assert any(item["coffee_name"] == "Geisha Natural" for item in public_profile["tabs"]["wishlist"])

        assert_status(
            client.put(
                "/api/auth/me/password",
                headers=headers_a,
                json={"new_password": "CafeSenha9"},
            ),
            200,
        )
        me_a = assert_status(client.get("/api/auth/me", headers=headers_a), 200).json()
        assert me_a["password_login_enabled"] is True
        assert_status(
            client.post(
                "/api/auth/login",
                json={"email": "google-a@example.com", "password": "CafeSenha9"},
            ),
            200,
        )

        register = assert_status(
            client.post(
                "/api/auth/register",
                json={
                    "name": "Manual Custom",
                    "email": "manual@example.com",
                    "password": "CafeForte9",
                },
            ),
            200,
            201,
        ).json()
        assert_status(
            client.post(
                "/api/auth/verify-email",
                json={"token": token_from_dev_url(register["dev_verification_url"])},
            ),
            200,
        )
        manual_login = assert_status(
            client.post(
                "/api/auth/login",
                json={"email": "manual@example.com", "password": "CafeForte9"},
            ),
            200,
        ).json()
        manual_headers = {"Authorization": f"Bearer {manual_login['access_token']}"}
        assert_status(
            client.put(
                "/api/auth/me",
                headers=manual_headers,
                json={"name": "Manual Editado", "bio": "bio"},
            ),
            200,
        )

        linked = assert_status(
            client.post("/api/auth/google", json={"credential": "existing"}), 200
        ).json()
        assert linked["user"]["email"] == "manual@example.com"
        assert linked["user"]["name"] == "Manual Editado"
        assert linked["user"]["google_connected"] is True
        with SessionLocal() as db:
            users = db.query(User).filter(User.email == "manual@example.com").all()
            assert len(users) == 1

        register_other = assert_status(
            client.post(
                "/api/auth/register",
                json={
                    "name": "Other",
                    "email": "other@example.com",
                    "password": "CafeOutro9",
                },
            ),
            200,
            201,
        ).json()
        assert_status(
            client.post(
                "/api/auth/verify-email",
                json={"token": token_from_dev_url(register_other["dev_verification_url"])},
            ),
            200,
        )
        assert_status(
            client.post("/api/auth/google", json={"credential": "same-sub-other-email"}),
            409,
        )

        linked_headers = {"Authorization": f"Bearer {linked['access_token']}"}
        disconnected = assert_status(
            client.delete("/api/auth/me/google", headers=linked_headers), 200
        ).json()
        assert disconnected["google_connected"] is False
