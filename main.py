import asyncio
import os
import shortuuid
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web
from dotenv import load_dotenv
from supabase import create_client, Client
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.web_app_info import WebAppInfo

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
except Exception as e:
    print("Supabase Init Error:", e)
    supabase = None


@dp.message(CommandStart())
async def handle_start(message: types.Message):
    if not supabase:
        await message.answer("Error: Supabase not connected.")
        return

    code = shortuuid.uuid()[:8]
    user_id = message.from_user.id

    domain = os.getenv("WEB_DOMAIN", "https://telegram-bot-watcher-tvrm.onrender.com")
    app_url = f"{domain}/?code={code}"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Watch Ad & Get Reward", web_app=WebAppInfo(url=app_url))]
    ])

    # Pehle message bhejo
    sent = await message.answer(
        "🎁 *Watch the AD and get your Result!*\n\n"
        "Tap the button below to open the Web App directly inside Telegram 👇",
        parse_mode="Markdown",
        reply_markup=markup
    )

    # ✅ Sirf EK insert — message_id ke saath
    try:
        supabase.table("user_sessions").insert({
            "user_id": user_id,
            "unique_code": code,
            "user_ads": False,
            "message_id": sent.message_id
        }).execute()
    except Exception as e:
        print("Supabase Insert Error:", e)
        await message.answer("Server Error: Try again.")
        return


async def handle_index(request):
    return web.FileResponse('index.html')


async def handle_ad_completed(request):
    if not supabase:
        return web.json_response({"status": "error", "message": "DB not configured"}, status=500)

    try:
        data = await request.json()
        code = data.get("code")

        if not code:
            return web.json_response({"status": "error", "message": "Code missing"}, status=400)

        # ✅ message_id NULL wali rows filter karo
        res = supabase.table("user_sessions").select("*").eq("unique_code", code).not_.is_("message_id", "null").execute()

        if not res.data:
            return web.json_response({"status": "already_used", "message": "Code already used or invalid."}, status=400)

        session = res.data[0]
        user_id = session["user_id"]
        message_id = session.get("message_id")

        # ✅ Pehle DB se delete karo (one-time use)
        supabase.table("user_sessions").delete().eq("unique_code", code).execute()

        # ✅ Ab message edit karo
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=(
                    "🎉 *Reward Unlocked!*\n\n"
                    "✅ Ad watch complete ho gaya!\n\n"
                    "🔓 *Your Result:* `I LOVE YOU MARI JAAN`\n\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "⚡ Powered by BIBX Bot"
                ),
                parse_mode="Markdown",
                reply_markup=None
            )
        except Exception as e:
            print("Edit Error:", e)
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

        return web.json_response({"status": "success", "message": "Reward Sent!"})

    except Exception as e:
        print("API Error:", e)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def start_web_server():
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index),
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
        print("🤖 Bot started...")
        await dp.start_polling(bot)
    else:
        print("BOT_TOKEN missing.")
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
