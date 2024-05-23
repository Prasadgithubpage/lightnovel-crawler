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

available_formats = [
    "epub",
]

# Your existing code continues here...
class TelegramBot:
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

    async def destroy_app(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_message.chat_id) if update else None

        if context.user_data.get("app"):
            app = context.user_data.pop("app")
            app.destroy()

        if chat_id:
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
            "I recognize input of a profile page URL of a light novel."
            "Enter the URL or send /cancel to stop."
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
            logger.info(f"Received novel URL: {app.user_input}")

            try:
                app.prepare_crawler()
            except Exception as e:
                logger.error(f"Error preparing crawler: {e}")
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
                logger.info("Crawler prepared successfully")
                await update.message.reply_text("Got your page link")
                return await self.get_novel_info(update, context)

    async def get_novel_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        logger.info(f"Fetching novel info for URL: {app.crawler.novel_url}")

        await update.message.reply_text(app.crawler.novel_url)

        await update.message.reply_text("Reading novel info...")
        app.get_novel_info()

        if os.path.exists(app.output_path):
            await update.message.reply_text(
                "Local cache found. Do you want to delete it? (yes/no)"
            )
            return "handle_delete_cache"
        else:
            os.makedirs(app.output_path, exist_ok=True)
            return await self.get_range_selection(update, context)

    async def handle_delete_cache(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")

        if "yes" in update.message.text.lower():
            await update.message.reply_text(
                "Got it, I will use local cache",
                reply_markup=ReplyKeyboardRemove(),
            )
            return await self.handle_pack_by_volume(update, context)
        else:
            await update.message.reply_text(
                "Got it, I will not use local cache",
                reply_markup=ReplyKeyboardRemove(),
            )
            shutil.rmtree(app.output_path)
            os.makedirs(app.output_path, exist_ok=True)
            return await self.get_range_selection(update, context)

    async def get_range_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        app.get_chapters()

        message = (
            "Got total %d chapters\n"
            "Send /all to get all chapters\n"
            "Send /last <range> to get last N number of chapters\n"
            "Send /first <range> to get first N number of chapters\n"
            "Send /volume to select by volume\n"
            "Send /chapter to select by chapter range\n"
            % len(app.chapters)
        )
        await update.message.reply_text(message)
        return "handle_range_selection"

    async def display_range_selection_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.get_range_selection(update, context)

    async def handle_range_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        await update.message.reply_text(
            "Got it, I will pack all the chapters", reply_markup=ReplyKeyboardRemove()
        )
        app.pack_by_range("all")
        return await self.handle_output_format(update, context)

    async def handle_range_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        n = re.search(r"\d+", update.message.text)
        if n:
            await update.message.reply_text(
                "Got it, I will pack last %d chapters" % int(n.group()),
                reply_markup=ReplyKeyboardRemove(),
            )
            app.pack_by_range("last:%d" % int(n.group()))
            return await self.handle_output_format(update, context)
        else:
            await update.message.reply_text(
                "Please provide a valid number. Example: /last 20"
            )

    async def handle_range_first(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        n = re.search(r"\d+", update.message.text)
        if n:
            await update.message.reply_text(
                "Got it, I will pack first %d chapters" % int(n.group()),
                reply_markup=ReplyKeyboardRemove(),
            )
            app.pack_by_range("first:%d" % int(n.group()))
            return await self.handle_output_format(update, context)
        else:
            await update.message.reply_text(
                "Please provide a valid number. Example: /first 20"
            )

    async def handle_range_volume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        if not app.chapters_has_volume():
            await update.message.reply_text("Sorry, I did not find volumes in this novel.")
            return await self.get_range_selection(update, context)

        await update.message.reply_text(
            "Got total %d volumes\n"
            "Please send volume numbers in ranges separated by comma.\n"
            "Example: 1,3,5 or 1-3,5,7"
            % app.crawler.volumes[-1]
        )
        return "handle_volume_selection"

    async def handle_volume_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        text = update.message.text.strip()

        try:
            app.pack_by_volume(text)
            return await self.handle_output_format(update, context)
        except Exception as e:
            await update.message.reply_text("Sorry, " + str(e))
            return await self.get_range_selection(update, context)

    async def handle_range_chapter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Please send chapter numbers in ranges separated by comma.\n"
            "Example: 1,3,5 or 1-3,5,7"
        )
        return "handle_chapter_selection"

    async def handle_chapter_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        text = update.message.text.strip()

        try:
            app.pack_by_range(text)
            return await self.handle_output_format(update, context)
        except Exception as e:
            await update.message.reply_text("Sorry, " + str(e))
            return await self.get_range_selection(update, context)

    async def handle_pack_by_volume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        await update.message.reply_text("Packing chapters by volumes")
        app.pack_by_volume(app.crawler.volumes)
        return await self.handle_output_format(update, context)

    async def handle_output_format(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        keyboard = [[fmt.upper()] for fmt in available_formats]
        await update.message.reply_text(
            "Select output format:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
        return "handle_output_format_selection"

    async def handle_output_format_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        output_format = update.message.text.strip().lower()

        if output_format in available_formats:
            app.pack_by_format(output_format)
            await update.message.reply_text("Packing in " + output_format + " format")
            app.create_epub()
            link = upload(app.pack_archive())
            await update.message.reply_text(
                "Here is your file: " + link, reply_markup=ReplyKeyboardRemove()
            )
            return await self.destroy_app(update, context)
        else:
            await update.message.reply_text("Invalid format selected. Please try again.")
            return await self.handle_output_format(update, context)

    async def handle_downloader(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")

        if app:
            await update.message.reply_text("Download in progress. Please wait...")
        else:
            await self.init_app(update, context)


if __name__ == "__main__":
    bot = TelegramBot()
    bot.start()
