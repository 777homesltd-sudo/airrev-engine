"""
AirRev Engine — Supabase Service
Logs searches, caches reports, stores community data
"""

import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger(__name__)


class SupabaseService:
    """
    Direct Supabase REST API client (no supabase-py dependency needed).
    Uses Service Key for server-side operations.
    """

    def __init__(self):
        self.base_url = settings.SUPABASE_URL
        self.headers = {
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and settings.SUPABASE_SERVICE_KEY)

    async def log_analysis(
        self,
        mls_number: str,
        analysis_type: str,
        result_summary: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """Log a listing analysis to listing_analytics table."""
        if not self.enabled:
            return None

        payload = {
            "mls_number": mls_number,
            "analysis_type": analysis_type,
            "cap_rate_ltr": result_summary.get("cap_rate_ltr"),
            "cap_rate_str": result_summary.get("cap_rate_str"),
            "coc_ltr": result_summary.get("coc_ltr"),
            "coc_str": result_summary.get("coc_str"),
            "recommendation": result_summary.get("recommendation"),
            "best_strategy": result_summary.get("best_strategy"),
            "purchase_price": result_summary.get("purchase_price"),
            "community": result_summary.get("community"),
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/rest/v1/listing_analytics",
                    json=payload,
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()
                return data[0].get("id") if data else None
            except Exception as e:
                logger.warning(f"Supabase log failed (non-critical): {e}")
                return None

    async def get_community_insights(self, community: str) -> Optional[Dict[str, Any]]:
        """Fetch cached community insights from Supabase."""
        if not self.enabled:
            return None

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/rest/v1/community_insights",
                    params={
                        "community_name": f"eq.{community}",
                        "select": "*",
                        "limit": 1,
                    },
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()
                return data[0] if data else None
            except Exception as e:
                logger.warning(f"Supabase community fetch failed: {e}")
                return None

    async def cache_report(
        self,
        mls_number: str,
        report_type: str,
        report_data: Dict[str, Any],
        ttl_hours: int = 24,
    ) -> Optional[str]:
        """Cache a report to avoid re-running expensive analysis."""
        if not self.enabled:
            return None

        payload = {
            "mls_number": mls_number,
            "report_type": report_type,
            "report_data": report_data,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": datetime.utcnow().isoformat(),  # TTL handled in Supabase policy
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/rest/v1/report_cache",
                    json=payload,
                    headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                )
                response.raise_for_status()
                data = response.json()
                return data[0].get("id") if data else None
            except Exception as e:
                logger.warning(f"Supabase cache write failed: {e}")
                return None


# Singleton
supabase = SupabaseService()
