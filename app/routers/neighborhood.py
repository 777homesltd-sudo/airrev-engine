"""
AirRev Engine — Neighborhood Insights Router
170+ Calgary communities data layer
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_api_key
from app.models.schemas import NeighborhoodInsightRequest, NeighborhoodInsightResponse
from app.services.supabase_service import supabase
from app.services.rent_service import rent_service, CALGARY_RENT_DATA

router = APIRouter()


@router.post("/insights", response_model=NeighborhoodInsightResponse)
async def neighborhood_insights(
    request: NeighborhoodInsightRequest,
    _: bool = Depends(require_api_key),
):
    """
    Full neighborhood investment profile for a Calgary community.
    Pulls from Supabase community_insights table when available,
    falls back to calculated estimates.
    """
    community = request.community.strip().title()

    # Try Supabase cache first
    cached = await supabase.get_community_insights(community)
    if cached:
        return NeighborhoodInsightResponse(**cached)

    # Build from rent data + defaults
    community_rents = CALGARY_RENT_DATA.get(community, {})

    ltr_by_bedroom = {
        str(beds): data[1]  # avg rent
        for beds, data in community_rents.items()
    }

    # STR estimates: avg LTR monthly / 30 * 2.1 = nightly estimate
    str_by_bedroom = {
        bed: round((rent / 30) * 2.1, 2)
        for bed, rent in ltr_by_bedroom.items()
    }

    if not community_rents:
        raise HTTPException(
            status_code=404,
            detail=f"Community '{community}' not yet in database. "
                   f"Add it to your Supabase community_insights table.",
        )

    return NeighborhoodInsightResponse(
        community=community,
        city="Calgary",
        overview=f"{community} is a Calgary community with active rental and investment activity.",
        ltr_avg_rent_by_bedroom=ltr_by_bedroom,
        str_avg_nightly_by_bedroom=str_by_bedroom,
        str_avg_occupancy=0.68,          # Calgary STR average
        avg_cap_rate_ltr=0.042,          # Calgary LTR avg cap rate
        avg_cap_rate_str=0.055,          # Calgary STR avg cap rate
        active_listings=0,               # Populated from DDF
        avg_days_on_market=28,           # Calgary 2024 average
        median_sale_price=550000,        # Update from CREB data
        price_per_sqft=425,
        yoy_appreciation=0.06,           # 6% Calgary 2024 appreciation
    )


@router.get("/communities")
async def list_communities(_: bool = Depends(require_api_key)):
    """
    Return all available Calgary communities in the database.
    """
    return {
        "total": len(CALGARY_RENT_DATA),
        "communities": sorted(list(CALGARY_RENT_DATA.keys())),
        "note": "Add more communities via Supabase community_insights table"
    }
