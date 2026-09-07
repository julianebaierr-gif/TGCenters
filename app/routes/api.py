from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from app.database import get_db
from app.models.article import Article, Category
from app.models.automation import Keyword, GenerationJob
from app.services.keyword_analyzer import KeywordAnalyzer
from app.services.duplicate_checker import DuplicateChecker
from app.services.queue_runner import QueueRunner
from app.services.ai_generator import AIGenerator

router = APIRouter(prefix="/api")

from typing import Optional, List, Union, Any

class KeywordAnalyzeRequest(BaseModel):
    keyword: str
    secondary_keywords: Optional[List[str]] = None

class GenerateArticleRequest(BaseModel):
    keyword: str
    secondary_keywords: Optional[str] = ""
    category_id: Optional[Union[int, str]] = None
    tone: Optional[str] = "informative"
    language: Optional[str] = "English"
    target_word_count: Optional[int] = 1500
    template_type: Optional[str] = "ultimate_guide"
    publish_mode: Optional[str] = "published"
    scheduled_delay_hours: Optional[int] = 0
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None

@router.post("/keywords/analyze")
def api_analyze_keyword(req: KeywordAnalyzeRequest, db: Session = Depends(get_db)):
    if not req.keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    data = KeywordAnalyzer.analyze(req.keyword, req.secondary_keywords)
    resolved_cat = KeywordAnalyzer.resolve_or_create_category(db, req.keyword)
    data["suggested_category"] = {
        "id": resolved_cat.id,
        "name": resolved_cat.name,
        "slug": resolved_cat.slug,
        "color": resolved_cat.color
    }
    return data


@router.post("/keywords/check-duplicate")
def api_check_duplicate(req: KeywordAnalyzeRequest, db: Session = Depends(get_db)):
    if not req.keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    return DuplicateChecker.check(db, req.keyword)

@router.post("/articles/generate")
def api_generate_article(
    req: GenerateArticleRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    kw_clean = req.keyword.strip()
    if not kw_clean:
        raise HTTPException(status_code=400, detail="Keyword is required")

    # Resolve OpenAI API Key from payload, cookie, or DB
    resolved_key = (
        (req.openai_api_key or "").strip()
        or request.cookies.get("tb_openai_key", "").strip()
        or AIGenerator.get_active_api_key(db)
    )

    if resolved_key and resolved_key.startswith("sk-"):
        # Refresh persistent 1-year cookie
        response.set_cookie(
            key="tb_openai_key",
            value=resolved_key,
            max_age=31536000,
            path="/",
            httponly=False,
            samesite="lax",
            secure=True
        )

    # Resolve category if 'auto', None, or empty
    resolved_category_id = None
    if req.category_id and str(req.category_id).isdigit() and int(req.category_id) > 0:
        resolved_category_id = int(req.category_id)
    else:
        # Auto-detect or create category based on target keyword
        resolved_cat = KeywordAnalyzer.resolve_or_create_category(db, kw_clean)
        resolved_category_id = resolved_cat.id

    # Create GenerationJob
    job = GenerationJob(
        keyword=kw_clean,
        secondary_keywords=req.secondary_keywords,
        category_id=resolved_category_id,
        tone=req.tone,
        language=req.language,
        target_word_count=req.target_word_count,
        template_type=req.template_type,
        status="processing",
        current_step="Starting automated pipeline"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Execute synchronous generation pipeline
    result = QueueRunner.execute_job(
        db=db,
        job_id=job.id,
        publish_mode=req.publish_mode or "published",
        scheduled_delay_hours=req.scheduled_delay_hours or 0,
        api_key=resolved_key,
        model=req.openai_model
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Generation failed"))

    article = db.query(Article).filter(Article.id == result["article_id"]).first()
    return {
        "success": True,
        "article_id": article.id,
        "title": article.title,
        "slug": article.slug,
        "url": f"/blog/{article.slug}",
        "quality_score": article.quality_score,
        "word_count": article.word_count,
        "featured_image": article.featured_image
    }

@router.post("/queue/run-all")
def api_run_queue(db: Session = Depends(get_db)):
    pending_jobs = db.query(GenerationJob).filter(GenerationJob.status.in_(["pending", "failed"])).all()
    processed = []
    for job in pending_jobs:
        res = QueueRunner.execute_job(db, job.id)
        processed.append({"job_id": job.id, "keyword": job.keyword, "result": res})
    return {"processed_count": len(processed), "details": processed}

@router.get("/search/suggest")
def api_search_suggest(q: str = Query("", min_length=2), db: Session = Depends(get_db)):
    pattern = f"%{q.strip()}%"
    results = db.query(Article.id, Article.title, Article.slug, Article.featured_image).filter(
        Article.status == "published",
        or_(Article.title.ilike(pattern), Article.primary_keyword.ilike(pattern))
    ).limit(5).all()
    
    return [{"id": r.id, "title": r.title, "slug": r.slug, "image": r.featured_image} for r in results]


# =========================================================================
# AI AUTO-BLOGGING REST API (/api/admin/ai-blog/...)
# =========================================================================

class AddKeywordApiRequest(BaseModel):
    keyword: str
    language: Optional[str] = "English"
    country: Optional[str] = "United States"
    article_type: Optional[str] = "informational"
    target_word_count: Optional[int] = 2000
    publish_status: Optional[str] = "automatic"
    schedule_frequency: Optional[str] = "daily"
    max_articles: Optional[int] = 1
    priority: Optional[int] = 1

class GenerateRequestApi(BaseModel):
    keyword: str
    language: Optional[str] = "English"
    country: Optional[str] = "United States"
    article_type: Optional[str] = "informational"
    target_word_count: Optional[int] = 2000
    publish_mode: Optional[str] = "automatic"

@router.get("/admin/ai-blog/keywords")
def api_get_keywords(db: Session = Depends(get_db)):
    kws = db.query(Keyword).order_by(Keyword.priority.asc(), desc(Keyword.id)).all()
    return [{"id": k.id, "keyword": k.keyword, "language": k.language, "country": k.country, "status": k.status, "priority": k.priority, "articles_generated": k.articles_generated, "max_articles": k.max_articles, "schedule_frequency": k.schedule_frequency} for k in kws]

@router.post("/admin/ai-blog/keywords")
def api_add_keyword(req: AddKeywordApiRequest, db: Session = Depends(get_db)):
    kw_clean = req.keyword.strip()
    if not kw_clean:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    existing = db.query(Keyword).filter(Keyword.keyword.ilike(kw_clean)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Keyword already exists in queue")
    kw_item = Keyword(
        keyword=kw_clean,
        language=req.language or "English",
        country=req.country or "United States",
        article_type=req.article_type or "informational",
        search_intent=req.article_type or "informational",
        target_word_count=req.target_word_count or 2000,
        publish_status=req.publish_status or "automatic",
        schedule_frequency=req.schedule_frequency or "daily",
        max_articles=req.max_articles or 1,
        priority=req.priority or 1,
        status="pending"
    )
    db.add(kw_item)
    db.commit()
    db.refresh(kw_item)
    return {"success": True, "keyword": {"id": kw_item.id, "keyword": kw_item.keyword, "status": kw_item.status}}

@router.post("/admin/ai-blog/generate")
def api_direct_generate(req: GenerateRequestApi, db: Session = Depends(get_db)):
    from app.services.auto_scheduler import AutoSchedulerService
    kw = db.query(Keyword).filter(Keyword.keyword.ilike(req.keyword.strip())).first()
    if not kw:
        kw = Keyword(
            keyword=req.keyword.strip(),
            language=req.language or "English",
            country=req.country or "United States",
            article_type=req.article_type or "informational",
            target_word_count=req.target_word_count or 2000,
            publish_status=req.publish_mode or "automatic",
            status="pending"
        )
        db.add(kw)
        db.commit()
        db.refresh(kw)

    kw.priority = 0
    kw.status = "pending"
    db.commit()
    result = AutoSchedulerService.process_next_keyword(db, force=True)
    return result

@router.post("/admin/ai-blog/generate-image")
def api_generate_image(payload: dict, db: Session = Depends(get_db)):
    from app.services.ai_image_service import AIImageService
    keyword = payload.get("keyword", "")
    title = payload.get("title", keyword.title())
    slug = payload.get("slug", "test-image")
    prompt = payload.get("prompt")
    language = payload.get("language", "English")
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required")
    res = AIImageService.generate_featured_image(keyword=keyword, title=title, slug=slug, image_prompt=prompt, language=language, db=db, allow_fallback=True)
    return res

@router.get("/admin/ai-blog/jobs")
def api_get_jobs(limit: int = 50, db: Session = Depends(get_db)):
    jobs = db.query(GenerationJob).order_by(desc(GenerationJob.created_at)).limit(limit).all()
    return [{"id": j.id, "keyword": j.keyword, "language": j.language, "status": j.status, "current_step": j.current_step, "progress": j.progress, "error": j.error_message, "result_article_id": j.result_article_id, "created_at": j.created_at.isoformat() if j.created_at else None} for j in jobs]

@router.get("/admin/ai-blog/articles")
def api_get_ai_articles(limit: int = 50, db: Session = Depends(get_db)):
    articles = db.query(Article).filter(Article.ai_generated == True).order_by(desc(Article.created_at)).limit(limit).all()
    return [{"id": a.id, "title": a.title, "slug": a.slug, "language": a.language, "status": a.status, "word_count": a.word_count, "quality_score": a.quality_score, "featured_image": a.featured_image, "indexing_status": a.indexing_status, "created_at": a.created_at.isoformat() if a.created_at else None} for a in articles]

@router.post("/admin/ai-blog/articles/{article_id}/publish")
def api_publish_article(article_id: int, db: Session = Depends(get_db)):
    from app.services.indexing_service import IndexingService
    from datetime import datetime
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.status = "published"
    article.published_at = datetime.utcnow()
    db.commit()
    try:
        IndexingService.submit_article_url(db, article)
    except Exception:
        pass
    return {"success": True, "id": article.id, "status": "published"}

@router.post("/admin/ai-blog/articles/{article_id}/regenerate-image")
def api_regenerate_image(article_id: int, db: Session = Depends(get_db)):
    from app.services.ai_image_service import AIImageService
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    img_res = AIImageService.generate_featured_image(
        keyword=article.primary_keyword,
        title=article.title,
        slug=f"{article.slug}-new",
        language=article.language or "English",
        db=db,
        allow_fallback=True
    )
    article.featured_image = img_res["url"]
    article.featured_image_alt = img_res.get("alt", article.title)
    db.commit()
    return {"success": True, "featured_image": article.featured_image}

@router.post("/admin/ai-blog/articles/{article_id}/index")
def api_index_article(article_id: int, db: Session = Depends(get_db)):
    from app.services.indexing_service import IndexingService
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    res = IndexingService.submit_article_url(db, article)
    return res

@router.get("/admin/ai-blog/logs")
def api_get_logs(limit: int = 50, db: Session = Depends(get_db)):
    from app.models.settings import SystemLog
    logs = db.query(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit).all()
    return [{"id": l.id, "level": l.level, "source": l.source, "message": l.message, "details": l.details, "created_at": l.created_at.isoformat() if l.created_at else None} for l in logs]

@router.get("/admin/ai-blog/settings")
def api_get_settings(db: Session = Depends(get_db)):
    from app.services.ai_content_service import AIContentService
    from app.services.ai_image_service import AIImageService
    from app.services.auto_scheduler import AutoSchedulerService
    key = AIContentService.get_api_key(db)
    masked_key = f"{key[:7]}...{key[-4:]}" if key and len(key) > 8 else "Not configured"
    return {
        "api_key_configured": bool(key and key.startswith("sk-")),
        "masked_api_key": masked_key,
        "text_model": AIContentService.get_model(db),
        "image_model": AIImageService.get_image_model(db),
        "daily_limit": AutoSchedulerService.get_setting_int(db, "daily_article_limit", 5),
        "publish_frequency": AutoSchedulerService.get_setting_str(db, "publish_frequency", "daily"),
        "timezone": AutoSchedulerService.get_setting_str(db, "timezone", "UTC")
    }

@router.api_route("/admin/ai-blog/cron-run", methods=["GET", "POST"])
def api_cron_run(db: Session = Depends(get_db)):
    """
    Dedicated endpoint for Vercel Cron and external job trigger.
    Processes the next scheduled keyword safely in serverless execution.
    """
    from app.services.auto_scheduler import AutoSchedulerService
    enabled = AutoSchedulerService.get_setting_str(db, "auto_scheduler_enabled", "true").lower() == "true"
    if not enabled:
        return {"status": "skipped", "message": "Auto-scheduler is currently paused in settings."}
    res = AutoSchedulerService.process_next_keyword(db, force=False)
    return {"status": "ok", "result": res or {}}
