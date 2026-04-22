import asyncio
import os
import shortuuid
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not all([BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    print("WARNING: Missing environment variables. Make sure BOT_TOKEN, SUPABASE_URL, and SUPABASE_KEY are set in .env")

# Initialize Bot, Dispatcher and Supabase Client
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp  = Dispatcher()
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
except Exception as e:
    print("Supabase Init Error:", e)
    supabase = None

# ==========================================
# TELEGRAM BOT LOGIC
# ==========================================
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.web_app_info import WebAppInfo

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    if not supabase:
        await message.answer("Developer Configuration Error: Supabase is not connected.")
        return

    # Generate a unique 8-character one-time code
    code    = shortuuid.uuid()[:8]
    user_id = message.from_user.id

    # Insert fresh code into supabase (each /start creates a brand new code)
    try:
        supabase.table("user_sessions").insert({
            "user_id":     user_id,
            "unique_code": code,
            "user_ads":    False          # False = not yet watched
        }).execute()
    except Exception as e:
        print("Supabase Insert Error:", e)
        await message.answer("Server Error: Unable to generate code right now. Make sure the 'user_sessions' table exists in Supabase.")
        return

    # Build the Web App URL
    domain  = os.getenv("WEB_DOMAIN", "https://telegram-bot-watcher-tvrm.onrender.com")
    app_url = f"{domain}/?code={code}"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Watch Ad & Get Reward", web_app=WebAppInfo(url=app_url))]
    ])

    await message.answer(
        "🎁 *Watch the AD and get your Result!*\n\n"
        "Tap the button below to open the Web App directly inside Telegram 👇",
        parse_mode="Markdown",
        reply_markup=markup
    )

# ==========================================
# WEB SERVER LOGIC (API + FRONTEND)
# ==========================================

async def handle_index(request):
    """Serves the frontend web application (index.html)"""
    return web.FileResponse('index.html')

async def handle_ad_completed(request):
    """
    API endpoint called by the web app when an ad finishes.
    ONE-TIME USE: code is DELETED from DB after reward is sent.
    """
    if not supabase:
        return web.json_response({"status": "error", "message": "Database not configured"}, status=500)

    try:
        data = await request.json()
        code = data.get("code")

        if not code:
            return web.json_response({"status": "error", "message": "Code parameter missing"}, status=400)

        # Look up the code in the database
        res = supabase.table("user_sessions").select("*").eq("unique_code", code).execute()

        if not res.data:
            # Code not found — already used and deleted, or never existed
            return web.json_response(
                {"status": "already_used", "message": "This code has already been used or is invalid."},
                status=400
            )

        session      = res.data[0]
        user_id      = session["user_id"]
        has_watched  = session.get("user_ads", False)

        if has_watched:
            # Extra safety check (should be rare after deletion)
            return web.json_response(
                {"status": "already_used", "message": "Reward already claimed for this code!"},
                status=400
            )

        # ── Send reward via Telegram ──────────────────────────────
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "🎉 *Reward Unlocked!*\n\n"
                    "✅ Ad watch complete ho gaya!\n\n"
                    "🔓 *Your Result:* `I LOVE YOU MARI JAAN`\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "⚡ Powered by BIBX Bot"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print("Bot Send Error:", e)
            # Still proceed to delete code even if message fails

        # ── ONE-TIME USE: Delete code from DB ────────────────────
        try:
            supabase.table("user_sessions").delete().eq("unique_code", code).execute()
        except Exception as e:
            print("Supabase Delete Error:", e)

        return web.json_response({"status": "success", "message": "Reward Sent!"})

    except Exception as e:
        print("API Error:", e)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def start_web_server():
    """Initializes and runs the web API"""
    app = web.Application()
    app.add_routes([
        web.get('/',              handle_index),
        web.post('/ad-completed', handle_ad_completed),
    ])

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🚀 Web server started on port {port}")


async def main():
    await start_web_server()

    if bot:
        print("🤖 Bot started polling...")
        await dp.start_polling(bot)
    else:
        print("Bot is not running because BOT_TOKEN is missing. Web API continues on port 8080.")
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
