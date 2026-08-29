import os
import tempfile

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(suffix='.db', delete=False).name}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ.pop("GOOGLE_CLIENT_ID", None)
os.environ.pop("OPENROUTER_API_KEY", None)

from fastapi.testclient import TestClient

import main
from core import Base, SessionLocal, User, engine, get_settings, hash_password


class FakeGoogleResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeGoogleClient:
    payload = {}
    status_code = 200

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return FakeGoogleResponse(self.status_code, self.payload)


def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    main.ensure_auth_columns()
    main.AUTH_RATE_LIMIT.clear()


def create_verified_user(email="barista@example.com", password="StrongPass1", **kwargs):
    db = SessionLocal()
    try:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            name=kwargs.pop("name", "Barista"),
            email_verified=True,
            **kwargs,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def auth_headers(client, email="barista@example.com", password="StrongPass1"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_google_login_rejects_when_client_id_is_missing(monkeypatch):
    reset_database()
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    get_settings.cache_clear()

    with TestClient(main.app) as client:
        response = client.post("/api/auth/google", json={"credential": "token"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Login com Google não configurado."


def test_google_login_creates_verified_user(monkeypatch):
    reset_database()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    get_settings.cache_clear()
    FakeGoogleClient.status_code = 200
    FakeGoogleClient.payload = {
        "aud": "client-id",
        "email": "novo@example.com",
        "email_verified": "true",
        "sub": "google-sub-1",
        "name": "Novo Barista",
        "picture": "https://example.com/avatar.png",
    }
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeGoogleClient)

    with TestClient(main.app) as client:
        response = client.post("/api/auth/google", json={"credential": "token"})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user"]["email"] == "novo@example.com"
    assert data["user"]["email_verified"] is True
    assert data["user"]["avatar_url"] == "https://example.com/avatar.png"


def test_google_login_blocks_ambiguous_link(monkeypatch):
    reset_database()
    create_verified_user(email="email-owner@example.com")
    create_verified_user(email="sub-owner@example.com", google_sub="google-sub-2")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    get_settings.cache_clear()
    FakeGoogleClient.status_code = 200
    FakeGoogleClient.payload = {
        "aud": "client-id",
        "email": "email-owner@example.com",
        "email_verified": "true",
        "sub": "google-sub-2",
        "name": "Conta Ambigua",
    }
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeGoogleClient)

    with TestClient(main.app) as client:
        response = client.post("/api/auth/google", json={"credential": "token"})

    assert response.status_code == 409


def test_google_login_rejects_inactive_existing_user(monkeypatch):
    reset_database()
    create_verified_user(email="inactive@example.com", google_sub="inactive-sub", is_active=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    get_settings.cache_clear()
    FakeGoogleClient.status_code = 200
    FakeGoogleClient.payload = {
        "aud": "client-id",
        "email": "inactive@example.com",
        "email_verified": "true",
        "sub": "inactive-sub",
        "name": "Inativo",
    }
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeGoogleClient)

    with TestClient(main.app) as client:
        response = client.post("/api/auth/google", json={"credential": "token"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Conta indisponível."


def test_inactive_user_login_is_rejected():
    reset_database()
    create_verified_user(is_active=False)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "barista@example.com", "password": "StrongPass1"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Conta indisponível."


def test_inactive_user_token_is_rejected():
    reset_database()
    user_id = create_verified_user(is_active=False)

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        token = main.create_access_token(data={"sub": user.email})
    finally:
        db.close()

    with TestClient(main.app) as client:
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Conta indisponível."


def test_sensory_profile_handles_empty_notes():
    reset_database()
    create_verified_user()

    with TestClient(main.app) as client:
        headers = auth_headers(client)
        create_response = client.post(
            "/api/sensory-logs",
            headers=headers,
            json={
                "aroma_score": 7,
                "acidity_score": 6,
                "body_score": 5,
                "sweetness_score": 6,
                "aftertaste_score": 7,
                "perceived_notes": None,
            },
        )
        assert create_response.status_code == 200, create_response.text

        profile_response = client.get("/api/sensory-explorer/profile", headers=headers)

    assert profile_response.status_code == 200, profile_response.text
    assert profile_response.json()["top_notes"] == []


def test_sensory_scores_are_limited_to_valid_range():
    reset_database()
    create_verified_user()

    with TestClient(main.app) as client:
        headers = auth_headers(client)
        response = client.post(
            "/api/sensory-logs",
            headers=headers,
            json={"aroma_score": 99},
        )

    assert response.status_code == 422


def test_domain_inputs_reject_impossible_values():
    reset_database()
    create_verified_user()

    with TestClient(main.app) as client:
        headers = auth_headers(client)

        invalid_coffee = client.post(
            "/api/coffees",
            headers=headers,
            json={
                "name": "Café Teste",
                "roastery": "Torra Teste",
                "origin": "Brasil",
                "sca_score": 120,
            },
        )
        assert invalid_coffee.status_code == 422

        valid_coffee = client.post(
            "/api/coffees",
            headers=headers,
            json={
                "name": "Café Teste",
                "roastery": "Torra Teste",
                "origin": "Brasil",
                "sca_score": 86,
            },
        )
        assert valid_coffee.status_code == 200, valid_coffee.text

        stock = client.get("/api/stock", headers=headers).json()[0]
        invalid_stock = client.put(
            f"/api/stock/{stock['id']}",
            headers=headers,
            json={"current_quantity": -10},
        )
        assert invalid_stock.status_code == 422

        invalid_recipe = client.post(
            "/api/recipes",
            headers=headers,
            json={
                "name": "Receita Inválida",
                "method": "V60",
                "coffee_weight": 15,
                "water_weight": 240,
                "water_temp": 130,
            },
        )
        assert invalid_recipe.status_code == 422

        invalid_extraction = client.post(
            "/api/extractions",
            headers=headers,
            json={"total_time": 0, "rating": 6},
        )
        assert invalid_extraction.status_code == 422
