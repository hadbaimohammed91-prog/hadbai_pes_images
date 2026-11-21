
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
    private_key = os.getenv("IMAGEKIT_PRIVATE_KEY", "").strip()

    if not private_key:
        raise HTTPException(
            status_code=503,
            detail="IMAGEKIT_PRIVATE_KEY is missing",
        )

    # Do not issue upload signatures without verifying
    # the caller's Firebase identity.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Firebase authentication required",
        )

    # Firebase Admin token verification will be added
    # before enabling signed uploads.
    raise HTTPException(
        status_code=503,
        detail="Firebase token verification is not configured yet",
    )
