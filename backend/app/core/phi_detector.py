from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# French NIR (social security number): 13 digits + 2-digit key. Loose form accepted.
NIR_RE = re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2,3}\s?\d{3}\s?\d{3}(?:\s?\d{2})?\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_FR_RE = re.compile(r"\b(?:(?:\+33|0033|0)\s?[1-9](?:[\s.-]?\d{2}){4})\b")
DOB_RE = re.compile(r"\b(0?[1-9]|[12]\d|3[01])[/\-\.](0?[1-9]|1[0-2])[/\-\.](19|20)\d{2}\b")
# French INSEE commune code (5 digits, not the same as NIR but similar pattern use at registries)
INSEE_RE = re.compile(r"\bINSEE[:\s]+\d{5}\b", re.IGNORECASE)


@dataclass
class PHIMatch:
    type: str
    value: str
    start: int
    end: int


@dataclass
class PHIReport:
    has_phi: bool
    high_sensitivity: bool
    matches: list[PHIMatch] = field(default_factory=list)


class PHIDetector:
    def __init__(self, terms_path: Path | None = None, nlp=None):
        path = terms_path or Path(__file__).with_name("phi_sensitive_terms.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self._terms = [t.lower() for t in data.get("high_sensitivity_terms", [])]
        self._rare_icd10 = [c.upper() for c in data.get("rare_disease_icd10", [])]
        self._nlp = nlp  # Optional spaCy pipeline. Loaded lazily.

    def _load_nlp(self):
        """Lazy-load a NER backend. Preference order:
        1. Jean-Baptiste/camembert-ner via transformers (clinical-grade French NER)
        2. spaCy fr_core_news_md (baseline)
        Falls through to False if neither is available.
        """
        if self._nlp is not None:
            return self._nlp
        # Prefer HuggingFace camembert-ner for precision on French medical text.
        try:
            from transformers import pipeline
            hf = pipeline(
                "token-classification",
                model="Jean-Baptiste/camembert-ner",
                aggregation_strategy="simple",
                device=-1,  # CPU
            )
            self._nlp = ("hf", hf)
            return self._nlp
        except Exception:
            pass
        try:
            import spacy
            self._nlp = ("spacy", spacy.load("fr_core_news_md"))
            return self._nlp
        except Exception:
            self._nlp = False
            return self._nlp

    def scan(self, text: str) -> PHIReport:
        if not text:
            return PHIReport(has_phi=False, high_sensitivity=False)

        matches: list[PHIMatch] = []

        for pattern, tag in (
            (NIR_RE, "nir"),
            (EMAIL_RE, "email"),
            (PHONE_FR_RE, "phone_fr"),
            (DOB_RE, "date_of_birth"),
            (INSEE_RE, "insee"),
        ):
            for m in pattern.finditer(text):
                matches.append(PHIMatch(type=tag, value=m.group(0), start=m.start(), end=m.end()))

        lower = text.lower()
        high_sens = False
        for term in self._terms:
            idx = lower.find(term)
            if idx != -1:
                matches.append(PHIMatch(type="high_sensitivity_term", value=term, start=idx, end=idx + len(term)))
                high_sens = True

        upper = text.upper()
        for code in self._rare_icd10:
            idx = upper.find(code)
            if idx != -1:
                # Require word boundary or trailing punctuation to avoid false positives.
                before_ok = idx == 0 or not upper[idx - 1].isalnum()
                end = idx + len(code)
                after_ok = end == len(upper) or not upper[end].isalnum() or upper[end] == "."
                if before_ok and after_ok:
                    matches.append(PHIMatch(type="rare_disease_icd10", value=code, start=idx, end=end))
                    high_sens = True

        nlp = self._load_nlp()
        if nlp:
            kind, model = nlp
            if kind == "hf":
                try:
                    ents = model(text)
                    for ent in ents:
                        tag = ent.get("entity_group", "")
                        if tag in {"PER", "LOC"} and ent.get("score", 0) >= 0.85:
                            start = int(ent.get("start", 0))
                            end = int(ent.get("end", 0))
                            matches.append(PHIMatch(
                                type=f"ner_{tag.lower()}",
                                value=str(ent.get("word", "")).strip(),
                                start=start, end=end,
                            ))
                except Exception:
                    pass
            else:
                doc = model(text)
                for ent in doc.ents:
                    if ent.label_ in {"PER", "PERSON", "LOC"}:
                        matches.append(PHIMatch(type=f"ner_{ent.label_.lower()}", value=ent.text, start=ent.start_char, end=ent.end_char))

        return PHIReport(has_phi=bool(matches), high_sensitivity=high_sens, matches=matches)

    def contains_high_sensitivity(self, text: str) -> bool:
        return self.scan(text).high_sensitivity
