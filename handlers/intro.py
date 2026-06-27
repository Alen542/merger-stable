from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID
from core.storage import save_intro, load_intro, delete_intro, save_thumb, delete_thumb

@Client.on_message(filters.command("setintro") & filters.user(OWNER_ID))
async def set_intro_cmd(client: Client, message: Message):
    video_msg = message.reply_to_message if message.reply_to_message else message
    
    if not video_msg.video:
        await message.reply_text("⚠️ Please reply to a video with /setintro or send a video with /setintro as caption.")
        return

    file_id = video_msg.video.file_id
    # file_name attribute can exist but be None — `or` covers both cases
    file_name = getattr(video_msg.video, "file_name", None) or "Intro.mp4"
    
    save_intro(file_id, file_name)
    await message.reply_text(f"✅ Intro set successfully: `{file_name}`\n\n(Note: Physically not downloaded yet. Will be fetched during merge.)")

@Client.on_message(filters.command("viewintro") & filters.user(OWNER_ID))
async def view_intro_cmd(client: Client, message: Message):
    intro_data = load_intro()
    # intro.json may exist with only a thumb_id — require a real intro file_id
    if not intro_data or "file_id" not in intro_data:
        await message.reply_text("❌ No intro is set. Use /setintro to add one.")
        return
    
    await message.reply_video(
        video=intro_data["file_id"],
        caption=f"🎬 **Current Intro:** `{intro_data.get('file_name', 'Intro.mp4')}`"
    )

@Client.on_message(filters.command("delintro") & filters.user(OWNER_ID))
async def del_intro_cmd(client: Client, message: Message):
    if delete_intro():
        await message.reply_text("✅ Intro deleted.")
    else:
        await message.reply_text("❌ No intro to delete.")

@Client.on_message(filters.photo & filters.user(OWNER_ID))
async def set_thumbnail(client: Client, message: Message):
    # Photos captioned with a command are handled by their own handlers
    if message.caption and message.caption.strip().startswith("/"):
        return
    file_id = message.photo.file_id
    save_thumb(file_id)
    await message.reply_text(
        "🖼️ **Thumbnail Saved!**\n"
        "This thumbnail will now be applied to all upcoming videos.\n"
        "Use /clearthumb to remove it."
    )

@Client.on_message(filters.command("clearthumb") & filters.user(OWNER_ID))
async def clear_thumbnail(client: Client, message: Message):
    if delete_thumb():
        await message.reply_text("✅ **Thumbnail cleared!** Default/Auto-generated thumbnail will be used now.")
    else:
        await message.reply_text("❌ No custom thumbnail found to clear.")
