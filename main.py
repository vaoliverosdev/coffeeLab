import hashlib
import secrets
import smtplib
import ssl
from io import BytesIO
from email.message import EmailMessage
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional, List
from datetime import date, datetime, timedelta
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy import inspect, text
from sqlalchemy import func
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Query, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from jose import jwt, JWTError
from sqlalchemy.orm import Session, relationship
from sqlalchemy import or_, desc
from pydantic import BaseModel
from core import (
    Base, engine, get_db, hash_password, verify_password, 
    create_access_token, User, UserCreate, UserLogin, 
    UserResponse, Token, ProfileUpdate, PasswordChangeRequest, PasswordRecoveryRequest, PasswordResetRequest,
    EmailVerificationRequest, GoogleLoginRequest, AuthActionResponse, NotificationItem,
    ALGORITHM, get_settings,
    Coffee, CoffeeCreate, CoffeeUpdate, CoffeeResponse,
    Stock, StockUpdate, StockResponse, StockMovement,
    Recipe, RecipeCreate, RecipeUpdate, RecipeResponse, MotorCalculationRequest, MotorCalculationResponse,
    ExtractionResponse, ExtractionCreate, Extraction, SensoryLog, SensoryLogCreate, SensoryLogResponse, 
    SensoryUserProfileResponse, Beverage, BeverageCreate, BeverageResponse,
    Follow, CoffeeReview, CoffeeRating, ActivityFeed, Post, Comment, Like, SavedItem, PublicRecipe,
    CoffeeWishlist, CafeTried, CoffeeGoal, PublicUserSummary, PostCreate, PostResponse,
    CoffeeReviewCreate, CoffeeReviewResponse, CoffeeRatingCreate, CoffeeRatingResponse, CommentCreate, CommentResponse,
    WishlistCreate, WishlistResponse, TriedCoffeeCreate, TriedCoffeeResponse,
    CoffeeGoalCreate, CoffeeGoalResponse, PublicRecipeResponse, ActivityResponse,
)
import httpx
import re

AVATAR_DIR = Path(__file__).parent / "static" / "uploads" / "avatars"
COFFEE_DIR = Path(__file__).parent / "static" / "uploads" / "coffees"
AUTH_RATE_LIMIT: dict[str, list[datetime]] = {}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

def get_allowed_origins() -> list[str]:
    value = get_settings().allowed_origins.strip()
    if not value or value == "*":
        return ["*"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]

def ensure_auth_columns() -> None:
    if engine.dialect.name == "sqlite":
        sqlite_columns = {
            "email_verified": "BOOLEAN NOT NULL DEFAULT 0",
            "email_verification_token_hash": "VARCHAR(128)",
            "email_verification_expires_at": "TIMESTAMP",
            "password_reset_token_hash": "VARCHAR(128)",
            "password_reset_expires_at": "TIMESTAMP",
            "google_sub": "VARCHAR(255)",
            "password_login_enabled": "BOOLEAN NOT NULL DEFAULT 1",
            "username": "VARCHAR(80)",
            "city": "VARCHAR(120)",
            "country": "VARCHAR(120)",
            "favorite_methods": "JSON",
            "favorite_roasteries": "JSON",
            "sensory_preferences": "JSON",
            "mastered_methods": "JSON",
            "barista_setup": "JSON",
            "is_public_profile": "BOOLEAN NOT NULL DEFAULT 0",
            "profile_visibility": "VARCHAR(20) NOT NULL DEFAULT 'private'",
            "diary_visibility": "VARCHAR(20) NOT NULL DEFAULT 'private'",
        }
        with engine.begin() as conn:
            existing = {column["name"] for column in inspect(conn).get_columns("users")}
            for column_name, column_sql in sqlite_columns.items():
                if column_name not in existing:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_sql}"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
            conn.execute(text(
                "UPDATE users SET email_verified = 1 "
                "WHERE email_verified = 0 AND email_verification_token_hash IS NULL"
            ))
        return

    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_token_hash VARCHAR(128)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token_hash VARCHAR(128)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_login_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(80)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS city VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS country VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS favorite_methods JSON",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS favorite_roasteries JSON",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS sensory_preferences JSON",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mastered_methods JSON",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS barista_setup JSON",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_public_profile BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_visibility VARCHAR(20) NOT NULL DEFAULT 'private'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS diary_visibility VARCHAR(20) NOT NULL DEFAULT 'private'",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
        conn.execute(text(
            "UPDATE users SET email_verified = TRUE "
            "WHERE email_verified = FALSE AND email_verification_token_hash IS NULL"
        ))

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_secure_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)

def app_url(path_with_hash: str) -> str:
    base_url = get_settings().public_base_url.rstrip("/")
    return f"{base_url}/{path_with_hash.lstrip('/')}"

def normalize_username(value: str) -> str:
    username = re.sub(r"[^a-z0-9_.]+", "", value.lower().strip())
    username = username.strip("._")
    return username[:30] or "barista"

def generate_unique_username(db: Session, name: str, email: str) -> str:
    base_source = name or email.split("@")[0]
    base = normalize_username(base_source)
    if len(base) < 3:
        base = f"{base}lab"[:30]
    candidate = base
    suffix = 2
    while db.query(User).filter(User.username == candidate).first():
        tail = str(suffix)
        candidate = f"{base[:30 - len(tail)]}{tail}"
        suffix += 1
    return candidate

def clean_profile_list(values: Optional[list]) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in cleaned:
            cleaned.append(item[:80])
    return cleaned[:12]

def clean_barista_setup(value: Optional[dict]) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    allowed = ("grinder", "kettle", "scale", "espresso_machine", "brewers")
    cleaned: dict[str, str] = {}
    for key in allowed:
        item = str(value.get(key) or "").strip()
        if item:
            cleaned[key] = item[:120]
    return cleaned

def user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        username=user.username,
        bio=user.bio,
        avatar_url=user.avatar_url,
        city=user.city,
        country=user.country,
        favorite_methods=clean_profile_list(getattr(user, "favorite_methods", None)),
        favorite_roasteries=clean_profile_list(getattr(user, "favorite_roasteries", None)),
        sensory_preferences=clean_profile_list(getattr(user, "sensory_preferences", None)),
        mastered_methods=clean_profile_list(getattr(user, "mastered_methods", None)),
        barista_setup=clean_barista_setup(getattr(user, "barista_setup", None)),
        is_public_profile=bool(getattr(user, "is_public_profile", False)),
        profile_visibility=getattr(user, "profile_visibility", "public" if getattr(user, "is_public_profile", False) else "private"),
        diary_visibility=getattr(user, "diary_visibility", "private"),
        is_active=bool(user.is_active),
        email_verified=bool(user.email_verified),
        google_connected=bool(user.google_sub),
        password_login_enabled=bool(getattr(user, "password_login_enabled", True)),
    )

def public_user(user: Optional[User]) -> Optional[PublicUserSummary]:
    if not user:
        return None
    return PublicUserSummary(
        id=user.id,
        name=user.name,
        username=user.username,
        avatar_url=user.avatar_url,
    )

def count_target(db: Session, model, target_type: str, target_id: int) -> int:
    return db.query(model).filter(model.target_type == target_type, model.target_id == target_id).count()

def liked_by(db: Session, user_id: Optional[int], target_type: str, target_id: int) -> bool:
    if not user_id:
        return False
    return db.query(Like).filter(
        Like.user_id == user_id,
        Like.target_type == target_type,
        Like.target_id == target_id,
    ).first() is not None

def saved_by(db: Session, user_id: Optional[int], target_type: str, target_id: int) -> bool:
    if not user_id:
        return False
    return db.query(SavedItem).filter(
        SavedItem.user_id == user_id,
        SavedItem.target_type == target_type,
        SavedItem.target_id == target_id,
    ).first() is not None

def validate_limit_offset(limit: int, offset: int, max_limit: int = 100) -> tuple[int, int]:
    return max(1, min(limit, max_limit)), max(0, offset)

def can_view_profile(viewer: Optional[User], target: Optional[User]) -> bool:
    if not target:
        return False
    if viewer and viewer.id == target.id:
        return True
    return bool(getattr(target, "is_public_profile", False) or getattr(target, "profile_visibility", "private") == "public")

def assert_social_target_visible(db: Session, target_type: str, target_id: int, user: User) -> None:
    visible = False
    if target_type == "activity":
        item = db.query(ActivityFeed).filter(ActivityFeed.id == target_id).first()
        visible = bool(item and (item.visibility == "public" or item.user_id == user.id))
    elif target_type == "post":
        item = db.query(Post).filter(Post.id == target_id).first()
        visible = bool(item and (item.visibility == "public" or item.user_id == user.id))
    elif target_type == "review":
        item = db.query(CoffeeReview).filter(CoffeeReview.id == target_id).first()
        visible = bool(item and (item.visibility == "public" or item.user_id == user.id))
    elif target_type == "public_recipe":
        visible = db.query(PublicRecipe.id).filter(PublicRecipe.id == target_id).first() is not None
    elif target_type == "recipe":
        visible = db.query(Recipe.id).filter(Recipe.id == target_id, Recipe.user_id == user.id).first() is not None
    elif target_type == "coffee":
        item = db.query(Coffee).filter(Coffee.id == target_id).first()
        visible = bool(item and (item.user_id == user.id or can_view_profile(user, item.user)))
    elif target_type == "extraction":
        visible = db.query(Extraction.id).filter(Extraction.id == target_id, Extraction.user_id == user.id).first() is not None
    if not visible:
        raise HTTPException(status_code=404, detail="Item social não encontrado ou privado.")

def create_activity(
    db: Session,
    user: User,
    verb: str,
    target_type: str,
    target_id: Optional[int],
    summary: str,
    visibility: str = "public",
) -> ActivityFeed:
    activity = ActivityFeed(
        user_id=user.id,
        verb=verb,
        target_type=target_type,
        target_id=target_id,
        summary=summary[:255],
        visibility=visibility,
    )
    db.add(activity)
    return activity

def activity_to_response(db: Session, activity: ActivityFeed, current_user_id: Optional[int] = None) -> ActivityResponse:
    return ActivityResponse(
        id=activity.id,
        user_id=activity.user_id,
        verb=activity.verb,
        target_type=activity.target_type,
        target_id=activity.target_id,
        summary=activity.summary,
        visibility=activity.visibility,
        created_at=activity.created_at,
        user=public_user(activity.user),
        likes_count=count_target(db, Like, "activity", activity.id),
        comments_count=count_target(db, Comment, "activity", activity.id),
        liked_by_me=liked_by(db, current_user_id, "activity", activity.id),
    )

def post_to_response(db: Session, post: Post, current_user_id: Optional[int] = None) -> PostResponse:
    return PostResponse(
        id=post.id,
        user_id=post.user_id,
        content=post.content,
        image_url=post.image_url,
        visibility=post.visibility,
        created_at=post.created_at,
        user=public_user(post.user),
        likes_count=count_target(db, Like, "post", post.id),
        comments_count=count_target(db, Comment, "post", post.id),
        liked_by_me=liked_by(db, current_user_id, "post", post.id),
    )

def review_to_response(db: Session, review: CoffeeReview, current_user_id: Optional[int] = None) -> CoffeeReviewResponse:
    return CoffeeReviewResponse(
        id=review.id,
        user_id=review.user_id,
        coffee_id=review.coffee_id,
        title=review.title,
        body=review.body,
        rating=review.rating,
        visibility=review.visibility,
        created_at=review.created_at,
        user=public_user(review.user),
        coffee=review.coffee,
        likes_count=count_target(db, Like, "review", review.id),
        comments_count=count_target(db, Comment, "review", review.id),
        liked_by_me=liked_by(db, current_user_id, "review", review.id),
    )

def rating_to_response(rating: CoffeeRating) -> CoffeeRatingResponse:
    return CoffeeRatingResponse(
        id=rating.id,
        user_id=rating.user_id,
        coffee_id=rating.coffee_id,
        coffee_name=rating.coffee_name,
        rating=rating.rating,
        scale=rating.scale,
        visibility=rating.visibility,
        created_at=rating.created_at,
        user=public_user(rating.user),
        coffee=rating.coffee,
    )

def public_recipe_to_response(db: Session, item: PublicRecipe, current_user_id: Optional[int] = None) -> PublicRecipeResponse:
    return PublicRecipeResponse(
        id=item.id,
        user_id=item.user_id,
        recipe_id=item.recipe_id,
        title=item.title,
        description=item.description,
        created_at=item.created_at,
        user=public_user(item.user),
        recipe=item.recipe,
        likes_count=count_target(db, Like, "public_recipe", item.id),
        saves_count=count_target(db, SavedItem, "public_recipe", item.id),
        saved_by_me=saved_by(db, current_user_id, "public_recipe", item.id),
    )

async def fetch_google_profile(credential: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Credencial do Google inválida.")
    return response.json()

def validate_google_profile(profile: dict) -> tuple[str, str, str, Optional[str]]:
    settings = get_settings()
    if profile.get("aud") != settings.google_client_id:
        raise HTTPException(status_code=401, detail="Credencial do Google não pertence a este app.")
    if profile.get("email_verified") not in ("true", True):
        raise HTTPException(status_code=401, detail="O Google não confirmou este e-mail.")

    email = str(profile.get("email") or "").strip().lower()
    google_sub = str(profile.get("sub") or "").strip()
    name = str(profile.get("name") or email.split("@")[0] or "Barista").strip()
    avatar_url = profile.get("picture")
    if not email or not google_sub:
        raise HTTPException(status_code=401, detail="Perfil do Google incompleto.")
    return email, google_sub, name, avatar_url

def resolve_google_user(
    db: Session,
    email: str,
    google_sub: str,
    name: str,
    avatar_url: Optional[str],
) -> User:
    user_by_sub = db.query(User).filter(User.google_sub == google_sub).first()
    user_by_email = db.query(User).filter(User.email == email).first()

    if user_by_sub and user_by_email and user_by_sub.id != user_by_email.id:
        raise HTTPException(
            status_code=409,
            detail="Esta conta Google já está vinculada a outro perfil.",
        )

    if user_by_sub:
        if user_by_sub.email != email:
            raise HTTPException(
                status_code=409,
                detail="O e-mail desta conta Google mudou. Entre em contato para revisar o vínculo.",
            )
        user = user_by_sub
    elif user_by_email:
        user = user_by_email
        user.google_sub = google_sub
    else:
        user = User(
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            name=name,
            username=generate_unique_username(db, name, email),
            avatar_url=avatar_url,
            is_active=True,
            email_verified=True,
            google_sub=google_sub,
            password_login_enabled=False,
        )
        db.add(user)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta indisponível.")

    user.email_verified = True
    if avatar_url and not user.avatar_url:
        user.avatar_url = avatar_url
    if not user.name:
        user.name = name
    return user

def smtp_is_configured() -> bool:
    settings = get_settings()
    return all([
        settings.smtp_host,
        settings.smtp_username,
        settings.smtp_password,
        settings.smtp_from_email,
    ])

def send_email(to_email: str, subject: str, text_body: str) -> bool:
    settings = get_settings()
    if not smtp_is_configured():
        print(f"[Auth] SMTP nao configurado. E-mail nao enviado para {to_email}.")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to_email
    message.set_content(text_body)

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.starttls(context=context)
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
    return True

def send_verification_email(user: User, token: str) -> bool:
    verify_url = app_url(f"#/verify-email?token={token}")
    return send_email(
        user.email,
        "Verifique seu e-mail no Coffee Lab",
        (
            f"Oi, {user.name}!\n\n"
            "Clique no link abaixo para verificar seu e-mail no Coffee Lab:\n"
            f"{verify_url}\n\n"
            "Este link expira em 24 horas."
        ),
    )

def send_password_reset_email(user: User, token: str) -> bool:
    reset_url = app_url(f"#/reset-password?token={token}")
    return send_email(
        user.email,
        "Recuperacao de senha do Coffee Lab",
        (
            f"Oi, {user.name}!\n\n"
            "Clique no link abaixo para criar uma nova senha:\n"
            f"{reset_url}\n\n"
            "Este link expira em 1 hora. Se voce nao pediu isso, ignore este e-mail."
        ),
    )

def check_auth_rate_limit(request: Request, scope: str, limit: int = 8, minutes: int = 15) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"{scope}:{client_ip}"
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=minutes)
    attempts = [attempt for attempt in AUTH_RATE_LIMIT.get(key, []) if attempt > window_start]
    if len(attempts) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.",
        )
    attempts.append(now)
    AUTH_RATE_LIMIT[key] = attempts

async def read_valid_image_upload(file: UploadFile) -> tuple[bytes, str]:
    if file.content_type and file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="Envie uma imagem JPG, PNG ou WebP.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Envie uma imagem válida.")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Imagem muito grande. O limite é 5 MB.")

    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            image_format = image.format
            width, height = image.size
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Arquivo de imagem inválido.")

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise HTTPException(status_code=400, detail="Formato de imagem não suportado.")
    if width * height > MAX_IMAGE_PIXELS:
        raise HTTPException(status_code=400, detail="Imagem muito grande em resolução.")

    return content, ALLOWED_IMAGE_FORMATS[image_format]

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_auth_columns()
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    COFFEE_DIR.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title="Coffee Lab", version="0.5.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=get_allowed_origins() != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

async def get_current_user(db: Session = Depends(get_db), token: str = None):
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None: 
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada")
    user = db.query(User).filter(User.email == email).first()
    if user is None: 
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user

def get_token_from_header(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "): 
        return None
    return authorization.split(" ")[1]

# --- ENDPOINTS DE AUTENTICAÇÃO ---
@app.get("/api/auth/config")
def auth_config():
    return {"google_client_id": get_settings().google_client_id}

@app.post("/api/auth/register", response_model=AuthActionResponse)
def register(user_in: UserCreate, request: Request, db: Session = Depends(get_db)):
    check_auth_rate_limit(request, "register", limit=5, minutes=20)
    normalized_email = user_in.email.lower()
    if db.query(User).filter(User.email == normalized_email).first():
        raise HTTPException(status_code=400, detail="E-mail existente.")

    token, token_hash = create_secure_token()
    u = User(
        email=normalized_email,
        hashed_password=hash_password(user_in.password),
        name=user_in.name.strip(),
        username=generate_unique_username(db, user_in.name, normalized_email),
        email_verified=False,
        password_login_enabled=True,
        email_verification_token_hash=token_hash,
        email_verification_expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    sent = send_verification_email(u, token)
    response = {
        "detail": "Conta criada. Verifique seu e-mail para liberar o acesso."
        if sent
        else "Conta criada. Configure o SMTP para enviar o e-mail de verificação.",
    }
    if get_settings().app_env == "development" and not sent:
        response["dev_verification_url"] = app_url(f"#/verify-email?token={token}")
    return response

@app.post("/api/auth/login", response_model=Token)
def login(credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    check_auth_rate_limit(request, "login", limit=10, minutes=15)
    u = db.query(User).filter(User.email == credentials.email.lower()).first()
    if not u:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    if not verify_password(credentials.password, u.hashed_password):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    if not u.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Verifique seu e-mail antes de entrar. Use o link enviado ou solicite um novo.",
        )
    if not getattr(u, "password_login_enabled", True):
        raise HTTPException(
            status_code=401,
            detail="Esta conta usa Google. Defina uma senha pelo perfil ou recuperação para entrar com e-mail.",
        )
    return {
        "access_token": create_access_token(data={"sub": u.email}),
        "token_type": "bearer",
        "user": user_to_response(u),
    }

@app.post("/api/auth/resend-verification", response_model=AuthActionResponse)
def resend_verification(req: PasswordRecoveryRequest, request: Request, db: Session = Depends(get_db)):
    check_auth_rate_limit(request, "resend-verification", limit=5, minutes=20)
    user = db.query(User).filter(User.email == req.email.lower()).first()
    response = {"detail": "Se este e-mail estiver cadastrado e pendente, enviaremos um novo link."}
    if not user or user.email_verified:
        return response

    token, token_hash = create_secure_token()
    user.email_verification_token_hash = token_hash
    user.email_verification_expires_at = datetime.utcnow() + timedelta(hours=24)
    db.commit()

    sent = send_verification_email(user, token)
    if get_settings().app_env == "development" and not sent:
        response["dev_verification_url"] = app_url(f"#/verify-email?token={token}")
    return response

@app.post("/api/auth/verify-email", response_model=AuthActionResponse)
def verify_email(req: EmailVerificationRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(req.token)
    user = db.query(User).filter(User.email_verification_token_hash == token_hash).first()
    if not user:
        raise HTTPException(status_code=400, detail="Link de verificação inválido.")
    if user.email_verification_expires_at and user.email_verification_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Link de verificação expirado. Solicite um novo.")

    user.email_verified = True
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    db.commit()
    return {"detail": "E-mail verificado com sucesso. Agora você já pode entrar."}

@app.post("/api/auth/recover", response_model=AuthActionResponse)
def recover_password(req: PasswordRecoveryRequest, request: Request, db: Session = Depends(get_db)):
    check_auth_rate_limit(request, "recover", limit=5, minutes=20)
    user = db.query(User).filter(User.email == req.email.lower()).first()
    response = {"detail": "Se este e-mail estiver cadastrado, as instruções de recuperação serão enviadas."}
    if not user:
        return response

    token, token_hash = create_secure_token()
    user.password_reset_token_hash = token_hash
    user.password_reset_expires_at = datetime.utcnow() + timedelta(hours=1)
    db.commit()

    sent = send_password_reset_email(user, token)
    if get_settings().app_env == "development" and not sent:
        response["dev_reset_url"] = app_url(f"#/reset-password?token={token}")
    return response

@app.post("/api/auth/reset-password", response_model=AuthActionResponse)
def reset_password(req: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    check_auth_rate_limit(request, "reset-password", limit=8, minutes=20)
    token_hash = hash_token(req.token)
    user = db.query(User).filter(User.password_reset_token_hash == token_hash).first()
    if not user:
        raise HTTPException(status_code=400, detail="Link de recuperação inválido.")
    if user.password_reset_expires_at and user.password_reset_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Link de recuperação expirado. Solicite um novo.")

    user.hashed_password = hash_password(req.password)
    user.password_login_enabled = True
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    user.email_verified = True
    db.commit()
    return {"detail": "Senha atualizada com sucesso. Entre usando a nova senha."}

@app.post("/api/auth/google", response_model=Token)
async def google_login(req: GoogleLoginRequest, request: Request, db: Session = Depends(get_db)):
    check_auth_rate_limit(request, "google-login", limit=12, minutes=15)
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=400, detail="Login com Google não configurado.")

    profile = await fetch_google_profile(req.credential)
    email, google_sub, name, avatar_url = validate_google_profile(profile)
    user = resolve_google_user(db, email, google_sub, name, avatar_url)
    db.commit()
    db.refresh(user)
    return {
        "access_token": create_access_token(data={"sub": user.email}),
        "token_type": "bearer",
        "user": user_to_response(user),
    }

@app.post("/api/auth/me/google", response_model=UserResponse)
async def connect_google(
    req: GoogleLoginRequest,
    request: Request,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    check_auth_rate_limit(request, "google-connect", limit=8, minutes=15)
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(status_code=400, detail="Login com Google não configurado.")

    current_user = await get_current_user(db, token=authorization)
    profile = await fetch_google_profile(req.credential)
    email, google_sub, _name, avatar_url = validate_google_profile(profile)
    if current_user.email != email:
        raise HTTPException(
            status_code=409,
            detail="A conta Google precisa usar o mesmo e-mail do seu perfil para ser conectada.",
        )

    linked_user = db.query(User).filter(User.google_sub == google_sub, User.id != current_user.id).first()
    if linked_user:
        raise HTTPException(status_code=409, detail="Esta conta Google já está vinculada a outro perfil.")

    current_user.google_sub = google_sub
    current_user.email_verified = True
    if avatar_url and not current_user.avatar_url:
        current_user.avatar_url = avatar_url
    db.commit()
    db.refresh(current_user)
    return user_to_response(current_user)

@app.delete("/api/auth/me/google", response_model=UserResponse)
async def disconnect_google(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    current_user = await get_current_user(db, token=authorization)
    if not current_user.google_sub:
        return user_to_response(current_user)
    if not getattr(current_user, "password_login_enabled", True):
        raise HTTPException(
            status_code=400,
            detail="Defina uma senha antes de desconectar o Google.",
        )

    current_user.google_sub = None
    db.commit()
    db.refresh(current_user)
    return user_to_response(current_user)

@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    return user_to_response(await get_current_user(db, token=authorization))

@app.put("/api/auth/me", response_model=UserResponse)
async def update_profile(profile_data: ProfileUpdate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    if profile_data.name: u.name = profile_data.name.strip()[:120]
    if profile_data.username:
        username = normalize_username(profile_data.username)
        if len(username) < 3:
            raise HTTPException(status_code=422, detail="Username precisa ter pelo menos 3 caracteres.")
        existing = db.query(User).filter(User.username == username, User.id != u.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Este username já está em uso.")
        u.username = username
    if profile_data.bio is not None: u.bio = profile_data.bio
    if profile_data.city is not None: u.city = profile_data.city.strip()[:120] or None
    if profile_data.country is not None: u.country = profile_data.country.strip()[:120] or None
    if profile_data.favorite_methods is not None:
        u.favorite_methods = clean_profile_list(profile_data.favorite_methods)
    if profile_data.favorite_roasteries is not None:
        u.favorite_roasteries = clean_profile_list(profile_data.favorite_roasteries)
    if profile_data.sensory_preferences is not None:
        u.sensory_preferences = clean_profile_list(profile_data.sensory_preferences)
    if profile_data.mastered_methods is not None:
        u.mastered_methods = clean_profile_list(profile_data.mastered_methods)
    if profile_data.barista_setup is not None:
        u.barista_setup = clean_barista_setup(profile_data.barista_setup)
    if profile_data.is_public_profile is not None:
        u.is_public_profile = bool(profile_data.is_public_profile)
        u.profile_visibility = "public" if u.is_public_profile else "private"
    if profile_data.profile_visibility is not None:
        visibility = "public" if profile_data.profile_visibility == "public" else "private"
        u.profile_visibility = visibility
        u.is_public_profile = visibility == "public"
    if profile_data.diary_visibility is not None:
        u.diary_visibility = "public" if profile_data.diary_visibility == "public" else "private"
    db.commit(); db.refresh(u)
    return user_to_response(u)

@app.get("/api/users/{username}/profile")
async def get_public_profile(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == normalize_username(username)).first()
    if not user or (not user.is_public_profile and getattr(user, "profile_visibility", "private") != "public"):
        raise HTTPException(status_code=404, detail="Perfil público não encontrado.")

    coffees = db.query(Coffee).filter(Coffee.user_id == user.id).all()
    recipes = db.query(Recipe).filter(Recipe.user_id == user.id).all()
    extractions = db.query(Extraction).filter(Extraction.user_id == user.id).all()
    sensory_logs = db.query(SensoryLog).filter(SensoryLog.user_id == user.id).order_by(desc(SensoryLog.created_at)).all()
    ratings = db.query(CoffeeRating).filter(CoffeeRating.user_id == user.id, CoffeeRating.visibility == "public").order_by(desc(CoffeeRating.created_at)).limit(24).all()
    tried = db.query(CafeTried).filter(CafeTried.user_id == user.id).order_by(desc(CafeTried.tried_at)).limit(24).all()
    wishlist = db.query(CoffeeWishlist).filter(CoffeeWishlist.user_id == user.id).order_by(desc(CoffeeWishlist.created_at)).limit(24).all()
    posts = db.query(Post).filter(Post.user_id == user.id, Post.visibility == "public").order_by(desc(Post.created_at)).limit(12).all()
    public_recipes = db.query(PublicRecipe).filter(PublicRecipe.user_id == user.id).order_by(desc(PublicRecipe.created_at)).limit(12).all()
    activities = db.query(ActivityFeed).filter(ActivityFeed.user_id == user.id, ActivityFeed.visibility == "public").order_by(desc(ActivityFeed.created_at)).limit(20).all()

    from collections import Counter
    method_counts = Counter(recipe.method for recipe in recipes if recipe.method)
    origin_counts = Counter(coffee.origin for coffee in coffees if coffee.origin)
    note_counts: Counter[str] = Counter()
    for log in sensory_logs:
        if log.perceived_notes:
            note_counts.update(note.strip().capitalize() for note in re.split(r"[,;]", log.perceived_notes) if note.strip())
    extraction_days = {ext.extraction_date.date() for ext in extractions if ext.extraction_date}
    streak = 0
    day = datetime.utcnow().date()
    while day in extraction_days:
        streak += 1
        day -= timedelta(days=1)
    recipe_by_id = {recipe.id: recipe for recipe in recipes}
    grams_prepared = round(sum(float(recipe_by_id.get(ext.recipe_id).coffee_weight or 0) for ext in extractions if ext.recipe_id in recipe_by_id), 1)
    followers_count = db.query(Follow).filter(Follow.following_id == user.id).count()
    following_count = db.query(Follow).filter(Follow.follower_id == user.id).count()
    goals = db.query(CoffeeGoal).filter(CoffeeGoal.user_id == user.id).order_by(desc(CoffeeGoal.created_at)).limit(8).all()
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_extractions = [ext for ext in extractions if ext.extraction_date and ext.extraction_date >= month_start]
    roastery_counts = Counter(coffee.roastery for coffee in coffees if coffee.roastery)
    stock_items = db.query(Stock).join(Coffee).filter(Coffee.user_id == user.id).all()
    grams_consumed = round(sum(abs(m.quantity_changed) for item in stock_items for m in item.movements if m.quantity_changed < 0), 1)
    diary_is_public = getattr(user, "diary_visibility", "private") == "public"
    mastered_methods = clean_profile_list(getattr(user, "mastered_methods", None)) or [
        method for method, total in method_counts.most_common(8) if total >= 2
    ]

    return {
        "name": user.name,
        "username": user.username,
        "bio": user.bio,
        "avatar_url": user.avatar_url,
        "city": user.city,
        "country": user.country,
        "favorite_methods": clean_profile_list(user.favorite_methods),
        "favorite_roasteries": clean_profile_list(user.favorite_roasteries),
        "sensory_preferences": clean_profile_list(user.sensory_preferences),
        "mastered_methods": mastered_methods,
        "diary_visibility": getattr(user, "diary_visibility", "private"),
        "barista_setup": clean_barista_setup(getattr(user, "barista_setup", None)),
        "stats": {
            "coffees": db.query(Coffee).filter(Coffee.user_id == user.id).count(),
            "recipes": db.query(Recipe).filter(Recipe.user_id == user.id).count(),
            "extractions": db.query(Extraction).filter(Extraction.user_id == user.id).count(),
            "sensory_logs": db.query(SensoryLog).filter(SensoryLog.user_id == user.id).count(),
            "cafes_tried": db.query(CafeTried).filter(CafeTried.user_id == user.id).count(),
            "coffee_ratings": db.query(CoffeeRating).filter(CoffeeRating.user_id == user.id).count(),
            "grams_prepared": grams_prepared,
            "grams_consumed": grams_consumed,
            "cups_extracted": len(extractions),
            "cups_this_month": len(month_extractions),
            "methods_used": len(method_counts),
            "mastered_methods": len(mastered_methods),
            "roasteries_explored": len(roastery_counts),
            "origins_explored": len(origin_counts),
            "open_coffees": sum(1 for item in stock_items if item.is_opened),
            "followers": followers_count,
            "following": following_count,
            "current_streak_days": streak,
            "favorite_method": method_counts.most_common(1)[0][0] if method_counts else None,
            "top_origin": origin_counts.most_common(1)[0][0] if origin_counts else None,
            "top_sensory_notes": [item[0] for item in note_counts.most_common(6)],
            "top_roasteries": [item[0] for item in roastery_counts.most_common(6)],
        },
        "tabs": {
            "overview": [activity_to_response(db, activity).model_dump(mode="json") for activity in activities[:6]],
            "cafes_tried": [TriedCoffeeResponse.model_validate(item).model_dump(mode="json") for item in tried],
            "ratings": [rating_to_response(item).model_dump(mode="json") for item in ratings],
            "recipes": [public_recipe_to_response(db, item).model_dump(mode="json") for item in public_recipes],
            "sensory": [SensoryLogResponse.model_validate(log).model_dump(mode="json") for log in sensory_logs[:12]] if diary_is_public else [],
            "feed": [activity_to_response(db, activity).model_dump(mode="json") for activity in activities],
            "favorites": [],
            "wishlist": [WishlistResponse.model_validate(item).model_dump(mode="json") for item in wishlist],
            "goals": [CoffeeGoalResponse.model_validate(goal).model_dump(mode="json") for goal in goals],
        },
    }

@app.put("/api/auth/me/password", response_model=AuthActionResponse)
async def change_password(
    req: PasswordChangeRequest,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    u = await get_current_user(db, token=authorization)
    if getattr(u, "password_login_enabled", True) and not req.current_password:
        raise HTTPException(status_code=401, detail="Informe sua senha atual.")
    if getattr(u, "password_login_enabled", True) and not verify_password(req.current_password, u.hashed_password):
        raise HTTPException(status_code=401, detail="Senha atual incorreta.")
    if getattr(u, "password_login_enabled", True) and verify_password(req.new_password, u.hashed_password):
        raise HTTPException(status_code=400, detail="A nova senha precisa ser diferente da senha atual.")

    u.hashed_password = hash_password(req.new_password)
    u.password_login_enabled = True
    u.password_reset_token_hash = None
    u.password_reset_expires_at = None
    db.commit()
    return {"detail": "Senha alterada com sucesso."}


# --- ENDPOINTS SOCIAIS (REDE DE CAFÉS) ---
@app.get("/api/social/feed", response_model=List[ActivityResponse])
async def get_social_feed(
    filter: str = Query("general", pattern="^(general|following|mine|popular_coffees|popular_recipes)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    limit, offset = validate_limit_offset(limit, offset)
    query = db.query(ActivityFeed).filter(ActivityFeed.visibility == "public")
    if filter == "mine":
        query = query.filter(ActivityFeed.user_id == user.id)
    elif filter == "following":
        following_ids = [row.following_id for row in db.query(Follow).filter(Follow.follower_id == user.id).all()]
        if not following_ids:
            return []
        query = query.filter(ActivityFeed.user_id.in_(following_ids))
    elif filter == "popular_coffees":
        query = query.filter(ActivityFeed.target_type.in_(["coffee", "review", "rating", "tried"]))
    elif filter == "popular_recipes":
        query = query.filter(ActivityFeed.target_type.in_(["recipe", "public_recipe"]))
    activities = query.order_by(desc(ActivityFeed.created_at)).offset(offset).limit(limit).all()
    return [activity_to_response(db, activity, user.id) for activity in activities]


@app.post("/api/social/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_social_post(
    payload: PostCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    visibility = "private" if payload.visibility == "private" else "public"
    post = Post(
        user_id=user.id,
        content=payload.content.strip(),
        image_url=payload.image_url,
        visibility=visibility,
    )
    db.add(post)
    db.flush()
    create_activity(db, user, "publicou", "post", post.id, f"{user.name} publicou sobre café.", visibility)
    db.commit()
    db.refresh(post)
    return post_to_response(db, post, user.id)


@app.post("/api/social/reviews", response_model=CoffeeReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_coffee_review(
    payload: CoffeeReviewCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    coffee = None
    if payload.coffee_id:
        coffee = db.query(Coffee).filter(Coffee.id == payload.coffee_id, Coffee.user_id == user.id).first()
        if not coffee:
            raise HTTPException(status_code=404, detail="Café não encontrado.")
    visibility = "private" if payload.visibility == "private" else "public"
    review = CoffeeReview(
        user_id=user.id,
        coffee_id=payload.coffee_id,
        title=payload.title.strip(),
        body=payload.body,
        rating=payload.rating,
        visibility=visibility,
    )
    db.add(review)
    db.flush()
    target_name = coffee.name if coffee else payload.title
    create_activity(db, user, "avaliou", "review", review.id, f"{user.name} avaliou {target_name} com {payload.rating:g}/5.", visibility)
    db.commit()
    db.refresh(review)
    return review_to_response(db, review, user.id)


@app.post("/api/social/ratings", response_model=CoffeeRatingResponse, status_code=status.HTTP_201_CREATED)
async def create_coffee_rating(
    payload: CoffeeRatingCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    data = payload.model_dump()
    coffee = None
    if payload.coffee_id:
        coffee = db.query(Coffee).filter(Coffee.id == payload.coffee_id, Coffee.user_id == user.id).first()
        if not coffee:
            raise HTTPException(status_code=404, detail="Café não encontrado.")
        data["coffee_name"] = coffee.name
    visibility = "private" if payload.visibility == "private" else "public"
    scale = "hundred" if payload.scale == "hundred" else "five"
    if scale == "five" and not 1 <= payload.rating <= 5:
        raise HTTPException(status_code=422, detail="Notas na escala 1 a 5 precisam ficar entre 1 e 5.")
    rating = CoffeeRating(
        user_id=user.id,
        coffee_id=data.get("coffee_id"),
        coffee_name=data["coffee_name"].strip(),
        rating=data["rating"],
        scale=scale,
        visibility=visibility,
    )
    db.add(rating)
    db.flush()
    scale_label = "/100" if scale == "hundred" else "/5"
    create_activity(db, user, "deu nota", "rating", rating.id, f"{user.name} deu nota {rating.rating:g}{scale_label} para {rating.coffee_name}.", visibility)
    db.commit()
    db.refresh(rating)
    return rating_to_response(rating)


@app.post("/api/social/follow/{username}")
async def follow_user(
    username: str,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    target = db.query(User).filter(User.username == normalize_username(username), User.is_public_profile == True).first()
    if not target:
        raise HTTPException(status_code=404, detail="Perfil público não encontrado.")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Você não pode seguir seu próprio perfil.")
    existing = db.query(Follow).filter(Follow.follower_id == user.id, Follow.following_id == target.id).first()
    if not existing:
        db.add(Follow(follower_id=user.id, following_id=target.id))
        create_activity(db, user, "seguiu", "user", target.id, f"{user.name} começou a seguir {target.name}.")
        db.commit()
    return {"following": True}


@app.delete("/api/social/follow/{username}")
async def unfollow_user(
    username: str,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    target = db.query(User).filter(User.username == normalize_username(username)).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    existing = db.query(Follow).filter(Follow.follower_id == user.id, Follow.following_id == target.id).first()
    if existing:
        db.delete(existing)
        db.commit()
    return {"following": False}


@app.get("/api/social/users/{username}/followers", response_model=List[PublicUserSummary])
async def list_followers(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    viewer = await get_current_user(db, token=authorization)
    target = db.query(User).filter(User.username == normalize_username(username)).first()
    if not can_view_profile(viewer, target):
        raise HTTPException(status_code=404, detail="Perfil público não encontrado.")
    limit, offset = validate_limit_offset(limit, offset)
    rows = (
        db.query(User)
        .join(Follow, Follow.follower_id == User.id)
        .filter(Follow.following_id == target.id, User.is_active == True)
        .order_by(User.name)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [public_user(user) for user in rows]


@app.get("/api/social/users/{username}/following", response_model=List[PublicUserSummary])
async def list_following(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    viewer = await get_current_user(db, token=authorization)
    target = db.query(User).filter(User.username == normalize_username(username)).first()
    if not can_view_profile(viewer, target):
        raise HTTPException(status_code=404, detail="Perfil público não encontrado.")
    limit, offset = validate_limit_offset(limit, offset)
    rows = (
        db.query(User)
        .join(Follow, Follow.following_id == User.id)
        .filter(Follow.follower_id == target.id, User.is_active == True)
        .order_by(User.name)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [public_user(user) for user in rows]


@app.get("/api/social/users/{username}/activities", response_model=List[ActivityResponse])
async def list_user_activities(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    viewer = await get_current_user(db, token=authorization)
    target = db.query(User).filter(User.username == normalize_username(username)).first()
    if not can_view_profile(viewer, target):
        raise HTTPException(status_code=404, detail="Perfil público não encontrado.")
    limit, offset = validate_limit_offset(limit, offset)
    query = db.query(ActivityFeed).filter(ActivityFeed.user_id == target.id)
    if viewer.id != target.id:
        query = query.filter(ActivityFeed.visibility == "public")
    activities = query.order_by(desc(ActivityFeed.created_at)).offset(offset).limit(limit).all()
    return [activity_to_response(db, activity, viewer.id) for activity in activities]


@app.post("/api/social/{target_type}/{target_id}/like")
async def toggle_like(
    target_type: str,
    target_id: int,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    if target_type not in {"activity", "post", "review", "public_recipe", "recipe", "coffee"}:
        raise HTTPException(status_code=400, detail="Tipo de item inválido.")
    assert_social_target_visible(db, target_type, target_id, user)
    existing = db.query(Like).filter(Like.user_id == user.id, Like.target_type == target_type, Like.target_id == target_id).first()
    liked = existing is None
    if existing:
        db.delete(existing)
    else:
        db.add(Like(user_id=user.id, target_type=target_type, target_id=target_id))
    db.commit()
    return {"liked": liked, "likes_count": count_target(db, Like, target_type, target_id)}


@app.get("/api/social/{target_type}/{target_id}/comments", response_model=List[CommentResponse])
async def list_comments(
    target_type: str,
    target_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    assert_social_target_visible(db, target_type, target_id, user)
    limit, offset = validate_limit_offset(limit, offset)
    comments = db.query(Comment).filter(Comment.target_type == target_type, Comment.target_id == target_id).order_by(Comment.created_at).offset(offset).limit(limit).all()
    return [
        CommentResponse(
            id=item.id,
            user_id=item.user_id,
            target_type=item.target_type,
            target_id=item.target_id,
            body=item.body,
            created_at=item.created_at,
            user=public_user(item.user),
        )
        for item in comments
    ]


@app.post("/api/social/{target_type}/{target_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    target_type: str,
    target_id: int,
    payload: CommentCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    if target_type not in {"activity", "post", "review", "public_recipe", "recipe", "coffee", "extraction"}:
        raise HTTPException(status_code=400, detail="Tipo de item inválido.")
    assert_social_target_visible(db, target_type, target_id, user)
    comment = Comment(user_id=user.id, target_type=target_type, target_id=target_id, body=payload.body.strip())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return CommentResponse(
        id=comment.id,
        user_id=comment.user_id,
        target_type=comment.target_type,
        target_id=comment.target_id,
        body=comment.body,
        created_at=comment.created_at,
        user=public_user(user),
    )


@app.delete("/api/social/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentário não encontrado.")
    owns_parent = False
    if comment.target_type == "activity":
        owns_parent = db.query(ActivityFeed.id).filter(ActivityFeed.id == comment.target_id, ActivityFeed.user_id == user.id).first() is not None
    elif comment.target_type == "post":
        owns_parent = db.query(Post.id).filter(Post.id == comment.target_id, Post.user_id == user.id).first() is not None
    elif comment.target_type == "review":
        owns_parent = db.query(CoffeeReview.id).filter(CoffeeReview.id == comment.target_id, CoffeeReview.user_id == user.id).first() is not None
    elif comment.target_type == "public_recipe":
        owns_parent = db.query(PublicRecipe.id).filter(PublicRecipe.id == comment.target_id, PublicRecipe.user_id == user.id).first() is not None
    if comment.user_id != user.id and not owns_parent:
        raise HTTPException(status_code=403, detail="Você não tem permissão para remover este comentário.")
    db.delete(comment)
    db.commit()
    return {"detail": "Comentário removido."}


@app.post("/api/social/{target_type}/{target_id}/save")
async def toggle_saved_item(
    target_type: str,
    target_id: int,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    if target_type not in {"public_recipe", "recipe", "coffee", "review", "post"}:
        raise HTTPException(status_code=400, detail="Tipo de item inválido.")
    existing = db.query(SavedItem).filter(SavedItem.user_id == user.id, SavedItem.target_type == target_type, SavedItem.target_id == target_id).first()
    saved = existing is None
    if existing:
        db.delete(existing)
    else:
        db.add(SavedItem(user_id=user.id, target_type=target_type, target_id=target_id))
    db.commit()
    return {"saved": saved, "saves_count": count_target(db, SavedItem, target_type, target_id)}


@app.post("/api/social/recipes/{recipe_id}/share", response_model=PublicRecipeResponse)
async def share_recipe_publicly(
    recipe_id: int,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.user_id == user.id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    item = db.query(PublicRecipe).filter(PublicRecipe.user_id == user.id, PublicRecipe.recipe_id == recipe.id).first()
    if not item:
        item = PublicRecipe(user_id=user.id, recipe_id=recipe.id, title=recipe.name, description=recipe.description)
        db.add(item)
        db.flush()
        create_activity(db, user, "compartilhou", "public_recipe", item.id, f"{user.name} compartilhou a receita {recipe.name}.")
        db.commit()
        db.refresh(item)
    return public_recipe_to_response(db, item, user.id)


@app.get("/api/social/public-recipes", response_model=List[PublicRecipeResponse])
async def list_public_recipes(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    limit, offset = validate_limit_offset(limit, offset)
    items = db.query(PublicRecipe).order_by(desc(PublicRecipe.created_at)).offset(offset).limit(limit).all()
    return [public_recipe_to_response(db, item, user.id) for item in items]


@app.delete("/api/social/public-recipes/{public_recipe_id}")
async def unpublish_recipe(
    public_recipe_id: int,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    item = db.query(PublicRecipe).filter(PublicRecipe.id == public_recipe_id, PublicRecipe.user_id == user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Receita pública não encontrada.")
    db.query(SavedItem).filter(SavedItem.target_type == "public_recipe", SavedItem.target_id == item.id).delete()
    db.query(Like).filter(Like.target_type == "public_recipe", Like.target_id == item.id).delete()
    db.query(Comment).filter(Comment.target_type == "public_recipe", Comment.target_id == item.id).delete()
    db.query(ActivityFeed).filter(ActivityFeed.target_type == "public_recipe", ActivityFeed.target_id == item.id, ActivityFeed.user_id == user.id).delete()
    db.delete(item)
    db.commit()
    return {"detail": "Receita despublicada."}


@app.post("/api/social/public-recipes/{public_recipe_id}/copy", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def copy_public_recipe(
    public_recipe_id: int,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    item = db.query(PublicRecipe).filter(PublicRecipe.id == public_recipe_id).first()
    if not item or not item.recipe:
        raise HTTPException(status_code=404, detail="Receita pública não encontrada.")
    source = item.recipe
    copy = Recipe(
        user_id=user.id,
        coffee_id=None,
        name=f"{source.name} (copiada)",
        method=source.method,
        coffee_weight=source.coffee_weight,
        water_weight=source.water_weight,
        grind_size=source.grind_size,
        water_temp=source.water_temp,
        description=source.description,
        steps=source.steps,
        is_favorite=False,
    )
    db.add(copy)
    db.flush()
    db.add(SavedItem(user_id=user.id, target_type="public_recipe", target_id=item.id))
    create_activity(db, user, "salvou", "recipe", copy.id, f"{user.name} copiou a receita {source.name}.")
    db.commit()
    db.refresh(copy)
    return copy


@app.get("/api/social/wishlist", response_model=List[WishlistResponse])
async def list_wishlist(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    limit, offset = validate_limit_offset(limit, offset)
    return db.query(CoffeeWishlist).filter(CoffeeWishlist.user_id == user.id).order_by(desc(CoffeeWishlist.created_at)).offset(offset).limit(limit).all()


@app.post("/api/social/wishlist", response_model=WishlistResponse, status_code=status.HTTP_201_CREATED)
async def add_wishlist_item(
    payload: WishlistCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    item = CoffeeWishlist(user_id=user.id, **payload.model_dump())
    db.add(item)
    db.flush()
    create_activity(db, user, "quer provar", "wishlist", item.id, f"{user.name} quer provar {item.coffee_name}.")
    db.commit()
    db.refresh(item)
    return item


@app.post("/api/social/coffees/{coffee_id}/wishlist", response_model=WishlistResponse, status_code=status.HTTP_201_CREATED)
async def mark_coffee_wishlist(
    coffee_id: int,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    coffee = db.query(Coffee).filter(Coffee.id == coffee_id).first()
    if not coffee or (coffee.user_id != user.id and not can_view_profile(user, coffee.user)):
        raise HTTPException(status_code=404, detail="Café não encontrado ou privado.")
    existing = db.query(CoffeeWishlist).filter(
        CoffeeWishlist.user_id == user.id,
        CoffeeWishlist.coffee_name == coffee.name,
        CoffeeWishlist.roastery == coffee.roastery,
    ).first()
    if existing:
        return existing
    item = CoffeeWishlist(user_id=user.id, coffee_name=coffee.name, roastery=coffee.roastery, origin=coffee.origin)
    db.add(item)
    db.flush()
    create_activity(db, user, "quer provar", "wishlist", item.id, f"{user.name} quer provar {coffee.name}.")
    db.commit()
    db.refresh(item)
    return item


@app.delete("/api/social/wishlist/{item_id}")
async def delete_wishlist_item(
    item_id: int,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    item = db.query(CoffeeWishlist).filter(CoffeeWishlist.id == item_id, CoffeeWishlist.user_id == user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    db.delete(item)
    db.commit()
    return {"detail": "Item removido."}


@app.get("/api/social/tried", response_model=List[TriedCoffeeResponse])
async def list_tried_coffees(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    limit, offset = validate_limit_offset(limit, offset)
    return db.query(CafeTried).filter(CafeTried.user_id == user.id).order_by(desc(CafeTried.tried_at)).offset(offset).limit(limit).all()


@app.post("/api/social/tried", response_model=TriedCoffeeResponse, status_code=status.HTTP_201_CREATED)
async def add_tried_coffee(
    payload: TriedCoffeeCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    coffee = None
    data = payload.model_dump()
    if payload.coffee_id:
        coffee = db.query(Coffee).filter(Coffee.id == payload.coffee_id, Coffee.user_id == user.id).first()
        if coffee:
            data.update({"coffee_name": coffee.name, "roastery": coffee.roastery, "origin": coffee.origin})
    item = CafeTried(user_id=user.id, **data)
    db.add(item)
    db.flush()
    create_activity(db, user, "provou", "tried", item.id, f"{user.name} provou {item.coffee_name}.")
    db.commit()
    db.refresh(item)
    return item


@app.post("/api/social/coffees/{coffee_id}/tried", response_model=TriedCoffeeResponse, status_code=status.HTTP_201_CREATED)
async def mark_coffee_tried(
    coffee_id: int,
    payload: Optional[dict] = None,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    coffee = db.query(Coffee).filter(Coffee.id == coffee_id).first()
    if not coffee or (coffee.user_id != user.id and not can_view_profile(user, coffee.user)):
        raise HTTPException(status_code=404, detail="Café não encontrado ou privado.")
    data = payload or {}
    rating = data.get("rating")
    if rating is not None and not 1 <= float(rating) <= 5:
        raise HTTPException(status_code=422, detail="A nota precisa ficar entre 1 e 5.")
    item = CafeTried(
        user_id=user.id,
        coffee_id=coffee.id,
        coffee_name=coffee.name,
        roastery=coffee.roastery,
        origin=coffee.origin,
        rating=rating,
        notes=data.get("notes"),
    )
    db.add(item)
    db.flush()
    create_activity(db, user, "provou", "tried", item.id, f"{user.name} provou {coffee.name}.")
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/social/goals", response_model=List[CoffeeGoalResponse])
async def list_goals(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    limit, offset = validate_limit_offset(limit, offset)
    return db.query(CoffeeGoal).filter(CoffeeGoal.user_id == user.id).order_by(desc(CoffeeGoal.created_at)).offset(offset).limit(limit).all()


@app.post("/api/social/goals", response_model=CoffeeGoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: CoffeeGoalCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    goal = CoffeeGoal(user_id=user.id, **payload.model_dump())
    db.add(goal)
    db.flush()
    create_activity(db, user, "criou meta", "goal", goal.id, f"{user.name} criou a meta: {goal.title}.")
    db.commit()
    db.refresh(goal)
    return goal


@app.get("/api/social/explore")
async def explore_social(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    popular_coffees = (
        db.query(CafeTried.coffee_name, func.count(CafeTried.id).label("total"))
        .group_by(CafeTried.coffee_name)
        .order_by(desc("total"))
        .limit(10)
        .all()
    )
    popular_recipes = (
        db.query(PublicRecipe.id, PublicRecipe.title, func.count(SavedItem.id).label("saves"))
        .outerjoin(SavedItem, (SavedItem.target_type == "public_recipe") & (SavedItem.target_id == PublicRecipe.id))
        .group_by(PublicRecipe.id, PublicRecipe.title)
        .order_by(desc("saves"), desc(PublicRecipe.created_at))
        .limit(10)
        .all()
    )
    popular_methods = (
        db.query(Recipe.method, func.count(Recipe.id).label("total"))
        .group_by(Recipe.method)
        .order_by(desc("total"))
        .limit(10)
        .all()
    )
    week_ago = datetime.utcnow() - timedelta(days=7)
    active_users = (
        db.query(User.id, User.name, User.username, User.avatar_url, func.count(ActivityFeed.id).label("total"))
        .join(ActivityFeed, ActivityFeed.user_id == User.id)
        .filter(ActivityFeed.created_at >= week_ago, User.is_public_profile == True)
        .group_by(User.id, User.name, User.username, User.avatar_url)
        .order_by(desc("total"))
        .limit(10)
        .all()
    )
    return {
        "popular_coffees": [{"name": name, "total": total} for name, total in popular_coffees],
        "popular_recipes": [{"id": id_, "title": title, "saves": saves} for id_, title, saves in popular_recipes],
        "popular_methods": [{"method": method, "total": total} for method, total in popular_methods],
        "active_users": [{"id": id_, "name": name, "username": username, "avatar_url": avatar_url, "total": total} for id_, name, username, avatar_url, total in active_users],
        "my_following_count": db.query(Follow).filter(Follow.follower_id == user.id).count(),
    }


@app.get("/api/social/trends")
async def social_trends(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    await get_current_user(db, token=authorization)
    return await public_trends(db)


# --- ENDPOINTS PÚBLICOS E EXPERIÊNCIA SOCIAL DE CAFÉ ---
@app.get("/api/public/landing")
async def public_landing(db: Session = Depends(get_db)):
    featured_recipes = db.query(PublicRecipe).order_by(desc(PublicRecipe.created_at)).limit(4).all()
    activities = db.query(ActivityFeed).filter(ActivityFeed.visibility == "public").order_by(desc(ActivityFeed.created_at)).limit(5).all()
    return {
        "stats": {
            "public_baristas": db.query(User).filter(User.is_public_profile == True).count(),
            "coffees_logged": db.query(Coffee).count(),
            "recipes_shared": db.query(PublicRecipe).count(),
            "cups_extracted": db.query(Extraction).count(),
            "sensory_notes": db.query(SensoryLog).count(),
        },
        "featured_recipes": [public_recipe_to_response(db, item).model_dump(mode="json") for item in featured_recipes],
        "recent_activity": [activity_to_response(db, item).model_dump(mode="json") for item in activities],
    }


@app.get("/api/public/feed", response_model=List[ActivityResponse])
async def public_feed(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    limit, offset = validate_limit_offset(limit, offset)
    activities = db.query(ActivityFeed).filter(ActivityFeed.visibility == "public").order_by(desc(ActivityFeed.created_at)).offset(offset).limit(limit).all()
    return [activity_to_response(db, activity) for activity in activities]


@app.get("/api/public/explore")
async def public_explore(db: Session = Depends(get_db)):
    popular_coffees = (
        db.query(CafeTried.coffee_name, func.count(CafeTried.id).label("total"))
        .group_by(CafeTried.coffee_name)
        .order_by(desc("total"))
        .limit(12)
        .all()
    )
    popular_roasteries = (
        db.query(Coffee.roastery, func.count(Coffee.id).label("total"))
        .filter(Coffee.roastery.isnot(None))
        .group_by(Coffee.roastery)
        .order_by(desc("total"))
        .limit(12)
        .all()
    )
    popular_origins = (
        db.query(Coffee.origin, func.count(Coffee.id).label("total"))
        .filter(Coffee.origin.isnot(None))
        .group_by(Coffee.origin)
        .order_by(desc("total"))
        .limit(12)
        .all()
    )
    popular_methods = (
        db.query(Recipe.method, func.count(Recipe.id).label("total"))
        .group_by(Recipe.method)
        .order_by(desc("total"))
        .limit(12)
        .all()
    )
    public_recipes = db.query(PublicRecipe).order_by(desc(PublicRecipe.created_at)).limit(8).all()
    return {
        "popular_coffees": [{"name": name, "total": total} for name, total in popular_coffees],
        "popular_roasteries": [{"name": name, "total": total} for name, total in popular_roasteries],
        "popular_origins": [{"name": name, "total": total} for name, total in popular_origins],
        "popular_methods": [{"method": method, "total": total} for method, total in popular_methods],
        "public_recipes": [public_recipe_to_response(db, item).model_dump(mode="json") for item in public_recipes],
    }


@app.get("/api/public/trends")
async def public_trends(db: Session = Depends(get_db)):
    week_ago = datetime.utcnow() - timedelta(days=7)
    active_users = (
        db.query(User.id, User.name, User.username, User.avatar_url, func.count(ActivityFeed.id).label("total"))
        .join(ActivityFeed, ActivityFeed.user_id == User.id)
        .filter(ActivityFeed.created_at >= week_ago, User.is_public_profile == True)
        .group_by(User.id, User.name, User.username, User.avatar_url)
        .order_by(desc("total"))
        .limit(10)
        .all()
    )
    saved_recipes = (
        db.query(PublicRecipe.id, PublicRecipe.title, func.count(SavedItem.id).label("saves"))
        .outerjoin(SavedItem, (SavedItem.target_type == "public_recipe") & (SavedItem.target_id == PublicRecipe.id))
        .group_by(PublicRecipe.id, PublicRecipe.title)
        .order_by(desc("saves"), desc(PublicRecipe.created_at))
        .limit(10)
        .all()
    )
    methods = (
        db.query(Recipe.method, func.count(Recipe.id).label("total"))
        .group_by(Recipe.method)
        .order_by(desc("total"))
        .limit(10)
        .all()
    )
    return {
        "active_baristas": [{"id": id_, "name": name, "username": username, "avatar_url": avatar_url, "total": total} for id_, name, username, avatar_url, total in active_users],
        "saved_recipes": [{"id": id_, "title": title, "saves": saves} for id_, title, saves in saved_recipes],
        "methods": [{"method": method, "total": total} for method, total in methods],
    }


@app.get("/api/public/coffees/{coffee_id}")
async def public_coffee_page(
    coffee_id: int,
    limit: int = Query(12, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    limit, offset = validate_limit_offset(limit, offset, 50)
    coffee = db.query(Coffee).join(User, Coffee.user_id == User.id).filter(Coffee.id == coffee_id, User.is_public_profile == True).first()
    if not coffee:
        raise HTTPException(status_code=404, detail="Café público não encontrado.")
    ratings = db.query(CoffeeRating).filter(CoffeeRating.coffee_id == coffee.id, CoffeeRating.visibility == "public").order_by(desc(CoffeeRating.created_at)).offset(offset).limit(limit).all()
    reviews = db.query(CoffeeReview).filter(CoffeeReview.coffee_id == coffee.id, CoffeeReview.visibility == "public").order_by(desc(CoffeeReview.created_at)).offset(offset).limit(limit).all()
    return {
        "coffee": CoffeeResponse.model_validate(coffee).model_dump(mode="json"),
        "owner": public_user(coffee.user).model_dump(mode="json") if coffee.user else None,
        "ratings": [rating_to_response(item).model_dump(mode="json") for item in ratings],
        "reviews": [review_to_response(db, item).model_dump(mode="json") for item in reviews],
        "tried_count": db.query(CafeTried).filter(CafeTried.coffee_name == coffee.name).count(),
    }


@app.get("/api/public/recipes/{public_recipe_id}")
async def public_recipe_page(public_recipe_id: int, db: Session = Depends(get_db)):
    item = db.query(PublicRecipe).filter(PublicRecipe.id == public_recipe_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Receita pública não encontrada.")
    return public_recipe_to_response(db, item).model_dump(mode="json")


@app.get("/api/public/roasteries/{roastery}")
async def public_roastery_page(
    roastery: str,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    limit, offset = validate_limit_offset(limit, offset)
    coffees = db.query(Coffee).join(User, Coffee.user_id == User.id).filter(Coffee.roastery == roastery, User.is_public_profile == True).offset(offset).limit(limit).all()
    if not coffees:
        raise HTTPException(status_code=404, detail="Torrefação ainda não possui cafés públicos.")
    origins = sorted({coffee.origin for coffee in coffees if coffee.origin})
    return {
        "name": roastery,
        "coffees_count": len(coffees),
        "origins": origins,
        "coffees": [CoffeeResponse.model_validate(coffee).model_dump(mode="json") for coffee in coffees],
    }


@app.get("/api/public/methods/{method}")
async def public_method_page(
    method: str,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    limit, offset = validate_limit_offset(limit, offset)
    recipes = db.query(PublicRecipe).join(Recipe, PublicRecipe.recipe_id == Recipe.id).filter(func.lower(Recipe.method) == method.lower()).order_by(desc(PublicRecipe.created_at)).offset(offset).limit(limit).all()
    return {
        "method": method,
        "recipes_count": len(recipes),
        "public_recipes": [public_recipe_to_response(db, item).model_dump(mode="json") for item in recipes],
    }


@app.get("/api/onboarding/status")
async def onboarding_status(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    has_stock = db.query(Stock).join(Coffee).filter(Coffee.user_id == user.id, Stock.current_quantity > 0).first() is not None
    completed = {
        "first_coffee": db.query(Coffee).filter(Coffee.user_id == user.id).first() is not None,
        "stock": has_stock,
        "recipe": db.query(Recipe).filter(Recipe.user_id == user.id).first() is not None,
        "extraction": db.query(Extraction).filter(Extraction.user_id == user.id).first() is not None,
        "sensory": db.query(SensoryLog).filter(SensoryLog.user_id == user.id).first() is not None,
        "public_profile": bool(user.is_public_profile),
        "wishlist": db.query(CoffeeWishlist).filter(CoffeeWishlist.user_id == user.id).first() is not None,
        "goal": db.query(CoffeeGoal).filter(CoffeeGoal.user_id == user.id).first() is not None,
    }
    steps = [
        {"key": "first_coffee", "title": "Cadastre seu primeiro café", "href": "#/coffees"},
        {"key": "stock", "title": "Adicione quantidade em estoque", "href": "#/stock"},
        {"key": "recipe", "title": "Crie ou escolha uma receita", "href": "#/recipes"},
        {"key": "extraction", "title": "Registre sua primeira extração", "href": "#/recipes"},
        {"key": "sensory", "title": "Avalie sensorialmente", "href": "#/sensory"},
        {"key": "public_profile", "title": "Prepare seu perfil público", "href": "#/profile"},
        {"key": "wishlist", "title": "Monte sua lista Quero provar", "href": "#/social"},
        {"key": "goal", "title": "Crie uma meta de preparo", "href": "#/social"},
    ]
    done = sum(1 for item in completed.values() if item)
    return {"completed": completed, "steps": steps, "progress": round(done / len(steps) * 100)}


@app.get("/api/auth/me/privacy")
async def get_privacy_settings(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    return {
        "profile_visibility": getattr(user, "profile_visibility", "private"),
        "diary_visibility": getattr(user, "diary_visibility", "private"),
        "is_public_profile": bool(user.is_public_profile),
    }


@app.put("/api/auth/me/privacy")
async def update_privacy_settings(
    payload: dict,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db),
):
    user = await get_current_user(db, token=authorization)
    profile_visibility = "public" if payload.get("profile_visibility") == "public" else "private"
    diary_visibility = "public" if payload.get("diary_visibility") == "public" else "private"
    user.profile_visibility = profile_visibility
    user.is_public_profile = profile_visibility == "public"
    user.diary_visibility = diary_visibility
    db.commit()
    db.refresh(user)
    return {
        "profile_visibility": user.profile_visibility,
        "diary_visibility": user.diary_visibility,
        "is_public_profile": user.is_public_profile,
    }

@app.post("/api/auth/me/avatar")
async def upload_avatar(file: UploadFile = File(...), authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    image_bytes, ext = await read_valid_image_upload(file)
    filename = f"user_{u.id}_{int(datetime.utcnow().timestamp())}{ext}"
    with open(AVATAR_DIR / filename, "wb") as b:
        b.write(image_bytes)
    u.avatar_url = f"/static/uploads/avatars/{filename}"
    db.commit()
    return {"avatar_url": u.avatar_url}

# --- ENDPOINTS DE CAFÉS ---
@app.post("/api/coffees", response_model=CoffeeResponse)
async def create_coffee(coffee_in: CoffeeCreate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    c = Coffee(**coffee_in.model_dump(), user_id=u.id)
    db.add(c)
    db.flush()
    create_activity(db, u, "cadastrou", "coffee", c.id, f"{u.name} adicionou {c.name} à biblioteca.")
    db.commit(); db.refresh(c)
    # Inicializa a ficha de estoque zerada
    stk = Stock(coffee_id=c.id, current_quantity=0.0, min_quantity=50.0)
    db.add(stk); db.commit()
    return c

@app.get("/api/coffees", response_model=List[CoffeeResponse])
async def list_coffees(
    search: Optional[str] = None, 
    process: Optional[str] = None, 
    roast_level: Optional[str] = None, 
    sort_by: Optional[str] = "name", 
    favorites_only: bool = False, 
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None, 
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    q = db.query(Coffee).filter(Coffee.user_id == u.id)
    if favorites_only: q = q.filter(Coffee.is_favorite == True)
    if search: 
        q = q.filter(or_(Coffee.name.ilike(f"%{search}%"), Coffee.roastery.ilike(f"%{search}%"), Coffee.sensory_notes.ilike(f"%{search}%")))
    if process: q = q.filter(Coffee.process == process)
    if roast_level: q = q.filter(Coffee.roast_level == roast_level)
    
    if sort_by == "sca_score": q = q.order_by(desc(Coffee.sca_score))
    elif sort_by == "roast_date": q = q.order_by(desc(Coffee.roast_date))
    else: q = q.order_by(Coffee.name)
    return q.all()

@app.put("/api/coffees/{coffee_id}", response_model=CoffeeResponse)
async def update_coffee(coffee_id: int, coffee_data: CoffeeUpdate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    c = db.query(Coffee).filter(Coffee.id == coffee_id, Coffee.user_id == u.id).first()
    if not c: raise HTTPException(status_code=404, detail="Café não encontrado")
    for k, v in coffee_data.model_dump(exclude_unset=True).items(): setattr(c, k, v)
    db.commit(); db.refresh(c)
    return c

@app.delete("/api/coffees/{coffee_id}")
async def delete_coffee(coffee_id: int, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    c = db.query(Coffee).filter(Coffee.id == coffee_id, Coffee.user_id == u.id).first()
    if not c: raise HTTPException(status_code=404, detail="Café não encontrado")
    db.delete(c); db.commit()
    return {"detail": "Café removido com sucesso"}

@app.post("/api/coffees/{coffee_id}/photo")
async def upload_coffee_photo(coffee_id: int, file: UploadFile = File(...), authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    c = db.query(Coffee).filter(Coffee.id == coffee_id, Coffee.user_id == u.id).first()
    if not c: raise HTTPException(status_code=404, detail="Café não encontrado")
    image_bytes, ext = await read_valid_image_upload(file)
    filename = f"coffee_{c.id}_{int(datetime.utcnow().timestamp())}{ext}"
    with open(COFFEE_DIR / filename, "wb") as b:
        b.write(image_bytes)
    c.photo_url = f"/static/uploads/coffees/{filename}"
    db.commit()
    return {"photo_url": c.photo_url}

# --- ENDPOINTS DE INVENTÁRIO / ESTOQUE ---
@app.get("/api/stock", response_model=List[StockResponse])
async def list_stock(authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    return db.query(Stock).join(Coffee).filter(Coffee.user_id == u.id).order_by(Stock.current_quantity.asc()).all()

@app.put("/api/stock/{stock_id}", response_model=StockResponse)
async def modify_stock_entry(stock_id: int, data_in: StockUpdate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    stk = db.query(Stock).join(Coffee).filter(Stock.id == stock_id, Coffee.user_id == u.id).first()
    if not stk: raise HTTPException(status_code=404, detail="Registro de estoque inexistente.")
    
    old_qty = stk.current_quantity
    payload = data_in.model_dump(exclude_unset=True)
    
    if "current_quantity" in payload and payload["current_quantity"] != old_qty:
        diff = payload["current_quantity"] - old_qty
        db.add(StockMovement(stock_id=stk.id, quantity_changed=diff, action_type="ajuste", notes="Ajuste manual de inventário"))
        
    if "is_opened" in payload and payload["is_opened"] != stk.is_opened:
        if payload["is_opened"] is True:
            db.add(StockMovement(stock_id=stk.id, quantity_changed=0.0, action_type="abertura", notes="Pacote aberto para consumo"))

    for k, v in payload.items(): setattr(stk, k, v)
    db.commit(); db.refresh(stk)
    return stk

@app.post("/api/stock/{stock_id}/refill", response_model=StockResponse)
async def register_coffee_purchase(stock_id: int, quantity_added: float = Query(..., ge=1), notes: Optional[str] = Query(None), authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    stk = db.query(Stock).join(Coffee).filter(Stock.id == stock_id, Coffee.user_id == u.id).first()
    if not stk: raise HTTPException(status_code=404, detail="Estoque não encontrado.")
    
    stk.current_quantity += quantity_added
    db.add(StockMovement(stock_id=stk.id, quantity_changed=quantity_added, action_type="compra", notes=notes or "Nova remessa adicionada"))
    db.commit(); db.refresh(stk)
    return stk

@app.get("/api/stock/{stock_id}/movements")
async def get_stock_history(stock_id: int, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    stk = db.query(Stock).join(Coffee).filter(Stock.id == stock_id, Coffee.user_id == u.id).first()
    if not stk: raise HTTPException(status_code=404, detail="Estoque não encontrado.")
    return db.query(StockMovement).filter(StockMovement.stock_id == stk.id).order_by(desc(StockMovement.created_at)).all()

# --- ENDPOINTS DE RECEITAS ---
@app.post("/api/recipes", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(recipe_in: RecipeCreate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    if recipe_in.coffee_id:
        c = db.query(Coffee).filter(Coffee.id == recipe_in.coffee_id, Coffee.user_id == u.id).first()
        if not c: raise HTTPException(status_code=400, detail="O café selecionado é inválido.")
    new_recipe = Recipe(**recipe_in.model_dump(), user_id=u.id)
    db.add(new_recipe)
    db.flush()
    create_activity(db, u, "criou", "recipe", new_recipe.id, f"{u.name} criou a receita {new_recipe.name}.")
    db.commit(); db.refresh(new_recipe)
    return new_recipe

@app.get("/api/recipes", response_model=List[RecipeResponse])
async def list_recipes(search: Optional[str] = None, method: Optional[str] = None, favorites_only: bool = False, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    q = db.query(Recipe).filter(Recipe.user_id == u.id)
    if favorites_only: q = q.filter(Recipe.is_favorite == True)
    if method: q = q.filter(Recipe.method == method)
    if search:
        q = q.filter(or_(Recipe.name.ilike(f"%{search}%"), Recipe.description.ilike(f"%{search}%"), Recipe.grind_size.ilike(f"%{search}%")))
    return q.order_by(desc(Recipe.is_favorite), Recipe.name).all()

@app.put("/api/recipes/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(recipe_id: int, recipe_data: RecipeUpdate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    rec = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.user_id == u.id).first()
    if not rec: raise HTTPException(status_code=404, detail="Receita não encontrada.")
    for k, v in recipe_data.model_dump(exclude_unset=True).items(): setattr(rec, k, v)
    db.commit(); db.refresh(rec)
    return rec

@app.delete("/api/recipes/{recipe_id}")
async def delete_recipe(recipe_id: int, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    rec = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.user_id == u.id).first()
    if not rec: raise HTTPException(status_code=404, detail="Receita não encontrada.")
    db.delete(rec); db.commit()
    return {"detail": "Receita removida com sucesso"}

@app.post("/api/recipes/{recipe_id}/duplicate", response_model=RecipeResponse)
async def duplicate_recipe(recipe_id: int, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    origin = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.user_id == u.id).first()
    if not origin: raise HTTPException(status_code=404, detail="Receita original não encontrada.")
    clone = Recipe(
        user_id=u.id, coffee_id=origin.coffee_id, name=f"{origin.name} (Cópia)", method=origin.method,
        coffee_weight=origin.coffee_weight, water_weight=origin.water_weight, grind_size=origin.grind_size,
        water_temp=origin.water_temp, description=origin.description, steps=origin.steps, is_favorite=False
    )
    db.add(clone)
    db.flush()
    create_activity(db, u, "duplicou", "recipe", clone.id, f"{u.name} duplicou a receita {origin.name}.")
    db.commit(); db.refresh(clone)
    return clone

#--- ENDPOINTS DO MOTOR INTELIGENTE (FASE 6)
@app.post("/api/motor/calculate", response_model=MotorCalculationResponse)
async def calculate_motor_ratio(req: MotorCalculationRequest, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    # Valida usuário apenas para garantir sessão segura
    await get_current_user(db, token=authorization)
    
    c_w = req.coffee_weight
    w_w = req.water_weight
    ratio = req.ratio

    if c_w and ratio:
        w_w = c_w * ratio
    elif w_w and ratio:
        c_w = w_w / ratio
    elif c_w and w_w:
        ratio = w_w / c_w
    else:
        raise HTTPException(status_code=400, detail="Forneça ao menos duas variáveis para calcular a terceira.")

    # Sugestão básica inteligente com base no volume físico
    note = "Moagem Padrão"
    if w_w > 500:
        note = "Considere engrossar a moagem devido ao alto volume de água para evitar super-extração."
    elif w_w < 150:
        note = "Considere afinar levemente a moagem para compensar o fluxo rápido em doses baixas."

    return {
        "coffee_weight": round(c_w, 1),
        "water_weight": round(w_w, 0),
        "ratio": round(ratio, 1),
        "suggested_grind_note": note
    }

# ==========================================
# --- ROTAS FASE 11: CADERNO DE BEBIDAS ----
# ==========================================
@app.get("/api/beverages", response_model=List[BeverageResponse])
async def get_beverages(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    return db.query(Beverage).filter(Beverage.user_id == u.id).all()

@app.post("/api/beverages", response_model=BeverageResponse)
async def create_beverage(
    bev: BeverageCreate, 
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None, 
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    new_bev = Beverage(**bev.model_dump(), user_id=u.id) # Use .dict() se for Pydantic v1
    db.add(new_bev)
    db.flush()
    create_activity(db, u, "publicou bebida", "beverage", new_bev.id, f"{u.name} publicou a bebida autoral {new_bev.name}.")
    db.commit()
    db.refresh(new_bev)
    return new_bev

@app.put("/api/beverages/{bev_id}", response_model=BeverageResponse)
async def update_beverage(
    bev_id: int,
    data: BeverageCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    bev = db.query(Beverage).filter(Beverage.id == bev_id, Beverage.user_id == u.id).first()
    if not bev:
        raise HTTPException(status_code=404, detail="Bebida não encontrada")
    for k, v in data.model_dump().items():
        setattr(bev, k, v)
    db.commit()
    db.refresh(bev)
    return bev

@app.delete("/api/beverages/{bev_id}")
async def delete_beverage(
    bev_id: int, 
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None, 
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    bev = db.query(Beverage).filter(Beverage.id == bev_id, Beverage.user_id == u.id).first()
    if not bev:
        raise HTTPException(status_code=404, detail="Bebida não encontrada")
    db.delete(bev)
    db.commit()
    return {"message": "Bebida removida"}

# ========================================================
# --- MODELOS PARA SESSÕES E HISTÓRICO DO CHAT DE IA ---
# ========================================================


def extract_openrouter_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content") or ""
                parts.append(str(text))
            elif part:
                parts.append(str(part))
        return "\n".join(part for part in parts if part.strip()).strip()

    return str(content or "").strip()


def clean_ai_response(response: str | None) -> str:
    if not response:
        return ""

    # Remove negrito Markdown
    response = response.replace("**", "")

    # Remove itálico Markdown
    response = response.replace("*", "")

    # Remove títulos Markdown (#, ##, ###)
    response = re.sub(r"^#{1,6}\s*", "", response, flags=re.MULTILINE)

    # Remove espaços excessivos no final das linhas
    response = "\n".join(line.rstrip() for line in response.splitlines())

    # Evita mais de duas quebras de linha consecutivas
    response = re.sub(r"\n{3,}", "\n\n", response)

    return response.strip()


class AIChatRequest(BaseModel):
    message: str


class AIChatResponse(BaseModel):
    reply: str


class RenameSessionRequest(BaseModel):
    title: str


class AIChatUnifiedRequest(BaseModel):
    session_id: int | None = None
    message: str


class AIChatSession(Base):
    __tablename__ = "ai_chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(255), default="Nova Conversa", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship(
        "AIChatMessage", back_populates="session", cascade="all, delete-orphan"
    )


class AIChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(50), nullable=False)  # 'user' ou 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("AIChatSession", back_populates="messages")


# --- ROTAS DA IA COM SUPORTE A SESSÕES ---


@app.get("/api/ai/sessions")
async def list_ai_sessions(
    authorization: Annotated[
        str | None, Depends(get_token_from_header)
    ] = None,
    db: Session = Depends(get_db),
):
    u = await get_current_user(db, token=authorization)
    sessions = (
        db.query(AIChatSession)
        .filter(AIChatSession.user_id == u.id)
        .order_by(AIChatSession.created_at.desc())
        .all()
    )
    return [
        {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()}
        for s in sessions
    ]


@app.post("/api/ai/sessions")
async def create_ai_session(
    authorization: Annotated[
        str | None, Depends(get_token_from_header)
    ] = None,
    db: Session = Depends(get_db),
):
    u = await get_current_user(db, token=authorization)
    new_session = AIChatSession(user_id=u.id, title="Nova Conversa")
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return {
        "id": new_session.id,
        "title": new_session.title,
        "created_at": new_session.created_at.isoformat(),
    }


@app.get("/api/ai/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    authorization: Annotated[
        str | None, Depends(get_token_from_header)
    ] = None,
    db: Session = Depends(get_db),
):
    u = await get_current_user(db, token=authorization)
    session = (
        db.query(AIChatSession)
        .filter(AIChatSession.id == session_id, AIChatSession.user_id == u.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    messages = (
        db.query(AIChatMessage)
        .filter(AIChatMessage.session_id == session_id)
        .order_by(AIChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@app.delete("/api/ai/sessions/{session_id}")
async def delete_ai_session(
    session_id: int,
    authorization: Annotated[
        str | None, Depends(get_token_from_header)
    ] = None,
    db: Session = Depends(get_db),
):
    u = await get_current_user(db, token=authorization)
    session = (
        db.query(AIChatSession)
        .filter(AIChatSession.id == session_id, AIChatSession.user_id == u.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    db.delete(session)
    db.commit()
    return {"detail": "Chat excluído com sucesso"}


@app.put("/api/ai/sessions/{session_id}")
async def rename_ai_session(
    session_id: int,
    req: RenameSessionRequest,
    authorization: Annotated[
        str | None, Depends(get_token_from_header)
    ] = None,
    db: Session = Depends(get_db),
):
    u = await get_current_user(db, token=authorization)
    session = (
        db.query(AIChatSession)
        .filter(AIChatSession.id == session_id, AIChatSession.user_id == u.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    session.title = req.title
    db.commit()
    return {"id": session.id, "title": session.title}


# --- ROTA UNIFICADA DE CHAT (Lida com novas sessões e histórico) ---
@app.post("/api/ai/chat")
async def ai_chat_unified(
    req: AIChatUnifiedRequest,
    authorization: Annotated[
        str | None, Depends(get_token_from_header)
    ] = None,
    db: Session = Depends(get_db),
):
    try:
        u = await get_current_user(db, token=authorization)

        # 1. Se não enviou session_id, cria uma nova sessão automaticamente
        if not req.session_id:
            title = req.message[:28] + ("..." if len(req.message) > 28 else "")
            session = AIChatSession(user_id=u.id, title=title)
            db.add(session)
            db.commit()
            db.refresh(session)
        else:
            session = (
                db.query(AIChatSession)
                .filter(
                    AIChatSession.id == req.session_id,
                    AIChatSession.user_id == u.id,
                )
                .first()
            )
            if not session:
                raise HTTPException(
                    status_code=404, detail="Sessão não encontrada"
                )

            if session.title == "Nova Conversa":
                session.title = req.message[:28] + (
                    "..." if len(req.message) > 28 else ""
                )
                db.commit()

        settings = get_settings()
        if not settings.openrouter_api_key:
            raise HTTPException(
                status_code=400,
                detail="Chave da API OpenRouter não configurada.",
            )

        # 2. Salva a mensagem do usuário
        user_msg = AIChatMessage(
            session_id=session.id, role="user", content=req.message
        )
        db.add(user_msg)
        db.commit()

        # 3. Contexto do usuário
        coffees = db.query(Coffee).filter(Coffee.user_id == u.id).all()
        recipes = db.query(Recipe).filter(Recipe.user_id == u.id).all()
        stock_items = db.query(Stock).join(Coffee).filter(Coffee.user_id == u.id).all()
        extractions = (
            db.query(Extraction).filter(Extraction.user_id == u.id).order_by(desc(Extraction.extraction_date)).limit(20).all()
        )
        sensory_logs = (
            db.query(SensoryLog).filter(SensoryLog.user_id == u.id).order_by(desc(SensoryLog.created_at)).limit(12).all()
        )

        coffees_info = (
            ", ".join(
                [
                    f"{c.name} ({c.roastery}, origem: {c.origin}{', torra: ' + c.roast_level if c.roast_level else ''}{', notas: ' + c.sensory_notes if c.sensory_notes else ''})"
                    for c in coffees
                ]
            )
            if coffees
            else "Nenhum café cadastrado."
        )
        recipes_info = (
            ", ".join([f"{r.name} no método {r.method}, {r.coffee_weight:g}g para {r.water_weight:g}g" for r in recipes[:20]])
            if recipes
            else "Nenhuma receita."
        )
        stock_info = (
            ", ".join([
                f"{item.coffee.name}: {item.current_quantity:g}g {'aberto/em uso' if item.is_opened else 'fechado'}"
                for item in stock_items[:20]
            ])
            if stock_items
            else "Nenhum estoque registrado."
        )
        extractions_info = (
            f"Últimas extrações analisadas: {len(extractions)}. "
            + "; ".join([
                f"{ext.recipe.name if ext.recipe else 'preparo manual'} ({ext.total_time}s, nota {ext.rating if ext.rating is not None else 'não informada'})"
                for ext in extractions[:8]
            ])
        )
        sensory_info = (
            ", ".join([
                f"{log.perceived_notes} (aroma {log.aroma_score}/10, acidez {log.acidity_score}/10, corpo {log.body_score}/10, doçura {log.sweetness_score}/10)"
                for log in sensory_logs
                if log.perceived_notes
            ])
            or "Nenhuma preferência sensorial registrada no diário."
        )
        profile_preferences = ", ".join(clean_profile_list(getattr(u, "sensory_preferences", None))) or "Nenhuma preferência sensorial no perfil."

        system_prompt = (
            f"""
            Você é o "Barista de IA", o assistente virtual oficial do Coffee Lab e especiallista na area.
            Você atua como um barista especializado em cafés especiais e como um consultor pessoal de café. Sua função é ajudar o usuário
            a tomar melhores decisões sobre seus cafés, receitas e extrações, utilizando de forma inteligente e fiel os dados disponíveis no contexto.
            Seu objetivo não é apenas responder perguntas: é ajudar o usuário a explorar, entender e melhorar sua experiência com café.

            REGRA PRIORITARIA DE RESPOSTA CURTA:
            Responda sempre direto ao ponto. Use no maximo 3 frases curtas ou 3 bullets, salvo quando o usuario pedir detalhes.
            Nao escreva introducoes longas, explicacoes extensas, emojis, floreios ou repeticoes.
            Se a pergunta pedir uma acao pratica, entregue primeiro a recomendacao objetiva e apenas 1 motivo tecnico breve.

            ════════════════════════════════════
            ESCOPO DE ATUAÇÃO
            ════════════════════════════════════
            Você pode ajudar exclusivamente com assuntos relacionados a:

            • Cafés especiais e características sensoriais
            • Métodos de extração
            • Receitas de café
            • Moagem e granulometria
            • Proporção café/água (ratio)
            • Temperatura da água
            • Tempo de extração
            • Técnicas de preparo
            • Ajustes de receita
            • Diagnóstico de problemas de extração
            • Harmonização com alimentos
            • Comparação entre cafés cadastrados
            • Histórico e evolução das extrações
            • Controle e organização do estoque de café
            • Criação de receitas personalizadas com café (drinks e experimentos segundo o perfil e gosto do usuario)

            Se o usuário perguntar sobre assuntos completamente fora desse universo, responda de maneira educada e breve, informando que sua especialidade
            é café e redirecionando a conversa para esse tema.

            ════════════════════════════════════
            CONTEXTO DO USUÁRIO
            ════════════════════════════════════
            Os dados abaixo representam informações reais cadastradas pelo usuário no Coffee Lab.

            Cafés cadastrados:
            {coffees_info}

            Receitas cadastradas:
            {recipes_info}

            Histórico de extrações:
            {extractions_info}

            Estoque atual:
            {stock_info}

            Preferências sensoriais do perfil:
            {profile_preferences}

            Diário sensorial recente:
            {sensory_info}

            ════════════════════════════════════
            REGRAS DE FIDELIDADE AOS DADOS
            ════════════════════════════════════
            1. Nunca invente cafés, receitas, métodos, extrações ou dados que não estejam disponíveis no contexto.
            2. Quando mencionar um café do usuário, utilize exatamente os dados fornecidos.
            3. Nunca apresente valores ausentes, nulos ou "None" diretamente ao usuário. Quando uma informação não estiver disponível, simplesmente omita-a ou diga
            que esse dado não foi informado.
            4. Diferencie claramente:
            - Dados cadastrados pelo usuário
            - Receitas já existentes no Coffee Lab
            - Sugestões ou recomendações geradas por você
            5. Nunca diga que uma receita é "perfeita" ou que um café "certamente" terá determinado resultado sem dados suficientes para justificar essa afirmação.
            6. Se houver uma receita cadastrada que seja relevante para a solicitação do usuário, priorize essa receita e explique por que ela é um bom ponto de partida.
            7. Se não houver uma receita cadastrada adequada, você pode criar uma sugestão de preparo utilizando apenas os cafés que o usuário realmente possui.
            8. Quando os dados forem insuficientes para uma recomendação precisa, faça uma pergunta objetiva. Evite fazer várias perguntas de uma vez quando já for possível
            oferecer uma recomendação inicial.

            ════════════════════════════════════
            COMPORTAMENTO INTELIGENTE
            ════════════════════════════════════
            Sempre que possível:

            • Use primeiro os dados do próprio usuário.
            • Aproveite o histórico de extrações para sugerir ajustes.
            • Considere as receitas já cadastradas antes de criar uma nova.
            • Adapte quantidades, ratios e parâmetros ao objetivo do usuário.
            • Explique brevemente o motivo técnico das suas recomendações.
            • Se o usuário relatar um problema na bebida, identifique possíveis causas e sugira ajustes práticos.
            • Quando houver várias possibilidades, recomende primeiro a opção mais adequada e apresente alternativas apenas quando forem relevantes.
            • Evite respostas excessivamente genéricas.
            • Responda sempre brevemente evitando respostas muito longas que o usuario não queira ler.

            O usuário deve sentir que você conhece o Coffee Lab dele e está analisando seus próprios cafés, receitas e histórico.

            ════════════════════════════════════
            ESTILO DE RESPOSTA
            ════════════════════════════════════
            Seu tom deve ser:

            • Profissional
            • Técnico, mas fácil de entender
            • Amigável
            • Entusiasmado
            • Natural
            • Conciso
            • Apaixonado por café

            FORMATAÇÃO DAS RESPOSTAS:

            Não utilize Markdown de negrito ou itálico, como **texto** ou *texto*.

            Prefira uma apresentação limpa e visual utilizando:
            - Títulos em letras maiúsculas ou simples
            - Emojis para separar seções
            - Listas com marcadores
            - Listas numeradas para instruções
            - Quebras de linha para facilitar a leitura

            Evite excesso de formatação e não utilize blocos de texto muito longos.
            Quando apresentar uma receita, organize os parâmetros em linhas individuais:

            Não seja excessivamente formal.
            Não escreva textos longos sem necessidade.
            Não repita informações que o usuário já forneceu.

            Use emojis com MUITA moderação. Se usar, no máximo 1 por resposta.

            Quando apresentar uma receita, prefira uma estrutura visual semelhante a:

            ☕ NOME DA RECEITA

            Café: ...
            Método: ...
            Ratio: ...
            Café: ... g
            Água: ... ml
            Moagem: ...
            Temperatura: ...
            Tempo: ...


            Depois, quando relevante, apresente de forma MUITO breve:

            💡 Por que essa receita?
            Uma explicação curta e técnica.

            ⚙️ Preparo
            Passo a passo objetivo.

            🔎 Ajustes
            Sugestões de como corrigir a extração de acordo com o sabor percebido.

            ════════════════════════════════════
            PRINCÍPIO FUNDAMENTAL
            ════════════════════════════════════
            Você não é apenas um chatbot que responde sobre café.
            Você é o Barista de IA do Coffee Lab.
            Sua função é transformar os dados do usuário em recomendações úteis, personalizadas e tecnicamente coerentes, ajudando-o a preparar cafés cada vez melhores.
            Sempre priorize personalização, precisão e utilidade.
            Nas respostas NUNCA inclua ** ou * ou qualquer outro símbolo que seja irrelevante para a receita.
            """
        )

        recent_msgs = (
            db.query(AIChatMessage)
            .filter(AIChatMessage.session_id == session.id)
            .order_by(AIChatMessage.created_at.desc())
            .limit(10)
            .all()
        )
        recent_msgs.reverse()

        messages_payload = [{"role": "system", "content": system_prompt}]
        for m in recent_msgs:
            messages_payload.append({"role": m.role, "content": m.content})

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Coffee Lab",
        }
        payload = {
            "model": "openrouter/auto",
            "messages": messages_payload,
            "temperature": 0.35,
            "max_tokens": 420,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers,
            )

            if response.status_code != 200:
                print("OpenRouter error:", response.status_code, response.text[:500])
                raise HTTPException(
                    status_code=502,
                    detail="O Barista de IA não conseguiu responder agora. Tente novamente em alguns segundos.",
                )

            data = response.json()
            raw_reply = extract_openrouter_content(data)
            reply = clean_ai_response(raw_reply)
            if not reply:
                print("OpenRouter retornou uma resposta vazia.")
                raise HTTPException(
                    status_code=502,
                    detail="A IA retornou uma resposta vazia. Tente novamente em alguns segundos.",
                )

            assistant_msg = AIChatMessage(
                session_id=session.id, role="assistant", content=reply
            )
            db.add(assistant_msg)
            db.commit()

            return {"session_id": session.id, "response": reply}

    except HTTPException as http_exc:
        raise http_exc

    except Exception as error:
        print("Erro interno no Barista de IA:", repr(error))
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao consultar o Barista de IA.",
        )
        
# --- ENDPOINT DE HISTÓRICO DE EXTRAÇÃO (FASE 8) ---
@app.get("/api/extractions", response_model=List[ExtractionResponse])
async def get_extractions(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None, 
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    extractions = db.query(Extraction).filter(
        Extraction.user_id == u.id
    ).order_by(desc(Extraction.extraction_date)).all()
    
    return extractions

@app.get("/api/notifications", response_model=List[NotificationItem])
async def get_notifications(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    now = datetime.utcnow()
    notifications: list[NotificationItem] = []

    stock_items = (
        db.query(Stock)
        .join(Coffee)
        .filter(Coffee.user_id == u.id)
        .order_by(Stock.current_quantity.asc())
        .all()
    )
    for item in stock_items:
        min_qty = max(float(item.min_quantity or 0), 0)
        current_qty = float(item.current_quantity or 0)
        coffee_name = item.coffee.name if item.coffee else "Café"
        if min_qty <= 0:
            continue
        critical_limit = max(15.0, min_qty * 0.35)
        if current_qty <= critical_limit:
            notifications.append(NotificationItem(
                id=f"stock-critical-{item.id}-{int(current_qty)}",
                type="stock_critical",
                title="Estoque crítico",
                message=f"{coffee_name} está com {current_qty:g}g. Reabasteça antes do próximo preparo.",
                severity="critical",
                created_at=item.updated_at or now,
                action_url="#/stock"
            ))
        elif current_qty <= min_qty:
            notifications.append(NotificationItem(
                id=f"stock-low-{item.id}-{int(current_qty)}",
                type="stock_low",
                title="Estoque baixo",
                message=f"{coffee_name} está abaixo do limite configurado ({current_qty:g}g de {min_qty:g}g).",
                severity="warning",
                created_at=item.updated_at or now,
                action_url="#/stock"
            ))

    counts = {
        "coffees": db.query(Coffee).filter(Coffee.user_id == u.id).count(),
        "recipes": db.query(Recipe).filter(Recipe.user_id == u.id).count(),
        "extractions": db.query(Extraction).filter(Extraction.user_id == u.id).count(),
        "sensory": db.query(SensoryLog).filter(SensoryLog.user_id == u.id).count(),
        "beverages": db.query(Beverage).filter(Beverage.user_id == u.id).count(),
    }
    achievement_rules = [
        ("first-coffee", counts["coffees"] >= 1, "Primeiro café cadastrado", "Sua biblioteca de cafés especiais começou.", "#/coffees"),
        ("five-recipes", counts["recipes"] >= 5, "Livro de receitas crescendo", "Você já tem 5 receitas cadastradas no Coffee Lab.", "#/recipes"),
        ("ten-extractions", counts["extractions"] >= 10, "Ritual consistente", "Você registrou 10 extrações. As estatísticas já estão ganhando corpo.", "#/stats"),
        ("five-sensory", counts["sensory"] >= 5, "Paladar em treino", "Você já registrou 5 degustações no diário sensorial.", "#/sensory"),
        ("first-beverage", counts["beverages"] >= 1, "Primeira bebida autoral", "Seu caderno de bebidas já tem a primeira criação.", "#/beverages"),
    ]
    for key, unlocked, title, message, action_url in achievement_rules:
        if unlocked:
            notifications.append(NotificationItem(
                id=f"achievement-{key}",
                type="achievement",
                title=title,
                message=message,
                severity="success",
                created_at=now,
                action_url=action_url
            ))

    recent_recipes = (
        db.query(Recipe)
        .filter(Recipe.user_id == u.id, Recipe.created_at >= now - timedelta(days=7))
        .order_by(desc(Recipe.created_at))
        .limit(3)
        .all()
    )
    for recipe in recent_recipes:
        notifications.append(NotificationItem(
            id=f"new-recipe-{recipe.id}",
            type="new_recipe",
            title="Nova receita disponível",
            message=f"{recipe.name} foi adicionada ao seu livro de receitas.",
            severity="info",
            created_at=recipe.created_at,
            action_url="#/recipes"
        ))

    severity_order = {"critical": 0, "warning": 1, "success": 2, "info": 3}
    notifications.sort(key=lambda item: (severity_order.get(item.severity, 9), -item.created_at.timestamp()))
    return notifications

# --- SERVINDO FRONTEND (DEVE FICAR SEMPRE POR ÚLTIMO) ---
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# --- ENDPOINTS DIÁRIO SENSORIAL (FASE 9) ---

@app.get("/api/sensory-logs", response_model=List[SensoryLogResponse])
async def get_sensory_logs(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    return db.query(SensoryLog).filter(SensoryLog.user_id == u.id).order_by(desc(SensoryLog.created_at)).all()

@app.post("/api/sensory-logs", response_model=SensoryLogResponse)
async def create_sensory_log(
    payload: SensoryLogCreate,
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    log = SensoryLog(
        user_id=u.id,
        coffee_id=payload.coffee_id,
        extraction_id=payload.extraction_id,
        aroma_score=payload.aroma_score,
        acidity_score=payload.acidity_score,
        body_score=payload.body_score,
        sweetness_score=payload.sweetness_score,
        aftertaste_score=payload.aftertaste_score,
        perceived_notes=payload.perceived_notes,
        unperceived_notes=payload.unperceived_notes,
        comments=payload.comments
    )
    db.add(log)
    db.flush()
    coffee = db.query(Coffee).filter(Coffee.id == payload.coffee_id, Coffee.user_id == u.id).first() if payload.coffee_id else None
    create_activity(
        db,
        u,
        "compartilhou degustação",
        "sensory",
        log.id,
        f"{u.name} registrou uma degustação de {coffee.name if coffee else 'café especial'}.",
    )
    db.commit()
    db.refresh(log)
    return log

# --- ENDPOINTS EXPLORADOR SENSORIAL (FASE 10) ---
@app.get("/api/sensory-explorer/profile", response_model=SensoryUserProfileResponse)
async def get_sensory_profile(
    authorization: Annotated[str | None, Depends(get_token_from_header)] = None,
    db: Session = Depends(get_db)
):
    u = await get_current_user(db, token=authorization)
    logs = db.query(SensoryLog).filter(SensoryLog.user_id == u.id).all()
    
    if not logs:
        return SensoryUserProfileResponse(
            total_evaluations=0,
            avg_aroma=0.0,
            avg_acidity=0.0,
            avg_body=0.0,
            avg_sweetness=0.0,
            avg_aftertaste=0.0,
            top_notes=[],
            preferred_roast=None,
            suggestions=["Registre pelo menos uma degustação no Diário Sensorial para gerar seu perfil."]
        )
    
    count = len(logs)
    avg_aroma = round(sum(l.aroma_score for l in logs) / count, 1)
    avg_acidity = round(sum(l.acidity_score for l in logs) / count, 1)
    avg_body = round(sum(l.body_score for l in logs) / count, 1)
    avg_sweetness = round(sum(l.sweetness_score for l in logs) / count, 1)
    avg_aftertaste = round(sum(l.aftertaste_score for l in logs) / count, 1)
    
    # Extração de notas mais percebidas
    all_notes = []
    for l in logs:
        if l.perceived_notes:
            notes_split = [n.strip().capitalize() for n in l.perceived_notes.replace(',', ';').split(';') if n.strip()]
            all_notes.extend(notes_split)
    
    from collections import Counter
    top_notes = [item[0] for item in Counter(all_notes).most_common(5)]
    
    # Gera sugestões automáticas baseadas nas preferências
    suggestions = []
    if avg_acidity > 7.0:
        suggestions.append("Você aprecia alta acidez! Experimente métodos como Hario V60 com grãos lavados de altitude (ex: Quênia ou Colômbia).")
    if avg_body > 7.0:
        suggestions.append("Seu perfil indica preferência por corpo denso. Experimente Prensa Francesa ou Aeropress com filtros de metal.")
    if avg_sweetness < 5.0:
        suggestions.append("Dica de extração: Tente ajustar a moagem um pouco mais fina ou elevar ligeiramente a temperatura para maximizar a extração de doçura.")
    if not suggestions:
        suggestions.append("Seu paladar está bem equilibrado entre acidez, corpo e doçura!")

    return SensoryUserProfileResponse(
        total_evaluations=count,
        avg_aroma=avg_aroma,
        avg_acidity=avg_acidity,
        avg_body=avg_body,
        avg_sweetness=avg_sweetness,
        avg_aftertaste=avg_aftertaste,
        top_notes=top_notes,
        preferred_roast="Média",
        suggestions=suggestions
    )

# --- ROTA DO SERVICE WORKER ---
BASE_DIR = Path(__file__).resolve().parent


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        BASE_DIR / "sw.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache"
        },
    )

# --- FALLBACK DA SPA ---
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index_file = static_path / "index.html"
    if index_file.exists(): return FileResponse(str(index_file))
    return JSONResponse({"detail": "index.html não encontrado"}, status_code=404)

# --- ENDPOINTS DE EXECUÇÃO DE EXTRAÇÃO (FASE 7)
@app.post("/api/extractions", response_model=ExtractionResponse)
async def record_extraction(ext_in: ExtractionCreate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    
    # Salva o log de extração
    new_ext = Extraction(**ext_in.model_dump(), user_id=u.id)
    db.add(new_ext)
    db.flush()
    recipe = db.query(Recipe).filter(Recipe.id == ext_in.recipe_id, Recipe.user_id == u.id).first() if ext_in.recipe_id else None
    create_activity(
        db,
        u,
        "registrou extração",
        "extraction",
        new_ext.id,
        f"{u.name} registrou uma extração{f' de {recipe.name}' if recipe else ''}.",
    )
    db.commit()
    db.refresh(new_ext)
    
    # Automação de Estoque: Se houver receita vinculada e grão definido, deduz o peso usado
    if ext_in.recipe_id:
        rec = db.query(Recipe).filter(Recipe.id == ext_in.recipe_id, Recipe.user_id == u.id).first()
        if rec and rec.coffee_id:
            stk = db.query(Stock).join(Coffee).filter(Stock.coffee_id == rec.coffee_id, Coffee.user_id == u.id).first()
            if stk:
                stk.current_quantity = max(0.0, stk.current_quantity - rec.coffee_weight)
                db.add(StockMovement(
                    stock_id=stk.id,
                    quantity_changed=-rec.coffee_weight,
                    action_type="consumo",
                    notes=f"Consumo automático via preparo da receita: {rec.name}"
                ))
                db.commit()
                
    return new_ext

