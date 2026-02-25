"""
streamlit_app.py — Difference Engine Web Interface

The Difference Engine is an AI-assisted fiction production system that 
generates novel chapters matching the author's voice.
"""

import streamlit as st
import json
import storage
from engine.pipeline import analyze_corpus, parse_chapter_beats, produce_from_text

# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Difference Engine",
    page_icon="⚙️",
    layout="wide"
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .score-good { color: #28a745; font-size: 2em; font-weight: bold; }
    .score-ok { color: #ffc107; font-size: 2em; font-weight: bold; }
    .score-bad { color: #dc3545; font-size: 2em; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login_screen():
    st.title("⚙️ The Difference Engine")
    st.caption("AI-assisted fiction production — write novels in YOUR voice")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Enter your name to get started")
        username = st.text_input("Username:", placeholder="e.g., jane")
        if st.button("Enter", type="primary", use_container_width=True):
            if username and username.strip():
                user = storage.get_or_create_user(username.strip().lower())
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Please enter a username")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar():
    user = st.session_state.user
    
    with st.sidebar:
        st.title("⚙️ Difference Engine")
        st.caption(f"Logged in as **{user['username']}**")
        
        if st.button("Log out", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        st.markdown("---")
        
        projects = storage.get_user_projects(user["id"])
        
        if projects:
            project_names = [p["name"] for p in projects]
            current_idx = 0
            if "project" in st.session_state:
                current_name = st.session_state.project["name"]
                if current_name in project_names:
                    current_idx = project_names.index(current_name)
            
            selected = st.selectbox("📁 Project:", project_names, index=current_idx)
            st.session_state.project = next(p for p in projects if p["name"] == selected)
        
        st.markdown("---")
        new_name = st.text_input("New project name:")
        if st.button("➕ Create Project", use_container_width=True) and new_name:
            try:
                project = storage.create_project(user["id"], new_name.strip())
                st.session_state.project = project
                st.rerun()
            except Exception as e:
                st.error(f"Could not create project: {e}")
        
        st.markdown("---")
        total_cost = storage.get_total_cost()
        st.caption(f"💰 Total API cost: ${total_cost:.2f}")


# ---------------------------------------------------------------------------
# Bible Tab
# ---------------------------------------------------------------------------

def render_bible_tab():
    project = st.session_state.project
    bible_content = storage.get_bible(project["id"])
    
    # File upload
    st.markdown("#### Upload a bible")
    uploaded = st.file_uploader(
        "Upload a .md or .txt bible file (or edit below):",
        type=["md", "txt"],
        key="bible_upload"
    )
    
    if uploaded:
        content = uploaded.read().decode("utf-8")
        storage.save_bible(project["id"], content)
        st.success(f"Uploaded {uploaded.name}!")
        st.rerun()
    
    st.markdown("#### Edit your bible")
    st.caption("Define your world, characters, voice rules, and chapter beats.")
    
    edited = st.text_area(
        "Bible content:",
        value=bible_content,
        height=500,
        label_visibility="collapsed"
    )
    
    if st.button("💾 Save Bible", type="primary"):
        storage.save_bible(project["id"], edited)
        st.success("Bible saved!")
    
    # Preview parsed chapters
    chapters = parse_chapter_beats(edited)
    if chapters:
        st.markdown("---")
        st.markdown(f"**{len(chapters)} chapters detected:**")
        for ch in chapters:
            st.caption(f"📄 {ch['chapter_key']}: {ch['title']} ({ch['scene_type']})")
    else:
        st.info("No chapter beats found yet. Add them under '## Chapter Beats' → '### Chapter 1: Title'")


# ---------------------------------------------------------------------------
# Baseline Tab
# ---------------------------------------------------------------------------

def render_baseline_tab():
    project = st.session_state.project
    
    baseline = storage.get_baseline(project["id"])
    if baseline:
        st.success(f"✅ Baseline built from {baseline['corpus_word_count']:,} words")
        
        metrics = baseline["metrics"]
        st.markdown("#### Voice Fingerprint")
        
        metric_labels = {
            "avg_sentence_length": "Avg sentence length (words)",
            "sentence_length_std": "Sentence length std dev",
            "dialogue_ratio_pct": "Dialogue ratio (%)",
            "fragment_ratio_pct": "Fragment ratio (%)",
            "avg_paragraph_length": "Avg paragraph length (words)",
            "em_dashes_per_1k": "Em-dashes per 1k words",
            "semicolons_per_1k": "Semicolons per 1k words",
            "adverbs_per_1k": "Adverbs per 1k words",
            "interiority_pct": "Interiority (%)",
            "smoothing_per_1k": "Smoothing words per 1k",
            "vocabulary_richness": "Vocabulary richness (TTR)",
        }
        
        rows = []
        for key, label in metric_labels.items():
            if key in metrics:
                rows.append({"Metric": label, "Value": metrics[key]})
        if rows:
            st.table(rows)
        
        st.markdown("---")
    
    # Upload corpus
    st.markdown("#### Upload your writing")
    st.caption("Upload 3-5 chapters or stories in your voice (.txt or .md files).")
    
    corpus = storage.get_corpus_files(project["id"])
    total_words = sum(f["word_count"] for f in corpus)
    
    if corpus:
        st.write(f"**{len(corpus)} files** ({total_words:,} words)")
        for f in corpus:
            col1, col2 = st.columns([5, 1])
            col1.write(f"📄 {f['filename']} ({f['word_count']:,} words)")
            if col2.button("🗑️", key=f"del_{f['id']}"):
                storage.delete_corpus_file(f["id"])
                st.rerun()
    
    uploaded = st.file_uploader(
        "Add writing samples:",
        type=["txt", "md"],
        accept_multiple_files=True,
        key="corpus_upload"
    )
    
    if uploaded:
        for file in uploaded:
            content = file.read().decode("utf-8")
            word_count = len(content.split())
            storage.add_corpus_file(project["id"], file.name, content, word_count)
        st.rerun()
    
    # Build baseline
    st.markdown("---")
    if total_words >= 5000:
        if st.button("🔬 Build Baseline", type="primary"):
            with st.spinner("Analyzing your voice..."):
                all_text = "\n\n".join(f["content"] for f in corpus)
                metrics = analyze_corpus(all_text)
                storage.save_baseline(project["id"], metrics, total_words)
            st.success("Baseline built!")
            st.rerun()
    elif corpus:
        remaining = 5000 - total_words
        st.warning(f"Need at least 5,000 words for a reliable baseline. "
                   f"Currently: {total_words:,} ({remaining:,} more needed)")
    else:
        st.info("Upload some writing samples to get started.")


# ---------------------------------------------------------------------------
# Produce Tab
# ---------------------------------------------------------------------------

def render_produce_tab():
    project = st.session_state.project
    
    baseline = storage.get_baseline(project["id"])
    if not baseline:
        st.warning("⚠️ Build your baseline first (Baseline tab)")
        return
    
    bible_content = storage.get_bible(project["id"])
    if not bible_content or len(bible_content) < 100:
        st.warning("⚠️ Write your bible first (Bible tab)")
        return
    
    chapters = parse_chapter_beats(bible_content)
    if not chapters:
        st.warning("⚠️ No chapter beats found in your bible.")
        return
    
    # Chapter selector
    chapter_options = [f"{ch['chapter_key']}: {ch['title']}" for ch in chapters]
    selected_idx = st.selectbox("Select chapter:", range(len(chapter_options)),
                                format_func=lambda i: chapter_options[i])
    chapter_info = chapters[selected_idx]
    
    # Chapter details
    with st.expander("Chapter details", expanded=True):
        st.write(f"**Scene type:** {chapter_info['scene_type']}")
        st.write(f"**Target:** {chapter_info['target_word_count']} words")
        if chapter_info['beats']:
            for i, beat in enumerate(chapter_info['beats'], 1):
                st.write(f"  {i}. {beat}")
        if chapter_info['ending']:
            st.write(f"**Ending:** {chapter_info['ending']}")
    
    # Existing versions
    existing = storage.get_chapter(project["id"], chapter_info["chapter_key"])
    if existing:
        st.info(f"Previous version exists (v{existing['version']}, score: {existing['quality_score']}). "
                f"Producing again creates a new version.")
    
    # Produce
    if st.button("⚙️ Produce Chapter", type="primary", use_container_width=True):
        corpus = storage.get_corpus_files(project["id"])
        corpus_text = "\n\n".join(f["content"] for f in corpus[:2])
        
        progress = st.progress(0, text="Starting pipeline...")
        
        try:
            progress.progress(10, text="Building prompt...")
            progress.progress(30, text="Generating chapter...")
            
            result = produce_from_text(
                bible_text=bible_content,
                baseline={"metrics": baseline["metrics"]},
                chapter_info=chapter_info,
                corpus_text=corpus_text
            )
            
            progress.progress(80, text="Analyzing quality...")
            
            storage.save_chapter(
                project_id=project["id"],
                chapter_key=chapter_info["chapter_key"],
                chapter_title=chapter_info.get("title", ""),
                content=result["chapter_text"],
                word_count=result["word_count"],
                quality_score=result["quality_score"],
                quality_report=result["quality_report"],
                voice_delta=result["voice_delta"],
                hotspots=result["hotspots"],
                manifest=result["manifest"]
            )
            
            usage = result["api_usage"]
            storage.log_api_usage(
                project["id"], chapter_info["chapter_key"],
                usage["input_tokens"], usage["output_tokens"], usage["cost"]
            )
            
            progress.progress(100, text="Complete!")
            display_chapter_result(result)
            
        except Exception as e:
            st.error(f"Production failed: {e}")
            import traceback
            st.code(traceback.format_exc())


def display_chapter_result(result: dict):
    score = result["quality_score"]
    if score <= 4:
        score_class = "score-good"
    elif score <= 10:
        score_class = "score-ok"
    else:
        score_class = "score-bad"
    
    st.markdown(f'<div class="{score_class}">Quality Score: {score}</div>',
                unsafe_allow_html=True)
    
    st.caption(f"{result['word_count']:,} words | "
               f"Cost: ${result['api_usage']['cost']:.4f}")
    
    # Voice delta
    if result["voice_delta"]:
        with st.expander("📊 Voice Delta", expanded=True):
            rows = []
            for metric, data in result["voice_delta"].items():
                rows.append({
                    "Metric": metric,
                    "Baseline": data["baseline"],
                    "Output": data["output"],
                    "Drift": f"{data['drift_pct']}%",
                    "Status": data["status"]
                })
            st.table(rows)
    
    # Issues
    issues = result.get("quality_report", {}).get("issues", [])
    if issues:
        with st.expander(f"⚠️ Quality Issues ({len(issues)})"):
            for issue in issues:
                st.write(f"- {issue}")
    
    # Chapter text
    st.markdown("---")
    st.markdown("#### Chapter Text")
    st.text_area("", value=result["chapter_text"], height=400,
                 label_visibility="collapsed", disabled=True)
    
    st.download_button(
        "📥 Download as .md",
        data=result["chapter_text"],
        file_name=f"{result['manifest'].get('chapter_key', 'chapter')}.md",
        mime="text/markdown"
    )


# ---------------------------------------------------------------------------
# Chapters Tab
# ---------------------------------------------------------------------------

def render_chapters_tab():
    project = st.session_state.project
    chapters = storage.get_chapters(project["id"])
    
    if not chapters:
        st.info("No chapters produced yet. Go to the **Produce** tab!")
        return
    
    seen = set()
    for ch in chapters:
        key = ch["chapter_key"]
        if key in seen:
            continue
        seen.add(key)
        
        title = ch.get("chapter_title", key)
        score = ch.get("quality_score", "?")
        version = ch.get("version", 1)
        words = ch.get("word_count", 0)
        
        with st.expander(f"📄 {title} (v{version}) — Score: {score} — {words:,} words"):
            delta = ch.get("voice_delta")
            if delta:
                if isinstance(delta, str):
                    delta = json.loads(delta)
                rows = []
                for metric, data in delta.items():
                    if isinstance(data, dict):
                        rows.append({
                            "Metric": metric,
                            "Baseline": data.get("baseline", ""),
                            "Output": data.get("output", ""),
                            "Drift": f"{data.get('drift_pct', 0)}%",
                            "Status": data.get("status", "")
                        })
                if rows:
                    st.table(rows)
            
            report = ch.get("quality_report")
            if report:
                if isinstance(report, str):
                    report = json.loads(report)
                issues = report.get("issues", [])
                if issues:
                    st.write("**Issues:**")
                    for issue in issues:
                        st.write(f"- {issue}")
            
            st.text_area("", value=ch["content"], height=300,
                        label_visibility="collapsed", disabled=True,
                        key=f"ch_text_{ch['id']}")
            
            st.download_button(
                "📥 Download",
                data=ch["content"],
                file_name=f"{key}_v{version}.md",
                mime="text/markdown",
                key=f"dl_{ch['id']}"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if "user" not in st.session_state:
        login_screen()
        return
    
    render_sidebar()
    
    if "project" not in st.session_state:
        st.title("⚙️ The Difference Engine")
        st.info("👈 Create a project in the sidebar to get started")
        return
    
    st.title(f"⚙️ {st.session_state.project['name']}")
    
    tab_bible, tab_baseline, tab_produce, tab_chapters = st.tabs([
        "📖 Bible", "📊 Baseline", "⚙️ Produce", "📄 Chapters"
    ])
    
    with tab_bible:
        render_bible_tab()
    with tab_baseline:
        render_baseline_tab()
    with tab_produce:
        render_produce_tab()
    with tab_chapters:
        render_chapters_tab()


if __name__ == "__main__":
    main()
