"""
AirRev Engine — Analyze Listing Router
POST /analyze/listing  — The core AirRev Engine endpoint
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from app.core.security import require_api_key
from app.core.cache import cache, analyze_limiter, rate_limit_check
from app.models.schemas import (
    AnalyzeListingRequest,
    AnalyzeListingResponse,
    AnalysisType,
)
from app.services.ddf_service import ddf_service
from app.services.calculator_service import calculator
from app.services.rent_service import rent_service
from app.services.supabase_service import supabase
from app.services.str_comp_service import str_comp_service

router = APIRouter()


@router.post("/listing", response_model=AnalyzeListingResponse)
async def analyze_listing(
    request: AnalyzeListingRequest,
    background_tasks: BackgroundTasks,
    http_request: Request = None,
    _: bool = Depends(require_api_key),
):
    # Rate limiting
    if http_request:
        await rate_limit_check(http_request, analyze_limiter)

    # Cache check — skip DDF + recalculation if recently analyzed
    cache_key = (request.mls_number, request.analysis_type.value,
                 str(request.purchase_price_override), str(request.interest_rate))
    cached_result = cache.get(*cache_key)
    if cached_result:
        return cached_result
    """
    **AirRev Engine Core Endpoint**

    Pass in an MLS® number and get back a full investment analysis:
    - Property details from CREA DDF
    - Mortgage breakdown (Canadian semi-annual compounding)
    - LTR analysis (cap rate, CoC, cash flow)
    - STR analysis with Airbnb comp data
    - Investment recommendation

    ```
    POST /analyze/listing
    X-AirRev-Key: your-secret-key

    {
      "mls_number": "A2123456",
      "analysis_type": "both"
    }
    ```
    """

    # ── Step 1: Fetch listing from DDF ──────────────────────────────
    raw_listing = await ddf_service.get_listing_by_mls(request.mls_number)

    if not raw_listing:
        raise HTTPException(
            status_code=404,
            detail=f"MLS® {request.mls_number} not found in DDF feed. "
                   f"Verify the listing is active and accessible via your DDF credentials.",
        )

    property_details = ddf_service.parse_property_details(raw_listing)

    # Allow price override (user negotiating below list)
    if request.purchase_price_override:
        property_details.list_price = request.purchase_price_override

    # ── Step 2: Mortgage ────────────────────────────────────────────
    mortgage = calculator.calculate_mortgage(
        purchase_price=property_details.list_price,
        interest_rate=request.interest_rate,
        down_payment_pct=request.down_payment_pct,
        amortization_years=request.amortization_years,
    )

    # ── Step 3: Rent Estimates ──────────────────────────────────────
    rent_insight = rent_service.get_rent_estimate(
        community=property_details.community,
        bedrooms=property_details.bedrooms,
        property_type=property_details.property_type,
        square_footage=property_details.square_footage,
    )
    monthly_rent = request.monthly_rent_override or rent_insight.avg_rent

    # STR nightly rate estimate: monthly / 30 * premium multiplier
    # STR typically earns 1.5-2x LTR on revenue basis when occupied
    nightly_rate = request.nightly_rate_override or round((monthly_rent / 30) * 2.1, 2)

    # ── Step 4: LTR Analysis ────────────────────────────────────────
    ltr_analysis = None
    if request.analysis_type in (AnalysisType.LTR, AnalysisType.BOTH):
        ltr_analysis = calculator.calculate_ltr(
            property=property_details,
            mortgage=mortgage,
            monthly_rent=monthly_rent,
        )

    # ── Step 5: STR Analysis ────────────────────────────────────────
    str_analysis = None
    if request.analysis_type in (AnalysisType.STR, AnalysisType.BOTH):
        # Get STR estimate + nearby comps
        str_estimate = str_comp_service.get_str_estimate(
            community=property_details.community,
            bedrooms=property_details.bedrooms,
            property_type=property_details.property_type,
        )
        nearby_airbnbs = str_comp_service.get_mock_nearby_comps(
            community=property_details.community,
            bedrooms=property_details.bedrooms,
        )

        effective_nightly = request.nightly_rate_override or str_estimate["estimated_nightly_rate"]
        effective_occ = str_estimate["estimated_occupancy_rate"]

        str_analysis = calculator.calculate_str(
            property=property_details,
            mortgage=mortgage,
            nightly_rate=effective_nightly,
            occupancy_rate=effective_occ,
            nearby_airbnbs=nearby_airbnbs,
        )

    # ── Step 6: Investment Summary ──────────────────────────────────
    summary = calculator.generate_summary(
        ltr=ltr_analysis,
        str_analysis=str_analysis,
        analysis_type=request.analysis_type,
    )

    # ── Step 7: Log to Supabase (non-blocking) ──────────────────────
    background_tasks.add_task(
        supabase.log_analysis,
        mls_number=request.mls_number,
        analysis_type=request.analysis_type,
        result_summary={
            "cap_rate_ltr": ltr_analysis.cap_rate if ltr_analysis else None,
            "cap_rate_str": str_analysis.cap_rate if str_analysis else None,
            "coc_ltr": ltr_analysis.cash_on_cash_return if ltr_analysis else None,
            "coc_str": str_analysis.cash_on_cash_return if str_analysis else None,
            "recommendation": summary.recommendation,
            "best_strategy": summary.best_strategy,
            "purchase_price": property_details.list_price,
            "community": property_details.community,
        },
    )

    result = AnalyzeListingResponse(
        property=property_details,
        mortgage=mortgage,
        ltr=ltr_analysis,
        str_analysis=str_analysis,
        summary=summary,
    )

    # Cache for 1 hour (DDF listings don't change that fast)
    cache.set(*cache_key, value=result, ttl_seconds=3600)

    return result


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
