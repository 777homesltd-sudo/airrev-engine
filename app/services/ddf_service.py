"""
AirRev Engine — DDF Service
Connects to CREA's Data Distribution Facility (DDF) OData API
Canadian REALTORS® feed — clean structured data, no scraping needed
"""

import httpx
import logging
from typing import Optional, Dict, Any
from app.core.config import settings
from app.models.schemas import PropertyDetails

logger = logging.getLogger(__name__)


class DDFService:
    """
    CREA DDF OData v1 client.
    Docs: https://ddfapi.realtor.ca/
    Auth: Basic auth with your DDF Access Key + Secret Key
    """

    BASE_URL = "https://ddfapi.realtor.ca/odata/v1"

    def __init__(self):
        self.auth = (settings.DDF_ACCESS_KEY, settings.DDF_SECRET_KEY)
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "AirRev.io/1.0",
        }

    async def get_listing_by_mls(self, mls_number: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single listing by MLS® number from the DDF feed.
        Returns raw DDF JSON or None if not found.
        """
        # DDF OData filter syntax
        filter_query = f"ListingKey eq '{mls_number}'"
        url = f"{self.BASE_URL}/Property"
        params = {
            "$filter": filter_query,
            "$top": 1,
            "$expand": "Media,Room",  # Include photos and room breakdown
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    auth=self.auth,
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()
                listings = data.get("value", [])
                return listings[0] if listings else None

            except httpx.HTTPStatusError as e:
                logger.error(f"DDF API error for MLS {mls_number}: {e.response.status_code}")
                raise
            except httpx.RequestError as e:
                logger.error(f"DDF connection error: {e}")
                raise

    async def search_listings_by_community(
        self,
        community: str,
        city: str = "Calgary",
        limit: int = 50,
    ) -> list:
        """
        Fetch active listings in a community for comp analysis.
        """
        filter_query = (
            f"City eq '{city}' and CommunityName eq '{community}' "
            f"and StandardStatus eq 'Active'"
        )
        url = f"{self.BASE_URL}/Property"
        params = {
            "$filter": filter_query,
            "$top": limit,
            "$select": (
                "ListingKey,ListPrice,BedroomsTotal,BathroomsTotalInteger,"
                "LivingArea,PropertyType,CommunityName,UnparsedAddress"
            ),
            "$orderby": "ListPrice asc",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    auth=self.auth,
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json().get("value", [])
            except Exception as e:
                logger.error(f"DDF community search error: {e}")
                return []

    def parse_property_details(self, raw: Dict[str, Any]) -> PropertyDetails:
        """
        Map raw DDF JSON fields → our PropertyDetails model.
        DDF field names follow RESO Data Dictionary standard.
        """
        return PropertyDetails(
            mls_number=raw.get("ListingKey", ""),
            address=raw.get("UnparsedAddress", ""),
            community=raw.get("CommunityName", ""),
            city=raw.get("City", "Calgary"),
            province=raw.get("StateOrProvince", "AB"),
            postal_code=raw.get("PostalCode"),
            list_price=float(raw.get("ListPrice", 0)),
            bedrooms=int(raw.get("BedroomsTotal", 0)),
            bathrooms=float(raw.get("BathroomsTotalInteger", 0)),
            square_footage=float(raw["LivingArea"]) if raw.get("LivingArea") else None,
            property_type=raw.get("PropertyType", "Residential"),
            year_built=int(raw["YearBuilt"]) if raw.get("YearBuilt") else None,
            lot_size=float(raw["LotSizeArea"]) if raw.get("LotSizeArea") else None,
            parking=int(raw["ParkingTotal"]) if raw.get("ParkingTotal") else None,
            listing_url=f"https://www.realtor.ca/{raw.get('ListingKey', '')}",
        )


# Singleton
ddf_service = DDFService()
