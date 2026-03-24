import asyncio
import csv
import io
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from database import Base, SessionLocal, engine
from models import Company, Job
from worker import run_scraper

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
    await asyncio.to_thread(run_scraper, job_id, url)


@app.get("/job/{job_id}")
def get_job(job_id: str):

    db = SessionLocal()

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        raise HTTPException(status_code=404, detail="Job not found")

    companies = db.query(Company).filter(Company.job_id == job_id).all()

    db.close()

    return {
        "status": job.status,
        "results": [c.__dict__ for c in companies],
    }


@app.get("/job/{job_id}/results.csv")
def download_job_results_csv(job_id: str):
    db = SessionLocal()

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        raise HTTPException(status_code=404, detail="Job not found")

    companies = db.query(Company).filter(Company.job_id == job_id).all()
    db.close()

    output = io.StringIO()
    fieldnames = [
        "id",
        "job_id",
        "companyName",
        "industry",
        "employeeCountRange",
        "employeeDisplayCount",
        "linkedinCompanyUrl",
        "foundedYear",
        "headquarters",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for company in companies:
        writer.writerow({
            "id": company.id,
            "job_id": company.job_id,
            "companyName": company.companyName,
            "industry": company.industry,
            "employeeCountRange": company.employeeCountRange,
            "employeeDisplayCount": company.employeeDisplayCount,
            "linkedinCompanyUrl": company.linkedinCompanyUrl,
            "foundedYear": company.foundedYear,
            "headquarters": company.headquarters,
        })

    csv_data = output.getvalue()
    output.close()

    headers = {"Content-Disposition": f'attachment; filename="job_{job_id}_results.csv"'}
    return StreamingResponse(iter([csv_data]), media_type="text/csv", headers=headers)
