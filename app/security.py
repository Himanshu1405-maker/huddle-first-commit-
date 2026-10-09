"""Server-side Fernet encryption for chat messages and uploaded media.
Encrypted data can be decrypted by the service operator holding HUDDLE_MESSAGE_KEY.
This is NOT end-to-end encryption. Use a separately backed-up, stable key in deployment.
"""
from __future__ import annotations
import os
from cryptography.fernet import Fernet, InvalidToken

TEXT_PREFIX="huddle.enc.v1:"
FILE_PREFIX=b"HUDDLE_MEDIA_V1:"

def _cipher():
    key=os.getenv("HUDDLE_MESSAGE_KEY","").strip()
    if not key:
        return None
    return Fernet(key.encode("ascii"))

def encrypt_text(value: str) -> str:
    cipher=_cipher()
    return TEXT_PREFIX+cipher.encrypt(value.encode("utf-8")).decode("ascii") if cipher else value

def decrypt_text(value: str) -> str:
    if not value.startswith(TEXT_PREFIX):
        return value
    cipher=_cipher()
    if not cipher:
        raise RuntimeError("Encrypted messages require HUDDLE_MESSAGE_KEY")
    return cipher.decrypt(value[len(TEXT_PREFIX):].encode("ascii")).decode("utf-8")

def encrypt_bytes(raw: bytes) -> bytes:
    cipher=_cipher()
    return FILE_PREFIX+cipher.encrypt(raw) if cipher else raw

def decrypt_bytes(raw: bytes) -> bytes:
    if not raw.startswith(FILE_PREFIX):
        return raw
    cipher=_cipher()
    if not cipher:
        raise RuntimeError("Encrypted files require HUDDLE_MESSAGE_KEY")
    return cipher.decrypt(raw[len(FILE_PREFIX):])
