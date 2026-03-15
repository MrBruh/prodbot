from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

scheduler = AsyncIOScheduler(
    jobstores={"default": SQLAlchemyJobStore(url="sqlite:///jobs.db")}
)


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
