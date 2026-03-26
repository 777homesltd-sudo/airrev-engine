"""
AirRev Engine — Analyze Listing Router
POST /analyze/listing  — The core AirRev Engine endpoint
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from app.core.security import require_api_key
from app.models.schemas import (
    AnalyzeListingRequest,
    AnalyzeListingResponse,
    AnalysisType,
)
from app.services.ddf_service import ddf_service
from app.services.calculator_service import calculator
from app.services.supabase_service import supabase

router = APIRouter()

from datetime import datetime, timedelta, timezone

def is_stale(last_scraped):
    if not last_scraped:
        return True
    # last_scraped expected as ISO string or datetime
    if isinstance(last_scraped, str):
        try:
            scraped_time = datetime.fromisoformat(last_scraped)
        except Exception:
            return True
    else:
        scraped_time = last_scraped
    now = datetime.now(timezone.utc)
    return scraped_time < now - timedelta(days=7)


@router.post("/listing", response_model=AnalyzeListingResponse)
async def analyze_listing(
    request: AnalyzeListingRequest,
    background_tasks: BackgroundTasks,  # Magic key: for async refresh trigger
    _: bool = Depends(require_api_key),
):
    # 1. Fetch property details from DDF
    raw_listing = await ddf_service.get_listing_by_mls(request.mls_number)
    if not raw_listing:
        raise HTTPException(
            status_code=404,
            detail=f"MLS® {request.mls_number} not found in DDF feed. "
                   f"Verify the listing is active and accessible via your DDF credentials.",
        )
    property_details = ddf_service.parse_property_details(raw_listing)
    if request.purchase_price_override:
        property_details.list_price = request.purchase_price_override

    # 2. LAYER 1: Check Supabase Cache First (use 1km)
    existing_comps = await supabase.get_nearby_airbnb_comps(
        lat=property_details.latitude,
        lng=property_details.longitude
    )

    # 3. LAYER 2 & 3: Background Refresh Logic
    should_refresh = not existing_comps or is_stale(
        getattr(existing_comps[0], "last_scraped", None)
        if existing_comps else None
    )
    if should_refresh and property_details.latitude and property_details.longitude:
        background_tasks.add_task(
            supabase.invoke_edge_function,
            "analyze-str-v2",
            {"lat": property_details.latitude, "lng": property_details.longitude}
        )

    # 4. Immediate Response: calculate STR and dummy response
    str_analysis = calculator.calculate_str(existing_comps or [])

    return AnalyzeListingResponse(
        property=property_details,
        str_analysis=str_analysis,
        # ...rest of your response fields as needed (return what your frontend requires)
    )


@router.post("/quick-calc")
async def quick_calculate(
    purchase_price: float,
    monthly_rent: float,
    bedrooms: int = 2,
    _: bool = Depends(require_api_key),
):
    """
    Fast back-of-napkin calculation without MLS lookup.
    Useful for Lovable UI live sliders.
    """
    from app.models.schemas import PropertyDetails

    # Create a minimal property object
    prop = PropertyDetails(
        mls_number="MANUAL",
        address="Manual Entry",
        community="Calgary",
        city="Calgary",
        province="AB",
        list_price=purchase_price,
        bedrooms=bedrooms,
        bathrooms=1.0,
        property_type="Residential",
    )

    mortgage = calculator.calculate_mortgage(purchase_price=purchase_price)
    ltr = calculator.calculate_ltr(prop, mortgage, monthly_rent)

    return {
        "purchase_price": purchase_price,
        "monthly_rent": monthly_rent,
        "mortgage_monthly": mortgage.monthly_payment,
        "cap_rate": ltr.cap_rate_display,
        "cash_on_cash": ltr.cash_on_cash_display,
        "monthly_cash_flow": ltr.monthly_cash_flow,
        "annual_cash_flow": ltr.annual_cash_flow,
        "noi": ltr.noi,
    }
