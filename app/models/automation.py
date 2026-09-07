from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from app.database import Base

class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(200), unique=True, index=True, nullable=False)
    language = Column(String(50), default="English", index=True)
    country = Column(String(100), default="United States")
    article_type = Column(String(50), default="informational")
    search_intent = Column(String(50), default="informational")
    target_audience = Column(String(100), default="General Professional")
    target_word_count = Column(Integer, default=2000)
    publish_status = Column(String(30), default="automatic")  # automatic, draft, scheduled
    schedule_frequency = Column(String(50), default="daily")  # hourly, 3_hours, 6_hours, daily, custom
    max_articles = Column(Integer, default=1)
    articles_generated = Column(Integer, default=0)
    priority = Column(Integer, default=1)
    status = Column(String(30), default="pending", index=True)  # pending, processing, completed, published, failed, paused
    is_paused = Column(Integer, default=0) # 0=Active, 1=Paused
    last_generated_at = Column(DateTime, nullable=True)
    next_scheduled_at = Column(DateTime, nullable=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(200), nullable=False)
    secondary_keywords = Column(Text, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    tone = Column(String(50), default="informative")
    language = Column(String(50), default="English")
    country = Column(String(100), default="United States")
    target_word_count = Column(Integer, default=2000)
    template_type = Column(String(50), default="ultimate_guide")
    publish_mode = Column(String(30), default="automatic") # automatic, published, draft, scheduled
    
    # Execution Tracking
    status = Column(String(30), default="pending", index=True) # pending, queued, generating, image_generating, validating, ready, scheduled, published, failed
    current_step = Column(String(80), default="Initialized")
    progress = Column(Integer, default=0) # 0 to 100
    attempts = Column(Integer, default=0)
    validation_errors = Column(Text, nullable=True)
    
    result_article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, default="Job created.")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AIUsage(Base):
    __tablename__ = "ai_usage"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), default="openai")
    model = Column(String(80), default="gpt-4o-mini")
    operation = Column(String(80), nullable=False)  # article_text, outline, images, qc, seo
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
