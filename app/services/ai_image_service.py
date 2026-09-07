import os
import re
import time
import base64
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings
from app.models.settings import SiteSetting
from app.models.automation import AIUsage

class AIImageService:
    """
    Dedicated AI Image Generation Service powered by OpenAI (DALL-E 3 / DALL-E 2).
    Generates editorial, photorealistic, watermark-free featured visual assets,
    downloads and persists them locally with unique filenames, and handles retries.
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
    def get_image_model(cls, db: Optional[Any] = None) -> str:
        if db:
            try:
                s = db.query(SiteSetting).filter(SiteSetting.key == "image_model").first()
                if s and s.value and s.value.strip():
                    return s.value.strip()
            except Exception:
                pass
        return settings.DALL_E_MODEL or "dall-e-3"

    @classmethod
    def generate_featured_image(
        cls,
        keyword: str,
        title: str,
        slug: str,
        image_prompt: Optional[str] = None,
        language: str = "English",
        alt_text: Optional[str] = None,
        caption: Optional[str] = None,
        db: Optional[Any] = None,
        custom_api_key: Optional[str] = None,
        allow_fallback: bool = True,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Generates and saves a featured image using OpenAI's image generation API.
        Handles downloading, unique file persistence, alt-text generation, and retries.
        """
        from openai import OpenAI

        api_key = (custom_api_key or "").strip() or cls.get_api_key(db)
        image_model = cls.get_image_model(db)

        if not api_key or not api_key.startswith("sk-"):
            raise ValueError(
                "OpenAI API Key is required for image generation. Please configure it in Admin Settings (/admin/settings)."
            )

        client = OpenAI(api_key=api_key, timeout=60.0)
        os.makedirs(settings.UPLOADS_DIR, exist_ok=True)

        # Build refined prompt if not provided
        if not image_prompt or len(image_prompt.strip()) < 10:
            image_prompt = (
                f"An authentic, candid real-world editorial photograph representing '{keyword}'. "
                f"Natural bright daylight, tangible physical textures, real environment, genuine perspective. "
                f"Shot on a 35mm lens, realistic depth of field. "
                f"Strictly a real photograph: zero CGI, zero 3D rendering, zero cartoon, zero text, zero watermarks, zero logos."
            )
        else:
            # Ensure no text/logo directive is reinforced
            if "zero text" not in image_prompt.lower():
                image_prompt += " Strictly a clean editorial photograph: zero text, zero words, zero watermark, zero logos, natural sunlight."

        # Truncate prompt if exceeds DALL-E limit (1000 chars for DALL-E 2, 4000 for DALL-E 3)
        clean_prompt = image_prompt[:1000].strip()

        img_bytes = None
        last_error = None
        used_model = image_model

        # Attempt generation with exponential backoff retries
        candidate_models = [image_model]
        if image_model != "dall-e-2":
            candidate_models.append("dall-e-2")

        for attempt in range(1, max_retries + 1):
            for model_cand in candidate_models:
                try:
                    # Request 1024x1024 image
                    resp = client.images.generate(
                        model=model_cand,
                        prompt=clean_prompt,
                        n=1,
                        size="1024x1024"
                    )
                    used_model = model_cand
                    item = resp.data[0]
                    b64_data = getattr(item, "b64_json", None)
                    img_url = getattr(item, "url", None)

                    if b64_data:
                        img_bytes = base64.b64decode(b64_data)
                        break
                    elif img_url:
                        req_dl = urllib.request.Request(img_url, headers={"User-Agent": "TrendBlogo/2.0"})
                        with urllib.request.urlopen(req_dl, timeout=30.0) as dl:
                            img_bytes = dl.read()
                        break
                except Exception as e_gen:
                    last_error = e_gen
                    time.sleep(1.0 * attempt)

            if img_bytes:
                break

        if not img_bytes:
            if allow_fallback:
                # Use high-fidelity SVG fallback so the article is not blocked
                from app.services.image_service import ImageService
                filename = f"{slug}-featured.svg"
                svg_code = ImageService.render_fallback_svg(filename)
                svg_path = settings.UPLOADS_DIR / filename
                with open(svg_path, "w", encoding="utf-8") as f_svg:
                    f_svg.write(svg_code)

                # Mirror to static uploads
                for m_dir in [settings.BASE_DIR / "static" / "uploads", settings.BASE_DIR / "app" / "static" / "uploads"]:
                    try:
                        m_dir.mkdir(parents=True, exist_ok=True)
                        with open(m_dir / filename, "w", encoding="utf-8") as f_m:
                            f_m.write(svg_code)
                    except Exception:
                        pass

                return {
                    "success": True,
                    "url": f"/static/uploads/{filename}",
                    "filename": filename,
                    "file_path": str(svg_path),
                    "alt": alt_text or f"{title} - Featured Cover",
                    "caption": caption or f"Editorial overview of {keyword}",
                    "model": "vector_fallback",
                    "is_fallback": True,
                    "error_notice": str(last_error) if last_error else None
                }
            else:
                raise RuntimeError(
                    f"OpenAI Image Generation failed after {max_retries} attempts: {last_error}"
                )

        # Save downloaded PNG
        filename = f"{slug}-featured.png"
        file_path = settings.UPLOADS_DIR / filename
        with open(file_path, "wb") as f_out:
            f_out.write(img_bytes)

        # Mirror file to static uploads directories
        for m_dir in [settings.BASE_DIR / "static" / "uploads", settings.BASE_DIR / "app" / "static" / "uploads"]:
            try:
                m_dir.mkdir(parents=True, exist_ok=True)
                with open(m_dir / filename, "wb") as f_m:
                    f_m.write(img_bytes)
            except Exception:
                pass

        # Log AI Image usage
        if db:
            try:
                img_cost = 0.040 if "dall-e-3" in used_model else 0.020
                ai_log = AIUsage(
                    provider="openai",
                    model=used_model,
                    operation="image_generation",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    estimated_cost=img_cost
                )
                db.add(ai_log)
                db.commit()
            except Exception:
                pass

        return {
            "success": True,
            "url": f"/static/uploads/{filename}",
            "filename": filename,
            "file_path": str(file_path),
            "alt": alt_text or f"{title} - Editorial Photography",
            "caption": caption or f"Real-world documentary analysis of {keyword}",
            "prompt": clean_prompt,
            "model": used_model,
            "is_fallback": False
        }
