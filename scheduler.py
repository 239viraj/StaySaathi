from apscheduler.schedulers.blocking import BlockingScheduler
from app import app, send_subscription_reminders
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app.logger.setLevel(logging.INFO)


scheduler = BlockingScheduler(
    timezone="Asia/Kolkata"
)

# Run once shortly after scheduler startup.
scheduler.add_job(
    send_subscription_reminders,
    trigger="date",
    id="initial_subscription_reminders",
    replace_existing=True
)

# Send subscription reminders every day at 9:00 AM.
scheduler.add_job(
    send_subscription_reminders,
    trigger="cron",
    hour=9,
    minute=0,
    id="daily_subscription_reminders",
    replace_existing=True
)

if __name__ == "__main__":
    try:
        app.logger.info("StaySaathi scheduler started.")
        scheduler.start()

    except (KeyboardInterrupt, SystemExit):
        app.logger.info("StaySaathi scheduler stopped.")
        scheduler.shutdown()