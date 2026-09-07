import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.article import Article

class ContentValidator:
    """
    Strict Pre-Publishing Quality & SEO Content Validator.
    Ensures zero invalid, incomplete, duplicate, or broken content is automatically published.
    """

    @classmethod
    def validate(
        cls,
        db: Session,
        title: str,
        slug: str,
        meta_description: str,
        content_markdown: str,
        content_html: str,
        keyword: str,
        featured_image_url: str,
        target_word_count: int = 1500,
        min_word_count: Optional[int] = None,
        current_article_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Runs comprehensive validation checks.
        Returns:
            {
                "is_valid": bool,
                "errors": List[str],
                "warnings": List[str],
                "score": float
            }
        """
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Missing or Short Title
        if not title or len(title.strip()) < 10:
            errors.append("Article title is missing or too short (minimum 10 characters required).")

        # 2. Missing or Short Meta Description
        if not meta_description or len(meta_description.strip()) < 30:
            errors.append("Meta description is missing or too short (minimum 30 characters required).")
        elif len(meta_description.strip()) > 180:
            warnings.append(f"Meta description is {len(meta_description)} characters (recommended max 160).")

        # 3. Missing Slug
        if not slug or len(slug.strip()) < 3:
            errors.append("URL slug is missing or too short.")
        elif not re.match(r"^[a-z0-9-]+$", slug.strip()):
            errors.append("URL slug contains invalid characters (only lowercase letters, numbers, and hyphens permitted).")

        # 4. Duplicate Title Check
        query_title = db.query(Article).filter(Article.title == title.strip())
        if current_article_id:
            query_title = query_title.filter(Article.id != current_article_id)
        if query_title.first():
            errors.append(f"Duplicate article title already exists in database: '{title.strip()}'.")

        # 5. Duplicate Slug Check
        query_slug = db.query(Article).filter(Article.slug == slug.strip())
        if current_article_id:
            query_slug = query_slug.filter(Article.id != current_article_id)
        if query_slug.first():
            errors.append(f"Duplicate URL slug already exists in database: '{slug.strip()}'.")

        # 6. Word Count Validation
        words = re.findall(r"\w+", content_markdown or "")
        word_count = len(words)
        effective_min = min_word_count if min_word_count is not None else min(500, int(target_word_count * 0.5))
        if word_count < effective_min:
            errors.append(f"Word count ({word_count}) is below minimum threshold of {effective_min} words.")

        # 7. Empty Sections / Truncated Content
        heading_blocks = re.split(r"\n(?=#{1,4}\s+)", content_markdown or "")
        for idx, block in enumerate(heading_blocks):
            clean_block = block.strip()
            if not clean_block or not clean_block.startswith("#"):
                continue
            lines = [l.strip() for l in clean_block.split("\n") if l.strip()]
            heading_line = lines[0]
            heading_name = heading_line.lstrip("#").strip()
            body_lines = [l for l in lines[1:] if not l.startswith("#")]
            
            # Check if this heading has no body text
            if not body_lines:
                # If followed immediately by a deeper heading (e.g. ## FAQ followed by ### Question), it is valid structure
                next_block = heading_blocks[idx + 1].strip() if idx + 1 < len(heading_blocks) else ""
                cur_level = len(heading_line) - len(heading_line.lstrip("#"))
                next_level = len(next_block) - len(next_block.lstrip("#")) if next_block.startswith("#") else 0
                if next_level > cur_level:
                    continue  # Valid container heading (e.g. ## FAQ containing ### questions)
                errors.append(f"Empty section detected under heading: '{heading_name}'.")

        # 8. Focus Keyword Presence
        kw_clean = keyword.lower().strip()
        # Clean special chars from keyword for regex
        kw_pattern = re.escape(kw_clean)
        content_lower = content_markdown.lower()
        if not re.search(kw_pattern, content_lower):
            # Check individual tokens if multi-word
            tokens = [t for t in re.split(r"\s+", kw_clean) if len(t) > 3]
            matched = sum(1 for t in tokens if t in content_lower)
            if not tokens or (matched / len(tokens)) < 0.5:
                warnings.append(f"Focus keyword '{keyword}' is not prominently represented in the article body.")

        # 9. Heading Link Purity (Zero Heading Links Rule)
        for line in content_markdown.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                if re.search(r"\[([^\]]+)\]\([^)]+\)", stripped) or "<a " in stripped.lower():
                    errors.append(f"Forbidden hyperlink found inside heading: '{stripped}'. Headings must be plain text.")

        # 10. Featured Image Availability
        if not featured_image_url or not featured_image_url.strip():
            errors.append("Featured image URL is missing.")

        # 11. HTML / Markdown Validity
        if not content_html or len(content_html.strip()) < 50:
            errors.append("Rendered HTML content is missing or empty.")

        # Compute Quality Score
        base_score = 100.0
        base_score -= (len(errors) * 25.0)
        base_score -= (len(warnings) * 5.0)
        score = max(0.0, min(100.0, round(base_score, 1)))

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "score": score,
            "word_count": word_count
        }
