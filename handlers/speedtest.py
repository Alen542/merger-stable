import asyncio
import speedtest
from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID

def get_speedtest_results():
    """Blocking function to run speedtest (runs in background thread)"""
    st = speedtest.Speedtest()
    st.get_best_server()
    
    # Calculate speeds in Megabits per second (Mbps)
    download_speed = st.download() / 1000 / 1000 
    upload_speed = st.upload() / 1000 / 1000
    ping = st.results.ping
    
    # Convert to MBps (Megabytes per second)
    download_mbps = round(download_speed / 8, 2)
    upload_mbps = round(upload_speed / 8, 2)
    
    return download_mbps, upload_mbps, ping

@Client.on_message(filters.command("speedtest") & filters.user(OWNER_ID))
async def speedtest_cmd(client: Client, message: Message):
    status_msg = await message.reply_text("🔄 **Running Speedtest...**\nTesting server internet speed, please wait a minute (this will not block the bot).")
    
    try:
        # Run the synchronous speedtest logic in a background thread so it doesn't freeze the bot
        download, upload, ping = await asyncio.to_thread(get_speedtest_results)
        
        text = (
            "📊 **Server Speedtest Results:**\n\n"
            f"🔻 **Download Speed:** `{download} MBps`\n"
            f"🔺 **Upload Speed:** `{upload} MBps`\n"
            f"🏓 **Ping:** `{ping} ms`\n\n"
            "💡 *Note: Results are shown in Megabytes per second (MBps).*"
        )
        await status_msg.edit_text(text)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to run speedtest. Error: {str(e)}")