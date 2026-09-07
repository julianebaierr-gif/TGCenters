import json
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.article import Article, Category
from app.models.links import InternalLink, ExternalLink, RelatedPost
from app.models.media import Media
from app.models.automation import Keyword, GenerationJob
from app.models.settings import SystemLog
from app.services.keyword_analyzer import KeywordAnalyzer
from app.services.duplicate_checker import DuplicateChecker
from app.services.ai_generator import AIGenerator
from app.services.image_service import ImageService
from app.services.link_engine import LinkEngine
from app.services.seo_engine import SEOEngine
from app.services.quality_control import QualityControl

class QueueRunner:
    @classmethod
    def execute_job(
        cls,
        db: Session,
        job_id: int,
        publish_mode: str = "published",
        scheduled_delay_hours: int = 0,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if not job:
            return {"error": "Job not found"}

        try:
            # Step 1: Initialize
            job.status = "processing"
            job.current_step = "Analyzing keyword intent & structure"
            job.progress = 10
            db.commit()

            # Step 2: Keyword Analysis
            analysis = KeywordAnalyzer.analyze(job.keyword)
            outline = analysis["outline"]
            slug = analysis["suggested_slug"]
            # Ensure unique slug
            base_slug = slug
            counter = 2
            while db.query(Article).filter(Article.slug == slug).first():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            # Step 3: Duplicate & Cannibalization Check
            dup_report = DuplicateChecker.check(db, job.keyword)
            job.current_step = "Duplicate check completed. Generating article content"
            job.progress = 25
            db.commit()

            # Step 4 & 5: AI Article Generation
            category = db.query(Category).filter(Category.id == job.category_id).first() if job.category_id else None
            cat_name = category.name if category else "Technology"

            generated = AIGenerator.generate_article(
                keyword=job.keyword,
                secondary_keywords=[k.strip() for k in (job.secondary_keywords or "").split(",") if k.strip()],
                search_intent=analysis["search_intent"],
                tone=job.tone or "informative",
                language=job.language or "English",
                target_word_count=job.target_word_count or 1500,
                template_type=job.template_type or "ultimate_guide",
                category_name=cat_name,
                db=db,
                api_key=api_key,
                model=model
            )

            job.current_step = "Injecting contextual internal and external links"
            job.progress = 45
            db.commit()

            # Step 6 & 7: Link Engine (Strict plain-text headings rule)
            raw_markdown = generated["markdown"]
            # Internal links
            linked_markdown, int_links = LinkEngine.inject_internal_links(db, raw_markdown)
            # External links
            final_markdown, ext_links = LinkEngine.inject_external_links(linked_markdown, job.keyword, api_key=api_key)
            # Final sanitize headings: guarantee NO hyperlinks in headings
            final_markdown = LinkEngine.sanitize_headings(final_markdown)

            job.current_step = "Generating 2 contextual visual assets (1 featured hero + 1 in-article)"
            job.progress = 65
            db.commit()

            # Step 8, 9 & 10: 2-Image Generation (1 Featured + 1 In-Article photo)
            images_data = ImageService.create_article_images(
                keyword=job.keyword,
                title=generated["title"],
                outline_sections=outline,
                slug=slug,
                db=db,
                api_key=api_key
            )

            featured = images_data["featured"]
            img1 = images_data.get("image_1")

            # Embed the 1 in-content image into markdown
            if img1:
                img1_md = f"\n\n![{img1['alt']}]({img1['url']})\n*{img1['caption']}*\n\n"
                if "<!-- IN_CONTENT_IMAGE_1 -->" in final_markdown:
                    final_markdown = final_markdown.replace("<!-- IN_CONTENT_IMAGE_1 -->", img1_md)
                else:
                    final_markdown += img1_md

            # Clean any leftover markers or Kramdown syntax
            final_markdown = final_markdown.replace("<!-- IN_CONTENT_IMAGE_2 -->", "")
            final_markdown = final_markdown.replace("<!-- IN_CONTENT_IMAGE_3 -->", "")
            final_markdown = LinkEngine.clean_markdown_syntax(final_markdown)

            # Render final HTML
            import markdown as md_renderer
            final_html = md_renderer.markdown(
                final_markdown,
                extensions=["fenced_code", "tables", "toc", "sane_lists"]
            )

            job.current_step = "Generating SEO metadata and Schema.org structured data"
            job.progress = 80
            db.commit()

            # Step 11: SEO Metadata & Schema
            seo_meta = SEOEngine.generate_metadata(
                keyword=job.keyword,
                title=generated["title"],
                summary=generated["summary"],
                slug=slug,
                featured_image=featured["url"]
            )

            # Step 12 & 13: Quality Control Audit (1 Featured + 1 In-Content = 2 Total)
            qc_report = QualityControl.audit(
                keyword=job.keyword,
                title=generated["title"],
                content=final_markdown,
                featured_image=featured["url"],
                in_content_images=[img1] if img1 else [],
                internal_links_count=len(int_links),
                external_links_count=len(ext_links)
            )

            job.current_step = "Finalizing article entity and database persistence"
            job.progress = 92
            db.commit()

            # Determine publication timestamp
            now = datetime.utcnow()
            scheduled_at = None
            if publish_mode == "scheduled":
                delay = scheduled_delay_hours if scheduled_delay_hours > 0 else 24
                scheduled_at = now + timedelta(hours=delay)
                article_status = "scheduled"
            elif publish_mode == "draft":
                article_status = "draft"
            else:
                article_status = "published"

            # Create Article Record
            article = Article(
                title=generated["title"],
                slug=slug,
                primary_keyword=job.keyword,
                secondary_keywords=job.secondary_keywords,
                search_intent=analysis["search_intent"],
                template_type=job.template_type or "ultimate_guide",
                summary=generated["summary"],
                content=final_markdown,
                html_content=final_html,
                featured_image=featured["url"],
                featured_image_alt=featured["alt"],
                featured_image_caption=featured["caption"],
                image_1_url=img1["url"] if img1 else None,
                image_1_alt=img1["alt"] if img1 else None,
                image_1_caption=img1["caption"] if img1 else None,
                image_2_url=None,
                image_2_alt=None,
                image_2_caption=None,
                image_3_url=None,
                image_3_alt=None,
                image_3_caption=None,
                category_id=job.category_id,
                author_name="Alex Rivera",
                author_slug="alex-rivera",
                status=article_status,
                scheduled_at=scheduled_at,
                published_at=now,
                word_count=generated["word_count"],
                reading_time=generated["reading_time"],
                seo_title=seo_meta["seo_title"],
                meta_description=seo_meta["meta_description"],
                canonical_url=seo_meta["canonical_url"],
                og_title=seo_meta["og_title"],
                og_description=seo_meta["og_description"],
                quality_score=qc_report["score"],
                quality_report=json.dumps(qc_report)
            )
            db.add(article)
            db.flush()

            # Generate and assign Schema.org JSON
            article.schema_json = SEOEngine.generate_schema_json(article)

            # Persist Media Records (1 Featured + 1 In-Article = 2 images)
            for img_info in [featured, img1]:
                if not img_info:
                    continue
                media_rec = Media(
                    filename=img_info["filename"],
                    file_path=img_info.get("file_path", ""),
                    url=img_info["url"],
                    media_type="image/png" if img_info["url"].endswith(".png") else "image/svg+xml",
                    alt_text=img_info["alt"],
                    caption=img_info.get("caption", ""),
                    prompt=img_info.get("prompt", ""),
                    article_id=article.id
                )
                db.add(media_rec)

            # Persist Internal Links
            for link_data in int_links:
                int_rec = InternalLink(
                    source_article_id=article.id,
                    target_article_id=link_data["target_article_id"],
                    anchor_text=link_data["anchor"],
                    target_url=link_data["target_url"]
                )
                db.add(int_rec)

            # Persist External Links
            for ext_data in ext_links:
                ext_rec = ExternalLink(
                    article_id=article.id,
                    anchor_text=ext_data["anchor"],
                    url=ext_data["url"],
                    domain=ext_data["domain"],
                    source_type="authoritative"
                )
                db.add(ext_rec)

            # Link Keyword record
            kw_rec = db.query(Keyword).filter(Keyword.keyword == job.keyword).first()
            if kw_rec:
                kw_rec.status = "completed"
                kw_rec.article_id = article.id

            # Update Job Record
            job.status = "completed"
            job.progress = 100
            job.current_step = "Article published and live!"
            job.result_article_id = article.id
            job.logs = f"Success. Generated {article.word_count} words, 4 images, Quality Score: {qc_report['score']}/100."

            # System Log
            log_entry = SystemLog(
                level="SUCCESS",
                source="QUEUE_RUNNER",
                message=f"Successfully generated article for keyword '{job.keyword}' (Article #{article.id})",
                details=f"Slug: {article.slug}, QC: {qc_report['score']}%"
            )
            db.commit()

            # Automatically crosslink internal links across all published articles
            try:
                LinkEngine.auto_crosslink_all_articles(db)
            except Exception as e_cross:
                logger.warning(f"Auto-crosslink notice: {e_cross}")

            # Auto-deploy live to Vercel
            try:
                from app.services.auto_deploy import trigger_auto_deploy_background
                trigger_auto_deploy_background()
            except Exception as e_deploy:
                logger.warning(f"Auto-deploy notice: {e_deploy}")
            return {"success": True, "article_id": article.id, "slug": article.slug}

        except Exception as e:
            db.rollback()
            err_msg = f"{str(e)}\n{traceback.format_exc()}"
            job.status = "failed"
            job.error_message = str(e)
            job.current_step = f"Failed at {job.current_step}"
            job.logs = err_msg
            
            log_entry = SystemLog(
                level="ERROR",
                source="QUEUE_RUNNER",
                message=f"Failed processing job for keyword '{job.keyword}'",
                details=err_msg
            )
            db.add(log_entry)
            db.commit()
            return {"success": False, "error": str(e)}
