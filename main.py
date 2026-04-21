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

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not all([BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    print("WARNING: Missing environment variables. Make sure BOT_TOKEN, SUPABASE_URL, and SUPABASE_KEY are set in .env")

# Initialize Bot, Dispatcher and Supabase Client
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()
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

    # Generate an 8 character unique code
    code = shortuuid.uuid()[:8]
    user_id = message.from_user.id
    
    # Insert code into supabase database
    try:
        supabase.table("user_sessions").insert({
            "user_id": user_id,
            "unique_code": code,
            "user_ads": False
        }).execute()
    except Exception as e:
        print("Supabase Insert Error:", e)
        await message.answer("Server Error: Unable to generate code right now. Make sure the 'user_sessions' table exists in Supabase.")
        return
        
    # The URL for the Web App (Must be HTTPS for Telegram Web App)
    # WARNING: Localhost (127.0.0.1) won't load inside Telegram WebApp unless you use ngrok/localtunnel to get https://...
    app_url = f"https://your-deployed-domain.com/?code={code}"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Open Ad & Get Reward", web_app=WebAppInfo(url=app_url))]
    ])
    
    await message.answer(
        f"🎁 *Watch the AD and get your Result!*\n\n"
        f"Tap the button below to open the Web App directly inside Telegram 👇",
        parse_mode="Markdown",
        reply_markup=markup
    )

# ==========================================
# WEB SERVER LOGIC (API + FRONTAL APP)
# ==========================================
async def handle_index(request):
    """Serves the frontend web application (index.html)"""
    return web.FileResponse('index.html')

async def handle_ad_completed(request):
    """API Endpoint called by the web app when an ad finishes"""
    if not supabase:
        return web.json_response({"status": "error", "message": "Database not configured"}, status=500)

    try:
        data = await request.json()
        code = data.get("code")
        
        if not code:
            return web.json_response({"status": "error", "message": "Code query parameter missing"}, status=400)
        
        # Verify the code inside database
        res = supabase.table("user_sessions").select("*").eq("unique_code", code).execute()
        
        if len(res.data) > 0:
            session = res.data[0]
            user_id = session['user_id']
            has_watched = session.get('user_ads', False)
            
            if has_watched:
                return web.json_response({"status": "error", "message": "Result already claimed for this code!"}, status=400)

            # Update Supabase database
            supabase.table("user_sessions").update({"user_ads": True}).eq("unique_code", code).execute()
            
            # Send result back via telegram bot dynamically!
            try:
                # Custom result based on instruction: "hello uska naam"
                # Since we don't have the explicit telegram name in db, we just say Hello.
                await bot.send_message(chat_id=user_id, text=f"🎉 Hello! Ad complete ho gaya hai!\n\nHere is your Result: I LOVE YOU MARI JAAN")
            except Exception as e:
                print("Bot Send Error:", e)
                
            return web.json_response({"status": "success", "message": "Reward Sent!"})
        else:
            return web.json_response({"status": "error", "message": "Invalid or expired code"}, status=404)
            
    except Exception as e:
        print("API Error:", e)
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def start_web_server():
    """Initializes and runs the web API"""
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index),
        web.post('/ad-completed', handle_ad_completed)
    ])
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Bind to port 8080 locally
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("🚀 Web server started on http://127.0.0.1:8080")

async def main():
    # Start web server task background
    await start_web_server()
    
    # Start telegram bot polling
    if bot:
        print("🤖 Bot started polling...")
        await dp.start_polling(bot)
    else:
        print("Bot is not running because BOT_TOKEN is missing. However, Web API continues on port 8080.")
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
