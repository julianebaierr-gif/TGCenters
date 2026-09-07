import os
import re
import json
import markdown
from typing import Dict, Any, List, Optional
from app.config import settings
from app.models.settings import SiteSetting
from app.models.automation import AIUsage

SUPPORTED_LANGUAGES = {
    "English": {"code": "en", "native": "English", "locale": "en_US"},
    "Urdu": {"code": "ur", "native": "اردو", "locale": "ur_PK"},
    "Hindi": {"code": "hi", "native": "हिन्दी", "locale": "hi_IN"},
    "Spanish": {"code": "es", "native": "Español", "locale": "es_ES"},
    "French": {"code": "fr", "native": "Français", "locale": "fr_FR"},
    "German": {"code": "de", "native": "Deutsch", "locale": "de_DE"},
    "Arabic": {"code": "ar", "native": "العربية", "locale": "ar_SA"},
    "Portuguese": {"code": "pt", "native": "Português", "locale": "pt_BR"},
    "Italian": {"code": "it", "native": "Italiano", "locale": "it_IT"},
    "Turkish": {"code": "tr", "native": "Türkçe", "locale": "tr_TR"},
    "Russian": {"code": "ru", "native": "Русский", "locale": "ru_RU"},
    "Japanese": {"code": "ja", "native": "日本語", "locale": "ja_JP"},
    "Chinese": {"code": "zh", "native": "中文", "locale": "zh_CN"}
}

class AIContentService:
    """
    Dedicated AI Article Generation Service powered by OpenAI.
    Supports native generation directly in the selected language,
    strict plain-text headings, structured metadata, and Google Helpful Content standards.
    """

    @classmethod
    def get_api_key(cls, db: Optional[Any] = None) -> str:
        if db:
            try:
                s = db.query(SiteSetting).filter(SiteSetting.key == "openai_api_key").first()
                if s and s.value and s.value.strip().startswith("sk-"):
                    return s.value.strip()
            except Exception:
                pass
        return (settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")).strip()

    @classmethod
    def get_model(cls, db: Optional[Any] = None) -> str:
        if db:
            try:
                s = db.query(SiteSetting).filter(SiteSetting.key == "openai_model").first()
                if s and s.value and s.value.strip():
                    return s.value.strip()
            except Exception:
                pass
        return settings.OPENAI_MODEL or "gpt-4o-mini"

    @classmethod
    def enforce_plain_text_headings(cls, markdown_text: str) -> str:
        """
        Guarantees that all H1 to H6 headings contain 100% plain text only.
        Never allow hyperlinks, anchors, or HTML tags inside headings.
        """
        lines = markdown_text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                # Strip markdown links [Anchor Text](url) -> Anchor Text
                line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
                # Strip html links <a href="...">Anchor Text</a> -> Anchor Text
                line = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", line, flags=re.IGNORECASE)
                # Strip any leftover curly braces or attributes
                line = re.sub(r"\{:[^}]*\}", "", line)
            cleaned.append(line)
        return "\n".join(cleaned)

    @classmethod
    def generate_article_pipeline(
        cls,
        keyword: str,
        language: str = "English",
        country: str = "United States",
        article_type: str = "informational",
        target_word_count: int = 2000,
        secondary_keywords: Optional[List[str]] = None,
        tone: str = "authoritative, engaging, and practical",
        category_name: str = "Technology",
        db: Optional[Any] = None,
        custom_api_key: Optional[str] = None,
        custom_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        End-to-end AI Article Generation pipeline.
        Generates directly in the requested language (no translation).
        Produces full SEO fields, structured headings, bullet lists, comparison tables, and FAQs.
        """
        from openai import OpenAI

        api_key = (custom_api_key or "").strip() or cls.get_api_key(db)
        model_name = (custom_model or "").strip() or cls.get_model(db)

        if not api_key or not api_key.startswith("sk-"):
            raise ValueError(
                "OpenAI API Key is missing or invalid. Please configure your OpenAI API Key in Admin Settings (/admin/settings)."
            )

        client = OpenAI(api_key=api_key, timeout=75.0)
        secondary_kw_list = secondary_keywords or []
        sec_kw_str = ", ".join(secondary_kw_list) if secondary_kw_list else "None specified"

        lang_info = SUPPORTED_LANGUAGES.get(language, {"code": "en", "native": language, "locale": "en_US"})
        target_lang_name = lang_info["native"] if language != "English" else "English"

        system_instruction = f"""You are an elite multilingual editorial journalist and SEO content architect writing for TrendBlogo.
You MUST write the complete article directly and natively in {language} ({target_lang_name}).
Do NOT write in English and translate. Think, structure, and write natively in {language}.
Follow 2026 Google Search Quality Rater and Helpful Content Guidelines strictly:
- Original, natural, high-value, and deeply comprehensive content matching search intent for audience in {country}.
- No repetitive filler, no keyword stuffing, no generic clichés.
- Strictly NO fake citations, fake academic papers, fake statistical studies, or fabricated quotes.
- Provide objective, genuine, actionable explanations, authentic criteria, and real-world considerations.
- Enforce strict heading hierarchy: Single H1 headline, followed by logical H2 sections and nested H3 subsections.
- Plain-text headings only: Never insert any markdown links or HTML anchors inside any heading (H1, H2, H3, H4, H5, H6).
- Include practical bullet lists and at least one comparison or summary markdown table where helpful.
- Include a comprehensive Frequently Asked Questions (FAQ) section answering real questions user searchers ask.
- Include a strong conclusion summarizing key actionable takeaways.
"""

        user_prompt = f"""Generate a publication-ready {article_type} article natively in {language}.

Topic / Primary Keyword: {keyword}
Secondary Keywords: {sec_kw_str}
Target Market / Country: {country}
Article Type: {article_type}
Target Word Count: approximately {target_word_count} words
Tone: {tone}
Category: {category_name}

OUTPUT FORMAT REQUIREMENTS:
You MUST respond with a valid, clean JSON object matching this schema:
{{
  "title": "A compelling, natural headline in {language} (between 40 and 60 characters)",
  "slug": "url-friendly-english-or-transliterated-slug-for-clean-urls",
  "meta_title": "SEO meta title in {language} (under 60 characters)",
  "meta_description": "Precise, clickable meta description in {language} summarizing the article (strictly between 140 and 155 characters)",
  "focus_keyword": "{keyword}",
  "secondary_keywords": ["keyword 1", "keyword 2", "keyword 3"],
  "image_prompt": "An English description of an authentic, professional documentary/editorial real-world photograph for DALL-E (bright natural lighting, tangible textures, real environment, zero CGI, zero cartoon, zero text)",
  "image_alt_text": "Descriptive SEO image alt text in {language}",
  "image_caption": "Informative editorial caption in {language}",
  "suggested_tags": ["tag1", "tag2", "tag3", "tag4"],
  "content_markdown": "# Title in {language}\\n\\nIntroduction...\\n\\n## Section 1...\\n\\n### Subsection...\\n\\n| Column 1 | Column 2 |\\n|---|---|\\n\\n## Frequently Asked Questions\\n\\n### Question 1?\\nAnswer...\\n\\n## Conclusion\\nSummary..."
}}
"""

        # Call OpenAI Chat Completions API
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=4000
            )
        except Exception as e_api:
            raise RuntimeError(f"OpenAI Generation API failed: {str(e_api)}")

        # Parse JSON
        raw_text = response.choices[0].message.content
        try:
            parsed = json.loads(raw_text)
        except Exception as e_json:
            raise ValueError(f"Failed to parse AI JSON response: {e_json}\nRaw output: {raw_text[:200]}")

        # Extract usage and cost tracking
        usage = getattr(response, "usage", None)
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        # Estimated cost calculation ($0.15/1M input, $0.60/1M output for gpt-4o-mini)
        est_cost = 0.0
        if "gpt-4o-mini" in model_name:
            est_cost = (prompt_tokens * 0.00000015) + (completion_tokens * 0.0000006)
        elif "gpt-4o" in model_name:
            est_cost = (prompt_tokens * 0.0000025) + (completion_tokens * 0.00001)

        if db:
            try:
                ai_log = AIUsage(
                    provider="openai",
                    model=model_name,
                    operation="article_generation",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=est_cost
                )
                db.add(ai_log)
                db.commit()
            except Exception:
                pass

        # Validate and sanitize markdown
        content_md = parsed.get("content_markdown", "").strip()
        content_md = cls.enforce_plain_text_headings(content_md)

        # Extract title if not in json or clean it
        title = parsed.get("title", "").strip()
        if not title:
            first_line = content_md.split("\n")[0].strip()
            if first_line.startswith("#"):
                title = first_line.replace("#", "").strip()
            else:
                title = keyword.title()

        # Generate clean URL slug
        slug = parsed.get("slug", "").strip()
        if not slug or len(slug) < 3:
            # Generate slug from keyword or title
            slug = re.sub(r"[^a-zA-Z0-9\s-]", "", keyword.lower())
            slug = re.sub(r"[\s-]+", "-", slug).strip("-")[:80]

        # Calculate word count & reading time
        words = re.findall(r"\w+", content_md)
        word_count = len(words)
        reading_time = max(1, round(word_count / 200))

        # Render Markdown to HTML with modern extensions
        html_rendered = markdown.markdown(
            content_md,
            extensions=["fenced_code", "tables", "toc", "sane_lists"]
        )

        return {
            "title": title,
            "slug": slug,
            "meta_title": parsed.get("meta_title", title)[:60],
            "meta_description": parsed.get("meta_description", "")[:160],
            "focus_keyword": parsed.get("focus_keyword", keyword),
            "secondary_keywords": parsed.get("secondary_keywords", secondary_kw_list),
            "image_prompt": parsed.get("image_prompt", f"An editorial documentary photograph illustrating {keyword}"),
            "image_alt_text": parsed.get("image_alt_text", f"{title} - Overview"),
            "image_caption": parsed.get("image_caption", f"Essential guide to {keyword}"),
            "suggested_tags": parsed.get("suggested_tags", []),
            "markdown": content_md,
            "html": html_rendered,
            "word_count": word_count,
            "reading_time": reading_time,
            "language": language,
            "country": country,
            "article_type": article_type,
            "tokens": total_tokens,
            "estimated_cost": est_cost,
            "model_used": model_name
        }
