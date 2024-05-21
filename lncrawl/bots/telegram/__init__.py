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

available_formats = [
    "epub",
    "text",
    "web",
    "mobi",
    "pdf",
]

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
        "- Time of upload will depend on the number of chapters available.\n"
        "- Some popular supported sites: http://novelfull.com/, http://novelhall.com/, https://boxnovel.com/ and many more.\n"
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
            # remove output path
            # shutil.rmtree(app.output_path, ignore_errors=True)

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
- Time of upload will depend on the number of chapters available.
- Some popular supported sites: http://novelfull.com/, http://novelhall.com/, https://boxnovel.com/ and many more''')

        await update.message.reply_text(
            "Please send the profile page URL of the light novel you want to download, "
            "or send /cancel to stop."
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

            if app.user_input.startswith("http://") or app.user_input.startswith("https://"):
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
            else:
                await update.message.reply_text(
                    "Please enter a valid profile page URL or send /cancel to stop."
                )
                return "handle_novel_url"

    async def handle_select_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        selected = context.user_data.get("selected_source", [])
        selected.append(int(update.message.text.strip()) - 1)
        context.user_data["selected_source"] = selected
        if len(selected) < len(app.crawler_list):
            await update.message.reply_text("Got it! Please select more")
            return await self.get_novel_info(update, context)
        else:
            app.crawler = app.crawler_list[selected[0]]
            return await self.get_novel_info(update, context)

    async def get_novel_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        crawler = prepare_crawler(app.crawler)
        app.get_novel_info(crawler)
        context.user_data["crawler"] = crawler
        context.user_data["novel_title"] = crawler.novel_title
        await update.message.reply_text(
            "Novel title: %s\n\n%s" % (crawler.novel_title, crawler.synopsis)
        )
        await update.message.reply_text(
            "Enter the download range:\n"
            "/all - for all chapters\n"
            "/last - for last 10 chapters\n"
            "/first - for first 10 chapters\n"
            "/volume - for specific volumes\n"
            "/chapter - for specific chapters\n"
            "/cancel - to stop"
        )
        return "handle_range_selection"

    async def display_range_selection_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Enter the download range:\n"
            "/all - for all chapters\n"
            "/last - for last 10 chapters\n"
            "/first - for first 10 chapters\n"
            "/volume - for specific volumes\n"
            "/chapter - for specific chapters\n"
            "/cancel - to stop"
        )
        return "handle_range_selection"

    async def handle_range_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.start_download(update, context, "all")

    async def handle_range_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.start_download(update, context, "last")

    async def handle_range_first(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.start_download(update, context, "first")

    async def handle_range_volume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Enter volume numbers separated by comma.")
        return "handle_volume_selection"

    async def handle_range_chapter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Enter chapter numbers separated by comma.")
        return "handle_chapter_selection"

    async def handle_volume_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        volumes = [int(x.strip()) for x in update.message.text.split(",")]
        return await self.start_download(update, context, "volume", volumes)

    async def handle_chapter_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chapters = [int(x.strip()) for x in update.message.text.split(",")]
        return await self.start_download(update, context, "chapter", chapters)

    async def start_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, range_type, values=None):
        app = context.user_data.get("app")
        app.get_chapters(context.user_data["crawler"], range_type, values)
        context.user_data["status"] = "started"
        context.job_queue.run_repeating(self.download_status, 2, context=context, name=str(update.message.chat_id), data={"app": app})
        return "handle_downloader"

    async def download_status(self, context: ContextTypes.DEFAULT_TYPE):
        app = context.job.data["app"]
        app.download_chapters()
        context.user_data["status"] = app.status
        if app.status == "downloaded":
            await self.handle_delete_cache(context.job.data["update"], context)
            context.job.schedule_removal()
            return ConversationHandler.END

    async def handle_delete_cache(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        context.user_data["status"] = "deleting cache"
        app.delete_cache()
        context.user_data["status"] = "deleted cache"
        context.user_data["app"] = app
        await update.message.reply_text(
            "Done!\n"
            + "Title: %s\n"
            + "Total: %d\n"
            + "Downloaded: %d\n"
            + "Undownloaded: %d\n"
            + "Failures: %d\n"
            % (
                app.novel_title,
                len(app.chapters),
                app.progress,
                app.total - app.progress,
                len(app.failures),
            )
        )
        await self.select_output_format(update, context)

    async def select_output_format(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        app = context.user_data.get("app")
        context.user_data["status"] = "done"
        reply_keyboard = [available_formats]
        await update.message.reply_text(
            "Please select output format:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
        return "handle_output_format"

    async def handle_output_format(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        format = update.message.text.strip().lower()
        if format not in available_formats:
            await update.message.reply_text(
                "Please select a valid format.", reply_markup=ReplyKeyboardMarkup(available_formats, one_time_keyboard=True)
            )
            return "handle_output_format"

        app = context.user_data.get("app")
        app.pack(format)
        await update.message.reply_text("Converting...")
        file_path = app.pack(format)

        await update.message.reply_text("Uploading...")
        download_link = upload(file_path)

        await update.message.reply_text(
            "All done!\n"
            + "Title: %s\n"
            + "Total: %d\n"
            + "Downloaded: %d\n"
            + "Undownloaded: %d\n"
            + "Failures: %d\n"
            + "Download: %s\n"
            % (
                app.novel_title,
                len(app.chapters),
                app.progress,
                app.total - app.progress,
                len(app.failures),
                download_link,
            )
        )
        await self.destroy_app(update, context)

    async def handle_downloader(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Sorry, I did not understand that command.\nSend /help to see the available commands."
        )
