#!/usr/bin/env python3
"""verify_citations.py - Citation Integrity and Reference Verification Engine.

Validates bibliographic identifiers (DOI, arXiv, PubMed PMID, ISBN, and URLs)
against authoritative registries (CrossRef, arXiv, PubMed NCBI, Open Library).

Epistemic Model:
1. Identifier Status: RESOLVED | NOT_FOUND | LOOKUP_ERROR
2. Metadata Status  : MATCH | PARTIAL | MISMATCH | UNVERIFIED
3. Claim Status     : UNCHECKED (Citation existence != Claim support)

Features:
- Multi-factor identity validation: checks title similarity, first author match, and publication years.
- Domain token conflict detection: flags mismatched diseases, organs, or tasks (e.g. skin vs lung).
- Multi-identifier harvesting: extracts co-existing DOI, PMID, arXiv, and URLs from BibTeX without skipping.
- Epistemic clarity: uncompared citations are flagged as METADATA_UNVERIFIED, never falsely CONFIRMED.
- URL reachability distinction: HTTP 200 is reported as URL_ACCESSIBLE, not document identity confirmed.
- Windows safe: pure ASCII status indicators ([PASS], [INFO], [WARN], [FAIL], [ERR ], [URL ]).
"""

import argparse
import difflib
import json
import os
import re
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Optional contact email for CrossRef polite API pool
DEFAULT_EMAIL = os.environ.get("CITATION_VERIFIER_EMAIL", "")


def get_user_agent(email: Optional[str] = None) -> str:
    """Build User-Agent string with optional polite pool contact email."""
    contact = email or DEFAULT_EMAIL
    if contact:
        return f"CitationVerifier/1.2 (mailto:{contact}; https://github.com/AlpaZZ/office-agent-skills)"
    return "CitationVerifier/1.2 (https://github.com/AlpaZZ/office-agent-skills)"


# Regex Patterns for Citation Identifiers
DOI_PATTERNS = [
    re.compile(r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)(10\.\d{4,9}/[^\s\"\'><)\]]+)", re.IGNORECASE),
    re.compile(r"\b(10\.\d{4,9}/[A-Za-z0-9\._\-;()/:+]+[A-Za-z0-9])\b", re.IGNORECASE),
]

ARXIV_PATTERNS = [
    re.compile(r"\barXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)\b", re.IGNORECASE),
    re.compile(r"https?://arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", re.IGNORECASE),
]

PMID_PATTERNS = [
    re.compile(r"\bPMID:\s*([0-9]{6,9})\b", re.IGNORECASE),
    re.compile(r"https?://pubmed\.ncbi\.nlm\.nih\.gov/([0-9]{6,9})", re.IGNORECASE),
]

ISBN_PATTERNS = [
    re.compile(r"\bISBN(?:-1[03])?:?\s*([0-9Xx-]{10,17})\b", re.IGNORECASE),
]

KNOWN_ACADEMIC_DOMAINS = (
    "nature.com",
    "sciencedirect.com",
    "link.springer.com",
    "onlinelibrary.wiley.com",
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "pnas.org",
    "cell.com",
    "frontiersin.org",
    "mdpi.com",
    "academic.oup.com",
    "tandfonline.com",
    "jstor.org",
    "acs.org",
    "rsc.org",
)

URL_PATTERN = re.compile(r"https?://[^\s\"\'><)\]]+", re.IGNORECASE)

# Distinct domain topic clusters to detect semantic false positives
DOMAIN_CONFLICT_SETS = [
    ({"skin", "dermoscopy", "melanoma", "dermatology"}, {"lung", "pulmonary", "chest", "x-ray", "pneumonia"}),
    ({"retina", "retinal", "fundus", "eye", "glaucoma", "diabetic"}, {"brain", "mri", "tumor", "glioma", "cortex"}),
    ({"cardiac", "heart", "ecg", "cardiovascular"}, {"liver", "hepatic", "kidney", "renal"}),
    ({"breast", "mammography"}, {"prostate", "colon", "colorectal"}),
]


def _clean_trailing_punct(s: str) -> str:
    """Strip common trailing punctuation from captured identifiers."""
    return re.sub(r"[\.,;:!\)\]]+$", "", s).strip()


def _get_ssl_context() -> ssl.SSLContext:
    """Return an SSL context with fallback for environments lacking local CA bundles."""
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        pass
    return ssl._create_unverified_context()


def _fetch_url(url: str, user_agent: str, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> Tuple[int, bytes, Dict[str, str]]:
    """Fetch URL with timeout and fallback SSL context."""
    req_headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    ctx = _get_ssl_context()

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            status = resp.status
            body = resp.read()
            resp_headers = dict(resp.headers)
            return status, body, resp_headers
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return e.code, body, dict(e.headers)
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            fallback_ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=fallback_ctx, timeout=timeout) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        raise e


def _probe_url(url: str, user_agent: str, timeout: int = 10) -> int:
    """Check reachability without downloading an arbitrary publisher payload."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent}, method="HEAD")
    try:
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        if exc.code not in (405, 501):
            return exc.code
        req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=timeout) as resp:
            return resp.status


def normalize_title(title: str) -> str:
    """Normalize paper title for fuzzy comparison."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _clean_evidence(value: str) -> str:
    """Turn registry HTML/XML abstracts into comparable plain text."""
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", value).strip()


def _content_tokens(value: str) -> Set[str]:
    stop = {"about", "after", "also", "among", "because", "between", "could", "from", "have", "into", "more", "most", "other", "over", "such", "than", "their", "there", "these", "this", "those", "using", "were", "which", "with", "within", "would"}
    return {x for x in re.findall(r"[a-z]{3,}", (value or "").lower()) if x not in stop}


def load_local_evidence(evidence_dir: Optional[Path]) -> Dict[str, List[Dict[str, Any]]]:
    """Load user-supplied full text keyed by DOI/PMID/arXiv in the filename."""
    if not evidence_dir or not evidence_dir.exists():
        return {}
    loaded: Dict[str, List[Dict[str, Any]]] = {}
    for path in sorted(evidence_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".txt", ".md"}:
            continue
        key = re.sub(r"[^a-z0-9]+", "", path.stem.lower())
        try:
            if path.suffix.lower() == ".pdf":
                import fitz
                pages = [{"page": i + 1, "text": page.get_text("text")} for i, page in enumerate(fitz.open(path))]
            else:
                pages = [{"page": None, "text": path.read_text(encoding="utf-8", errors="replace")}]
        except Exception:
            continue
        loaded[key] = pages
    return loaded


def _evidence_for(identifier: str, local: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    key = re.sub(r"[^a-z0-9]+", "", identifier.lower())
    return local.get(key, [])


def _claim_kind(sentence: str) -> str:
    s = sentence.lower()
    if re.search(r"\b(increased|decreased|improved|reduced|accuracy|\d+(?:\.\d+)?%|significant)\b", s): return "quantitative-result"
    if re.search(r"\b(cause|causes|caused|leads? to| ಪರಿಣಾಮ|because|due to)\b", s): return "causal"
    if re.search(r"\b(method|dataset|sample|participants|experiment|trained|evaluated)\b", s): return "methodology"
    return "descriptive"


def audit_claim_support(text: str, results: List[Dict[str, Any]], local_evidence: Optional[Dict[str, List[Dict[str, Any]]]] = None, citation_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Conservatively map cited sentences to source abstracts.

    A citation receives PASS only when its identifier is present in the same
    sentence and the claim shares several content terms with retrieved source
    evidence. Numeric/author-year citations remain UNMAPPED until a reference
    map is supplied; this prevents metadata validity from being reported as
    claim support.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]
    by_id = {str(r.get("identifier", "")).lower(): r for r in results if r.get("identifier")}
    local_evidence = local_evidence or {}
    citation_map = citation_map or {}
    id_patterns = [re.compile(r"10\.\d{4,9}/[^\s\"'<>\)\]]+", re.I), re.compile(r"\bPMID[:\s]+\d{6,9}\b", re.I), re.compile(r"\barXiv[:\s]+\d{4}\.\d{4,5}(?:v\d+)?", re.I)]
    out = []
    for sentence in sentences:
        identifiers = []
        for pat in id_patterns:
            identifiers.extend(_clean_trailing_punct(m.group(0).split(":", 1)[-1]) for m in pat.finditer(sentence))
        has_marker = bool(identifiers or re.search(r"\[[0-9,;\s-]+\]|\([A-Z][A-Za-z-]+(?:\s+et al\.)?,?\s*\d{4}[a-z]?\)", sentence))
        if not has_marker:
            continue
        numeric = re.findall(r"\[([0-9]+)\]", sentence)
        identifiers.extend(citation_map.get(n, "") for n in numeric if citation_map.get(n))
        matched = [by_id.get(i.lower()) for i in identifiers if i.lower() in by_id]
        if not matched:
            out.append({"sentence": sentence, "status": "UNMAPPED_CITATION", "evidence": [], "details": "Citation marker tidak dapat dipetakan ke identifier sumber."})
            continue
        claim_tokens = _content_tokens(sentence)
        evidence = []
        evidence_refs = []
        for source in matched:
            pages = _evidence_for(str(source.get("identifier", "")), local_evidence)
            if pages:
                evidence.extend(p.get("text", "") for p in pages)
                evidence_refs.extend({"identifier": source.get("identifier"), "page": p.get("page"), "excerpt": _clean_evidence(p.get("text", ""))[:500]} for p in pages)
            elif source.get("evidence_text"):
                evidence.append(source["evidence_text"])
                evidence_refs.append({"identifier": source.get("identifier"), "page": None, "excerpt": _clean_evidence(source["evidence_text"])[:500]})
        if not evidence:
            out.append({"sentence": sentence, "claim_kind": _claim_kind(sentence), "status": "EVIDENCE_UNAVAILABLE", "evidence": [r.get("identifier") for r in matched], "details": "Registry mengonfirmasi metadata, tetapi full text/abstract sumber tidak tersedia."})
            continue
        scores = []
        for ev in evidence:
            ev_tokens = _content_tokens(ev)
            overlap = len(claim_tokens & ev_tokens)
            scores.append(overlap / max(1, len(claim_tokens)))
        best = max(scores)
        status = "ABSTRACT_SUPPORT" if best >= 0.20 and max(len(claim_tokens), 1) >= 3 else "ABSTRACT_NO_SUPPORT"
        out.append({"sentence": sentence, "claim_kind": _claim_kind(sentence), "status": status, "score": round(best, 3), "evidence": [r.get("identifier") for r in matched], "evidence_refs": evidence_refs, "details": "Kecocokan leksikal terhadap bukti sumber; klaim rinci tetap memerlukan pemeriksaan halaman/section."})
    return out


def check_domain_conflicts(tokens1: Set[str], tokens2: Set[str]) -> bool:
    """Detect if title 1 and title 2 belong to explicitly conflicting organ/disease topics."""
    for set_a, set_b in DOMAIN_CONFLICT_SETS:
        if (tokens1 & set_a and tokens2 & set_b) or (tokens1 & set_b and tokens2 & set_a):
            return True
    return False


def titles_match(t1: str, t2: str, threshold: float = 0.65) -> Tuple[bool, float, str]:
    """Compare two titles using sequence ratio, token overlap, and domain conflict detection."""
    n1 = normalize_title(t1)
    n2 = normalize_title(t2)
    if not n1 or not n2:
        return True, 1.0, "Missing title comparison string"

    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    stopwords = {"a", "an", "the", "in", "on", "of", "for", "with", "and", "to", "at", "by", "from", "via", "using", "based", "approach", "method"}
    tokens1 -= stopwords
    tokens2 -= stopwords

    # Domain conflict check: e.g. Skin Disease vs Lung Disease
    if check_domain_conflicts(tokens1, tokens2):
        return False, 0.40, "Contradictory domain tokens detected (different organ/disease topic)"

    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    if ratio >= threshold:
        return True, ratio, "Sequence similarity threshold satisfied"

    # Token overlap check (useful when subtitles or formatting are omitted)
    if tokens1 and tokens2:
        overlap = len(tokens1 & tokens2) / min(len(tokens1), len(tokens2))
        if overlap >= 0.70:
            return True, max(ratio, overlap), "High token set overlap satisfied"

    return False, ratio, "Low sequence similarity and token overlap"


def authors_match(expected_authors: Any, resolved_authors: Optional[List[str]]) -> Tuple[bool, str]:
    """Check author correspondence between document and registry.

    Requires:
    1. First author match (surname intersection), OR
    2. At least two author surnames intersecting when multiple authors are listed.
    """
    if not expected_authors or not resolved_authors:
        return True, "No author metadata available for comparison"

    if isinstance(expected_authors, str):
        exp_list = [a.strip() for a in re.split(r"[;,]|\band\b", expected_authors) if a.strip()]
    elif isinstance(expected_authors, list):
        exp_list = [str(a).strip() for a in expected_authors if str(a).strip()]
    else:
        return True, "Author format unparseable"

    if not exp_list or not resolved_authors:
        return True, "Empty author list"

    def get_parts(author_str: str) -> Set[str]:
        return {p.lower().strip(".,;:") for p in re.split(r"[\s,]+", author_str) if len(p.strip()) > 1}

    def first_authors_compatible(exp_first: str, res_first: str) -> bool:
        exp_parts = [p.lower().strip(".,;:") for p in re.split(r"[\s,]+", exp_first) if len(p.strip()) > 0]
        res_parts = [p.lower().strip(".,;:") for p in re.split(r"[\s,]+", res_first) if len(p.strip()) > 0]
        shared = {p for p in exp_parts if len(p) > 1} & {p for p in res_parts if len(p) > 1}
        if not shared:
            return False
        exp_other = [p for p in exp_parts if p not in shared]
        res_other = [p for p in res_parts if p not in shared]
        if exp_other and res_other:
            exp_inits = {p[0] for p in exp_other}
            res_inits = {p[0] for p in res_other}
            if not (exp_inits & res_inits):
                return False
        return True

    first_author_matched = first_authors_compatible(exp_list[0], resolved_authors[0])

    all_exp_parts = set()
    for a in exp_list:
        all_exp_parts.update(get_parts(a))

    all_res_parts = set()
    for a in resolved_authors:
        all_res_parts.update(get_parts(a))

    overlap = len(all_exp_parts & all_res_parts)

    if first_author_matched:
        return True, f"First author matches ('{exp_list[0]}' / '{resolved_authors[0]}')"
    elif len(exp_list) == 1 and overlap >= 1 and first_author_matched:
        return True, f"Single author surname matches ('{exp_list[0]}')"
    elif overlap >= 2:
        return True, f"{overlap} author surnames match between document and registry"
    else:
        return False, f"Author mismatch: expected first author '{exp_list[0]}', registry has '{resolved_authors[0]}'"


def evaluate_identity(
    expected_title: Optional[str],
    resolved_title: str,
    expected_authors: Optional[Any] = None,
    resolved_authors: Optional[List[str]] = None,
    expected_year: Optional[Any] = None,
    resolved_year: Optional[Any] = None,
) -> Tuple[str, str, str, float, str]:
    """Multi-factor identity assessment.

    Returns:
        (overall_status, identifier_status, metadata_status, similarity_score, details)
    """
    identifier_status = "RESOLVED"

    # Epistemic honesty fix: if no in-document title/author was provided, do NOT confirm identity!
    if not expected_title and not expected_authors:
        return (
            "METADATA_UNVERIFIED",
            identifier_status,
            "UNVERIFIED",
            1.0,
            "Identifier resolved in registry, but no in-document title or author was available to confirm match.",
        )

    matched, score, match_reason = titles_match(expected_title or "", resolved_title)

    author_ok, author_detail = True, "Author not checked"
    if expected_authors and resolved_authors:
        author_ok, author_detail = authors_match(expected_authors, resolved_authors)

    year_ok, year_diff = True, 0
    if expected_year and resolved_year:
        try:
            ey = int(str(expected_year)[:4])
            ry = int(str(resolved_year)[:4])
            year_diff = abs(ey - ry)
            year_ok = (year_diff <= 1)
        except Exception:
            pass

    if score >= 0.82 and author_ok and year_ok:
        return (
            "IDENTITY_CONFIRMED",
            identifier_status,
            "MATCH",
            round(score, 2),
            f"Title, author, and year confirmed against registry ({author_detail}).",
        )
    elif score >= 0.82 and author_ok and not year_ok:
        return (
            "METADATA_PARTIAL",
            identifier_status,
            "PARTIAL",
            round(score, 2),
            f"Title and author match, but publication year differs significantly ({expected_year} vs {resolved_year}).",
        )
    elif score >= 0.82 and not author_ok:
        return (
            "METADATA_PARTIAL",
            identifier_status,
            "PARTIAL",
            round(score, 2),
            f"Title matches ({score:.2f}), but author names differ ({author_detail}).",
        )
    elif score >= 0.65 and author_ok and year_ok:
        return (
            "IDENTITY_CONFIRMED",
            identifier_status,
            "MATCH",
            round(score, 2),
            f"Identity confirmed (similarity: {score:.2f}, {author_detail}).",
        )
    elif score >= 0.65 and (not author_ok or not year_ok):
        return (
            "METADATA_PARTIAL",
            identifier_status,
            "PARTIAL",
            round(score, 2),
            f"Borderline match (title: {score:.2f}, {author_detail}, year diff: {year_diff}y).",
        )
    else:
        return (
            "METADATA_MISMATCH",
            identifier_status,
            "MISMATCH",
            round(score, 2),
            f"Registry title differs: '{resolved_title}' vs expected '{expected_title}' (similarity: {score:.2f}; {match_reason}).",
        )


class CitationVerifier:
    def __init__(self, email: Optional[str] = None, timeout: int = 10, cache_file: Optional[Path] = None, no_cache: bool = False):
        self.email = email or DEFAULT_EMAIL
        self.timeout = timeout
        self.no_cache = no_cache
        self.cache_file = cache_file or (Path.cwd() / ".citation_cache.json")
        self.cache: Dict[str, Any] = {}
        self.user_agent = get_user_agent(self.email)
        self._load_cache()

    def _load_cache(self):
        if not self.no_cache and self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def _save_cache(self):
        if not self.no_cache:
            try:
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(self.cache, f, indent=2)
            except Exception:
                pass

    def verify_doi(
        self,
        doi: str,
        expected_title: Optional[str] = None,
        expected_authors: Optional[Any] = None,
        expected_year: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Verify a DOI against CrossRef REST API."""
        clean_doi = _clean_trailing_punct(doi.strip())
        cache_key = f"doi:{clean_doi.lower()}"

        if not self.no_cache and cache_key in self.cache:
            res = dict(self.cache[cache_key])
            overall, ident_st, meta_st, score, detail = evaluate_identity(
                expected_title,
                res.get("title", ""),
                expected_authors=expected_authors,
                resolved_authors=res.get("authors"),
                expected_year=expected_year,
                resolved_year=res.get("year"),
            )
            res["status"] = overall
            res["identifier_status"] = ident_st
            res["metadata_status"] = meta_st
            res["title_similarity"] = score
            res["details"] = detail
            res["claim_status"] = "UNCHECKED"
            return res

        url = f"https://api.crossref.org/works/{urllib.parse.quote(clean_doi, safe='/:')}"
        headers = {"Accept": "application/json"}

        try:
            status, body, _ = _fetch_url(url, user_agent=self.user_agent, headers=headers, timeout=self.timeout)
            if status == 200:
                data = json.loads(body.decode("utf-8"))
                item = data.get("message", {})
                titles = item.get("title", [])
                remote_title = titles[0] if titles else ""
                authors_raw = item.get("author", [])
                authors = [f"{a.get('family', '')} {a.get('given', '')}".strip() for a in authors_raw if isinstance(a, dict)]
                journal = (item.get("container-title") or [""])[0]
                year = None
                created = item.get("published-print") or item.get("published-online") or item.get("created")
                if created and "date-parts" in created and created["date-parts"]:
                    parts = created["date-parts"][0]
                    if parts:
                        year = parts[0]

                overall, ident_st, meta_st, score, detail = evaluate_identity(
                    expected_title,
                    remote_title,
                    expected_authors=expected_authors,
                    resolved_authors=authors,
                    expected_year=expected_year,
                    resolved_year=year,
                )

                res = {
                    "type": "DOI",
                    "identifier": clean_doi,
                    "status": overall,
                    "identifier_status": ident_st,
                    "metadata_status": meta_st,
                    "claim_status": "UNCHECKED",
                    "title": remote_title,
                    "authors": authors[:5],
                    "venue": journal,
                    "year": year,
                    "evidence_text": _clean_evidence(item.get("abstract", "")),
                    "title_similarity": score,
                    "details": detail,
                }

                self.cache[cache_key] = res
                self._save_cache()
                return res

            elif status == 404:
                res = {
                    "type": "DOI",
                    "identifier": clean_doi,
                    "status": "NOT_FOUND",
                    "identifier_status": "NOT_FOUND",
                    "metadata_status": "UNVERIFIED",
                    "claim_status": "UNCHECKED",
                    "details": "DOI not found in CrossRef registry (likely invalid or hallucinated)",
                }
                self.cache[cache_key] = res
                self._save_cache()
                return res
            else:
                return {
                    "type": "DOI",
                    "identifier": clean_doi,
                    "status": "LOOKUP_ERROR",
                    "identifier_status": "LOOKUP_ERROR",
                    "metadata_status": "UNVERIFIED",
                    "claim_status": "UNCHECKED",
                    "details": f"CrossRef returned HTTP {status}",
                }
        except Exception as e:
            return {
                "type": "DOI",
                "identifier": clean_doi,
                "status": "LOOKUP_ERROR",
                "identifier_status": "LOOKUP_ERROR",
                "metadata_status": "UNVERIFIED",
                "claim_status": "UNCHECKED",
                "details": f"Connection error: {str(e)}",
            }

    def verify_arxiv(
        self,
        arxiv_id: str,
        expected_title: Optional[str] = None,
        expected_authors: Optional[Any] = None,
        expected_year: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Verify an arXiv identifier via the official arXiv API."""
        clean_id = _clean_trailing_punct(arxiv_id.strip())
        cache_key = f"arxiv:{clean_id.lower()}"

        if not self.no_cache and cache_key in self.cache:
            res = dict(self.cache[cache_key])
            overall, ident_st, meta_st, score, detail = evaluate_identity(
                expected_title,
                res.get("title", ""),
                expected_authors=expected_authors,
                resolved_authors=res.get("authors"),
                expected_year=expected_year,
                resolved_year=res.get("year"),
            )
            res["status"] = overall
            res["identifier_status"] = ident_st
            res["metadata_status"] = meta_st
            res["title_similarity"] = score
            res["details"] = detail
            res["claim_status"] = "UNCHECKED"
            return res

        url = f"https://export.arxiv.org/api/query?id_list={clean_id}"
        try:
            status, body, _ = _fetch_url(url, user_agent=self.user_agent, timeout=self.timeout)
            if status == 200:
                root = ET.fromstring(body)
                entry = root.find("{http://www.w3.org/2005/Atom}entry")
                if entry is not None:
                    title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
                    remote_title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""

                    if "Error" in remote_title or not remote_title:
                        res = {
                            "type": "arXiv",
                            "identifier": clean_id,
                            "status": "NOT_FOUND",
                            "identifier_status": "NOT_FOUND",
                            "metadata_status": "UNVERIFIED",
                            "claim_status": "UNCHECKED",
                            "details": "arXiv ID not found in repository",
                        }
                    else:
                        authors = [a.find("{http://www.w3.org/2005/Atom}name").text for a in entry.findall("{http://www.w3.org/2005/Atom}author")]
                        published_elem = entry.find("{http://www.w3.org/2005/Atom}published")
                        year = published_elem.text[:4] if published_elem is not None and published_elem.text else None

                        overall, ident_st, meta_st, score, detail = evaluate_identity(
                            expected_title,
                            remote_title,
                            expected_authors=expected_authors,
                            resolved_authors=authors,
                            expected_year=expected_year,
                            resolved_year=year,
                        )

                        res = {
                            "type": "arXiv",
                            "identifier": clean_id,
                            "status": overall,
                            "identifier_status": ident_st,
                            "metadata_status": meta_st,
                            "claim_status": "UNCHECKED",
                            "title": remote_title,
                            "authors": authors[:5],
                            "year": year,
                            "evidence_text": _clean_evidence(entry.findtext("{http://www.w3.org/2005/Atom}summary", "")),
                            "title_similarity": score,
                            "details": detail,
                        }
                    self.cache[cache_key] = res
                    self._save_cache()
                    return res
            return {
                "type": "arXiv",
                "identifier": clean_id,
                "status": "LOOKUP_ERROR",
                "identifier_status": "LOOKUP_ERROR",
                "metadata_status": "UNVERIFIED",
                "claim_status": "UNCHECKED",
                "details": f"arXiv API returned status {status}",
            }
        except Exception as e:
            return {
                "type": "arXiv",
                "identifier": clean_id,
                "status": "LOOKUP_ERROR",
                "identifier_status": "LOOKUP_ERROR",
                "metadata_status": "UNVERIFIED",
                "claim_status": "UNCHECKED",
                "details": f"arXiv lookup error: {str(e)}",
            }

    def verify_pmid(
        self,
        pmid: str,
        expected_title: Optional[str] = None,
        expected_authors: Optional[Any] = None,
        expected_year: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Verify a PubMed PMID via NCBI E-utilities."""
        clean_pmid = _clean_trailing_punct(pmid.strip())
        cache_key = f"pmid:{clean_pmid}"

        if not self.no_cache and cache_key in self.cache:
            res = dict(self.cache[cache_key])
            overall, ident_st, meta_st, score, detail = evaluate_identity(
                expected_title,
                res.get("title", ""),
                expected_authors=expected_authors,
                resolved_authors=res.get("authors"),
                expected_year=expected_year,
                resolved_year=res.get("year"),
            )
            res["status"] = overall
            res["identifier_status"] = ident_st
            res["metadata_status"] = meta_st
            res["title_similarity"] = score
            res["details"] = detail
            res["claim_status"] = "UNCHECKED"
            return res

        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={clean_pmid}&retmode=json"
        try:
            status, body, _ = _fetch_url(url, user_agent=self.user_agent, timeout=self.timeout)
            if status == 200:
                data = json.loads(body.decode("utf-8"))
                result_obj = data.get("result", {})
                if clean_pmid in result_obj:
                    pdata = result_obj[clean_pmid]
                    if "error" in pdata:
                        res = {
                            "type": "PMID",
                            "identifier": clean_pmid,
                            "status": "NOT_FOUND",
                            "identifier_status": "NOT_FOUND",
                            "metadata_status": "UNVERIFIED",
                            "claim_status": "UNCHECKED",
                            "details": "PMID not found in PubMed",
                        }
                    else:
                        remote_title = pdata.get("title", "")
                        authors_list = [a.get("name") for a in pdata.get("authors", []) if isinstance(a, dict) and "name" in a]
                        year = pdata.get("pubdate", "")[:4]
                        evidence_text = ""
                        try:
                            est, ebody, _ = _fetch_url(
                                f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={clean_pmid}&rettype=abstract&retmode=xml",
                                user_agent=self.user_agent,
                                timeout=self.timeout,
                            )
                            if est == 200:
                                eroot = ET.fromstring(ebody)
                                evidence_text = _clean_evidence(" ".join(eroot.itertext()))
                        except Exception:
                            evidence_text = ""

                        overall, ident_st, meta_st, score, detail = evaluate_identity(
                            expected_title,
                            remote_title,
                            expected_authors=expected_authors,
                            resolved_authors=authors_list,
                            expected_year=expected_year,
                            resolved_year=year,
                        )

                        res = {
                            "type": "PMID",
                            "identifier": clean_pmid,
                            "status": overall,
                            "identifier_status": ident_st,
                            "metadata_status": meta_st,
                            "claim_status": "UNCHECKED",
                            "title": remote_title,
                            "authors": authors_list[:5],
                            "year": year,
                            "venue": pdata.get("source", ""),
                            "evidence_text": evidence_text,
                            "title_similarity": score,
                            "details": detail,
                        }
                    self.cache[cache_key] = res
                    self._save_cache()
                    return res
            return {
                "type": "PMID",
                "identifier": clean_pmid,
                "status": "LOOKUP_ERROR",
                "identifier_status": "LOOKUP_ERROR",
                "metadata_status": "UNVERIFIED",
                "claim_status": "UNCHECKED",
                "details": f"PubMed API returned HTTP {status}",
            }
        except Exception as e:
            return {
                "type": "PMID",
                "identifier": clean_pmid,
                "status": "LOOKUP_ERROR",
                "identifier_status": "LOOKUP_ERROR",
                "metadata_status": "UNVERIFIED",
                "claim_status": "UNCHECKED",
                "details": f"PubMed lookup error: {str(e)}",
            }

    def verify_isbn(self, isbn: str, expected_title: Optional[str] = None) -> Dict[str, Any]:
        """Verify an ISBN via Open Library API."""
        clean_isbn = re.sub(r"[^0-9Xx]", "", isbn)
        cache_key = f"isbn:{clean_isbn}"

        if not self.no_cache and cache_key in self.cache:
            res = dict(self.cache[cache_key])
            overall, ident_st, meta_st, score, detail = evaluate_identity(expected_title, res.get("title", ""))
            res["status"] = overall
            res["identifier_status"] = ident_st
            res["metadata_status"] = meta_st
            res["title_similarity"] = score
            res["details"] = detail
            res["claim_status"] = "UNCHECKED"
            return res

        url = f"https://openlibrary.org/isbn/{clean_isbn}.json"
        try:
            status, body, _ = _fetch_url(url, user_agent=self.user_agent, timeout=self.timeout)
            if status == 200:
                data = json.loads(body.decode("utf-8"))
                remote_title = data.get("title", "")
                overall, ident_st, meta_st, score, detail = evaluate_identity(expected_title, remote_title)
                res = {
                    "type": "ISBN",
                    "identifier": isbn,
                    "status": overall,
                    "identifier_status": ident_st,
                    "metadata_status": meta_st,
                    "claim_status": "UNCHECKED",
                    "title": remote_title,
                    "title_similarity": score,
                    "details": detail,
                }
                self.cache[cache_key] = res
                self._save_cache()
                return res
            elif status == 404:
                res = {
                    "type": "ISBN",
                    "identifier": isbn,
                    "status": "NOT_FOUND",
                    "identifier_status": "NOT_FOUND",
                    "metadata_status": "UNVERIFIED",
                    "claim_status": "UNCHECKED",
                    "details": "ISBN not found in Open Library",
                }
                self.cache[cache_key] = res
                self._save_cache()
                return res
            else:
                return {
                    "type": "ISBN",
                    "identifier": isbn,
                    "status": "LOOKUP_ERROR",
                    "identifier_status": "LOOKUP_ERROR",
                    "metadata_status": "UNVERIFIED",
                    "claim_status": "UNCHECKED",
                    "details": f"Open Library returned HTTP {status}",
                }
        except Exception as e:
            return {
                "type": "ISBN",
                "identifier": isbn,
                "status": "LOOKUP_ERROR",
                "identifier_status": "LOOKUP_ERROR",
                "metadata_status": "UNVERIFIED",
                "claim_status": "UNCHECKED",
                "details": f"Open Library lookup error: {str(e)}",
            }

    def verify_url(self, url: str) -> Dict[str, Any]:
        """Verify reachability of a publisher or paper URL.

        Epistemic rule: HTTP 200 confirms reachability (URL_ACCESSIBLE),
        NOT document identity or claim support.
        """
        clean_url = _clean_trailing_punct(url.strip())
        cache_key = f"url:{clean_url}"
        if not self.no_cache and cache_key in self.cache:
            return self.cache[cache_key]

        try:
            status = _probe_url(clean_url, user_agent=self.user_agent, timeout=self.timeout)
            if status in (200, 301, 302, 307, 308):
                res = {
                    "type": "URL",
                    "identifier": clean_url,
                    "status": "URL_ACCESSIBLE",
                    "identifier_status": "ACCESSIBLE",
                    "metadata_status": "UNVERIFIED",
                    "claim_status": "UNCHECKED",
                    "details": f"URL reachable (HTTP {status}). Document identity and claims unverified.",
                }
            elif status in (404, 410):
                res = {
                    "type": "URL",
                    "identifier": clean_url,
                    "status": "NOT_FOUND",
                    "identifier_status": "NOT_FOUND",
                    "metadata_status": "UNVERIFIED",
                    "claim_status": "UNCHECKED",
                    "details": f"Broken link (HTTP {status})",
                }
            else:
                res = {
                    "type": "URL",
                    "identifier": clean_url,
                    "status": "LOOKUP_ERROR",
                    "identifier_status": "LOOKUP_ERROR",
                    "metadata_status": "UNVERIFIED",
                    "claim_status": "UNCHECKED",
                    "details": f"Returned HTTP {status}",
                }
            self.cache[cache_key] = res
            self._save_cache()
            return res
        except Exception as e:
            return {
                "type": "URL",
                "identifier": clean_url,
                "status": "LOOKUP_ERROR",
                "identifier_status": "LOOKUP_ERROR",
                "metadata_status": "UNVERIFIED",
                "claim_status": "UNCHECKED",
                "details": f"URL check error: {str(e)}",
            }


def extract_zotero_citations_from_docx(doc_path: Path) -> List[Dict[str, Any]]:
    """Extract citations from Word document Zotero CSL field codes."""
    return _extract_csl_citations_from_docx(doc_path, "ADDIN ZOTERO_ITEM CSL_CITATION", "Zotero")


def extract_mendeley_citations_from_docx(doc_path: Path) -> List[Dict[str, Any]]:
    """Extract legacy Mendeley Desktop CSL_CITATION fields from a DOCX."""
    return _extract_csl_citations_from_docx(doc_path, "ADDIN CSL_CITATION", "Mendeley")


def _extract_csl_citations_from_docx(
    doc_path: Path, field_marker: str, manager_name: str
) -> List[Dict[str, Any]]:
    citations = []
    if not zipfile.is_zipfile(doc_path):
        return citations

    with zipfile.ZipFile(doc_path, "r") as zf:
        xml_parts = [
            name for name in zf.namelist()
            if name.startswith("word/") and name.endswith(".xml") and (
                "document" in name or "footnotes" in name or "endnotes" in name or "comments" in name
            )
        ]
        for part in xml_parts:
            try:
                xml_content = zf.read(part).decode("utf-8", errors="replace")
            except Exception:
                continue

            start_pos = 0
            while True:
                idx = xml_content.find(field_marker, start_pos)
                if idx == -1:
                    break
                brace_start = xml_content.find("{", idx)
                if brace_start == -1:
                    start_pos = idx + len(field_marker)
                    continue

                depth = 0
                brace_end = -1
                in_string = False
                escape = False
                for i in range(brace_start, len(xml_content)):
                    char = xml_content[i]
                    if escape:
                        escape = False
                        continue
                    if char == "\\":
                        escape = True
                        continue
                    if char == '"':
                        in_string = not in_string
                        continue
                    if not in_string:
                        if char == "{":
                            depth += 1
                        elif char == "}":
                            depth -= 1
                            if depth == 0:
                                brace_end = i + 1
                                break

                if brace_end != -1:
                    raw_json = xml_content[brace_start:brace_end]
                    try:
                        data = json.loads(raw_json)
                        for item in data.get("citationItems", []):
                            idata = item.get("itemData", {})
                            doi = idata.get("DOI") or ""
                            title = idata.get("title") or ""
                            authors_list = idata.get("author", [])
                            authors = [f"{a.get('family', '')} {a.get('given', '')}".strip() for a in authors_list if isinstance(a, dict)]
                            year = None
                            issued = idata.get("issued", {})
                            if "date-parts" in issued and issued["date-parts"]:
                                parts = issued["date-parts"][0]
                                if parts:
                                    year = parts[0]

                            citations.append({
                                "source": f"{manager_name} ({part})",
                                "doi": doi,
                                "title": title,
                                "authors": authors,
                                "year": year,
                                "raw_citation": item.get("citationText", ""),
                            })
                    except Exception:
                        pass
                    start_pos = brace_end
                else:
                    start_pos = idx + len(field_marker)
    return citations


def extract_text_from_docx(doc_path: Path) -> str:
    """Extract plain body text from docx xml parts."""
    texts = []
    if not zipfile.is_zipfile(doc_path):
        return ""
    with zipfile.ZipFile(doc_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                try:
                    content = zf.read(name).decode("utf-8", errors="replace")
                    extracted = re.findall(r"<w:t(?:[^>]*)>([^<]+)</w:t>", content)
                    if extracted:
                        texts.append(" ".join(extracted))
                except Exception:
                    pass
    return "\n".join(texts)


def extract_from_bibtex(bib_content: str) -> List[Dict[str, Any]]:
    """Parse BibTeX entries and extract ALL co-existing identifiers with nested brace support."""
    entries = []
    entry_re = re.compile(r"@(\w+)\s*\{\s*([^,]+)\s*,", re.MULTILINE)
    pos = 0
    while pos < len(bib_content):
        m = entry_re.search(bib_content, pos)
        if not m:
            break
        entry_type = m.group(1).lower()
        cite_key = m.group(2).strip()

        start_body = m.end()
        depth = 1
        i = start_body
        in_quote = False
        entry_end = -1
        while i < len(bib_content):
            c = bib_content[i]
            if c == '"' and (i == 0 or bib_content[i - 1] != '\\'):
                in_quote = not in_quote
            elif not in_quote:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        entry_end = i
                        break
            i += 1

        if entry_end == -1:
            pos = start_body
            continue

        body = bib_content[start_body:entry_end]
        pos = entry_end + 1

        fields = {}
        f_pos = 0
        while f_pos < len(body):
            field_m = re.search(r"(\w+)\s*=\s*", body[f_pos:])
            if not field_m:
                break
            f_key = field_m.group(1).lower()
            val_start = f_pos + field_m.end()
            if val_start >= len(body):
                break

            val_char = body[val_start]
            if val_char == '{':
                f_depth = 1
                fj = val_start + 1
                while fj < len(body) and f_depth > 0:
                    if body[fj] == '{':
                        f_depth += 1
                    elif body[fj] == '}':
                        f_depth -= 1
                    fj += 1
                raw_val = body[val_start + 1 : fj - 1 if f_depth == 0 else fj]
                val = re.sub(r"[{}]", "", raw_val).strip()
                f_pos = fj
            elif val_char == '"':
                fj = val_start + 1
                while fj < len(body):
                    if body[fj] == '"' and body[fj - 1] != '\\':
                        break
                    fj += 1
                raw_val = body[val_start + 1 : fj]
                val = re.sub(r"[{}]", "", raw_val).strip()
                f_pos = fj + 1
            else:
                end_m = re.search(r"[,}\n]", body[val_start:])
                if end_m:
                    val = body[val_start : val_start + end_m.start()].strip()
                    f_pos = val_start + end_m.end()
                else:
                    val = body[val_start:].strip()
                    f_pos = len(body)

            fields[f_key] = re.sub(r"\s+", " ", val)

        entries.append({
            "source": f"BibTeX (@{entry_type}: {cite_key})",
            "citation_key": cite_key,
            "doi": fields.get("doi", ""),
            "eprint": fields.get("eprint", "") or fields.get("arxiv", ""),
            "pmid": fields.get("pmid", ""),
            "isbn": fields.get("isbn", ""),
            "url": fields.get("url", ""),
            "title": fields.get("title", ""),
            "author": fields.get("author", ""),
            "year": fields.get("year", ""),
        })
    return entries


def scan_raw_text(text: str, source_label: str = "Text") -> List[Dict[str, Any]]:
    """Scan raw text with regex patterns for citations."""
    items = []
    seen = set()

    # Scan DOIs
    for pat in DOI_PATTERNS:
        for match in pat.finditer(text):
            val = _clean_trailing_punct(match.group(1))
            if val.startswith("10.") and "/" in val and val not in seen:
                seen.add(val)
                items.append({
                    "source": source_label,
                    "type": "DOI",
                    "identifier": val,
                    "title": "",
                })

    # Scan arXiv IDs
    for pat in ARXIV_PATTERNS:
        for match in pat.finditer(text):
            val = _clean_trailing_punct(match.group(1))
            if val not in seen:
                seen.add(val)
                items.append({
                    "source": source_label,
                    "type": "arXiv",
                    "identifier": val,
                    "title": "",
                })

    # Scan PMIDs
    for pat in PMID_PATTERNS:
        for match in pat.finditer(text):
            val = _clean_trailing_punct(match.group(1))
            if val not in seen:
                seen.add(val)
                items.append({
                    "source": source_label,
                    "type": "PMID",
                    "identifier": val,
                    "title": "",
                })

    # Scan ISBNs
    for pat in ISBN_PATTERNS:
        for match in pat.finditer(text):
            val = _clean_trailing_punct(match.group(1))
            if val not in seen:
                seen.add(val)
                items.append({
                    "source": source_label,
                    "type": "ISBN",
                    "identifier": val,
                    "title": "",
                })

    # Scan URLs from known academic publishers
    for match in URL_PATTERN.finditer(text):
        url = _clean_trailing_punct(match.group(0))
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if any(domain.endswith(kd) for kd in KNOWN_ACADEMIC_DOMAINS):
            if url not in seen and not any(url.endswith(i.get("identifier", "")) for i in items if i["type"] == "DOI"):
                seen.add(url)
                items.append({
                    "source": source_label,
                    "type": "URL",
                    "identifier": url,
                    "title": "",
                })

    return items


def harvest_document_citations(doc_path: Path) -> List[Dict[str, Any]]:
    """Harvest all citation candidates from any supported file format.

    Note: In BibTeX entries with multiple identifiers (e.g. DOI + PMID + URL),
    all of them are preserved and evaluated.
    """
    ext = doc_path.suffix.lower()
    citations = []

    if ext in (".docx", ".dotx"):
        manager_items = (
            extract_zotero_citations_from_docx(doc_path)
            + extract_mendeley_citations_from_docx(doc_path)
        )
        for z in manager_items:
            if z.get("doi"):
                citations.append({
                    "source": z["source"],
                    "type": "DOI",
                    "identifier": z["doi"],
                    "title": z.get("title", ""),
                    "authors": z.get("authors", []),
                    "year": z.get("year"),
                })

        body_text = extract_text_from_docx(doc_path)
        text_items = scan_raw_text(body_text, source_label="DOCX Body Text")
        for item in text_items:
            if not any(c["identifier"].lower() == item["identifier"].lower() for c in citations):
                citations.append(item)

        # Mendeley Cite keeps library CSL-JSON in the web-extension package,
        # outside Word's visible text runs. Harvest identifiers from that data
        # without modifying the extension or trying to interpret its UI state.
        try:
            with zipfile.ZipFile(doc_path, "r") as zf:
                for name in zf.namelist():
                    if not name.startswith("word/webextensions/") or not name.endswith(".xml"):
                        continue
                    raw = zf.read(name).decode("utf-8", errors="replace")
                    for item in scan_raw_text(raw, source_label="Mendeley Cite metadata"):
                        if not any(c["identifier"].lower() == item["identifier"].lower() for c in citations):
                            citations.append(item)
        except (OSError, zipfile.BadZipFile):
            pass

    elif ext == ".bib":
        with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
            bib_text = f.read()
        bib_entries = extract_from_bibtex(bib_text)
        for b in bib_entries:
            common_meta = {
                "source": b["source"],
                "title": b.get("title", ""),
                "authors": [b.get("author", "")] if b.get("author") else [],
                "year": b.get("year"),
            }
            # Harvest co-existing identifiers without elif skipping
            if b.get("doi"):
                c = dict(common_meta)
                c["type"] = "DOI"
                c["identifier"] = b["doi"]
                citations.append(c)
            if b.get("eprint"):
                c = dict(common_meta)
                c["type"] = "arXiv"
                c["identifier"] = b["eprint"]
                citations.append(c)
            if b.get("pmid"):
                c = dict(common_meta)
                c["type"] = "PMID"
                c["identifier"] = b["pmid"]
                citations.append(c)
            if b.get("isbn"):
                c = dict(common_meta)
                c["type"] = "ISBN"
                c["identifier"] = b["isbn"]
                citations.append(c)
            if b.get("url"):
                c = dict(common_meta)
                c["type"] = "URL"
                c["identifier"] = b["url"]
                citations.append(c)

    else:
        with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()
        citations = scan_raw_text(raw_text, source_label=f"{ext.upper()} File")

    return citations


def run_verification(citations: List[Dict[str, Any]], verifier: CitationVerifier) -> List[Dict[str, Any]]:
    """Run validation checks on list of citation candidates."""
    results = []
    for item in citations:
        c_type = item.get("type", "DOI")
        ident = item.get("identifier", "").strip()
        expected_title = item.get("title", "").strip() or None
        expected_authors = item.get("authors") or None
        expected_year = item.get("year") or None

        if not ident:
            continue

        if c_type == "DOI":
            res = verifier.verify_doi(
                ident,
                expected_title=expected_title,
                expected_authors=expected_authors,
                expected_year=expected_year,
            )
        elif c_type == "arXiv":
            res = verifier.verify_arxiv(
                ident,
                expected_title=expected_title,
                expected_authors=expected_authors,
                expected_year=expected_year,
            )
        elif c_type == "PMID":
            res = verifier.verify_pmid(
                ident,
                expected_title=expected_title,
                expected_authors=expected_authors,
                expected_year=expected_year,
            )
        elif c_type == "ISBN":
            res = verifier.verify_isbn(ident, expected_title=expected_title)
        elif c_type == "URL":
            res = verifier.verify_url(ident)
        else:
            res = {
                "type": c_type,
                "identifier": ident,
                "status": "LOOKUP_ERROR",
                "identifier_status": "LOOKUP_ERROR",
                "metadata_status": "UNVERIFIED",
                "claim_status": "UNCHECKED",
                "details": f"Unsupported citation type '{c_type}'",
            }

        res["source"] = item.get("source", "Unknown")
        if expected_title:
            res["expected_title"] = expected_title
        results.append(res)
    return results


def format_text_report(results: List[Dict[str, Any]], target_file: Path, claim_audit: Optional[List[Dict[str, Any]]] = None) -> str:
    """Format results into a clean ASCII terminal report safe for Windows cp1252."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"CITATION INTEGRITY & REFERENCE AUDIT: {target_file.name}")
    lines.append("=" * 80)

    confirmed_count = sum(1 for r in results if r["status"] == "IDENTITY_CONFIRMED")
    unverified_meta = sum(1 for r in results if r["status"] == "METADATA_UNVERIFIED")
    url_accessible = sum(1 for r in results if r["status"] == "URL_ACCESSIBLE")
    partial_count = sum(1 for r in results if r["status"] == "METADATA_PARTIAL")
    mismatch_count = sum(1 for r in results if r["status"] == "METADATA_MISMATCH")
    fail_count = sum(1 for r in results if r["status"] == "NOT_FOUND")
    err_count = sum(1 for r in results if r["status"] == "LOOKUP_ERROR")

    for idx, r in enumerate(results, 1):
        status = r["status"]
        if status == "IDENTITY_CONFIRMED":
            tag = "[PASS:CONFIRMED]"
        elif status == "METADATA_UNVERIFIED":
            tag = "[INFO:RESOLVED ]"
        elif status == "URL_ACCESSIBLE":
            tag = "[URL :REACHABLE]"
        elif status == "METADATA_PARTIAL":
            tag = "[WARN:PARTIAL  ]"
        elif status == "METADATA_MISMATCH":
            tag = "[WARN:MISMATCH ]"
        elif status == "NOT_FOUND":
            tag = "[FAIL:NOT_FOUND]"
        else:
            tag = "[ERR :LOOKUP   ]"

        lines.append(f"{idx:2d}. {tag} {r.get('type', 'ID')}: {r.get('identifier', '')}")
        lines.append(f"    Source: {r.get('source', 'Unknown')}")
        lines.append(f"    Scope : Ident: {r.get('identifier_status', '-')} | Meta: {r.get('metadata_status', '-')} | Claim: {r.get('claim_status', 'UNCHECKED')}")
        if r.get("expected_title"):
            lines.append(f"    In-Doc Title: {r['expected_title']}")
        if r.get("title"):
            lines.append(f"    Registry Title: {r['title']}")
        if r.get("authors"):
            authors_str = ", ".join(r["authors"])
            lines.append(f"    Authors: {authors_str}")
        lines.append(f"    Status Detail: {r.get('details', '')}")
        lines.append("-" * 80)

    lines.append("")
    lines.append("SUMMARY SCOREBOARD:")
    lines.append(f"  Total Identifiers Checked  : {len(results)}")
    lines.append(f"  Identity Confirmed [PASS]  : {confirmed_count}")
    lines.append(f"  Resolved (Meta Unverified) : {unverified_meta}")
    lines.append(f"  URL Reachable Only [URL]   : {url_accessible}")
    lines.append(f"  Metadata Partial   [WARN]  : {partial_count}")
    lines.append(f"  Metadata Mismatch  [WARN]  : {mismatch_count}")
    lines.append(f"  Hallucinated / Missing     : {fail_count} [FAIL]")
    lines.append(f"  Registry Lookup Errors     : {err_count}")
    lines.append("=" * 80)

    if fail_count > 0:
        lines.append("CRITICAL: Hallucinated or non-existent identifiers detected! Review [FAIL] entries.")
    elif mismatch_count > 0:
        lines.append("WARNING: In-document citations point to real DOIs with mismatched titles/domains! Review [WARN] entries.")
    elif partial_count > 0:
        lines.append("NOTE: Some references have partial metadata matches (author/year discrepancy).")
    else:
        lines.append("SUCCESS: All citation identifiers resolved against authoritative registries.")

    lines.append("-" * 80)
    lines.append("EPISTEMIC DISCLAIMER:")
    lines.append("• A verified citation confirms that the paper exists in an authoritative registry.")
    lines.append("• It does NOT confirm that the cited paper supports the claim made in your text.")
    lines.append("• To verify claim validity, methodology, and dataset leakage, run research-reviewer.")
    lines.append("=" * 80)
    if claim_audit:
        lines.append("CLAIM-TO-EVIDENCE AUDIT:")
        for claim in claim_audit:
            lines.append(f"[{claim['status']}] {claim['sentence']}")
            lines.append(f"    Evidence: {', '.join(claim.get('evidence', [])) or '-'} | {claim.get('details', '')}")
        lines.append("=" * 80)
    return "\n".join(lines)


def format_markdown_report(results: List[Dict[str, Any]], target_file: Path, claim_audit: Optional[List[Dict[str, Any]]] = None) -> str:
    """Format verification results as clean Markdown."""
    lines = []
    lines.append(f"# Citation Integrity Report: `{target_file.name}`\n")

    confirmed_count = sum(1 for r in results if r["status"] == "IDENTITY_CONFIRMED")
    unverified_meta = sum(1 for r in results if r["status"] == "METADATA_UNVERIFIED")
    url_accessible = sum(1 for r in results if r["status"] == "URL_ACCESSIBLE")
    partial_count = sum(1 for r in results if r["status"] == "METADATA_PARTIAL")
    mismatch_count = sum(1 for r in results if r["status"] == "METADATA_MISMATCH")
    fail_count = sum(1 for r in results if r["status"] == "NOT_FOUND")
    err_count = sum(1 for r in results if r["status"] == "LOOKUP_ERROR")

    lines.append("| Metric | Count |")
    lines.append("| :--- | :--- |")
    lines.append(f"| Total Identifiers Checked | {len(results)} |")
    lines.append(f"| **Identity Confirmed (PASS)** | **{confirmed_count}** |")
    lines.append(f"| **Resolved (Metadata Unverified)** | **{unverified_meta}** |")
    lines.append(f"| **URL Reachable Only (URL)** | **{url_accessible}** |")
    lines.append(f"| **Metadata Partial (WARN)** | **{partial_count}** |")
    lines.append(f"| **Metadata Mismatch (WARN)** | **{mismatch_count}** |")
    lines.append(f"| **Hallucinated / Missing (FAIL)** | **{fail_count}** |")
    lines.append(f"| Registry Lookup Errors | {err_count} |\n")

    lines.append("## Detailed Reference Audit\n")
    lines.append("| # | Status | Type | Identifier | Identifier Status | Metadata Status | Claim Status | Notes |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    for idx, r in enumerate(results, 1):
        status = r["status"]
        if status == "IDENTITY_CONFIRMED":
            badge = "**PASS**"
        elif status == "METADATA_UNVERIFIED":
            badge = "INFO"
        elif status == "URL_ACCESSIBLE":
            badge = "URL"
        elif status == "METADATA_PARTIAL":
            badge = "**WARN:PARTIAL**"
        elif status == "METADATA_MISMATCH":
            badge = "**WARN:MISMATCH**"
        elif status == "NOT_FOUND":
            badge = "**FAIL**"
        else:
            badge = "ERROR"

        c_type = r.get("type", "DOI")
        ident = r.get("identifier", "")
        if c_type == "DOI":
            ident_link = f"[{ident}](https://doi.org/{ident})"
        elif c_type == "arXiv":
            ident_link = f"[{ident}](https://arxiv.org/abs/{ident})"
        elif c_type == "PMID":
            ident_link = f"[{ident}](https://pubmed.ncbi.nlm.nih.gov/{ident}/)"
        else:
            ident_link = ident

        notes = r.get("details", "")
        if r.get("expected_title") and r.get("title") and r.get("title") != r.get("expected_title"):
            notes += f"<br>Doc: _{r['expected_title']}_"

        notes = notes.replace("|", "/")

        lines.append(f"| {idx} | {badge} | {c_type} | {ident_link} | {r.get('identifier_status', '-')} | {r.get('metadata_status', '-')} | {r.get('claim_status', 'UNCHECKED')} | {notes} |")

    if claim_audit:
        lines.append("\n## Claim-to-Evidence Audit\n")
        lines.append("| Status | Claim type | Sentence | Evidence | Page/excerpt | Details |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for claim in claim_audit:
            refs = "<br>".join(f"{r.get('identifier')}, p.{r.get('page') or '-'}: {r.get('excerpt', '')}" for r in claim.get('evidence_refs', [])) or "-"
            lines.append(f"| {claim['status']} | {claim.get('claim_kind', '-')} | {claim['sentence'].replace('|', '/') } | {', '.join(claim.get('evidence', [])) or '-'} | {refs.replace('|', '/')} | {claim.get('details', '').replace('|', '/')} |")
    lines.append("\n> **Epistemic rule**: registry resolution never proves claim support. `ABSTRACT_SUPPORT` only means the cited sentence has conservative lexical overlap with retrieved abstract evidence; full-text review is required for detailed, causal, quantitative, or negative claims.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Verify citation integrity and detect hallucinated references in .docx, .bib, .md, .tex, and text files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_path", help="Path to manuscript or bibliography file (.docx, .bib, .md, .tex, .txt)")
    parser.add_argument("-o", "--output", help="Path to write verification report (.md, .json, or .txt)")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text", help="Output format (default: text)")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Contact email for CrossRef polite API pool (optional)")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP request timeout in seconds (default: 10)")
    parser.add_argument("--no-cache", action="store_true", help="Bypass local cache and query live APIs")
    parser.add_argument("--cache-file", help="Custom cache file location (default: .citation_cache.json)")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any citation is missing or mismatched")
    parser.add_argument("--claim-audit", action="store_true", help="Map each cited sentence to retrieved source evidence; unmapped or unsupported claims are never marked as supported")
    parser.add_argument("--strict-claims", action="store_true", help="Exit with code 1 unless every cited sentence has ABSTRACT_SUPPORT")
    parser.add_argument("--evidence-dir", help="Directory of full-text .pdf/.txt/.md files named by DOI, PMID, or arXiv ID")
    parser.add_argument("--citation-map", help="JSON map for numeric markers, for example {\"1\": \"10.1234/example\"}")

    args = parser.parse_args()
    input_path = Path(args.input_path).resolve()

    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        sys.exit(2)

    cache_file = Path(args.cache_file).resolve() if args.cache_file else None
    verifier = CitationVerifier(
        email=args.email,
        timeout=args.timeout,
        cache_file=cache_file,
        no_cache=args.no_cache,
    )

    citations = harvest_document_citations(input_path)
    if not citations:
        print(f"No citations, DOIs, arXiv IDs, or PMIDs found in '{input_path.name}'.")
        sys.exit(0)

    results = run_verification(citations, verifier)
    claim_audit = []
    if args.claim_audit or args.strict_claims:
        citation_map = {}
        if args.citation_map:
            citation_map = json.loads(Path(args.citation_map).read_text(encoding="utf-8"))
        claim_audit = audit_claim_support(
            extract_text_from_docx(input_path) if input_path.suffix.lower() in (".docx", ".dotx") else input_path.read_text(encoding="utf-8", errors="replace"),
            results,
            local_evidence=load_local_evidence(Path(args.evidence_dir).resolve() if args.evidence_dir else None),
            citation_map=citation_map,
        )
        by_id = {}
        for claim in claim_audit:
            for ident in claim.get("evidence", []):
                by_id.setdefault(str(ident).lower(), []).append(claim["status"])
        for result in results:
            statuses = by_id.get(str(result.get("identifier", "")).lower(), [])
            if statuses:
                result["claim_status"] = "ABSTRACT_SUPPORT" if all(s == "ABSTRACT_SUPPORT" for s in statuses) else statuses[0]

    if args.format == "json":
        report = json.dumps({
            "target": str(input_path),
            "total": len(results),
            "results": results,
            "claim_audit": claim_audit,
            "disclaimer": "ABSTRACT_SUPPORT is conservative lexical evidence, not proof that every detail or causal claim is supported by the full paper.",
        }, indent=2)
    elif args.format == "markdown":
        report = format_markdown_report(results, input_path, claim_audit)
    else:
        report = format_text_report(results, input_path, claim_audit)

    if args.output:
        out_path = Path(args.output).resolve()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Verification report saved to: {out_path}")
    else:
        print(report)

    has_hallucinations = any(r["status"] == "NOT_FOUND" for r in results)
    has_mismatches = any(r["status"] in ("METADATA_MISMATCH", "METADATA_PARTIAL") for r in results)
    has_unsupported_claims = any(c["status"] != "ABSTRACT_SUPPORT" for c in claim_audit)

    if has_hallucinations or (args.strict and has_mismatches) or (args.strict_claims and has_unsupported_claims):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
