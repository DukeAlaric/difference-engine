"""
engine/pipeline.py — Real production pipeline for the Difference Engine.
Calls Claude API to generate chapters based on bible, baseline, and beats.
"""

import re
import random
import anthropic
import streamlit as st


def get_anthropic_client():
    return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])


def build_baseline(corpus_text):
    """Analyze corpus and return voice metrics."""
    words = corpus_text.split()
    word_count = len(words)
    sentences = [s.strip() for s in re.split(r'[.!?]+', corpus_text) if s.strip()]
    num_sentences = max(len(sentences), 1)
    avg_sl = word_count / num_sentences
    paragraphs = [p.strip() for p in corpus_text.split('\n\n') if p.strip()]
    fragments = sum(1 for s in sentences if len(s.split()) < 5)
    em_dashes = corpus_text.count('\u2014') + corpus_text.count('--')
    dialogue_lines = len(re.findall(r'"[^"]*"', corpus_text))

    # Sentence length standard deviation
    lengths = [len(s.split()) for s in sentences]
    mean_len = sum(lengths) / max(len(lengths), 1)
    variance = sum((l - mean_len) ** 2 for l in lengths) / max(len(lengths), 1)
    stdev = variance ** 0.5

    # Adverb count (rough — words ending in -ly)
    adverbs = sum(1 for w in words if w.lower().endswith('ly') and len(w) > 3)

    # Smoothing words
    smoothing_words = ['however', 'moreover', 'furthermore', 'nevertheless',
                       'nonetheless', 'meanwhile', 'consequently', 'therefore',
                       'indeed', 'certainly', 'naturally', 'obviously',
                       'of course', 'in fact', 'as a matter of fact']
    text_lower = corpus_text.lower()
    smoothing_count = sum(text_lower.count(w) for w in smoothing_words)

    # Said ratio
    dialogue_tags = len(re.findall(r'\b(said|asked|replied|whispered|shouted|muttered|called|cried|answered)\b',
                                    corpus_text, re.IGNORECASE))
    said_count = len(re.findall(r'\bsaid\b', corpus_text, re.IGNORECASE))
    said_ratio = (said_count / max(dialogue_tags, 1)) * 100

    # Name openers (sentences starting with a capitalized name-like word followed by verb)
    sentence_starts = [s.split()[0] if s.split() else '' for s in sentences]
    name_like = sum(1 for w in sentence_starts if w and w[0].isupper() and len(w) > 1
                    and w.lower() not in ['the', 'a', 'an', 'it', 'he', 'she', 'they',
                                           'we', 'i', 'this', 'that', 'there', 'when',
                                           'where', 'what', 'how', 'but', 'and', 'so',
                                           'if', 'as', 'in', 'on', 'at', 'for', 'to',
                                           'his', 'her', 'my', 'our', 'its', 'no',
                                           'not', 'all', 'one', 'two', 'some', 'any',
                                           'every', 'each', 'after', 'before', 'now',
                                           'then', 'just', 'even', 'still', 'with'])
    name_opener_pct = (name_like / num_sentences) * 100

    # Interiority (thought verbs)
    thought_verbs = len(re.findall(
        r'\b(thought|wondered|realized|knew|felt|remembered|imagined|hoped|feared|wished|believed|supposed|figured|guessed)\b',
        corpus_text, re.IGNORECASE))
    interiority_pct = (thought_verbs / num_sentences) * 100

    return {
        "avg_sentence_length": round(avg_sl, 1),
        "sentence_length_stdev": round(stdev, 1),
        "fragment_pct": round((fragments / num_sentences) * 100, 1),
        "dialogue_ratio_pct": round((dialogue_lines / max(len(corpus_text.split('\n')), 1)) * 100, 1),
        "avg_paragraph_length": round(word_count / max(len(paragraphs), 1), 1),
        "em_dash_per_1k": round((em_dashes / max(word_count, 1)) * 1000, 1),
        "semicolon_per_1k": round((corpus_text.count(';') / max(word_count, 1)) * 1000, 1),
        "exclamation_per_1k": round((corpus_text.count('!') / max(word_count, 1)) * 1000, 1),
        "question_per_1k": round((corpus_text.count('?') / max(word_count, 1)) * 1000, 1),
        "interiority_pct": round(interiority_pct, 1),
        "adverb_per_1k": round((adverbs / max(word_count, 1)) * 1000, 1),
        "smoothing_per_1k": round((smoothing_count / max(word_count, 1)) * 1000, 1),
        "name_opener_pct": round(name_opener_pct, 1),
        "said_ratio_pct": round(said_ratio, 1),
        "corpus_word_count": word_count
    }


def produce_chapter(bible_text, baseline_metrics, chapter_beats, scene_type, config=None):
    """
    Produce a chapter by calling Claude API.
    
    Three stages:
    1. Draft — generate initial chapter from bible + beats
    2. Rewrite — corrective pass for voice compliance
    3. Quality check — analyze the output
    """
    client = get_anthropic_client()
    
    # Build the voice target string from baseline
    voice_targets = []
    for metric, value in baseline_metrics.items():
        label = metric.replace("_", " ").replace("pct", "%").replace("per 1k", "/1k")
        voice_targets.append(f"  - {label}: {value}")
    voice_target_str = "\n".join(voice_targets)

    # ---- STAGE 1: DRAFT ----
    draft_prompt = f"""You are a fiction ghostwriter. Your job is to write a chapter of a novel 
based on the project bible and chapter beats below. Write in the author's voice as described 
in the voice guide and style brief.

PROJECT BIBLE:
{bible_text}

CHAPTER TO WRITE:
{chapter_beats}

Scene type: {scene_type}

VOICE TARGETS (match these metrics from the author's existing writing):
{voice_target_str}

CRITICAL RULES:
- Write ONLY the chapter prose. No headers, no meta-commentary, no "Chapter 1:" label.
- Match the sentence rhythm described in the Voice Guide.
- Follow ALL rules in the Style Brief exactly.
- Use "said" for 70%+ of dialogue tags. Use action beats for the rest. No creative tags.
- NO em-dashes. Use periods and sentence fragments instead.
- NO adverbs after dialogue tags.
- NO smoothing words (however, moreover, furthermore, nevertheless, indeed, certainly, naturally, obviously).
- NO purple prose. Concrete sensory details only.
- NO words from the NEVER list in the Style Brief.
- Hit the target word count specified in the beats.
- End the chapter exactly as the beats describe.

Write the chapter now. Prose only."""

    draft_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": draft_prompt}]
    )
    
    draft_text = draft_response.content[0].text
    draft_input_tokens = draft_response.usage.input_tokens
    draft_output_tokens = draft_response.usage.output_tokens

    # ---- STAGE 2: CORRECTIVE REWRITE ----
    rewrite_prompt = f"""You are a fiction editor. Below is a draft chapter and the author's voice targets.
Your job is to rewrite the chapter to better match the author's voice while preserving the story content.

DRAFT:
{draft_text}

VOICE TARGETS:
{voice_target_str}

STYLE RULES FROM THE BIBLE:
- Em-dashes: NONE. Zero. Replace any em-dashes with periods and sentence fragments.
- Semicolons: No. Replace with periods.
- Adverbs: Almost none. Cut any adverb that doesn't earn its place.
- "said" for 70%+ of dialogue tags. Cut creative tags (growled, hissed, muttered) — replace with said or action beats.
- NO smoothing words: however, moreover, furthermore, nevertheless, indeed, certainly, naturally, obviously, of course, in fact.
- NO banned words: delve, tapestry, something was off, the weight of, a chill ran down, little did he know, unbeknownst, whilst, amidst.
- Sentence fragments: Use frequently in action and fear sequences.
- Concrete sensory details: Name specific trees (loblolly pine, cypress), birds, sounds. Not just "a tree."
- Interiority: Blend Jesse's thoughts into narration naturally. When scared, shorter fragments.

REWRITE OBJECTIVES:
1. Remove every em-dash. Replace with period + new sentence or sentence fragment.
2. Remove every smoothing word. Restructure the sentence without it.
3. Replace creative dialogue tags with "said" or action beats.
4. Cut adverbs. Let verbs carry the weight.
5. Vary sentence length — mix short punchy with longer rolling sentences. Avoid monotonous rhythm.
6. Ensure the ending matches what the beats specify.

Output ONLY the rewritten chapter. No commentary."""

    rewrite_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": rewrite_prompt}]
    )
    
    final_text = rewrite_response.content[0].text
    rewrite_input_tokens = rewrite_response.usage.input_tokens
    rewrite_output_tokens = rewrite_response.usage.output_tokens

    # ---- STAGE 3: QUALITY CHECK ----
    word_count = len(final_text.split())
    
    # Run local quality checks
    quality_issues = []
    quality_score = 0
    
    # Em-dash check
    em_dash_count = final_text.count('\u2014') + final_text.count('--')
    if em_dash_count > 0:
        quality_issues.append(f"Em-dashes found: {em_dash_count}")
        quality_score += em_dash_count * 2
    
    # Smoothing words check
    smoothing_words = ['however', 'moreover', 'furthermore', 'nevertheless',
                       'nonetheless', 'meanwhile', 'consequently', 'therefore',
                       'indeed', 'certainly', 'naturally', 'obviously']
    text_lower = final_text.lower()
    for sw in smoothing_words:
        count = text_lower.count(sw)
        if count > 0:
            quality_issues.append(f"Smoothing word '{sw}': {count}")
            quality_score += count
    
    # Banned words check
    banned = ['delve', 'tapestry', 'unbeknownst', 'whilst', 'amidst',
              'little did he know', 'a chill ran down', 'the weight of']
    for bw in banned:
        if bw in text_lower:
            quality_issues.append(f"Banned word/phrase: '{bw}'")
            quality_score += 3
    
    # Adverb check (rough)
    words = final_text.split()
    adverbs = [w for w in words if w.lower().endswith('ly') and len(w) > 3]
    adverb_per_1k = (len(adverbs) / max(len(words), 1)) * 1000
    if adverb_per_1k > 8:
        quality_issues.append(f"High adverb density: {adverb_per_1k:.1f}/1k")
        quality_score += 2
    
    # Creative dialogue tags check
    creative_tags = re.findall(r'\b(growled|hissed|muttered|exclaimed|declared|proclaimed|intoned|breathed|purred)\b',
                                final_text, re.IGNORECASE)
    if creative_tags:
        quality_issues.append(f"Creative dialogue tags: {', '.join(set(t.lower() for t in creative_tags))}")
        quality_score += len(set(creative_tags))
    
    # Said ratio
    all_tags = len(re.findall(r'\b(said|asked|replied|whispered|shouted|called|cried|answered|growled|hissed|muttered|exclaimed)\b',
                               final_text, re.IGNORECASE))
    said_count = len(re.findall(r'\bsaid\b', final_text, re.IGNORECASE))
    said_ratio = (said_count / max(all_tags, 1)) * 100
    
    # Sentence rhythm check
    sentences = [s.strip() for s in re.split(r'[.!?]+', final_text) if s.strip()]
    sent_lengths = [len(s.split()) for s in sentences]
    if sent_lengths:
        mean_sl = sum(sent_lengths) / len(sent_lengths)
        variance = sum((l - mean_sl) ** 2 for l in sent_lengths) / len(sent_lengths)
        stdev = variance ** 0.5
        if stdev < 3:
            quality_issues.append(f"Low sentence length variance: {stdev:.1f} (monotonous rhythm)")
            quality_score += 2

    # Build voice delta
    chapter_metrics = {
        "avg_sentence_length": round(mean_sl, 1) if sent_lengths else 0,
        "sentence_length_stdev": round(stdev, 1) if sent_lengths else 0,
        "fragment_pct": round((sum(1 for l in sent_lengths if l < 5) / max(len(sent_lengths), 1)) * 100, 1),
        "em_dash_per_1k": round((em_dash_count / max(word_count, 1)) * 1000, 1),
        "adverb_per_1k": round(adverb_per_1k, 1),
        "said_ratio_pct": round(said_ratio, 1),
    }
    
    voice_delta = {}
    for metric, chapter_val in chapter_metrics.items():
        baseline_val = baseline_metrics.get(metric, 0)
        if isinstance(baseline_val, (int, float)) and baseline_val > 0:
            drift = abs(chapter_val - baseline_val) / baseline_val
            severity = "ok" if drift < 0.3 else ("drift" if drift < 0.6 else "alarm")
        else:
            severity = "ok"
        voice_delta[metric] = {
            "baseline": baseline_val,
            "chapter": chapter_val,
            "severity": severity
        }

    # Total tokens and cost
    total_input = draft_input_tokens + rewrite_input_tokens
    total_output = draft_output_tokens + rewrite_output_tokens
    cost = (total_input / 1_000_000 * 3) + (total_output / 1_000_000 * 15)

    return {
        "chapter_text": final_text,
        "word_count": word_count,
        "quality_score": quality_score,
        "quality_report": {
            "total_score": quality_score,
            "issues": quality_issues,
            "em_dashes": em_dash_count,
            "adverb_per_1k": round(adverb_per_1k, 1),
            "said_ratio_pct": round(said_ratio, 1),
            "word_count": word_count
        },
        "voice_delta": voice_delta,
        "hotspots": [],
        "manifest": {
            "pipeline_version": "web-v1",
            "scene_type": scene_type,
            "stages": ["draft", "rewrite", "quality_check"],
            "model": "claude-sonnet-4-20250514",
            "total_input_tokens": total_input,
            "total_output_tokens": total_output
        },
        "api_usage": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost": round(cost, 4)
        }
    }
