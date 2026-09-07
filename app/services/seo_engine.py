import json
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.config import settings
from app.models.article import Article, Category

class SEOEngine:
    @classmethod
    def generate_metadata(cls, keyword: str, title: str, summary: str, slug: str, featured_image: str) -> Dict[str, Any]:
        kw_title = keyword.title()
        
        # SEO Title: Strictly 40 to 55 characters (Point 1)
        clean_title = title.strip()
        if len(clean_title) < 40:
            clean_title = f"{clean_title}: Essential Guide & Review"
            if len(clean_title) > 55:
                clean_title = clean_title[:55].rsplit(" ", 1)[0]
        elif len(clean_title) > 55:
            clean_title = clean_title[:55].rsplit(" ", 1)[0]
            if len(clean_title) < 40:
                clean_title = title.strip()[:55]
        seo_title = clean_title

        # Meta Description: Strictly 140 to 150 characters, never over 150 (Point 2)
        base_desc = (summary or "").strip()
        if not base_desc or len(base_desc) < 40:
            base_desc = f"Discover verified insights, in-depth comparisons, and expert recommendations for {keyword} to make the smartest buying choice on TrendBlogo."
        
        if len(base_desc) > 150:
            truncated = base_desc[:147].rsplit(" ", 1)[0] + "..."
            if len(truncated) > 150:
                truncated = base_desc[:150]
            meta_desc = truncated
        else:
            meta_desc = base_desc

        # If still shorter than 140 characters, pad with informative editorial context up to 140-150 chars
        if len(meta_desc) < 140:
            fillers = [
                " Read our complete breakdown now.",
                " Explore comprehensive verified analysis.",
                " Learn full expert buying tips today.",
                " Find all performance insights here."
            ]
            for f in fillers:
                if 140 <= len(meta_desc + f) <= 150:
                    meta_desc = meta_desc + f
                    break
                elif len(meta_desc + f) < 140:
                    meta_desc = meta_desc + f

            if len(meta_desc) < 140:
                needed = 140 - len(meta_desc)
                meta_desc = meta_desc.rstrip(".") + " with full tested comparisons."
                if len(meta_desc) > 150:
                    meta_desc = meta_desc[:150]
                elif len(meta_desc) < 140:
                    meta_desc = (meta_desc + " " * (140 - len(meta_desc))).strip()
                    if len(meta_desc) < 140:
                        meta_desc = meta_desc.ljust(140, ".")

        canonical_url = f"{settings.BASE_URL}/blog/{slug}"
        og_image = f"{settings.BASE_URL}{featured_image}" if featured_image.startswith("/") else featured_image

        return {
            "seo_title": seo_title,
            "meta_description": meta_desc,
            "canonical_url": canonical_url,
            "og_title": seo_title,
            "og_description": meta_desc,
            "og_image": og_image,
            "twitter_card": "summary_large_image"
        }

    @classmethod
    def generate_schema_json(cls, article: Article) -> str:
        """
        Generates schema.org Article + Breadcrumbs + Publisher JSON-LD.
        """
        base = settings.BASE_URL
        published_iso = article.published_at.isoformat() if article.published_at else datetime.utcnow().isoformat()
        updated_iso = article.updated_at.isoformat() if article.updated_at else published_iso

        img_url = f"{base}{article.featured_image}" if article.featured_image.startswith("/") else article.featured_image

        schema = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "Article",
                    "@id": f"{base}/blog/{article.slug}#article",
                    "isPartOf": {
                        "@type": "WebPage",
                        "@id": f"{base}/blog/{article.slug}"
                    },
                    "headline": article.title,
                    "description": article.meta_description or article.summary,
                    "image": img_url,
                    "datePublished": published_iso,
                    "dateModified": updated_iso,
                    "mainEntityOfPage": f"{base}/blog/{article.slug}",
                    "wordCount": article.word_count,
                    "articleSection": article.category.name if article.category else "Technology",
                    "author": {
                        "@type": "Person",
                        "name": article.author_name or "TrendBlogo Editorial Team"
                    },
                    "publisher": {
                        "@type": "Organization",
                        "name": "TrendBlogo",
                        "url": base,
                        "logo": {
                            "@type": "ImageObject",
                            "url": f"{base}/static/images/logo.svg"
                        }
                    }
                },
                {
                    "@type": "BreadcrumbList",
                    "@id": f"{base}/blog/{article.slug}#breadcrumb",
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": 1,
                            "name": "Home",
                            "item": base
                        },
                        {
                            "@type": "ListItem",
                            "position": 2,
                            "name": "Blog",
                            "item": f"{base}/blog"
                        },
                        {
                            "@type": "ListItem",
                            "position": 3,
                            "name": article.category.name if article.category else "Articles",
                            "item": f"{base}/category/{article.category.slug}" if article.category else f"{base}/blog"
                        },
                        {
                            "@type": "ListItem",
                            "position": 4,
                            "name": article.title,
                            "item": f"{base}/blog/{article.slug}"
                        }
                    ]
                }
            ]
        }
        return json.dumps(schema, indent=2)

    @classmethod
    def generate_sitemap_xml(cls, db: Session) -> str:
        base = settings.BASE_URL
        articles = db.query(Article).filter(Article.status == "published").all()
        categories = db.query(Category).all()

        root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

        # Static pages
        static_pages = [
            ("/", "1.0", "daily"),
            ("/blog", "0.9", "daily"),
            ("/about", "0.7", "monthly"),
            ("/contact", "0.7", "monthly"),
            ("/guest-posting", "0.8", "weekly"),
            ("/privacy-policy", "0.5", "yearly"),
            ("/terms-and-conditions", "0.5", "yearly"),
            ("/disclaimer", "0.5", "yearly"),
            ("/cookie-policy", "0.5", "yearly"),
        ]

        for path, priority, freq in static_pages:
            url_elem = ET.SubElement(root, "url")
            ET.SubElement(url_elem, "loc").text = f"{base}{path}"
            ET.SubElement(url_elem, "changefreq").text = freq
            ET.SubElement(url_elem, "priority").text = priority

        for cat in categories:
            url_elem = ET.SubElement(root, "url")
            ET.SubElement(url_elem, "loc").text = f"{base}/category/{cat.slug}"
            ET.SubElement(url_elem, "changefreq").text = "weekly"
            ET.SubElement(url_elem, "priority").text = "0.8"

        for art in articles:
            url_elem = ET.SubElement(root, "url")
            ET.SubElement(url_elem, "loc").text = f"{base}/blog/{art.slug}"
            ET.SubElement(url_elem, "lastmod").text = art.updated_at.strftime("%Y-%m-%d")
            ET.SubElement(url_elem, "changefreq").text = "weekly"
            ET.SubElement(url_elem, "priority").text = "0.9"

        return ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")

    @classmethod
    def generate_robots_txt(cls) -> str:
        base = settings.BASE_URL
        return f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/

Sitemap: {base}/sitemap.xml
"""
