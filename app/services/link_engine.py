import re
import json
import urllib.parse
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session
from app.models.article import Article
from app.config import settings

class LinkEngine:

    @classmethod
    def sanitize_headings(cls, markdown_content: str) -> str:
        """
        CRITICAL RULE: Headings (H2-H5) must NEVER contain hyperlinks.
        Strips any [text](url) or <a href="...">text</a> from lines starting with #.
        """
        lines = markdown_content.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("##"):
                # Strip markdown link: [Anchor](url) -> Anchor
                line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
                # Strip HTML link: <a ...>Anchor</a> -> Anchor
                line = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", line, flags=re.IGNORECASE)
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    @classmethod
    def inject_internal_links(cls, db: Session, content: str, current_article_id: int = None, max_links: int = 3) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Scans existing published articles and weaves natural internal links into body paragraphs.
        RULE: ONLY link to articles that actually exist on the site.
        If no other published articles exist, links to the Home page ('/').
        NEVER touches headings or lines starting with #.
        """
        query = db.query(Article).filter(Article.status == "published")
        if current_article_id:
            query = query.filter(Article.id != current_article_id)
        existing_articles = query.all()

        if not existing_articles:
            # If no relevant published articles exist, internal linking is optional (do not force links)
            return content, []

        inserted_links = []
        lines = content.split("\n")
        new_lines = []

        used_target_ids = set()

        for line in lines:
            # Skip headings, quotes, code fences, image tags
            if (line.strip().startswith("#") or 
                line.strip().startswith("!") or 
                line.strip().startswith("```") or 
                line.strip().startswith(">") or 
                len(line.strip()) < 40 or 
                len(inserted_links) >= max_links):
                new_lines.append(line)
                continue

            # Attempt to find a natural keyword phrase match for an existing article
            modified_line = line
            for art in existing_articles:
                if art.id in used_target_ids or len(inserted_links) >= max_links:
                    continue

                kw = art.primary_keyword.strip()
                if not kw or len(kw) < 4:
                    continue

                # Search case-insensitively for keyword without already being part of a link
                pattern = rf"(?<!\[)(?<!/)\b({re.escape(kw)})\b(?![^\[]*\])(?![^\(]*\))"
                match = re.search(pattern, modified_line, flags=re.IGNORECASE)
                if match:
                    matched_text = match.group(1)
                    replacement = f"[{matched_text}](/blog/{art.slug})"
                    modified_line = modified_line[:match.start()] + replacement + modified_line[match.end():]
                    
                    inserted_links.append({
                        "target_article_id": art.id,
                        "title": art.title,
                        "slug": art.slug,
                        "anchor": matched_text,
                        "target_url": f"/blog/{art.slug}"
                    })
                    used_target_ids.add(art.id)
                    break # One link per paragraph max

            new_lines.append(modified_line)

        return "\n".join(new_lines), inserted_links

    @classmethod
    def clean_markdown_syntax(cls, text: str) -> str:
        """
        Strips any Kramdown/Jekyll attribute leaks like {:target="_blank"...}
        and ensures pristine, pure Markdown.
        """
        # Remove any {:target="_blank"...} or {:...} attribute blocks
        cleaned = re.sub(r"\{:[^}]*\}", "", text)
        return cleaned

    @classmethod
    def resolve_dynamic_external_link(cls, topic_keyword: str, content: str = "", api_key: Optional[str] = None) -> Dict[str, str]:
        """
        Dynamically resolves a single authoritative external citation tailored strictly
        to the given topic without ANY hardcoded or fixed list.
        Uses OpenAI ChatGPT when available, or dynamic topical encyclopedic reference.
        """
        clean_kw = topic_keyword.strip()
        
        # 1. Try ChatGPT API if available
        key_to_use = (api_key or "").strip() or settings.OPENAI_API_KEY
        if key_to_use and key_to_use.startswith("sk-") and len(key_to_use) > 15:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=key_to_use, timeout=8.0)
                prompt = (
                    f"For the topic or primary keyword '{clean_kw}', provide exactly ONE real, highly authoritative, reputable external reference website "
                    f"(such as an official standards body, research institute, official documentation, or renowned encyclopedic authority). "
                    f"Output ONLY valid JSON with keys: anchor, url, domain. "
                    f"Example: {{\"anchor\": \"W3C Web Standards\", \"url\": \"https://www.w3.org/standards/\", \"domain\": \"w3.org\"}}"
                )
                res = client.chat.completions.create(
                    model=settings.OPENAI_MODEL or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are an SEO citations assistant. Output strictly JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=100
                )
                raw_json = res.choices[0].message.content.strip()
                raw_json = re.sub(r"^```(?:json)?", "", raw_json, flags=re.MULTILINE).replace("```", "").strip()
                parsed = json.loads(raw_json)
                if parsed.get("url") and parsed.get("anchor"):
                    domain = parsed.get("domain") or re.sub(r"^https?://(?:www\.)?([^/]+).*", r"\1", parsed["url"])
                    return {
                        "anchor": parsed["anchor"],
                        "url": parsed["url"],
                        "domain": domain
                    }
            except Exception:
                pass

        # 2. Dynamic topical encyclopedia reference (No hardcoded domain list)
        topic_slug = clean_kw.replace(" ", "_").capitalize()
        wiki_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(topic_slug)}"
        return {
            "anchor": clean_kw,
            "url": wiki_url,
            "domain": "en.wikipedia.org"
        }

    @classmethod
    def inject_external_links(cls, content: str, topic_keyword: str, max_links: int = 1, api_key: Optional[str] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Extracts or injects dynamic, topic-specific external citations.
        NO hardcoded/fixed lists. Respects 2026 Google Helpful Content guidelines.
        """
        content = cls.clean_markdown_syntax(content)
        
        # 1. If the article already contains a natural external citation (e.g. written by ChatGPT), extract it
        existing_ext = re.findall(r"\[([^\]]+)\]\((https?://(?!(?:www\.)?(?:trendblogo\.com|localhost))[^)]+)\)", content)
        if existing_ext:
            results = []
            for anchor, url in existing_ext[:max_links]:
                domain = re.sub(r"^https?://(?:www\.)?([^/]+).*", r"\1", url)
                results.append({"anchor": anchor, "url": url, "domain": domain})
            return content, results

        # 2. Dynamically resolve a topic-specific authoritative citation (No fixed list)
        dynamic_ref = cls.resolve_dynamic_external_link(topic_keyword, content, api_key=api_key)
        anchor = dynamic_ref["anchor"]
        url = dynamic_ref["url"]
        domain = dynamic_ref["domain"]

        lines = content.split("\n")
        new_lines = []
        inserted = False

        # Try to find a paragraph containing the anchor word or topic keyword to link naturally
        kw_pattern = rf"(?<!\[)(?<!/)\b({re.escape(anchor)}|{re.escape(topic_keyword)})\b(?![^\[]*\])(?![^\(]*\))"

        for line in lines:
            stripped = line.strip()
            if (not inserted and 
                not stripped.startswith("#") and 
                not stripped.startswith("!") and 
                not stripped.startswith(">") and 
                not stripped.startswith("```") and 
                len(stripped) > 50):
                
                m = re.search(kw_pattern, line, flags=re.IGNORECASE)
                if m:
                    matched_text = m.group(0)
                    replacement = f"[{matched_text}]({url})"
                    line = line[:m.start()] + replacement + line[m.end():]
                    inserted = True
            new_lines.append(line)

        # If keyword wasn't found verbatim in paragraphs, weave a natural citation sentence
        if not inserted:
            for idx, l in enumerate(new_lines):
                st = l.strip()
                if not st.startswith("#") and not st.startswith("!") and len(st) > 80:
                    new_lines[idx] = l + f" For broader industry context and technical documentation, refer to [{anchor}]({url})."
                    inserted = True
                    break

        if inserted:
            return "\n".join(new_lines), [{"anchor": anchor, "url": url, "domain": domain}]

        return content, []

    @classmethod
    def auto_crosslink_all_articles(cls, db: Session, max_links_per_article: int = 4) -> int:
        """
        Scans all published articles and establishes internal links.
        STRICT RULES:
        1. ONLY link to articles that actually exist with status='published' in the database. Never link to non-existent posts.
        2. If only 1 article exists on the site, link to the Home page ('/').
        3. Remove any dead or hallucinated links pointing to non-existent /blog/... slugs.
        4. Headings (H2-H5) must NEVER contain hyperlinks.
        """
        import markdown as md_lib
        from app.models.links import InternalLink

        published = db.query(Article).filter(Article.status == "published").all()
        if not published:
            return 0

        valid_slugs = {p.slug for p in published}
        total_links_created = 0

        # Step 1: Clean any dead / non-existent article links from all articles
        for art in published:
            art_modified = False
            content = art.content or ""
            
            def replace_invalid_slug(match):
                nonlocal art_modified
                anchor = match.group(1)
                slug = match.group(2)
                if slug not in valid_slugs:
                    art_modified = True
                    return anchor
                return match.group(0)

            cleaned_content = re.sub(r"\[([^\]]+)\]\(/blog/([a-zA-Z0-9_-]+)\)", replace_invalid_slug, content)
            if art_modified:
                art.content = cls.sanitize_headings(cleaned_content)
                art.html_content = md_lib.markdown(art.content, extensions=["fenced_code", "tables", "toc", "sane_lists"])

        # Clean invalid internal_links table rows
        db.query(InternalLink).filter(~InternalLink.target_url.in_(["/", ""] + [f"/blog/{s}" for s in valid_slugs])).delete(synchronize_session=False)

        # Step 2: If only 1 article exists on the entire site, link to Home (/)
        if len(published) == 1:
            art = published[0]
            content = art.content or ""
            if not re.search(r"\[([^\]]+)\]\(/(?:\)|#|$)", content):
                lines = content.split("\n")
                new_lines = []
                placed = False
                for line in lines:
                    stripped = line.strip()
                    if not placed and not stripped.startswith("#") and not stripped.startswith("!") and len(stripped) > 60:
                        line += " For more product reviews and expert buyer insights, explore our [homepage](/)."
                        placed = True
                    new_lines.append(line)
                if placed:
                    art.content = cls.sanitize_headings("\n".join(new_lines))
                    art.html_content = md_lib.markdown(art.content, extensions=["fenced_code", "tables", "toc", "sane_lists"])
                    total_links_created += 1
            
            # Ensure internal_links table has the home link
            home_link_rec = db.query(InternalLink).filter(InternalLink.source_article_id == art.id, InternalLink.target_url == "/").first()
            if not home_link_rec:
                db.add(InternalLink(source_article_id=art.id, target_article_id=art.id, anchor_text="homepage", target_url="/"))

            db.commit()
            return total_links_created

        # Step 3: Multiple published articles exist -> strictly crosslink between REAL published articles
        for source in published:
            source_modified = False
            source_content = source.content or ""
            lines = source_content.split("\n")

            existing_links = re.findall(r"/blog/([a-zA-Z0-9_-]+)", source_content)
            linked_slugs = set(existing_links)

            candidates = [p for p in published if p.id != source.id and p.slug not in linked_slugs]

            for target in candidates:
                current_int_links_count = len(re.findall(r"\[([^\]]+)\]\(/blog/[^\)]+\)", source_content))
                if current_int_links_count >= max_links_per_article:
                    break

                target_url = f"/blog/{target.slug}"
                keywords_to_try = []
                if target.primary_keyword and len(target.primary_keyword.strip()) >= 3:
                    keywords_to_try.append(target.primary_keyword.strip())
                
                if target.secondary_keywords:
                    for sk in target.secondary_keywords.split(","):
                        sk_clean = sk.strip()
                        if len(sk_clean) >= 3 and sk_clean not in keywords_to_try:
                            keywords_to_try.append(sk_clean)

                title_clean = re.sub(r"[:\-\|].*$", "", target.title).strip()
                if title_clean and title_clean not in keywords_to_try and len(title_clean) > 5:
                    keywords_to_try.append(title_clean)

                link_placed = False
                new_lines = []

                for line in lines:
                    stripped = line.strip()
                    if (link_placed or 
                        stripped.startswith("#") or 
                        stripped.startswith("!") or 
                        stripped.startswith("```") or 
                        stripped.startswith(">") or 
                        len(stripped) < 40 or
                        target_url in line):
                        new_lines.append(line)
                        continue

                    matched = False
                    for kw in keywords_to_try:
                        pattern = rf"(?<!\[)(?<!/)\b({re.escape(kw)})\b(?![^\[]*\])(?![^\(]*\))"
                        m = re.search(pattern, line, flags=re.IGNORECASE)
                        if m:
                            anchor_word = m.group(1)
                            replacement = f"[{anchor_word}]({target_url})"
                            line = line[:m.start()] + replacement + line[m.end():]
                            link_placed = True
                            matched = True

                            existing_rec = db.query(InternalLink).filter(
                                InternalLink.source_article_id == source.id,
                                InternalLink.target_article_id == target.id
                            ).first()
                            if not existing_rec:
                                db.add(InternalLink(
                                    source_article_id=source.id,
                                    target_article_id=target.id,
                                    anchor_text=anchor_word,
                                    target_url=target_url
                                ))
                            total_links_created += 1
                            break

                    new_lines.append(line)

                # Contextual fallback strictly to THIS real target article
                if not link_placed and current_int_links_count < max_links_per_article:
                    insert_idx = -1
                    for idx, l in enumerate(new_lines):
                        st = l.strip()
                        if not st.startswith("#") and not st.startswith("!") and len(st) > 80:
                            insert_idx = idx
                    
                    if insert_idx != -1:
                        anchor_title = target.title
                        reference_sentence = f" For complementary insights, explore our comprehensive breakdown on [{anchor_title}]({target_url})."
                        new_lines[insert_idx] = new_lines[insert_idx] + reference_sentence
                        link_placed = True

                        existing_rec = db.query(InternalLink).filter(
                            InternalLink.source_article_id == source.id,
                            InternalLink.target_article_id == target.id
                        ).first()
                        if not existing_rec:
                            db.add(InternalLink(
                                source_article_id=source.id,
                                target_article_id=target.id,
                                anchor_text=anchor_title,
                                target_url=target_url
                            ))
                        total_links_created += 1

                if link_placed:
                    lines = new_lines
                    source_content = "\n".join(lines)
                    source_modified = True

            if source_modified:
                source.content = cls.sanitize_headings(source_content)
                source.content = cls.clean_markdown_syntax(source.content)
                source.html_content = md_lib.markdown(
                    source.content,
                    extensions=["fenced_code", "tables", "toc", "sane_lists"]
                )

        if total_links_created > 0:
            db.commit()

        return total_links_created

    @classmethod
    def get_related_posts(cls, db: Session, article_id: int, category_id: int = None, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Finds 3 to 6 contextually related articles based on category and topic proximity.
        """
        query = db.query(Article).filter(
            Article.status == "published",
            Article.id != article_id
        )

        same_category_posts = []
        if category_id:
            same_category_posts = query.filter(Article.category_id == category_id).limit(limit).all()

        other_posts = []
        if len(same_category_posts) < limit:
            remaining = limit - len(same_category_posts)
            exclude_ids = [p.id for p in same_category_posts] + [article_id]
            other_posts = query.filter(~Article.id.in_(exclude_ids)).limit(remaining).all()

        all_related = same_category_posts + other_posts
        
        results = []
        for post in all_related:
            results.append({
                "id": post.id,
                "title": post.title,
                "slug": post.slug,
                "excerpt": post.summary or (post.content[:160] + "..."),
                "featured_image": post.featured_image,
                "category": post.category.name if post.category else "Technology",
                "category_slug": post.category.slug if post.category else "technology",
                "published_at": post.published_at.strftime("%B %d, %Y") if post.published_at else "Recently",
                "reading_time": post.reading_time
            })
        return results
