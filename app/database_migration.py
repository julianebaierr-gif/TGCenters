import sqlite3
from pathlib import Path
from app.database import engine, Base
from app.config import settings
from app.models.settings import IndexingLog

def run_migrations():
    """
    Safely inspects existing database schema and non-destructively adds
    new columns required for AI Auto-Blogging and Indexing.
    Creates any new tables if not already existing.
    """
    # 1. Create all declarative tables (e.g. indexing_logs) if they don't exist
    Base.metadata.create_all(bind=engine)

    # 2. Check and alter existing SQLite tables if needed
    db_path = None
    db_url = str(settings.DATABASE_URL)
    if db_url.startswith("sqlite:///"):
        raw_path = db_url.replace("sqlite:///", "")
        db_path = Path(raw_path)

    if not db_path or not db_path.exists():
        print("Database initialized via SQLAlchemy Base.metadata.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Column additions for 'articles' table
    article_columns = [
        ("language", "VARCHAR(50) DEFAULT 'English'"),
        ("focus_keyword", "VARCHAR(150)"),
        ("ai_generated", "BOOLEAN DEFAULT 1"),
        ("ai_model", "VARCHAR(80) DEFAULT 'gpt-4o-mini'"),
        ("image_model", "VARCHAR(80) DEFAULT 'dall-e-3'"),
        ("generation_attempts", "INTEGER DEFAULT 1"),
        ("error_message", "TEXT"),
        ("indexing_status", "VARCHAR(50) DEFAULT 'pending'"),
        ("indexing_requested_at", "DATETIME"),
        ("indexing_response", "TEXT"),
        ("indexing_service", "VARCHAR(50)"),
    ]

    cursor.execute("PRAGMA table_info(articles)")
    existing_article_cols = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in article_columns:
        if col_name not in existing_article_cols:
            try:
                cursor.execute(f"ALTER TABLE articles ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name} to articles table.")
            except Exception as e:
                print(f"Notice adding {col_name} to articles: {e}")

    # Column additions for 'keywords' table
    keyword_columns = [
        ("language", "VARCHAR(50) DEFAULT 'English'"),
        ("country", "VARCHAR(100) DEFAULT 'United States'"),
        ("article_type", "VARCHAR(50) DEFAULT 'informational'"),
        ("target_word_count", "INTEGER DEFAULT 2000"),
        ("publish_status", "VARCHAR(30) DEFAULT 'automatic'"),
        ("schedule_frequency", "VARCHAR(50) DEFAULT 'daily'"),
        ("max_articles", "INTEGER DEFAULT 1"),
        ("articles_generated", "INTEGER DEFAULT 0"),
        ("is_paused", "INTEGER DEFAULT 0"),
        ("last_generated_at", "DATETIME"),
        ("next_scheduled_at", "DATETIME"),
    ]

    cursor.execute("PRAGMA table_info(keywords)")
    existing_kw_cols = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in keyword_columns:
        if col_name not in existing_kw_cols:
            try:
                cursor.execute(f"ALTER TABLE keywords ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name} to keywords table.")
            except Exception as e:
                print(f"Notice adding {col_name} to keywords: {e}")

    # Column additions for 'generation_jobs' table
    job_columns = [
        ("language", "VARCHAR(50) DEFAULT 'English'"),
        ("country", "VARCHAR(100) DEFAULT 'United States'"),
        ("publish_mode", "VARCHAR(30) DEFAULT 'automatic'"),
        ("attempts", "INTEGER DEFAULT 0"),
        ("validation_errors", "TEXT"),
    ]

    cursor.execute("PRAGMA table_info(generation_jobs)")
    existing_job_cols = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in job_columns:
        if col_name not in existing_job_cols:
            try:
                cursor.execute(f"ALTER TABLE generation_jobs ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name} to generation_jobs table.")
            except Exception as e:
                print(f"Notice adding {col_name} to generation_jobs: {e}")

    conn.commit()
    conn.close()
    print("Database migrations applied successfully.")

if __name__ == "__main__":
    run_migrations()
