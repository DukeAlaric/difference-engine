"""
storage.py — Supabase persistence layer for the Difference Engine web app.

All database operations go through this module.
The engine/ code never touches the database directly.
"""

from supabase import create_client
import streamlit as st
import json
from datetime import datetime, timezone


DEFAULT_BIBLE_TEMPLATE = """# Project: My Novel

## World Rules
- Setting: [describe your world — time period, location, key details]
- Tone: [dark? whimsical? literary? gritty?]
- [add world rules, constraints, social structures]

## Characters

### [Character Name]
- Role: [protagonist/antagonist/etc.]
- Want: [what they want more than anything]
- Obstacle: [what's stopping them]
- Voice: [how they speak — verbal tics, vocabulary, dialect]
- Thinking: [how they process the world — analytical? emotional? impulsive?]
- Arc: [where they start → where they end]

## Voice Guide
- Sentence rhythm: [short and punchy? long and layered? volatile mix?]
- Dialogue style: [naturalistic? formal? subtext-heavy?]
- POV: [first person / close third / omniscient]
- Tense: [past / present]
- Internal monologue: [italicized? integrated? stream-of-consciousness?]
- Fragment usage: [frequent / occasional / rare]
- Comp voices: [authors your style resembles]

## Style Brief
- Em-dashes: [none / rare / frequent]
- Semicolons: [yes / no]
- Adverbs: [strict (almost none) / relaxed]
- NEVER use: [banned words and phrases]
- ALWAYS: [positive style rules]

## Chapter Beats

### Chapter 1: [Title]
scene_type: [reflective/social_confrontation/action/intimate/procedural]
- Beat 1: [what happens]
- Beat 2: [what happens]
- Beat 3: [what happens]
- Ending: [how it ends, what carries forward]
- Target word count: [range, e.g., 3000-4000]
"""


def get_client():
    """Get or create Supabase client, cached per session."""
    if "supabase_client" not in st.session_state:
        st.session_state.supabase_client = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )
    return st.session_state.supabase_client


# --- Users ---

def get_or_create_user(username: str) -> dict:
    """Get existing user or create new one. Returns user row."""
    db = get_client()
    result = db.table("users").select("*").eq("username", username).execute()
    if result.data:
        return result.data[0]
    result = db.table("users").insert({"username": username}).execute()
    return result.data[0]


# --- Projects ---

def get_user_projects(user_id: str) -> list:
    """Get all projects for a user."""
    db = get_client()
    result = db.table("projects").select("*").eq("user_id", user_id).order("created_at").execute()
    return result.data


def create_project(user_id: str, name: str) -> dict:
    """Create a new project with an empty bible."""
    db = get_client()
    result = db.table("projects").insert({"user_id": user_id, "name": name}).execute()
    project = result.data[0]
    # Create empty bible for this project
    db.table("bibles").insert({
        "project_id": project["id"],
        "content": DEFAULT_BIBLE_TEMPLATE
    }).execute()
    return project


def delete_project(project_id: str):
    """Delete a project and all its data (cascades)."""
    db = get_client()
    db.table("projects").delete().eq("id", project_id).execute()


# --- Bible ---

def get_bible(project_id: str) -> str:
    """Get bible content for a project."""
    db = get_client()
    result = db.table("bibles").select("content").eq("project_id", project_id).execute()
    if result.data:
        return result.data[0]["content"]
    return DEFAULT_BIBLE_TEMPLATE


def save_bible(project_id: str, content: str):
    """Save bible content. Creates or updates."""
    db = get_client()
    db.table("bibles").upsert({
        "project_id": project_id,
        "content": content,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }, on_conflict="project_id").execute()


# --- Baseline ---

def get_baseline(project_id: str) -> dict | None:
    """Get baseline metrics for a project, or None if not built."""
    db = get_client()
    result = db.table("baselines").select("*").eq("project_id", project_id).execute()
    if result.data:
        row = result.data[0]
        if isinstance(row.get("metrics"), str):
            row["metrics"] = json.loads(row["metrics"])
        return row
    return None


def save_baseline(project_id: str, metrics: dict, word_count: int):
    """Save or update baseline metrics."""
    db = get_client()
    db.table("baselines").upsert({
        "project_id": project_id,
        "metrics": metrics,
        "corpus_word_count": word_count,
        "built_at": datetime.now(timezone.utc).isoformat()
    }, on_conflict="project_id").execute()


# --- Corpus Files ---

def get_corpus_files(project_id: str) -> list:
    """Get all uploaded writing samples for a project."""
    db = get_client()
    result = db.table("corpus_files").select("*").eq("project_id", project_id).order("uploaded_at").execute()
    return result.data


def add_corpus_file(project_id: str, filename: str, content: str, word_count: int):
    """Add an uploaded writing sample."""
    db = get_client()
    db.table("corpus_files").insert({
        "project_id": project_id,
        "filename": filename,
        "content": content,
        "word_count": word_count
    }).execute()


def delete_corpus_file(file_id: str):
    """Delete a corpus file."""
    db = get_client()
    db.table("corpus_files").delete().eq("id", file_id).execute()


# --- Chapters ---

def get_chapters(project_id: str) -> list:
    """Get all produced chapters for a project, latest versions first."""
    db = get_client()
    result = (db.table("chapters").select("*")
              .eq("project_id", project_id)
              .order("chapter_key")
              .order("version", desc=True)
              .execute())
    return result.data


def get_chapter(project_id: str, chapter_key: str, version: int = None) -> dict | None:
    """Get a specific chapter. Latest version if version not specified."""
    db = get_client()
    query = (db.table("chapters").select("*")
             .eq("project_id", project_id)
             .eq("chapter_key", chapter_key))
    if version:
        query = query.eq("version", version)
    else:
        query = query.order("version", desc=True).limit(1)
    result = query.execute()
    if result.data:
        row = result.data[0]
        for field in ("quality_report", "voice_delta", "hotspots", "manifest"):
            if isinstance(row.get(field), str):
                row[field] = json.loads(row[field])
        return row
    return None


def save_chapter(project_id: str, chapter_key: str, chapter_title: str,
                 content: str, word_count: int, quality_score: int,
                 quality_report: dict, voice_delta: dict, hotspots: list,
                 manifest: dict):
    """Save a new chapter version."""
    db = get_client()
    existing = (db.table("chapters").select("version")
                .eq("project_id", project_id)
                .eq("chapter_key", chapter_key)
                .order("version", desc=True)
                .limit(1).execute())
    version = (existing.data[0]["version"] + 1) if existing.data else 1

    db.table("chapters").insert({
        "project_id": project_id,
        "chapter_key": chapter_key,
        "chapter_title": chapter_title,
        "version": version,
        "content": content,
        "word_count": word_count,
        "quality_score": quality_score,
        "quality_report": quality_report,
        "voice_delta": voice_delta,
        "hotspots": hotspots,
        "manifest": manifest
    }).execute()


# --- API Usage ---

def log_api_usage(project_id: str, chapter_key: str,
                  input_tokens: int, output_tokens: int, cost: float):
    """Log API usage for cost tracking."""
    db = get_client()
    db.table("api_usage").insert({
        "project_id": project_id,
        "chapter_key": chapter_key,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": cost
    }).execute()


def get_project_cost(project_id: str) -> float:
    """Get total API cost for a project."""
    db = get_client()
    result = db.table("api_usage").select("estimated_cost").eq("project_id", project_id).execute()
    return sum(float(row["estimated_cost"]) for row in result.data)


def get_total_cost() -> float:
    """Get total API cost across all projects."""
    db = get_client()
    result = db.table("api_usage").select("estimated_cost").execute()
    return sum(float(row["estimated_cost"]) for row in result.data)
