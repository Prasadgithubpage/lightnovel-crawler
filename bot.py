from aiohttp import web
import asyncio
import subprocess

# Inline configuration
class Config:
    WEB_SUPPORT = True  # Set this to True if you want to enable web support

class Bot:
    async def start(self):
        if Config.WEB_SUPPORT:
            app = web.Application(client_max_size=30000000)
            async def handle(request):
                return web.Response(text="Server is running")
            app.router.add_get('/', handle)
            
            runner = web.AppRunner(app)
            await runner.setup()
            # Render might use port 10000 or another specified port
            site = web.TCPSite(runner, "0.0.0.0", 8080)  
            await site.start()
            print("Server started at http://0.0.0.0:8080")

        # Run the command in the background
        subprocess.Popen(["python", "-m", "lncrawl", "--suppress", "--bot", "telegram"])

async def main():
    bot = Bot()
    await bot.start()

# Run the bot
asyncio.run(main())
