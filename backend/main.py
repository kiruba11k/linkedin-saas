from fastapi import FastAPI
from database import Base, engine, SessionLocal
from models import Job, Company
from worker import run_scraper
import uuid
from threading import Thread
import csv, io
from fastapi.responses import StreamingResponse

app = FastAPI()
Base.metadata.create_all(bind=engine)


@app.post("/start-job")
def start_job(payload: dict):

    job_id = str(uuid.uuid4())

    db = SessionLocal()
    db.add(Job(id=job_id, status="queued"))
    db.commit()
    db.close()

    Thread(target=run_scraper, args=(job_id, payload["sales_nav_url"])).start()

    return {"job_id": job_id}


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


@app.get("/export/{job_id}")
def export_csv(job_id: str):

    db = SessionLocal()
    companies = db.query(Company).filter(Company.job_id == job_id).all()
    db.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Company Name", "Industry", "Employees",
        "Founded", "Headquarters", "LinkedIn URL"
    ])

    for c in companies:
        writer.writerow([
            c.companyName,
            c.industry,
            c.employeeCountRange,
            c.foundedYear,
            c.headquarters,
            c.linkedinCompanyUrl
        ])

    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=companies_{job_id}.csv"
        }
    )
