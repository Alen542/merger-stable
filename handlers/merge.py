import re
import uuid
from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID
from core.storage import load_intro, get_thumb
from core.queue_manager import task_queue

# Only match links the downloader can actually parse (id= or /d/ patterns)
GDRIVE_REGEX = r"https?://drive\.google\.com/\S*(?:\bid=|/d/)\S+"

@Client.on_message((filters.video | (filters.text & ~filters.regex(r"^/"))) & filters.user(OWNER_ID))
async def handle_main_video(client: Client, message: Message):
    # Skip videos sent with a command caption (e.g. a video captioned "/setintro").
    # Those are handled by their own command handlers and must NOT enter the merge queue.
    if message.video and message.caption and message.caption.strip().startswith("/"):
        return

    # Check for GDrive link if text
    gdrive_link = None
    if message.text:
        match = re.search(GDRIVE_REGEX, message.text)
        if match:
            gdrive_link = match.group(0)
        else:
            return # Ignore other text

    intro_data = load_intro()

    # intro.json may exist with only a thumb_id — require a real intro file_id
    if not intro_data or "file_id" not in intro_data:
        await message.reply_text(
            "⚠️ Please set an intro first.\n"
            "Send your intro video with the caption `/setintro`, "
            "or reply to it with /setintro."
        )
        return

    # logic fix: capturing thumb_id right now!
    active_thumb = get_thumb()

    # Queue position
    position = task_queue.qsize() + 1
    status_msg = await message.reply_text(f"📥 Added to queue. Position: #{position}\n⏳ Waiting for processing...")
    
    task_id = str(uuid.uuid4())
    
    task = {
        "task_id": task_id,
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "main_video_message": message,
        "gdrive_link": gdrive_link,
        "status_message": status_msg,
        "thumb_id": active_thumb
    }
    
    # Add to queue
    await task_queue.put(task)
