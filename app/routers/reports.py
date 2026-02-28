"""
AirRev Engine — PDF Report Router
Generates print/email-ready PDFs for property analysis + CREB reports
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

from app.core.security import require_api_key
from app.services.pdf_service import generate_property_report, generate_creb_report
from app.services.email_service import email_service
from app.services.creb_pipeline import creb_pipeline
from app.models.schemas import AnalyzeListingRequest, AnalysisType

router = APIRouter()


class EmailReportRequest(BaseModel):
    to_email: str
    mls_number: Optional[str] = None
    analysis_type: str = "both"
    interest_rate: Optional[float] = None
    down_payment_pct: Optional[float] = None
    month: Optional[int] = None
    year: Optional[int] = None
    community: str = "Calgary"


async def _run_analysis(mls_number: str, analysis_type: str,
                         interest_rate=None, down_payment_pct=None):
    """Helper to run analysis and return dict."""
    from app.routers.analyze import analyze_listing
    from fastapi import BackgroundTasks as BT
    req = AnalyzeListingRequest(
        mls_number=mls_number,
        analysis_type=AnalysisType(analysis_type),
        interest_rate=interest_rate,
        down_payment_pct=down_payment_pct,
    )
    analysis = await analyze_listing(req, BT())
    return analysis.model_dump()


@router.get("/property/{mls_number}")
async def property_report_pdf(
    mls_number: str,
    analysis_type: str = "both",
    interest_rate: Optional[float] = None,
    down_payment_pct: Optional[float] = None,
    _: bool = Depends(require_api_key),
):
    """
    Generate a print-ready Property Investment Report PDF.
    Returns PDF binary — Lovable can trigger download or open in new tab.
    """
    try:
        analysis_dict = await _run_analysis(mls_number, analysis_type, interest_rate, down_payment_pct)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    try:
        pdf_bytes = generate_property_report(analysis_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    filename = f"AirRev_{mls_number}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/creb")
async def creb_report_pdf(
    month: Optional[int] = None,
    year: Optional[int] = None,
    community: str = "Calgary",
    _: bool = Depends(require_api_key),
):
    """Generate a print-ready CREB Monthly Market Report PDF."""
    now = datetime.now()
    report_data = await creb_pipeline.get_monthly_report(
        month=month or now.month,
        year=year or now.year,
        community=community,
    )

    try:
        pdf_bytes = generate_creb_report(report_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    m = month or now.month
    y = year or now.year
    month_name = datetime(y, m, 1).strftime("%b%Y")
    filename = f"AirRev_CREB_{community.replace(' ', '')}_{month_name}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/email/property")
async def email_property_report(
    request: EmailReportRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(require_api_key),
):
    """
    Generate a Property Investment Report and email it as a PDF attachment.

    ```
    POST /reports/email/property
    { "to_email": "client@example.com", "mls_number": "A2123456" }
    ```
    """
    if not request.mls_number:
        raise HTTPException(status_code=400, detail="mls_number is required for property reports")

    if not email_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Email not configured. Set EMAIL_PROVIDER + RESEND_API_KEY in .env"
        )

    try:
        analysis_dict = await _run_analysis(
            request.mls_number, request.analysis_type,
            request.interest_rate, request.down_payment_pct
        )
    except HTTPException as e:
        raise e

    pdf_bytes = generate_property_report(analysis_dict)
    prop = analysis_dict.get("property", {})
    summary = analysis_dict.get("summary", {})

    # Send in background — don't make user wait
    background_tasks.add_task(
        email_service.send_property_report,
        to_email=request.to_email,
        address=prop.get("address", "Property"),
        mls_number=request.mls_number,
        summary=summary,
        pdf_bytes=pdf_bytes,
    )

    return {
        "success": True,
        "message": f"Report is being sent to {request.to_email}",
        "mls_number": request.mls_number,
        "address": prop.get("address"),
        "recommendation": summary.get("recommendation"),
    }


@router.post("/email/creb")
async def email_creb_report(
    request: EmailReportRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(require_api_key),
):
    """
    Generate a CREB Monthly Report and email it as a PDF attachment.

    ```
    POST /reports/email/creb
    { "to_email": "client@example.com", "community": "Calgary" }
    ```
    """
    if not email_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Email not configured. Set EMAIL_PROVIDER + RESEND_API_KEY in .env"
        )

    now = datetime.now()
    report_data = await creb_pipeline.get_monthly_report(
        month=request.month or now.month,
        year=request.year or now.year,
        community=request.community,
    )

    pdf_bytes = generate_creb_report(report_data)
    m = request.month or now.month
    y = request.year or now.year
    month_name = datetime(y, m, 1).strftime("%B %Y")

    background_tasks.add_task(
        email_service.send_creb_report,
        to_email=request.to_email,
        month_name=month_name,
        community=request.community,
        report_data=report_data,
        pdf_bytes=pdf_bytes,
    )

    return {
        "success": True,
        "message": f"CREB report for {month_name} is being sent to {request.to_email}",
        "community": request.community,
        "period": month_name,
    }


@router.get("/property/{mls_number}")
async def property_report_pdf(
    mls_number: str,
    analysis_type: str = "both",
    interest_rate: Optional[float] = None,
    down_payment_pct: Optional[float] = None,
    _: bool = Depends(require_api_key),
):
    """
    Generate a print-ready Property Investment Report PDF.

    Returns the PDF as a binary response — your Lovable frontend
    can trigger a download or open it in a new tab.

    ```
    GET /reports/property/A2123456
    X-AirRev-Key: your-key
    ```
    """
    from fastapi import BackgroundTasks as BT
    from fastapi import Request

    # Run the full analysis
    req = AnalyzeListingRequest(
        mls_number=mls_number,
        analysis_type=AnalysisType(analysis_type),
        interest_rate=interest_rate,
        down_payment_pct=down_payment_pct,
    )

    try:
        analysis = await analyze_listing(req, BT())
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    # Convert Pydantic model → dict for PDF generator
    analysis_dict = analysis.model_dump()

    # Generate PDF
    try:
        pdf_bytes = generate_property_report(analysis_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    filename = f"AirRev_{mls_number}_{datetime.now().strftime('%Y%m%d')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.get("/creb")
async def creb_report_pdf(
    month: Optional[int] = None,
    year: Optional[int] = None,
    community: str = "Calgary",
    _: bool = Depends(require_api_key),
):
    """
    Generate a print-ready CREB Monthly Market Report PDF.

    ```
    GET /reports/creb?month=1&year=2025&community=Calgary
    X-AirRev-Key: your-key
    ```
    """
    from app.routers.creb import monthly_summary

    # Get the CREB data
    report_data = await monthly_summary(month=month, year=year, community=community)

    # Generate PDF
    try:
        pdf_bytes = generate_creb_report(report_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    now = datetime.now()
    m = month or now.month
    y = year or now.year
    month_name = datetime(y, m, 1).strftime("%b%Y")
    filename = f"AirRev_CREB_{community.replace(' ', '')}_{month_name}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(len(pdf_bytes)),
        },
    )
