"""
streamlit_app.py — Difference Engine Web Interface
"""

import streamlit as st
import json
import re
import storage
from engine.pipeline import build_baseline, produce_chapter

# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Difference Engine",
    page_icon="⚙️",
    layout="wide"
)

st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .score-good { color: #28a745; font-size: 2em; font-weight: bold; }
    .score-ok { color: #ffc107; font-size: 2em; font-weight: bold; }
    .score-bad { color: #dc3545; font-size: 2em; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_uploaded_file(f) -> str:
    content = f.read()
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def parse_chapter_beats(bible_text: str) -> list[dict]:
    """Parse chapter beats from bible markdown."""
    chapters = []
    pattern = r'###\s+Chapter\s+(\d+)[:\s\u2014\u2013\-]+\s*(.+?)(?=\n)'
    matches = list(re.finditer(pattern, bible_text, re.IGNORECASE))

    for i, match in enumerate(matches):
        num = match.group(1).strip()
        title = match.group(2).strip()
        chapter_key = f"chapter{num.zfill(2)}"

        # Extract section text until next chapter heading or next ## heading
        start = match.end()
        if i + 1 < len(matches):
            section = bible_text[start:matches[i + 1].start()]
        else:
            # Go until next ## heading or end of file
            next_h2 = re.search(r'\n##\s', bible_text[start:])
            section = bible_text[start:start + next_h2.start()] if next_h2 else bible_text[start:]

        # Extract scene_type
        scene_match = re.search(r'scene_type:\s*(\w+)', section, re.IGNORECASE)
        scene_type = scene_match.group(1) if scene_match else "reflective"

        # Extract beats
        beats = re.findall(r'-\s+Beat\s+\d+:\s*(.+)', section)

        # Extract ending
        ending_match = re.search(r'-\s+Ending:\s*(.+)', section)
        ending = ending_match.group(1).strip() if ending_match else ""

        # Extract target word count
        wc_match = re.search(r'Target word count:\s*(.+)', section)
        target_wc = wc_match.group(1).strip() if wc_match else "800-1000"

        chapters.append({
            "chapter_key": chapter_key,
            "title": title,
            "scene_type": scene_type,
            "beats": beats,
            "ending": ending,
            "target_word_count": target_wc,
            "raw_section": section.strip()
        })

    return chapters


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
        content = read_uploaded_file(uploaded)
        if content.strip():
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
        if isinstance(metrics, str):
            metrics = json.loads(metrics)

        st.markdown("#### Voice Fingerprint")
        rows = []
        for key, val in metrics.items():
            label = key.replace("_", " ").replace("pct", "%").replace("per 1k", "/1k").title()
            rows.append({"Metric": label, "Value": val})
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
        existing_names = {f["filename"] for f in corpus}
        new_files = [f for f in uploaded if f.name not in existing_names]
        if new_files:
            for file in new_files:
                content = read_uploaded_file(file)
                word_count = len(content.split())
                storage.add_corpus_file(project["id"], file.name, content, word_count)
            st.rerun()

    # Build baseline
    st.markdown("---")
    if total_words >= 5000:
        if st.button("🔬 Build Baseline", type="primary", use_container_width=True):
            with st.spinner("Analyzing your voice across 14 metrics..."):
                all_text = "\n\n".join(f["content"] for f in corpus)
                metrics = build_baseline(all_text)
                word_count = metrics.pop("corpus_word_count", total_words)
                storage.save_baseline(project["id"], metrics, word_count)
            st.success("Baseline built!")
            st.rerun()
    elif corpus:
        remaining = 5000 - total_words
        st.warning(f"Need at least 5,000 words. Currently: {total_words:,} ({remaining:,} more needed)")
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
        progress = st.progress(0, text="Starting pipeline...")

        try:
            metrics = baseline["metrics"]
            if isinstance(metrics, str):
                metrics = json.loads(metrics)

            progress.progress(10, text="Building prompt...")
            progress.progress(30, text="Generating chapter...")

            result = produce_chapter(
                bible_text=bible_content,
                baseline_metrics=metrics,
                chapter_beats=chapter_info["raw_section"],
                scene_type=chapter_info["scene_type"]
            )

            progress.progress(80, text="Saving results...")

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

            usage = result.get("api_usage", {})
            if usage.get("cost", 0) > 0:
                storage.log_api_usage(
                    project["id"], chapter_info["chapter_key"],
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                    usage.get("cost", 0)
                )

            progress.progress(100, text="Complete!")

            # Display results
            score = result["quality_score"]
            if score <= 4:
                score_class = "score-good"
            elif score <= 10:
                score_class = "score-ok"
            else:
                score_class = "score-bad"

            st.markdown(f'<div class="{score_class}">Quality Score: {score}</div>',
                        unsafe_allow_html=True)
            st.caption(f"{result['word_count']:,} words")

            # Voice delta
            if result.get("voice_delta"):
                with st.expander("📊 Voice Delta", expanded=True):
                    delta_rows = []
                    for metric, data in result["voice_delta"].items():
                        if isinstance(data, dict):
                            delta_rows.append({
                                "Metric": metric.replace("_", " ").title(),
                                "Baseline": data.get("baseline", "—"),
                                "Chapter": data.get("chapter", "—"),
                                "Severity": data.get("severity", "—")
                            })
                    if delta_rows:
                        st.table(delta_rows)

            # Chapter text
            st.markdown("---")
            st.markdown("#### Chapter Text")
            st.text_area("", value=result["chapter_text"], height=400,
                         label_visibility="collapsed", disabled=True)

            st.download_button(
                "📥 Download as .md",
                data=result["chapter_text"],
                file_name=f"{chapter_info['chapter_key']}.md",
                mime="text/markdown"
            )

        except Exception as e:
            st.error(f"Production failed: {e}")
            import traceback
            st.code(traceback.format_exc())


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
                            "Metric": metric.replace("_", " ").title(),
                            "Baseline": data.get("baseline", ""),
                            "Chapter": data.get("chapter", ""),
                            "Severity": data.get("severity", "")
                        })
                if rows:
                    st.table(rows)

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
