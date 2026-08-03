from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
import httpx
import os
import urllib.parse
from pathlib import Path

# Explicitly load .env from the same folder as main.py
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

app = FastAPI(title="Spotify Taste Dashboard API")

# Allow frontend to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

SCOPES = [
    "user-read-private",
    "user-read-email",
    "user-top-read",
    "user-read-recently-played",
    "user-read-currently-playing",
    "user-read-playback-state"
]

@app.get("/")
def root():
    return {"message": "Spotify Taste Dashboard API is running"}

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/login")
def login():
    """Redirect user to Spotify authorization page"""
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "show_dialog": "true"
    }

    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    return RedirectResponse(url)

@app.get("/api/callback")
async def callback(code: str = Query(None), error: str = Query(None)):
    """Exchange authorization code for access token, then send user back to frontend"""
    if error:
        raise HTTPException(status_code=400, detail=f"Spotify error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    token_url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data=data,
            auth=(CLIENT_ID, CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to get token from Spotify")

    token_data = response.json()

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    # Redirect back to the frontend with tokens in the URL
    frontend_url = (
        f"http://127.0.0.1:5173/?"
        f"access_token={access_token}"
        f"&refresh_token={refresh_token}"
        f"&expires_in={expires_in}"
    )

    return RedirectResponse(frontend_url)

@app.get("/api/debug")
def debug():
    return {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI
    }

@app.get("/api/top-artists")
async def get_top_artists(access_token: str = Query(...), time_range: str = "medium_term"):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/me/top/artists?time_range={time_range}&limit=10"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()

@app.get("/api/top-tracks")
async def get_top_tracks(access_token: str = Query(...), time_range: str = "medium_term"):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/me/top/tracks?time_range={time_range}&limit=10"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()

@app.get("/api/recently-played")
async def get_recently_played(access_token: str = Query(...)):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.spotify.com/v1/me/player/recently-played?limit=10"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()

@app.get("/api/currently-playing")
async def get_currently_playing(access_token: str = Query(...)):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.spotify.com/v1/me/player/currently-playing"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code == 204:
        return {"is_playing": False, "message": "Nothing is currently playing"}

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()

@app.get("/api/refresh")
async def refresh_token(refresh_token: str = Query(...)):
    token_url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data=data,
            auth=(CLIENT_ID, CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to refresh token")

    return response.json()