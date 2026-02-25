"""
engine/pipeline.py — Stub pipeline for the web app.

REPLACE THIS with your real engine code. This stub provides:
1. analyze_corpus() — basic style metrics from text (works standalone)
2. produce_from_text() — calls Claude API to generate a chapter
3. parse_chapter_beats() — extracts chapter list from bible markdown

The real engine has: multi-stage pipeline, corrective rewrite, 
post-processing, quality gate, voice delta comparison, etc.
This stub generates chapters with a single API call so you can 
test the web app end-to-end before wiring in the full pipeline.
"""

import re
import json
import anthropic
import streamlit as st
from collections import Counter


# ---------------------------------------------------------------------------
# Style Analyzer (simplified but functional)
# ---------------------------------------------------------------------------

def analyze_corpus(text: str) -> dict:
    """
    Analyze a corpus of text and return voice metrics.
    
    This is a simplified version of the full style analyzer.
    Replace with engine/style.py when wiring in the real pipeline.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s for s in sentences if len(s.strip()) > 0]
    words = text.split()
    paragraphs = [p for p in text.split('\n\n') if p.strip()]
    
    # Sentence lengths
    sent_lengths = [len(s.split()) for s in sentences]
    avg_sent_len = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0
    
    # Sentence length variance (rhythm volatility)
    if len(sent_lengths) > 1:
        mean = avg_sent_len
        variance = sum((x - mean) ** 2 for x in sent_lengths) / len(sent_lengths)
        std_dev = variance ** 0.5
    else:
        std_dev = 0
    
    # Dialogue ratio
    dialogue_lines = len(re.findall(r'["""].*?["""]', text))
    dialogue_ratio = (dialogue_lines / len(sentences) * 100) if sentences else 0
    
    # Fragment ratio (sentences < 5 words)
    fragments = sum(1 for l in sent_lengths if l < 5)
    fragment_ratio = (fragments / len(sentences) * 100) if sentences else 0
    
    # Average paragraph length
    para_lengths = [len(p.split()) for p in paragraphs]
    avg_para_len = sum(para_lengths) / len(para_lengths) if para_lengths else 0
    
    # Em-dash count per 1000 words
    em_dash_count = text.count('—') + text.count('--')
    em_dash_per_1k = (em_dash_count / len(words) * 1000) if words else 0
    
    # Semicolons per 1000 words
    semicolon_count = text.count(';')
    semicolons_per_1k = (semicolon_count / len(words) * 1000) if words else 0
    
    # Adverb density (rough: words ending in -ly)
    adverbs = sum(1 for w in words if w.lower().endswith('ly') and len(w) > 3)
    adverb_per_1k = (adverbs / len(words) * 1000) if words else 0
    
    # Interiority ratio (rough: sentences with thought verbs)
    thought_verbs = ['thought', 'wondered', 'realized', 'knew', 'felt', 'believed', 
                     'considered', 'imagined', 'remembered', 'supposed']
    interiority = sum(1 for s in sentences if any(v in s.lower() for v in thought_verbs))
    interiority_pct = (interiority / len(sentences) * 100) if sentences else 0
    
    # Smoothing words per 1000 words
    smoothing = ['however', 'moreover', 'furthermore', 'nevertheless', 'nonetheless',
                 'consequently', 'accordingly', 'indeed', 'certainly', 'undoubtedly',
                 'meanwhile', 'subsequently']
    smooth_count = sum(1 for w in words if w.lower().strip('.,;:') in smoothing)
    smoothing_per_1k = (smooth_count / len(words) * 1000) if words else 0
    
    # Vocabulary richness (type-token ratio on first 1000 words)
    sample = [w.lower().strip('.,;:!?"\'') for w in words[:1000]]
    ttr = len(set(sample)) / len(sample) if sample else 0
    
    return {
        "avg_sentence_length": round(avg_sent_len, 1),
        "sentence_length_std": round(std_dev, 1),
        "dialogue_ratio_pct": round(dialogue_ratio, 1),
        "fragment_ratio_pct": round(fragment_ratio, 1),
        "avg_paragraph_length": round(avg_para_len, 1),
        "em_dashes_per_1k": round(em_dash_per_1k, 2),
        "semicolons_per_1k": round(semicolons_per_1k, 2),
        "adverbs_per_1k": round(adverb_per_1k, 1),
        "interiority_pct": round(interiority_pct, 1),
        "smoothing_per_1k": round(smoothing_per_1k, 2),
        "vocabulary_richness": round(ttr, 3),
        "total_words": len(words),
        "total_sentences": len(sentences),
        "total_paragraphs": len(paragraphs)
    }


# ---------------------------------------------------------------------------
# Bible Parser
# ---------------------------------------------------------------------------

def parse_chapter_beats(bible_text: str) -> list[dict]:
    """
    Extract chapter beats from bible markdown.
    Returns list of dicts with chapter_key, title, scene_type, beats.
    """
    chapters = []
    
    # Match ### Chapter N: Title patterns
    pattern = r'###\s+Chapter\s+(\d+)\s*:\s*(.+?)(?:\n|$)'
    matches = list(re.finditer(pattern, bible_text))
    
    for i, match in enumerate(matches):
        num = match.group(1).strip()
        title = match.group(2).strip()
        
        # Extract the text between this chapter header and the next
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(bible_text)
        block = bible_text[start:end]
        
        # Extract scene_type
        scene_match = re.search(r'scene_type:\s*(\w+)', block)
        scene_type = scene_match.group(1) if scene_match else "procedural"
        
        # Extract beats
        beats = re.findall(r'-\s+Beat\s+\d+:\s*(.+)', block)
        
        # Extract ending
        ending_match = re.search(r'-\s+Ending:\s*(.+)', block)
        ending = ending_match.group(1) if ending_match else ""
        
        # Extract target word count
        wc_match = re.search(r'-\s+Target\s+word\s+count:\s*(.+)', block)
        target_wc = wc_match.group(1) if wc_match else "3000-4000"
        
        chapters.append({
            "chapter_key": f"chapter{num.zfill(2)}",
            "title": title,
            "scene_type": scene_type,
            "beats": beats,
            "ending": ending,
            "target_word_count": target_wc
        })
    
    return chapters


# ---------------------------------------------------------------------------
# Chapter Production (stub — replace with full pipeline)
# ---------------------------------------------------------------------------

def produce_from_text(bible_text: str, baseline: dict, chapter_info: dict,
                      corpus_text: str = "") -> dict:
    """
    Produce a chapter using the Difference Engine pipeline.
    
    STUB VERSION: Makes a single Claude API call with bible + baseline context.
    Replace with the full multi-stage pipeline (draft → rewrite → postprocess 
    → quality gate) when wiring in the real engine.
    
    Args:
        bible_text: Full bible markdown
        baseline: Baseline metrics dict
        chapter_info: Dict from parse_chapter_beats() for this chapter
        corpus_text: Sample of the author's writing (for voice reference)
    
    Returns:
        Dict with chapter_text, word_count, quality_score, quality_report,
        voice_delta, hotspots, manifest, api_usage
    """
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    
    # Build the prompt
    metrics_str = "\n".join(f"  {k}: {v}" for k, v in baseline.get("metrics", {}).items())
    beats_str = "\n".join(f"  - {b}" for b in chapter_info.get("beats", []))
    
    system_prompt = f"""You are a fiction ghostwriter. You must write in the author's voice, 
not in generic AI prose. Here is the author's voice profile:

BASELINE METRICS:
{metrics_str}

STYLE RULES FROM BIBLE:
{bible_text}

{f'AUTHOR WRITING SAMPLE (match this voice):{chr(10)}{corpus_text[:3000]}' if corpus_text else ''}

CRITICAL RULES:
- NO em-dashes (—) unless the style brief explicitly allows them
- NO smoothing words (however, moreover, furthermore, nevertheless, etc.)
- Match the author's sentence rhythm — vary sentence lengths dramatically
- Match the author's dialogue style
- No purple prose, no "AI voice"
- Write the chapter, nothing else. No preamble, no commentary."""

    user_prompt = f"""Write Chapter {chapter_info.get('title', 'Untitled')}.

Scene type: {chapter_info.get('scene_type', 'procedural')}

Beats:
{beats_str}

Ending: {chapter_info.get('ending', '')}

Target word count: {chapter_info.get('target_word_count', '3000-4000')}

Write the complete chapter now."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    chapter_text = response.content[0].text
    word_count = len(chapter_text.split())
    
    # Analyze the output
    output_metrics = analyze_corpus(chapter_text)
    
    # Build voice delta (compare output to baseline)
    voice_delta = {}
    baseline_metrics = baseline.get("metrics", {})
    for key in baseline_metrics:
        if key in output_metrics and key not in ("total_words", "total_sentences", "total_paragraphs"):
            base_val = baseline_metrics[key]
            out_val = output_metrics[key]
            if isinstance(base_val, (int, float)) and base_val != 0:
                drift = abs(out_val - base_val) / base_val * 100
            else:
                drift = 0
            voice_delta[key] = {
                "baseline": base_val,
                "output": out_val,
                "drift_pct": round(drift, 1),
                "status": "ok" if drift < 25 else "DRIFT" if drift < 50 else "SEVERE"
            }
    
    # Simple quality score (count issues)
    quality_issues = []
    em_dashes = chapter_text.count('—')
    if em_dashes > 0:
        quality_issues.append(f"Em-dashes found: {em_dashes}")
    
    smoothing_words = ['however', 'moreover', 'furthermore', 'nevertheless',
                       'nonetheless', 'consequently', 'indeed', 'certainly']
    for w in smoothing_words:
        count = len(re.findall(rf'\b{w}\b', chapter_text, re.IGNORECASE))
        if count > 0:
            quality_issues.append(f"Smoothing word '{w}': {count}")
    
    drift_count = sum(1 for v in voice_delta.values() if v["status"] in ("DRIFT", "SEVERE"))
    quality_score = len(quality_issues) * 2 + drift_count * 3
    
    # API usage
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (input_tokens / 1_000_000 * 3) + (output_tokens / 1_000_000 * 15)
    
    return {
        "chapter_text": chapter_text,
        "word_count": word_count,
        "quality_score": quality_score,
        "quality_report": {
            "issues": quality_issues,
            "output_metrics": output_metrics
        },
        "voice_delta": voice_delta,
        "hotspots": [],  # Full pipeline has detailed hotspot detection
        "manifest": {
            "chapter_key": chapter_info["chapter_key"],
            "chapter_title": chapter_info.get("title", ""),
            "scene_type": chapter_info.get("scene_type", ""),
            "model": "claude-sonnet-4-20250514",
            "pipeline": "stub-v1"
        },
        "api_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": round(cost, 4)
        }
    }
