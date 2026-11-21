
import os
import time
import uuid
import hmac
import hashlib

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="HADBAI PES Images API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/")
def home():
    return {"message": "HADBAI PES Images server is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/imagekit/auth")
def imagekit_auth(authorization: str | None = Header(default=None)):
    # Authentication must be verified server-side before signing uploads.
    raise HTTPException(
        status_code=503,
        detail="Upload authentication is not configured yet",
    )
