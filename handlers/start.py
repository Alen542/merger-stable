from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID

@Client.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start_cmd(client: Client, message: Message):
    text = (
        "👋 **Welcome to Video Merger Bot**\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "I automatically attach your intro to any video you send — "
        "with perfect resolution, FPS and codec matching.\n\n"
        "**Quick Start:**\n"
        "1. Send your intro video with caption `/setintro`\n"
        "2. Send any video — I'll merge & upload it\n"
        "3. Send a photo to set a custom thumbnail\n\n"
        "📖 Use /help to see all commands.\n"
        "⚡ Use /speedtest to check server speed."
    )
    await message.reply_text(text)

@Client.on_message(filters.command("help") & filters.user(OWNER_ID))
async def help_cmd(client: Client, message: Message):
    text = (
        "📖 **Help & Commands**\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "🎬 **Intro**\n"
        "• /setintro — Set intro (send video with this caption, or reply to a video)\n"
        "• /viewintro — View current intro\n"
        "• /delintro — Delete current intro\n\n"

        "🖼 **Thumbnail**\n"
        "• Send any photo — Set as upload thumbnail (HD cover included)\n"
        "• /clearthumb — Remove saved thumbnail\n\n"

        "✏️ **Filename Rules**\n"
        "• /replace `old=new` — Replace words in filename\n"
        "• /viewreplace — View replacement rules\n"
        "• /delreplace `word` — Delete a rule\n"
        "• /setprefix `text` — Remove a prefix from filename\n"
        "• /viewprefix — View prefixes\n"
        "• /delprefix `text` — Delete a prefix\n\n"

        "⚙️ **General**\n"
        "• /start — Welcome message\n"
        "• /help — This guide\n"
        "• /speedtest — Check server internet speed\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "💡 **How merging works**\n"
        "Send any video (or a Google Drive link) and the bot will:\n"
        "1. Download it\n"
        "2. Match your intro to it (resolution, FPS, codec)\n"
        "3. Merge losslessly & upload with your thumbnail\n\n"
        "Multiple videos are queued and processed one-by-one.\n\n"

        "🚀 **Features**\n"
        "• Lossless stream-copy merging\n"
        "• Faststart (instant video preview)\n"
        "• SBRips metadata embedded\n"
        "• HD cover thumbnail support"
    )
    await message.reply_text(text)
