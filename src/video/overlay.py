import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

import config
from src.logger import logger
from src.reddit.models import RedditPost


def _wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit within a maximum width in pixels."""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        line_str = " ".join(current_line)
        # Get width of current line
        bbox = draw.textbbox((0, 0), line_str, font=font)
        w = bbox[2] - bbox[0]
        
        if w > max_width:
            if len(current_line) == 1:
                # Word itself is too long, force split it
                lines.append(line_str)
                current_line = []
            else:
                current_line.pop()
                lines.append(" ".join(current_line))
                current_line = [word]
                
    if current_line:
        lines.append(" ".join(current_line))
        
    return lines


def generate_reddit_card(post: RedditPost) -> Path:
    """
    Generate a beautiful dark mode Reddit post card overlay.
    Returns the path to the saved transparent PNG image.
    """
    output_path = config.OUTPUT_DIR / "reddit_card.png"
    
    # ── Dimensions & Padding ─────────────────────────────────
    card_width = 900
    padding = 40
    
    # Fonts loading with fallbacks
    try:
        # Try loading standard windows / unix sans fonts
        font_title = ImageFont.truetype("arialbd.ttf", 36)
        font_meta = ImageFont.truetype("arial.ttf", 24)
        font_meta_bold = ImageFont.truetype("arialbd.ttf", 24)
    except Exception:
        try:
            font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
            font_meta = ImageFont.truetype("DejaVuSans.ttf", 24)
            font_meta_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
        except Exception:
            # Absolute fallback
            font_title = ImageFont.load_default()
            font_meta = ImageFont.load_default()
            font_meta_bold = ImageFont.load_default()

    # Pre-render wrap to calculate dynamic height
    temp_img = Image.new("RGBA", (card_width, 100))
    temp_draw = ImageDraw.Draw(temp_img)
    
    max_text_width = card_width - (padding * 2)
    wrapped_title = _wrap_text(post.title, temp_draw, font_title, max_text_width)
    
    # Title height estimation
    line_spacing = 8
    title_height = 0
    for line in wrapped_title:
        bbox = temp_draw.textbbox((0, 0), line, font=font_title)
        h = bbox[3] - bbox[1]
        title_height += h + line_spacing
    title_height = max(title_height - line_spacing, 40)
    
    # Header: 60px, Footer: 50px, Padding/Spacing: 100px
    card_height = 60 + title_height + 50 + (padding * 2) + 20
    
    # ── Draw Card ────────────────────────────────────────────
    # Transparent canvas
    canvas = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    # Colors
    bg_color = (26, 26, 27, 240)        # Reddit Dark Mode Background (#1A1A1B, 94% opaque)
    reddit_orange = (255, 69, 0, 255)   # #FF4500
    text_white = (255, 255, 255, 255)   # #FFFFFF
    text_gray = (120, 124, 126, 255)    # #787C7E
    border_gray = (52, 53, 54, 255)     # #343536
    
    # Draw rounded background
    draw.rounded_rectangle(
        [(0, 0), (card_width, card_height)],
        radius=20,
        fill=bg_color,
        outline=border_gray,
        width=2
    )
    
    # 1. Header (Subreddit Badge, Subreddit Name, Author, Timestamp)
    y_cursor = padding
    
    if config.OVERLAY_PROFILE_ICON:
        # Draw circular orange badge placeholder
        badge_radius = 20
        badge_center = (padding + badge_radius, y_cursor + badge_radius)
        draw.ellipse(
            [(badge_center[0] - badge_radius, badge_center[1] - badge_radius),
             (badge_center[0] + badge_radius, badge_center[1] + badge_radius)],
            fill=reddit_orange
        )
        # Draw small 'r/' text on badge
        draw.text(
            (badge_center[0] - 8, badge_center[1] - 12),
            "r",
            font=font_meta_bold,
            fill=text_white
        )
        x_cursor = padding + (badge_radius * 2) + 15
    else:
        x_cursor = padding
        
    # Subreddit Name
    sub_tag = f"r/{post.subreddit}" if config.OVERLAY_SUBREDDIT_TAG else "r/Reddit"
    draw.text((x_cursor, y_cursor + 6), sub_tag, font=font_meta_bold, fill=text_white)
    
    # Get width of subreddit tag to align u/author
    sub_bbox = draw.textbbox((0, 0), sub_tag, font=font_meta_bold)
    sub_w = sub_bbox[2] - sub_bbox[0]
    
    # Author and Meta info
    meta_text = f" • Posted by u/{post.author}"
    draw.text(
        (x_cursor + sub_w + 5, y_cursor + 6),
        meta_text,
        font=font_meta,
        fill=text_gray
    )
    
    y_cursor += 65  # Advance below header
    
    # 2. Post Title
    for line in wrapped_title:
        draw.text((padding, y_cursor), line, font=font_title, fill=text_white)
        # Compute height of line
        bbox = draw.textbbox((0, 0), line, font=font_title)
        h = bbox[3] - bbox[1]
        y_cursor += h + line_spacing
        
    y_cursor += 15  # Spacing before footer
    
    # Draw simple thin separator line
    draw.line(
        [(padding, y_cursor), (card_width - padding, y_cursor)],
        fill=border_gray,
        width=1
    )
    y_cursor += 15
    
    # 3. Footer (Upvotes & Comments counts)
    # Formats count like 1.2k if > 1000
    def format_count(num: int) -> str:
        if num >= 1000:
            return f"{num / 1000:.1f}k"
        return str(num)
        
    stats_text = f"▲ {format_count(post.score)}  |  💬 {format_count(post.num_comments)} Comments"
    draw.text((padding, y_cursor), stats_text, font=font_meta_bold, fill=text_gray)
    
    # Save the card image
    canvas.save(output_path, "PNG")
    logger.info(f"Reddit card overlay generated at {output_path} ({card_width}x{card_height})")
    return output_path


def split_caption_for_landscape(title: str) -> tuple[str, str | None]:
    """
    Intelligently splits a title into (top_text, bottom_text) for landscape videos.
    If the title is short, keeps it as a single punchy top title and returns (top_text, None).
    """
    clean = re.sub(r'\s+', ' ', title).strip()
    words = clean.split()
    
    # If title is short (<= 7 words and <= 38 characters), keep together on top
    if len(words) <= 7 and len(clean) <= 38:
        return clean, None
        
    # Check for strong sentence/clause delimiters: ".", "?", "!", ";", " - ", " | "
    for delim in [". ", "? ", "! ", " - ", " | ", "; "]:
        if delim in clean:
            parts = clean.split(delim, 1)
            p1, p2 = parts[0].strip(), parts[1].strip()
            if delim.strip() in [".", "?", "!"]:
                p1 += delim.strip()
            if len(p1) >= 8 and len(p2) >= 8:
                return p1, p2
                
    # Check for secondary punctuation like commas
    if ", " in clean:
        parts = clean.split(", ", 1)
        p1, p2 = parts[0].strip(), parts[1].strip()
        if len(p1) >= 10 and len(p2) >= 10:
            return p1, p2
            
    # Check for natural conjunction split points near middle
    conjunctions = [" while ", " when ", " but ", " until ", " then ", " and ", " because "]
    mid_idx = len(clean) // 2
    best_conj = None
    best_dist = 999
    for conj in conjunctions:
        idx = clean.lower().find(conj)
        while idx != -1:
            dist = abs(idx - mid_idx)
            if dist < best_dist and idx > 10 and (len(clean) - idx) > 10:
                best_dist = dist
                best_conj = (idx, conj)
            idx = clean.lower().find(conj, idx + len(conj))
            
    if best_conj and best_dist < len(clean) * 0.35:
        idx, conj = best_conj
        p1 = clean[:idx].strip()
        p2 = clean[idx:].strip()
        return p1, p2
        
    # Fallback: split evenly by words
    mid_word = len(words) // 2
    p1 = " ".join(words[:mid_word])
    p2 = " ".join(words[mid_word:])
    return p1, p2


def generate_creator_caption_banner(
    text: str,
    max_width: int = 1000,
    min_width: int = 840,
    font_size: int = 0,
    is_bottom: bool = False,
    is_vertical: bool = False,
    filename: str = "top_caption.png"
) -> Path:
    """
    Generate an impactful, viral creator-style caption banner.
    Dynamically scales font size and container width to eliminate dead blank space.
    """
    output_path = config.OUTPUT_DIR / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    clean_text = re.sub(r'\s+', ' ', text).strip()
    if not clean_text:
        return output_path

    # Determine dynamic font size based on text length and placement
    if font_size <= 0:
        if is_vertical:
            font_size = 42
            min_width = 650
        elif is_bottom:
            font_size = 48 if len(clean_text) <= 35 else 42
            min_width = 780
        else:
            # Top banner for horizontal/square:
            if len(clean_text) <= 26:
                font_size = 56  # Bold, punchy text for short titles
                min_width = 820
            elif len(clean_text) <= 48:
                font_size = 48
                min_width = 800
            else:
                font_size = 42
                min_width = 760

    # Load bold fonts
    font = None
    for font_path in [
        "C:/Windows/Fonts/ariblk.ttf",      # Arial Black (extra bold)
        "C:/Windows/Fonts/arialbd.ttf",     # Arial Bold
        "C:/Windows/Fonts/segoeuib.ttf",    # Segoe UI Bold
        "arialbd.ttf",
        "DejaVuSans-Bold.ttf"
    ]:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Pre-render dummy image for text measurement
    dummy = Image.new("RGBA", (max_width, 100))
    d = ImageDraw.Draw(dummy)
    
    # Calculate wrapped lines
    padding_x = 48
    padding_y = 28
    line_spacing = 14
    max_text_w = max_width - (padding_x * 2)
    lines = _wrap_text(clean_text, d, font, max_text_w)
    if not lines:
        lines = [clean_text]
    full_text = "\n".join(lines)
        
    # Measure whole multiline text block accurately using Pillow's multiline_textbbox
    mb = d.multiline_textbbox((0, 0), full_text, font=font, spacing=line_spacing, align="center")
    text_w = int(mb[2] - mb[0])
    text_h = int(mb[3] - mb[1])
    
    # Proportional banner width to balance and fill upper/lower zones
    banner_w = min(max_width, max(min_width, text_w + (padding_x * 2)))
    banner_h = text_h + (padding_y * 2)
    
    canvas = Image.new("RGBA", (banner_w, banner_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    # Clean, vibrant white card container with rounded corners and subtle crisp border
    bg_color = (255, 255, 255, 255)
    border_color = (212, 215, 222, 255)
    draw.rounded_rectangle(
        [(0, 0), (banner_w - 1, banner_h - 1)],
        radius=24,
        fill=bg_color,
        outline=border_color,
        width=2
    )
    
    # Draw centered text lines with razor-sharp black text (offset by mb[0], mb[1] for exact centering)
    text_x = int((banner_w - text_w) // 2 - mb[0])
    text_y = int((banner_h - text_h) // 2 - mb[1])
    text_color = (12, 12, 16, 255)  # Deep bold black
    
    draw.multiline_text(
        (text_x, text_y),
        full_text,
        font=font,
        fill=text_color,
        align="center",
        spacing=line_spacing
    )
        
    canvas.save(output_path, "PNG")
    logger.info(f"Caption banner '{filename}' generated at {output_path} ({banner_w}x{banner_h}, font_size={font_size})")
    return output_path


# Backward compatibility alias
generate_top_caption_banner = generate_creator_caption_banner


def _parse_color(c: str) -> tuple[int, int, int, int]:
    """Parse hex color like #FB0101 into RGBA tuple."""
    c = c.lstrip("#")
    if len(c) == 6:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)
    elif len(c) == 8:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16))
    return (251, 1, 1, 255)


def _draw_verified_badge(size: int = 40, bg_color: tuple[int, int, int, int] = (251, 1, 1, 255)) -> Image.Image:
    """Renders a supersampled, anti-aliased verified checkmark badge."""
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([(0, 0), (s - 1, s - 1)], fill=bg_color)
    
    # Twitter / X checkmark points
    pts = [
        (s * 0.28, s * 0.52),
        (s * 0.44, s * 0.68),
        (s * 0.74, s * 0.36),
    ]
    check_width = max(int(s * 0.105), 3)
    d.line(pts, fill=(255, 255, 255, 255), width=check_width, joint="curve")
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _create_circular_avatar(img_path: Path | str, size: int = 132) -> Image.Image:
    """Loads and returns a circular-masked avatar with generous inner margin so nothing touches or clips the border."""
    path = Path(img_path)
    if not path.exists():
        assets_p = getattr(config, "ASSETS_DIR", config.ROOT / "data" / "assets")
        alt_paths = [
            assets_p / "Diet Joke.jpg",
            assets_p / "Diet Joke.jpeg",
            assets_p / "Diet Joke.png",
            config.ROOT / "data" / "assets" / "Diet Joke.jpg",
        ]
        for ap in alt_paths:
            if ap.exists():
                path = ap
                break
                
    if path.exists():
        raw = Image.open(path).convert("RGBA")
        import numpy as np
        arr = np.array(raw)
        # Isolate content bounding box (skip outer white background)
        is_content = (arr[:, :, 0] < 240) | (arr[:, :, 1] < 240) | (arr[:, :, 2] < 240)
        ys, xs = np.where(is_content)
        if len(xs) > 0 and len(ys) > 0:
            tight_logo = raw.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        else:
            min_dim = min(raw.size)
            left = (raw.width - min_dim) // 2
            top = (raw.height - min_dim) // 2
            tight_logo = raw.crop((left, top, left + min_dim, top + min_dim))
            
        # Scale logo with generous inner breathing room (74% of circle diameter)
        # to ensure there is plenty of clean padding and no text touches the border
        target_w = int(size * 0.74)
        scale_factor = target_w / tight_logo.width
        target_h = int(tight_logo.height * scale_factor)
        if target_h > int(size * 0.74):
            target_h = int(size * 0.74)
            target_w = int(tight_logo.width * (target_h / tight_logo.height))
            
        tight_logo = tight_logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
    else:
        raw = Image.new("RGBA", (size, size), (240, 242, 245, 255))
        d_raw = ImageDraw.Draw(raw)
        d_raw.text((size // 4, size // 4), "DJ", fill=(251, 1, 1, 255))
        tight_logo = raw
        target_w, target_h = size, size
        
    scale = 4
    canvas_s = size * scale
    circle_img = Image.new("RGBA", (canvas_s, canvas_s), (255, 255, 255, 0))
    d_circ = ImageDraw.Draw(circle_img)
    d_circ.ellipse([(0, 0), (canvas_s - 1, canvas_s - 1)], fill=(255, 255, 255, 255))
    
    logo_s = tight_logo.resize((target_w * scale, target_h * scale), Image.Resampling.LANCZOS)
    pos_x = (canvas_s - logo_s.width) // 2
    pos_y = (canvas_s - logo_s.height) // 2
    circle_img.paste(logo_s, (pos_x, pos_y), logo_s)
    
    d_circ.ellipse([(0, 0), (canvas_s - 1, canvas_s - 1)], outline=(228, 230, 235, 255), width=2 * scale)
    return circle_img.resize((size, size), Image.Resampling.LANCZOS)


def _is_emoji_char(c: str) -> bool:
    """Fast check for emoji codepoint ranges."""
    cp = ord(c)
    return (
        0x1F600 <= cp <= 0x1F64F or
        0x1F300 <= cp <= 0x1F5FF or
        0x1F680 <= cp <= 0x1F6FF or
        0x1F700 <= cp <= 0x1F77F or
        0x1F780 <= cp <= 0x1F7FF or
        0x1F800 <= cp <= 0x1F8FF or
        0x1F900 <= cp <= 0x1F9FF or
        0x1FA00 <= cp <= 0x1FA6F or
        0x1FA70 <= cp <= 0x1FAFF or
        0x2600 <= cp <= 0x26FF or
        0x2700 <= cp <= 0x27BF or
        0xFE00 <= cp <= 0xFE0F or
        0x1F1E6 <= cp <= 0x1F1FF
    )


def _segment_text(text: str) -> list[tuple[str, bool]]:
    """Split text into segments of (text_chunk, is_emoji)."""
    segments = []
    curr = ""
    is_em = None
    for c in text:
        e = _is_emoji_char(c)
        if is_em is None:
            is_em = e
            curr = c
        elif e == is_em:
            curr += c
        else:
            segments.append((curr, is_em))
            curr = c
            is_em = e
    if curr:
        segments.append((curr, is_em))
    return segments


def _get_text_width(text: str, font_text: ImageFont.FreeTypeFont, font_emoji: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw) -> int:
    """Compute total rendered width of text mixing font_text and font_emoji."""
    w = 0
    for seg, is_em in _segment_text(text):
        f = font_emoji if is_em else font_text
        bbox = draw.textbbox((0, 0), seg, font=f)
        w += bbox[2] - bbox[0]
    return w


def _wrap_text_mixed(text: str, font_text: ImageFont.FreeTypeFont, font_emoji: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Word-wrap text accounting for variable emoji glyph widths."""
    words = text.split()
    lines = []
    curr = []
    for w in words:
        curr.append(w)
        line_str = " ".join(curr)
        if _get_text_width(line_str, font_text, font_emoji, draw) > max_width:
            if len(curr) == 1:
                lines.append(line_str)
                curr = []
            else:
                curr.pop()
                lines.append(" ".join(curr))
                curr = [w]
    if curr:
        lines.append(" ".join(curr))
    return lines


def generate_creator_header_card(
    title: str,
    output_filename: str = "creator_header.png",
    display_name: str | None = None,
    handle: str | None = None,
    profile_pic_path: Path | str | None = None
) -> Path:
    """
    Generate an authentic, high-impact Twitter/X style creator card overlay (as in reference 1 & 2).
    Includes circular avatar, display name, red verified tick badge, handle, and bold caption with emoji support.
    """
    output_path = config.OUTPUT_DIR / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    clean_title = re.sub(r'\s+', ' ', title).strip()
    if not clean_title:
        clean_title = "Bro doubted physics for a sec 😂"
        
    name = display_name or getattr(config, "CHANNEL_DISPLAY_NAME", "Diet Joke")
    hnd = handle or getattr(config, "CHANNEL_HANDLE", "@DietJoke")
    pfp_path = profile_pic_path or getattr(config, "PROFILE_PICTURE_PATH", config.ROOT / "data" / "assets" / "Diet Joke.jpg")
    badge_hex = getattr(config, "BADGE_COLOR", "#FB0101")
    badge_color = _parse_color(badge_hex)

    width = 1080
    pad_x = 48
    avatar_size = 132
    badge_size = 40
    
    # Fonts
    font_name = None
    font_caption = None
    for fp in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]:
        try:
            font_name = ImageFont.truetype(fp, 52)
            font_caption = ImageFont.truetype(fp, 54)
            break
        except Exception:
            continue
    if font_name is None:
        font_name = ImageFont.load_default()
        font_caption = ImageFont.load_default()
        
    font_handle = None
    for fp in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "arial.ttf", "DejaVuSans.ttf"]:
        try:
            font_handle = ImageFont.truetype(fp, 40)
            break
        except Exception:
            continue
    if font_handle is None:
        font_handle = ImageFont.load_default()
        
    font_emoji = None
    for fp in ["C:/Windows/Fonts/seguiemj.ttf", "C:/Windows/Fonts/seguisym.ttf"]:
        try:
            font_emoji = ImageFont.truetype(fp, 48)
            break
        except Exception:
            continue
    if font_emoji is None:
        font_emoji = font_caption

    dummy = Image.new("RGBA", (width, 100))
    d_dummy = ImageDraw.Draw(dummy)
    
    max_text_w = width - (pad_x * 2)
    caption_lines = _wrap_text_mixed(clean_title, font_caption, font_emoji, max_text_w, d_dummy)
    if not caption_lines:
        caption_lines = [clean_title]
        
    line_h = 72
    caption_total_h = len(caption_lines) * line_h
    gap_after_avatar = 32
    
    total_h = avatar_size + gap_after_avatar + caption_total_h + 10
    
    card = Image.new("RGBA", (width, total_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(card)
    
    # 1. Circular Avatar
    pfp = _create_circular_avatar(pfp_path, size=avatar_size)
    card.paste(pfp, (pad_x, 0), pfp)
    
    # 2. Display Name
    name_x = pad_x + avatar_size + 24
    name_y = 12
    draw.text((name_x, name_y), name, font=font_name, fill=(15, 20, 25, 255))
    
    # 3. Red Verified Badge (accurately centered vertically with the display name text ink)
    name_bbox = d_dummy.textbbox((0, 0), name, font=font_name)
    name_w = name_bbox[2] - name_bbox[0]
    text_mid_y = name_y + (name_bbox[1] + name_bbox[3]) / 2.0
    badge_y = int(round(text_mid_y - badge_size / 2.0))
    badge_x = name_x + name_w + 14
    badge = _draw_verified_badge(size=badge_size, bg_color=badge_color)
    card.paste(badge, (badge_x, badge_y), badge)
    
    # 4. Handle
    handle_y = name_y + 58
    draw.text((name_x, handle_y), hnd, font=font_handle, fill=(83, 100, 113, 255))
    
    # 5. Caption with mixed emoji support
    caption_y = avatar_size + gap_after_avatar
    for line in caption_lines:
        cur_x = pad_x
        for seg, is_em in _segment_text(line):
            f = font_emoji if is_em else font_caption
            bbox = draw.textbbox((0, 0), seg, font=f)
            seg_w = bbox[2] - bbox[0]
            if is_em:
                draw.text((cur_x, caption_y - 2), seg, font=f, embedded_color=True)
            else:
                draw.text((cur_x, caption_y), seg, font=f, fill=(15, 20, 25, 255))
            cur_x += seg_w + (4 if is_em else 0)
        caption_y += line_h
        
    card.save(output_path, "PNG")
    logger.info(f"Creator header card generated at {output_path} ({width}x{total_h})")
    return output_path

