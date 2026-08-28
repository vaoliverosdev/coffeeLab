from functools import lru_cache
from datetime import datetime, timedelta, timezone, date
from typing import Optional, List, Any
import bcrypt
import re
from jose import jwt
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, String, Integer, Boolean, Text, Float, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship

class Settings(BaseSettings):
    database_url: str = "sqlite:///./coffee_lab_dev.db"
    secret_key: str = "change-me-to-something-really-truly-secret"
    openrouter_api_key: Optional[str] = None
    app_env: str = "development"
    public_base_url: str = "http://localhost:8000"
    allowed_origins: str = "*"
    google_client_id: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: str = "Coffee Lab"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache
def get_settings() -> Settings:
    return Settings()

class Base(DeclarativeBase):
    pass

# --- MODELO DE USUÁRIO ---
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(80), unique=True, index=True, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(510), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    favorite_methods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    favorite_roasteries: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    sensory_preferences: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    mastered_methods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    barista_setup: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_public_profile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    profile_visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False)
    diary_visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_token_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    email_verification_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    password_reset_token_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    password_reset_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    password_login_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    coffees: Mapped[List["Coffee"]] = relationship("Coffee", back_populates="user", cascade="all, delete-orphan")
    recipes: Mapped[List["Recipe"]] = relationship("Recipe", back_populates="user", cascade="all, delete-orphan")

# --- MODELO DE CAFÉ ---
class Coffee(Base):
    __tablename__ = "cafes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    roastery: Mapped[str] = mapped_column(String(255), nullable=False)
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    variety: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    process: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    altitude: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    roast_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    roast_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sensory_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sca_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(String(510), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User", back_populates="coffees")
    stock: Mapped[Optional["Stock"]] = relationship("Stock", back_populates="coffee", cascade="all, delete-orphan", uselist=False)
    recipes: Mapped[List["Recipe"]] = relationship("Recipe", back_populates="coffee")

# --- MODELO DE ESTOQUE ---
class Stock(Base):
    __tablename__ = "stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    coffee_id: Mapped[int] = mapped_column(Integer, ForeignKey("cafes.id", ondelete="CASCADE"), unique=True, nullable=False)
    current_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    min_quantity: Mapped[float] = mapped_column(Float, default=50.0)
    is_opened: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    coffee: Mapped["Coffee"] = relationship("Coffee", back_populates="stock")
    movements: Mapped[List["StockMovement"]] = relationship("StockMovement", back_populates="stock", cascade="all, delete-orphan")

class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.id", ondelete="CASCADE"), nullable=False)
    quantity_changed: Mapped[float] = mapped_column(Float, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    stock: Mapped["Stock"] = relationship("Stock", back_populates="movements")

# --- MODELO DE RECEITA (FASE 5) ---
class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    coffee_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cafes.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(100), nullable=False) # V60, Aeropress, Chemex, etc
    coffee_weight: Mapped[float] = mapped_column(Float, nullable=False) # g
    water_weight: Mapped[float] = mapped_column(Float, nullable=False) # g
    grind_size: Mapped[Optional[str]] = mapped_column(String(100), nullable=True) # Fina, Média, 24 cliques
    water_temp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # °C
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    steps: Mapped[Optional[Any]] = mapped_column(JSON, default=list) # Lista de instruções estruturadas
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="recipes")
    coffee: Mapped[Optional["Coffee"]] = relationship("Coffee", back_populates="recipes")


# --- ENGINE CONFIG ---
engine_kwargs = {
    "pool_pre_ping": True,
    "echo": get_settings().app_env == "debug",
}
if get_settings().database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(get_settings().database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- SEGURANÇA ---
ALGORITHM = "HS256"
def hash_password(p: str) -> str: return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
def verify_password(p: str, h: str) -> bool: return bcrypt.checkpw(p.encode('utf-8'), h.encode('utf-8'))
def create_access_token(data: dict, d: Optional[timedelta] = None) -> str:
    encode = data.copy()
    encode.update({"exp": int((datetime.now(timezone.utc) + (d or timedelta(days=7))).timestamp())})
    return jwt.encode(encode, get_settings().secret_key, algorithm=ALGORITHM)

# --- SCHEMAS PYDANTIC EXISTENTES ---
COMMON_PASSWORDS = {"12345", "123456", "12345678", "123456789", "password", "senha123", "abcde", "abcdef"}

def validate_password_strength(password: str, email: str | None = None) -> str:
    if len(password) < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
    if password.lower() in COMMON_PASSWORDS:
        raise ValueError("Escolha uma senha menos óbvia.")
    if email and email.split("@")[0].lower() in password.lower():
        raise ValueError("A senha não deve conter partes do seu e-mail.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("A senha precisa ter pelo menos uma letra maiúscula.")
    if not re.search(r"[a-z]", password):
        raise ValueError("A senha precisa ter pelo menos uma letra minúscula.")
    if not re.search(r"\d", password):
        raise ValueError("A senha precisa ter pelo menos um número.")
    return password

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str = Field(..., min_length=2, max_length=120)

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, value: str, info):
        return validate_password_strength(value, info.data.get("email"))

class UserLogin(BaseModel): email: EmailStr; password: str
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str
    username: Optional[str] = None
    bio: Optional[str]
    avatar_url: Optional[str]
    city: Optional[str] = None
    country: Optional[str] = None
    favorite_methods: List[str] = Field(default_factory=list)
    favorite_roasteries: List[str] = Field(default_factory=list)
    sensory_preferences: List[str] = Field(default_factory=list)
    mastered_methods: List[str] = Field(default_factory=list)
    barista_setup: dict = Field(default_factory=dict)
    is_public_profile: bool = False
    profile_visibility: str = "private"
    diary_visibility: str = "private"
    is_active: bool
    email_verified: bool
    google_connected: bool = False
    password_login_enabled: bool = True
    class Config: from_attributes = True
class Token(BaseModel): access_token: str; token_type: str; user: UserResponse
class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    favorite_methods: Optional[List[str]] = None
    favorite_roasteries: Optional[List[str]] = None
    sensory_preferences: Optional[List[str]] = None
    mastered_methods: Optional[List[str]] = None
    barista_setup: Optional[dict] = None
    is_public_profile: Optional[bool] = None
    profile_visibility: Optional[str] = None
    diary_visibility: Optional[str] = None

    @field_validator("username")
    @classmethod
    def username_is_clean(cls, value: Optional[str]):
        if value is None or value == "":
            return None
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9_\\.]{3,30}", normalized):
            raise ValueError("Use 3 a 30 caracteres: letras, números, ponto ou underline.")
        return normalized
class PasswordChangeRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_is_strong(cls, value: str):
        return validate_password_strength(value)

class PasswordRecoveryRequest(BaseModel): email: EmailStr
class PasswordResetRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, value: str):
        return validate_password_strength(value)

class EmailVerificationRequest(BaseModel): token: str
class GoogleLoginRequest(BaseModel): credential: str
class AuthActionResponse(BaseModel):
    detail: str
    dev_verification_url: Optional[str] = None
    dev_reset_url: Optional[str] = None

class NotificationItem(BaseModel):
    id: str
    type: str
    title: str
    message: str
    severity: str = "info"
    created_at: datetime
    action_url: Optional[str] = None

class CoffeeCreate(BaseModel): name: str; roastery: str; origin: str; region: Optional[str] = None; variety: Optional[str] = None; process: Optional[str] = None; altitude: Optional[str] = None; roast_level: Optional[str] = None; roast_date: Optional[date] = None; sensory_notes: Optional[str] = None; sca_score: Optional[float] = None
class CoffeeUpdate(BaseModel): name: Optional[str] = None; roastery: Optional[str] = None; origin: Optional[str] = None; region: Optional[str] = None; variety: Optional[str] = None; process: Optional[str] = None; altitude: Optional[str] = None; roast_level: Optional[str] = None; roast_date: Optional[date] = None; sensory_notes: Optional[str] = None; sca_score: Optional[float] = None; is_favorite: Optional[bool] = None
class CoffeeResponse(BaseModel):
    id: int; user_id: int; name: str; roastery: str; origin: str; region: Optional[str]; variety: Optional[str]; process: Optional[str]; altitude: Optional[str]; roast_level: Optional[str]; roast_date: Optional[date]; sensory_notes: Optional[str]; sca_score: Optional[float]; photo_url: Optional[str]; is_favorite: bool
    class Config: from_attributes = True

class StockUpdate(BaseModel): current_quantity: Optional[float] = None; min_quantity: Optional[float] = None; is_opened: Optional[bool] = None
class StockResponse(BaseModel):
    id: int; coffee_id: int; current_quantity: float; min_quantity: float; is_opened: bool; updated_at: datetime; coffee: CoffeeResponse
    class Config: from_attributes = True

# --- SCHEMAS PYDANTIC - RECEITAS (FASE 5) ---
class RecipeCreate(BaseModel):
    coffee_id: Optional[int] = None
    name: str = Field(..., min_length=1)
    method: str
    coffee_weight: float = Field(..., gt=0)
    water_weight: float = Field(..., gt=0)
    grind_size: Optional[str] = None
    water_temp: Optional[int] = None
    description: Optional[str] = None
    steps: Optional[List[str]] = [] # Armazenado como uma lista de strings sequenciais

class RecipeUpdate(BaseModel):
    coffee_id: Optional[int] = None
    name: Optional[str] = None
    method: Optional[str] = None
    coffee_weight: Optional[float] = None
    water_weight: Optional[float] = None
    grind_size: Optional[str] = None
    water_temp: Optional[int] = None
    description: Optional[str] = None
    steps: Optional[List[str]] = None
    is_favorite: Optional[bool] = None

class RecipeResponse(BaseModel):
    id: int
    user_id: int
    coffee_id: Optional[int]
    name: str
    method: str
    coffee_weight: float
    water_weight: float
    grind_size: Optional[str]
    water_temp: Optional[int]
    description: Optional[str]
    steps: Optional[Any]
    is_favorite: bool
    created_at: datetime
    coffee: Optional[CoffeeResponse] = None

    class Config:
        from_attributes = True

#--- SCHEMAS PYDANTIC - MOTOR INTELIGENTE (FASE 6)
class MotorCalculationRequest(BaseModel):
    coffee_weight: Optional[float] = None
    water_weight: Optional[float] = None
    ratio: Optional[float] = None  # Ex: 16.0 para proporção 1:16

class MotorCalculationResponse(BaseModel):
    coffee_weight: float
    water_weight: float
    ratio: float
    suggested_grind_note: Optional[str] = None

# --- MODELO DE EXTRAÇÃO (FASE 7 & 8)
class Extraction(Base):
    __tablename__ = "extractions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipe_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True)
    coffee_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cafes.id", ondelete="SET NULL"), nullable=True)
    total_time: Mapped[int] = mapped_column(Integer, nullable=False) # em segundos
    extraction_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Adicione estes relacionamentos para permitir carregar o nome do café e receita:
    coffee: Mapped[Optional["Coffee"]] = relationship("Coffee")
    recipe: Mapped[Optional["Recipe"]] = relationship("Recipe")

# --- SCHEMAS PYDANTIC - EXTRAÇÃO
class ExtractionCreate(BaseModel):
    recipe_id: Optional[int] = None
    coffee_id: Optional[int] = None
    total_time: int
    rating: Optional[int] = None
    notes: Optional[str] = None

class ExtractionResponse(BaseModel):
    id: int
    user_id: int
    recipe_id: Optional[int]
    coffee_id: Optional[int]
    total_time: int
    extraction_date: datetime
    rating: Optional[int]
    notes: Optional[str]
    coffee: Optional[CoffeeResponse] = None
    recipe: Optional[RecipeResponse] = None

    class Config:
        from_attributes = True

# ==========================================
# --- FASE 9: MODELO DIÁRIO SENSORIAL ------
# ==========================================

class SensoryLog(Base):
    __tablename__ = "sensory_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    coffee_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cafes.id", ondelete="SET NULL"), nullable=True)
    extraction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True)
    
    aroma_score: Mapped[int] = mapped_column(Integer, default=5)      # 1 a 10
    acidity_score: Mapped[int] = mapped_column(Integer, default=5)    # 1 a 10
    body_score: Mapped[int] = mapped_column(Integer, default=5)       # 1 a 10
    sweetness_score: Mapped[int] = mapped_column(Integer, default=5)  # 1 a 10
    aftertaste_score: Mapped[int] = mapped_column(Integer, default=5) # 1 a 10
    
    perceived_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # Ex: "Frutas vermelhas, Caramelo"
    unperceived_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Notas da embalagem não sentidas
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    coffee: Mapped[Optional["Coffee"]] = relationship("Coffee")
    extraction: Mapped[Optional["Extraction"]] = relationship("Extraction")


# --- SCHEMAS PYDANTIC - DIÁRIO SENSORIAL ---

class SensoryLogCreate(BaseModel):
    coffee_id: Optional[int] = None
    extraction_id: Optional[int] = None
    aroma_score: int = 5
    acidity_score: int = 5
    body_score: int = 5
    sweetness_score: int = 5
    aftertaste_score: int = 5
    perceived_notes: Optional[str] = None
    unperceived_notes: Optional[str] = None
    comments: Optional[str] = None

class SensoryLogResponse(BaseModel):
    id: int
    user_id: int
    coffee_id: Optional[int]
    extraction_id: Optional[int]
    aroma_score: int
    acidity_score: int
    body_score: int
    sweetness_score: int
    aftertaste_score: int
    perceived_notes: Optional[str]
    unperceived_notes: Optional[str]
    comments: Optional[str]
    created_at: datetime
    coffee: Optional[CoffeeResponse] = None

    class Config:
        from_attributes = True

# --- SCHEMAS PYDANTIC - EXPLORADOR SENSORIAL (FASE 10) ---
class SensoryUserProfileResponse(BaseModel):
    total_evaluations: int
    avg_aroma: float
    avg_acidity: float
    avg_body: float
    avg_sweetness: float
    avg_aftertaste: float
    top_notes: List[str]
    preferred_roast: Optional[str] = None
    suggestions: List[str]

# --- ADICIONE JUNTO COM AS OUTRAS TABELAS DO BANCO DE DADOS ---
class Beverage(Base):
    __tablename__ = "beverages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_cold: Mapped[bool] = mapped_column(Boolean, default=False)
    ingredients: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    espresso_shots: Mapped[int] = mapped_column(Integer, default=1)
    total_volume_ml: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


# --- MODELOS SOCIAIS (COMUNIDADE) ---
class Follow(Base):
    __tablename__ = "follows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    follower_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    following_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoffeeReview(Base):
    __tablename__ = "coffee_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    coffee_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cafes.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship("User")
    coffee: Mapped[Optional["Coffee"]] = relationship("Coffee")


class CoffeeRating(Base):
    __tablename__ = "coffee_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    coffee_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cafes.id", ondelete="SET NULL"), nullable=True, index=True)
    coffee_name: Mapped[str] = mapped_column(String(180), nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    scale: Mapped[str] = mapped_column(String(20), default="five", nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship("User")
    coffee: Mapped[Optional["Coffee"]] = relationship("Coffee")


class ActivityFeed(Base):
    __tablename__ = "activity_feed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    verb: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship("User")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(510), nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship("User")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship("User")


class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SavedItem(Base):
    __tablename__ = "saved_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PublicRecipe(Base):
    __tablename__ = "public_recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipe_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship("User")
    recipe: Mapped["Recipe"] = relationship("Recipe")


class CoffeeWishlist(Base):
    __tablename__ = "coffee_wishlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    coffee_name: Mapped[str] = mapped_column(String(180), nullable=False)
    roastery: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    origin: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CafeTried(Base):
    __tablename__ = "cafes_tried"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    coffee_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cafes.id", ondelete="SET NULL"), nullable=True)
    coffee_name: Mapped[str] = mapped_column(String(180), nullable=False)
    roastery: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    origin: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tried_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    coffee: Mapped[Optional["Coffee"]] = relationship("Coffee")


class CoffeeGoal(Base):
    __tablename__ = "coffee_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    current_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period: Mapped[str] = mapped_column(String(30), default="monthly", nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

# --- ADICIONE JUNTO COM OS OUTROS SCHEMAS PYDANTIC ---
class BeverageCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_cold: bool = False
    ingredients: Optional[str] = None
    espresso_shots: int = 1
    total_volume_ml: Optional[int] = None

class BeverageResponse(BeverageCreate):
    id: int
    user_id: int
    
    class Config:
        from_attributes = True # Se usar Pydantic v2 (FastAPI mais recente)
        # orm_mode = True      # Descomente essa linha e apague a de cima se usar Pydantic v1


# --- SCHEMAS SOCIAIS ---
class PublicUserSummary(BaseModel):
    id: int
    name: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class PostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1200)
    image_url: Optional[str] = None
    visibility: str = "public"


class PostResponse(BaseModel):
    id: int
    user_id: int
    content: str
    image_url: Optional[str]
    visibility: str
    created_at: datetime
    user: Optional[PublicUserSummary] = None
    likes_count: int = 0
    comments_count: int = 0
    liked_by_me: bool = False

    class Config:
        from_attributes = True


class CoffeeReviewCreate(BaseModel):
    coffee_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=180)
    body: Optional[str] = Field(default=None, max_length=2000)
    rating: float = Field(..., ge=1, le=5)
    visibility: str = "public"


class CoffeeReviewResponse(BaseModel):
    id: int
    user_id: int
    coffee_id: Optional[int]
    title: str
    body: Optional[str]
    rating: float
    visibility: str
    created_at: datetime
    user: Optional[PublicUserSummary] = None
    coffee: Optional[CoffeeResponse] = None
    likes_count: int = 0
    comments_count: int = 0
    liked_by_me: bool = False

    class Config:
        from_attributes = True


class CoffeeRatingCreate(BaseModel):
    coffee_id: Optional[int] = None
    coffee_name: str = Field(..., min_length=1, max_length=180)
    rating: float = Field(..., ge=0, le=100)
    scale: str = "five"
    visibility: str = "public"


class CoffeeRatingResponse(BaseModel):
    id: int
    user_id: int
    coffee_id: Optional[int]
    coffee_name: str
    rating: float
    scale: str
    visibility: str
    created_at: datetime
    user: Optional[PublicUserSummary] = None
    coffee: Optional[CoffeeResponse] = None

    class Config:
        from_attributes = True


class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=800)


class CommentResponse(BaseModel):
    id: int
    user_id: int
    target_type: str
    target_id: int
    body: str
    created_at: datetime
    user: Optional[PublicUserSummary] = None

    class Config:
        from_attributes = True


class WishlistCreate(BaseModel):
    coffee_name: str = Field(..., min_length=1, max_length=180)
    roastery: Optional[str] = Field(default=None, max_length=180)
    origin: Optional[str] = Field(default=None, max_length=180)
    notes: Optional[str] = Field(default=None, max_length=1000)


class WishlistResponse(WishlistCreate):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class TriedCoffeeCreate(BaseModel):
    coffee_id: Optional[int] = None
    coffee_name: str = Field(..., min_length=1, max_length=180)
    roastery: Optional[str] = Field(default=None, max_length=180)
    origin: Optional[str] = Field(default=None, max_length=180)
    rating: Optional[float] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=1000)


class TriedCoffeeResponse(TriedCoffeeCreate):
    id: int
    user_id: int
    tried_at: datetime

    class Config:
        from_attributes = True


class CoffeeGoalCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=180)
    goal_type: str = Field(..., min_length=1, max_length=50)
    target_value: int = Field(..., gt=0, le=10000)
    period: str = "monthly"


class CoffeeGoalResponse(CoffeeGoalCreate):
    id: int
    user_id: int
    current_value: int
    is_completed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PublicRecipeResponse(BaseModel):
    id: int
    user_id: int
    recipe_id: int
    title: str
    description: Optional[str]
    created_at: datetime
    user: Optional[PublicUserSummary] = None
    recipe: Optional[RecipeResponse] = None
    likes_count: int = 0
    saves_count: int = 0
    saved_by_me: bool = False

    class Config:
        from_attributes = True


class ActivityResponse(BaseModel):
    id: int
    user_id: int
    verb: str
    target_type: str
    target_id: Optional[int]
    summary: str
    visibility: str
    created_at: datetime
    user: Optional[PublicUserSummary] = None
    likes_count: int = 0
    comments_count: int = 0
    liked_by_me: bool = False

    class Config:
        from_attributes = True
