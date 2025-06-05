'''
Security utilities for password hashing and verification.
This module uses Passlib for secure password hashing.
'''
from passlib.context import CryptContext


# Importing CryptContext from Passlib to handle password hashing
# and verification securely.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)
