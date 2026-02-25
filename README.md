# ⚙️ The Difference Engine

AI-assisted fiction production system that generates novel chapters in YOUR voice.

## What It Does

The Difference Engine takes three inputs:
1. **A Bible** — your novel's world, characters, voice rules, and chapter beats
2. **A Baseline** — your existing writing, analyzed across 14 voice metrics
3. **Chapter beats** — what happens in the chapter you want to produce

It then generates a chapter that matches your voice fingerprint, running every draft through a quality gate that catches AI-isms (purple prose, smoothing words, repetitive rhythm, on-the-nose dialogue) and rewrites until it passes.

## Getting Started

### 1. Build Your Bible

Use the **Bible Builder** — open [claude.ai](https://claude.ai) and paste in the [Bible Builder prompt](BIBLE_BUILDER_PROMPT.md). Upload your notes and writing samples, and Claude will walk you through creating a structured bible document.

### 2. Visit the App

Go to the deployed app and enter your username. Create a project, upload your bible, upload 3-5 chapters of your writing, build your baseline, and hit produce.

### 3. Produce Chapters

Select a chapter from your bible, hit produce, and wait 2-3 minutes. Review the quality score, voice delta, and chapter text. Download or iterate.

## Tech Stack

- **Streamlit** — web interface
- **Supabase** — database (bibles, baselines, chapters persist between sessions)  
- **Anthropic Claude** — chapter generation
- **Python** — style analysis, quality gate, pipeline orchestration

## Local Development

```bash
pip install -r requirements.txt

# Create .streamlit/secrets.toml:
# ANTHROPIC_API_KEY = "sk-ant-..."
# SUPABASE_URL = "https://xxxx.supabase.co"
# SUPABASE_KEY = "your-key-here"

streamlit run streamlit_app.py
```
