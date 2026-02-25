"""
engine/pipeline.py — Full production pipeline for the Difference Engine web app.

Stages:
  1. Baseline analysis (14 metrics)
  2. Draft generation (Claude API)
  3. Corrective rewrite (Claude API)
  4. Post-processing:
     4.1 Em-dash mechanical removal
     4.2 Smoothing word mechanical removal
     4.3 Opener fix (reduce name-opener percentage)
     4.4 Impact paragraph isolation
  5. Quality gate (full scoring)
  6. Voice delta with z-scores
"""

import re
import math
import anthropic
import streamlit as st


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------

def get_anthropic_client():
    return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])


# ---------------------------------------------------------------------------
# STAGE 1: Baseline Analysis
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

    # Sentence length stdev
    lengths = [len(s.split()) for s in sentences]
    mean_len = sum(lengths) / max(len(lengths), 1)
    variance = sum((l - mean_len) ** 2 for l in lengths) / max(len(lengths), 1)
    stdev = variance ** 0.5

    # Adverbs (words ending in -ly, excluding common non-adverbs)
    non_adverbs = {'only', 'early', 'family', 'likely', 'belly', 'holy', 'ugly',
                   'lonely', 'friendly', 'elderly', 'daily', 'july', 'fly', 'reply',
                   'supply', 'ally', 'apply', 'rely', 'italy', 'sally', 'billy',
                   'molly', 'emily', 'lily'}
    adverbs = sum(1 for w in words if w.lower().endswith('ly') and len(w) > 3
                  and w.lower() not in non_adverbs)

    # Smoothing words
    smoothing_list = ['however', 'moreover', 'furthermore', 'nevertheless',
                      'nonetheless', 'meanwhile', 'consequently', 'therefore',
                      'indeed', 'certainly', 'naturally', 'obviously',
                      'of course', 'in fact', 'as a matter of fact',
                      'it is worth noting', 'it should be noted']
    text_lower = corpus_text.lower()
    smoothing_count = sum(text_lower.count(w) for w in smoothing_list)

    # Said ratio
    all_tags = re.findall(
        r'\b(said|asked|replied|whispered|shouted|muttered|called|cried|answered|'
        r'growled|hissed|exclaimed|declared|snapped|barked|sighed|groaned)\b',
        corpus_text, re.IGNORECASE)
    said_count = sum(1 for t in all_tags if t.lower() == 'said')
    said_ratio = (said_count / max(len(all_tags), 1)) * 100

    # Name openers
    common_starters = {'the', 'a', 'an', 'it', 'he', 'she', 'they', 'we', 'i',
                       'this', 'that', 'there', 'when', 'where', 'what', 'how',
                       'but', 'and', 'so', 'if', 'as', 'in', 'on', 'at', 'for',
                       'to', 'his', 'her', 'my', 'our', 'its', 'no', 'not', 'all',
                       'one', 'two', 'some', 'any', 'every', 'each', 'after',
                       'before', 'now', 'then', 'just', 'even', 'still', 'with',
                       'from', 'by', 'up', 'out', 'down', 'back', 'over', 'through'}
    sentence_starts = [s.split()[0] if s.split() else '' for s in sentences]
    name_openers = sum(1 for w in sentence_starts
                       if w and w[0].isupper() and len(w) > 1
                       and w.lower() not in common_starters)
    name_opener_pct = (name_openers / num_sentences) * 100

    # Interiority (thought verbs)
    thought_verbs = len(re.findall(
        r'\b(thought|wondered|realized|knew|felt|remembered|imagined|hoped|'
        r'feared|wished|believed|supposed|figured|guessed|considered|'
        r'understood|recognized|noticed|sensed)\b',
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


# ---------------------------------------------------------------------------
# STAGE 4.1: Em-dash Mechanical Removal
# ---------------------------------------------------------------------------

def remove_em_dashes(text):
    """Replace em-dashes with periods or commas, context-aware."""
    count = 0

    # Pattern: word — word (mid-sentence break)
    def replace_em(match):
        nonlocal count
        before = match.group(1)
        after = match.group(2)
        count += 1
        # If after starts lowercase, use period + capitalize
        if after and after[0].islower():
            return f"{before}. {after[0].upper()}{after[1:]}"
        return f"{before}. {after}"

    # Replace em-dash (—) and double-dash (--)
    text = re.sub(r'(\w+)\s*\u2014\s*(\w+)', replace_em, text)
    text = re.sub(r'(\w+)\s*--\s*(\w+)', replace_em, text)

    # Catch any remaining standalone em-dashes
    remaining = text.count('\u2014') + text.count('--')
    text = text.replace('\u2014', '.').replace('--', '.')
    count += remaining

    return text, count


# ---------------------------------------------------------------------------
# STAGE 4.2: Smoothing Word Mechanical Removal
# ---------------------------------------------------------------------------

SMOOTHING_WORDS = [
    'however', 'moreover', 'furthermore', 'nevertheless', 'nonetheless',
    'consequently', 'therefore', 'indeed', 'certainly', 'naturally',
    'obviously', 'of course', 'in fact', 'as a matter of fact',
    'it is worth noting', 'it should be noted', 'needless to say'
]


def remove_smoothing_words(text):
    """Remove smoothing words and fix resulting punctuation."""
    count = 0
    for word in SMOOTHING_WORDS:
        # Pattern: "However, " or "however, " at start of sentence
        pattern = re.compile(
            r'(?i)(?:^|\.\s+)' + re.escape(word) + r',?\s*',
            re.MULTILINE
        )
        matches = pattern.findall(text)
        if matches:
            count += len(matches)

        # Remove the word (case-insensitive) with optional trailing comma
        # At start of sentence: "However, the..." -> "The..."
        text = re.sub(
            r'(?i)((?:^|\.\s+))' + re.escape(word) + r',?\s*(\w)',
            lambda m: m.group(1) + m.group(2).upper(),
            text,
            flags=re.MULTILINE
        )
        # Mid-sentence: "was, however, not" -> "was not"
        text = re.sub(
            r'(?i),?\s*' + re.escape(word) + r',?\s*',
            ' ',
            text
        )

    # Clean up double spaces
    text = re.sub(r'  +', ' ', text)
    return text, count


# ---------------------------------------------------------------------------
# STAGE 4.3: Opener Fix
# ---------------------------------------------------------------------------

def fix_name_openers(text, target_pct=40.0):
    """
    Reduce name-opener percentage by restructuring sentences.
    Restructures some "Name verbed" openings to vary sentence starts.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if not sentences:
        return text, 0, 0

    common_starters = {'the', 'a', 'an', 'it', 'he', 'she', 'they', 'we', 'i',
                       'this', 'that', 'there', 'when', 'where', 'what', 'how',
                       'but', 'and', 'so', 'if', 'as', 'in', 'on', 'at', 'for',
                       'to', 'his', 'her', 'my', 'our', 'its', 'no', 'not'}

    # Find name-opener sentences
    name_opener_indices = []
    for i, s in enumerate(sentences):
        words = s.split()
        if words and words[0][0:1].isupper() and len(words[0]) > 1:
            if words[0].lower() not in common_starters:
                name_opener_indices.append(i)

    current_pct = (len(name_opener_indices) / max(len(sentences), 1)) * 100
    if current_pct <= target_pct:
        return text, round(current_pct, 1), 0

    # How many to fix
    target_count = int(len(sentences) * (target_pct / 100))
    to_fix = len(name_opener_indices) - target_count
    fixes_made = 0

    # Restructure some name openers (skip the first few — they're often intentional)
    for idx in name_opener_indices[2:]:  # Skip first two
        if fixes_made >= to_fix:
            break
        s = sentences[idx]
        words = s.split()
        if len(words) < 4:
            continue

        name = words[0]
        # Try prepending with a transition from context
        # "Jesse ran" -> "Without thinking, Jesse ran"
        # "Dale laughed" -> "From the porch, Dale laughed"
        # Simple approach: occasionally restructure
        if fixes_made % 3 == 0 and len(words) > 5:
            # Move a prepositional phrase to front if one exists later
            prep_match = re.search(r'\b(in the|on the|at the|from the|by the|through the|across the|behind the)\b',
                                   s, re.IGNORECASE)
            if prep_match and prep_match.start() > len(name) + 5:
                # Extract prep phrase (up to next comma or 5 words)
                phrase_start = prep_match.start()
                rest = s[phrase_start:]
                phrase_words = rest.split()[:4]
                phrase = ' '.join(phrase_words)
                before_phrase = s[:phrase_start].rstrip(' ,')
                after_phrase = s[phrase_start + len(phrase):].lstrip(' ,')
                sentences[idx] = f"{phrase.capitalize()}, {before_phrase.lower()}{after_phrase}"
                fixes_made += 1

    new_pct = current_pct - (fixes_made / max(len(sentences), 1)) * 100
    return ' '.join(sentences), round(new_pct, 1), fixes_made


# ---------------------------------------------------------------------------
# STAGE 4.4: Impact Paragraph Isolation
# ---------------------------------------------------------------------------

def isolate_impact_paragraphs(text, target_pct=30.0):
    """
    Ensure short, punchy paragraphs (1-2 sentences) make up ~25-40% of paragraphs.
    Split some longer paragraphs at dramatic moments.
    """
    paragraphs = text.split('\n\n')
    if not paragraphs:
        return text, 0, 0

    # Count current short paragraphs (1-2 sentences)
    short_count = 0
    for p in paragraphs:
        sents = [s.strip() for s in re.split(r'[.!?]+', p) if s.strip()]
        if len(sents) <= 2:
            short_count += 1

    current_pct = (short_count / max(len(paragraphs), 1)) * 100
    if current_pct >= target_pct * 0.8:  # Close enough
        return text, round(current_pct, 1), 0

    # Find long paragraphs that could be split
    splits_made = 0
    new_paragraphs = []

    for p in paragraphs:
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', p) if s.strip()]
        if len(sents) >= 4 and splits_made < 5:
            # Look for a dramatic sentence to isolate
            for i, s in enumerate(sents[1:-1], 1):  # Skip first and last
                # Short sentences or sentences with strong words
                if (len(s.split()) <= 6 or
                    any(w in s.lower() for w in ['stopped', 'silence', 'nothing',
                                                  'gone', 'dead', 'dark', 'alone',
                                                  'screamed', 'ran', 'heard'])):
                    # Split: everything before, the impact sentence, everything after
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
# STAGE 5: Quality Gate
# ---------------------------------------------------------------------------

SCENE_TYPE_DIALOGUE_TARGETS = {
    "reflective": (0, 15),
    "social_confrontation": (45, 85),
    "action": (10, 40),
    "intimate": (30, 65),
    "procedural": (5, 30),
}


def run_quality_gate(text, baseline_metrics, scene_type="reflective"):
    """Full quality gate with 6 check categories. Returns score and details."""
    word_count = len(text.split())
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    num_sentences = max(len(sentences), 1)
    text_lower = text.lower()

    issues = []
    score = 0

    # --- CHECK 1: Style Compliance ---
    # Em-dashes
    em_dashes = text.count('\u2014') + text.count('--')
    if em_dashes > 0:
        issues.append(f"[STYLE] Em-dashes remaining: {em_dashes}")
        score += em_dashes * 3

    # Semicolons
    semicolons = text.count(';')
    if semicolons > 0:
        issues.append(f"[STYLE] Semicolons: {semicolons}")
        score += semicolons

    # --- CHECK 2: Contamination (AI-isms) ---
    banned_words = ['delve', 'tapestry', 'unbeknownst', 'whilst', 'amidst',
                    'little did he know', 'a chill ran down', 'the weight of',
                    'something was off', 'pierced the silence', 'shattered the',
                    'a tapestry of', 'in the tapestry', 'hung in the air',
                    'sent shivers', 'etched across', 'knuckles whitened']
    for bw in banned_words:
        if bw in text_lower:
            issues.append(f"[CONTAMINATION] '{bw}'")
            score += 3

    # Smoothing words
    for sw in SMOOTHING_WORDS:
        count = text_lower.count(sw.lower())
        if count > 0:
            issues.append(f"[CONTAMINATION] Smoothing word '{sw}': {count}")
            score += count * 2

    # --- CHECK 3: Dialogue Tags ---
    all_tags = re.findall(
        r'\b(said|asked|replied|whispered|shouted|muttered|called|cried|answered|'
        r'growled|hissed|exclaimed|declared|snapped|barked|sighed|groaned|'
        r'breathed|intoned|purred|proclaimed)\b',
        text, re.IGNORECASE)
    said_count = sum(1 for t in all_tags if t.lower() == 'said')
    said_ratio = (said_count / max(len(all_tags), 1)) * 100

    creative_tags = [t for t in all_tags if t.lower() not in
                     ('said', 'asked', 'replied', 'whispered', 'shouted', 'called', 'cried', 'answered')]
    if creative_tags:
        unique_creative = set(t.lower() for t in creative_tags)
        issues.append(f"[TAGS] Creative tags: {', '.join(unique_creative)}")
        score += len(unique_creative)

    if all_tags and said_ratio < 60:
        issues.append(f"[TAGS] Said ratio low: {said_ratio:.0f}% (target: 70%+)")
        score += 1

    # --- CHECK 4: Adverb Density ---
    non_adverbs = {'only', 'early', 'family', 'likely', 'belly', 'holy', 'ugly',
                   'lonely', 'friendly', 'elderly', 'daily', 'fly', 'reply', 'supply'}
    words = text.split()
    adverbs = [w for w in words if w.lower().endswith('ly') and len(w) > 3
               and w.lower() not in non_adverbs]
    adverb_per_1k = (len(adverbs) / max(len(words), 1)) * 1000
    if adverb_per_1k > 8:
        issues.append(f"[ADVERBS] High density: {adverb_per_1k:.1f}/1k (target: <8)")
        score += 2
    if adverb_per_1k > 12:
        score += 2  # Extra penalty

    # --- CHECK 5: Rhythm ---
    sent_lengths = [len(s.split()) for s in sentences]
    if sent_lengths:
        mean_sl = sum(sent_lengths) / len(sent_lengths)
        variance = sum((l - mean_sl) ** 2 for l in sent_lengths) / len(sent_lengths)
        stdev = variance ** 0.5

        # Monotony detection: count clusters of similar-length sentences
        clusters = 0
        for i in range(len(sent_lengths) - 2):
            a, b, c = sent_lengths[i], sent_lengths[i+1], sent_lengths[i+2]
            if max(a, b, c) - min(a, b, c) <= 3:
                clusters += 1
        if clusters > 3:
            issues.append(f"[RHYTHM] Monotonous clusters: {clusters} (target: ≤3)")
            score += clusters - 3

        if stdev < 3:
            issues.append(f"[RHYTHM] Low variance: {stdev:.1f}")
            score += 2

    # --- CHECK 6: Name Openers ---
    common_starters = {'the', 'a', 'an', 'it', 'he', 'she', 'they', 'we', 'i',
                       'this', 'that', 'there', 'when', 'where', 'what', 'how',
                       'but', 'and', 'so', 'if', 'as', 'in', 'on', 'at', 'for',
                       'to', 'his', 'her', 'my', 'our', 'its', 'no', 'not'}
    sentence_starts = [s.split()[0] if s.split() else '' for s in sentences]
    name_openers = sum(1 for w in sentence_starts
                       if w and w[0].isupper() and len(w) > 1
                       and w.lower() not in common_starters)
    name_opener_pct = (name_openers / num_sentences) * 100
    if name_opener_pct > 60:
        issues.append(f"[OPENERS] Name opener: {name_opener_pct:.0f}% (target: <60%)")
        score += 2

    # --- CHECK 7: Dialogue Ratio (scene-type aware) ---
    dialogue_lines = len(re.findall(r'"[^"]*"', text))
    total_lines = max(len(text.split('\n')), 1)
    dialogue_pct = (dialogue_lines / total_lines) * 100
    target_range = SCENE_TYPE_DIALOGUE_TARGETS.get(scene_type, (10, 50))
    if dialogue_pct < target_range[0] or dialogue_pct > target_range[1]:
        issues.append(f"[DIALOGUE] {dialogue_pct:.0f}% (target: {target_range[0]}-{target_range[1]}% for {scene_type})")
        score += 2

    return {
        "total_score": score,
        "issues": issues,
        "em_dashes": em_dashes,
        "adverb_per_1k": round(adverb_per_1k, 1),
        "said_ratio_pct": round(said_ratio, 1),
        "name_opener_pct": round(name_opener_pct, 1),
        "dialogue_pct": round(dialogue_pct, 1),
        "word_count": word_count,
        "sentence_count": num_sentences,
        "rhythm_stdev": round(stdev, 1) if sent_lengths else 0,
        "rhythm_clusters": clusters if sent_lengths else 0
    }


# ---------------------------------------------------------------------------
# STAGE 6: Voice Delta with Z-Scores
# ---------------------------------------------------------------------------

def compute_voice_delta(text, baseline_metrics, scene_type="reflective"):
    """Compare chapter metrics against baseline with z-score-like severity."""
    word_count = len(text.split())
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    num_sentences = max(len(sentences), 1)
    sent_lengths = [len(s.split()) for s in sentences]

    non_adverbs = {'only', 'early', 'family', 'likely', 'belly', 'holy', 'ugly',
                   'lonely', 'friendly', 'elderly', 'daily'}
    words = text.split()
    adverbs = sum(1 for w in words if w.lower().endswith('ly') and len(w) > 3
                  and w.lower() not in non_adverbs)

    em_dashes = text.count('\u2014') + text.count('--')
    dialogue_lines = len(re.findall(r'"[^"]*"', text))
    fragments = sum(1 for l in sent_lengths if l < 5)

    all_tags = re.findall(
        r'\b(said|asked|replied|whispered|shouted|muttered|called|cried|answered|'
        r'growled|hissed|exclaimed|declared|snapped)\b', text, re.IGNORECASE)
    said_count = sum(1 for t in all_tags if t.lower() == 'said')

    mean_sl = sum(sent_lengths) / max(len(sent_lengths), 1)
    variance = sum((l - mean_sl) ** 2 for l in sent_lengths) / max(len(sent_lengths), 1)
    stdev = variance ** 0.5

    thought_verbs = len(re.findall(
        r'\b(thought|wondered|realized|knew|felt|remembered|imagined|hoped|feared)\b',
        text, re.IGNORECASE))

    smoothing_count = sum(text.lower().count(w) for w in SMOOTHING_WORDS)

    common_starters = {'the', 'a', 'an', 'it', 'he', 'she', 'they', 'we', 'i',
                       'this', 'that', 'there', 'when', 'where', 'what', 'how',
                       'but', 'and', 'so', 'if', 'as', 'in', 'on', 'at', 'for',
                       'to', 'his', 'her', 'my', 'our', 'its', 'no', 'not'}
    sentence_starts = [s.split()[0] if s.split() else '' for s in sentences]
    name_openers = sum(1 for w in sentence_starts
                       if w and w[0].isupper() and len(w) > 1
                       and w.lower() not in common_starters)

    chapter_metrics = {
        "avg_sentence_length": round(mean_sl, 1),
        "sentence_length_stdev": round(stdev, 1),
        "fragment_pct": round((fragments / num_sentences) * 100, 1),
        "dialogue_ratio_pct": round((dialogue_lines / max(len(text.split('\n')), 1)) * 100, 1),
        "avg_paragraph_length": round(word_count / max(len(text.split('\n\n')), 1), 1),
        "em_dash_per_1k": round((em_dashes / max(word_count, 1)) * 1000, 1),
        "semicolon_per_1k": round((text.count(';') / max(word_count, 1)) * 1000, 1),
        "exclamation_per_1k": round((text.count('!') / max(word_count, 1)) * 1000, 1),
        "question_per_1k": round((text.count('?') / max(word_count, 1)) * 1000, 1),
        "interiority_pct": round((thought_verbs / num_sentences) * 100, 1),
        "adverb_per_1k": round((adverbs / max(word_count, 1)) * 1000, 1),
        "smoothing_per_1k": round((smoothing_count / max(word_count, 1)) * 1000, 1),
        "name_opener_pct": round((name_openers / num_sentences) * 100, 1),
        "said_ratio_pct": round((said_count / max(len(all_tags), 1)) * 100, 1),
    }

    # Scene-type-aware dialogue check
    target_range = SCENE_TYPE_DIALOGUE_TARGETS.get(scene_type, (10, 50))

    delta = {}
    for metric, chapter_val in chapter_metrics.items():
        baseline_val = baseline_metrics.get(metric, 0)
        if isinstance(baseline_val, (int, float)) and baseline_val > 0:
            # Z-score-like: how many baseline stdevs away
            pct_drift = abs(chapter_val - baseline_val) / baseline_val
            if pct_drift < 0.25:
                severity = "ok"
            elif pct_drift < 0.5:
                severity = "drift"
            else:
                severity = "alarm"
        else:
            severity = "ok"

        # Override for dialogue ratio if within scene-type range
        if metric == "dialogue_ratio_pct":
            if target_range[0] <= chapter_val <= target_range[1]:
                severity = "ok"

        delta[metric] = {
            "baseline": baseline_val,
            "chapter": chapter_val,
            "severity": severity
        }

    return delta


# ---------------------------------------------------------------------------
# MAIN PIPELINE: produce_chapter
# ---------------------------------------------------------------------------

def produce_chapter(bible_text, baseline_metrics, chapter_beats, scene_type, config=None):
    """
    Full production pipeline:
      Stage 2: Draft (API)
      Stage 3: Corrective rewrite (API)
      Stage 4.1: Em-dash removal
      Stage 4.2: Smoothing removal
      Stage 4.3: Opener fix
      Stage 4.4: Impact paragraph isolation
      Stage 5: Quality gate
      Stage 6: Voice delta
    """
    client = get_anthropic_client()

    # Build voice target string
    voice_targets = []
    for metric, value in baseline_metrics.items():
        label = metric.replace("_", " ").replace("pct", "%").replace("per 1k", "/1k")
        voice_targets.append(f"  - {label}: {value}")
    voice_target_str = "\n".join(voice_targets)

    # ---- STAGE 2: DRAFT ----
    draft_prompt = f"""You are a fiction ghostwriter. Write a chapter based on the project bible 
and chapter beats below. Write in the author's voice as described in the voice guide and style brief.

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
    draft_input = draft_response.usage.input_tokens
    draft_output = draft_response.usage.output_tokens

    # ---- STAGE 3: CORRECTIVE REWRITE ----
    rewrite_prompt = f"""You are a fiction editor. Rewrite the draft to better match the author's voice.

DRAFT:
{draft_text}

VOICE TARGETS:
{voice_target_str}

STYLE RULES:
- Em-dashes: NONE. Replace with periods and sentence fragments.
- Semicolons: No. Replace with periods.
- Adverbs: Almost none. Cut any that don't earn their place.
- "said" for 70%+ of dialogue tags. Cut creative tags. Use said or action beats.
- NO smoothing words: however, moreover, furthermore, nevertheless, indeed, certainly, 
  naturally, obviously, of course, in fact.
- NO banned words: delve, tapestry, something was off, the weight of, a chill ran down, 
  little did he know, unbeknownst, whilst, amidst.
- Sentence fragments: Frequent in action/fear. Rare in calm scenes.
- Concrete sensory details: Name specific trees, birds, sounds. Not just "a tree."
- Interiority: Blend thoughts into narration. Shorter fragments when scared.
- Vary sentence length. Mix short punchy with longer rolling. Avoid monotonous rhythm.
- Ensure the ending matches the beats.

Output ONLY the rewritten chapter. No commentary."""

    rewrite_response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": rewrite_prompt}]
    )
    rewrite_text = rewrite_response.content[0].text
    rewrite_input = rewrite_response.usage.input_tokens
    rewrite_output = rewrite_response.usage.output_tokens

    # ---- STAGE 4.1: EM-DASH REMOVAL ----
    text, em_dashes_removed = remove_em_dashes(rewrite_text)

    # ---- STAGE 4.2: SMOOTHING REMOVAL ----
    text, smoothing_removed = remove_smoothing_words(text)

    # ---- STAGE 4.3: OPENER FIX ----
    text, opener_pct, openers_fixed = fix_name_openers(text, target_pct=40.0)

    # ---- STAGE 4.4: IMPACT PARAGRAPH ISOLATION ----
    text, impact_pct, impacts_split = isolate_impact_paragraphs(text, target_pct=30.0)

    # ---- STAGE 5: QUALITY GATE ----
    quality_report = run_quality_gate(text, baseline_metrics, scene_type)

    # ---- STAGE 6: VOICE DELTA ----
    voice_delta = compute_voice_delta(text, baseline_metrics, scene_type)

    # ---- Build hotspots ----
    hotspots = []
    if em_dashes_removed > 0:
        hotspots.append({"type": "post-process", "text": f"Removed {em_dashes_removed} em-dashes"})
    if smoothing_removed > 0:
        hotspots.append({"type": "post-process", "text": f"Removed {smoothing_removed} smoothing words"})
    if openers_fixed > 0:
        hotspots.append({"type": "post-process", "text": f"Fixed {openers_fixed} name openers (now {opener_pct}%)"})
    if impacts_split > 0:
        hotspots.append({"type": "post-process", "text": f"Isolated {impacts_split} impact paragraphs (now {impact_pct}%)"})

    # Token totals
    total_input = draft_input + rewrite_input
    total_output = draft_output + rewrite_output
    cost = (total_input / 1_000_000 * 3) + (total_output / 1_000_000 * 15)

    return {
        "chapter_text": text,
        "word_count": len(text.split()),
        "quality_score": quality_report["total_score"],
        "quality_report": quality_report,
        "voice_delta": voice_delta,
        "hotspots": hotspots,
        "manifest": {
            "pipeline_version": "web-v2-full",
            "scene_type": scene_type,
            "stages": ["draft", "rewrite", "em_dash_removal", "smoothing_removal",
                       "opener_fix", "impact_isolation", "quality_gate", "voice_delta"],
            "model": "claude-sonnet-4-20250514",
            "post_process": {
                "em_dashes_removed": em_dashes_removed,
                "smoothing_removed": smoothing_removed,
                "openers_fixed": openers_fixed,
                "impacts_split": impacts_split,
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
