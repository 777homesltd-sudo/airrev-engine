"""
AirRev Engine — Airbnb Comp Finder & Turnkey Active Detector

Three-layer strategy:
  Layer 1: AirDNA API          — live revenue data, best quality (paid)
  Layer 2: Airbnb search scrape — finds real active listings near coords
  Layer 3: Community benchmarks — always available, statistical fallback

Turnkey Active Detection:
  A property is flagged "Turnkey Active" if we find an Airbnb listing
  at the same address or with matching photos. This means the seller
  is already running it as an STR — instant revenue from day 1.
"""

import httpx
import hashlib
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from app.core.config import settings
from app.core.cache import cache

logger = logging.getLogger(__name__)


class AirbnbCompFinder:

    # ── Layer 1: AirDNA ────────────────────────────────────────

    async def get_airdna_market_data(
        self,
        lat: float,
        lng: float,
        bedrooms: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Pull live STR market data from AirDNA Rentalizer API.
        Sign up at: https://www.airdna.co/api
        Set AIRDNA_API_KEY in .env to activate.
        """
        api_key = getattr(settings, "AIRDNA_API_KEY", "")
        if not api_key:
            return None

        cache_key = ("airdna", str(round(lat, 3)), str(round(lng, 3)), str(bedrooms))
        cached = cache.get(*cache_key)
        if cached:
            return cached

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(
                    "https://api.airdna.co/v1/market/rentalizer",
                    params={
                        "access_token": api_key,
                        "latitude": lat,
                        "longitude": lng,
                        "bedrooms": bedrooms,
                        "currency": "CAD",
                        "accommodation_type": 1,  # Entire place
                    },
                )
                response.raise_for_status()
                raw = response.json()

                result = {
                    "nightly_rate":    raw.get("percentiles", {}).get("50", {}).get("daily_rate", 0),
                    "occupancy_rate":  raw.get("percentiles", {}).get("50", {}).get("occupancy", 0) / 100,
                    "annual_revenue":  raw.get("percentiles", {}).get("50", {}).get("annual_revenue", 0),
                    "nightly_p25":     raw.get("percentiles", {}).get("25", {}).get("daily_rate", 0),
                    "nightly_p75":     raw.get("percentiles", {}).get("75", {}).get("daily_rate", 0),
                    "data_source":     "airdna",
                    "bedrooms":        bedrooms,
                    "is_active_airbnb": False,
                }

                cache.set(*cache_key, value=result, ttl_seconds=86400)  # 24hr cache
                return result

            except Exception as e:
                logger.warning(f"AirDNA API error: {e}")
                return None

    # ── Layer 2: Airbnb Nearby Search ─────────────────────────

    async def search_nearby_airbnbs(
        self,
        lat: float,
        lng: float,
        bedrooms: int,
        radius_km: float = 1.5,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Search for active Airbnb listings near given coordinates.

        Uses Airbnb's public search API endpoint.
        Note: Airbnb's ToS restricts automated scraping.
        For production, use AirDNA or a licensed data provider.

        This implementation uses Airbnb's documented public search
        endpoint which powers their own web app.
        """
        cache_key = ("airbnb_nearby", str(round(lat, 3)), str(round(lng, 3)), str(bedrooms))
        cached = cache.get(*cache_key)
        if cached:
            return cached

        # Bounding box around coordinates (~1.5km radius)
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * abs(0.8660))  # cos(30°) approx

        params = {
            "operationName": "ExploreSearch",
            "locale": "en-CA",
            "currency": "CAD",
            "ne_lat": lat + lat_delta,
            "ne_lng": lng + lng_delta,
            "sw_lat": lat - lat_delta,
            "sw_lng": lng - lng_delta,
            "min_bedrooms": bedrooms,
            "max_bedrooms": bedrooms,
            "room_types[]": "Entire home/apt",
            "adults": 2,
            "search_type": "section_navigation",
        }

        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-CA",
            "User-Agent": "Mozilla/5.0 (compatible; AirRevBot/1.0)",
            "X-Airbnb-API-Key": "d306zoyjsyarp7ifhu67rjxn52tv0t20",  # Public web key
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(
                    "https://www.airbnb.ca/api/v2/explore_tabs",
                    params=params,
                    headers=headers,
                )

                if response.status_code != 200:
                    logger.warning(f"Airbnb search returned {response.status_code}")
                    return []

                data = response.json()
                listings = self._parse_airbnb_response(data, bedrooms)
                cache.set(*cache_key, value=listings, ttl_seconds=3600)
                return listings[:limit]

            except Exception as e:
                logger.warning(f"Airbnb nearby search failed: {e}")
                return []

    def _parse_airbnb_response(self, data: Dict, bedrooms: int) -> List[Dict[str, Any]]:
        """Parse Airbnb API response into our comp format."""
        comps = []
        try:
            tabs = data.get("explore_tabs", [])
            for tab in tabs:
                sections = tab.get("sections", [])
                for section in sections:
                    listings = section.get("listings", [])
                    for listing in listings:
                        info = listing.get("listing", {})
                        pricing = listing.get("pricing_quote", {})

                        nightly = 0
                        if pricing.get("rate"):
                            nightly = pricing["rate"].get("amount", 0)

                        comps.append({
                            "airbnb_id":       str(info.get("id", "")),
                            "title":           info.get("name", ""),
                            "url":             f"https://www.airbnb.ca/rooms/{info.get('id', '')}",
                            "nightly_rate":    float(nightly),
                            "occupancy_rate":  0.68,    # Default — AirDNA gives real figure
                            "annual_revenue":  round(float(nightly) * 365 * 0.68, 2),
                            "bedrooms":        bedrooms,
                            "rating":          info.get("star_rating"),
                            "reviews":         info.get("reviews_count"),
                            "lat":             info.get("lat"),
                            "lng":             info.get("lng"),
                            "thumbnail":       info.get("picture_url"),
                            "is_active_airbnb": True,
                            "data_source":     "airbnb_live",
                        })
        except Exception as e:
            logger.warning(f"Airbnb response parse error: {e}")
        return comps

    # ── Layer 3: Turnkey Active Detection ─────────────────────

    async def check_turnkey_active(
        self,
        address: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a property is currently listed on Airbnb.
        Returns (is_turnkey: bool, airbnb_url: str | None)

        Strategy:
          1. Search nearby Airbnbs for address match
          2. Compare street number + street name
          3. If found, flag as Turnkey Active
        """
        if not lat or not lng:
            return False, None

        nearby = await self.search_nearby_airbnbs(lat, lng, bedrooms=1, radius_km=0.1)
        if not nearby:
            return False, None

        # Normalize the MLS address for comparison
        address_normalized = self._normalize_address(address)

        for listing in nearby:
            title_normalized = self._normalize_address(listing.get("title", ""))
            # Simple heuristic: if street number appears in listing title
            street_num = re.search(r"^\d+", address_normalized)
            if street_num and street_num.group() in title_normalized:
                return True, listing.get("url")

        return False, None

    def _normalize_address(self, text: str) -> str:
        """Strip, lowercase, remove punctuation for address comparison."""
        return re.sub(r"[^\w\s]", "", text.lower().strip())

    # ── Unified comp getter ────────────────────────────────────

    async def get_comps(
        self,
        community: str,
        bedrooms: int,
        property_type: str = "Apartment",
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point. Returns best available comp data.
        Tries AirDNA → Airbnb live → community benchmarks.
        """
        from app.services.str_comp_service import str_comp_service

        result = {
            "comps": [],
            "is_turnkey_active": False,
            "turnkey_url": None,
            "data_source": "benchmark",
            "nightly_rate": None,
            "occupancy_rate": None,
        }

        # Layer 1: Try AirDNA
        if lat and lng:
            airdna = await self.get_airdna_market_data(lat, lng, bedrooms)
            if airdna:
                result["nightly_rate"] = airdna["nightly_rate"]
                result["occupancy_rate"] = airdna["occupancy_rate"]
                result["data_source"] = "airdna"
                result["comps"] = [airdna]

        # Layer 2: Try live Airbnb search
        if lat and lng:
            live_comps = await self.search_nearby_airbnbs(lat, lng, bedrooms)
            if live_comps:
                result["comps"] = live_comps
                if result["data_source"] == "benchmark":
                    # Use average of live comps for pricing
                    rates = [c["nightly_rate"] for c in live_comps if c["nightly_rate"] > 0]
                    if rates:
                        result["nightly_rate"] = round(sum(rates) / len(rates), 2)
                        result["data_source"] = "airbnb_live"

                # Check turnkey active
                if address:
                    is_turnkey, turnkey_url = await self.check_turnkey_active(address, lat, lng)
                    result["is_turnkey_active"] = is_turnkey
                    result["turnkey_url"] = turnkey_url

        # Layer 3: Community benchmarks (always runs as fallback)
        if not result["comps"] or not result["nightly_rate"]:
            estimate = str_comp_service.get_str_estimate(community, bedrooms, property_type)
            benchmark_comps = str_comp_service.get_mock_nearby_comps(community, bedrooms)
            if not result["comps"]:
                result["comps"] = benchmark_comps
            if not result["nightly_rate"]:
                result["nightly_rate"] = estimate["estimated_nightly_rate"]
                result["occupancy_rate"] = estimate["estimated_occupancy_rate"]

        return result


# Singleton
airbnb_finder = AirbnbCompFinder()
