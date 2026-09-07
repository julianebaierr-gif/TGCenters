import pytest
import os
import json
from datetime import datetime
from starlette.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.database import SessionLocal, engine, Base
from app.models.article import Article, Category
from app.models.automation import Keyword, GenerationJob
from app.models.settings import SiteSetting, IndexingLog
from app.models.user import User
from app.services.ai_content_service import AIContentService, SUPPORTED_LANGUAGES
from app.services.content_validator import ContentValidator
from app.services.ai_image_service import AIImageService
from app.services.indexing_service import IndexingService
from app.services.auto_scheduler import AutoSchedulerService
from app.routes.admin import create_signed_session_token

client = TestClient(app)

def get_admin_session_cookie(db: Session):
    admin = db.query(User).filter(User.is_active == True).first()
    if not admin:
        import hashlib
        admin = User(
            name="Admin Test",
            email="admintest@trendblogo.com",
            password_hash=hashlib.sha256("Admin123!".encode()).hexdigest(),
            role="admin",
            is_active=True
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return create_signed_session_token(admin)

def test_database_schema_and_models():
    """Verify all extended columns and tables exist in the database."""
    with SessionLocal() as db:
        # Check Article columns
        art = Article(
            title="Test AI Article Schema",
            slug="test-ai-article-schema",
            primary_keyword="schema test",
            language="Urdu",
            content="# Title\n\nContent body...",
            featured_image="/static/uploads/test.png",
            featured_image_alt="Test alt",
            ai_generated=True,
            ai_model="gpt-4o-mini",
            image_model="dall-e-3",
            indexing_status="submitted"
        )
        db.add(art)
        db.commit()
        db.refresh(art)
        assert art.language == "Urdu"
        assert art.ai_generated is True
        assert art.ai_model == "gpt-4o-mini"
        assert art.indexing_status == "submitted"

        # Check Keyword columns
        kw = Keyword(
            keyword="test schema keyword",
            language="Hindi",
            country="India",
            article_type="commercial",
            target_word_count=2500,
            publish_status="automatic",
            schedule_frequency="hourly",
            priority=1,
            status="pending"
        )
        db.add(kw)
        db.commit()
        db.refresh(kw)
        assert kw.language == "Hindi"
        assert kw.country == "India"
        assert kw.target_word_count == 2500
        assert kw.status == "pending"

        # Check IndexingLog table
        log = IndexingLog(
            article_id=art.id,
            url=f"http://localhost:8000/blog/{art.slug}",
            service="indexnow",
            status="success",
            response_code=200
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        assert log.id is not None
        assert log.service == "indexnow"

        # Clean up
        db.delete(log)
        db.delete(kw)
        db.delete(art)
        db.commit()

def test_plain_text_heading_enforcement():
    """Verify strict plain-text headings rule (Zero heading links rule)."""
    dirty_md = """# [Main Heading](https://example.com)
Some paragraph here with [valid inline link](https://valid.com).

## Overview of [Technology Domain](https://example.com/tech)
Paragraph text under overview.

### <a href="https://example.com">Sub Topic Link</a>
Another paragraph.
"""
    cleaned = AIContentService.enforce_plain_text_headings(dirty_md)
    lines = cleaned.split("\n")
    # Headings must not contain hyperlinks
    assert "[Main Heading]" not in lines[0]
    assert "Main Heading" in lines[0]
    assert "Overview of Technology Domain" in lines[3]
    assert "<a href" not in lines[6]
    assert "Sub Topic Link" in lines[6]
    # Inline links in regular paragraphs must be preserved!
    assert "[valid inline link](https://valid.com)" in cleaned

def test_content_validator_rules():
    """Verify pre-publishing validation catches errors and passes valid articles."""
    with SessionLocal() as db:
        # 1. Invalid: Empty section & short word count
        res_invalid = ContentValidator.validate(
            db=db,
            title="Short",
            slug="short",
            meta_description="Too short",
            content_markdown="# Heading\n\n## Empty Section\n\n",
            content_html="<p>Short</p>",
            keyword="gaming laptops",
            featured_image_url="",
            target_word_count=1500
        )
        assert res_invalid["is_valid"] is False
        assert len(res_invalid["errors"]) > 0

        # 2. Valid article
        body_words = " ".join(["gaming", "laptop", "performance", "review", "budget"] * 200)
        valid_md = f"""# The Best Gaming Laptops Under Budget Review

In modern PC gaming, finding the ideal balance of GPU performance and thermal efficiency is essential for budget-conscious players.

## Top Performance Hardware Analysis

When selecting gaming laptops under a strict budget, buyers must analyze display refresh rates and cooling architectures. {body_words}

### Thermal Management Considerations

Effective cooling ensures components maintain clock speeds during extended sessions.

## Frequently Asked Questions

### Which GPU is best for budget laptops?
Modern entry-level graphics cards offer high frame rates at 1080p resolution.

## Final Verdict and Summary
Investing in balanced specs delivers maximum gaming value.
"""
        res_valid = ContentValidator.validate(
            db=db,
            title="The Best Gaming Laptops Under Budget Review Complete",
            slug="best-gaming-laptops-budget-review-test",
            meta_description="Discover our comprehensive, hands-on review and benchmarks of the best budget gaming laptops tested for real-world performance.",
            content_markdown=valid_md,
            content_html="<div>" + valid_md + "</div>",
            keyword="gaming laptops",
            featured_image_url="/static/uploads/test.png",
            target_word_count=1000
        )
        assert res_valid["is_valid"] is True
        assert res_valid["score"] >= 80

def test_sitemap_and_robots_dynamic_generation():
    """Verify /sitemap.xml dynamically includes published articles and excludes drafts."""
    with SessionLocal() as db:
        # Clean up any leftover test slugs if present
        ts = int(datetime.utcnow().timestamp())
        pub_slug = f"published-sitemap-art-{ts}"
        draft_slug = f"draft-sitemap-art-{ts}"

        # Create one published article and one draft article
        pub_art = Article(
            title="Published Dynamic Sitemap Article",
            slug=pub_slug,
            primary_keyword="sitemap test",
            status="published",
            content="Content",
            featured_image="/static/uploads/test.png",
            featured_image_alt="Test"
        )
        draft_art = Article(
            title="Draft Secret Article Should Not Appear",
            slug=draft_slug,
            primary_keyword="draft test",
            status="draft",
            content="Content",
            featured_image="/static/uploads/test.png",
            featured_image_alt="Test"
        )
        db.add(pub_art)
        db.add(draft_art)
        db.commit()

        # Fetch sitemap.xml
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        content = resp.text
        assert pub_slug in content
        assert draft_slug not in content

        # Fetch robots.txt
        resp_robots = client.get("/robots.txt")
        assert resp_robots.status_code == 200
        assert "Sitemap:" in resp_robots.text
        assert "Disallow: /admin" in resp_robots.text

        # Clean up
        db.delete(pub_art)
        db.delete(draft_art)
        db.commit()

def test_indexnow_verification_route():
    """Verify IndexNow host verification key endpoint /{key}.txt."""
    key = IndexingService.get_indexnow_key()
    resp = client.get(f"/{key}.txt")
    assert resp.status_code == 200
    assert resp.text.strip() == key

def test_admin_ai_blog_page_and_security():
    """Verify /admin/ai-blog renders all tabs and NEVER exposes raw API keys."""
    with SessionLocal() as db:
        token = get_admin_session_cookie(db)
        client.cookies.set("tb_session", token)

        resp = client.get("/admin/ai-blog")
        assert resp.status_code == 200
        html = resp.text

        # Verify main tabs are present
        assert "AI Autonomous Publishing Engine" in html
        assert "Dashboard" in html
        assert "AI Generator" in html
        assert "Keywords" in html
        assert "Content Queue" in html
        assert "Published" in html
        assert "Failed Jobs" in html
        assert "History" in html
        assert "Settings & Limits" in html
        assert "OpenAI API" in html
        assert "SEO & Indexing" in html

        # Verify SECURITY: Raw sk-proj- API key must NEVER be printed in HTML
        raw_key = AIContentService.get_api_key(db)
        if raw_key and len(raw_key) > 20:
            assert raw_key not in html  # Full key must never leak
            assert "sk-..." in html or "..." in html  # Only masked key allowed

def test_api_endpoints_ai_blog():
    """Verify JSON REST API endpoints under /api/admin/ai-blog/..."""
    with SessionLocal() as db:
        token = get_admin_session_cookie(db)
        client.cookies.set("tb_session", token)

        # GET settings
        resp_settings = client.get("/api/admin/ai-blog/settings")
        assert resp_settings.status_code == 200
        data = resp_settings.json()
        assert data["api_key_configured"] is True
        assert "masked_api_key" in data
        assert "sk-proj-3rSR" not in json.dumps(data) # Key is masked

        # POST add keyword via API
        test_kw = f"test-api-keyword-{int(datetime.utcnow().timestamp())}"
        resp_kw = client.post("/api/admin/ai-blog/keywords", json={
            "keyword": test_kw,
            "language": "French",
            "country": "France",
            "article_type": "informational",
            "target_word_count": 1800,
            "publish_status": "automatic"
        })
        assert resp_kw.status_code == 200
        assert resp_kw.json()["success"] is True

        # GET keywords
        resp_list = client.get("/api/admin/ai-blog/keywords")
        assert resp_list.status_code == 200
        kws = resp_list.json()
        assert any(k["keyword"] == test_kw for k in kws)

        # Clean up added keyword
        kw_rec = db.query(Keyword).filter(Keyword.keyword == test_kw).first()
        if kw_rec:
            db.delete(kw_rec)
            db.commit()

def test_auto_scheduler_daily_limit():
    """Verify AutoScheduler halts when daily article limit is reached."""
    with SessionLocal() as db:
        # Set daily limit to 0 temporarily
        limit_setting = db.query(SiteSetting).filter(SiteSetting.key == "daily_article_limit").first()
        orig_val = limit_setting.value if limit_setting else "5"
        if not limit_setting:
            limit_setting = SiteSetting(key="daily_article_limit", value="0", category="ai_blog")
            db.add(limit_setting)
        else:
            limit_setting.value = "0"
        db.commit()

        res = AutoSchedulerService.process_next_keyword(db, force=False)
        assert res["status"] == "limit_reached"
        assert "Daily publishing limit" in res["message"]

        # Restore setting
        limit_setting.value = orig_val
        db.commit()
