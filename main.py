import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import User as UserSchema, Problem as ProblemSchema, Submission as SubmissionSchema

# App setup
app = FastAPI(title="LeetCode-style API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth setup
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class SignupModel(BaseModel):
    name: str
    email: str
    password: str
    is_admin: bool = False


class LoginModel(BaseModel):
    email: str
    password: str


class CreateProblemModel(ProblemSchema):
    pass


class RunSubmitModel(BaseModel):
    problem_id: str
    language: str
    code: str


# Utilities

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain_password, password_hash):
    return pwd_context.verify(plain_password, password_hash)


def get_password_hash(password):
    return pwd_context.hash(password)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        is_admin: bool = payload.get("is_admin", False)
        if user_id is None:
            raise credentials_exception
        return {"_id": user_id, "email": email, "is_admin": is_admin}
    except JWTError:
        raise credentials_exception


# Routes
@app.get("/")
def root():
    return {"message": "API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set" if not os.getenv("DATABASE_URL") else "✅ Set",
        "database_name": "❌ Not Set" if not os.getenv("DATABASE_NAME") else "✅ Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "❌ Not Available"
    except Exception as e:
        response["database"] = f"⚠️ {str(e)[:60]}"
    return response


# Auth
@app.post("/auth/signup", response_model=TokenResponse)
def signup(payload: SignupModel):
    if db is None:
        raise HTTPException(500, "Database not configured")

    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(400, "Email already registered")

    user_doc = UserSchema(
        email=payload.email,
        name=payload.name,
        password_hash=get_password_hash(payload.password),
        is_admin=payload.is_admin,
    )
    user_id = create_document("user", user_doc)

    token = create_access_token({"sub": user_id, "email": payload.email, "is_admin": payload.is_admin})
    return {"access_token": token, "user": {"_id": user_id, "email": payload.email, "name": payload.name, "isAdmin": payload.is_admin}}


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginModel):
    if db is None:
        raise HTTPException(500, "Database not configured")

    user = db["user"].find_one({"email": payload.email})
    if not user:
        raise HTTPException(401, "Invalid credentials")

    if not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(401, "Invalid credentials")

    token = create_access_token({"sub": str(user.get("_id")), "email": user.get("email"), "is_admin": user.get("is_admin", False)})
    return {"access_token": token, "user": {"_id": str(user.get("_id")), "email": user.get("email"), "name": user.get("name"), "isAdmin": user.get("is_admin", False)}}


# Problems
@app.get("/problems")
def get_problems():
    docs = get_documents("problem")
    out = []
    for d in docs:
        out.append({
            "_id": str(d.get("_id")),
            "title": d.get("title"),
            "difficulty": d.get("difficulty"),
        })
    return out


@app.get("/problems/{pid}")
def get_problem(pid: str):
    from bson.objectid import ObjectId
    try:
        obj_id = ObjectId(pid)
    except Exception:
        raise HTTPException(400, "Invalid id")
    doc = db["problem"].find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(404, "Problem not found")
    doc["_id"] = str(doc["_id"]) 
    return doc


@app.post("/problems")
def create_problem(problem: CreateProblemModel, user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Admins only")
    pid = create_document("problem", problem)
    return {"_id": pid}


# Submissions (mock runner)
@app.post("/submit/run")
def run_code(payload: RunSubmitModel, user=Depends(get_current_user)):
    status = "Accepted"
    stderr = ""
    stdout = "Ran sample tests successfully."
    if "fail" in payload.code.lower():
        status = "Wrong Answer"
        stdout = ""
        stderr = "Expected output mismatch on sample test."
    return {"status": status, "stdout": stdout, "stderr": stderr}


@app.post("/submit")
def submit_code(payload: RunSubmitModel, user=Depends(get_current_user)):
    res = run_code(payload, user)  # type: ignore
    doc = SubmissionSchema(
        user_id=user.get("_id"),
        problem_id=payload.problem_id,
        language=payload.language,
        code=payload.code,
        status=res["status"],
        stdout=res.get("stdout", ""),
        stderr=res.get("stderr", ""),
    )
    sid = create_document("submission", doc)
    return {"_id": sid, **res}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
