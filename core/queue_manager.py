import asyncio
import os
import shutil
import time
import re
import logging
import aiohttp
from pyrogram import Client
from pyrogram.types import Message
from core.storage import (
    load_intro, get_thumb, get_replacements, get_prefixes
)
from core.ffmpeg_utils import merge_videos, get_video_properties

logger = logging.getLogger(__name__)

# Global Queue
task_queue = asyncio.Queue()

# Per-message last progress-edit timestamps (FloodWait protection)
_last_edit_times: dict[int, float] = {}
PROGRESS_EDIT_INTERVAL = 4.0  # seconds between progress edits

def humanbytes(size):
    if not size:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

def time_formatter(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = (
        ((str(days) + "d, ") if days else "")
        + ((str(hours) + "h, ") if hours else "")
        + ((str(minutes) + "m, ") if minutes else "")
        + ((str(seconds) + "s, ") if seconds else "")
    )
    return tmp[:-2] if tmp.endswith(", ") else tmp

def apply_naming_rules(caption: str) -> str:
    if not caption:
        return ""
    
    # 1. Remove Prefixes
    prefixes = get_prefixes()
    for p in prefixes:
        if caption.startswith(p):
            caption = caption[len(p):].strip()
    
    # 2. Apply Replacements
    replaces = get_replacements()
    for old, new in replaces.items():
        caption = caption.replace(old, new)
    
    return caption

def sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in filenames, including
    newlines and other control characters."""
    if not name:
        return ""
    # Strip path separators, reserved chars, and ALL control chars (incl. \n \r \t)
    cleaned = re.sub(r'[\\/*?:"<>|\x00-\x1f\x7f]', "", name)
    # Collapse repeated whitespace left behind
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

async def safe_edit(status_msg: Message, text: str):
    """Edit a status message without ever raising (msg deleted, FloodWait,
    MESSAGE_NOT_MODIFIED etc. must never kill the worker)."""
    try:
        await status_msg.edit_text(text)
    except Exception as e:
        logger.warning(f"safe_edit failed: {e}")

async def download_gdrive(url: str, dest: str, status_msg: Message, start_time: float):
    """Dynamic form-based GDrive downloader. Returns (destination_path, original_filename)."""
    file_id = ""
    if "id=" in url:
        file_id = url.split("id=")[1].split("&")[0]
    elif "d/" in url:
        file_id = url.split("d/")[1].split("/")[0]
    elif "uc?" in url and "id=" in url:
        file_id = url.split("id=")[1].split("&")[0]
    
    if not file_id:
        raise Exception("Invalid GDrive URL format.")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive"
    }

    async with aiohttp.ClientSession(headers=headers, cookie_jar=aiohttp.CookieJar()) as session:
        # Step 1: Request the initial download link
        base_url = "https://drive.google.com/uc?export=download"
        first_url = f"{base_url}&id={file_id}"
        
        async with session.get(first_url) as response:
            if "text/html" not in response.headers.get("Content-Type", "").lower():
                filename = _get_filename_from_headers(response.headers) or "merged_video.mp4"
                await _save_file(response, dest, status_msg, start_time)
                return dest, filename
            
            html = await response.text()
            
            # Extract filename from HTML if possible (it's in the uc-name-size span)
            filename_match = re.search(r'<span class="uc-name-size"><a [^>]*>([^<]+)</a>', html)
            real_filename = filename_match.group(1) if filename_match else "merged_video.mp4"
            
            # Step 2: Dynamically parse the "Download anyway" form
            # Extract the Action URL
            action_match = re.search(r'<form.*?action="([^"]+)"', html)
            if action_match:
                action_url = action_match.group(1)
                if action_url.startswith("/"):
                    action_url = "https://drive.google.com" + action_url
                
                # Extract all hidden inputs: <input type="hidden" name="xxx" value="yyy">
                params = {}
                input_matches = re.finditer(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html)
                for m in input_matches:
                    params[m.group(1)] = m.group(2)
                
                if params:
                    # Step 3: Final request with all parsed parameters and cookies
                    async with session.get(action_url, params=params) as final_response:
                        await _save_file(final_response, dest, status_msg, start_time)
                        return dest, real_filename
            
            # Fallback patterns if form parsing fails
            confirm_token = None
            match = re.search(r'confirm=([a-zA-Z0-9_]+)', html)
            if match:
                confirm_token = match.group(1)
                final_url = f"{base_url}&id={file_id}&confirm={confirm_token}"
                async with session.get(final_url) as final_response:
                    await _save_file(final_response, dest, status_msg, start_time)
                    return dest, real_filename

            if "Google Drive - Quota exceeded" in html:
                raise Exception("GDrive Quota exceeded. This file is temporarily unavailable.")
            if "Access denied" in html or "Sign in" in html:
                raise Exception("GDrive Access Denied. Check link permissions.")
            
            raise Exception("Could not find the 'Download anyway' form in Google's response.")

def _get_filename_from_headers(headers):
    cd = headers.get("Content-Disposition")
    if not cd:
        return None
    match = re.search(r'filename="([^"]+)"', cd)
    if match:
        return match.group(1)
    return None

async def _save_file(response, dest, status_msg, start_time):
    if response.status != 200:
        raise Exception(f"Download failed with status {response.status}")
    
    content_type = response.headers.get("Content-Type", "").lower()
    # Log content type for debugging if it fails
    if "text/html" in content_type:
        # Check if the HTML is small (likely an error) or large (unexpected)
        text_preview = (await response.text())[:500]
        if "Google Drive - Quota exceeded" in text_preview:
            raise Exception("GDrive Quota exceeded for this file. Try again later or use another link.")
        if "Access denied" in text_preview or "Sign in" in text_preview:
            raise Exception("GDrive Access Denied. Make sure the link is 'Anyone with the link' can view.")
        
        # If it's still HTML and we reached here, it's the virus scan page that we failed to bypass
        raise Exception("GDrive is still showing the 'Virus Scan' or 'Large File' warning. Token extraction failed.")

    total_size = int(response.headers.get("Content-Length", 0))
    current_size = 0
    f = await asyncio.to_thread(open, dest, "wb")
    try:
        async for chunk in response.content.iter_chunked(1024 * 1024):
            if chunk:
                # Write in a thread so slow disk I/O never blocks the event loop
                await asyncio.to_thread(f.write, chunk)
                current_size += len(chunk)
                if total_size > 0:
                    await progress_callback(current_size, total_size, status_msg, "⏳ Downloading...", start_time)
    finally:
        await asyncio.to_thread(f.close)
    
    if os.path.getsize(dest) < 10 * 1024: # Reduced to 10KB to be safe
        raise Exception("Downloaded file is too small. GDrive might be blocking the request.")
        
    return True

async def progress_callback(current, total, status_msg: Message, text: str, start_time: float):
    now = time.time()
    diff = now - start_time
    if diff <= 0:
        diff = 0.01

    is_final = total > 0 and current >= total
    msg_key = status_msg.id

    # Time-based throttle: edit at most once every PROGRESS_EDIT_INTERVAL seconds
    last = _last_edit_times.get(msg_key, 0.0)
    if not is_final and (now - last) < PROGRESS_EDIT_INTERVAL:
        return
    _last_edit_times[msg_key] = now

    # Prevent division by zero if total is 0
    total_val = total if total > 0 else current
    percentage = current * 100 / (total_val if total_val > 0 else 1)
    speed = current / diff
    eta = round((total - current) / speed) if (speed > 0 and total > 0) else 0

    # Visual Bar
    bar_length = 10
    filled_length = int(bar_length * current // (total_val if total_val > 0 else 1))
    bar = "█" * filled_length + "░" * (bar_length - filled_length)

    progress_str = (
        f"**{text}**\n\n"
        f"┌ {bar} {percentage:.1f}%\n"
        f"├ **Size:** {humanbytes(current)} / {humanbytes(total) if total > 0 else 'Unknown'}\n"
        f"├ **Speed:** {humanbytes(speed)}/s\n"
        f"└ **ETA:** {time_formatter(eta) if eta > 0 else '0s'}"
    )

    try:
        await status_msg.edit_text(progress_str)
    except Exception:
        pass

async def _process_task(client: Client, task: dict):
    """Process a single merge task. Raises on failure; caller handles errors."""
    task_id = task["task_id"]
    main_msg: Message = task["main_video_message"]
    gdrive_link = task.get("gdrive_link")
    status_msg: Message = task["status_message"]
    thumb_id = task["thumb_id"]

    work_dir = os.path.join("downloads", task_id)
    os.makedirs(work_dir, exist_ok=True)

    try:
        intro_data = load_intro()
        # Validate that an intro is actually set (intro.json may exist with only a thumb_id)
        if not intro_data or "file_id" not in intro_data:
            await safe_edit(status_msg, "❌ Error: Intro video not found. Set one with /setintro first.")
            return

        # 1. Download Intro
        start_time = time.time()
        intro_path = await client.download_media(
            intro_data["file_id"],
            file_name=os.path.join(work_dir, "intro.mp4"),
            progress=progress_callback,
            progress_args=(status_msg, "⏳ Downloading intro...", start_time)
        )

        if not intro_path or not os.path.exists(intro_path):
            raise Exception("Intro video download failed or file not found.")

        # 2. Download Main Video
        start_time = time.time()
        if gdrive_link:
            main_path = os.path.join(work_dir, "main.mp4")
            _, gdrive_filename = await download_gdrive(gdrive_link, main_path, status_msg, start_time)
            # Use the real filename from GDrive as the original caption
            original_caption = gdrive_filename
        else:
            main_path = await client.download_media(
                main_msg,
                file_name=os.path.join(work_dir, "main.mp4"),
                progress=progress_callback,
                progress_args=(status_msg, "⏳ Downloading main video...", start_time)
            )
            original_caption = main_msg.caption or (main_msg.video.file_name if main_msg.video else None) or "merged_video.mp4"

        if not main_path or not os.path.exists(main_path):
            raise Exception("Main video download failed or file not found.")

        # Process Caption/Filename
        final_caption = apply_naming_rules(original_caption)

        # Sanitize filename (removes invalid chars, newlines and control chars)
        clean_filename = sanitize_filename(final_caption)
        if not clean_filename:
            clean_filename = f"merged_{task_id}"

        if not clean_filename.lower().endswith(".mp4"):
            final_filename = clean_filename + ".mp4"
        else:
            final_filename = clean_filename

        # 3. Download Thumbnail
        thumb_path = None
        if thumb_id:
            try:
                thumb_path = await client.download_media(
                    thumb_id,
                    file_name=os.path.join(work_dir, "thumb.jpg")
                )
            except Exception as te:
                logger.warning(f"Thumb Download Error: {te}")

        # 4. Merge (adds SBRips metadata + moov atom faststart)
        await safe_edit(status_msg, "🔄 Matching intro & Merging videos...")
        output_path = os.path.join(work_dir, final_filename)

        title = os.path.splitext(final_filename)[0]
        await merge_videos(intro_path, main_path, output_path, work_dir, title=title)

        # 5. Properties check
        await safe_edit(status_msg, "⏱️ Finalizing...")
        final_props = await get_video_properties(output_path)
        duration = final_props['duration']
        width = final_props['width']
        height = final_props['height']

        # 6. Upload (thumb = classic thumbnail, cover = HD thumbnail)
        start_time = time.time()
        try:
            await main_msg.reply_video(
                video=output_path,
                caption=final_caption,
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_path,
                cover=thumb_path,
                supports_streaming=True,
                progress=progress_callback,
                progress_args=(status_msg, "📤 Uploading merged video...", start_time)
            )
        except TypeError:
            # Older pyrofork/pyrogram without `cover` support — fall back gracefully
            logger.warning("`cover` param not supported by installed pyrogram fork; uploading without HD cover.")
            await main_msg.reply_video(
                video=output_path,
                caption=final_caption,
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_path,
                supports_streaming=True,
                progress=progress_callback,
                progress_args=(status_msg, "📤 Uploading merged video...", start_time)
            )

        await safe_edit(status_msg, "✅ Done! Video merged successfully.")

    except Exception as e:
        logger.error(f"Task Error: {e}", exc_info=True)
        await safe_edit(status_msg, f"❌ Merge failed. Error: {str(e)[:100]}...")

    finally:
        _last_edit_times.pop(status_msg.id, None)
        shutil.rmtree(work_dir, ignore_errors=True)

async def worker_loop(client: Client):
    if os.path.exists("downloads"):
        shutil.rmtree("downloads", ignore_errors=True)
    os.makedirs("downloads", exist_ok=True)

    while True:
        task = await task_queue.get()
        try:
            await _process_task(client, task)
        except Exception as e:
            # Absolute safety net: the worker loop must NEVER die,
            # otherwise the queue stops processing forever.
            logger.critical(f"Worker loop caught unexpected error: {e}", exc_info=True)
        finally:
            task_queue.task_done()
