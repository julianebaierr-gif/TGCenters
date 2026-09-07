import re
from typing import Dict, Any, List

class QualityControl:
    @classmethod
    def audit(
        cls,
        keyword: str,
        title: str,
        content: str,
        featured_image: str,
        in_content_images: List[Dict[str, str]],
        internal_links_count: int,
        external_links_count: int
    ) -> Dict[str, Any]:
        warnings = []
        recommendations = []
        score = 100.0

        # 1. Heading Link Purity Check (CRITICAL RULE)
        heading_links_found = 0
        heading_hierarchy = []
        lines = content.split("\n")
        
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("##"):
                level = len(stripped) - len(stripped.lstrip("#"))
                heading_text = stripped.lstrip("#").strip()
                heading_hierarchy.append({"level": level, "text": heading_text})
                
                # Check for link in heading
                if re.search(r"\[.*?\]\(.*?\)", heading_text) or "<a " in heading_text:
                    heading_links_found += 1

        if heading_links_found > 0:
            score -= 25.0
            warnings.append(f"Found {heading_links_found} heading(s) containing hyperlinks! Headings must be plain text only.")
            recommendations.append("Ensure all H2-H5 headings are clean plain text. Move all anchor links into body paragraphs.")

        # 1b. Title Length SERP Check (Must be 40 to 55 characters)
        if len(title) > 55:
            score -= 10.0
            warnings.append(f"Title length ({len(title)} chars) exceeds the 55-character limit.")
            recommendations.append("Shorten title to 40-55 characters for optimal search snippet display.")
        elif len(title) < 40:
            score -= 5.0
            warnings.append(f"Title length ({len(title)} chars) is below the recommended 40-character minimum.")
            recommendations.append("Expand title to between 40 and 55 characters.")

        # 2. Heading Structure Check
        h2_count = sum(1 for h in heading_hierarchy if h["level"] == 2)
        if h2_count < 3:
            score -= 10.0
            warnings.append("Article has fewer than 3 H2 sections.")
            recommendations.append("Expand the article structure with at least 3-5 comprehensive H2 sections.")

        # 3. Keyword Density Check
        total_words = len(re.findall(r"\w+", content))
        kw_tokens = re.findall(r"\w+", keyword.lower())
        kw_phrase_count = len(re.findall(rf"\b{re.escape(keyword.lower())}\b", content.lower()))
        
        density = (kw_phrase_count * len(kw_tokens) / max(total_words, 1)) * 100 if total_words > 0 else 0
        
        if density > 3.0:
            score -= 15.0
            warnings.append(f"Keyword density ({density:.1f}%) is higher than optimal. Risk of keyword stuffing.")
            recommendations.append("Tone down repetitive keyword mentions and use natural synonyms.")
        elif density < 0.3:
            score -= 5.0
            recommendations.append(f"Primary keyword appears infrequently ({kw_phrase_count} times). Ensure key sections reference it naturally.")

        # 4. Word Count Check
        if total_words < 600:
            score -= 15.0
            warnings.append(f"Word count ({total_words}) is below the standard depth target (1,000+ words).")
            recommendations.append("Provide deeper technical exploration, real-world examples, or actionable tips.")
        
        # 5. Image Count Check (Must have 1 featured + 1 in-content = 2 images total)
        valid_body_images = [img for img in in_content_images if img and img.get("url")]
        if not featured_image:
            score -= 15.0
            warnings.append("Missing featured hero image.")
        if len(valid_body_images) < 1:
            score -= 10.0
            warnings.append(f"Article contains {len(valid_body_images)} in-content images (target is 1).")
            recommendations.append("Ensure 1 relevant photographic asset is distributed within the article body.")

        # 6. Alt Text Check
        missing_alt = sum(1 for img in valid_body_images if not img.get("alt"))
        if missing_alt > 0:
            score -= 5.0
            warnings.append(f"{missing_alt} image(s) lack SEO alt text descriptions.")

        # 7. Link Distribution Check
        if internal_links_count < 1:
            recommendations.append("Consider adding 1-3 internal links to relevant existing TrendBlogo articles.")
        if external_links_count < 1:
            recommendations.append("Add at least 1 authoritative external citation (e.g. W3C, Wikipedia, official docs).")

        # 8. Readability Score (Flesch Reading Ease estimate)
        sentences = max(len(re.split(r"[.!?]+", content)), 1)
        avg_sentence_len = total_words / sentences
        readability_rating = "Excellent" if avg_sentence_len < 20 else ("Good" if avg_sentence_len < 25 else "Dense")

        final_score = max(0.0, min(100.0, score))
        is_passed = final_score >= 80.0 and heading_links_found == 0

        return {
            "score": round(final_score, 1),
            "is_passed": is_passed,
            "readability_rating": readability_rating,
            "total_words": total_words,
            "keyword_density_pct": round(density, 2),
            "keyword_occurrences": kw_phrase_count,
            "heading_links_found": heading_links_found,
            "h2_count": h2_count,
            "in_content_images_count": len(valid_body_images),
            "warnings": warnings,
            "recommendations": recommendations
        }
