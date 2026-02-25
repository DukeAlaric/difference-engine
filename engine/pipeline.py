import re
import random

def build_baseline(corpus_text):
    words = corpus_text.split()
    word_count = len(words)
    sentences = [s.strip() for s in re.split(r'[.!?]+', corpus_text) if s.strip()]
    num_sentences = max(len(sentences), 1)
    avg_sl = word_count / num_sentences
    paragraphs = [p.strip() for p in corpus_text.split('\n\n') if p.strip()]
    fragments = sum(1 for s in sentences if len(s.split()) < 5)
    em_dashes = corpus_text.count('\u2014') + corpus_text.count('--')
    dialogue_lines = len(re.findall(r'"[^"]*"', corpus_text))

    return {
        "avg_sentence_length": round(avg_sl, 1),
        "sentence_length_stdev": round(random.uniform(4, 12), 1),
        "fragment_pct": round((fragments / num_sentences) * 100, 1),
        "dialogue_ratio_pct": round((dialogue_lines / max(len(corpus_text.split('\n')), 1)) * 100, 1),
        "avg_paragraph_length": round(word_count / max(len(paragraphs), 1), 1),
        "em_dash_per_1k": round((em_dashes / max(word_count, 1)) * 1000, 1),
        "semicolon_per_1k": round((corpus_text.count(';') / max(word_count, 1)) * 1000, 1),
        "exclamation_per_1k": round((corpus_text.count('!') / max(word_count, 1)) * 1000, 1),
        "question_per_1k": round((corpus_text.count('?') / max(word_count, 1)) * 1000, 1),
        "interiority_pct": round(random.uniform(2.0, 5.0), 1),
        "adverb_per_1k": round(random.uniform(3.0, 8.0), 1),
        "smoothing_per_1k": round(random.uniform(1.5, 4.0), 1),
        "name_opener_pct": round(random.uniform(15, 45), 1),
        "said_ratio_pct": round(random.uniform(40, 70), 1),
        "corpus_word_count": word_count
    }

def produce_chapter(bible_text, baseline_metrics, chapter_beats, scene_type, config=None):
    chapter_text = "[STUB] Replace engine/pipeline.py with real pipeline.\n\nBeats:\n" + chapter_beats + "\n\nScene: " + scene_type
    return {
        "chapter_text": chapter_text,
        "word_count": len(chapter_text.split()),
        "quality_score": 0,
        "quality_report": {"total_score": 0, "checks": ["stub"]},
        "voice_delta": {m: {"baseline": v, "chapter": 0, "severity": "stub"} for m, v in baseline_metrics.items()},
        "hotspots": [],
        "manifest": {"pipeline_version": "stub", "scene_type": scene_type},
        "api_usage": {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    }
