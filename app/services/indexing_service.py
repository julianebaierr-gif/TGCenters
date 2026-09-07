import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.article import Article
from app.models.settings import IndexingLog, SiteSetting

class IndexingService:
    """
    Legitimate Search Engine Indexing & URL Discovery Integration.
    Supports:
    1. IndexNow API Protocol (Microsoft Bing, Yandex, Seznam, Naver)
    2. Google Search Engine Sitemap Discovery Ping
    3. Comprehensive Submission Logging, Status Tracking, and Retries
    """

    INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

    @classmethod
    def get_indexnow_key(cls, db: Optional[Session] = None) -> str:
        """
        Retrieves or generates a consistent IndexNow host verification key.
        """
        if db:
            setting = db.query(SiteSetting).filter(SiteSetting.key == "indexnow_key").first()
            if setting and setting.value and len(setting.value) >= 16:
                return setting.value.strip()
        
        # Consistent key derived from APP_SECRET or fallback
        import hashlib
        return hashlib.sha256(settings.APP_SECRET.encode("utf-8")).hexdigest()[:32]

    @classmethod
    def submit_article_url(
        cls,
        db: Session,
        article: Article,
        base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submits a published article's URL to IndexNow and search engine ping endpoints.
        Logs every attempt in the indexing_logs table.
        """
        site_base = (base_url or settings.BASE_URL).rstrip("/")
        article_url = f"{site_base}/blog/{article.slug}"
        host = urllib.parse.urlparse(site_base).netloc or "localhost"

        indexnow_key = cls.get_indexnow_key(db)
        key_location = f"{site_base}/{indexnow_key}.txt"

        payload = {
            "host": host,
            "key": indexnow_key,
            "keyLocation": key_location,
            "urlList": [article_url]
        }

        results = []
        overall_success = False

        # 1. Submit to IndexNow API Protocol
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                cls.INDEXNOW_ENDPOINT,
                data=req_data,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "TrendBlogo-Indexer/2.0"
                }
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                code = resp.getcode()
                body = resp.read().decode("utf-8", errors="ignore")
                
                # IndexNow returns 200 (OK) or 202 (Accepted) on success
                is_success = code in (200, 202)
                if is_success:
                    overall_success = True

                log_entry = IndexingLog(
                    article_id=article.id,
                    url=article_url,
                    service="indexnow",
                    status="success" if is_success else "failed",
                    response_code=code,
                    response_body=body or "URL accepted for search engine indexing.",
                    error_message=None if is_success else f"HTTP {code}",
                    created_at=datetime.utcnow()
                )
                db.add(log_entry)
                results.append({"service": "indexnow", "success": is_success, "code": code})
        except Exception as e_idx:
            err_msg = str(e_idx)
            log_entry = IndexingLog(
                article_id=article.id,
                url=article_url,
                service="indexnow",
                status="failed",
                response_code=500,
                response_body=None,
                error_message=err_msg,
                created_at=datetime.utcnow()
            )
            db.add(log_entry)
            results.append({"service": "indexnow", "success": False, "error": err_msg})

        # 2. Ping Search Engine Sitemap Endpoint
        try:
            sitemap_url = f"{site_base}/sitemap.xml"
            ping_url = f"https://www.google.com/ping?sitemap={urllib.parse.quote(sitemap_url)}"
            req_ping = urllib.request.Request(ping_url, headers={"User-Agent": "TrendBlogo-Sitemap/2.0"})
            with urllib.request.urlopen(req_ping, timeout=10.0) as ping_resp:
                ping_code = ping_resp.getcode()
                ping_log = IndexingLog(
                    article_id=article.id,
                    url=sitemap_url,
                    service="google_sitemap_ping",
                    status="success" if ping_code == 200 else "submitted",
                    response_code=ping_code,
                    response_body="Google sitemap ping dispatched successfully.",
                    created_at=datetime.utcnow()
                )
                db.add(ping_log)
                results.append({"service": "google_sitemap_ping", "success": True, "code": ping_code})
        except Exception as e_ping:
            ping_log = IndexingLog(
                article_id=article.id,
                url=f"{site_base}/sitemap.xml",
                service="google_sitemap_ping",
                status="failed",
                error_message=str(e_ping),
                created_at=datetime.utcnow()
            )
            db.add(ping_log)
            results.append({"service": "google_sitemap_ping", "success": False, "error": str(e_ping)})

        # Update article model fields
        article.indexing_status = "submitted" if overall_success else "failed"
        article.indexing_requested_at = datetime.utcnow()
        article.indexing_service = "indexnow"
        article.indexing_response = json.dumps(results)
        db.commit()

        return {
            "success": overall_success,
            "article_id": article.id,
            "url": article_url,
            "results": results
        }

    @classmethod
    def retry_indexing_log(cls, db: Session, log_id: int) -> Dict[str, Any]:
        """
        Retries a specific failed indexing submission.
        """
        log = db.query(IndexingLog).filter(IndexingLog.id == log_id).first()
        if not log:
            return {"success": False, "error": "Log entry not found"}

        article = db.query(Article).filter(Article.id == log.article_id).first() if log.article_id else None
        if not article:
            return {"success": False, "error": "Associated article not found"}

        return cls.submit_article_url(db, article)
