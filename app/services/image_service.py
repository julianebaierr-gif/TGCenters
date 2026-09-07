import os
import re
import random
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from app.config import settings

class ImageService:
    THEME_PALETTES = [
        {"bg1": "#1E1B4B", "bg2": "#312E81", "accent": "#818CF8", "glow": "#C7D2FE", "name": "indigo_nebula"},
        {"bg1": "#0F172A", "bg2": "#1E293B", "accent": "#38BDF8", "glow": "#7DD3FC", "name": "slate_cyan"},
        {"bg1": "#141E30", "bg2": "#243B55", "accent": "#2DD4BF", "glow": "#99F6E4", "name": "teal_flow"},
        {"bg1": "#18181B", "bg2": "#27272A", "accent": "#A855F7", "glow": "#E9D5FF", "name": "violet_deep"},
        {"bg1": "#0C1A30", "bg2": "#1D3557", "accent": "#457B9D", "glow": "#A8DADC", "name": "blue_arctic"},
    ]

    @classmethod
    def generate_image_prompts(
        cls,
        keyword: str,
        title: str,
        outline_sections: List[Dict[str, Any]],
        client: Optional[Any] = None
    ) -> List[Dict[str, str]]:
        """
        Creates exactly 2 prompt specs (1 Featured Hero + 1 In-Article Image).
        Prompts are designed for authentic, photorealistic real-life documentary/street/product photography
        matching the style of genuine snapshots taken in natural sunlight (storefronts, paper plates, concrete sidewalks, real textures).
        """
        # 1. Default fallback photographic prompts (strict real-world documentary aesthetic)
        sec_title = "In-Depth Exploration"
        for s in outline_sections:
            cand = s.get("h2", "").replace("##", "").strip()
            if cand and "FAQ" not in cand and "Takeaway" not in cand and "Verdict" not in cand:
                sec_title = cand
                break

        featured_prompt = (
            f"An authentic, candid real-life photograph capturing the subject '{keyword}'. "
            f"A wide or medium establishing street-level or environmental documentary scene in bright natural daylight. "
            f"Real-world architecture, authentic painted storefront facade with vintage lettering, aged brick, glass window reflections "
            f"showing city street, concrete sidewalk with natural sun shadows, genuine surroundings. "
            f"Captured on an iPhone 15 Pro or 35mm lens, raw unretouched documentary photography, natural colors, realistic depth of field. "
            f"Strictly a real photograph: zero CGI, zero 3D rendering, zero digital illustration, zero cartoon, zero vector graphics, zero sci-fi neon."
        )

        in_article_prompt = (
            f"An authentic, candid close-up tabletop photograph focusing on practical real-life '{keyword}'. "
            f"Resting on a white paper plate or sunlit surface outdoors in direct natural midday sunlight, casting crisp realistic shadows. "
            f"Rich tangible physical textures, visible details, natural background with greenery or everyday environment. "
            f"Casual documentary snapshot taken with a modern smartphone camera in bright daytime. "
            f"Strictly a real photograph: zero 3D graphics, zero digital drawing, zero vector art, zero artificial studio rendering."
        )

        featured_alt = f"{title} - Real World Guide and Analysis"
        featured_caption = f"Authentic perspective and real-world overview of {keyword}."
        in_article_alt = f"{sec_title} - Hands-On Real-World Application"
        in_article_caption = f"Hands-on detail and practical perspective for {sec_title}."

        # 2. If OpenAI client is available, let ChatGPT craft specialized custom photo prompts for this exact topic
        if client:
            try:
                import json
                chat_resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an award-winning documentary photojournalist and commercial street photographer. "
                                "Write two distinct, ultra-realistic real-life photography prompts for OpenAI DALL-E based on the user's article topic and outline.\n\n"
                                "MANDATORY PHOTOGRAPHIC STYLE RULES:\n"
                                "1. Real-World Authentic Photography Only: Must look like a real, raw, candid photograph captured in the real physical world (shot on an iPhone 15 Pro, Leica Q3, or Canon EOS R5 with 35mm/50mm f/1.8 lens in direct natural daylight).\n"
                                "2. Natural Lighting & Shadows: Bright natural sunlight, afternoon sun with soft realistic directional shadows, or natural bright window daylight. Real atmospheric light and organic reflections.\n"
                                "3. Real Textures & Environments: Tangible real-world details — sunlit concrete curbs, aged brick walls, painted wooden storefronts with gold lettering, glass window reflections of city streets, real food on paper plates, wooden tabletops, authentic clothing fabrics, real human hands or people interacting.\n"
                                "4. STRICT PROHIBITIONS: Absolutely NO CGI, NO 3D rendering, NO digital art, NO illustration, NO vector graphics, NO sci-fi glow, NO neon, NO cartoon, NO plastic smoothness, NO artificial studio backdrops.\n\n"
                                "SPECIFICATIONS FOR THE 2 IMAGES:\n"
                                "- Image 1 (Featured Cover / Hero): Wide or medium establishing shot in a real-world setting (e.g. authentic building storefront, street sidewalk scene, workshop, or outdoor environment in natural sunlight).\n"
                                "- Image 2 (In-Article Midpoint): A close-up, tabletop, or hands-on candid detail snapshot showing the physical subject, meal, tool, or product in action (e.g. food on a paper plate, hand holding an item, rich tangible textures, shallow depth of field).\n\n"
                                "Respond with a JSON object:\n"
                                "{\n"
                                '  "featured_prompt": "A real photograph of...",\n'
                                '  "featured_alt": "Detailed descriptive alt text",\n'
                                '  "featured_caption": "Short photojournalistic caption",\n'
                                '  "in_article_prompt": "A close-up real photograph of...",\n'
                                '  "in_article_alt": "Detailed descriptive alt text",\n'
                                '  "in_article_caption": "Short photojournalistic caption"\n'
                                "}"
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Topic / Keyword: {keyword}\nTitle: {title}\nKey Outline Sections: {sec_title}"
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                    timeout=15.0
                )
                data = json.loads(chat_resp.choices[0].message.content)
                if data.get("featured_prompt"):
                    featured_prompt = data["featured_prompt"]
                if data.get("featured_alt"):
                    featured_alt = data["featured_alt"]
                if data.get("featured_caption"):
                    featured_caption = data["featured_caption"]
                if data.get("in_article_prompt"):
                    in_article_prompt = data["in_article_prompt"]
                if data.get("in_article_alt"):
                    in_article_alt = data["in_article_alt"]
                if data.get("in_article_caption"):
                    in_article_caption = data["in_article_caption"]
            except Exception as e_chat:
                pass

        return [
            {
                "type": "featured",
                "section_title": "Featured Hero",
                "prompt": featured_prompt,
                "alt_text": featured_alt,
                "caption": featured_caption
            },
            {
                "type": "in_article_1",
                "section_title": sec_title,
                "prompt": in_article_prompt,
                "alt_text": in_article_alt,
                "caption": in_article_caption
            }
        ]

    @classmethod
    def get_active_credentials(cls, db: Optional[Any] = None) -> Tuple[str, str]:
        from app.models.settings import SiteSetting
        api_key = ""
        provider = "openai"
        if db:
            try:
                s_key = db.query(SiteSetting).filter(SiteSetting.key == "openai_api_key").first()
                if s_key and s_key.value and s_key.value.strip():
                    api_key = s_key.value.strip()
            except Exception:
                pass

        if not api_key:
            try:
                from app.database import SessionLocal
                with SessionLocal() as session:
                    s_key = session.query(SiteSetting).filter(SiteSetting.key == "openai_api_key").first()
                    if s_key and s_key.value and s_key.value.strip():
                        api_key = s_key.value.strip()
            except Exception:
                pass
                
        if not api_key:
            api_key = (settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")).strip()
            
        return api_key, provider

    @classmethod
    def create_article_images(
        cls,
        keyword: str,
        title: str,
        outline_sections: List[Dict[str, Any]],
        slug: str,
        db: Optional[Any] = None,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates exactly 2 unique real-life photographs (1 featured hero + 1 in-article)
        exclusively using the ChatGPT / OpenAI API.
        """
        if api_key and api_key.strip():
            active_key = api_key.strip()
        else:
            active_key, _ = cls.get_active_credentials(db)

        if not active_key or len(active_key) < 8 or not active_key.startswith("sk-"):
            raise ValueError(
                "OpenAI API Key is required for image generation. Please configure your OpenAI API Key in Admin Settings (/admin/settings) or enter your ChatGPT API Key."
            )

        from openai import OpenAI
        import base64
        import urllib.request
        import concurrent.futures

        client = OpenAI(api_key=active_key, timeout=60.0)
        os.makedirs(settings.UPLOADS_DIR, exist_ok=True)

        # Generate custom documentary photo prompts using ChatGPT
        prompt_specs = cls.generate_image_prompts(keyword, title, outline_sections, client=client)
        results = {}

        # Candidate OpenAI image models (prioritize DALL-E 3 for high-fidelity realism)
        candidate_models = ["dall-e-3", "dall-e-2"]

        def _generate_one(spec_with_idx):
            idx, spec = spec_with_idx
            img_type = spec["type"]
            img_prompt = spec["prompt"][:1000]
            img_bytes = None
            last_err = None

            for model_name in candidate_models:
                try:
                    img_resp = client.images.generate(
                        model=model_name,
                        prompt=img_prompt,
                        n=1,
                        size="1024x1024"
                    )
                    item = img_resp.data[0]
                    b64_data = getattr(item, "b64_json", None)
                    img_url = getattr(item, "url", None)

                    if b64_data:
                        img_bytes = base64.b64decode(b64_data)
                        break
                    elif img_url:
                        req_dl = urllib.request.Request(img_url, headers={"User-Agent": "TrendBlogo/2.0"})
                        with urllib.request.urlopen(req_dl, timeout=35.0) as dl_resp:
                            img_bytes = dl_resp.read()
                        break
                except Exception as e_gen:
                    last_err = e_gen
                    continue

            if img_bytes:
                png_filename = f"{slug}-{img_type}.png"
                png_path = settings.UPLOADS_DIR / png_filename
                with open(png_path, "wb") as f_png:
                    f_png.write(img_bytes)

                # Mirror to all static upload locations
                for mirror_dir in [settings.BASE_DIR / "static" / "uploads", settings.BASE_DIR / "app" / "static" / "uploads"]:
                    try:
                        mirror_dir.mkdir(parents=True, exist_ok=True)
                        with open(mirror_dir / png_filename, "wb") as f_m:
                            f_m.write(img_bytes)
                    except Exception:
                        pass

                rel_url = f"/static/uploads/{png_filename}"
                return (img_type, {
                    "url": rel_url,
                    "file_path": str(png_path),
                    "filename": png_filename,
                    "alt": spec["alt_text"],
                    "caption": spec["caption"],
                    "prompt": spec["prompt"]
                })
            else:
                raise RuntimeError(
                    f"Failed to generate real photograph for '{img_type}' via OpenAI API: {last_err}. "
                    f"Please verify that your OpenAI API Key has active image generation credits."
                )

        # Generate the 2 images in parallel (max_workers=2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            task_items = list(enumerate(prompt_specs))
            for img_type, img_meta in executor.map(_generate_one, task_items):
                results[img_type] = img_meta

        return {
            "featured": results.get("featured"),
            "image_1": results.get("in_article_1"),
            "image_2": None,
            "image_3": None,
            "all_images": results
        }


    PALETTES = THEME_PALETTES

    @classmethod
    def _render_vector_image(cls, title: str, subtitle: str, img_type: str, palette: Dict[str, str], idx: int) -> str:
        width = 1200
        height = 630 if img_type == "featured" else 675
        
        clean_title = re.sub(r"[^a-zA-Z0-9\s:,-]", "", title)[:52]
        if len(title) > 52:
            clean_title += "..."

        # Unique motifs for each image
        motif_svg = cls._get_motif_svg(idx, palette)

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" fill="none">
  <defs>
    <linearGradient id="bgGrad_{idx}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{palette['bg1']}" />
      <stop offset="100%" stop-color="{palette['bg2']}" />
    </linearGradient>
    <linearGradient id="accGrad_{idx}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{palette['accent']}" />
      <stop offset="100%" stop-color="{palette['glow']}" />
    </linearGradient>
    <filter id="blurFilter_{idx}" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="60" result="blur" />
    </filter>
    <pattern id="grid_{idx}" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255, 255, 255, 0.05)" stroke-width="1" />
    </pattern>
  </defs>

  <!-- Background Base -->
  <rect width="{width}" height="{height}" fill="url(#bgGrad_{idx})" />
  <rect width="{width}" height="{height}" fill="url(#grid_{idx})" />

  <!-- Ambient Glow Orbs -->
  <circle cx="200" cy="180" r="180" fill="{palette['accent']}" opacity="0.22" filter="url(#blurFilter_{idx})" />
  <circle cx="1000" cy="450" r="220" fill="{palette['glow']}" opacity="0.18" filter="url(#blurFilter_{idx})" />

  <!-- Thematic Center Illustration Graphic -->
  <g transform="translate(620, 100)">
    {motif_svg}
  </g>

  <!-- Content Banner / Overlay Card -->
  <g transform="translate(80, 160)">
    <!-- Category Badge -->
    <rect x="0" y="0" width="220" height="38" rx="8" fill="rgba(255, 255, 255, 0.08)" stroke="rgba(255, 255, 255, 0.15)" />
    <circle cx="24" cy="19" r="6" fill="{palette['accent']}" />
    <text x="40" y="24" font-family="system-ui, -apple-system, sans-serif" font-size="13" font-weight="700" letter-spacing="1.5" fill="{palette['glow']}">{subtitle}</text>

    <!-- Main Title -->
    <text x="0" y="90" font-family="system-ui, -apple-system, sans-serif" font-size="38" font-weight="800" fill="#FFFFFF" letter-spacing="-0.5">{clean_title}</text>
    
    <!-- Meta details -->
    <text x="0" y="145" font-family="system-ui, -apple-system, sans-serif" font-size="16" font-weight="500" fill="rgba(255, 255, 255, 0.65)">TrendBlogo Intelligence ? Automated Editorial Architecture</text>

    <!-- Visual Indicator Line -->
    <rect x="0" y="180" width="120" height="4" rx="2" fill="url(#accGrad_{idx})" />
  </g>

  <!-- Watermark / Brand Badge -->
  <g transform="translate(80, {height - 70})">
    <rect x="0" y="0" width="150" height="32" rx="6" fill="rgba(15, 23, 42, 0.6)" stroke="rgba(255, 255, 255, 0.1)" />
    <text x="14" y="20" font-family="system-ui, -apple-system, sans-serif" font-size="12" font-weight="700" fill="#F8FAFC">TrendBlogo AI</text>
  </g>
</svg>"""
        return svg

    @classmethod
    def _get_motif_svg(cls, idx: int, palette: Dict[str, str]) -> str:
        acc = palette["accent"]
        glow = palette["glow"]
        if idx == 0:  # Featured: Modern Isometric Platform + Growth Spark
            return f"""
            <polygon points="240,40 440,150 240,260 40,150" fill="rgba(255,255,255,0.04)" stroke="{acc}" stroke-width="2" />
            <polygon points="240,90 380,170 240,250 100,170" fill="rgba(255,255,255,0.08)" stroke="{glow}" stroke-width="1.5" />
            <line x1="240" y1="260" x2="240" y2="360" stroke="{acc}" stroke-width="2" stroke-dasharray="6,6" />
            <!-- Floating Data Cubes -->
            <rect x="180" y="100" width="50" height="50" rx="8" fill="{acc}" opacity="0.85" />
            <rect x="270" y="70" width="40" height="40" rx="6" fill="{glow}" opacity="0.9" />
            <circle cx="240" cy="150" r="16" fill="#FFFFFF" />
            <circle cx="240" cy="150" r="32" stroke="{glow}" stroke-width="2" opacity="0.6" />
            """
        elif idx == 1: # Section 1: Network Matrix Nodes
            return f"""
            <circle cx="200" cy="160" r="70" fill="none" stroke="{acc}" stroke-width="2" />
            <circle cx="360" cy="120" r="50" fill="none" stroke="{glow}" stroke-width="2" />
            <circle cx="280" cy="280" r="60" fill="none" stroke="{acc}" stroke-width="1.5" />
            <line x1="200" y1="160" x2="360" y2="120" stroke="{acc}" stroke-width="2" />
            <line x1="360" y1="120" x2="280" y2="280" stroke="{glow}" stroke-width="2" />
            <line x1="280" y1="280" x2="200" y2="160" stroke="{acc}" stroke-width="2" />
            <circle cx="200" cy="160" r="14" fill="{acc}" />
            <circle cx="360" cy="120" r="12" fill="{glow}" />
            <circle cx="280" cy="280" r="16" fill="#FFFFFF" />
            """
        elif idx == 2: # Section 2: Analytical Telemetry Charts
            return f"""
            <rect x="80" y="60" width="360" height="240" rx="14" fill="rgba(255,255,255,0.03)" stroke="{acc}" stroke-width="1.5" />
            <path d="M 110 240 L 170 190 L 230 210 L 290 130 L 350 160 L 410 90" fill="none" stroke="{glow}" stroke-width="4" stroke-linecap="round" />
            <circle cx="410" cy="90" r="6" fill="#FFFFFF" stroke="{acc}" stroke-width="2" />
            <line x1="110" y1="260" x2="410" y2="260" stroke="rgba(255,255,255,0.2)" stroke-width="2" />
            <rect x="140" y="210" width="24" height="50" rx="4" fill="{acc}" opacity="0.4" />
            <rect x="200" y="180" width="24" height="80" rx="4" fill="{acc}" opacity="0.6" />
            <rect x="260" y="140" width="24" height="120" rx="4" fill="{glow}" opacity="0.8" />
            <rect x="320" y="110" width="24" height="150" rx="4" fill="#FFFFFF" opacity="0.9" />
            """
        else: # Section 3: Smart Execution Pipeline
            return f"""
            <rect x="100" y="120" width="100" height="70" rx="10" fill="{acc}" opacity="0.85" />
            <rect x="250" y="120" width="100" height="70" rx="10" fill="{glow}" opacity="0.85" />
            <rect x="400" y="120" width="100" height="70" rx="10" fill="#FFFFFF" opacity="0.95" />
            <path d="M 200 155 L 250 155" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" />
            <path d="M 350 155 L 400 155" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" />
            <circle cx="150" cy="155" r="10" fill="#FFFFFF" />
            <circle cx="300" cy="155" r="10" fill="{acc}" />
            <circle cx="450" cy="155" r="10" fill="{glow}" />
            """

    @classmethod
    def render_fallback_svg(cls, filename: str) -> str:
        """
        Renders a high-resolution, responsive vector SVG card for any article image.
        Guarantees that images never 404 or show broken image icons.
        """
        base_name = filename.rsplit(".", 1)[0]
        is_featured = "featured" in base_name
        clean_name = base_name.replace("-featured", "").replace("-in_article_1", "").replace("-in_article_2", "").replace("-in_article_3", "").replace("-", " ").title()
        
        palettes = [
            {"c1": "#0f172a", "c2": "#1e1b4b", "accent": "#6366f1", "glow": "#818cf8"},
            {"c1": "#0c1a30", "c2": "#064e3b", "accent": "#10b981", "glow": "#34d399"},
            {"c1": "#18181b", "c2": "#31104b", "accent": "#a855f7", "glow": "#c084fc"},
            {"c1": "#0f172a", "c2": "#1e293b", "accent": "#38bdf8", "glow": "#7dd3fc"},
        ]
        import hashlib
        h = int(hashlib.md5(clean_name.encode("utf-8")).hexdigest()[:6], 16)
        pal = palettes[h % len(palettes)]
        
        subtitle = "Editorial Featured Guide" if is_featured else "In-Depth Editorial Visual"
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" width="1200" height="675" style="background:{pal['c1']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{pal['c1']}" />
      <stop offset="60%" stop-color="{pal['c2']}" />
      <stop offset="100%" stop-color="#020617" />
    </linearGradient>
    <linearGradient id="acc" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{pal['accent']}" />
      <stop offset="100%" stop-color="{pal['glow']}" />
    </linearGradient>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="1" />
    </pattern>
  </defs>
  <rect width="1200" height="675" fill="url(#bg)" />
  <rect width="1200" height="675" fill="url(#grid)" />
  <circle cx="1050" cy="150" r="280" fill="{pal['accent']}" opacity="0.12" filter="blur(60px)" />
  <circle cx="150" cy="550" r="220" fill="{pal['glow']}" opacity="0.08" filter="blur(60px)" />
  
  <g transform="translate(100, 180)">
    <!-- Brand Badge -->
    <rect x="0" y="0" width="160" height="34" rx="17" fill="rgba(99,102,241,0.15)" stroke="rgba(129,140,248,0.3)" stroke-width="1" />
    <text x="80" y="22" fill="{pal['glow']}" font-size="12" font-weight="700" text-anchor="middle" letter-spacing="1.5">TRENDBLOGO</text>
    
    <!-- Subtitle / Tag -->
    <text x="180" y="22" fill="rgba(255,255,255,0.5)" font-size="13" font-weight="600" letter-spacing="1">{subtitle.upper()}</text>
    
    <!-- Main Headline -->
    <text x="0" y="110" fill="#ffffff" font-size="52" font-weight="900" letter-spacing="-1">{clean_name}</text>
    <text x="0" y="170" fill="rgba(255,255,255,0.7)" font-size="22" font-weight="400">Expert Reviews, Buying Insights &amp; Comprehensive Comparisons</text>
    
    <!-- Accent Bar -->
    <rect x="0" y="220" width="120" height="6" rx="3" fill="url(#acc)" />
  </g>
  
  <!-- Footer metadata -->
  <text x="100" y="590" fill="rgba(255,255,255,0.4)" font-size="14" font-family="monospace">trendblogo.com • Verified Editorial Review</text>
</svg>'''
        return svg
