"""GA4 (Google Analytics 4) から動画別の流入・購入データを自動取得する.

計測リンクの utm_campaign (svf_<code>) をキーに、GA4 Data API から
セッション数・購入数・売上を動画単位で取得する。

前提 (10分程度の初回設定):
1. LP/ショップにGA4を導入し、eコマース計測 (purchase イベント) を有効化
2. Google Cloud でサービスアカウントを作成し、JSONキーをダウンロード
3. GA4 プロパティの管理画面で、そのサービスアカウントのメールアドレスに
   「閲覧者」権限を付与
4. .env に設定:
   GA4_PROPERTY_ID=123456789
   GOOGLE_APPLICATION_CREDENTIALS=C:/path/to/service-account.json
5. pip install "short-video-factory[ga4]"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

GA4_ENDPOINT = "https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

CAMPAIGN_PREFIX = "svf_"


@dataclass
class GA4VideoTraffic:
    """1動画×1流入元ぶんのGA4データ."""

    short_code: str
    platform: Optional[str]  # youtube / tiktok / instagram / None(判別不能)
    raw_source: str
    sessions: int
    purchases: int
    revenue: float


def _normalize_platform(source: str) -> Optional[str]:
    s = (source or "").lower()
    if "youtube" in s:
        return "youtube"
    if "tiktok" in s:
        return "tiktok"
    if "instagram" in s or s in ("ig", "igshopping"):
        return "instagram"
    return None


def fetch_video_traffic(
    property_id: str,
    days: int = 28,
    credentials_path: str = "",
) -> list[GA4VideoTraffic]:
    """utm_campaign が svf_ で始まるトラフィックを動画単位で取得する."""
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        import google.auth
    except ImportError as e:
        raise RuntimeError(
            "GA4連携には追加パッケージが必要です: "
            'pip install "short-video-factory[ga4]"'
        ) from e

    if credentials_path:
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=_SCOPES
        )
    else:
        # GOOGLE_APPLICATION_CREDENTIALS 環境変数などから自動解決
        creds, _ = google.auth.default(scopes=_SCOPES)

    body = {
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
        "dimensions": [
            {"name": "sessionCampaignName"},
            {"name": "sessionSource"},
        ],
        "metrics": [
            {"name": "sessions"},
            {"name": "ecommercePurchases"},
            {"name": "purchaseRevenue"},
        ],
        "dimensionFilter": {
            "filter": {
                "fieldName": "sessionCampaignName",
                "stringFilter": {
                    "matchType": "BEGINS_WITH",
                    "value": CAMPAIGN_PREFIX,
                },
            }
        },
        "limit": 10000,
    }

    session = AuthorizedSession(creds)
    response = session.post(
        GA4_ENDPOINT.format(property_id=property_id), json=body, timeout=60
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"GA4 APIエラー ({response.status_code}): {response.text[:500]}"
        )

    results: list[GA4VideoTraffic] = []
    for row in response.json().get("rows", []):
        dims = [d.get("value", "") for d in row.get("dimensionValues", [])]
        mets = [m.get("value", "0") for m in row.get("metricValues", [])]
        campaign, source = (dims + ["", ""])[:2]
        if not campaign.startswith(CAMPAIGN_PREFIX):
            continue
        results.append(
            GA4VideoTraffic(
                short_code=campaign[len(CAMPAIGN_PREFIX):],
                platform=_normalize_platform(source),
                raw_source=source,
                sessions=int(float(mets[0] or 0)),
                purchases=int(float(mets[1] or 0)),
                revenue=float(mets[2] or 0),
            )
        )
    return results
