from aiohttp import web
import asyncio

class Config:
    WEB_SUPPORT = True  # Ensure this is True to enable the web server

class Bot:
    async def start(self):
        if Config.WEB_SUPPORT:
            app = web.Application(client_max_size=30000000)
            async def handle(request):
                return web.Response(text="Server is running")
            app.router.add_get('/', handle)
            
            runner = web.AppRunner(app)
            await runner.setup()
            # Render may use port 10000 or another specified port
            site = web.TCPSite(runner, "0.0.0.0", 10000)  
            await site.start()
            print("Server started at http://0.0.0.0:10000")

async def main():
    bot = Bot()
    await bot.start()

asyncio.run(main())
