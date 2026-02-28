"""
AirRev Engine — Calculator Router
Standalone calculator endpoints for Lovable UI widgets
"""

from fastapi import APIRouter, Depends
from app.core.security import require_api_key
from app.models.schemas import InvestmentCalculatorRequest, RentInsightRequest, RentInsightResponse
from app.services.calculator_service import calculator
from app.services.rent_service import rent_service
from app.services.ddf_service import ddf_service

router = APIRouter()


@router.post("/investment")
async def investment_calculator(
    request: InvestmentCalculatorRequest,
    _: bool = Depends(require_api_key),
):
    """
    Full investment calculator with custom inputs.
    Powers the manual calculator widget in Lovable.
    """
    from app.models.schemas import PropertyDetails

    prop = PropertyDetails(
        mls_number="CALC",
        address="Calculator Input",
        community="Calgary",
        city="Calgary",
        province="AB",
        list_price=request.purchase_price,
        bedrooms=2,
        bathrooms=1,
        property_type="Residential",
    )

    mortgage = calculator.calculate_mortgage(
        purchase_price=request.purchase_price,
        interest_rate=request.interest_rate,
        down_payment_pct=request.down_payment_pct,
        amortization_years=request.amortization_years,
    )

    # Override property tax if provided
    if request.property_tax_annual:
        prop_tax_override = request.property_tax_annual
    else:
        prop_tax_override = None

    monthly_rent = request.annual_revenue / 12

    ltr = None
    str_result = None

    if request.analysis_type.value in ("ltr", "both"):
        ltr = calculator.calculate_ltr(prop, mortgage, monthly_rent)
        if prop_tax_override and ltr:
            # Recalculate with overridden property tax
            diff = prop_tax_override - ltr.property_tax_annual
            ltr.property_tax_annual = round(prop_tax_override, 2)
            ltr.total_annual_expenses = round(ltr.total_annual_expenses + diff, 2)
            ltr.noi = round(ltr.noi - diff, 2)

    if request.analysis_type.value in ("str", "both"):
        nightly = (request.annual_revenue / 365) / 0.70  # Back-calculate nightly from revenue
        str_result = calculator.calculate_str(prop, mortgage, nightly)

    summary = calculator.generate_summary(ltr, str_result, request.analysis_type)

    return {
        "mortgage": mortgage,
        "ltr": ltr,
        "str": str_result,
        "summary": summary,
    }


@router.post("/rent-insight", response_model=RentInsightResponse)
async def rent_insight(
    request: RentInsightRequest,
    _: bool = Depends(require_api_key),
):
    """
    Get rent estimates for a Calgary community + bedroom combo.
    Pulls comparable active DDF listings to validate estimates.
    """
    # Get base estimate
    estimate = rent_service.get_rent_estimate(
        community=request.community,
        bedrooms=request.bedrooms,
        property_type=request.property_type or "Apartment",
        square_footage=request.square_footage,
    )

    # Fetch real comps from DDF to validate
    comps = await ddf_service.search_listings_by_community(
        community=request.community,
        limit=10,
    )

    # Format comps for frontend display
    formatted_comps = [
        {
            "mls_number": c.get("ListingKey"),
            "address": c.get("UnparsedAddress", ""),
            "list_price": c.get("ListPrice"),
            "bedrooms": c.get("BedroomsTotal"),
            "bathrooms": c.get("BathroomsTotalInteger"),
            "sqft": c.get("LivingArea"),
            "property_type": c.get("PropertyType"),
        }
        for c in comps
        if c.get("BedroomsTotal") == request.bedrooms
    ][:5]

    estimate.comparable_listings = formatted_comps
    return estimate


@router.get("/mortgage-breakdown")
async def mortgage_breakdown(
    purchase_price: float,
    interest_rate: float = None,
    down_payment_pct: float = None,
    amortization_years: int = None,
    _: bool = Depends(require_api_key),
):
    """
    Just the mortgage numbers. For live UI sliders in Lovable.
    """
    result = calculator.calculate_mortgage(
        purchase_price=purchase_price,
        interest_rate=interest_rate,
        down_payment_pct=down_payment_pct,
        amortization_years=amortization_years,
    )
    return result
