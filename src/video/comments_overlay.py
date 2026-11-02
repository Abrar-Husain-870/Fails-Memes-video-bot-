"""
Comments Overlay Module:
Transforms template images from data/assets/Comments into clean, high-resolution,
customized comment cards featuring real top Reddit comments and random usernames.
Chooses comment box size based on comment content (3-4 words or short comments for small, etc.)
and adapts theme (dark for landscape mode, light for portrait/square).
Applies circular, antialiased custom meme profile pictures from Comments/Profile pics.
"""

import os
import random
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

import config
from src.logger import logger
from src.video.overlay import _segment_text, _wrap_text_mixed, _get_text_width


FUNNY_USER_PROFILES = [
    ("Professional Overthinker", "overthinker_9000"),
    ("Lord of the Lag", "packetloss_king"),
    ("Certified Couch Potato", "potato_supreme"),
    ("Emotional Damage", "emotional_dmg_officer"),
    ("WiFi Disconnected", "searching_for_signal"),
    ("Karen's Manager", "talk_to_manager"),
    ("Zero Braincells", "head_empty_af"),
    ("Instant Regret", "ragret_nothing"),
    ("Sarcasm Specialist", "subtle_sarcasm"),
    ("Captain Obvious", "obvious_captain"),
    ("Suspicious Pigeon", "coo_coo_agent"),
    ("Tactical Napper", "tactical_snooze"),
    ("Chief Confusion Officer", "what_just_happened"),
    ("Grandmaster Flop", "flop_era_ceo"),
    ("Gravity Denier", "physics_left_chat"),
    ("Average Monday Victim", "monday_survivor"),
    ("Ctrl+Z Enthusiast", "undo_my_life"),
    ("Serial Snack Connoisseur", "midnight_snacker"),
    ("Quantum Procrastinator", "do_it_tomorrow"),
    ("Speedy Snail", "slow_and_furious"),
    ("Dangerously Clumsy", "drop_everything"),
    ("Sleep Deprived Genius", "3am_thoughts"),
    ("Broccoli Hater", "anti_veggie_gang"),
    ("Uncertified Mechanic", "just_duct_tape_it"),
    ("404 Motivation Missing", "error_404_human"),
    ("Couch Astronaut", "space_cadet_couch"),
    ("Living On Borrowed Time", "deadline_dodger"),
    ("Certified Clown", "honk_honk_circus"),
    ("Low Battery Warning", "running_on_1_percent"),
    ("Professional Googler", "how_to_adult_help")
]


def choose_comment_box_type(comment_text: str) -> str:
    """
    Select comment box size based on comment content length:
    - Short punchy comments (<= 5 words and <= 28 characters) -> 'small' (Small1.png)
    - Medium comments (6 to 14 words or <= 70 characters)     -> 'medium' (Medium1.png or Medium2.png)
    - Longer comments (15+ words or > 70 characters)         -> 'large' (Large1.png)
    """
    words = comment_text.strip().split()
    word_count = len(words)
    char_count = len(comment_text.strip())

    if word_count <= 5 and char_count <= 28:
        return "small"
    elif word_count <= 14 and char_count <= 70:
        return random.choice(["medium1", "medium2"])
    else:
        return "large"


def extract_clean_card(template_path: Path) -> Image.Image:
    """
    Chroma-keys green screen background (#00e600 / #00ff00),
    ignores bottom-right sparkle watermark, crops to exact card bounds,
    and applies a clean rounded rectangle mask to eliminate any green fringe.
    """
    im = Image.open(template_path).convert("RGBA")
    arr = np.array(im)
    r = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    b = arr[:, :, 2].astype(int)

    # Detect green background
    is_green = (g > 130) & (g > r * 1.32) & (g > b * 1.32)
    # Ignore bottom-right 120x120 corner to prevent watermark star expanding bounding box
    is_green[-120:, -120:] = True
    arr[is_green, 3] = 0

    # Suppress green color bleed along borders
    edge_green = (g > 95) & (g > r * 1.12) & (g > b * 1.12) & (arr[:, :, 3] > 0)
    arr[edge_green, 1] = np.minimum(arr[edge_green, 1], np.maximum(arr[edge_green, 0], arr[edge_green, 2]))

    keyed = Image.fromarray(arr)
    bbox = keyed.getbbox()
    if not bbox:
        return keyed

    card = keyed.crop(bbox)
    w, h = card.size

    # Inset by 3px and apply antialiased rounded rectangle mask
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    radius = max(14, min(int(min(w, h) * 0.12), 32))
    d.rounded_rectangle([3, 3, w - 4, h - 4], radius=radius, fill=255)
    card.putalpha(mask)

    return card


def load_and_crop_circular_avatar(image_path: Path, diameter: int) -> Image.Image:
    """
    Loads an avatar image, automatically trims any outer solid border/sticker margins,
    crops to square centered on the subject, resizes with 2x supersampling,
    and applies an antialiased circular mask.
    """
    img = Image.open(image_path).convert("RGBA")
    arr = np.array(img)
    
    # Auto-trim sticker borders if image has white borders
    top_edge = arr[0, :]
    if (top_edge[:, 0] > 245).mean() > 0.7:
        non_white = (arr[:, :, 0] < 240) | (arr[:, :, 1] < 240) | (arr[:, :, 2] < 240)
        y_idx, x_idx = np.where(non_white)
        if len(x_idx) > 0:
            x1, x2 = max(0, x_idx.min() - 1), min(img.width, x_idx.max() + 2)
            y1, y2 = max(0, y_idx.min() - 1), min(img.height, y_idx.max() + 2)
            img = img.crop((x1, y1, x2, y2))

    w, h = img.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    cropped = img.crop((left, top, left + min_dim, top + min_dim))

    # 2x supersampling for high fidelity
    scale_factor = 2
    target_dim = diameter * scale_factor
    resized = cropped.resize((target_dim, target_dim), Image.Resampling.LANCZOS)

    mask = Image.new("L", (target_dim, target_dim), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([0, 0, target_dim - 1, target_dim - 1], fill=255)
    resized.putalpha(mask)

    return resized.resize((diameter, diameter), Image.Resampling.LANCZOS)


def _get_font(bold: bool = False, size: int = 28, is_emoji: bool = False) -> ImageFont.FreeTypeFont:
    """Safely load system font with fallbacks."""
    if is_emoji:
        for fp in ["C:/Windows/Fonts/seguiemj.ttf", "C:/Windows/Fonts/seguisym.ttf"]:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, size=size)
                except Exception:
                    pass
    else:
        for fp in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]:
            if os.path.exists(fp):
                try:
                    if bold:
                        bfp = fp.replace(".ttf", "b.ttf")
                        if os.path.exists(bfp):
                            return ImageFont.truetype(bfp, size=size)
                    return ImageFont.truetype(fp, size=size)
                except Exception:
                    pass
    return ImageFont.load_default()


def _draw_fitted_comment_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_w: int,
    max_h: int,
    initial_font_size: int = 38,
    text_color: tuple = (18, 18, 20, 255),
    line_spacing: int = 6,
    max_lines: int = 3,
    min_font_size: int = 28
) -> int:
    """
    Renders comment text wrapped inside a strictly bounded rectangle (max_w, max_h).
    Dynamically shrinks font size until all lines fit completely without running outside.
    Vertically centers the text block inside max_h so there is never an awkward empty void.
    """
    font_size = initial_font_size
    lines = []
    font_text = None
    font_emoji = None
    line_h = 0

    while font_size >= min_font_size:
        font_text = _get_font(bold=False, size=font_size)
        font_emoji = _get_font(bold=False, size=int(font_size * 0.95), is_emoji=True)
        lines = _wrap_text_mixed(text, font_text, font_emoji, max_w, draw)
        ref_bbox = draw.textbbox((0, 0), "Ag", font=font_text)
        line_h = (ref_bbox[3] - ref_bbox[1]) + line_spacing
        total_h = len(lines) * line_h
        if total_h <= max_h and len(lines) <= max_lines:
            break
        font_size -= 2

    lines = lines[:max_lines]
    total_text_h = len(lines) * line_h

    # Vertically center within max_h
    v_offset = max(0, (max_h - total_text_h) // 2)
    curr_y = y + v_offset

    ref_bbox = draw.textbbox((0, 0), "Bro angle Hg", font=font_text)
    text_mid_y = (ref_bbox[1] + ref_bbox[3]) / 2.0

    for line in lines:
        cur_x = x
        for seg, is_em in _segment_text(line):
            f = font_emoji if is_em else font_text
            bbox = draw.textbbox((0, 0), seg, font=f)
            seg_w = bbox[2] - bbox[0]
            if is_em:
                em_mid_y = (bbox[1] + bbox[3]) / 2.0
                em_y = curr_y + int(round(text_mid_y - em_mid_y))
                draw.text((cur_x, em_y), seg, font=f, embedded_color=True)
            else:
                draw.text((cur_x, curr_y), seg, font=f, fill=text_color)
            cur_x += seg_w + (4 if is_em else 0)
        curr_y += line_h

    return curr_y


def _render_small_template(
    raw_card: Image.Image,
    author_name: str,
    handle: str,
    comment_text: str,
    is_dark: bool,
    target_width: int,
    avatar_path: Optional[Path] = None
) -> Image.Image:
    """
    Renders Small1.png (Instagram compact pill).
    Designed specifically for short punchy 3-5 word comments with large, bold text.
    """
    factor = target_width / 860.0
    scale = target_width / raw_card.width
    target_h = int(round(raw_card.height * scale))
    card = raw_card.resize((target_width, target_h), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(card)

    bg_color = (30, 30, 32, 255) if is_dark else (255, 255, 255, 255)
    text_color = (245, 245, 245, 255) if is_dark else (18, 18, 20, 255)
    author_color = (255, 255, 255, 255) if is_dark else (15, 15, 15, 255)

    clean_handle = f"@{handle}" if not handle.startswith("@") else handle

    # Overlay circular profile picture inside Instagram gradient ring
    if avatar_path and avatar_path.exists():
        try:
            dia = int(round(88 * factor))
            cx = int(round((85 if is_dark else 83) * factor))
            cy = int(round(85 * factor))
            av = load_and_crop_circular_avatar(avatar_path, dia)
            card.alpha_composite(av, (cx - dia // 2, cy - dia // 2))
        except Exception as e:
            logger.warning(f"Failed to composite avatar in Small1: {e}")

    # Mask original text area
    mask_x1 = int(round(158 * factor))
    mask_y1 = int(12 * scale)
    mask_x2 = target_width - int(55 * scale)
    mask_y2 = target_h - int(50 * scale)
    draw.rectangle([mask_x1, mask_y1, mask_x2, mask_y2], fill=bg_color)

    font_author = _get_font(bold=True, size=int(round(30 * factor)))
    draw.text((mask_x1, int(18 * factor)), clean_handle, font=font_author, fill=author_color)

    # Render punchy comment text clearly below handle
    _draw_fitted_comment_text(
        draw, comment_text,
        x=mask_x1,
        y=int(56 * factor),
        max_w=mask_x2 - mask_x1 - 10,
        max_h=int(52 * factor),
        initial_font_size=36,
        text_color=text_color,
        max_lines=1,
        min_font_size=28
    )

    return card


def _render_medium1_template(
    raw_card: Image.Image,
    author_name: str,
    handle: str,
    comment_text: str,
    is_dark: bool,
    target_width: int,
    avatar_path: Optional[Path] = None
) -> Image.Image:
    """
    Renders Medium1.png (Instagram comment card).
    """
    factor = target_width / 860.0
    scale = target_width / raw_card.width
    target_h = int(round(raw_card.height * scale))
    card = raw_card.resize((target_width, target_h), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(card)

    bg_color = (30, 30, 32, 255) if is_dark else (255, 255, 255, 255)
    text_color = (245, 245, 245, 255) if is_dark else (18, 18, 20, 255)
    author_color = (255, 255, 255, 255) if is_dark else (15, 15, 15, 255)
    sub_color = (160, 160, 160, 255) if is_dark else (115, 115, 115, 255)

    clean_handle = f"@{handle}" if not handle.startswith("@") else handle

    # Overlay circular profile picture inside Instagram gradient ring
    if avatar_path and avatar_path.exists():
        try:
            dia = int(round(90 * factor))
            cx = int(round((96 if is_dark else 95) * factor))
            cy = int(round((104 if is_dark else 100) * factor))
            av = load_and_crop_circular_avatar(avatar_path, dia)
            card.alpha_composite(av, (cx - dia // 2, cy - dia // 2))
        except Exception as e:
            logger.warning(f"Failed to composite avatar in Medium1: {e}")

    # Mask original text area
    mask_x1 = int(round(158 * factor))
    mask_y1 = int(20 * scale)
    mask_x2 = target_width - int(75 * scale)
    mask_y2 = target_h - int(60 * scale)
    draw.rectangle([mask_x1, mask_y1, mask_x2, mask_y2], fill=bg_color)

    font_author = _get_font(bold=True, size=int(round(32 * factor)))
    draw.text((mask_x1, int(24 * scale)), clean_handle, font=font_author, fill=author_color)
    time_x = mask_x1 + int(draw.textlength(clean_handle, font=font_author)) + 14
    draw.text((time_x, int(26 * scale)), f"{random.randint(2, 14)}h", font=_get_font(bold=False, size=int(round(24 * factor))), fill=sub_color)

    # Use full available width for large, mobile-friendly font
    max_text_w = mask_x2 - mask_x1 - 10
    max_text_h = mask_y2 - int(66 * scale) - 6
    _draw_fitted_comment_text(
        draw, comment_text,
        x=mask_x1,
        y=int(66 * scale),
        max_w=max_text_w,
        max_h=max_text_h,
        initial_font_size=38,
        text_color=text_color,
        line_spacing=8,
        max_lines=2,
        min_font_size=30
    )

    return card


def _render_medium2_template(
    raw_card: Image.Image,
    author_name: str,
    handle: str,
    comment_text: str,
    is_dark: bool,
    target_width: int,
    avatar_path: Optional[Path] = None
) -> Image.Image:
    """
    Renders Medium2.png (Twitter/X Tweet card).
    """
    factor = target_width / 860.0
    scale = target_width / raw_card.width
    target_h = int(round(raw_card.height * scale))
    card = raw_card.resize((target_width, target_h), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(card)

    bg_color = (25, 25, 27, 255) if is_dark else (255, 255, 255, 255)
    text_color = (245, 245, 245, 255) if is_dark else (18, 18, 20, 255)
    author_color = (255, 255, 255, 255) if is_dark else (15, 15, 15, 255)
    sub_color = (150, 155, 160, 255) if is_dark else (110, 115, 120, 255)

    clean_handle = f"@{handle}" if not handle.startswith("@") else handle

    # Overlay circular profile picture over Twitter placeholder circle
    if avatar_path and avatar_path.exists():
        try:
            dia = int(round(86 * factor))
            cx = int(round((93 if is_dark else 91) * factor))
            cy = int(round((62 if is_dark else 64) * factor))
            av = load_and_crop_circular_avatar(avatar_path, dia)
            card.alpha_composite(av, (cx - dia // 2, cy - dia // 2))
        except Exception as e:
            logger.warning(f"Failed to composite avatar in Medium2: {e}")
    else:
        av_cx, av_cy, av_r = int(round(91 * factor)), int(round(64 * factor)), int(round(44 * factor))
        draw.ellipse([av_cx - av_r, av_cy - av_r, av_cx + av_r, av_cy + av_r], fill=(235, 87, 87, 255))
        initial = (author_name[0] if author_name else "U").upper()
        font_av = _get_font(bold=True, size=int(40 * scale))
        bbox_in = draw.textbbox((0, 0), initial, font=font_av)
        draw.text((av_cx - (bbox_in[2] - bbox_in[0]) // 2, av_cy - (bbox_in[3] - bbox_in[1]) // 2 - 2), initial, font=font_av, fill=(255, 255, 255, 255))

    # Mask header text and comment body
    mask_x1 = int(round(155 * factor))
    mask_y1 = int(18 * scale)
    mask_x2 = target_width - int(115 * scale)
    mask_y2 = target_h - int(72 * scale)
    draw.rectangle([mask_x1, mask_y1, mask_x2, mask_y2], fill=bg_color)

    # Draw Name + Verified badge + @handle
    font_author = _get_font(bold=True, size=int(round(32 * factor)))
    draw.text((mask_x1, int(22 * scale)), author_name, font=font_author, fill=author_color)
    author_w = draw.textlength(author_name, font=font_author)

    badge_x = mask_x1 + int(author_w) + 10
    badge_y = int(28 * scale)
    badge_size = int(round(18 * factor))
    draw.ellipse([badge_x, badge_y, badge_x + badge_size, badge_y + badge_size], fill=(29, 155, 240, 255))
    draw.text((badge_x + 3, badge_y - 2), "✔", font=_get_font(bold=True, size=13), fill=(255, 255, 255, 255))

    handle_x = badge_x + badge_size + 10
    draw.text((handle_x, int(26 * scale)), clean_handle.lower(), font=_get_font(bold=False, size=int(round(24 * factor))), fill=sub_color)

    # Use full available width for large, mobile-friendly font
    max_text_w = mask_x2 - mask_x1 - 10
    max_text_h = mask_y2 - int(66 * scale) - 6
    _draw_fitted_comment_text(
        draw, comment_text,
        x=mask_x1,
        y=int(66 * scale),
        max_w=max_text_w,
        max_h=max_text_h,
        initial_font_size=38,
        text_color=text_color,
        line_spacing=8,
        max_lines=2,
        min_font_size=30
    )

    return card


def _render_large_template(
    raw_card: Image.Image,
    author_name: str,
    handle: str,
    comment_text: str,
    is_dark: bool,
    target_width: int,
    avatar_path: Optional[Path] = None
) -> Image.Image:
    """
    Renders Large1.png (YouTube comment box).
    Fits longer comments (15+ words) with bold, multi-line typography.
    """
    factor = target_width / 860.0
    scale = target_width / raw_card.width
    target_h = int(round(raw_card.height * scale))
    card = raw_card.resize((target_width, target_h), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(card)

    bg_color = (32, 32, 34, 255) if is_dark else (255, 255, 255, 255)
    text_color = (245, 245, 245, 255) if is_dark else (18, 18, 20, 255)
    author_color = (255, 255, 255, 255) if is_dark else (15, 15, 15, 255)
    sub_color = (160, 160, 160, 255) if is_dark else (115, 115, 115, 255)

    # Overlay circular profile picture over YouTube hiker avatar
    if avatar_path and avatar_path.exists():
        try:
            dia = int(round(76 * factor))
            cx = int(round((62 if is_dark else 64) * factor))
            cy = int(round(72 * factor))
            av = load_and_crop_circular_avatar(avatar_path, dia)
            card.alpha_composite(av, (cx - dia // 2, cy - dia // 2))
        except Exception as e:
            logger.warning(f"Failed to composite avatar in Large1: {e}")

    # Mask original author and comment text (leave like / reply action icons unmasked)
    mask_x1 = int(round(120 * factor))
    mask_y1 = int(16 * scale)
    mask_x2 = target_width - int(50 * scale)
    mask_y2 = int(194 * scale)
    draw.rectangle([mask_x1, mask_y1, mask_x2, mask_y2], fill=bg_color)

    font_author = _get_font(bold=True, size=int(round(32 * factor)))
    draw.text((mask_x1, int(24 * scale)), author_name, font=font_author, fill=author_color)
    time_x = mask_x1 + int(draw.textlength(author_name, font=font_author)) + 16
    draw.text((time_x, int(26 * scale)), f"{random.randint(1, 10)} days ago", font=_get_font(bold=False, size=int(round(24 * factor))), fill=sub_color)

    max_text_w = mask_x2 - mask_x1 - 10
    max_text_h = mask_y2 - int(66 * scale) - 6
    _draw_fitted_comment_text(
        draw, comment_text,
        x=mask_x1,
        y=int(66 * scale),
        max_w=max_text_w,
        max_h=max_text_h,
        initial_font_size=38,
        text_color=text_color,
        line_spacing=8,
        max_lines=3,
        min_font_size=30
    )

    return card


def generate_outro_comment_cards(
    comments: List[Dict[str, any]],
    is_landscape: bool = False,
    output_dir: Optional[Path] = None,
    target_width: int = 960,
    max_height_budget: Optional[int] = None
) -> List[Path]:
    """
    Generate customized comment cards for outro pop-up display.
    - Selects Dark theme for landscape videos and Light theme for portrait/vertical videos.
    - Automatically chooses box size based on comment length (small for <=9 words/45 chars, medium/large accordingly).
    - Randomly selects unique, hilarious profile pictures from Comments/Profile pics (circularly cropped).
    - Assigns creative, funny names and matching handles to give every short rich variety.
    - Enforces text boundaries so text never runs outside the box.
    - Scales down card height if max_height_budget is provided so it never obstructs video borders.
    """
    if not comments:
        return []

    out_dir = output_dir or (config.OUTPUT_DIR / "comments")
    out_dir.mkdir(parents=True, exist_ok=True)

    comments_root = getattr(config, "OUTRO_COMMENTS_DIR", config.ROOT / "data" / "assets" / "Comments")
    mode_folder = "Dark mode comments" if is_landscape else "Light mode comments"
    theme_dir = comments_root / mode_folder
    if not theme_dir.exists():
        theme_dir = comments_root

    # Discover profile pictures from Comments/Profile pics (case-insensitive)
    profile_pics = []
    for cand in [comments_root / "Profile pics", comments_root / "Profile Pics", comments_root]:
        if cand.exists():
            for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                profile_pics.extend(list(cand.glob(ext)))
            if profile_pics:
                break
    
    # Shuffle profile pictures and funny profiles to guarantee variety across cards
    random.shuffle(profile_pics)
    available_profiles = list(FUNNY_USER_PROFILES)
    random.shuffle(available_profiles)

    card_paths = []
    card_images = []
    max_c = getattr(config, "OUTRO_COMMENTS_COUNT", 2)

    for idx, c in enumerate(comments[:max_c], start=1):
        # Pick unique funny profile & profile picture for this card
        if available_profiles:
            disp_name, handle = available_profiles.pop()
        else:
            disp_name, handle = random.choice(FUNNY_USER_PROFILES)

        # Allow keeping a specific Reddit author if explicitly provided and not default
        raw_author = c.get("author")
        if raw_author and raw_author not in ["AutoModerator", "None", ""]:
            # If user wants variety, we still provide funny names, or combine
            pass

        avatar_pic = profile_pics[(idx - 1) % len(profile_pics)] if profile_pics else None

        body = c.get("body", "").strip()
        card_type = choose_comment_box_type(body)

        if card_type == "small":
            tpath = theme_dir / "Small1.png"
            render_fn = _render_small_template
        elif card_type == "medium1":
            tpath = theme_dir / "Medium1.png"
            render_fn = _render_medium1_template
        elif card_type == "medium2":
            tpath = theme_dir / "Medium2.png"
            render_fn = _render_medium2_template
        else:
            tpath = theme_dir / "Large1.png"
            render_fn = _render_large_template

        if not tpath.exists():
            matches = list(comments_root.rglob(tpath.name))
            if matches:
                tpath = matches[0]

        if tpath.exists():
            try:
                raw_card = extract_clean_card(tpath)
                card_img = render_fn(
                    raw_card=raw_card,
                    author_name=disp_name,
                    handle=handle,
                    comment_text=body,
                    is_dark=is_landscape,
                    target_width=target_width,
                    avatar_path=avatar_pic
                )
            except Exception as e:
                logger.warning(f"Error rendering template {tpath.name}: {e}")
                card_img = None
        else:
            card_img = None

        if card_img is None:
            card_img = _render_native_comment_card(
                author_name=disp_name,
                handle=handle,
                comment_text=body,
                score=1500,
                target_width=target_width,
                is_dark=is_landscape,
                avatar_path=avatar_pic
            )

        card_images.append(card_img)

    # Check height budget (for landscape clips to strictly preserve video clip borders)
    if max_height_budget and card_images:
        total_h = sum(im.height for im in card_images) + (len(card_images) - 1) * 20
        if total_h > max_height_budget:
            shrink_ratio = max_height_budget / total_h
            shrunk_images = []
            for im in card_images:
                new_w = int(round(im.width * shrink_ratio))
                new_h = int(round(im.height * shrink_ratio))
                shrunk_images.append(im.resize((new_w, new_h), Image.Resampling.LANCZOS))
            card_images = shrunk_images

    # Save final cards
    for idx, card_img in enumerate(card_images, start=1):
        out_path = out_dir / f"comment_card_{idx}.png"
        card_img.save(out_path, "PNG")
        logger.info(f"Generated comment card #{idx} at {out_path} ({card_img.size[0]}x{card_img.size[1]})")
        card_paths.append(out_path)

    return card_paths


def _render_native_comment_card(
    author_name: str,
    handle: str,
    comment_text: str,
    score: int,
    target_width: int,
    is_dark: bool = False,
    avatar_path: Optional[Path] = None
) -> Image.Image:
    """Render a crisp, modern native comment card with authentic styling."""
    font_name = _get_font(bold=True, size=28)
    font_comment = _get_font(bold=False, size=28)
    font_emoji = _get_font(bold=False, size=26, is_emoji=True)

    dummy = Image.new("RGBA", (100, 100))
    d_dummy = ImageDraw.Draw(dummy)
    max_text_w = target_width - 150
    lines = _wrap_text_mixed(comment_text, font_comment, font_emoji, max_text_w, d_dummy)
    if not lines:
        lines = [comment_text]

    line_h = 38
    card_h = 120 + len(lines) * line_h

    base = Image.new("RGBA", (target_width, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)

    card_bg = (32, 32, 34, 255) if is_dark else (255, 255, 255, 255)
    text_color = (245, 245, 245, 255) if is_dark else (18, 18, 20, 255)
    author_color = (255, 255, 255, 255) if is_dark else (15, 15, 15, 255)
    sub_color = (160, 160, 160, 255) if is_dark else (115, 115, 115, 255)

    draw.rounded_rectangle([0, 0, target_width - 1, card_h - 1], radius=22, fill=card_bg)

    # Avatar
    av_x = 24
    av_y = 22
    av_size = 50
    if avatar_path and avatar_path.exists():
        try:
            av = load_and_crop_circular_avatar(avatar_path, av_size)
            base.alpha_composite(av, (av_x, av_y))
        except Exception:
            pass
    else:
        colors = [(235, 87, 87), (47, 128, 237), (39, 174, 96), (155, 81, 224), (242, 153, 74)]
        draw.ellipse([av_x, av_y, av_x + av_size, av_y + av_size], fill=random.choice(colors))
        initial = (author_name[0] if author_name else "U").upper()
        font_av = _get_font(bold=True, size=24)
        bbox_in = draw.textbbox((0, 0), initial, font=font_av)
        draw.text(
            (av_x + (av_size - (bbox_in[2] - bbox_in[0])) // 2, av_y + (av_size - (bbox_in[3] - bbox_in[1])) // 2 - 2),
            initial, font=font_av, fill=(255, 255, 255, 255)
        )

    name_x = av_x + av_size + 16
    name_y = 22
    clean_handle = f"@{handle}" if not handle.startswith("@") else handle
    display_header = f"{author_name}  {clean_handle}"
    draw.text((name_x, name_y), display_header, font=font_name, fill=author_color)

    _draw_fitted_comment_text(
        draw, comment_text,
        x=name_x,
        y=name_y + 36,
        max_w=max_text_w,
        max_h=card_h - (name_y + 36) - 10,
        initial_font_size=28,
        text_color=text_color,
        max_lines=3,
        min_font_size=22
    )

    return base
