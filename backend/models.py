from sqlalchemy import Column, String, Integer, ForeignKey
from database import Base

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)
    status = Column(String)

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    job_id = Column(String, ForeignKey("jobs.id"))

    companyName = Column(String)
    industry = Column(String)
    employeeCountRange = Column(String)
    employeeDisplayCount = Column(String)
    linkedinCompanyUrl = Column(String)
    foundedYear = Column(String)
    headquarters = Column(String)
