import os
import re
import shutil
import logging
from pathlib import Path
from urllib.parse import urlparse
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          ConversationHandler, Job, MessageHandler, filters)


from lncrawl.core.app import App
from lncrawl.core.sources import prepare_crawler
from lncrawl.utils.uploader import upload
import traceback

logger = logging.getLogger(__name__)

# Custom JSON formatter
class CustomJsonFormatter(logging.Formatter):
    def format(self, record):
        record_dict = {
            'levelname': record.levelname,
            'asctime': self.formatTime(record),
            'message': record.getMessage(),
            'module': record.module,
            'lineno': record.lineno,
            'funcName': record.funcName
        }
        return record_dict

formatter = CustomJsonFormatter()

# Set the formatter to the logger
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)
logger.setLevel(logging.INFO)

available_formats = ["epub"]

# Your existing code continues here...
async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Add the welcome message here
    welcome_message = (
        "📚 Welcome to Night Novel Book Downloader bot! 🌙\n"
        "Join our channel [WebsNovel](https://t.me/websnovel) for more such awesome reads!\n"
        "\n"
        "LINK 🔗 :- [WebsNovel](https://t.me/websnovel)\n"
        "\n"
        "👉 How to use:\n"
        "- Upload your url and our bot will send the epub file.\n"
        "- Time of upload will be depend on no. of chapters available in \n"
        "- Some popular supported sites http://novelfull.com/ ,http://novelhall.com/ , https://boxnovel.com/ and many more\n"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown', disable_web_page_preview=True)


class TelegramBot:
    def start(self):
        os.environ["debug_mode"] = "yes"

        # Build the Application and with bot's token.
        TOKEN = os.getenv("TELEGRAM_TOKEN", "")
        self.application = Application.builder().token(TOKEN).build()

        # Add a command helper for help
        self.application.add_handler(CommandHandler("help", self.show_help))

        # Add conversation handler with states
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", self.init_app),
                MessageHandler(
                    filters.TEXT & ~(filters.COMMAND), self.handle_novel_url
                ),
            ],
            fallbacks=[
                CommandHandler("cancel", self.destroy_app),
            ],
            states={
                "handle_novel_url": [
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_novel_url
                    ),
                ],
                "handle_crawler_to_search": [
                    CommandHandler(
                        "skip", self.handle_crawler_to_search
                    ),
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_crawler_to_search
                    ),
                ],
                "handle_select_novel": [
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_select_novel
                    ),
                ],
                "handle_select_source": [
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_select_source
                    ),
                ],
                "handle_delete_cache": [
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_delete_cache
                    ),
                ],
                "handle_range_selection": [
                    CommandHandler("all", self.handle_range_all),
                    CommandHandler("last", self.handle_range_last),
                    CommandHandler(
                        "first", self.handle_range_first
                    ),
                    CommandHandler(
                        "volume", self.handle_range_volume
                    ),
                    CommandHandler(
                        "chapter", self.handle_range_chapter
                    ),
                    MessageHandler(filters.TEXT & ~(filters.COMMAND), self.display_range_selection_help),
                ],
                "handle_volume_selection": [
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_volume_selection
                    ),
                ],
                "handle_chapter_selection": [
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_chapter_selection
                    ),
                ],
                "handle_pack_by_volume": [
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_pack_by_volume
                    ),
                ],
                "handle_output_format": [
                    MessageHandler(
                        filters.TEXT & ~(filters.COMMAND), self.handle_output_format
                    ),
                ],
            },
        )
        self.application.add_handler(conv_handler)

        # Fallback helper
        self.application.add_handler(
            MessageHandler(filters.TEXT, self.handle_downloader)
        )

        # Log all errors
        self.application.add_error_handler(self.error_handler)

        print("Telegram bot is online!")

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        # Start the Bot
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log Errors caused by Updates."""
        error_str = "".join(traceback.format_exception(etype=type(context.error), value=context.error, tb=context.error.__traceback__))
        logger.warning("Error: %s\nCaused by: %s", error_str, update)


    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Send /start to create new session.\n")
        return ConversationHandler.END

    def get_current_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None):
        if update:
            name = str(update.effective_message.chat_id)
        else:
            name = chat_id
        current_jobs = context.job_queue.get_jobs_by_name(name)
        return current_jobs

    async def destroy_app(self, update: Update, context: ContextTypes.DEFAULT_TYPE, job: Job = None):
        if update:
            chat_id = str(update.effective_message.chat_id)
        else:
            chat_id = job.chat_id

        for job in self.get_current_jobs(update, context, chat_id):
            job.schedule_removal()

        if job or context.user_data.get("app"):
            app = job.data.pop("app", None) or context.user_data.pop("app")
            app.destroy()

        await context.bot.send_message(chat_id, text="Session closed", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END


        await context.bot.send_message(chat_id, text="Session closed", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    async def init_app(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get("app"):
            await self.destroy_app(update, context)

        app = App()
        app.initialize()
        context.user_data["app"] = app
        await update.message.reply_text('''📚 Welcome to Night Novel Book Downloader bot! 🌙
Join our channel [WebsNovel](https://t.me/websnovel) for more such awesome reads!

LINK 🔗 :- https://t.me/websnovel

👉 How to use:
- Upload your url and our bot will send the epub file.
- Time of upload will be depend on no. of chapters available in 
- Some popular supported sites http://novelfull.com/ ,http://novelhall.com/ , https://boxnovel.com/ and many more''')

        await update.message.reply_text(
            "I recognize input of these two categories:\n"
            "- Profile page url of a lightnovel.\n"
            "- A query to search your lightnovel.\n"
            "Enter whatever you want or send /cancel to stop."
        )
        return "handle_novel_url"

    async def handle_novel_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.get_current_jobs(update, context):
            app = context.user_data.get("app")
            await update.message.reply_text(
                "%s\n"
                "%d out of %d chapters has been downloaded.\n"
                "To terminate this session send /cancel."
                % (context.user_data.get("status"), app.progress, len(app.chapters))
            )
        else:
            if context.user_data.get("app"):
                app = context.user_data.get("app")
            else:
                app = App()
                app.initialize()
                context.user_data["app"] = app

            app.user_input = update.message.text.strip()

            try:
                app.prepare_search()
            except Exception:
                await update.message.reply_text(
                    "Sorry! I only recognize these sources:\n"
                    + "https://github.com/dipu-bd/lightnovel-crawler#supported-sources"
                )
                await update.message.reply_text(
                    "Enter something again or send /cancel to stop."
                )
                await update.message.reply_text(
                    "You can send the novelupdates link of the novel too.",
                )
                return "handle_novel_url"

            if app.crawler:
                await update.message.reply_text("Got your page link")
                return await self.get_novel_info(update, context)

            if len(app.user_input) < 5:
                await update.message.reply_text(
                    "Please enter a longer query text (at least 5 letters)."
                )
                return "handle_novel_url"

            try:
                prepare_crawler(app)
            except Exception:
                await update.message.reply_text(
                    "Error! Please read the instructions again."
                )
                await update.message.reply_text(
                    "Enter something again or send /cancel to stop."
                )
                return "handle_novel_url"

            results = app.search_novel(app.user_input)
            context.user_data["results"] = results

            if len(results) == 0:
                await update.message.reply_text("No novel found")
                await update.message.reply_text(
                    "Enter something again or send /cancel to stop."
                )
                return "handle_novel_url"

            await update.message.reply_text(
                "I found these novels:\n"
                + "\n".join(
                    ["(%d) %s" % (i + 1, v["title"]) for i, v in enumerate(results)]
                )
            )
            await update.message.reply_text("Enter the novel no or send /skip to skip.")
            return "handle_crawler_to_search"

    async def handle_crawler_to_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        results = context.user_data["results"]
        app = context.user_data["app"]

        try:
            text = update.message.text.strip()
            if text:
                app.user_input = int(text) - 1
            if not 0 <= app.user_input < len(results):
                raise IndexError
        except (ValueError, IndexError):
            await update.message.reply_text("Enter the correct novel no")
            return "handle_crawler_to_search"

        await update.message.reply_text("Selected: %s" % results[app.user_input]["title"])

        app.crawler = app.get_crawler(results[app.user_input])
        return await self.get_novel_info(update, context)

    async def get_novel_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]
        app.get_novel_info()

        context.user_data["range"] = "%d to %d" % (1, app.chapters_count)
        context.user_data["pack_by_volume"] = "yes"
        context.user_data["output_format"] = "epub"

        await update.message.reply_text(
            "Novel: %s\n"
            "Title: %s\n"
            "Author: %s\n"
            "Chapter count: %d\n"
            "Host: %s\n"
            "Type: %s"
            % (
                app.crawler.novel_url,
                app.crawler.novel_title,
                app.crawler.novel_author,
                app.crawler.chapters_count,
                app.crawler.home_url,
                app.crawler.novel_type,
            )
        )

        await update.message.reply_text(
            "Should I remove cache? (yes/no)\n"
            "All previous downloads will be deleted."
        )
        return "handle_delete_cache"

    async def handle_delete_cache(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip().lower()
        app = context.user_data["app"]
        if text in ["yes", "no"]:
            app.pack_by_volume = context.user_data.get("pack_by_volume") == "yes"
            if text == "yes":
                app.chapters = []
                app.packages = []
                app.cache.clear()
            else:
                app.load_chapters()
            await self.show_range(update, context)
            return "handle_range_selection"
        else:
            await update.message.reply_text("Please enter yes or no")
            return "handle_delete_cache"

    async def show_range(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]
        ranges = "1-%d" % app.chapters_count
        await update.message.reply_text(
            "Select chapters range (default is all): %s" % ranges
        )
        await update.message.reply_text(
            "You can enter by the range of chapters\n"
            "like 5-10 or 10-15.\n"
            "You can enter multiple ranges by comma separated\n"
            "like 5-10,15-20\n"
            "Or send /all for all chapters"
        )

    async def display_range_selection_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Select chapters range:\n"
            "e.g. 5-10 or 10-15.\n"
            "Send /all for all chapters"
        )
        return "handle_range_selection"

    async def handle_range_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]
        context.user_data["range"] = "1 to %d" % app.chapters_count
        await update.message.reply_text(
            "Got all chapters (%d to %d)" % (1, app.chapters_count)
        )
        await self.ask_pack_by_volume(update, context)

    async def handle_range_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]
        context.user_data["range"] = "%d to %d" % (
            app.chapters_count - 50,
            app.chapters_count,
        )
        await update.message.reply_text(
            "Got last 50 chapters (%d to %d)"
            % (app.chapters_count - 50, app.chapters_count)
        )
        await self.ask_pack_by_volume(update, context)

    async def handle_range_first(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]
        context.user_data["range"] = "%d to %d" % (1, 50)
        await update.message.reply_text("Got first 50 chapters (1 to 50)")
        await self.ask_pack_by_volume(update, context)

    async def handle_range_volume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]
        volumes = app.crawler.get_volumes()
        await update.message.reply_text(
            "Volumes:\n" + "\n".join([v["title"] for v in volumes])
        )
        await update.message.reply_text("Enter the volume no or send /skip to skip.")
        return "handle_volume_selection"

    async def handle_volume_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]
        volumes = app.crawler.get_volumes()

        try:
            text = update.message.text.strip()
            if text:
                app.user_input = int(text) - 1
            if not 0 <= app.user_input < len(volumes):
                raise IndexError
        except (ValueError, IndexError):
            await update.message.reply_text("Enter the correct volume no")
            return "handle_volume_selection"

        context.user_data["range"] = "Volume %d" % app.user_input
        await update.message.reply_text(
            "Got volume %d\n%s"
            % (app.user_input, volumes[app.user_input]["title"])
        )
        await self.ask_pack_by_volume(update, context)

    async def handle_range_chapter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Enter chapter no or range of chapters (e.g. 5-10 or 10-15)"
        )
        return "handle_chapter_selection"

    async def handle_chapter_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]

        try:
            text = update.message.text.strip()
            if text:
                ranges = [
                    [int(c) for c in r.split("-")]
                    for r in re.split(",|and", text.replace(" ", ""))
                ]
                for r in ranges:
                    if not (1 <= r[0] <= r[1] <= app.chapters_count):
                        raise IndexError
        except (ValueError, IndexError):
            await update.message.reply_text("Enter correct chapter no or range")
            return "handle_chapter_selection"

        context.user_data["range"] = ", ".join(
            ["%d to %d" % (r[0], r[1]) for r in ranges]
        )
        await update.message.reply_text("Got chapters %s" % context.user_data["range"])
        await self.ask_pack_by_volume(update, context)

    async def ask_pack_by_volume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Pack by volume? (yes/no)")
        return "handle_pack_by_volume"

    async def handle_pack_by_volume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip().lower()
        if text in ["yes", "no"]:
            context.user_data["pack_by_volume"] = text
            await self.ask_output_format(update, context)
        else:
            await update.message.reply_text("Please enter yes or no")
            return "handle_pack_by_volume"

    async def ask_output_format(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # available_formats = ["epub", "mobi", "text", "web"]
        keyboard = [[f] for f in available_formats]
        await update.message.reply_text(
            "Choose output format:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
        return "handle_output_format"

    async def handle_output_format(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip().lower()
        if text in available_formats:
            context.user_data["output_format"] = text
            await self.handle_downloader(update, context)
        else:
            await update.message.reply_text("Please select the correct output format")
            return "handle_output_format"

    async def handle_downloader(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data["app"]
        app.range = context.user_data["range"]
        app.output_format = context.user_data["output_format"]
        app.pack_by_volume = context.user_data["pack_by_volume"] == "yes"

        try:
            downloader = app.get_downloader()
            await update.message.reply_text("Starting download...")
            await self.run_downloader(update, context, downloader)
        except Exception as e:
            await update.message.reply_text("Download error: %s" % e)

    async def run_downloader(self, update: Update, context: ContextTypes.DEFAULT_TYPE, downloader):
        for msg in downloader.run():
            await update.message.reply_text(msg)
            await asyncio.sleep(1)

        output_file = downloader.output_file
        if not output_file.exists():
            await update.message.reply_text("Failed to create output file")
        else:
            await update.message.reply_text(
                "Download completed\nFile: %s" % output_file
            )
        await self.done(update, context)

    async def done(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await update.message.reply_text("Done")
        return ConversationHandler.END

    def setup(self):
        return ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                "handle_novel_url": [
                    MessageHandler(Filters.text & ~Filters.command, self.handle_novel_url)
                ],
                "handle_crawler_to_search": [
                    MessageHandler(Filters.text & ~Filters.command, self.handle_crawler_to_search)
                ],
                "handle_delete_cache": [
                    MessageHandler(Filters.text & ~Filters.command, self.handle_delete_cache)
                ],
                "handle_range_selection": [
                    CommandHandler("all", self.handle_range_all),
                    CommandHandler("last", self.handle_range_last),
                    CommandHandler("first", self.handle_range_first),
                    CommandHandler("volume", self.handle_range_volume),
                    CommandHandler("chapter", self.handle_range_chapter),
                    MessageHandler(Filters.text & ~Filters.command, self.display_range_selection_help)
                ],
                "handle_volume_selection": [
                    MessageHandler(Filters.text & ~Filters.command, self.handle_volume_selection)
                ],
                "handle_chapter_selection": [
                    MessageHandler(Filters.text & ~Filters.command, self.handle_chapter_selection)
                ],
                "handle_pack_by_volume": [
                    MessageHandler(Filters.text & ~Filters.command, self.handle_pack_by_volume)
                ],
                "handle_output_format": [
                    MessageHandler(Filters.text & ~Filters.command, self.handle_output_format)
                ],
            },
            fallbacks=[CommandHandler("cancel", self.done)],
        )

if __name__ == "__main__":
    ApplicationBuilder().token("TOKEN").build().add_handler(DownloaderHandler().setup()).run()
