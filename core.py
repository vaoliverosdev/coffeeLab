from functools import lru_cache
from datetime import datetime, timedelta, timezone, date
from typing import Optional, List, Any
import bcrypt
from jose import jwt
from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, String, Integer, Boolean, Text, Float, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://user:pass@localhost/coffee_lab"
    secret_key: str = "change-me-to-something-really-truly-secret"
    openrouter_api_key: Optional[str] = None
    app_env: str = "development"

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
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(510), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

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
engine = create_engine(get_settings().database_url, pool_pre_ping=True, echo=get_settings().app_env == "development")
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
class UserCreate(BaseModel): email: EmailStr; password: str; name: str
class UserLogin(BaseModel): email: EmailStr; password: str
class UserResponse(BaseModel):
    id: int; email: EmailStr; name: str; bio: Optional[str]; avatar_url: Optional[str]; is_active: bool
    class Config: from_attributes = True
class Token(BaseModel): access_token: str; token_type: str; user: UserResponse
class ProfileUpdate(BaseModel): name: Optional[str] = None; bio: Optional[str] = None
class PasswordRecoveryRequest(BaseModel): email: EmailStr

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