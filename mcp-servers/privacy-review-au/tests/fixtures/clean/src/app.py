import argon2

def hash_password(pw: str) -> str:
    return argon2.PasswordHasher().hash(pw)

API = "https://api.widgets.example.com"
