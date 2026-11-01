import numpy as np
import pytest

from app.speech.acoustic import SimulatedBackend, SimulatedUtterance
from app.speech.ctc import ctc_nll, forced_align, greedy_decode
from app.speech.devanagari import aksharas, normalize, words
from app.speech.eccl import CORRECT, CORRECT_DIALECT, ERROR, NO_SPEECH, score_word
from app.speech.mutations import generate_candidates
from app.speech.passage import score_passage
from app.speech.regions import RegionProfile

M = SimulatedBackend()


def lp(text: str, **kw) -> np.ndarray:
    return M.synthesize(SimulatedUtterance(text, **kw))


def test_aksharas():
    assert [a.text for a in aksharas("किताब")] == ["कि", "ता", "ब"]
    assert [a.text for a in aksharas("प्यार")] == ["प्या", "र"]
    assert [a.text for a in aksharas("संतरा")] == ["सं", "त", "रा"]
    assert aksharas("बिल्ली")[1].is_conjunct


def test_words_strip_danda_and_hyphen():
    assert words("मेरा नाम रानी है। उड़ते-उड़ते") == ["मेरा", "नाम", "रानी", "है", "उड़ते", "उड़ते"]


def test_nukta_normalisation():
    assert normalize("ज़") == "ज़"


@pytest.mark.parametrize("word,rule,produced", [
    ("नदी", "MLEN", "नदि"),
    ("फल", "ASP", "पल"),
    ("भालू", "ASP", "बालू"),
    ("किताब", "MDROP", "कताब"),
    ("मेला", "MSWAP", "मैला"),
    ("बन", "VIS", "वन"),
    ("संतरा", "NAS", "सतरा"),
    ("प्यार", "CONJ", "पियार"),
    ("खाना", "VIS", "रवाना"),
])
def test_candidates_contain_expected_mutation(word, rule, produced):
    cands = generate_candidates(word)
    assert cands[0].is_target and cands[0].text == normalize(word)
    assert any(c.rule == rule and c.text == normalize(produced) for c in cands)
    assert len({c.text for c in cands}) == len(cands)


def test_ctc_nll_prefers_spoken_text():
    logp = lp("नदी")
    good = ctc_nll(logp, M.tokenize("नदी"), M.blank_id)
    bad = ctc_nll(logp, M.tokenize("नदि"), M.blank_id)
    assert good < bad
    assert M.detokenize(greedy_decode(logp, M.blank_id)) == "नदी"


def test_ctc_nll_matches_bruteforce_tiny():
    # 3 frames, vocab {blank, a}; P('a') = sum over paths {a__, _a_, __a, aa_, _aa, aaa}
    p = np.array([[0.6, 0.4], [0.5, 0.5], [0.7, 0.3]])
    logp = np.log(p)
    paths = ["a--", "-a-", "--a", "aa-", "-aa", "aaa"]
    total = sum(np.prod([p[t, 1 if ch == "a" else 0] for t, ch in enumerate(path)]) for path in paths)
    assert abs(ctc_nll(logp, [1], 0) - (-np.log(total))) < 1e-9


def test_forced_align_spans_ordered():
    logp = lp("घर")
    spans, score = forced_align(logp, M.tokenize("घर"), M.blank_id)
    assert len(spans) == 2 and spans[0].end <= spans[1].start and score > -1e9


@pytest.mark.parametrize("target,spoken,status,rule", [
    ("नदी", "नदी", CORRECT, None),
    ("नदी", "नदि", ERROR, "MLEN"),
    ("फल", "पल", ERROR, "ASP"),
    ("किताब", "कताब", ERROR, "MDROP"),
    ("संतरा", "सतरा", ERROR, "NAS"),
])
def test_eccl_types_errors(target, spoken, status, rule):
    v = score_word(lp(spoken), target, M)
    assert v.status == status, v
    assert v.rule == rule
    if status == ERROR:
        assert v.produced == normalize(spoken) and v.confidence > 0.7


def test_eccl_dialect_tolerance():
    prof = RegionProfile("east", "east", substitutions=(("व", "ब"),))
    assert score_word(lp("बन"), "वन", M).status == ERROR  # standard: visual confusion
    v = score_word(lp("बन"), "वन", M, prof)
    assert v.status == CORRECT_DIALECT


def test_eccl_no_speech():
    silent = np.log(np.full((60, len(M.vocab)), 1e-6))
    silent[:, M.blank_id] = 0.0
    assert score_word(silent, "घर", M).status == NO_SPEECH


def test_eccl_sounding_out_detected():
    v = score_word(lp("कमल", gap_frames=20), "कमल", M)
    assert v.status == CORRECT and v.sounding_out


def test_passage_wcpm_and_errors():
    text = "मेरा नाम रानी है। मेरे घर में एक गाय है।"
    spoken = "मेरा नाम रानि है मेरे घर में एक गाय है"
    v = score_passage(lp(spoken), text, M)
    assert v.n_words == 10 and v.attempted == 10
    statuses = {w["target"]: w["status"] for w in v.words}
    assert statuses[normalize("रानी")] == ERROR
    assert v.correct == 9 and v.wcpm > 0 and v.wcpm_low <= v.wcpm <= v.wcpm_high
