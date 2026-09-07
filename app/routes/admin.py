import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, Response, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.article import Article, Category, Tag, ArticleTag
from app.models.media import Media
from app.models.links import InternalLink, ExternalLink
from app.models.automation import Keyword, GenerationJob, AIUsage
from app.models.inquiries import ContactMessage, GuestPostSubmission
from app.models.settings import SiteSetting, SystemLog, HomepageSection
from app.services.queue_runner import QueueRunner
from app.services.quality_control import QualityControl
from app.services.image_service import ImageService
from app.services.seo_engine import SEOEngine

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

import hmac
import hashlib
import time
import secrets

def create_signed_session_token(user: User) -> str:
    timestamp = int(time.time())
    payload = f"{user.id}:{user.email}:{timestamp}"
    sig = hmac.new(
        settings.APP_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{payload}:{sig}"

def verify_signed_session_token(token: str, max_age_seconds: int = 86400 * 14) -> Optional[dict]:
    if not token or ":" not in token:
        return None
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return None
        user_id_str, email, timestamp_str, sig = parts
        user_id = int(user_id_str)
        timestamp = int(timestamp_str)
        
        now = int(time.time())
        if now - timestamp > max_age_seconds or timestamp > now + 300:
            return None
            
        payload = f"{user_id}:{email}:{timestamp}"
        expected_sig = hmac.new(
            settings.APP_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        if secrets.compare_digest(sig, expected_sig):
            return {"user_id": user_id, "email": email}
        return None
    except Exception:
        return None

def get_current_admin(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("tb_session")
    if not token:
        return None
    
    # 1. Stateless cryptographic verification (immune to serverless instance isolation and cold boots)
    payload = verify_signed_session_token(token)
    if payload:
        user = db.query(User).filter(User.email == payload["email"], User.is_active == True).first()
        if not user:
            user = db.query(User).filter(User.id == payload["user_id"], User.is_active == True).first()
        if user:
            return user
            
    # 2. Database session token fallback
    user = db.query(User).filter(User.session_token == token, User.is_active == True).first()
    return user

def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    admin = get_current_admin(request, db)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/admin/login"}
        )
    return admin

def admin_context(request: Request, admin: User, db: Session, active_page: str) -> dict:
    unread_messages = db.query(ContactMessage).filter(ContactMessage.is_read == False).count()
    pending_guest_posts = db.query(GuestPostSubmission).filter(GuestPostSubmission.status == "pending").count()
    return {
        "request": request,
        "admin": admin,
        "active_page": active_page,
        "unread_messages": unread_messages,
        "pending_guest_posts": pending_guest_posts,
        "base_url": settings.BASE_URL
    }

# --- AUTH ROUTES ---

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin(request, db)
    if admin:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(request=request, name="admin/login.html", context={"request": request, "error": None})

@router.post("/login", response_class=HTMLResponse)
def do_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not user.verify_password(password.strip()):
        return templates.TemplateResponse(
            request=request,
            name="admin/login.html",
            context={
                "request": request,
                "error": "Invalid email or password. Please try again."
            }
        )

    # Generate stateless cryptographically signed token
    token = create_signed_session_token(user)
    try:
        user.session_token = token
        db.commit()
    except Exception:
        db.rollback()

    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie(
        key="tb_session",
        value=token,
        httponly=True,
        max_age=86400 * 14,
        samesite="lax",
        path="/",
        secure=settings.IS_VERCEL
    )
    return resp

@router.get("/logout")
def do_logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("tb_session")
    if token:
        try:
            user = db.query(User).filter(User.session_token == token).first()
            if user:
                user.session_token = None
                db.commit()
        except Exception:
            pass
    resp = RedirectResponse(url="/admin/login", status_code=303)
    resp.delete_cookie(key="tb_session", path="/")
    return resp

# --- DASHBOARD & ANALYTICS ---

@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ctx = admin_context(request, admin, db, "dashboard")
    
    total_articles = db.query(Article).count()
    published_count = db.query(Article).filter(Article.status == "published").count()
    draft_count = db.query(Article).filter(Article.status == "draft").count()
    scheduled_count = db.query(Article).filter(Article.status == "scheduled").count()
    
    total_keywords = db.query(Keyword).count()
    total_images = db.query(Media).count()
    failed_jobs = db.query(GenerationJob).filter(GenerationJob.status == "failed").count()
    total_api_calls = db.query(AIUsage).count()

    recent_articles = db.query(Article).order_by(desc(Article.created_at)).limit(6).all()
    recent_jobs = db.query(GenerationJob).order_by(desc(GenerationJob.created_at)).limit(5).all()
    categories = db.query(Category).all()

    ctx.update({
        "stats": {
            "total_articles": total_articles,
            "published": published_count,
            "drafts": draft_count,
            "scheduled": scheduled_count,
            "total_keywords": total_keywords,
            "total_images": total_images,
            "failed_jobs": failed_jobs,
            "api_usage": total_api_calls
        },
        "recent_articles": recent_articles,
        "recent_jobs": recent_jobs,
        "categories": categories
    })
    return templates.TemplateResponse(request=request, name="admin/dashboard.html", context=ctx)

@router.get("/generate", response_class=HTMLResponse)
def generate_wizard(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ctx = admin_context(request, admin, db, "generate")
    categories = db.query(Category).all()
    from app.services.ai_generator import AIGenerator
    cookie_key = request.cookies.get("tb_openai_key", "").strip()
    db_key = AIGenerator.get_active_api_key(db)
    active_key = cookie_key or db_key or ""

    # Auto sync cookie to db if needed
    if cookie_key and cookie_key.startswith("sk-") and not db_key:
        try:
            s = db.query(SiteSetting).filter(SiteSetting.key == "openai_api_key").first()
            if s:
                s.value = cookie_key
            else:
                db.add(SiteSetting(key="openai_api_key", value=cookie_key, category="api"))
            db.commit()
        except Exception:
            pass

    ctx.update({
        "categories": categories,
        "default_word_count": settings.DEFAULT_WORD_COUNT,
        "has_openai_key": bool(active_key and active_key.startswith("sk-")),
        "active_openai_key": active_key
    })
    return templates.TemplateResponse(request=request, name="admin/generate.html", context=ctx)

# --- AUTOMATION QUEUE ---

@router.get("/queue", response_class=HTMLResponse)
def queue_view(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ctx = admin_context(request, admin, db, "queue")
    jobs = db.query(GenerationJob).order_by(desc(GenerationJob.created_at)).all()
    keywords = db.query(Keyword).order_by(desc(Keyword.created_at)).limit(20).all()
    categories = db.query(Category).all()

    ctx.update({
        "jobs": jobs,
        "keywords": keywords,
        "categories": categories
    })
    return templates.TemplateResponse(request=request, name="admin/queue.html", context=ctx)

@router.post("/queue/batch-add")
def batch_add_keywords(
    request: Request,
    raw_keywords: str = Form(...),
    category_id: Optional[int] = Form(None),
    publish_mode: str = Form("published"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    lines = [line.strip() for line in raw_keywords.split("\n") if line.strip()]
    added_count = 0

    for kw_text in lines:
        existing_kw = db.query(Keyword).filter(Keyword.keyword == kw_text).first()
        if not existing_kw:
            existing_kw = Keyword(keyword=kw_text, status="queued")
            db.add(existing_kw)
            db.flush()

        job = GenerationJob(
            keyword=kw_text,
            category_id=category_id,
            status="pending",
            current_step="Queued for automated generation"
        )
        db.add(job)
        added_count += 1

    db.commit()
    return RedirectResponse(url="/admin/queue", status_code=303)

@router.post("/queue/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if job:
        job.status = "pending"
        job.progress = 0
        job.error_message = None
        job.current_step = "Reset for execution"
        db.commit()
        QueueRunner.execute_job(db, job.id)
    return RedirectResponse(url="/admin/queue", status_code=303)

@router.post("/queue/{job_id}/delete")
def delete_queue_job(job_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if job:
        db.delete(job)
        db.commit()
    return RedirectResponse(url="/admin/queue", status_code=303)

@router.post("/queue/clear")
def clear_queue(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    db.query(GenerationJob).delete()
    db.commit()
    return RedirectResponse(url="/admin/queue", status_code=303)


# --- ARTICLES MANAGER & EDITOR ---

@router.get("/articles", response_class=HTMLResponse)
def articles_list(
    request: Request,
    status_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    ctx = admin_context(request, admin, db, "articles")
    query = db.query(Article)
    if status_filter in ["published", "draft", "scheduled"]:
        query = query.filter(Article.status == status_filter)
    articles = query.order_by(desc(Article.created_at)).all()

    ctx.update({
        "articles": articles,
        "status_filter": status_filter or "all"
    })
    return templates.TemplateResponse(request=request, name="admin/articles.html", context=ctx)

@router.get("/articles/{article_id}/edit", response_class=HTMLResponse)
def edit_article(article_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    ctx = admin_context(request, admin, db, "articles")
    categories = db.query(Category).all()
    
    # Parse quality report
    qc_data = {}
    if article.quality_report:
        try:
            qc_data = json.loads(article.quality_report)
        except:
            qc_data = {}

    ctx.update({
        "article": article,
        "categories": categories,
        "qc_data": qc_data
    })
    return templates.TemplateResponse(request=request, name="admin/editor.html", context=ctx)

@router.post("/articles/{article_id}/edit")
def save_article(
    article_id: int,
    request: Request,
    title: str = Form(...),
    slug: str = Form(...),
    category_id: Optional[int] = Form(None),
    status: str = Form(...),
    content: str = Form(...),
    summary: Optional[str] = Form(None),
    seo_title: Optional[str] = Form(None),
    meta_description: Optional[str] = Form(None),
    featured_image_alt: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Enforce strict plain text on all H2-H5 headings (NO hyperlinks in headings)
    from app.services.link_engine import LinkEngine
    clean_content = LinkEngine.sanitize_headings(content)

    import markdown as md_lib
    html = md_lib.markdown(clean_content, extensions=["fenced_code", "tables", "toc", "sane_lists"])

    article.title = title.strip()
    article.slug = slug.strip().lower()
    article.category_id = category_id
    article.status = status
    article.content = clean_content
    article.html_content = html
    article.summary = summary.strip() if summary else ""
    article.seo_title = seo_title.strip() if seo_title else ""
    article.meta_description = meta_description.strip() if meta_description else ""
    if featured_image_alt:
        article.featured_image_alt = featured_image_alt.strip()

    # Re-run quality control audit
    qc_report = QualityControl.audit(
        keyword=article.primary_keyword,
        title=article.title,
        content=clean_content,
        featured_image=article.featured_image,
        in_content_images=[
            {"url": article.image_1_url, "alt": article.image_1_alt},
            {"url": article.image_2_url, "alt": article.image_2_alt},
            {"url": article.image_3_url, "alt": article.image_3_alt}
        ],
        internal_links_count=len(article.internal_links_out),
        external_links_count=len(article.external_links)
    )
    article.quality_score = qc_report["score"]
    article.quality_report = json.dumps(qc_report)
    article.schema_json = SEOEngine.generate_schema_json(article)

    db.commit()

    # Automatically crosslink internal links across all published articles
    try:
        LinkEngine.auto_crosslink_all_articles(db)
    except Exception as e_cross:
        pass
    
    # Auto-deploy to Vercel in background
    try:
        from app.services.auto_deploy import trigger_auto_deploy_background
        trigger_auto_deploy_background()
    except Exception:
        pass

    return RedirectResponse(url=f"/admin/articles/{article.id}/edit?saved=1", status_code=303)

@router.post("/articles/{article_id}/delete")
def delete_article(article_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if article:
        db.delete(article)
        db.commit()
        try:
            from app.services.auto_deploy import trigger_auto_deploy_background
            trigger_auto_deploy_background()
        except Exception:
            pass
    return RedirectResponse(url="/admin/articles?deleted=1", status_code=303)

@router.post("/deploy-now")
def deploy_now(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from app.services.auto_deploy import run_auto_deploy
    res = run_auto_deploy()
    return JSONResponse(res)

@router.post("/articles/{article_id}/duplicate")
def duplicate_article(article_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    orig = db.query(Article).filter(Article.id == article_id).first()
    if orig:
        new_slug = f"{orig.slug}-copy-{int(datetime.utcnow().timestamp())}"
        dup = Article(
            title=f"{orig.title} (Copy)",
            slug=new_slug,
            primary_keyword=orig.primary_keyword,
            secondary_keywords=orig.secondary_keywords,
            search_intent=orig.search_intent,
            template_type=orig.template_type,
            summary=orig.summary,
            content=orig.content,
            html_content=orig.html_content,
            featured_image=orig.featured_image,
            featured_image_alt=orig.featured_image_alt,
            featured_image_caption=orig.featured_image_caption,
            image_1_url=orig.image_1_url,
            image_1_alt=orig.image_1_alt,
            image_1_caption=orig.image_1_caption,
            image_2_url=orig.image_2_url,
            image_2_alt=orig.image_2_alt,
            image_2_caption=orig.image_2_caption,
            image_3_url=orig.image_3_url,
            image_3_alt=orig.image_3_alt,
            image_3_caption=orig.image_3_caption,
            category_id=orig.category_id,
            author_name=orig.author_name,
            status="draft",
            word_count=orig.word_count,
            reading_time=orig.reading_time,
            seo_title=f"{orig.seo_title} (Copy)",
            meta_description=orig.meta_description,
            quality_score=orig.quality_score,
            quality_report=orig.quality_report
        )
        db.add(dup)
        db.commit()
    return RedirectResponse(url="/admin/articles", status_code=303)

# --- MEDIA LIBRARY ---

@router.get("/media", response_class=HTMLResponse)
def media_library(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ctx = admin_context(request, admin, db, "media")
    media_items = db.query(Media).order_by(desc(Media.created_at)).all()
    ctx.update({
        "media_items": media_items
    })
    return templates.TemplateResponse(request=request, name="admin/media.html", context=ctx)

# --- LINK INTELLIGENCE ---

@router.get("/links", response_class=HTMLResponse)
def link_intelligence(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ctx = admin_context(request, admin, db, "links")
    internal_links = db.query(InternalLink).order_by(desc(InternalLink.created_at)).limit(50).all()
    external_links = db.query(ExternalLink).order_by(desc(ExternalLink.created_at)).limit(50).all()
    ctx.update({
        "internal_links": internal_links,
        "external_links": external_links
    })
    return templates.TemplateResponse(request=request, name="admin/links.html", context=ctx)

# --- INQUIRIES & GUEST POSTS ---

@router.get("/messages", response_class=HTMLResponse)
def messages_view(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ctx = admin_context(request, admin, db, "messages")
    messages = db.query(ContactMessage).order_by(desc(ContactMessage.created_at)).all()
    ctx.update({"messages": messages})
    return templates.TemplateResponse(request=request, name="admin/messages.html", context=ctx)

@router.post("/messages/{msg_id}/read")
def mark_message_read(msg_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    msg = db.query(ContactMessage).filter(ContactMessage.id == msg_id).first()
    if msg:
        msg.is_read = True
        db.commit()
    return RedirectResponse(url="/admin/messages", status_code=303)

@router.get("/guest-posts", response_class=HTMLResponse)
def guest_posts_view(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ctx = admin_context(request, admin, db, "guest_posts")
    submissions = db.query(GuestPostSubmission).order_by(desc(GuestPostSubmission.created_at)).all()
    ctx.update({"submissions": submissions})
    return templates.TemplateResponse(request=request, name="admin/guest_posts.html", context=ctx)

@router.post("/guest-posts/{post_id}/status")
def update_guest_post_status(
    post_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    sub = db.query(GuestPostSubmission).filter(GuestPostSubmission.id == post_id).first()
    if sub:
        sub.status = status
        db.commit()
    return RedirectResponse(url="/admin/guest-posts", status_code=303)

# --- SETTINGS & CONFIGURATION ---

@router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    ctx = admin_context(request, admin, db, "settings")
    settings_items = db.query(SiteSetting).all()
    settings_dict = {item.key: item.value for item in settings_items}
    cookie_key = request.cookies.get("tb_openai_key", "").strip()
    db_key = settings_dict.get("openai_api_key", "").strip()
    active_key = cookie_key or db_key or settings.OPENAI_API_KEY or ""
    has_key = bool(active_key and active_key.startswith("sk-"))

    # Auto sync cookie key to db in current container
    if cookie_key and cookie_key.startswith("sk-") and not db_key:
        try:
            s = db.query(SiteSetting).filter(SiteSetting.key == "openai_api_key").first()
            if s:
                s.value = cookie_key
            else:
                db.add(SiteSetting(key="openai_api_key", value=cookie_key, category="api"))
            db.commit()
            settings_dict["openai_api_key"] = cookie_key
        except Exception:
            pass

    ctx.update({
        "settings_dict": settings_dict,
        "env_has_openai_key": has_key,
        "active_key": active_key
    })
    return templates.TemplateResponse(request=request, name="admin/settings.html", context=ctx)

@router.post("/settings")
def save_settings(
    request: Request,
    site_name: str = Form(...),
    site_tagline: str = Form(...),
    site_description: str = Form(...),
    contact_email: str = Form(...),
    openai_api_key: str = Form(""),
    openai_model: str = Form("gpt-4o-mini"),
    image_provider: str = Form("auto"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    key_clean = openai_api_key.strip()
    updates = {
        "site_name": site_name,
        "site_tagline": site_tagline,
        "site_description": site_description,
        "contact_email": contact_email,
        "openai_api_key": key_clean,
        "openai_model": openai_model,
        "image_provider": image_provider
    }
    
    settings.OPENAI_API_KEY = key_clean
    settings.OPENAI_MODEL = openai_model
    settings.IMAGE_GENERATION_PROVIDER = image_provider

    for k, v in updates.items():
        s = db.query(SiteSetting).filter(SiteSetting.key == k).first()
        if s:
            s.value = v
        else:
            db.add(SiteSetting(key=k, value=v, category="api" if "openai" in k or "image" in k else "general"))
    
    db.commit()
    resp = RedirectResponse(url="/admin/settings?saved=1", status_code=303)
    if key_clean and key_clean.startswith("sk-"):
        resp.set_cookie(
            key="tb_openai_key",
            value=key_clean,
            max_age=31536000,
            path="/",
            httponly=False,
            samesite="lax",
            secure=settings.IS_VERCEL
        )
    elif not key_clean:
        resp.delete_cookie(key="tb_openai_key", path="/")
    return resp

@router.post("/api/test-openai-key")
async def test_openai_key(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    from fastapi.responses import JSONResponse
    try:
        body = await request.json()
        key_to_test = body.get("api_key", "").strip()
    except Exception:
        key_to_test = ""

    if not key_to_test:
        cookie_k = request.cookies.get("tb_openai_key", "").strip()
        s = db.query(SiteSetting).filter(SiteSetting.key == "openai_api_key").first()
        key_to_test = cookie_k or (s.value.strip() if s and s.value else settings.OPENAI_API_KEY)

    if not key_to_test or len(key_to_test) < 8:
        return JSONResponse({"success": False, "message": "API key cannot be empty (should start with sk-...)."})

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key_to_test, timeout=12.0)
        models_page = client.models.list()

        # Key is verified: sync to DB and persist in cookie
        try:
            s = db.query(SiteSetting).filter(SiteSetting.key == "openai_api_key").first()
            if s:
                s.value = key_to_test
            else:
                db.add(SiteSetting(key="openai_api_key", value=key_to_test, category="api"))
            db.commit()
        except Exception:
            pass

        res = JSONResponse({
            "success": True,
            "message": "OpenAI API Key is valid and successfully connected!"
        })
        res.set_cookie(
            key="tb_openai_key",
            value=key_to_test,
            max_age=31536000,
            path="/",
            httponly=False,
            samesite="lax",
            secure=settings.IS_VERCEL
        )
        return res
    except Exception as e:
        err_msg = str(e)
        if "Incorrect API key" in err_msg or "invalid_api_key" in err_msg:
            return JSONResponse({"success": False, "message": "Incorrect API key. Please check your OpenAI secret key."})
        elif "quota" in err_msg.lower():
            return JSONResponse({"success": False, "message": "Key is valid, but your OpenAI account has exceeded its credit quota."})
        return JSONResponse({"success": False, "message": f"OpenAI error: {err_msg[:120]}"})

# --- SYSTEM LOGS ---

@router.get("/logs", response_class=HTMLResponse)
def logs_view(
    request: Request,
    level: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    ctx = admin_context(request, admin, db, "logs")
    query = db.query(SystemLog)
    if level and level != "ALL":
        query = query.filter(SystemLog.level == level)
    logs = query.order_by(desc(SystemLog.created_at)).limit(100).all()

    ctx.update({
        "logs": logs,
        "selected_level": level or "ALL"
    })
    return templates.TemplateResponse(request=request, name="admin/logs.html", context=ctx)

@router.post("/logs/clear")
def clear_logs(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    db.query(SystemLog).delete()
    db.commit()
    return RedirectResponse(url="/admin/logs", status_code=303)


# --- HOMEPAGE SECTIONS MANAGEMENT ---

@router.get("/sections", response_class=HTMLResponse)
def sections_view(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    ctx = admin_context(request, admin, db, "sections")
    sections = db.query(HomepageSection).order_by(HomepageSection.sort_order).all()
    categories = db.query(Category).all()
    ctx.update({
        "title": "Homepage Sections Manager — TrendBlogo Admin",
        "sections": sections,
        "categories": categories
    })
    return templates.TemplateResponse(request=request, name="admin/sections.html", context=ctx)


@router.post("/sections/save")
async def sections_save(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    form = await request.form()
    sections = db.query(HomepageSection).all()
    for sec in sections:
        title_key = f"title_{sec.id}"
        subtitle_key = f"subtitle_{sec.id}"
        sort_key = f"sort_{sec.id}"
        enabled_key = f"enabled_{sec.id}"
        cat_key = f"cat_{sec.id}"
        
        if title_key in form:
            sec.title = str(form[title_key]).strip()
        if subtitle_key in form:
            sec.subtitle = str(form[subtitle_key]).strip()
        if sort_key in form:
            try:
                sec.sort_order = int(form[sort_key])
            except ValueError:
                pass
        sec.is_enabled = enabled_key in form
        if cat_key in form:
            sec.category_slug = str(form[cat_key]).strip() or None

    db.commit()
    return RedirectResponse(url="/admin/sections?saved=1", status_code=303)

