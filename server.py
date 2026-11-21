
import os
import time
import uuid
import hmac
import hashlib

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="HADBAI PES Images API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Firebase Admin initialization
SERVICE_ACCOUNT_PATH = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_PATH",
    "/etc/secrets/serviceAccountKey.json"
)

FIREBASE_READY = False

try:
    if not firebase_admin._apps:
        credential = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(credential)

    FIREBASE_READY = True
    print("Firebase Admin initialized successfully")

except Exception as error:
    print("Firebase initialization error:", error)


@app.get("/")
def home():
    return {
        "message": "HADBAI PES Images server is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "firebase": FIREBASE_READY
    }


@app.post("/imagekit/auth")
def imagekit_auth(
    authorization: str | None = Header(default=None)
):
    private_key = os.getenv(
        "IMAGEKIT_PRIVATE_KEY", ""
    ).strip()

    if not private_key:
        raise HTTPException(
            status_code=503,
            detail="ImageKit private key is missing"
        )

    if not FIREBASE_READY:
        raise HTTPException(
            status_code=503,
            detail="Firebase is not initialized"
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Firebase authentication required"
        )

    id_token = authorization.split(" ", 1)[1].strip()

    try:
        decoded_token = firebase_auth.verify_id_token(id_token)

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Firebase token"
        )

    if not decoded_token.get("uid"):
        raise HTTPException(
            status_code=401,
            detail="Invalid Firebase user"
        )

    token = str(uuid.uuid4())
    expire = int(time.time()) + 60

    message = (token + str(expire)).encode("utf-8")

    signature = hmac.new(
        private_key.encode("utf-8"),
        message,
        hashlib.sha1
    ).hexdigest()

    return {
        "token": token,
        "expire": expire,
        "signature": signature
    }
