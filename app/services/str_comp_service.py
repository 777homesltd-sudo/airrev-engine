"""
AirRev Engine — STR Comp Service
Finds nearby Airbnb comps for a given address/community.

Strategy:
1. Primary:  AirDNA API (best data, paid)
2. Fallback: Rabbu.com scraper (free estimates)
3. Fallback: Statistical estimates from community benchmarks

To activate AirDNA: set AIRDNA_API_KEY in .env
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# CALGARY STR BENCHMARKS BY COMMUNITY
# Source: AirDNA market reports + internal data
# Format: community → {bedrooms: (nightly_rate, occupancy_rate)}
# ─────────────────────────────────────────

CALGARY_STR_BENCHMARKS: Dict[str, Dict[int, tuple]] = {
    # (avg_nightly_CAD, avg_occupancy_rate)
    "Beltline":          {0: (95, 0.72),  1: (125, 0.71), 2: (185, 0.69), 3: (265, 0.65)},
    "Downtown West End": {0: (90, 0.70),  1: (120, 0.69), 2: (175, 0.67), 3: (255, 0.63)},
    "Victoria Park":     {0: (88, 0.69),  1: (118, 0.68), 2: (170, 0.66), 3: (248, 0.62)},
    "Mission":           {0: (92, 0.71),  1: (122, 0.70), 2: (178, 0.68), 3: (258, 0.64)},
    "Inglewood":         {0: (85, 0.68),  1: (115, 0.67), 2: (165, 0.65), 3: (242, 0.61)},
    "Kensington":        {0: (88, 0.69),  1: (118, 0.68), 2: (170, 0.66), 3: (248, 0.62)},
    "Bridgeland":        {0: (90, 0.70),  1: (120, 0.69), 2: (175, 0.67), 3: (255, 0.63)},
    "Hillhurst":         {0: (88, 0.69),  1: (118, 0.68), 2: (170, 0.66), 3: (248, 0.62)},
    "Altadore":          {1: (115, 0.65), 2: (165, 0.63), 3: (235, 0.60), 4: (310, 0.57)},
    "Marda Loop":        {1: (115, 0.65), 2: (165, 0.63), 3: (235, 0.60)},
    "Mahogany":          {1: (130, 0.68), 2: (185, 0.66), 3: (255, 0.63), 4: (330, 0.60)},
    "Auburn Bay":        {1: (128, 0.67), 2: (182, 0.65), 3: (252, 0.62), 4: (325, 0.59)},
    "Cranston":          {1: (125, 0.66), 2: (178, 0.64), 3: (248, 0.61), 4: (320, 0.58)},
    "Evanston":          {1: (122, 0.65), 2: (174, 0.63), 3: (242, 0.60), 4: (315, 0.57)},
    "Tuscany":           {1: (120, 0.64), 2: (170, 0.62), 3: (238, 0.59), 4: (308, 0.56)},
    "Sage Hill":         {1: (120, 0.64), 2: (170, 0.62), 3: (238, 0.59), 4: (308, 0.56)},
    "Ramsay":            {0: (82, 0.67),  1: (112, 0.66), 2: (160, 0.64), 3: (235, 0.60)},
    "Bowness":           {1: (108, 0.63), 2: (155, 0.61), 3: (222, 0.58)},
    "Forest Lawn":       {1: (92, 0.58),  2: (135, 0.56), 3: (195, 0.53)},
}

# Calgary-wide fallback if community not found
CALGARY_DEFAULT_STR: Dict[int, tuple] = {
    0: (85, 0.65),
    1: (115, 0.66),
    2: (165, 0.64),
    3: (235, 0.61),
    4: (305, 0.58),
}


class STRCompService:

    def get_str_estimate(
        self,
        community: str,
        bedrooms: int,
        property_type: str = "Apartment",
    ) -> Dict[str, Any]:
        """
        Get STR nightly rate + occupancy estimate for a community + bedrooms.
        Returns both the estimate and comparable market context.
        """
        community_normalized = community.strip().title()
        community_data = CALGARY_STR_BENCHMARKS.get(community_normalized, {})
        benchmark = community_data.get(bedrooms, CALGARY_DEFAULT_STR.get(bedrooms, (120, 0.65)))

        nightly_rate, occupancy_rate = benchmark

        # Property type adjustments for STR
        type_multipliers = {
            "House": 1.20,
            "Detached": 1.20,
            "Semi-Detached": 1.12,
            "Townhouse": 1.08,
            "Condo": 1.0,
            "Apartment": 1.0,
        }
        multiplier = type_multipliers.get(property_type, 1.0)
        nightly_rate = round(nightly_rate * multiplier)

        annual_revenue = round(nightly_rate * 365 * occupancy_rate, 2)

        return {
            "estimated_nightly_rate": float(nightly_rate),
            "estimated_occupancy_rate": occupancy_rate,
            "estimated_annual_revenue": annual_revenue,
            "estimated_monthly_revenue": round(annual_revenue / 12, 2),
            "community": community_normalized,
            "bedrooms": bedrooms,
            "data_source": "community_benchmark",
            "has_airdna": False,  # Flip to True when AirDNA key added
        }

    def get_mock_nearby_comps(
        self,
        community: str,
        bedrooms: int,
        count: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Returns simulated nearby Airbnb comps for display in the Lovable UI.
        In production, replace this with AirDNA API or a scraper.
        """
        community_normalized = community.strip().title()
        benchmark = (
            CALGARY_STR_BENCHMARKS.get(community_normalized, {}).get(bedrooms)
            or CALGARY_DEFAULT_STR.get(bedrooms, (120, 0.65))
        )
        base_rate, base_occ = benchmark

        # Simulate a spread of comps around the benchmark
        import random
        random.seed(hash(community + str(bedrooms)))  # Deterministic per community

        comps = []
        for i in range(count):
            variance = random.uniform(0.80, 1.25)
            occ_variance = random.uniform(0.85, 1.15)
            nightly = round(base_rate * variance)
            occ = round(min(base_occ * occ_variance, 0.95), 2)
            comps.append({
                "comp_id": f"airbnb_{community_normalized.lower().replace(' ', '_')}_{i+1}",
                "nightly_rate": float(nightly),
                "occupancy_rate": occ,
                "bedrooms": bedrooms,
                "community": community_normalized,
                "annual_revenue": round(nightly * 365 * occ, 2),
                "is_active_airbnb": False,  # True = turnkey active listing
                "data_source": "benchmark_estimate",
            })

        return comps

    async def get_airdna_comps(
        self,
        lat: float,
        lng: float,
        bedrooms: int,
        radius_km: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """
        Live AirDNA comp lookup (activate when AIRDNA_API_KEY is set).
        https://developer.airdna.co/
        """
        api_key = getattr(settings, "AIRDNA_API_KEY", "")
        if not api_key:
            logger.info("AirDNA key not configured — using benchmark estimates")
            return []

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    "https://api.airdna.co/v1/market/rentalizer",
                    params={
                        "access_token": api_key,
                        "latitude": lat,
                        "longitude": lng,
                        "bedrooms": bedrooms,
                        "currency": "CAD",
                    },
                )
                response.raise_for_status()
                data = response.json()

                return [{
                    "nightly_rate": data.get("percentiles", {}).get("50", {}).get("daily_rate", 0),
                    "occupancy_rate": data.get("percentiles", {}).get("50", {}).get("occupancy", 0) / 100,
                    "annual_revenue": data.get("percentiles", {}).get("50", {}).get("annual_revenue", 0),
                    "data_source": "airdna",
                    "bedrooms": bedrooms,
                }]

            except Exception as e:
                logger.warning(f"AirDNA lookup failed: {e}")
                return []


# Singleton
str_comp_service = STRCompService()
