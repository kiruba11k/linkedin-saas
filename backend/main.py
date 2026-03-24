from fastapi import FastAPI
from database import Base, engine, SessionLocal
from models import Job, Company
from worker import run_scraper
import uuid, asyncio

app = FastAPI()

Base.metadata.create_all(bind=engine)


@app.post("/start-job")
async def start_job(payload: dict):

    job_id = str(uuid.uuid4())

    db = SessionLocal()
    db.add(Job(id=job_id, status="queued"))
    db.commit()
    db.close()

    asyncio.create_task(run_async(job_id, payload["sales_nav_url"]))

    return {"job_id": job_id}


async def run_async(job_id, url):
    run_scraper(job_id, url)


@app.get("/job/{job_id}")
def get_job(job_id: str):

    db = SessionLocal()

    job = db.query(Job).filter(Job.id == job_id).first()
    companies = db.query(Company).filter(Company.job_id == job_id).all()

    db.close()

    return {
        "status": job.status,
        "results": [c.__dict__ for c in companies]
    }
