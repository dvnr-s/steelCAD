"""
SQLAlchemy models — import all models here so Alembic and Base.metadata can discover them.
"""
from app.models.user import User
from app.models.design import Design
from app.models.customer import Customer
from app.models.estimate import Estimate, EstimateFrame
from app.models.rate import Rate
from app.models.company import CompanySettings
from app.models.audit import AuditLog

__all__ = [
    "User", "Design", "Customer", "Estimate", "EstimateFrame", "Rate",
    "CompanySettings", "AuditLog",
]
