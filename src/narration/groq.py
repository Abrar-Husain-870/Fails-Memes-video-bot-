from typing import Tuple, List

from groq import Groq
import config
from src.logger import logger
from src.narration.base import BaseLLMProvider
from src.narration.helpers import parse_structured_response
from src.narration.prompts import SYSTEM_PROMPT_COMMENTARY, SYSTEM_PROMPT_NATURAL, get_user_prompt
from src.reddit.models import RedditPost


class GroqProvider(BaseLLMProvider):
    """Groq LLM provider for script generation."""

    def __init__(self) -> None:
        self.api_key = config.GROQ_API_KEY
        if not self.api_key:
            logger.warning("GROQ_API_KEY is not configured. GroqProvider may fail.")
        self.client = Groq(api_key=self.api_key) if self.api_key else None

    def generate_narration(
        self, 
        post: RedditPost, 
        mode: str = "commentary", 
        style: str = "chaotic",
        video_duration: float = None
    ) -> dict:
        if not self.client:
            raise ValueError("Groq client not initialized (missing API key)")

        system_prompt = SYSTEM_PROMPT_COMMENTARY if mode == "commentary" else SYSTEM_PROMPT_NATURAL
        
        if video_duration:
            target_words = int(video_duration * 2)
            min_w = max(5, target_words - 3)
            max_w = target_words + 3
            word_instruction = (
                f"- Write a short, natural, conversational reaction/commentary as the narration. "
                f"Your narration MUST be EXACTLY {min_w} to {max_w} words. This is a strict limit because the video playback duration is exactly {video_duration:.1f} seconds, and the speaker speed is ~2 words per second. Keep it within this word range."
            )
            system_prompt = system_prompt.replace(
                "- Write a short, natural, conversational reaction/commentary as the narration (EXACTLY 10 to 15 words. This is a strict limit. It should take 3 to 5 seconds to speak).",
                word_instruction
            )
            
        user_prompt = get_user_prompt(post.subreddit, post.title, post.selftext)

        models_to_try = [config.LLM_MODEL]
        for fallback_m in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)

        last_err = None
        for m in models_to_try:
            logger.info(f"Sending request to Groq model: {m}")
            try:
                completion = self.client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.8,
                    max_tokens=600,
                    timeout=30,
                )
                response = completion.choices[0].message.content
                if not response:
                    raise ValueError("Received empty response from Groq")
                    
                return parse_structured_response(response, default_title=post.title)

            except Exception as e:
                last_err = e
                err_s = str(e).lower()
                if "404" in err_s or "model_not_found" in err_s or "does not exist" in err_s:
                    logger.warning(f"Groq model {m} not found/deprecated. Trying fallback model...")
                    continue
                logger.error(f"Groq API error: {e}")
                raise e

        if last_err:
            raise last_err


SYSTEM_PROMPT_CURATOR = """You are an expert social media meme editor who writes viral, punchy captions for fail & unexpected video shorts (like Twitter/X memes).

Task:
Convert the provided Reddit post title into a snappy, engaging 4 to 12 word caption.

Guidelines:
1. WORD COUNT: Exactly 4 to 12 words. Neither too short nor too long.
2. RELEVANCE: Directly resemble and reflect the funny/unexpected action in the video based on the post context.
3. VAGUE TITLES: If the Reddit title is lazy, vague, or not to the point (e.g. 'An interesting title', 'Title', 'WCGW', 'Wait for it', 'Interesting', 'lol', 'Seen today', 'Wait till the end', 'Hold my beer'), generate a relatable, punchy general title suited for funny unexpected fails (e.g. 'Bro really thought he had it 💀', 'That escalated way too quickly 😭', 'Never let them know your next move 😂', 'Bro doubted physics for a sec 😂').
4. STYLE: Casual, modern creator humor (e.g. 'Bro doubted physics for a sec 😂', 'Muscle memory is crazy 💀', 'Confidence was high, execution was not 😭').
5. EMOJIS: Include 1 relevant emoji (😂, 💀, 😭, 🤦‍♂️, etc.) at the end.
6. FORMAT: Return ONLY the caption on a single line. Do not include quotes, prefixes, or explanations."""


def generate_curator_caption(title: str, subreddit: str = "") -> str:
    """
    Use Groq to convert raw Reddit titles into 4-12 word viral, snappy captions.
    If the title is vague or unhelpful, generates a relevant, punchy general title.
    Falls back gracefully if the API is unreachable.
    """
    api_key = config.GROQ_API_KEY
    if not api_key:
        logger.warning("GROQ_API_KEY not configured. Using sanitized fallback caption.")
        return _fallback_curator_caption(title)

    client = Groq(api_key=api_key)
    models_to_try = [
        config.LLM_MODEL,
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ]
    seen = set()
    deduped_models = []
    for m in models_to_try:
        if m and m not in seen:
            seen.add(m)
            deduped_models.append(m)

    prompt = f"Subreddit: r/{subreddit}\nReddit Title: {title}\nCaption:"
    for m in deduped_models:
        try:
            completion = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_CURATOR},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=60,
                timeout=20
            )
            raw_caption = completion.choices[0].message.content
            if raw_caption:
                cleaned = raw_caption.strip().strip('"\'')
                for prefix in ["Caption:", "Title:", "CAPTION:", "TITLE:"]:
                    if cleaned.startswith(prefix):
                        cleaned = cleaned[len(prefix):].strip().strip('"\'')
                
                words = cleaned.split()
                if 2 <= len(words) <= 15:
                    logger.info(f"✔ Groq generated viral curator caption: '{cleaned}' ({len(words)} words) using model '{m}'")
                    return cleaned
                elif len(words) > 15:
                    cleaned = " ".join(words[:12])
                    logger.info(f"✔ Groq generated curator caption (clamped to 12 words): '{cleaned}'")
                    return cleaned
        except Exception as e:
            logger.warning(f"Groq caption generation failed with model {m}: {e}")
            continue

    return _fallback_curator_caption(title)


def _fallback_curator_caption(title: str) -> str:
    """Safe local fallback for caption generation."""
    clean = title.strip()
    words = clean.split()
    vague_patterns = ["an interesting title", "title", "wcgw", "wait for it", "wait till the end", "lol", "interesting", "seen today"]
    if clean.lower().strip(".,!?:") in vague_patterns or len(words) <= 1:
        return "Bro really thought he had it 💀"
    
    if len(words) > 12:
        return " ".join(words[:12]) + " 💀"
    return clean

