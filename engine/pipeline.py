"""
engine/pipeline.py — Full production pipeline for the Difference Engine web app.
VERSION: web-v4 (voice-agnostic)

All style rules now come from the bible, not hardcoded in the pipeline.
Post-processing stages are conditional based on baseline metrics.
Prompts reference the bible for voice/style guidance instead of hardcoding rules.

Stages:
  2. Draft generation (Claude API)
  3. Corrective rewrite (Claude API)
  4.1 Em-dash removal (CONDITIONAL — only if baseline em-dash is 0 or bible says no)
  4.2 Smoothing removal (CONDITIONAL — only if baseline smoothing is low)
  4.3 Opener fix
  4.4 Impact paragraph isolation
  4.5 Paragraph splitter
  5. Quality gate
  6. Voice delta (style-rule-aware)
"""

import re
import math
import anthropic
import streamlit as st


def get_anthropic_client():
    return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SMOOTHING_WORDS = [
    'however', 'moreover', 'furthermore', 'nevertheless', 'nonetheless',
    'consequently', 'therefore', 'indeed', 'certainly', 'naturally',
    'obviously', 'of course', 'in fact', 'as a matter of fact',
    'it is worth noting', 'it should be noted', 'needless to say'
]

SCENE_TYPE_DIALOGUE_TARGETS = {
    "reflective": (0, 15),
    "social_confrontation": (45, 85),
    "action": (0, 40),
    "intimate": (30, 65),
    "procedural": (5, 30),
}

NON_ADVERBS = {'only', 'early', 'family', 'likely', 'belly', 'holy', 'ugly',
               'lonely', 'friendly', 'elderly', 'daily', 'july', 'fly', 'reply',
               'supply', 'ally', 'apply', 'rely', 'sally', 'billy', 'molly',
               'emily', 'lily', 'fully', 'really', 'finally'}

COMMON_STARTERS = {'the', 'a', 'an', 'it', 'he', 'she', 'they', 'we', 'i',
                   'this', 'that', 'there', 'when', 'where', 'what', 'how',
                   'but', 'and', 'so', 'if', 'as', 'in', 'on', 'at', 'for',
                   'to', 'his', 'her', 'my', 'our', 'its', 'no', 'not', 'all',
                   'one', 'two', 'some', 'any', 'every', 'each', 'after',
                   'before', 'now', 'then', 'just', 'even', 'still', 'with',
                   'from', 'by', 'up', 'out', 'down', 'back', 'over', 'through'}

# Contamination words that are ALWAYS bad regardless of voice
ALWAYS_BANNED = ['delve', 'tapestry', 'unbeknownst', 'a tapestry of',
                 'in the tapestry', 'little did he know',
                 'pierced the silence', 'sent shivers', 'etched across',
                 'knuckles whitened']


# ---------------------------------------------------------------------------
# STAGE 1: Baseline
# ---------------------------------------------------------------------------

def build_baseline(corpus_text):
    """Analyze corpus and return 14 voice metrics."""
    words = corpus_text.split()
    word_count = len(words)
    sentences = [s.strip() for s in re.split(r'[.!?]+', corpus_text) if s.strip()]
    num_sentences = max(len(sentences), 1)
    avg_sl = word_count / num_sentences
    paragraphs = [p.strip() for p in corpus_text.split('\n\n') if p.strip()]
    fragments = sum(1 for s in sentences if len(s.split()) < 5)
    em_dashes = corpus_text.count('\u2014') + corpus_text.count('--')
    dialogue_lines = len(re.findall(r'"[^"]*"', corpus_text))

    lengths = [len(s.split()) for s in sentences]
    mean_len = sum(lengths) / max(len(lengths), 1)
    variance = sum((l - mean_len) ** 2 for l in lengths) / max(len(lengths), 1)
    stdev = variance ** 0.5

    adverbs = sum(1 for w in words if w.lower().endswith('ly') and len(w) > 3
                  and w.lower() not in NON_ADVERBS)

    text_lower = corpus_text.lower()
    smoothing_count = sum(text_lower.count(w) for w in SMOOTHING_WORDS)

    all_tags = re.findall(
        r'\b(said|asked|replied|whispered|shouted|muttered|called|cried|answered|'
        r'growled|hissed|exclaimed|declared|snapped|barked|sighed|groaned)\b',
        corpus_text, re.IGNORECASE)
    said_count = sum(1 for t in all_tags if t.lower() == 'said')
    said_ratio = (said_count / max(len(all_tags), 1)) * 100

    sentence_starts = [s.split()[0] if s.split() else '' for s in sentences]
    name_openers = sum(1 for w in sentence_starts
                       if w and w[0].isupper() and len(w) > 1
                       and w.lower() not in COMMON_STARTERS)
    name_opener_pct = (name_openers / num_sentences) * 100

    thought_verbs = len(re.findall(
        r'\b(thought|wondered|realized|knew|felt|remembered|imagined|hoped|'
        r'feared|wished|believed|supposed|figured|guessed)\b',
        corpus_text, re.IGNORECASE))
    interiority_pct = (thought_verbs / num_sentences) * 100

    return {
        "avg_sentence_length": round(avg_sl, 1),
        "sentence_length_stdev": round(stdev, 1),
        "fragment_pct": round((fragments / num_sentences) * 100, 1),
        "dialogue_ratio_pct": round((dialogue_lines / max(len(paragraphs), 1)) * 100, 1),
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


# ---------------------------------------------------------------------------
# STAGE 4.1: Em-dash Removal (CONDITIONAL)
# ---------------------------------------------------------------------------

def remove_em_dashes(text):
    count = 0
    def replace_em(match):
        nonlocal count
        before = match.group(1)
        after = match.group(2)
        count += 1
        if after and after[0].islower():
            return f"{before}. {after[0].upper()}{after[1:]}"
        return f"{before}. {after}"
    text = re.sub(r'(\w+)\s*\u2014\s*(\w+)', replace_em, text)
    text = re.sub(r'(\w+)\s*--\s*(\w+)', replace_em, text)
    remaining = text.count('\u2014') + text.count('--')
    text = text.replace('\u2014', '.').replace('--', '.')
    count += remaining
    return text, count


# ---------------------------------------------------------------------------
# STAGE 4.2: Smoothing Removal (CONDITIONAL)
# ---------------------------------------------------------------------------

def remove_smoothing_words(text):
    count = 0
    for word in SMOOTHING_WORDS:
        text_before = text
        text = re.sub(
            r'(?i)((?:^|\.\s+))' + re.escape(word) + r',?\s*(\w)',
            lambda m: m.group(1) + m.group(2).upper(),
            text, flags=re.MULTILINE
        )
        text = re.sub(r'(?i),?\s*' + re.escape(word) + r',?\s*', ' ', text)
        if text != text_before:
            count += 1
    text = re.sub(r'  +', ' ', text)
    return text, count


# ---------------------------------------------------------------------------
# STAGE 4.3: Opener Fix
# ---------------------------------------------------------------------------

def fix_name_openers(text, target_pct=45.0):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if not sentences:
        return text, 0, 0

    name_opener_indices = []
    for i, s in enumerate(sentences):
        words = s.split()
        if words and words[0][0:1].isupper() and len(words[0]) > 1:
            if words[0].lower() not in COMMON_STARTERS:
                name_opener_indices.append(i)

    current_pct = (len(name_opener_indices) / max(len(sentences), 1)) * 100
    if current_pct <= target_pct:
        return text, round(current_pct, 1), 0

    target_count = int(len(sentences) * (target_pct / 100))
    to_fix = len(name_opener_indices) - target_count
    fixes_made = 0

    prep_patterns = [
        'in the', 'on the', 'at the', 'from the', 'by the',
        'through the', 'across the', 'behind the', 'under the',
        'with the', 'near the', 'past the', 'along the',
    ]

    for idx in name_opener_indices[2:]:
        if fixes_made >= to_fix:
            break
        s = sentences[idx]
        words = s.split()
        if len(words) < 6:
            continue

        best_prep = None
        best_prep_start = None
        for prep in prep_patterns:
            prep_words = prep.split()
            prep_len = len(prep_words)
            for wi in range(2, len(words) - prep_len - 1):
                candidate = ' '.join(words[wi:wi + prep_len]).lower()
                if candidate == prep:
                    best_prep_start = wi
                    best_prep = prep
                    break
            if best_prep:
                break

        if not best_prep or best_prep_start is None:
            continue

        prep_word_count = len(best_prep.split())
        phrase_end = min(best_prep_start + prep_word_count + 2, len(words))
        phrase_words = words[best_prep_start:phrase_end]

        if phrase_words:
            phrase_words[-1] = phrase_words[-1].rstrip('.,;:')

        before_words = words[:best_prep_start]
        after_words = words[phrase_end:]

        if before_words:
            before_words[-1] = before_words[-1].rstrip(',')

        phrase_str = ' '.join(phrase_words)
        phrase_str = phrase_str[0].upper() + phrase_str[1:]

        if before_words:
            before_words[0] = before_words[0][0].lower() + before_words[0][1:]

        remaining = before_words + after_words
        remaining_str = ' '.join(remaining)

        if not remaining_str.strip():
            continue

        new_sentence = f"{phrase_str}, {remaining_str}"

        if '  ' not in new_sentence and len(new_sentence.split()) >= 4:
            sentences[idx] = new_sentence
            fixes_made += 1

    new_pct = (len(name_opener_indices) - fixes_made) / max(len(sentences), 1) * 100
    return ' '.join(sentences), round(new_pct, 1), fixes_made


# ---------------------------------------------------------------------------
# STAGE 4.4: Impact Paragraph Isolation
# ---------------------------------------------------------------------------

def isolate_impact_paragraphs(text, target_pct=30.0):
    paragraphs = text.split('\n\n')
    if not paragraphs:
        return text, 0, 0

    short_count = sum(1 for p in paragraphs
                      if len([s for s in re.split(r'[.!?]+', p) if s.strip()]) <= 2)
    current_pct = (short_count / max(len(paragraphs), 1)) * 100
    if current_pct >= target_pct * 0.8:
        return text, round(current_pct, 1), 0

    splits_made = 0
    new_paragraphs = []
    impact_words = {'stopped', 'silence', 'nothing', 'gone', 'dead', 'dark',
                    'alone', 'screamed', 'ran', 'heard', 'waited', 'empty',
                    'still', 'quiet', 'frozen', 'cold'}

    for p in paragraphs:
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', p) if s.strip()]
        if len(sents) >= 4 and splits_made < 5:
            for i, s in enumerate(sents[1:-1], 1):
                if (len(s.split()) <= 6 or
                    any(w in s.lower() for w in impact_words)):
                    before = ' '.join(sents[:i])
                    impact = sents[i]
                    after = ' '.join(sents[i+1:])
                    new_paragraphs.append(before)
                    new_paragraphs.append(impact)
                    if after:
                        new_paragraphs.append(after)
                    splits_made += 1
                    break
            else:
                new_paragraphs.append(p)
        else:
            new_paragraphs.append(p)

    result = '\n\n'.join(new_paragraphs)
    new_short = sum(1 for p in new_paragraphs
                    if len([s for s in re.split(r'[.!?]+', p) if s.strip()]) <= 2)
    new_pct = (new_short / max(len(new_paragraphs), 1)) * 100
    return result, round(new_pct, 1), splits_made


# ---------------------------------------------------------------------------
# STAGE 4.5: Paragraph Splitter
# ---------------------------------------------------------------------------

def split_long_paragraphs(text, max_words=50):
    paragraphs = text.split('\n\n')
    new_paragraphs = []
    splits_made = 0

    for p in paragraphs:
        words = p.split()
        if len(words) <= max_words:
            new_paragraphs.append(p)
            continue

        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', p) if s.strip()]
        if len(sents) < 2:
            new_paragraphs.append(p)
            continue

        current_chunk = []
        current_words = 0

        for s in sents:
            s_words = len(s.split())
            if current_words + s_words > max_words and current_chunk:
                new_paragraphs.append(' '.join(current_chunk))
                current_chunk = [s]
                current_words = s_words
                splits_made += 1
            else:
                current_chunk.append(s)
                current_words += s_words

        if current_chunk:
            new_paragraphs.append(' '.join(current_chunk))

    return '\n\n'.join(new_paragraphs), splits_made


# ---------------------------------------------------------------------------
# Shared: compute chapter metrics
# ---------------------------------------------------------------------------

def compute_chapter_metrics(text):
    words = text.split()
    word_count = len(words)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    num_sentences = max(len(sentences), 1)
    sent_lengths = [len(s.split()) for s in sentences]
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    mean_sl = sum(sent_lengths) / max(len(sent_lengths), 1)
    variance = sum((l - mean_sl) ** 2 for l in sent_lengths) / max(len(sent_lengths), 1)
    stdev = variance ** 0.5

    fragments = sum(1 for l in sent_lengths if l < 5)
    em_dashes = text.count('\u2014') + text.count('--')
    dialogue_lines = len(re.findall(r'"[^"]*"', text))

    adverbs = sum(1 for w in words if w.lower().endswith('ly') and len(w) > 3
                  and w.lower() not in NON_ADVERBS)

    all_tags = re.findall(
        r'\b(said|asked|replied|whispered|shouted|muttered|called|cried|answered|'
        r'growled|hissed|exclaimed|declared|snapped|barked|sighed|groaned)\b',
        text, re.IGNORECASE)
    said_count = sum(1 for t in all_tags if t.lower() == 'said')

    smoothing_count = sum(text.lower().count(w) for w in SMOOTHING_WORDS)

    thought_verbs = len(re.findall(
        r'\b(thought|wondered|realized|knew|felt|remembered|imagined|hoped|feared)\b',
        text, re.IGNORECASE))

    sentence_starts = [s.split()[0] if s.split() else '' for s in sentences]
    name_openers = sum(1 for w in sentence_starts
                       if w and w[0].isupper() and len(w) > 1
                       and w.lower() not in COMMON_STARTERS)

    clusters = 0
    for i in range(len(sent_lengths) - 2):
        a, b, c = sent_lengths[i], sent_lengths[i+1], sent_lengths[i+2]
        if max(a, b, c) - min(a, b, c) <= 3:
            clusters += 1

    has_dialogue = len(all_tags) > 0

    return {
        "avg_sentence_length": round(mean_sl, 1),
        "sentence_length_stdev": round(stdev, 1),
        "fragment_pct": round((fragments / num_sentences) * 100, 1),
        "dialogue_ratio_pct": round((dialogue_lines / max(len(paragraphs), 1)) * 100, 1),
        "avg_paragraph_length": round(word_count / max(len(paragraphs), 1), 1),
        "em_dash_per_1k": round((em_dashes / max(word_count, 1)) * 1000, 1),
        "semicolon_per_1k": round((text.count(';') / max(word_count, 1)) * 1000, 1),
        "exclamation_per_1k": round((text.count('!') / max(word_count, 1)) * 1000, 1),
        "question_per_1k": round((text.count('?') / max(word_count, 1)) * 1000, 1),
        "interiority_pct": round((thought_verbs / num_sentences) * 100, 1),
        "adverb_per_1k": round((adverbs / max(word_count, 1)) * 1000, 1),
        "smoothing_per_1k": round((smoothing_count / max(word_count, 1)) * 1000, 1),
        "name_opener_pct": round((name_openers / num_sentences) * 100, 1),
        "said_ratio_pct": round((said_count / max(len(all_tags), 1)) * 100, 1),
        "_word_count": word_count,
        "_sentence_count": num_sentences,
        "_rhythm_stdev": round(stdev, 1),
        "_rhythm_clusters": clusters,
        "_has_dialogue": has_dialogue,
        "_all_tags": all_tags,
        "_adverb_per_1k": round((adverbs / max(word_count, 1)) * 1000, 1),
    }


# ---------------------------------------------------------------------------
# STAGE 5: Quality Gate
# ---------------------------------------------------------------------------

def run_quality_gate(text, metrics, scene_type="reflective"):
    issues = []
    score = 0
    text_lower = text.lower()

    # --- Contamination (always checked) ---
    for bw in ALWAYS_BANNED:
        if bw in text_lower:
            issues.append(f"[CONTAMINATION] '{bw}'")
            score += 3

    # --- Dialogue tags (only with 3+ tags) ---
    if metrics["_has_dialogue"] and len(metrics["_all_tags"]) >= 3:
        all_tags = metrics["_all_tags"]
        creative = [t for t in all_tags if t.lower() not in
                    ('said', 'asked', 'replied', 'whispered', 'shouted',
                     'called', 'cried', 'answered')]
        if creative:
            unique = set(t.lower() for t in creative)
            issues.append(f"[TAGS] Creative: {', '.join(unique)}")
            score += len(unique)

    # --- Adverbs (only alarm if excessive) ---
    if metrics["_adverb_per_1k"] > 15:
        issues.append(f"[ADVERBS] High: {metrics['_adverb_per_1k']:.1f}/1k (want <15)")
        score += 2

    # --- Rhythm ---
    if metrics["_rhythm_clusters"] > 5:
        issues.append(f"[RHYTHM] {metrics['_rhythm_clusters']} monotonous clusters")
        score += metrics["_rhythm_clusters"] - 5
    if metrics["_rhythm_stdev"] < 2:
        issues.append(f"[RHYTHM] Low variance: {metrics['_rhythm_stdev']:.1f}")
        score += 2

    # --- Name openers ---
    if metrics["name_opener_pct"] > 60:
        issues.append(f"[OPENERS] {metrics['name_opener_pct']:.0f}% (want <60%)")
        score += 2

    # --- Dialogue ratio (scene-type aware) ---
    target_range = SCENE_TYPE_DIALOGUE_TARGETS.get(scene_type, (0, 50))
    dial_pct = metrics["dialogue_ratio_pct"]
    if dial_pct < target_range[0] or dial_pct > target_range[1]:
        if not (dial_pct == 0 and target_range[0] == 0):
            issues.append(f"[DIALOGUE] {dial_pct:.0f}% (want {target_range[0]}-{target_range[1]}% for {scene_type})")
            score += 2

    return {
        "total_score": score,
        "issues": issues,
        "word_count": metrics["_word_count"],
        "sentence_count": metrics["_sentence_count"],
    }


# ---------------------------------------------------------------------------
# STAGE 6: Voice Delta
# ---------------------------------------------------------------------------

DIALOGUE_DEPENDENT_METRICS = {"said_ratio_pct", "dialogue_ratio_pct"}

def compute_voice_delta(metrics, baseline_metrics, scene_type="reflective"):
    target_range = SCENE_TYPE_DIALOGUE_TARGETS.get(scene_type, (0, 50))
    has_dialogue = metrics.get("_has_dialogue", False)

    delta = {}
    for metric in ["avg_sentence_length", "sentence_length_stdev", "fragment_pct",
                    "dialogue_ratio_pct", "avg_paragraph_length", "em_dash_per_1k",
                    "semicolon_per_1k", "exclamation_per_1k", "question_per_1k",
                    "interiority_pct", "adverb_per_1k", "smoothing_per_1k",
                    "name_opener_pct", "said_ratio_pct"]:

        chapter_val = metrics.get(metric, 0)
        baseline_val = baseline_metrics.get(metric, 0)

        # Skip dialogue-dependent metrics if no dialogue
        if metric in DIALOGUE_DEPENDENT_METRICS and not has_dialogue:
            delta[metric] = {"baseline": baseline_val, "chapter": chapter_val,
                             "severity": "n/a (no dialogue)"}
            continue

        # Said ratio with tiny sample
        if metric == "said_ratio_pct":
            num_tags = len(metrics.get("_all_tags", []))
            if num_tags < 3:
                delta[metric] = {"baseline": baseline_val, "chapter": chapter_val,
                                 "severity": f"n/a ({num_tags} tags)"}
                continue

        # Scene-type-aware dialogue ratio
        if metric == "dialogue_ratio_pct":
            if target_range[0] <= chapter_val <= target_range[1]:
                severity = "ok"
            else:
                severity = "drift"
            delta[metric] = {"baseline": baseline_val, "chapter": chapter_val,
                             "severity": severity}
            continue

        # Standard drift calculation
        if isinstance(baseline_val, (int, float)) and baseline_val > 0:
            pct_drift = abs(chapter_val - baseline_val) / baseline_val
            if pct_drift < 0.25:
                severity = "ok"
            elif pct_drift < 0.5:
                severity = "drift"
            else:
                severity = "alarm"
        elif chapter_val == 0 and baseline_val == 0:
            severity = "ok"
        elif baseline_val == 0 and chapter_val > 0:
            severity = "ok"  # Can't drift from zero
        else:
            severity = "ok"

        delta[metric] = {"baseline": baseline_val, "chapter": chapter_val,
                         "severity": severity}

    return delta


# ---------------------------------------------------------------------------
# MAIN: produce_chapter (VOICE-AGNOSTIC)
# ---------------------------------------------------------------------------

def produce_chapter(bible_text, baseline_metrics, chapter_beats, scene_type, config=None):
    client = get_anthropic_client()

    # Build voice target string
    voice_targets = []
    for metric, value in baseline_metrics.items():
        if metric == "corpus_word_count":
            continue
        label = metric.replace("_", " ").replace("pct", "%").replace("per 1k", "/1k")
        voice_targets.append(f"  - {label}: {value}")
    voice_target_str = "\n".join(voice_targets)

    # Determine style features from baseline
    baseline_em = baseline_metrics.get("em_dash_per_1k", 0)
    baseline_smooth = baseline_metrics.get("smoothing_per_1k", 0)
    baseline_adverb = baseline_metrics.get("adverb_per_1k", 7)
    baseline_interiority = baseline_metrics.get("interiority_pct", 4)
    baseline_question = baseline_metrics.get("question_per_1k", 5)
    baseline_exclamation = baseline_metrics.get("exclamation_per_1k", 2)
    baseline_fragment = baseline_metrics.get("fragment_pct", 15)
    baseline_avg_sl = baseline_metrics.get("avg_sentence_length", 12)
    baseline_para = baseline_metrics.get("avg_paragraph_length", 25)

    # Determine target word count from chapter beats (look for word count mention)
    # Default to 4000 max tokens, increase for longer chapters
    max_tokens = 4000
    if "3,000" in chapter_beats or "3000" in chapter_beats or "3,500" in chapter_beats:
        max_tokens = 6000
    elif "2,000" in chapter_beats or "2000" in chapter_beats or "2,500" in chapter_beats:
        max_tokens = 5000
    elif "1,500" in chapter_beats or "1500" in chapter_beats:
        max_tokens = 4000

    # ---- STAGE 2: DRAFT ----
    draft_prompt = f"""You are a fiction ghostwriter. Write a chapter based on the project bible
and chapter beats below. Match the author's voice EXACTLY as described in the bible.

PROJECT BIBLE:
{bible_text}

CHAPTER TO WRITE:
{chapter_beats}

Scene type: {scene_type}

VOICE METRICS FROM THE AUTHOR'S EXISTING WORK (match these closely):
{voice_target_str}

RULES:
- Write ONLY chapter prose. No headers, no commentary, no "Chapter X:" label.
- Match the voice, tone, POV, and style described in the bible EXACTLY.
- Follow ALL style rules in the bible. The bible is your authority on voice.
- Hit the target word count specified in the beats.
- End the chapter exactly as the beats describe.

METRIC TARGETS (from the author's corpus — match these):
- Average sentence length: ~{baseline_avg_sl:.0f} words per sentence.
- Fragment percentage: ~{baseline_fragment:.0f}% of sentences should be fragments (under 5 words).
- Interiority: ~{baseline_interiority:.0f}% of sentences should contain thought verbs (thought, wondered, knew, felt, realized, remembered, figured, hoped, feared).
- Adverbs: ~{baseline_adverb:.0f} per 1,000 words. Not zero, not excessive.
- Questions: ~{baseline_question:.0f} question marks per 1,000 words.
- Exclamations: ~{baseline_exclamation:.0f} exclamation marks per 1,000 words.
- Average paragraph length: ~{baseline_para:.0f} words. Use blank lines between paragraphs.
- Em-dashes: ~{baseline_em:.0f} per 1,000 words. {"Use em-dashes where natural." if baseline_em > 1 else "Avoid em-dashes."}
- Smoothing words: ~{baseline_smooth:.1f} per 1,000 words. {"Use sparingly where natural." if baseline_smooth > 0.5 else "Avoid smoothing words."}

Write the chapter now. Prose only."""

    draft_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": draft_prompt}]
    )
    draft_text = draft_response.content[0].text
    draft_input = draft_response.usage.input_tokens
    draft_output = draft_response.usage.output_tokens

    # ---- STAGE 3: CORRECTIVE REWRITE ----
    rewrite_prompt = f"""You are a fiction editor. Rewrite the draft to better match the author's voice metrics.

DRAFT:
{draft_text}

VOICE METRICS TO MATCH:
{voice_target_str}

REWRITE PRIORITIES:
1. Match the average sentence length (~{baseline_avg_sl:.0f} words). {"Lengthen short choppy sentences." if baseline_avg_sl > 10 else "Break up long sentences."}
2. Fragment percentage should be ~{baseline_fragment:.0f}%. {"Add more fragments." if baseline_fragment > 20 else "Reduce fragments — use complete sentences."}
3. Interiority should be ~{baseline_interiority:.0f}% of sentences with thought verbs (thought, wondered, knew, felt, realized, remembered).
4. Adverbs should be ~{baseline_adverb:.0f} per 1,000 words. {"Add adverbs where natural." if baseline_adverb > 5 else "Keep adverbs minimal."}
5. Questions: ~{baseline_question:.0f} per 1,000 words. Exclamations: ~{baseline_exclamation:.0f} per 1,000 words.
6. Paragraph length: ~{baseline_para:.0f} words average. Use blank lines between paragraphs.
7. Em-dashes: {"KEEP em-dashes, they're part of the voice." if baseline_em > 1 else "Remove em-dashes, replace with periods or commas."}
8. Smoothing words: {"Keep where natural." if baseline_smooth > 0.5 else "Remove smoothing words (however, moreover, furthermore, etc)."}
9. Vary sentence length. Mix short with long. Avoid monotonous rhythm.
10. Ensure the ending matches the beats exactly.

CRITICAL: Do NOT impose rules that aren't in the voice metrics. If the baseline shows em-dashes, KEEP them.
If the baseline shows long sentences, write LONG sentences. Match the numbers.

Output ONLY the rewritten chapter. No commentary."""

    rewrite_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": rewrite_prompt}]
    )
    text = rewrite_response.content[0].text
    rewrite_input = rewrite_response.usage.input_tokens
    rewrite_output = rewrite_response.usage.output_tokens

    # ---- CONDITIONAL POST-PROCESSING ----
    em_removed = 0
    smooth_removed = 0
    openers_fixed = 0
    opener_pct = 0
    impacts_split = 0
    impact_pct = 0
    para_splits = 0

    # 4.1: Em-dash removal ONLY if baseline says no em-dashes
    if baseline_em < 1:
        text, em_removed = remove_em_dashes(text)

    # 4.2: Smoothing removal ONLY if baseline has very low smoothing
    if baseline_smooth < 0.5:
        text, smooth_removed = remove_smoothing_words(text)

    # 4.3: Opener fix (always — but uses baseline target)
    opener_target = min(baseline_metrics.get("name_opener_pct", 30) * 1.5, 55)
    text, opener_pct, openers_fixed = fix_name_openers(text, target_pct=opener_target)

    # 4.4: Impact paragraph isolation
    text, impact_pct, impacts_split = isolate_impact_paragraphs(text)

    # 4.5: Paragraph splitter (target from baseline)
    para_max = max(int(baseline_para * 2.5), 60)
    text, para_splits = split_long_paragraphs(text, max_words=para_max)

    # ---- Compute metrics ----
    metrics = compute_chapter_metrics(text)

    # ---- STAGE 5: QUALITY GATE ----
    quality_report = run_quality_gate(text, metrics, scene_type)

    # ---- STAGE 6: VOICE DELTA ----
    voice_delta = compute_voice_delta(metrics, baseline_metrics, scene_type)

    # ---- Hotspots ----
    hotspots = []
    if em_removed > 0:
        hotspots.append({"type": "fix", "text": f"Removed {em_removed} em-dashes"})
    if smooth_removed > 0:
        hotspots.append({"type": "fix", "text": f"Removed {smooth_removed} smoothing words"})
    if openers_fixed > 0:
        hotspots.append({"type": "fix", "text": f"Fixed {openers_fixed} name openers → {opener_pct}%"})
    if impacts_split > 0:
        hotspots.append({"type": "fix", "text": f"Split {impacts_split} impact paragraphs → {impact_pct}%"})
    if para_splits > 0:
        hotspots.append({"type": "fix", "text": f"Split {para_splits} long paragraphs"})
    for issue in quality_report.get("issues", []):
        hotspots.append({"type": "issue", "text": issue})

    # ---- Tokens ----
    total_input = draft_input + rewrite_input
    total_output = draft_output + rewrite_output
    cost = (total_input / 1_000_000 * 3) + (total_output / 1_000_000 * 15)

    return {
        "chapter_text": text,
        "word_count": metrics["_word_count"],
        "quality_score": quality_report["total_score"],
        "quality_report": quality_report,
        "voice_delta": voice_delta,
        "hotspots": hotspots,
        "manifest": {
            "pipeline_version": "web-v4",
            "scene_type": scene_type,
            "stages": ["draft", "rewrite",
                       "em_dash_removal" if baseline_em < 1 else "em_dash_kept",
                       "smoothing_removal" if baseline_smooth < 0.5 else "smoothing_kept",
                       "opener_fix", "impact_isolation", "paragraph_split",
                       "quality_gate", "voice_delta"],
            "model": "claude-sonnet-4-20250514",
            "post_process": {
                "em_dashes_removed": em_removed,
                "smoothing_removed": smooth_removed,
                "openers_fixed": openers_fixed,
                "impacts_split": impacts_split,
                "paragraphs_split": para_splits,
            },
            "total_input_tokens": total_input,
            "total_output_tokens": total_output
        },
        "api_usage": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost": round(cost, 4)
        }
    }
