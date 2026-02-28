"""
AirRev Engine — CREB Data Pipeline
Manages monthly CREB market data stored in Supabase.

Flow:
  1. You (or a cron job) POST new monthly stats to /creb/update
  2. Data is stored in Supabase creb_monthly_reports table
  3. /creb/monthly-summary pulls from Supabase, falls back to defaults
  4. /reports/creb generates the PDF from that data

Future: wire a scraper to pull from CREB's public stats page monthly.
CREB publishes stats at: https://www.creb.com/market-stats/
"""

import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.core.config import settings
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)


class CREBPipeline:

    async def get_monthly_report(
        self,
        month: int,
        year: int,
        community: str = "Calgary",
    ) -> Dict[str, Any]:
        """
        Fetch monthly report from Supabase.
        Falls back to reasonable Calgary defaults if not found.
        """
        cached = await self._fetch_from_supabase(month, year, community)
        if cached:
            logger.info(f"CREB data: Supabase hit for {community} {month}/{year}")
            return cached

        logger.info(f"CREB data: no Supabase data for {community} {month}/{year}, using defaults")
        return self._default_report(month, year, community)

    async def upsert_monthly_report(self, report: Dict[str, Any]) -> bool:
        """
        Store a monthly report in Supabase.
        Called by the admin POST /creb/update endpoint.
        """
        if not supabase.enabled:
            return False

        payload = {
            "report_month": report["report_month"],
            "report_year": report["report_year"],
            "community": report.get("community", "Calgary"),
            "report_data": report,
            "updated_at": datetime.utcnow().isoformat(),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{supabase.base_url}/rest/v1/creb_monthly_reports",
                    json=payload,
                    headers={
                        **supabase.headers,
                        "Prefer": "resolution=merge-duplicates",
                    },
                )
                response.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Failed to store CREB report: {e}")
                return False

    async def _fetch_from_supabase(
        self, month: int, year: int, community: str
    ) -> Optional[Dict[str, Any]]:
        if not supabase.enabled:
            return None

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    f"{supabase.base_url}/rest/v1/creb_monthly_reports",
                    params={
                        "report_month": f"eq.{month}",
                        "report_year": f"eq.{year}",
                        "community": f"eq.{community}",
                        "select": "report_data",
                        "limit": 1,
                    },
                    headers=supabase.headers,
                )
                response.raise_for_status()
                data = response.json()
                if data:
                    return data[0]["report_data"]
                return None
            except Exception as e:
                logger.warning(f"CREB Supabase fetch failed: {e}")
                return None

    def _default_report(self, month: int, year: int, community: str) -> Dict[str, Any]:
        """
        Reasonable Calgary defaults.
        Replace with real CREB data by calling POST /creb/update.
        """
        month_name = datetime(year, month, 1).strftime("%B %Y")
        return {
            "report_month": month,
            "report_year": year,
            "community": community,
            "generated_at": datetime.utcnow().isoformat(),
            "data_source": "default_estimates",   # Flags this as not real data
            "market_summary": {
                "total_sales": 2847,
                "new_listings": 4231,
                "active_listings": 6102,
                "sales_to_new_listings_ratio": 0.67,
                "days_on_market_avg": 28,
                "benchmark_price": 607800,
                "benchmark_price_yoy_change": 0.062,
                "months_of_supply": 2.1,
                "market_condition": "Seller's Market",
            },
            "by_property_type": {
                "Detached":     {"sales": 1204, "benchmark_price": 782000, "yoy_change": 0.071, "dom": 22},
                "Semi-Detached":{"sales": 312,  "benchmark_price": 658000, "yoy_change": 0.065, "dom": 20},
                "Row":          {"sales": 487,  "benchmark_price": 435000, "yoy_change": 0.082, "dom": 18},
                "Apartment":    {"sales": 844,  "benchmark_price": 342000, "yoy_change": 0.094, "dom": 32},
            },
            "rental_market": {
                "avg_ltr_1bed": 1850,
                "avg_ltr_2bed": 2450,
                "avg_ltr_3bed": 3100,
                "vacancy_rate": 0.021,
                "yoy_rent_change": 0.038,
            },
            "investment_metrics": {
                "avg_cap_rate": 0.041,
                "avg_gross_yield": 0.052,
                "price_to_rent_ratio": 19.4,
            },
            "narrative": (
                f"Calgary's housing market in {month_name} continued to show resilience, "
                f"with benchmark prices rising 6.2% year-over-year. "
                f"Tight supply at 2.1 months keeps conditions firmly in seller's territory. "
                f"The apartment segment remains the strongest performer for investors, "
                f"with cap rates averaging 4.1% citywide."
            ),
            "print_ready": True,
        }


# Singleton
creb_pipeline = CREBPipeline()
