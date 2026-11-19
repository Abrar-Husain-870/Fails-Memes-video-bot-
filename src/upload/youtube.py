import datetime
import json
import random
import time
from pathlib import Path
from typing import List, Dict, Optional

import config
from src.logger import logger

HASHTAGS_POOL = [
    "#Shorts", "#Reddit", "#RedditMemes", "#Viral", "#Fyp", "#Trending",
    "#Comedy", "#Funny", "#Memes", "#Relatable", "#Lol", "#Humor", 
    "#CatMemes", "#Jokes", "#Wholesome"
]

YOUTUBE_API_TIMEOUT = 120


def load_upload_history() -> List[Dict]:
    """Load the upload history database."""
    if config.UPLOAD_HISTORY_FILE.exists():
        try:
            with open(config.UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read upload history: {e}. Starting fresh.")
    return []


def save_upload_record(video_id: str, title: str, status: str = "success") -> None:
    """Save an upload record to the history database."""
    history = load_upload_history()
    history.append({
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "video_id": video_id,
        "title": title,
        "status": status
    })
    try:
        config.UPLOAD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(config.UPLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        logger.info(f"Saved upload record to history: {video_id}")
    except Exception as e:
        logger.error(f"Failed to write upload record: {e}")


def count_uploads_last_24h() -> int:
    """Count successful uploads in the last 24 hours."""
    history = load_upload_history()
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=24)
    
    count = 0
    for record in history:
        if record.get("status") == "success":
            try:
                timestamp = datetime.datetime.fromisoformat(record["timestamp"])
                if timestamp > cutoff:
                    count += 1
            except Exception:
                continue
    return count


def can_upload_now() -> bool:
    """Check if we are within the limit of max uploads per day."""
    uploads_today = count_uploads_last_24h()
    logger.info(f"Uploads in last 24 hours: {uploads_today} (Limit: {config.MAX_VIDEOS_PER_DAY})")
    return uploads_today < config.MAX_VIDEOS_PER_DAY


def _pick_hashtags(n: int = 5) -> str:
    """Pick n random hashtags."""
    return " ".join(random.sample(HASHTAGS_POOL, min(n, len(HASHTAGS_POOL))))


def _get_authenticated_service():
    """Build YouTube API client. Reuses existing token caching and env refresh token logic."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    creds = None
    token_file = config.CACHE_DIR / "yt_token.json"

    # Load cached token if present
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as e:
            logger.warning(f"Could not load cached token: {e}")
            creds = None

    # Fallback to refresh token in env
    if (not creds or not creds.valid) and config.YT_REFRESH_TOKEN:
        logger.info("Authenticating using YT_REFRESH_TOKEN env variable...")
        creds = Credentials(
            token=None,
            refresh_token=config.YT_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=config.YT_CLIENT_ID,
            client_secret=config.YT_CLIENT_SECRET,
            scopes=SCOPES,
        )

    # Refresh expired credentials
    if creds and not creds.valid:
        try:
            creds.refresh(Request())
            logger.info("YouTube OAuth credentials refreshed successfully.")
        except Exception as e:
            logger.error(f"YouTube credentials refresh failed: {e}")
            creds = None

    if not creds or not creds.valid:
        logger.error("Could not authenticate with YouTube. Check YT_REFRESH_TOKEN configuration.")
        return None

    # Cache refreshed credentials
    try:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    except Exception as e:
        logger.warning(f"Could not cache token: {e}")

    return build("youtube", "v3", credentials=creds)


def upload_short(
    video_path: Path,
    title: str,
    description: str = "",
    tags: List[str] = None,
    category_id: str = "22",
    privacy: str = "public",
    retries: int = 3
) -> str:
    """
    Upload video to YouTube Shorts with automatic chunked retries and rate limiting.
    
    Returns:
        YouTube video ID on success, empty string on failure.
    """
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    if not video_path.exists():
        logger.error(f"Upload failed: Video not found at {video_path}")
        return ""
        
    if not can_upload_now():
        logger.error(f"Upload aborted: Daily upload limit reached ({config.MAX_VIDEOS_PER_DAY}/day)")
        return ""

    desc = description.strip()

    logger.info(f"Uploading short: {video_path.name}")
    logger.info(f"   Title: {title}")
    logger.info(f"   Privacy: {privacy}")

    # Loop to retry overall upload if HTTP client drops connection
    for attempt in range(1, retries + 1):
        youtube = _get_authenticated_service()
        if not youtube:
            logger.error("YouTube authentication failed.")
            return ""

        body = {
            "snippet": {
                "title": title[:100],
                "description": desc,
                "tags": tags if tags else ["Reddit", "Shorts", "RedditStories", "AskReddit", "Satisfying"],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(str(video_path), chunksize=4 * 1024 * 1024, resumable=True)
        
        try:
            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                import socket
                socket.setdefaulttimeout(YOUTUBE_API_TIMEOUT)
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    logger.info(f"   ⏫ Upload progress: {pct}%")

            video_id = response["id"]
            logger.info(f"✔ YouTube Upload Successful! https://www.youtube.com/shorts/{video_id}")
            save_upload_record(video_id, title, "success")
            return video_id

        except HttpError as e:
            logger.warning(f"YouTube Upload attempt {attempt}/{retries} failed: HTTP Error {e.resp.status}")
            if attempt == retries:
                logger.error("All upload attempts failed.")
                save_upload_record("", title, "failed")
                return ""
            time.sleep(5 * attempt)
            
        except Exception as e:
            logger.warning(f"YouTube Upload attempt {attempt}/{retries} failed with error: {e}")
            if attempt == retries:
                logger.error("All upload attempts failed.")
                save_upload_record("", title, "failed")
                return ""
            time.sleep(5 * attempt)
            
    return ""
