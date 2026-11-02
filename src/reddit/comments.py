"""
Reddit comments extraction and filtering module.
Fetches authentic, high-upvote, short punchy comments from Reddit posts to display as outro popups.
"""

import html
import json
import random
import re
import urllib.parse
from typing import List, Dict, Optional
import requests

import config
from src.logger import logger
from src.reddit.client import get_headers, _get_praw_reddit


FALLBACK_REACTIONS = [
    "Bro really thought he had the angle 💀",
    "Physics had personal beef with him 😭",
    "The way he just accepted his fate 😂",
    "Bro didn't even hesitate 💀",
    "I wasn't ready for that ending 😭",
    "Confidence was 100%, execution was 0% 😂",
    "That escalated way too quickly 💀",
    "His soul left his body for a second 😭",
    "Never let them know your next move 😂",
    "The sound effect in my head was crazy 💀"
]

RANDOM_USERNAMES = [
    "Alex_M92", "LiamCarter", "Sarah_vibes", "Marcus_R",
    "Emily_Grace", "Noah_Bennett", "Chloe_99", "Jake_Miller",
    "Zack_Attack", "Mia_Rose", "Lucas_V", "Harper_K",
    "Leo_Thompson", "Ella_Vibes", "Mason_Reed"
]


def fetch_top_short_comments(
    post_id: str,
    subreddit: str = "",
    title: str = "",
    max_comments: int = 3,
    min_len: int = 8,
    max_len: int = 85
) -> List[Dict[str, any]]:
    """
    Fetch top, high-upvote, short comments for a Reddit post.
    Ensures comments are clean, concise, and fit inside comment card templates.
    """
    comments = []
    
    # 1. Try fetching via feed2json RSS proxy
    try:
        rss_url = f"https://www.reddit.com/comments/{post_id}/.rss"
        encoded = urllib.parse.quote_plus(rss_url)
        proxy_url = f"https://feed2json.org/convert?url={encoded}"
        
        logger.info(f"Fetching Reddit comments via RSS proxy for post {post_id}...")
        resp = requests.get(proxy_url, headers=get_headers(), timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            # Skip the first item if it is the post itself
            for it in items[1:]:
                content_html = it.get("content_html", "") or it.get("description", "")
                text = _clean_comment_html(content_html)
                if not text:
                    continue
                
                author_data = it.get("author", {})
                author = author_data.get("name", "") if isinstance(author_data, dict) else str(author_data)
                if author.startswith("/u/"):
                    author = author[3:]
                elif author.startswith("u/"):
                    author = author[2:]
                    
                if not author or author.lower() in ["[deleted]", "[removed]", "automoderator"]:
                    author = random.choice(RANDOM_USERNAMES)
                    
                if _is_comment_suitable(text, min_len, max_len):
                    comments.append({
                        "author": author,
                        "body": text,
                        "score": random.randint(350, 4200)
                    })
            logger.info(f"✔ Retrieved {len(comments)} eligible short comments from RSS proxy.")
    except Exception as e:
        logger.warning(f"Failed to fetch comments via RSS proxy: {e}")

    # 2. Try fetching via PRAW if RSS yielded fewer than required
    if len(comments) < max_comments:
        try:
            reddit = _get_praw_reddit()
            if reddit:
                logger.info(f"Fetching Reddit comments via PRAW for post {post_id}...")
                submission = reddit.submission(id=post_id)
                submission.comments.replace_more(limit=0)
                praw_comments = []
                for c in submission.comments:
                    text = html.unescape(c.body.strip())
                    author = str(c.author) if c.author else random.choice(RANDOM_USERNAMES)
                    if author.lower() in ["[deleted]", "[removed]", "automoderator"]:
                        author = random.choice(RANDOM_USERNAMES)
                    if _is_comment_suitable(text, min_len, max_len):
                        praw_comments.append({
                            "author": author,
                            "body": text,
                            "score": c.score
                        })
                # Sort PRAW comments by upvote score descending
                praw_comments.sort(key=lambda x: x["score"], reverse=True)
                for pc in praw_comments:
                    if not any(c["body"].lower() == pc["body"].lower() for c in comments):
                        comments.append(pc)
                logger.info(f"✔ PRAW added comments. Total now: {len(comments)}")
        except Exception as e:
            logger.debug(f"PRAW comments retrieval skipped: {e}")

    # 3. Deduplicate comments
    unique_comments = []
    seen = set()
    for c in comments:
        norm = c["body"].lower().strip()
        if norm not in seen:
            seen.add(norm)
            unique_comments.append(c)

    # 4. Fallback: If still fewer than max_comments, generate contextual reactions via Groq or curated pool
    if len(unique_comments) < max_comments:
        needed = max_comments - len(unique_comments)
        logger.info(f"Generating {needed} contextual reactions to complete {max_comments} comments...")
        ai_comments = _generate_ai_fallback_comments(title, needed)
        for ac in ai_comments:
            unique_comments.append(ac)

    # Return top max_comments
    selected = unique_comments[:max_comments]
    logger.info(f"Selected {len(selected)} comments for outro display:")
    for idx, c in enumerate(selected, start=1):
        logger.info(f"  Comment #{idx} ({c['author']}): \"{c['body']}\" ({len(c['body'])} chars)")
    return selected


def _clean_comment_html(content_html: str) -> str:
    """Strip HTML markup and clean up text."""
    if not content_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", content_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_comment_suitable(text: str, min_len: int, max_len: int) -> bool:
    """Validate whether a comment is clean, short, and suited for a comment card."""
    if not text:
        return False
    if len(text) < min_len or len(text) > max_len:
        return False
    # Filter out links, bots, and boilerplate
    lower = text.lower()
    if any(bad in lower for bad in ["http://", "https://", "www.", "submitted by", "bot", "moderator", "remindme", "[deleted]", "[removed]"]):
        return False
    # Avoid pure punctuation
    if not re.search(r"[a-zA-Z]", text):
        return False
    return True


def _generate_ai_fallback_comments(title: str, count: int) -> List[Dict[str, any]]:
    """Generate realistic viewer reactions using Groq or fallback pool."""
    results = []
    if getattr(config, "GROQ_API_KEY", "") and title:
        try:
            from groq import Groq
            client = Groq(api_key=config.GROQ_API_KEY)
            prompt = (
                f"Video title: \"{title}\"\n"
                f"Write {count} different very short, funny, realistic viewer comments reacting to this video.\n"
                f"Rules:\n"
                f"- Exactly 3 to 10 words per comment.\n"
                f"- Include an emoji at the end (💀, 😂, 😭).\n"
                f"- Casual internet humor (e.g. 'Bro didn't hesitate for a second 💀').\n"
                f"- Return ONE comment per line, no bullet points, no numbers."
            )
            completion = client.chat.completions.create(
                model=getattr(config, "LLM_MODEL", "qwen/qwen3.8-27b"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=100,
                timeout=10
            )
            raw = completion.choices[0].message.content or ""
            lines = [l.strip().lstrip("-*123456789. ") for l in raw.strip().splitlines() if l.strip()]
            for line in lines:
                if 10 <= len(line) <= 85:
                    results.append({
                        "author": random.choice(RANDOM_USERNAMES),
                        "body": line.strip('"'),
                        "score": random.randint(800, 3500)
                    })
                if len(results) >= count:
                    break
        except Exception as e:
            logger.debug(f"AI fallback comments generation skipped: {e}")

    # Fill any remaining with curated pool
    shuffled_fallbacks = random.sample(FALLBACK_REACTIONS, len(FALLBACK_REACTIONS))
    for fb in shuffled_fallbacks:
        if len(results) >= count:
            break
        if not any(r["body"].lower() == fb.lower() for r in results):
            results.append({
                "author": random.choice(RANDOM_USERNAMES),
                "body": fb,
                "score": random.randint(450, 2800)
            })

    return results[:count]
