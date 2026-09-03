from functools import lru_cache
from datetime import datetime, timedelta, timezone, date
from typing import Optional, List, Any
import bcrypt
import re
from jose import jwt
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, String, Integer, Boolean, Text, Float, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship

DEFAULT_SECRET_KEY = "change-me-to-something-really-truly-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./coffee_lab_dev.db"
    secret_key: str = DEFAULT_SECRET_KEY
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
    strict_production_config: bool = False

@lru_cache
def get_settings() -> Settings:
    return Settings()

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_runtime_settings() -> None:
    settings = get_settings()
    if settings.app_env.lower() != "production":
        return

    errors = []
    if not settings.secret_key or settings.secret_key == DEFAULT_SECRET_KEY or len(settings.secret_key) < 32:
        errors.append("configure uma SECRET_KEY forte com pelo menos 32 caracteres")
    if settings.allowed_origins.strip() in {"", "*"}:
        errors.append("restrinja ALLOWED_ORIGINS ao domínio público do app")
    if settings.public_base_url.startswith(("http://localhost", "http://127.0.0.1")):
        errors.append("configure PUBLIC_BASE_URL com a URL pública de produção")
    if settings.database_url.startswith("sqlite"):
        errors.append("configure DATABASE_URL com PostgreSQL/NeonDB em produção")

    if errors:
        message = "Configuração de produção incompleta: " + "; ".join(errors) + "."
        if settings.strict_production_config:
            raise RuntimeError(message)
        print(f"[Config] {message}")

class Base(DeclarativeBase):
    pass

# --- MODELO DE USUÁRIO ---
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(510), nullable=True)
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

    @property
    def google_connected(self) -> bool:
        return bool(self.google_sub)

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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    coffee: Mapped["Coffee"] = relationship("Coffee", back_populates="stock")
    movements: Mapped[List["StockMovement"]] = relationship("StockMovement", back_populates="stock", cascade="all, delete-orphan")

class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.id", ondelete="CASCADE"), nullable=False)
    quantity_changed: Mapped[float] = mapped_column(Float, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

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

class UserLogin(BaseModel): email: EmailStr; password: str = Field(..., min_length=1, max_length=256)
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int; email: EmailStr; name: str; bio: Optional[str]; avatar_url: Optional[str]; is_active: bool; email_verified: bool; google_connected: bool = False; password_login_enabled: bool = True
class Token(BaseModel): access_token: str; token_type: str; user: UserResponse
class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    bio: Optional[str] = Field(None, max_length=1000)
class PasswordChangeRequest(BaseModel):
    current_password: Optional[str] = Field(None, max_length=256)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_is_strong(cls, value: str):
        return validate_password_strength(value)

class PasswordRecoveryRequest(BaseModel): email: EmailStr
class PasswordResetRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=256)
    password: str

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, value: str):
        return validate_password_strength(value)

class EmailVerificationRequest(BaseModel): token: str = Field(..., min_length=16, max_length=256)
class GoogleLoginRequest(BaseModel): credential: str = Field(..., min_length=1, max_length=4096)
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

class CoffeeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    roastery: str = Field(..., min_length=1, max_length=120)
    origin: str = Field(..., min_length=1, max_length=120)
    region: Optional[str] = Field(None, max_length=120)
    variety: Optional[str] = Field(None, max_length=120)
    process: Optional[str] = Field(None, max_length=80)
    altitude: Optional[str] = Field(None, max_length=80)
    roast_level: Optional[str] = Field(None, max_length=80)
    roast_date: Optional[date] = None
    sensory_notes: Optional[str] = Field(None, max_length=1000)
    sca_score: Optional[float] = Field(None, ge=0, le=100)
class CoffeeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    roastery: Optional[str] = Field(None, min_length=1, max_length=120)
    origin: Optional[str] = Field(None, min_length=1, max_length=120)
    region: Optional[str] = Field(None, max_length=120)
    variety: Optional[str] = Field(None, max_length=120)
    process: Optional[str] = Field(None, max_length=80)
    altitude: Optional[str] = Field(None, max_length=80)
    roast_level: Optional[str] = Field(None, max_length=80)
    roast_date: Optional[date] = None
    sensory_notes: Optional[str] = Field(None, max_length=1000)
    sca_score: Optional[float] = Field(None, ge=0, le=100)
    is_favorite: Optional[bool] = None
class CoffeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int; user_id: int; name: str; roastery: str; origin: str; region: Optional[str]; variety: Optional[str]; process: Optional[str]; altitude: Optional[str]; roast_level: Optional[str]; roast_date: Optional[date]; sensory_notes: Optional[str]; sca_score: Optional[float]; photo_url: Optional[str]; is_favorite: bool

class StockUpdate(BaseModel):
    current_quantity: Optional[float] = Field(None, ge=0, le=100000)
    min_quantity: Optional[float] = Field(None, ge=0, le=100000)
    is_opened: Optional[bool] = None
class StockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int; coffee_id: int; current_quantity: float; min_quantity: float; is_opened: bool; updated_at: datetime; coffee: CoffeeResponse

# --- SCHEMAS PYDANTIC - RECEITAS (FASE 5) ---
class RecipeCreate(BaseModel):
    coffee_id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=120)
    method: str = Field(..., min_length=1, max_length=80)
    coffee_weight: float = Field(..., gt=0, le=1000)
    water_weight: float = Field(..., gt=0, le=10000)
    grind_size: Optional[str] = Field(None, max_length=120)
    water_temp: Optional[int] = Field(None, ge=0, le=100)
    description: Optional[str] = Field(None, max_length=1000)
    steps: Optional[List[str]] = Field(default_factory=list) # Armazenado como uma lista de strings sequenciais

    @field_validator("steps")
    @classmethod
    def steps_are_reasonable(cls, value):
        if value is None:
            return value
        if len(value) > 20:
            raise ValueError("A receita pode ter no máximo 20 etapas.")
        if any(len(str(step)) > 500 for step in value):
            raise ValueError("Cada etapa da receita pode ter no máximo 500 caracteres.")
        return value

class RecipeUpdate(BaseModel):
    coffee_id: Optional[int] = None
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    method: Optional[str] = Field(None, min_length=1, max_length=80)
    coffee_weight: Optional[float] = Field(None, gt=0, le=1000)
    water_weight: Optional[float] = Field(None, gt=0, le=10000)
    grind_size: Optional[str] = Field(None, max_length=120)
    water_temp: Optional[int] = Field(None, ge=0, le=100)
    description: Optional[str] = Field(None, max_length=1000)
    steps: Optional[List[str]] = None
    is_favorite: Optional[bool] = None

    @field_validator("steps")
    @classmethod
    def steps_are_reasonable(cls, value):
        if value is None:
            return value
        if len(value) > 20:
            raise ValueError("A receita pode ter no máximo 20 etapas.")
        if any(len(str(step)) > 500 for step in value):
            raise ValueError("Cada etapa da receita pode ter no máximo 500 caracteres.")
        return value

class RecipeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

#--- SCHEMAS PYDANTIC - MOTOR INTELIGENTE (FASE 6)
class MotorCalculationRequest(BaseModel):
    coffee_weight: Optional[float] = Field(None, gt=0, le=1000)
    water_weight: Optional[float] = Field(None, gt=0, le=10000)
    ratio: Optional[float] = Field(None, gt=0, le=100)  # Ex: 16.0 para proporção 1:16

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
    extraction_date: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Adicione estes relacionamentos para permitir carregar o nome do café e receita:
    coffee: Mapped[Optional["Coffee"]] = relationship("Coffee")
    recipe: Mapped[Optional["Recipe"]] = relationship("Recipe")

# --- SCHEMAS PYDANTIC - EXTRAÇÃO
class ExtractionCreate(BaseModel):
    recipe_id: Optional[int] = None
    coffee_id: Optional[int] = None
    total_time: int = Field(..., gt=0, le=7200)
    rating: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = Field(None, max_length=1000)

class ExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    coffee: Mapped[Optional["Coffee"]] = relationship("Coffee")
    extraction: Mapped[Optional["Extraction"]] = relationship("Extraction")


# --- SCHEMAS PYDANTIC - DIÁRIO SENSORIAL ---

class SensoryLogCreate(BaseModel):
    coffee_id: Optional[int] = None
    extraction_id: Optional[int] = None
    aroma_score: int = Field(5, ge=1, le=10)
    acidity_score: int = Field(5, ge=1, le=10)
    body_score: int = Field(5, ge=1, le=10)
    sweetness_score: int = Field(5, ge=1, le=10)
    aftertaste_score: int = Field(5, ge=1, le=10)
    perceived_notes: Optional[str] = Field(None, max_length=1000)
    unperceived_notes: Optional[str] = Field(None, max_length=1000)
    comments: Optional[str] = Field(None, max_length=1000)

class SensoryLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

# --- ADICIONE JUNTO COM OS OUTROS SCHEMAS PYDANTIC ---
class BeverageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=1000)
    is_cold: bool = False
    ingredients: Optional[str] = Field(None, max_length=1000)
    espresso_shots: int = Field(1, ge=0, le=12)
    total_volume_ml: Optional[int] = Field(None, ge=0, le=5000)

class BeverageResponse(BeverageCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
