from aiohttp import web
import asyncio

# Inline configuration
class Config:
    WEB_SUPPORT = True  # Set this to True if you want to enable web support

class Bot:
    async def start(self):
        if Config.WEB_SUPPORT:
            app = web.Application(client_max_size=30000000)
            # Define a basic route to test
            async def handle(request):
                return web.Response(text="Server is running")

            app.router.add_get('/', handle)
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", 8080)
            await site.start()
            print("Server started at http://0.0.0.0:8080")

async def main():
    bot = Bot()
    await bot.start()

# Run the bot
asyncio.run(main())
