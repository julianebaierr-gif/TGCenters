import pytest
import base64
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.article import Article, Category
from app.services.link_engine import LinkEngine
from app.services.image_service import ImageService
from app.services.quality_control import QualityControl
from app.services.duplicate_checker import DuplicateChecker
from app.services.keyword_analyzer import KeywordAnalyzer
from app.services.ai_generator import AIGenerator

client = TestClient(app)


def test_heading_link_purity_sanitization():
    """
    CRITICAL RULE: Headings (H2-H5) must NEVER contain hyperlinks.
    """
    dirty_md = """# Main Title
## [Best AI Tools](https://example.com) for Automation
This is a body paragraph that can have a [valid body link](https://trendblogo.com).

### Key Features of <a href="http://badlink.com">Analytics Suite</a>
Another body sentence.

## Clean Heading Without Links
Clean content."""

    cleaned_md = LinkEngine.sanitize_headings(dirty_md)
    lines = cleaned_md.split("\n")
    
    # Check that H2 and H3 headings have no links
    h2_line = [l for l in lines if l.startswith("## ")][0]
    assert "[" not in h2_line
    assert "https://example.com" not in h2_line
    assert "Best AI Tools for Automation" in h2_line

    h3_line = [l for l in lines if l.startswith("### ")][0]
    assert "<a" not in h3_line
    assert "Analytics Suite" in h3_line

    # Verify body link was preserved
    assert "[valid body link](https://trendblogo.com)" in cleaned_md

def test_two_images_generation():
    """
    CRITICAL RULE: Exactly 1 featured image + 1 in-content image = 2 images total.
    Must require an OpenAI API Key, and when provided, produce 2 images via DALL-E/GPT-Image.
    """
    import base64
    from unittest.mock import patch, MagicMock
    sections = [
        {"h2": "Section One Overview", "h3_list": ["Subtopic A"]},
        {"h2": "Section Two Architecture", "h3_list": ["Subtopic B"]}
    ]

    # 1. Verify that without OpenAI API Key, it raises ValueError
    with patch.object(ImageService, "get_active_credentials", return_value=("", "auto")):
        with pytest.raises(ValueError, match="OpenAI API Key is required"):
            ImageService.create_article_images(
                keyword="automated seo tools",
                title="10 Best Automated SEO Tools for High-Growth Publications",
                outline_sections=sections,
                slug="test-automated-seo-tools"
            )

    # 2. Verify with mock OpenAI generation
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(b64_json=base64.b64encode(fake_png).decode("utf-8"))]

    with patch.object(ImageService, "get_active_credentials", return_value=("sk-proj-test1234567890", "openai")):
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.images.generate.return_value = mock_resp
            mock_openai_cls.return_value = mock_client

            images = ImageService.create_article_images(
                keyword="automated seo tools",
                title="10 Best Automated SEO Tools for High-Growth Publications",
                outline_sections=sections,
                slug="test-automated-seo-tools"
            )

            assert "featured" in images
            assert "image_1" in images
            assert images.get("featured") is not None
            assert images.get("image_1") is not None
            assert len(images["all_images"]) == 2

            for key in ["featured", "image_1"]:
                img = images[key]
                assert img["url"].startswith("/static/uploads/")
                assert img["alt"] != ""
                assert img["filename"].endswith(".png")

def test_anti_cannibalization_checker():
    db = SessionLocal()
    # Create temporary article to test collision detection
    art = Article(
        title="AI Content Automation Complete Guide",
        slug="test-ai-content-automation",
        primary_keyword="ai content automation",
        content="Comprehensive guide to AI content automation.",
        featured_image="/static/uploads/test.png",
        featured_image_alt="Test",
        status="published"
    )
    db.add(art)
    db.commit()

    try:
        # Test checking for an existing keyword
        result = DuplicateChecker.check(db, "ai content automation")
        assert result["has_collision"] is True
        assert result["risk_level"] in ["high", "moderate"]

        # Test checking for a unique new keyword
        unique_result = DuplicateChecker.check(db, "quantum cryptography for deep space satellites")
        assert unique_result["has_collision"] is False
        assert unique_result["risk_level"] == "none"
    finally:
        db.delete(art)
        db.commit()
        db.close()

def test_quality_control_audit():
    # Create a realistic 600+ word test article
    p1 = "Understanding modern cloud systems requires structured engineering discipline and strategic architectural foresight across all operational parameters. " * 15
    p2 = "Evaluating throughput, latency, and fault-tolerance boundaries allows engineering teams to eliminate bottlenecks before rolling out production workloads. " * 15
    p3 = "By establishing continuous telemetry monitoring, teams ensure high indexation velocity and resilient infrastructure uptime across distributed regions. " * 15
    valid_content = f"""# Test Title
## Foundations of Modern Cloud Systems
{p1}

## Implementation Metrics
{p2}

## Production Deployment Tactics
{p3}

## Frequently Asked Questions About Modern Cloud Systems
Q: What is key? A: Structured benchmarks.
"""

    report = QualityControl.audit(
        keyword="modern cloud systems",
        title="Mastering Modern Cloud Systems",
        content=valid_content,
        featured_image="/static/uploads/test-featured.svg",
        in_content_images=[
            {"url": "/img1.svg", "alt": "Alt 1"}
        ],
        internal_links_count=1,
        external_links_count=1
    )

    assert report["heading_links_found"] == 0
    assert report["score"] >= 80.0
    assert report["is_passed"] is True

def test_public_pages():
    # Home
    res = client.get("/")
    assert res.status_code == 200
    assert "TrendBlogo" in res.text
    assert "The Journal of Technology" in res.text or "TrendBlogo" in res.text

    # Blog list
    res = client.get("/blog")
    assert res.status_code == 200
    assert "Editorial Archives" in res.text or "Dispatches" in res.text


    # Informational & Legal Pages
    pages = ["/about", "/contact", "/guest-posting", "/privacy-policy", "/terms-and-conditions", "/disclaimer", "/cookie-policy", "/categories"]
    for p in pages:
        r = client.get(p)
        assert r.status_code == 200, f"Page {p} returned {r.status_code}"

    # Sitemap and Robots
    res_sitemap = client.get("/sitemap.xml")
    assert res_sitemap.status_code == 200
    assert "urlset" in res_sitemap.text

    res_robots = client.get("/robots.txt")
    assert res_robots.status_code == 200
    assert "Disallow: /admin" in res_robots.text

    res_rss = client.get("/rss.xml")
    assert res_rss.status_code == 200
    assert "<rss" in res_rss.text

def test_single_article_page():
    db = SessionLocal()
    # Create temporary published article
    art = Article(
        title="Sample Test Article for Single Page",
        slug="sample-test-article",
        primary_keyword="sample test article",
        content="## Overview\nThis is a sample test article.\n\n## Details\nMore detailed content here.",
        summary="Sample test article summary.",
        meta_description="Sample test article meta description.",
        featured_image="/static/uploads/sample-featured.png",
        featured_image_alt="Sample Featured Alt",
        status="published",
        reading_time=3,
        word_count=500,
        quality_score=95.0
    )
    db.add(art)
    db.commit()

    try:
        res = client.get(f"/blog/{art.slug}")
        assert res.status_code == 200
        assert art.title in res.text
        assert art.featured_image in res.text
        assert "Share Article" in res.text or "min read" in res.text
    finally:
        db.delete(art)
        db.commit()
        db.close()

def test_admin_auth_and_dashboard():
    # Unauthenticated access redirects to /admin/login
    res = client.get("/admin", follow_redirects=False)
    assert res.status_code in [302, 303, 307]
    assert "/admin/login" in res.headers.get("location", "")

    # Login
    res_login = client.post("/admin/login", data={"email": "admin@trendblogo.com", "password": "Admin123!"}, follow_redirects=False)
    assert res_login.status_code == 303
    cookies = res_login.cookies
    assert "tb_session" in cookies

    # Access dashboard with cookie
    res_dash = client.get("/admin", cookies=cookies)
    assert res_dash.status_code == 200
    assert "System Overview" in res_dash.text
    assert "Total Articles" in res_dash.text

def test_api_keyword_analyze_and_generate():
    # Test keyword analysis
    res_an = client.post("/api/keywords/analyze", json={"keyword": "best productivity tools"})
    assert res_an.status_code == 200
    data_an = res_an.json()
    assert "search_intent" in data_an
    assert "outline" in data_an

    # Verify article generation endpoint with mocked QueueRunner execution (protects user credits)
    from app.services.queue_runner import QueueRunner
    db = SessionLocal()
    fake_art = Article(
        title="Enterprise Workflow Automation",
        slug="test-mocked-article",
        primary_keyword="enterprise workflow automation",
        content="## Overview\nTest overview.",
        summary="Test summary.",
        featured_image="/static/uploads/test.png",
        featured_image_alt="Test Alt",
        status="published",
        reading_time=3,
        word_count=500,
        quality_score=95.0
    )
    db.add(fake_art)
    db.commit()
    art_id = fake_art.id
    try:
        with patch.object(QueueRunner, "execute_job", return_value={"success": True, "article_id": art_id}):
            res_gen = client.post("/api/articles/generate", json={
                "keyword": "enterprise workflow automation",
                "secondary_keywords": "scalability, cicd, devops",
                "tone": "informative",
                "target_word_count": 1200,
                "publish_mode": "published"
            })
            assert res_gen.status_code == 200
            data_gen = res_gen.json()
            assert data_gen.get("success") is True
            assert data_gen.get("article_id") == art_id
    finally:
        db.delete(fake_art)
        db.commit()
        db.close()

def test_auto_category_detection_and_resolution():
    db = SessionLocal()
    try:
        # 1. Health
        cat_health = KeywordAnalyzer.resolve_or_create_category(db, "intermittent fasting diet and longevity")
        assert cat_health.name == "Health"
        assert cat_health.slug == "health"

        # 2. Tech
        cat_tech = KeywordAnalyzer.resolve_or_create_category(db, "python async cloud backend architecture")
        assert cat_tech.name == "Tech"
        assert cat_tech.slug == "tech"

        # 3. News
        cat_news = KeywordAnalyzer.resolve_or_create_category(db, "breaking report on global inflation and market policy")
        assert cat_news.name == "News"
        assert cat_news.slug == "news"

        # 4. Lifestyle
        cat_life = KeywordAnalyzer.resolve_or_create_category(db, "minimalist remote home office design and routine")
        assert cat_life.name == "Lifestyle"
        assert cat_life.slug == "lifestyle"
    finally:
        db.close()

def test_guest_post_submission():
    res = client.post("/guest-posting", data={
        "author_name": "Test Contributor",
        "email": "contributor@example.com",
        "website": "https://contributor.io",
        "topic_category": "Tech",
        "proposed_title": "Novel Approaches to Vector Embeddings",
        "article_outline": "H2: Vector Spaces\nH3: Cosine Distance\nH2: Performance",
        "author_bio": "AI Engineer",
        "message": "Excited to share insights.",
        "agreed": "true"
    })
    assert res.status_code == 200
    assert "Proposal Submitted" in res.text or "has been received" in res.text

def test_contact_form_submission():
    res = client.post("/contact", data={
        "name": "Sarah Connor",
        "email": "sarah@resistance.org",
        "subject": "Platform Partnership",
        "message": "We would like to explore an enterprise content partnership."
    })
    assert res.status_code == 200
    assert "Message Received" in res.text or "Thank you" in res.text

def test_search_and_category_archives():
    res_search = client.get("/search?q=automation")
    assert res_search.status_code == 200
    assert "Results for" in res_search.text

    res_cat = client.get("/category/tech")
    assert res_cat.status_code == 200
    assert "Tech" in res_cat.text


def test_admin_full_workflow():
    # Login as admin
    res_login = client.post("/admin/login", data={"email": "admin@trendblogo.com", "password": "Admin123!"}, follow_redirects=False)
    cookies = res_login.cookies

    # Batch Add Keywords to Queue
    res_batch = client.post("/admin/queue/batch-add", data={
        "raw_keywords": "quantum machine learning\nedge computing architectures",
        "publish_mode": "draft"
    }, cookies=cookies, follow_redirects=False)
    assert res_batch.status_code == 303

    # Check Queue View
    res_queue = client.get("/admin/queue", cookies=cookies)
    assert res_queue.status_code == 200
    assert "quantum machine learning" in res_queue.text

    # Check Media View
    res_media = client.get("/admin/media", cookies=cookies)
    assert res_media.status_code == 200
    assert "Visual Assets Gallery" in res_media.text

    # Check Links View
    res_links = client.get("/admin/links", cookies=cookies)
    assert res_links.status_code == 200
    assert "Link Intelligence" in res_links.text

    # Check Guest Posts View
    res_gp = client.get("/admin/guest-posts", cookies=cookies)
    assert res_gp.status_code == 200
    assert "Test Contributor" in res_gp.text

    # Check Messages View
    res_msg = client.get("/admin/messages", cookies=cookies)
    assert res_msg.status_code == 200
    assert "Sarah Connor" in res_msg.text

    # Update Settings
    res_set = client.post("/admin/settings", data={
        "site_name": "TrendBlogo Enterprise",
        "site_tagline": "Autonomous Content Publishing Engine",
        "site_description": "Enterprise SEO publishing platform.",
        "contact_email": "editorial@trendblogo.com",
        "openai_model": "gpt-4o-mini",
        "image_provider": "auto"
    }, cookies=cookies, follow_redirects=False)
    assert res_set.status_code == 303

    # Check Logs View
    res_logs = client.get("/admin/logs", cookies=cookies)
    assert res_logs.status_code == 200
    assert "System &" in res_logs.text

def test_openai_api_key_configuration_and_tester():
    # Login as admin
    res_login = client.post("/admin/login", data={"email": "admin@trendblogo.com", "password": "Admin123!"}, follow_redirects=False)
    cookies = res_login.cookies

    # Test key endpoint with empty key
    res_empty = client.post("/admin/api/test-openai-key", json={"api_key": ""}, cookies=cookies)
    assert res_empty.status_code == 200
    data_empty = res_empty.json()
    assert data_empty["success"] is False
    assert "empty" in data_empty["message"].lower()

    # Save a custom OpenAI key and model via settings
    test_key = "sk-proj-test1234567890abcdefghijklmnopqrstuvwxyz"
    res_save = client.post("/admin/settings", data={
        "site_name": "TrendBlogo AI",
        "site_tagline": "AI Generated Content",
        "site_description": "Powered by OpenAI ChatGPT & DALL-E",
        "contact_email": "admin@trendblogo.com",
        "openai_api_key": test_key,
        "openai_model": "gpt-4o",
        "image_provider": "auto"
    }, cookies=cookies, follow_redirects=False)
    assert res_save.status_code == 303

    # Check that settings page displays the configured key
    res_settings = client.get("/admin/settings", cookies=cookies)
    assert res_settings.status_code == 200
    assert test_key in res_settings.text
    assert "API Key Active" in res_settings.text

    # Verify AIGenerator dynamically detects this active key
    from app.services.ai_generator import AIGenerator
    with SessionLocal() as db:
        resolved_key = AIGenerator.get_active_api_key(db)
        resolved_model = AIGenerator.get_active_model(db)
        assert resolved_key == test_key
        assert resolved_model == "gpt-4o"

    # Reset back to empty so no dummy key remains in database
    client.post("/admin/settings", data={
        "site_name": "TrendBlogo Enterprise",
        "site_tagline": "Autonomous Content Publishing Engine",
        "site_description": "Enterprise SEO publishing platform.",
        "contact_email": "editorial@trendblogo.com",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "image_provider": "auto"
    }, cookies=cookies, follow_redirects=False)

def test_cookie_and_payload_key_persistence():
    # Login as admin
    res_login = client.post("/admin/login", data={"email": "admin@trendblogo.com", "password": "Admin123!"}, follow_redirects=False)
    cookies = dict(res_login.cookies)

    test_key = "sk-proj-persistent1234567890abcdef"
    # 1. Save in settings -> check tb_openai_key cookie is set in response
    res_save = client.post("/admin/settings", data={
        "site_name": "TrendBlogo",
        "site_tagline": "AI Blog",
        "site_description": "SEO",
        "contact_email": "admin@trendblogo.com",
        "openai_api_key": test_key,
        "openai_model": "gpt-4o-mini",
        "image_provider": "auto"
    }, cookies=cookies, follow_redirects=False)
    assert res_save.status_code == 303
    assert "tb_openai_key" in res_save.cookies

    # 2. Access /admin/generate with that cookie -> active_openai_key is passed to template
    cookies["tb_openai_key"] = test_key
    res_gen = client.get("/admin/generate", cookies=cookies)
    assert res_gen.status_code == 200
    assert test_key in res_gen.text
    assert "Key Ready" in res_gen.text

    # 3. Clean up
    client.post("/admin/settings", data={
        "site_name": "TrendBlogo",
        "site_tagline": "AI Blog",
        "site_description": "SEO",
        "contact_email": "admin@trendblogo.com",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "image_provider": "auto"
    }, cookies=cookies, follow_redirects=False)


def test_tech_publication_and_modular_sections():
    # 1. Test new required policy & metadata pages
    res_editorial = client.get("/editorial-policy")
    assert res_editorial.status_code == 200
    assert "Editorial Policy" in res_editorial.text

    res_corrections = client.get("/corrections-policy")
    assert res_corrections.status_code == 200
    assert "Corrections" in res_corrections.text

    res_sitemap = client.get("/sitemap")
    assert res_sitemap.status_code == 200
    assert "Sitemap" in res_sitemap.text

    res_author = client.get("/author/alex-rivera")
    assert res_author.status_code == 200
    assert "Alex Rivera" in res_author.text

    # 2. Verify NO guest posting or DA 65+ callouts on homepage or base navigation
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "DA 65+" not in res_home.text
    assert "Write for Us" not in res_home.text
    assert "href=\"/admin\"" not in res_home.text  # Admin access concealed from public navigation

    # 3. Test Admin Sections Management
    res_login = client.post("/admin/login", data={"email": "admin@trendblogo.com", "password": "Admin123!"}, follow_redirects=False)
    cookies = dict(res_login.cookies)

    res_sections = client.get("/admin/sections", cookies=cookies)
    assert res_sections.status_code == 200
    assert "Homepage Sections Manager" in res_sections.text
    assert "featured" in res_sections.text

    # Test saving section changes
    res_save = client.post("/admin/sections/save", data={
        "title_1": "Top Cover Stories",
        "subtitle_1": "Primary editorial dispatches",
        "sort_1": "1",
        "enabled_1": "1"
    }, cookies=cookies, follow_redirects=False)
    assert res_save.status_code == 303

def test_automated_internal_and_external_linking():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    # Create two test articles
    art1 = Article(
        title="Comprehensive Running Gear Guide",
        slug="test-running-gear-guide",
        primary_keyword="running gear",
        featured_image="/static/uploads/test1.png",
        featured_image_alt="Test 1 Alt",
        content="## Proper Running Essentials\n\nInvesting in proper running gear ensures safety and endurance across all terrains.\n\nGood foot biomechanics and footwear support are vital.",
        html_content="<p>Content</p>",
        status="published"
    )
    art2 = Article(
        title="Ultimate Trail Shoes Review",
        slug="test-trail-shoes-review",
        primary_keyword="trail shoes",
        featured_image="/static/uploads/test2.png",
        featured_image_alt="Test 2 Alt",
        content="## Trail Performance\n\nSelecting durable trail shoes makes a huge difference on rugged mountain trails.\n\nEnsure you have high performance running gear before your run.",
        html_content="<p>Content</p>",
        status="published"
    )
    db.add(art1)
    db.add(art2)
    db.commit()

    try:
        # 1. Test dynamic external link resolution (no fixed list)
        sample_text = "Good foot biomechanics and footwear support are vital for long distance running."
        ext_md, ext_links = LinkEngine.inject_external_links(sample_text, "footwear")
        assert len(ext_links) > 0
        assert "footwear" in ext_links[0]["url"].lower() or "wikipedia.org" in ext_links[0]["url"]
        
        # Test in-content ChatGPT external citation extraction
        sample_with_chatgpt_link = "According to research from [TechCrunch Analysis](https://techcrunch.com/article), cloud scales fast."
        c_md, c_links = LinkEngine.inject_external_links(sample_with_chatgpt_link, "cloud computing")
        assert len(c_links) == 1
        assert c_links[0]["domain"] == "techcrunch.com"

        # 2. Test automated crosslinking between real articles
        links_created = LinkEngine.auto_crosslink_all_articles(db)
        assert links_created >= 1

        db.refresh(art1)
        db.refresh(art2)

        # art2 had 'running gear' which is art1's keyword -> art2 should link to art1
        assert f"/blog/{art1.slug}" in art2.content or f"/blog/{art2.slug}" in art1.content

        # Headings purity: guarantee headings have no links
        for line in art1.content.split("\n"):
            if line.startswith("#"):
                assert "[" not in line and "href" not in line
        for line in art2.content.split("\n"):
            if line.startswith("#"):
                assert "[" not in line and "href" not in line

    finally:
        db.close()

def test_six_point_requirements():
    """
    Test user requirements:
    1. Title: 40 to 55 characters strictly.
    2. Meta Description: 140 to 150 characters strictly.
    3. Outline: structured from H2 down to H5 with semantic keywords.
    4. Two images spec: exactly 2 images (1 featured + 1 in-article).
    """
    from app.services.seo_engine import SEOEngine
    from app.services.keyword_analyzer import KeywordAnalyzer
    from app.services.ai_generator import AIGenerator
    from app.services.image_service import ImageService

    # 1. Title length validation
    test_keywords = ["running shoes", "best laptops", "ai automation tools", "minimalist living"]
    for kw in test_keywords:
        t = AIGenerator._generate_title(kw, "informational", "ultimate_guide")
        assert 40 <= len(t) <= 55, f"Title '{t}' length {len(t)} not in [40, 55]"

    # 2. Meta description length validation
    for kw in test_keywords:
        meta = SEOEngine.generate_metadata(kw, "Running Shoes: Essential Guide & Full Review", "Sample summary", "test-slug", "/static/uploads/test.png")
        desc = meta["meta_description"]
        assert 140 <= len(desc) <= 150, f"Meta description '{desc}' length {len(desc)} not in [140, 150]"

    # 3. Outline H2 down to H5 with semantic keywords
    analysis = KeywordAnalyzer.analyze("running shoes")
    outline = analysis["outline"]
    assert len(outline) >= 3
    for sec in outline:
        assert "h2" in sec
        assert "h3_list" in sec
        assert "h4_list" in sec
        assert "h5_list" in sec
        assert "semantic_keywords" in sec
        assert len(sec["h3_list"]) > 0 or len(sec["h4_list"]) > 0

    # 4. Exactly 2 images spec
    prompts = ImageService.generate_image_prompts("running shoes", "Running Shoes: Essential Guide & Full Review", outline)
    assert len(prompts) == 2
    assert prompts[0]["type"] == "featured"
    assert prompts[1]["type"] == "in_article_1"






