import os
import time
import uuid
import hmac
import hashlib
import base64
import json
from datetime import datetime, timedelta, timezone
from urllib import request, parse, error

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth, firestore
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title='HADBAI PES Images API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['GET', 'POST', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type'],
)

SERVICE_ACCOUNT_PATH = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', '/etc/secrets/serviceAccountKey.json')
FIREBASE_READY = False
try:
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SERVICE_ACCOUNT_PATH))
    FIREBASE_READY = True
    print('Firebase Admin initialized successfully')
except Exception as exc:
    print('Firebase initialization error:', exc)


@app.get('/')
def home():
    return {'message': 'HADBAI PES Images server is running'}


@app.get('/health')
def health():
    return {'status': 'ok', 'firebase': FIREBASE_READY}


@app.post('/imagekit/auth')
def imagekit_auth(authorization: str | None = Header(default=None)):
    private_key = os.getenv('IMAGEKIT_PRIVATE_KEY', '').strip()
    if not private_key:
        raise HTTPException(status_code=503, detail='ImageKit private key is missing')
    if not FIREBASE_READY:
        raise HTTPException(status_code=503, detail='Firebase is not initialized')
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Firebase authentication required')
    id_token = authorization.split(' ', 1)[1].strip()
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
    except Exception:
        raise HTTPException(status_code=401, detail='Invalid or expired Firebase token')
    if not decoded_token.get('uid'):
        raise HTTPException(status_code=401, detail='Invalid Firebase user')
    token = str(uuid.uuid4())
    expire = int(time.time()) + 60
    message = (token + str(expire)).encode('utf-8')
    signature = hmac.new(private_key.encode('utf-8'), message, hashlib.sha1).hexdigest()
    return {'token': token, 'expire': expire, 'signature': signature}


def _imagekit(method: str, endpoint: str):
    key = os.getenv('IMAGEKIT_PRIVATE_KEY', '').strip()
    if not key:
        raise RuntimeError('IMAGEKIT_PRIVATE_KEY is missing')
    auth = base64.b64encode((key + ':').encode()).decode()
    req = request.Request(
        'https://api.imagekit.io/v1' + endpoint,
        headers={'Authorization': 'Basic ' + auth, 'Accept': 'application/json'},
        method=method,
    )
    try:
        with request.urlopen(req, timeout=25) as response:
            body = response.read()
            return json.loads(body) if body else None
    except error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:300]
        raise RuntimeError(f'ImageKit HTTP {exc.code}: {detail}') from exc


def _delete_listing_images(owner_id: str, listing_id: str):
    # ImageKit folder created by the Flutter upload code.
    folder = f'/hadbai_pes_market/{owner_id}/{listing_id}'
    deleted = 0
    # Five images max for new listings, but page for older listings too.
    for _ in range(20):
        query = parse.urlencode({'path': folder, 'limit': 100, 'skip': 0})
        files = _imagekit('GET', '/files?' + query)
        if not isinstance(files, list):
            raise RuntimeError('Unexpected ImageKit file list response')
        # Never delete a file outside this listing's own folder.
        matching = [f for f in files if isinstance(f, dict)
                    and str(f.get('filePath', '')).startswith(folder + '/')]
        if not matching:
            return deleted
        for file in matching:
            file_id = file.get('fileId')
            if not isinstance(file_id, str) or not file_id:
                raise RuntimeError('ImageKit file has no fileId')
            _imagekit('DELETE', '/files/' + parse.quote(file_id, safe=''))
            deleted += 1
    raise RuntimeError('Too many files; cleanup requires manual review')


@app.post('/maintenance/cleanup-sold-images')
def cleanup_sold_images(x_cleanup_secret: str | None = Header(default=None)):
    expected = os.getenv('CLEANUP_SECRET', '').strip()
    if not expected:
        raise HTTPException(status_code=503, detail='CLEANUP_SECRET is not configured')
    if not x_cleanup_secret or not hmac.compare_digest(x_cleanup_secret, expected):
        raise HTTPException(status_code=403, detail='Forbidden')
    if not FIREBASE_READY:
        raise HTTPException(status_code=503, detail='Firebase is not initialized')
    if not os.getenv('IMAGEKIT_PRIVATE_KEY', '').strip():
        raise HTTPException(status_code=503, detail='ImageKit private key is missing')

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    db = firestore.client()
    checked = 0
    cleaned = 0
    deleted_files = 0
    failures = []
    # Query by soldAt, then verify isSold and status locally; avoids composite index.
    query = db.collection('listings').where('soldAt', '<=', cutoff).order_by('soldAt')
    last_doc = None
    for _ in range(10):  # At most 1000 records per scheduled run.
        page_query = query.limit(100)
        if last_doc is not None:
            page_query = page_query.start_after(last_doc)
        page_docs = list(page_query.stream())
        if not page_docs:
            break
        for doc in page_docs:
            checked += 1
            data = doc.to_dict() or {}
            if data.get('isSold') is not True or data.get('imagesDeletedAt'):
                continue
            owner_id = data.get('ownerId')
            if not isinstance(owner_id, str) or not owner_id:
                failures.append({'listingId': doc.id, 'error': 'Missing ownerId'})
                continue
            try:
                count = _delete_listing_images(owner_id, doc.id)
                # Preserve sale record and other metadata; remove stale image URLs.
                doc.reference.update({
                    'images': [],
                    'mainPhotoIndex': 0,
                    'imagesDeletedAt': firestore.SERVER_TIMESTAMP,
                })
                cleaned += 1
                deleted_files += count
            except Exception as exc:
                failures.append({'listingId': doc.id, 'error': str(exc)[:180]})
        last_doc = page_docs[-1]
        if len(page_docs) < 100:
            break
    return {'checked': checked, 'cleaned': cleaned, 'deletedFiles': deleted_files, 'failures': failures}
