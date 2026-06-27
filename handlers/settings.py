from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID
from core.storage import (
    add_replacement, get_replacements, del_replacement,
    add_prefix, get_prefixes, del_prefix
)

@Client.on_message(filters.command("replace") & filters.user(OWNER_ID))
async def handle_replace(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("💡 Usage: `/replace old=new`\nYou can add multiple rules by sending again.")
        return
    
    pairs = message.text.split(None, 1)[1].split(",")
    added = []
    for pair in pairs:
        if "=" in pair:
            old, new = pair.split("=", 1)
            add_replacement(old.strip(), new.strip())
            added.append(f"{old.strip()} ➜ {new.strip()}")
    
    if added:
        await message.reply_text("✅ Added replacement rules:\n" + "\n".join(added))
    else:
        await message.reply_text("❌ Invalid format. Use `old=new`")

@Client.on_message(filters.command("viewreplace") & filters.user(OWNER_ID))
async def handle_viewreplace(client: Client, message: Message):
    replaces = get_replacements()
    if not replaces:
        await message.reply_text("📭 No replacement rules set.")
        return
    
    text = "📝 **Replacement Rules:**\n\n"
    for old, new in replaces.items():
        text += f"• `{old}` ➜ `{new}`\n"
    await message.reply_text(text)

@Client.on_message(filters.command("delreplace") & filters.user(OWNER_ID))
async def handle_delreplace(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("💡 Usage: `/delreplace word` to delete a specific rule.")
        return
    
    word = message.text.split(None, 1)[1].strip()
    if del_replacement(word):
        await message.reply_text(f"✅ Deleted replacement rule for: `{word}`")
    else:
        await message.reply_text(f"❌ Rule not found for: `{word}`")

@Client.on_message(filters.command("setprefix") & filters.user(OWNER_ID))
async def handle_setprefix(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("💡 Usage: `/setprefix FileName:`\nYou can add multiple by sending again.")
        return
    
    prefix = message.text.split(None, 1)[1].strip()
    add_prefix(prefix)
    await message.reply_text(f"✅ Added prefix to remove: `{prefix}`")

@Client.on_message(filters.command("viewprefix") & filters.user(OWNER_ID))
async def handle_viewprefix(client: Client, message: Message):
    prefixes = get_prefixes()
    if not prefixes:
        await message.reply_text("📭 No prefixes set.")
        return
    
    text = "📝 **Prefixes to Remove:**\n\n"
    for p in prefixes:
        text += f"• `{p}`\n"
    await message.reply_text(text)

@Client.on_message(filters.command("delprefix") & filters.user(OWNER_ID))
async def handle_delprefix(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("💡 Usage: `/delprefix FileName:`")
        return
    
    prefix = message.text.split(None, 1)[1].strip()
    if del_prefix(prefix):
        await message.reply_text(f"✅ Deleted prefix: `{prefix}`")
    else:
        await message.reply_text(f"❌ Prefix not found: `{prefix}`")
