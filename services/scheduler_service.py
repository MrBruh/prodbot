from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(jobstores={"default": SQLAlchemyJobStore(url="sqlite:///jobs.db")})


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
