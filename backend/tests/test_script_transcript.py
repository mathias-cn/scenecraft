from app.core.script_transcript import estimate_speech_ms, script_segments, split_script_sentences


def test_split_script_sentences_on_punctuation_and_newlines():
    text = "Olá mundo. Como vai?\nTudo bem!"
    assert split_script_sentences(text) == ["Olá mundo.", "Como vai?", "Tudo bem!"]


def test_split_script_sentences_keeps_unpunctuated_block():
    assert split_script_sentences("  só um bloco sem ponto  ") == ["só um bloco sem ponto"]


def test_split_script_sentences_empty():
    assert split_script_sentences("   ") == []


def test_estimate_speech_ms_uses_150_wpm():
    # 150 palavras / minuto → 1 palavra = 400 ms
    assert estimate_speech_ms("uma") == 400
    assert estimate_speech_ms(" ".join(["palavra"] * 150)) == 60_000


def test_script_segments_are_sequential_placeholders():
    segments = script_segments("Olá mundo. Segunda frase aqui.")
    assert len(segments) == 2
    assert segments[0].text == "Olá mundo."
    assert segments[1].text == "Segunda frase aqui."
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == segments[1].start_ms
    assert segments[1].end_ms > segments[1].start_ms
