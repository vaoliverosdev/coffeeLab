import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional, List
from datetime import date, datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Query, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt, JWTError
from sqlalchemy.orm import Session, relationship
from sqlalchemy import or_, desc
from pydantic import BaseModel
from core import (
    Base, engine, get_db, hash_password, verify_password, 
    create_access_token, User, UserCreate, UserLogin, 
    UserResponse, Token, ProfileUpdate, PasswordRecoveryRequest, ALGORITHM, get_settings,
    Coffee, CoffeeCreate, CoffeeUpdate, CoffeeResponse,
    Stock, StockUpdate, StockResponse, StockMovement,
    Recipe, RecipeCreate, RecipeUpdate, RecipeResponse, MotorCalculationRequest, MotorCalculationResponse,
    ExtractionResponse, ExtractionCreate, Extraction, SensoryLog, SensoryLogCreate, SensoryLogResponse, 
    SensoryUserProfileResponse, Beverage, BeverageCreate, BeverageResponse, 
)
import httpx
import traceback
import re

AVATAR_DIR = Path(__file__).parent / "static" / "uploads" / "avatars"
COFFEE_DIR = Path(__file__).parent / "static" / "uploads" / "coffees"

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    COFFEE_DIR.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title="Coffee Lab", version="0.5.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
@app.post("/api/auth/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_in.email).first(): 
        raise HTTPException(status_code=400, detail="E-mail existente.")
    u = User(email=user_in.email, hashed_password=hash_password(user_in.password), name=user_in.name)
    db.add(u); db.commit(); db.refresh(u)
    return u

@app.post("/api/auth/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == credentials.email).first()
    if not u:
        raise HTTPException(status_code=404, detail="Conta não encontrada para este e-mail.")
    if not verify_password(credentials.password, u.hashed_password):
        raise HTTPException(status_code=401, detail="Senha incorreta.")
    return {"access_token": create_access_token(data={"sub": u.email}), "token_type": "bearer", "user": u}

@app.post("/api/auth/recover")
def recover_password(req: PasswordRecoveryRequest, db: Session = Depends(get_db)):
    # Resposta neutra para evitar enumeração de contas. O envio real de e-mail entra em fase posterior.
    db.query(User).filter(User.email == req.email).first()
    return {"detail": "Se este e-mail estiver cadastrado, as instruções de recuperação serão enviadas."}

@app.get("/api/auth/me", response_model=UserResponse)
async def get_me(authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    return await get_current_user(db, token=authorization)

@app.put("/api/auth/me", response_model=UserResponse)
async def update_profile(profile_data: ProfileUpdate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    if profile_data.name: u.name = profile_data.name
    if profile_data.bio is not None: u.bio = profile_data.bio
    db.commit(); db.refresh(u)
    return u

@app.post("/api/auth/me/avatar")
async def upload_avatar(file: UploadFile = File(...), authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Envie um arquivo de imagem válido.")
    ext = os.path.splitext(file.filename)[1]
    filename = f"user_{u.id}_{int(datetime.utcnow().timestamp())}{ext}"
    with open(AVATAR_DIR / filename, "wb") as b: shutil.copyfileobj(file.file, b)
    u.avatar_url = f"/static/uploads/avatars/{filename}"
    db.commit()
    return {"avatar_url": u.avatar_url}

# --- ENDPOINTS DE CAFÉS ---
@app.post("/api/coffees", response_model=CoffeeResponse)
async def create_coffee(coffee_in: CoffeeCreate, authorization: Annotated[str | None, Depends(get_token_from_header)] = None, db: Session = Depends(get_db)):
    u = await get_current_user(db, token=authorization)
    c = Coffee(**coffee_in.model_dump(), user_id=u.id)
    db.add(c); db.commit(); db.refresh(c)
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
    ext = os.path.splitext(file.filename)[1]
    filename = f"coffee_{c.id}_{int(os.path.getmtime(Path(__file__).parent))}{ext}"
    with open(COFFEE_DIR / filename, "wb") as b: shutil.copyfileobj(file.file, b)
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
    db.add(new_recipe); db.commit(); db.refresh(new_recipe)
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
    db.add(clone); db.commit(); db.refresh(clone)
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


def clean_ai_response(response: str) -> str:
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
        extractions = (
            db.query(Extraction).filter(Extraction.user_id == u.id).all()
        )

        coffees_info = (
            ", ".join(
                [
                    f"{c.name} ({c.roastery}, origem: {c.origin}, torra: {c.roast_level})"
                    for c in coffees
                ]
            )
            if coffees
            else "Nenhum café cadastrado."
        )
        recipes_info = (
            ", ".join([f"{r.name} no método {r.method}" for r in recipes])
            if recipes
            else "Nenhuma receita."
        )
        extractions_info = f"Total de extrações: {len(extractions)}"

        system_prompt = (
            f"""
            Você é o "Barista de IA", o assistente virtual oficial do Coffee Lab e especiallista na area.
            Você atua como um barista especializado em cafés especiais e como um consultor pessoal de café. Sua função é ajudar o usuário
            a tomar melhores decisões sobre seus cafés, receitas e extrações, utilizando de forma inteligente e fiel os dados disponíveis no contexto.
            Seu objetivo não é apenas responder perguntas: é ajudar o usuário a explorar, entender e melhorar sua experiência com café.

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

            Use emojis com MUITA moderação para melhorar a experiência visual, principalmente:
            ☕ 🔥 💧 ⚙️ 💡 🔎

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
        payload = {"model": "openrouter/auto", "messages": messages_payload}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers,
            )

            if response.status_code != 200:
                print(
                    "❌ RESPOSTA OPENROUTER:",
                    response.status_code,
                    response.text,
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Erro OpenRouter ({response.status_code}): {response.text}",
                )

            data = response.json()
            raw_reply = data["choices"][0]["message"]["content"]
            reply = clean_ai_response(raw_reply)

            assistant_msg = AIChatMessage(
                session_id=session.id, role="assistant", content=reply
            )
            db.add(assistant_msg)
            db.commit()

            return {"session_id": session.id, "response": reply}

    except HTTPException as http_exc:
        raise http_exc

    except Exception as e:
        print("\n🔥 --- ERRO DETECTADO NO PYTHON --- 🔥")
        traceback.print_exc()
        print("---------------------------------------\n")
        raise HTTPException(
            status_code=500, detail=f"Erro interno no servidor: {str(e)}"
        )
        
# --- SERVINDO FRONTEND ---
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

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

