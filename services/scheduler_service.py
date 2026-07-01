from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.timeutil import get_tz

# Pin the scheduler to the configured zone so naive/aware run dates fire at the
# intended wall-clock time regardless of the host's system timezone.
scheduler = AsyncIOScheduler(timezone=get_tz())


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
