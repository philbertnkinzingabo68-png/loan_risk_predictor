from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from jose import JWTError, jwt
from passlib.context import CryptContext
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import uuid

# --- Config ---
SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- Setup FastAPI ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Password hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Database setup ---
conn = sqlite3.connect("loan_db.sqlite3", check_same_thread=False)
cursor = conn.cursor()

# Users
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    email TEXT,
    password TEXT
)
""")

# Predictions history
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    name TEXT,
    annual_income REAL,
    debt_to_income_ratio REAL,
    credit_score REAL,
    loan_amount REAL,
    interest_rate REAL,
    gender TEXT,
    marital_status TEXT,
    education_level TEXT,
    employment_status TEXT,
    loan_purpose TEXT,
    grade_subgrade TEXT,
    prediction_type TEXT,
    prediction INTEGER,
    probability REAL,
    created_at TEXT
)
""")
conn.commit()

# --- Pydantic models ---
class UserRegister(BaseModel):
    username: str
    password: str
    email: str

class UserLogin(BaseModel):
    username: str
    password: str

class SinglePrediction(BaseModel):
    name: str
    annual_income: float
    debt_to_income_ratio: float
    credit_score: float
    loan_amount: float
    interest_rate: float
    gender: str
    marital_status: str
    education_level: str
    employment_status: str
    loan_purpose: str
    grade_subgrade: str

# --- Auth helpers ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(lambda: None)):
    from fastapi import Header
    authorization: str = token
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    cursor.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

# --- Routes ---
@app.post("/register")
def register(user: UserRegister):
    hashed = get_password_hash(user.password)
    try:
        cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                       (user.username, user.email, hashed))
        conn.commit()
        access_token = create_access_token({"sub": user.username})
        return {"access_token": access_token, "token_type": "bearer"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")

@app.post("/login")
def login(user: UserLogin):
    cursor.execute("SELECT * FROM users WHERE username=?", (user.username,))
    db_user = cursor.fetchone()
    if not db_user or not verify_password(user.password, db_user[3]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me")
def auth_me(current_user=Depends(get_current_user)):
    return {"username": current_user[1], "email": current_user[2]}

@app.post("/predict/single")
def predict_single(pred: SinglePrediction, current_user=Depends(get_current_user)):
    # Dummy ML logic: approve if credit_score > 650 and DTI < 0.4
    probability = min(max((pred.credit_score - 600)/200 * (0.4 - pred.debt_to_income_ratio), 0), 1)
    prediction = 1 if probability >= 0.5 else 0
    
    pred_id = str(uuid.uuid4())
    cursor.execute("""
    INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pred_id, current_user[0], pred.name, pred.annual_income, pred.debt_to_income_ratio,
        pred.credit_score, pred.loan_amount, pred.interest_rate, pred.gender,
        pred.marital_status, pred.education_level, pred.employment_status,
        pred.loan_purpose, pred.grade_subgrade, "single", prediction, probability,
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    return {"id": pred_id, "prediction": prediction, "probability": probability}

@app.post("/predict_batch")
def predict_batch(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    df = pd.read_csv(file.file)
    results = []
    for _, row in df.iterrows():
        prob = min(max((row['credit_score'] - 600)/200 * (0.4 - row['debt_to_income_ratio']), 0), 1)
        pred_val = 1 if prob >= 0.5 else 0
        pred_id = str(uuid.uuid4())
        results.append({"id": pred_id, "prediction": pred_val, "probability": prob})
        cursor.execute("""
        INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pred_id, current_user[0], row['name'], row['annual_income'], row['debt_to_income_ratio'],
            row['credit_score'], row['loan_amount'], row['interest_rate'], row['gender'],
            row['marital_status'], row['education_level'], row['employment_status'],
            row['loan_purpose'], row['grade_subgrade'], "batch", pred_val, prob,
            datetime.utcnow().isoformat()
        ))
    conn.commit()
    return {"count": len(results), "batch_id": str(uuid.uuid4())}

@app.get("/predictions/history")
def get_history(current_user=Depends(get_current_user)):
    cursor.execute("SELECT * FROM predictions WHERE user_id=? ORDER BY created_at DESC", (current_user[0],))
    rows = cursor.fetchall()
    keys = [description[0] for description in cursor.description]
    return [dict(zip(keys, r)) for r in rows]
