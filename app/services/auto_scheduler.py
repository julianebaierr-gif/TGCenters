import os
import time
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.config import settings
from app.database import SessionLocal
from app.models.article import Article, Category
from app.models.automation import Keyword, GenerationJob
from app.models.settings import SiteSetting, SystemLog
from app.models.media import Media
from app.services.ai_content_service import AIContentService
from app.services.ai_image_service import AIImageService
from app.services.content_validator import ContentValidator
from app.services.indexing_service import IndexingService
from app.services.seo_engine import SEOEngine
from app.services.link_engine import LinkEngine

class AutoSchedulerService:
    """
    Autonomous Background Scheduler and Content Publishing Engine.
    Runs 24/7 independently of admin browser sessions.
    Executes queued keywords, adheres to daily article limits, validates content quality,
    auto-publishes, and submits URLs to search engine indexing protocols.
    """

    _running = False
    _lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None

    @classmethod
    def get_setting_int(cls, db: Session, key: str, default: int) -> int:
        s = db.query(SiteSetting).filter(SiteSetting.key == key).first()
        if s and s.value and s.value.isdigit():
            return int(s.value)
        return default

    @classmethod
    def get_setting_str(cls, db: Session, key: str, default: str) -> str:
        s = db.query(SiteSetting).filter(SiteSetting.key == key).first()
        if s and s.value:
            return s.value.strip()
        return default

    @classmethod
    def get_today_published_count(cls, db: Session) -> int:
        start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return db.query(Article).filter(
            Article.created_at >= start_of_day,
            Article.ai_generated == True
        ).count()

    @classmethod
    def calculate_next_schedule(cls, frequency: str) -> datetime:
        now = datetime.utcnow()
        freq = frequency.lower().strip()
        if freq in ("hourly", "1_hour"):
            return now + timedelta(hours=1)
        elif freq in ("3_hours", "3 hours", "every 3 hours"):
            return now + timedelta(hours=3)
        elif freq in ("6_hours", "6 hours", "every 6 hours"):
            return now + timedelta(hours=6)
        elif freq in ("12_hours", "12 hours"):
            return now + timedelta(hours=12)
        else:
            # Default daily
            return now + timedelta(days=1)

    @classmethod
    def process_next_keyword(cls, db: Session, force: bool = False) -> Dict[str, Any]:
        """
        Picks the next prioritized, active keyword and executes the complete pipeline:
        Keyword -> AI Article -> AI Image -> SEO -> Validation -> Database -> Auto Publish -> Sitemap -> Indexing -> Logging
        """
        # 1. Check daily publishing limit
        daily_limit = cls.get_setting_int(db, "daily_article_limit", 5)
        today_count = cls.get_today_published_count(db)

        if not force and today_count >= daily_limit:
            return {
                "status": "limit_reached",
                "message": f"Daily publishing limit ({today_count}/{daily_limit}) reached for today."
            }

        # 2. Pick next active keyword
        now = datetime.utcnow()
        query = db.query(Keyword).filter(
            Keyword.is_paused == 0,
            Keyword.status.in_(["pending", "processing"])
        )

        if not force:
            # Respect schedule if set
            query = query.filter(
                (Keyword.next_scheduled_at == None) | (Keyword.next_scheduled_at <= now)
            )

        keyword_obj = query.order_by(Keyword.priority.asc(), Keyword.id.asc()).first()
        if not keyword_obj:
            return {"status": "idle", "message": "No active keywords pending in queue."}

        # Mark as processing
        keyword_obj.status = "processing"
        keyword_obj.last_generated_at = now
        db.commit()

        # Create or update generation job
        job = GenerationJob(
            keyword=keyword_obj.keyword,
            language=keyword_obj.language or "English",
            country=keyword_obj.country or "United States",
            target_word_count=keyword_obj.target_word_count or 2000,
            status="generating",
            current_step="Step 1/5: Generating AI Article Content",
            progress=20,
            publish_mode=keyword_obj.publish_status or "automatic"
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        try:
            # Resolve or create category
            cat_name = "Technology"
            category = None
            if keyword_obj.article_type:
                cat_slug = "technology"
                category = db.query(Category).first()
                if category:
                    cat_name = category.name

            # Step 1: AI Content Generation directly in selected language
            job.current_step = f"Generating article natively in {keyword_obj.language}"
            job.progress = 30
            db.commit()

            generated = AIContentService.generate_article_pipeline(
                keyword=keyword_obj.keyword,
                language=keyword_obj.language or "English",
                country=keyword_obj.country or "United States",
                article_type=keyword_obj.article_type or "informational",
                target_word_count=keyword_obj.target_word_count or 2000,
                category_name=cat_name,
                db=db
            )

            # Ensure unique slug
            slug = generated["slug"]
            base_slug = slug
            counter = 2
            while db.query(Article).filter(Article.slug == slug).first():
                slug = f"{base_slug}-{counter}"
                counter += 1

            # Step 2: AI Image Generation
            job.status = "image_generating"
            job.current_step = "Step 2/5: Generating and persisting featured visual asset"
            job.progress = 60
            db.commit()

            image_res = AIImageService.generate_featured_image(
                keyword=keyword_obj.keyword,
                title=generated["title"],
                slug=slug,
                image_prompt=generated.get("image_prompt"),
                language=keyword_obj.language or "English",
                alt_text=generated.get("image_alt_text"),
                caption=generated.get("image_caption"),
                db=db,
                allow_fallback=True
            )

            featured_image_url = image_res["url"]

            # Step 3: Content Validation
            job.status = "validating"
            job.current_step = "Step 3/5: Validating content quality and SEO completeness"
            job.progress = 80
            db.commit()

            val_result = ContentValidator.validate(
                db=db,
                title=generated["title"],
                slug=slug,
                meta_description=generated["meta_description"],
                content_markdown=generated["markdown"],
                content_html=generated["html"],
                keyword=keyword_obj.keyword,
                featured_image_url=featured_image_url,
                target_word_count=keyword_obj.target_word_count or 2000
            )

            if not val_result["is_valid"]:
                err_str = "; ".join(val_result["errors"])
                job.status = "failed"
                job.error_message = f"Validation failed: {err_str}"
                job.validation_errors = err_str
                job.current_step = "Failed during pre-publishing validation"
                keyword_obj.status = "failed"
                db.commit()
                return {"status": "failed", "error": err_str, "job_id": job.id}

            # Step 4: Database Persistence & Publishing
            job.status = "publishing"
            job.current_step = "Step 4/5: Saving article to database and publishing"
            job.progress = 90
            db.commit()

            is_auto = (keyword_obj.publish_status == "automatic")
            article_status = "published" if is_auto else ("draft" if keyword_obj.publish_status == "draft" else "scheduled")

            article = Article(
                title=generated["title"],
                slug=slug,
                primary_keyword=keyword_obj.keyword,
                focus_keyword=keyword_obj.keyword,
                secondary_keywords=", ".join(generated.get("secondary_keywords", [])),
                search_intent=keyword_obj.article_type or "informational",
                summary=generated["meta_description"],
                content=generated["markdown"],
                html_content=generated["html"],
                featured_image=featured_image_url,
                featured_image_alt=image_res.get("alt", generated["title"]),
                featured_image_caption=image_res.get("caption", ""),
                category_id=category.id if category else None,
                author_name="Editorial Team",
                author_slug="editorial-team",
                status=article_status,
                published_at=now if article_status == "published" else None,
                word_count=generated["word_count"],
                reading_time=generated["reading_time"],
                seo_title=generated.get("meta_title", generated["title"]),
                meta_description=generated["meta_description"],
                canonical_url=f"{settings.BASE_URL}/blog/{slug}",
                og_title=generated.get("meta_title", generated["title"]),
                og_description=generated["meta_description"],
                quality_score=val_result["score"],
                language=keyword_obj.language or "English",
                ai_generated=True,
                ai_model=generated.get("model_used", "gpt-4o-mini"),
                image_model=image_res.get("model", "dall-e-3")
            )
            db.add(article)
            db.flush()

            # Generate Schema.org structured data
            article.schema_json = SEOEngine.generate_schema_json(article)

            # Record media asset
            img_filename = image_res.get("filename", f"{slug}-featured.png")
            img_filepath = image_res.get("file_path", str(settings.UPLOADS_DIR / img_filename))
            media_item = Media(
                filename=img_filename,
                file_path=img_filepath,
                url=featured_image_url,
                media_type="image/png" if featured_image_url.endswith(".png") else "image/svg+xml",
                alt_text=image_res.get("alt", article.title),
                caption=image_res.get("caption", ""),
                prompt=image_res.get("prompt", ""),
                article_id=article.id
            )
            db.add(media_item)

            # Update Keyword metadata and schedule
            keyword_obj.article_id = article.id
            keyword_obj.articles_generated = (keyword_obj.articles_generated or 0) + 1
            if keyword_obj.articles_generated >= (keyword_obj.max_articles or 1):
                keyword_obj.status = "completed"
            else:
                keyword_obj.status = "pending"
                keyword_obj.next_scheduled_at = cls.calculate_next_schedule(
                    keyword_obj.schedule_frequency or "daily"
                )

            # Update Job Record
            job.status = "published" if article_status == "published" else "completed"
            job.progress = 100
            job.result_article_id = article.id
            job.current_step = "Article published and live!"
            job.logs = f"Article '{article.title}' successfully generated ({article.word_count} words, score: {val_result['score']})."
            db.commit()

            # Step 5: Search Engine Indexing Submission
            if article_status == "published":
                try:
                    IndexingService.submit_article_url(db, article)
                except Exception as e_idx:
                    pass

            # Log to system audit logs
            sys_log = SystemLog(
                level="SUCCESS",
                source="AI_AUTO_BLOGGER",
                message=f"Auto-published article for keyword '{keyword_obj.keyword}' in {keyword_obj.language}",
                details=f"ID: {article.id}, Slug: {article.slug}, Words: {article.word_count}"
            )
            db.add(sys_log)
            db.commit()

            return {
                "status": "success",
                "article_id": article.id,
                "title": article.title,
                "slug": article.slug,
                "url": f"/blog/{article.slug}"
            }

        except Exception as e_full:
            db.rollback()
            err_msg = f"{str(e_full)}\n{traceback.format_exc()}"
            job.status = "failed"
            job.error_message = str(e_full)
            job.current_step = f"Pipeline failure: {str(e_full)}"
            job.logs = err_msg
            keyword_obj.status = "failed"
            
            sys_log = SystemLog(
                level="ERROR",
                source="AI_AUTO_BLOGGER",
                message=f"Pipeline failure for keyword '{keyword_obj.keyword}'",
                details=err_msg
            )
            db.add(sys_log)
            db.commit()
            return {"status": "error", "error": str(e_full), "job_id": job.id}

    @classmethod
    async def start_background_loop(cls):
        """
        Background daemon loop attached to FastAPI lifespan.
        Polls for scheduled work every 60 seconds.
        """
        if cls._running:
            return
        cls._running = True
        print("AutoScheduler background worker initiated.")

        while cls._running:
            try:
                # Run queue check with isolated database session
                with SessionLocal() as db:
                    # Check if auto-scheduler is globally enabled
                    enabled = cls.get_setting_str(db, "auto_scheduler_enabled", "true").lower() == "true"
                    if enabled:
                        cls.process_next_keyword(db, force=False)
            except Exception as e_loop:
                print(f"AutoScheduler background loop notice: {e_loop}")

            # Sleep 60 seconds between polling checks
            await asyncio.sleep(60)

    @classmethod
    def stop_background_loop(cls):
        cls._running = False
