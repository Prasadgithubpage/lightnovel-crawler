from aiohttp import web
import subprocess

# Inline configuration
class Config:
    WEB_SUPPORT = True  # Set this to True if you want to enable web support

class Bot:
    async def start(self):
        if Config.WEB_SUPPORT:
            app = web.Application(client_max_size=30000000)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", 8080)
            await site.start()

        # Run the command using subprocess
        subprocess.run(["python", "-m", "lncrawl", "--suppress", "--bot", "telegram"])

# Run the bot
Bot().start()
