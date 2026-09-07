from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(30), default="#4F46E5")
    icon = Column(String(50), default="folder")
    created_at = Column(DateTime, default=datetime.utcnow)

    articles = relationship("Article", back_populates="category")

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), unique=True, nullable=False)
    slug = Column(String(80), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    articles = relationship("ArticleTag", back_populates="tag")

class ArticleTag(Base):
    __tablename__ = "article_tags"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    article = relationship("Article", back_populates="tags")
    tag = relationship("Tag", back_populates="articles")

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    primary_keyword = Column(String(150), index=True, nullable=False)
    secondary_keywords = Column(Text, nullable=True)
    search_intent = Column(String(50), default="informational")
    template_type = Column(String(50), default="ultimate_guide")
    
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=False)  # Markdown format
    html_content = Column(Text, nullable=True)  # Rendered HTML
    
    # Visual Assets: Exactly 1 Featured + 3 In-Content Images = 4 Images Total
    featured_image = Column(String(255), nullable=False)
    featured_image_alt = Column(String(255), nullable=False)
    featured_image_caption = Column(String(255), nullable=True)
    
    image_1_url = Column(String(255), nullable=True)
    image_1_alt = Column(String(255), nullable=True)
    image_1_caption = Column(String(255), nullable=True)
    
    image_2_url = Column(String(255), nullable=True)
    image_2_alt = Column(String(255), nullable=True)
    image_2_caption = Column(String(255), nullable=True)
    
    image_3_url = Column(String(255), nullable=True)
    image_3_alt = Column(String(255), nullable=True)
    image_3_caption = Column(String(255), nullable=True)

    # Classification & Attribution
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    author_name = Column(String(100), default="Editorial Team")
    author_slug = Column(String(100), default="editorial-team", index=True)
    
    # Status & Dates
    status = Column(String(30), default="published", index=True)  # draft, published, scheduled
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Metrics
    word_count = Column(Integer, default=0)
    reading_time = Column(Integer, default=5)  # minutes
    view_count = Column(Integer, default=0)

    # SEO & Structured Data
    seo_title = Column(String(150), nullable=True)
    meta_description = Column(String(320), nullable=True)
    canonical_url = Column(String(255), nullable=True)
    og_title = Column(String(150), nullable=True)
    og_description = Column(String(320), nullable=True)
    schema_json = Column(Text, nullable=True)

    # Quality Control
    quality_score = Column(Float, default=95.0)
    quality_report = Column(Text, nullable=True)  # JSON string

    # AI Auto-Blogging & Generation Tracking
    language = Column(String(50), default="English", index=True)
    focus_keyword = Column(String(150), nullable=True)
    ai_generated = Column(Boolean, default=True)
    ai_model = Column(String(80), default="gpt-4o-mini")
    image_model = Column(String(80), default="dall-e-3")
    generation_attempts = Column(Integer, default=1)
    error_message = Column(Text, nullable=True)

    # Search Engine Indexing Status
    indexing_status = Column(String(50), default="pending", index=True) # pending, submitted, indexed, failed
    indexing_requested_at = Column(DateTime, nullable=True)
    indexing_response = Column(Text, nullable=True)
    indexing_service = Column(String(50), nullable=True)

    # Relationships
    category = relationship("Category", back_populates="articles")
    tags = relationship("ArticleTag", back_populates="article", cascade="all, delete-orphan")
    internal_links_out = relationship("InternalLink", foreign_keys="InternalLink.source_article_id", cascade="all, delete-orphan")
    external_links = relationship("ExternalLink", cascade="all, delete-orphan")
