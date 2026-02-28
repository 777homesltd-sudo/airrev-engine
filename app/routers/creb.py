"""
AirRev Engine — CREB Report Router
Monthly market summary reports, backed by Supabase pipeline
"""

from fastapi import APIRouter, Depends, Body
from app.core.security import require_api_key
from app.services.creb_pipeline import creb_pipeline
from datetime import datetime
from typing import Optional, Dict, Any

router = APIRouter()


@router.post("/update")
async def update_creb_data(
    report: Dict[str, Any] = Body(...),
    _: bool = Depends(require_api_key),
):
    """
    **Admin endpoint** — Store new monthly CREB data in Supabase.

    Call this once a month after CREB publishes stats.
    Paste in the JSON structure from /creb/monthly-summary as a template.

    ```
    POST /creb/update
    X-AirRev-Key: your-key
    { "report_month": 1, "report_year": 2025, "community": "Calgary", ... }
    ```
    """
    success = await creb_pipeline.upsert_monthly_report(report)
    return {
        "success": success,
        "message": "CREB data stored successfully" if success else "Stored locally (Supabase not configured)",
        "month": report.get("report_month"),
        "year": report.get("report_year"),
        "community": report.get("community", "Calgary"),
    }


@router.get("/monthly-summary")
async def monthly_summary(
    month: Optional[int] = None,
    year: Optional[int] = None,
    community: Optional[str] = None,
    _: bool = Depends(require_api_key),
):
    """
    Monthly CREB-style market summary.
    Returns data from Supabase if available, otherwise defaults.
    """
    now = datetime.now()
    return await creb_pipeline.get_monthly_report(
        month=month or now.month,
        year=year or now.year,
        community=community or "Calgary",
    )
