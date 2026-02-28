"""
A2Apex Authentication Module

User accounts, JWT tokens, and API key management.
"""

import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
import bcrypt
from jose import JWTError, jwt


# ============================================================================
# CONFIGURATION
# ============================================================================

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "users.db"
SECRET_KEY_PATH = Path(__file__).parent.parent / "data" / ".secret_key"

# JWT Settings
def get_secret_key():
    """Get or generate a stable secret key."""
    if os.getenv("A2APEX_SECRET_KEY"):
        return os.getenv("A2APEX_SECRET_KEY")
    
    # Try to load from file
    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_text().strip()
    
    # Generate and save new key
    key = secrets.token_urlsafe(32)
    SECRET_KEY_PATH.write_text(key)
    return key

SECRET_KEY = get_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Bearer token security
security = HTTPBearer(auto_error=False)


# ============================================================================
# DATABASE SETUP
# ============================================================================

def get_db():
    """Get database connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with users table."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            api_key TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)
    
    # Create index for faster lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key)")
    
    conn.commit()
    conn.close()


# Initialize database on module load
init_db()


# ============================================================================
# MODELS
# ============================================================================

class UserCreate(BaseModel):
    """Request model for user registration."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    name: str = Field(..., min_length=1, max_length=100)


class UserLogin(BaseModel):
    """Request model for user login."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Response model for user data."""
    id: int
    email: str
    name: str
    plan: str
    api_key: str
    created_at: str


class TokenResponse(BaseModel):
    """Response model for JWT token."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    # bcrypt has a 72 byte limit, truncate if necessary
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    password_bytes = plain_password.encode('utf-8')[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def generate_api_key() -> str:
    """Generate a unique API key."""
    return f"a2apex_{secrets.token_urlsafe(32)}"


def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {
        "sub": str(user_id),  # JWT spec requires sub to be a string
        "exp": expire
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user by ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_api_key(api_key: str) -> Optional[dict]:
    """Get user by API key."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE api_key = ?", (api_key,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(email: str, password: str, name: str) -> dict:
    """Create a new user."""
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.utcnow().isoformat() + "Z"
    password_hash = hash_password(password)
    api_key = generate_api_key()
    
    cursor.execute("""
        INSERT INTO users (email, password_hash, name, plan, api_key, created_at)
        VALUES (?, ?, ?, 'free', ?, ?)
    """, (email.lower(), password_hash, name, api_key, now))
    
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {
        "id": user_id,
        "email": email.lower(),
        "name": name,
        "plan": "free",
        "api_key": api_key,
        "created_at": now
    }


def user_to_response(user: dict) -> UserResponse:
    """Convert user dict to response model."""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        plan=user["plan"],
        api_key=user["api_key"],
        created_at=user["created_at"]
    )


# ============================================================================
# AUTH DEPENDENCY
# ============================================================================

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get the current authenticated user from JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = int(user_id_str)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    """Get current user if authenticated, None otherwise."""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate):
    """
    Register a new user account.
    
    Returns a JWT access token and user profile.
    Each user gets a unique API key for authenticated requests.
    """
    # Check if email already exists
    existing = get_user_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create the user
    user = create_user(data.email, data.password, data.name)
    
    # Generate JWT token
    access_token = create_access_token(user["id"])
    
    return TokenResponse(
        access_token=access_token,
        user=user_to_response(user)
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin):
    """
    Login with email and password.
    
    Returns a JWT access token and user profile.
    """
    user = get_user_by_email(data.email)
    
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Generate JWT token
    access_token = create_access_token(user["id"])
    
    return TokenResponse(
        access_token=access_token,
        user=user_to_response(user)
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Get the current authenticated user's profile.
    
    Requires a valid JWT token in the Authorization header.
    """
    return user_to_response(current_user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """
    Refresh the JWT access token.
    
    Returns a new token with extended expiry.
    """
    access_token = create_access_token(current_user["id"])
    
    return TokenResponse(
        access_token=access_token,
        user=user_to_response(current_user)
    )


@router.post("/regenerate-api-key", response_model=UserResponse)
async def regenerate_api_key(current_user: dict = Depends(get_current_user)):
    """
    Generate a new API key for the current user.
    
    The old API key will be invalidated.
    """
    new_api_key = generate_api_key()
    now = datetime.utcnow().isoformat() + "Z"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET api_key = ?, updated_at = ? WHERE id = ?",
        (new_api_key, now, current_user["id"])
    )
    conn.commit()
    conn.close()
    
    # Get updated user
    user = get_user_by_id(current_user["id"])
    return user_to_response(user)
