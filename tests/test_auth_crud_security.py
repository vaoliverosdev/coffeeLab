import os
import tempfile
from pathlib import Path

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.gettempdir()}/coffee_lab_pytest.db"
os.environ["SECRET_KEY"] = "test-secret-key-with-at-least-thirty-two-chars"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["ALLOWED_ORIGINS"] = "http://testserver"
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USERNAME"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["SMTP_FROM_EMAIL"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""

from fastapi.testclient import TestClient

from core import Base, engine, get_settings, validate_runtime_settings
from main import AUTH_RATE_LIMIT, app


TEST_DB_PATH = Path(tempfile.gettempdir()) / "coffee_lab_pytest.db"


def setup_module():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    Base.metadata.create_all(bind=engine)
    AUTH_RATE_LIMIT.clear()


def teardown_module():
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


def unique_email(prefix):
    return f"{prefix}-{next(unique_email.counter)}@example.com"


unique_email.counter = iter(range(1, 1000))


def register_verify_login(client, prefix="user"):
    email = unique_email(prefix)
    password = "StrongPass42"

    created = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "name": f"{prefix.title()} Barista"},
    )
    assert created.status_code == 200
    token = created.json()["dev_verification_url"].split("token=", 1)[1]

    verified = client.post("/api/auth/verify-email", json={"token": token})
    assert verified.status_code == 200

    logged = client.post("/api/auth/login", json={"email": email, "password": password})
    assert logged.status_code == 200
    auth_token = logged.json()["access_token"]
    return {"Authorization": f"Bearer {auth_token}"}, logged.json()["user"]


def coffee_payload(name="Bourbon Amarelo"):
    return {
        "name": name,
        "roastery": "Torra Laboratorio",
        "origin": "Mantiqueira",
        "region": "Sul de Minas",
        "variety": "Bourbon",
        "process": "Natural",
        "roast_level": "Media",
        "sensory_notes": "mel, frutas amarelas, chocolate",
        "sca_score": 86.5,
    }


def recipe_payload(coffee_id, name="V60 claro"):
    return {
        "coffee_id": coffee_id,
        "name": name,
        "method": "V60",
        "coffee_weight": 15,
        "water_weight": 240,
        "grind_size": "Media fina",
        "water_temp": 94,
        "description": "Receita base para cafes doces.",
        "steps": ["Bloom de 40s", "Duas despejadas circulares"],
    }


def test_authentication_flow_and_google_config_message():
    with TestClient(app) as client:
        weak = client.post(
            "/api/auth/register",
            json={"email": unique_email("weak"), "password": "12345678", "name": "Teste"},
        )
        assert weak.status_code == 422

        email = unique_email("pending")
        created = client.post(
            "/api/auth/register",
            json={"email": email, "password": "StrongPass42", "name": "Pending Barista"},
        )
        assert created.status_code == 200

        blocked = client.post("/api/auth/login", json={"email": email, "password": "StrongPass42"})
        assert blocked.status_code == 403

        token = created.json()["dev_verification_url"].split("token=", 1)[1]
        assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200

        wrong = client.post("/api/auth/login", json={"email": email, "password": "WrongPass42"})
        assert wrong.status_code == 401

        logged = client.post("/api/auth/login", json={"email": email, "password": "StrongPass42"})
        assert logged.status_code == 200
        assert logged.json()["user"]["email"] == email

        google_config = client.get("/api/auth/config").json()
        assert google_config["google_enabled"] is False
        assert "GOOGLE_CLIENT_ID" in google_config["google_status_message"]


def test_crud_validation_and_user_isolation():
    with TestClient(app) as client:
        headers_a, _ = register_verify_login(client, "alice")
        headers_b, _ = register_verify_login(client, "bruno")

        invalid = client.post("/api/coffees", headers=headers_a, json={**coffee_payload(), "sca_score": 101})
        assert invalid.status_code == 422

        created = client.post("/api/coffees", headers=headers_a, json=coffee_payload("Geisha Floral"))
        assert created.status_code == 200
        coffee_id = created.json()["id"]

        stock = client.get("/api/stock", headers=headers_a)
        assert stock.status_code == 200
        assert stock.json()[0]["coffee_id"] == coffee_id
        stock_id = stock.json()[0]["id"]

        updated_stock = client.put(
            f"/api/stock/{stock_id}",
            headers=headers_a,
            json={"current_quantity": 250, "min_quantity": 60, "is_opened": True},
        )
        assert updated_stock.status_code == 200

        assert client.get("/api/coffees", headers=headers_b).json() == []
        assert client.put(f"/api/coffees/{coffee_id}", headers=headers_b, json={"name": "Invasao"}).status_code == 404
        assert client.put(f"/api/stock/{stock_id}", headers=headers_b, json={"current_quantity": 999}).status_code == 404

        recipe = client.post("/api/recipes", headers=headers_a, json=recipe_payload(coffee_id))
        assert recipe.status_code == 201
        recipe_id = recipe.json()["id"]

        recipe_with_other_user_coffee = client.post("/api/recipes", headers=headers_b, json=recipe_payload(coffee_id, "Receita indevida"))
        assert recipe_with_other_user_coffee.status_code == 400

        own_recipe = client.post("/api/recipes", headers=headers_b, json=recipe_payload(None, "Receita livre"))
        assert own_recipe.status_code == 201
        assert client.put(f"/api/recipes/{own_recipe.json()['id']}", headers=headers_b, json={"coffee_id": coffee_id}).status_code == 400

        extraction = client.post(
            "/api/extractions",
            headers=headers_a,
            json={"recipe_id": recipe_id, "total_time": 180, "rating": 5, "notes": "Doce e limpa"},
        )
        assert extraction.status_code == 200
        extraction_id = extraction.json()["id"]
        assert extraction.json()["coffee_id"] == coffee_id

        assert client.post("/api/extractions", headers=headers_b, json={"coffee_id": coffee_id, "total_time": 120}).status_code == 400
        assert client.post("/api/extractions", headers=headers_b, json={"recipe_id": recipe_id, "total_time": 120}).status_code == 400

        sensory = client.post(
            "/api/sensory-logs",
            headers=headers_a,
            json={"coffee_id": coffee_id, "extraction_id": extraction_id, "aroma_score": 8, "comments": "Muito floral"},
        )
        assert sensory.status_code == 200

        assert client.post("/api/sensory-logs", headers=headers_b, json={"coffee_id": coffee_id}).status_code == 400
        assert client.post("/api/sensory-logs", headers=headers_b, json={"extraction_id": extraction_id}).status_code == 400


def test_frontend_has_xss_escape_guards():
    app_js = Path("static/js/app.js").read_text(encoding="utf-8")

    assert "function escapeHTML" in app_js
    assert "${escapeHTML(c.name)}" in app_js
    assert "${escapeHTML(r.name)}" in app_js
    assert "${escapeHTML(b.name)}" in app_js
    assert "${escapeHTML(item.title)}" in app_js
    assert "${c.name}" not in app_js
    assert "${r.name}" not in app_js
    assert "${b.name}" not in app_js


def test_pwa_shell_and_production_config_guards(monkeypatch):
    manifest = Path("static/manifest.json").read_text(encoding="utf-8")
    sw = Path("sw.js").read_text(encoding="utf-8")

    assert '"display": "standalone"' in manifest
    assert '"purpose": "any maskable"' in manifest
    assert "coffee-lab-v18.8" in sw
    assert 'url.pathname.startsWith("/api/")' in sw

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./prod.db")
    monkeypatch.setenv("SECRET_KEY", "short")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    get_settings.cache_clear()
    try:
        try:
            validate_runtime_settings()
        except RuntimeError as exc:
            message = str(exc)
            assert "SECRET_KEY" in message
            assert "ALLOWED_ORIGINS" in message
            assert "PUBLIC_BASE_URL" in message
            assert "DATABASE_URL" in message
        else:
            raise AssertionError("production config validation should fail")
    finally:
        monkeypatch.setenv("APP_ENV", "development")
        get_settings.cache_clear()
