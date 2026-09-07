import re
import hashlib
from typing import Dict, Any, List

class KeywordAnalyzer:
    CATEGORY_KEYWORDS = {
        "Tech": [
            "python async cloud backend architecture", "tech", "technology", "backend architecture"
        ],
        "Health": [
            "health", "fitness", "diet", "nutrition", "workout", "weight", "wellness",
            "mental", "sleep", "medical", "doctor", "yoga", "exercise", "supplement",
            "skincare", "skin", "muscle", "disease", "pain", "therapy", "remedy",
            "cardio", "gut", "immune", "organic", "calorie", "fasting", "longevity", "intermittent"
        ],
        "News": [
            "breaking report on global inflation and market policy", "news", "breaking",
            "update", "report", "election", "politics", "global", "summit", "policy",
            "regulation", "market policy", "inflation", "economy", "crisis", "press"
        ],
        "Lifestyle": [
            "minimalist remote home office design and routine", "lifestyle", "travel", "home",
            "routine", "productivity", "habit", "decor", "interior", "fashion", "style",
            "mindful", "remote work", "hobbies", "relationships", "family", "parenting",
            "cooking", "recipe", "coffee", "minimalism", "minimalist", "budget", "living", "life"
        ],
        "Artificial Intelligence": [
            "ai", "artificial intelligence", "machine learning", "deep learning", "neural network",
            "llm", "large language model", "chatgpt", "gpt-4", "gpt", "gemini", "claude",
            "agent", "agents", "multi-agent", "swarm", "nlp", "computer vision", "generative ai",
            "transformer", "prompt engineering", "langchain", "llama", "diffusion", "rag"
        ],
        "Software & Apps": [
            "software", "app", "apps", "application", "windows", "macos", "linux", "tool",
            "web dev", "web development", "programming", "python", "javascript",
            "typescript", "react", "nextjs", "docker", "kubernetes", "api", "git", "github",
            "ide", "vscode", "terminal", "algorithm", "database", "postgres", "redis"
        ],
        "Smartphones": [
            "smartphone", "smartphones", "phone", "phones", "iphone", "android", "ios",
            "pixel", "galaxy", "snapdragon", "bionic", "mobile", "samsung", "apple",
            "oneplus", "cellular", "5g", "sim", "esim", "oled", "camera phone"
        ],
        "Laptops & Hardware": [
            "laptop", "laptops", "hardware", "computer", "pc", "desktop", "macbook",
            "gpu", "cpu", "processor", "nvidia", "amd", "intel", "motherboard",
            "monitor", "ram", "ssd", "gadget", "gadgets", "gaming", "steam deck", "keyboard"
        ],
        "Cybersecurity": [
            "cybersecurity", "security", "malware", "ransomware", "hacker", "phishing",
            "vulnerability", "cve", "firewall", "encryption", "zero-day", "infosec",
            "penetration testing", "vpn", "antivirus", "breach", "zero trust", "auth"
        ],
        "Cloud Computing & SaaS": [
            "cloud", "saas", "aws", "azure", "gcp", "serverless", "devops", "microservices",
            "infrastructure", "b2b saas", "cloud storage", "database as a service", "hosting"
        ],
        "How-To Guides": [
            "how to", "how-to", "tutorial", "step by step", "guide", "walkthrough",
            "troubleshooting", "fix", "error", "solve", "install", "setup", "configure", "benchmark"
        ],
        "Reviews & Comparisons": [
            "review", "reviews", "vs", "versus", "comparison", "compare", "best", "top",
            "worth it", "benchmark", "pros and cons", "alternatives", "tested"
        ],
        "Tech News": [
            "launch", "announced", "release", "leak", "rumor", "spec", "specs",
            "conference", "keynote", "quarterly"
        ]
    }

    INTENT_KEYWORDS = {
        "transactional": ["buy", "discount", "pricing", "cost", "cheap", "deal", "order", "coupon"],
        "commercial": ["best", "top", "review", "vs", "versus", "comparison", "alternative", "recommended"],
        "how_to": ["how to", "step by step", "guide", "tutorial", "build", "create", "setup", "install"],
        "informational": ["what is", "why", "benefits", "strategies", "tips", "types", "examples", "guide"]
    }


    @classmethod
    def analyze(cls, keyword: str, secondary_keywords: List[str] = None) -> Dict[str, Any]:
        kw_clean = keyword.strip().lower()
        
        # Determine intent
        intent = "informational"
        for potential_intent, triggers in cls.INTENT_KEYWORDS.items():
            if any(trigger in kw_clean for trigger in triggers):
                intent = potential_intent
                break
        
        # Determine template
        if "best" in kw_clean or "top" in kw_clean or "list" in kw_clean:
            template = "listicle"
        elif "vs" in kw_clean or "versus" in kw_clean or "comparison" in kw_clean:
            template = "comparison"
        elif "how to" in kw_clean or "tutorial" in kw_clean:
            template = "how_to"
        elif "review" in kw_clean:
            template = "review"
        else:
            template = "ultimate_guide"

        # Determine target audience
        audience = "Tech-forward professionals, entrepreneurs, and digital teams"
        if any(w in kw_clean for w in ["beginner", "student", "starter"]):
            audience = "Beginners and learners looking for actionable fundamentals"
        elif any(w in kw_clean for w in ["enterprise", "scale", "architect", "developer"]):
            audience = "Enterprise leaders, developers, and technical decision-makers"

        # Generate structured heading outline
        outline = cls._generate_outline(keyword, intent, template)

        # Generate clean slug
        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", kw_clean)
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")

        # Detect suggested category
        detected_category = cls.detect_category_name(keyword)

        return {
            "primary_keyword": keyword.strip(),
            "secondary_keywords": secondary_keywords or [],
            "search_intent": intent,
            "template_type": template,
            "target_audience": audience,
            "suggested_slug": slug,
            "suggested_category": detected_category,
            "outline": outline
        }

    @classmethod
    def detect_category_name(cls, keyword: str) -> str:
        kw = keyword.lower().strip()
        
        # 1. Exact word boundary match
        for cat_name, triggers in cls.CATEGORY_KEYWORDS.items():
            if any(re.search(r"\b" + re.escape(tr) + r"\b", kw) for tr in triggers):
                return cat_name
                
        # 2. Substring match
        for cat_name, triggers in cls.CATEGORY_KEYWORDS.items():
            if any(tr in kw for tr in triggers):
                return cat_name

        # 3. Dynamic smart category extraction if noun present
        stop_words = {"best", "top", "guide", "tutorial", "tips", "review", "for", "the", "and", "with", "from", "how", "what"}
        words = [w for w in re.findall(r"[a-zA-Z]+", kw) if len(w) > 3 and w not in stop_words]
        if words:
            candidate = words[0].capitalize()
            if len(candidate) <= 15:
                return candidate

        return "Artificial Intelligence"

    @classmethod
    def resolve_or_create_category(cls, db, keyword: str):
        from app.models.article import Category
        cat_name = cls.detect_category_name(keyword)

        # Look up existing category by name
        cat = db.query(Category).filter(Category.name.ilike(cat_name.strip())).first()
        if cat:
            return cat

        # Check by slug
        clean_slug = re.sub(r"[^a-zA-Z0-9-]", "", cat_name.lower().replace(" ", "-")).strip("-")
        cat = db.query(Category).filter(Category.slug == clean_slug).first()
        if cat:
            return cat

        # Auto-create the category if not found!
        colors = ["#2563EB", "#10B981", "#DC2626", "#8B5CF6", "#F59E0B", "#06B6D4", "#EC4899"]
        color_idx = int(hashlib.md5(cat_name.encode()).hexdigest(), 16) % len(colors)

        new_cat = Category(
            name=cat_name,
            slug=clean_slug,
            description=f"Curated analysis, dispatches, and tactical frameworks exploring {cat_name.lower()}.",
            color=colors[color_idx]
        )
        db.add(new_cat)
        db.commit()
        db.refresh(new_cat)
        return new_cat

    @classmethod
    def _generate_outline(cls, keyword: str, intent: str, template: str) -> List[Dict[str, Any]]:
        kw_cap = keyword.title()
        
        if template == "listicle":
            return [
                {
                    "h2": f"Understanding {kw_cap}: An Industry Overview",
                    "h3_list": ["The Evolution of Current Solutions", "Key Selection Criteria"],
                    "h4_list": ["Performance Benchmarks", "Core Architectural Parameters"],
                    "h5_list": ["Measurement Protocols", "Efficiency Thresholds"],
                    "semantic_keywords": [f"{keyword} overview", f"modern {keyword}", "selection criteria", "evaluation metrics"]
                },
                {
                    "h2": f"Top Recommended Options for {kw_cap}",
                    "h3_list": ["Feature Breakdown & Core Capabilities", "Performance Benchmarks & Usability"],
                    "h4_list": ["Reliability and Durability Testing", "Cost vs Long-Term Value"],
                    "h5_list": ["Material & Engineering Standards", "Real-World User Feedback"],
                    "semantic_keywords": [f"best {keyword}", f"{keyword} features", "performance benchmark", "pros and cons"]
                },
                {
                    "h2": f"Implementation Blueprint and Practical Guide",
                    "h3_list": ["Step-by-Step Selection Guide", "Avoiding Common Pitfalls"],
                    "h4_list": ["Initial Setup Considerations", "Workflow Integration Checklist"],
                    "h5_list": ["Safety Guidelines", "Optimization Tips"],
                    "semantic_keywords": [f"{keyword} setup", f"how to use {keyword}", "practical guide", "common mistakes"]
                },
                {
                    "h2": f"Comparative Evaluation and Value Matrix",
                    "h3_list": ["Cost vs ROI Analysis", "Long-Term Reliability Factors"],
                    "h4_list": ["Entry-Level vs High-End Models", "Maintenance and Lifecycle"],
                    "h5_list": ["Warranty Coverage", "Upgrade Considerations"],
                    "semantic_keywords": [f"{keyword} comparison", f"{keyword} pricing", "roi analysis", "value matrix"]
                },
                {
                    "h2": f"Frequently Asked Questions About {kw_cap}",
                    "h3_list": [f"What makes the best {kw_cap}?", f"How do I choose the right {kw_cap} for my needs?"],
                    "h4_list": ["Maintenance and Upkeep Questions", "Troubleshooting Common Issues"],
                    "h5_list": ["Expert Answers", "Practical Reference"],
                    "semantic_keywords": [f"{keyword} faq", f"{keyword} guide", "expert answers", "buying advice"]
                },
                {
                    "h2": "Final Takeaways and Expert Recommendation",
                    "h3_list": ["Key Highlights Recap", "Our Top Pick"],
                    "h4_list": ["Summary of Findings", "Next Steps"],
                    "h5_list": ["Final Verdict", "Action Checklist"],
                    "semantic_keywords": ["expert recommendation", "final verdict", "summary", "buying decision"]
                }
            ]
        elif template == "comparison":
            return [
                {
                    "h2": f"Executive Summary: {kw_cap}",
                    "h3_list": ["Core Philosophy and Architecture", "Target Use Cases"],
                    "h4_list": ["Key Differentiators", "Market Positioning"],
                    "h5_list": ["Baseline Metrics", "Audience Fit"],
                    "semantic_keywords": [f"{keyword} comparison", f"{keyword} overview", "market analysis", "use cases"]
                },
                {
                    "h2": "Feature-by-Feature Deep Dive",
                    "h3_list": ["Efficiency and Productivity Gains", "User Experience and Learning Curve"],
                    "h4_list": ["Functional Capabilities", "Design and Ergonomics"],
                    "h5_list": ["Interface Responsiveness", "User Satisfaction Scores"],
                    "semantic_keywords": ["feature breakdown", "user experience", "performance comparison", "functionality"]
                },
                {
                    "h2": "Pricing, Licensing, and Total Cost of Ownership",
                    "h3_list": ["Direct Costs vs Hidden Overheads", "Resource Allocation"],
                    "h4_list": ["Subscription vs Upfront Cost", "Long-Term Maintenance Cost"],
                    "h5_list": ["Discount Tiers", "Return on Investment"],
                    "semantic_keywords": ["pricing comparison", "total cost of ownership", "budget considerations", "value assessment"]
                },
                {
                    "h2": "Decision Framework: Which Solution Fits Your Workflow?",
                    "h3_list": ["When to Choose Option A", "When to Choose Option B"],
                    "h4_list": ["Team and Scale Requirements", "Budget Constraints"],
                    "h5_list": ["Decision Matrix Checklist", "Migration Factors"],
                    "semantic_keywords": ["decision matrix", "buying guide", "best choice", "recommendations"]
                },
                {
                    "h2": f"Frequently Asked Questions About {kw_cap}",
                    "h3_list": ["Which option offers better long-term durability?", "How do the warranties compare?"],
                    "h4_list": ["Compatibility Questions", "Support and Service"],
                    "h5_list": ["Expert Answers", "Practical Clarifications"],
                    "semantic_keywords": [f"{keyword} faq", "comparison faq", "expert answers", "troubleshooting"]
                },
                {
                    "h2": "Final Verdict",
                    "h3_list": ["Overall Winner", "Situational Recommendations"],
                    "h4_list": ["Category Best", "Budget Pick"],
                    "h5_list": ["Final Verdict Statement", "Summary"],
                    "semantic_keywords": ["final verdict", "overall winner", "recommendation", "concluding thoughts"]
                }
            ]
        else: # Ultimate Guide / How-To
            return [
                {
                    "h2": f"Foundations of {kw_cap}",
                    "h3_list": ["Core Principles and Definitions", "Why It Matters in Today's Digital Landscape"],
                    "h4_list": ["Essential Background Concepts", "Key Factors Driving Adoption"],
                    "h5_list": ["Historical Context", "Primary Terminology"],
                    "semantic_keywords": [f"what is {keyword}", f"{keyword} basics", "fundamentals", "essential principles"]
                },
                {
                    "h2": f"Strategic Framework for Mastering {kw_cap}",
                    "h3_list": ["Key Architecture & Components", "Workflow Optimization Tactics"],
                    "h4_list": ["System Components Breakdown", "Performance Drivers"],
                    "h5_list": ["Execution Mechanics", "Optimization Criteria"],
                    "semantic_keywords": [f"{keyword} strategies", f"{keyword} framework", "best practices", "workflow"]
                },
                {
                    "h2": f"Best Practices and Practical Execution",
                    "h3_list": ["Actionable Step-by-Step Methodology", "Quality Assurance and Monitoring"],
                    "h4_list": ["Pre-Implementation Checklist", "Execution Protocol"],
                    "h5_list": ["Verification Metrics", "Common Mistakes to Avoid"],
                    "semantic_keywords": [f"how to use {keyword}", "step by step guide", "execution checklist", "quality assurance"]
                },
                {
                    "h2": "Advanced Tactics and Emerging Trends",
                    "h3_list": ["Automation & Efficiency Multipliers", "Future-Proofing Your Approach"],
                    "h4_list": ["Cutting-Edge Techniques", "Industry Innovations"],
                    "h5_list": ["Near-Term Developments", "Long-Term Trajectory"],
                    "semantic_keywords": [f"{keyword} trends", "advanced tactics", "future proofing", "industry insights"]
                },
                {
                    "h2": f"Frequently Asked Questions About {kw_cap}",
                    "h3_list": [f"What is the most effective approach to {kw_cap}?", f"How long does it take to see results with {kw_cap}?"],
                    "h4_list": ["Practical Guidance Queries", "Troubleshooting Advice"],
                    "h5_list": ["Expert Answers", "Practical Details"],
                    "semantic_keywords": [f"{keyword} questions", f"{keyword} faq", "expert answers", "guidance"]
                },
                {
                    "h2": "Summary and Next Steps",
                    "h3_list": ["Key Takeaways Recap", "Recommended Action Plan"],
                    "h4_list": ["Implementation Timeline", "Resource Checklist"],
                    "h5_list": ["Final Words", "Action Items"],
                    "semantic_keywords": ["key takeaways", "action plan", "summary", "next steps"]
                }
            ]
