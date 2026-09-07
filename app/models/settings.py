from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from app.database import Base

class SiteSetting(Base):
    __tablename__ = "site_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False)
    description = Column(String(255), nullable=True)
    category = Column(String(50), default="general")  # general, seo, api, appearance, legal
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), default="INFO")  # INFO, WARNING, ERROR, SUCCESS
    source = Column(String(80), nullable=False) # AI_ENGINE, IMAGE_GEN, QUEUE, AUTH, SEO
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class HomepageSection(Base):
    __tablename__ = "homepage_sections"

    id = Column(Integer, primary_key=True, index=True)
    section_key = Column(String(60), unique=True, index=True, nullable=False)
    title = Column(String(120), nullable=False)
    subtitle = Column(String(255), nullable=True)
    is_enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    category_slug = Column(String(80), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class IndexingLog(Base):
    __tablename__ = "indexing_logs"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, nullable=True)
    url = Column(String(255), nullable=False)
    service = Column(String(50), default="indexnow")  # indexnow, google, bing, sitemap_ping
    status = Column(String(30), default="submitted")   # submitted, success, failed
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

