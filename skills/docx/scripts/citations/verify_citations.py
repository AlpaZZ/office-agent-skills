#!/usr/bin/env python3
"""verify_citations.py - Citation and Reference Verifier for Office & Academic Documents.

Detects and validates citations, DOIs, arXiv IDs, PMIDs, ISBNs, and publisher URLs
in Word documents (.docx), BibTeX files (.bib), Markdown (.md), LaTeX (.tex), and plain text.
Flags hallucinated, broken, or mismatched references against CrossRef, arXiv, PubMed, and Open Library.

Features:
- .docx parsing: reads both Zotero CSL field codes (JSON metadata) and body text/footnotes/tables.
- .bib parsing: parses BibTeX entries and fields (doi, eprint, pmid, isbn, title, author, url).
- Text/Markdown parsing: extracts DOIs, arXiv IDs, PMIDs, ISBNs, and paper URLs via regex.
- Anti-hallucination check: compares paper titles from registries with local document text.
- Resilient networking: uses SSL fallback for Windows environments, respectful User-Agent, and caching.
- Safe console output: ASCII status markers ([PASS], [FAIL], [WARN]) compatible with Windows cp1252.

Credits:
- Inspired by John Kitchin's citation-verifier (https://github.com/jkitchin/skillz).
"""

import argparse
import difflib
import json
import os
import re
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Default contact email for CrossRef polite API pool
DEFAULT_EMAIL = os.environ.get("CITATION_VERIFIER_EMAIL", "alfarizki1810@gmail.com")
USER_AGENT = f"CitationVerifier/1.0 (mailto:{DEFAULT_EMAIL}; https://github.com/AlpaZZ/office-agent-skills)"

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
    ctx = ssl._create_unverified_context()
    return ctx


def _fetch_url(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> Tuple[int, bytes, Dict[str, str]]:
    """Fetch URL with timeout and fallback SSL context."""
    req_headers = {
        "User-Agent": USER_AGENT,
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
        # Retry once with unverified context if it was an SSL certificate verification failure
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            fallback_ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=fallback_ctx, timeout=timeout) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        raise e


def normalize_title(title: str) -> str:
    """Normalize paper title for fuzzy comparison."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"<[^>]+>", "", t)  # strip xml/html tags
    t = re.sub(r"[^a-z0-9\s]", " ", t)  # strip punctuation
    t = re.sub(r"\s+", " ", t).strip()
    return t


def titles_match(t1: str, t2: str, threshold: float = 0.65) -> Tuple[bool, float]:
    """Compare two titles using normalized sequence ratio and token overlap."""
    n1 = normalize_title(t1)
    n2 = normalize_title(t2)
    if not n1 or not n2:
        return True, 1.0  # Cannot refute if one side has no title

    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    if ratio >= threshold:
        return True, ratio

    # Token overlap check (useful when subtitles are omitted or truncated)
    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    stopwords = {"a", "an", "the", "in", "on", "of", "for", "with", "and", "to", "at", "by", "from"}
    tokens1 -= stopwords
    tokens2 -= stopwords

    if tokens1 and tokens2:
        overlap = len(tokens1 & tokens2) / min(len(tokens1), len(tokens2))
        if overlap >= 0.7:
            return True, max(ratio, overlap)

    return False, ratio


class CitationVerifier:
    def __init__(self, email: str = DEFAULT_EMAIL, timeout: int = 10, cache_file: Optional[Path] = None, no_cache: bool = False):
        self.email = email
        self.timeout = timeout
        self.no_cache = no_cache
        self.cache_file = cache_file or (Path.cwd() / ".citation_cache.json")
        self.cache: Dict[str, Any] = {}
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

    def verify_doi(self, doi: str, expected_title: Optional[str] = None) -> Dict[str, Any]:
        """Verify a DOI against CrossRef REST API."""
        clean_doi = _clean_trailing_punct(doi.strip())
        cache_key = f"doi:{clean_doi.lower()}"
        if not self.no_cache and cache_key in self.cache:
            res = dict(self.cache[cache_key])
            if expected_title and res.get("title"):
                matched, score = titles_match(expected_title, res["title"])
                res["title_similarity"] = round(score, 2)
                if not matched:
                    res["status"] = "METADATA_MISMATCH"
                    res["details"] = f"DOI exists, but resolved title differs: '{res['title']}' (similarity: {score:.2f})"
            return res

        url = f"https://api.crossref.org/works/{urllib.parse.quote(clean_doi, safe='/:')}"
        headers = {
            "User-Agent": f"CitationVerifier/1.0 (mailto:{self.email}; https://github.com/AlpaZZ/office-agent-skills)",
            "Accept": "application/json",
        }

        try:
            status, body, _ = _fetch_url(url, headers=headers, timeout=self.timeout)
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

                res = {
                    "type": "DOI",
                    "identifier": clean_doi,
                    "status": "VERIFIED",
                    "title": remote_title,
                    "authors": authors[:5],
                    "venue": journal,
                    "year": year,
                    "details": "Resolved via CrossRef",
                }

                if expected_title:
                    matched, score = titles_match(expected_title, remote_title)
                    res["title_similarity"] = round(score, 2)
                    if not matched:
                        res["status"] = "METADATA_MISMATCH"
                        res["details"] = f"DOI exists, but resolved title differs: '{remote_title}' (similarity: {score:.2f})"

                self.cache[cache_key] = res
                self._save_cache()
                return res

            elif status == 404:
                res = {
                    "type": "DOI",
                    "identifier": clean_doi,
                    "status": "NOT_FOUND",
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
                    "details": f"CrossRef returned HTTP {status}",
                }
        except Exception as e:
            return {
                "type": "DOI",
                "identifier": clean_doi,
                "status": "LOOKUP_ERROR",
                "details": f"Connection error: {str(e)}",
            }

    def verify_arxiv(self, arxiv_id: str, expected_title: Optional[str] = None) -> Dict[str, Any]:
        """Verify an arXiv identifier via the official arXiv API."""
        clean_id = _clean_trailing_punct(arxiv_id.strip())
        cache_key = f"arxiv:{clean_id.lower()}"
        if not self.no_cache and cache_key in self.cache:
            res = dict(self.cache[cache_key])
            if expected_title and res.get("title"):
                matched, score = titles_match(expected_title, res["title"])
                res["title_similarity"] = round(score, 2)
                if not matched:
                    res["status"] = "METADATA_MISMATCH"
                    res["details"] = f"arXiv article exists, but title differs: '{res['title']}' (similarity: {score:.2f})"
            return res

        url = f"https://export.arxiv.org/api/query?id_list={clean_id}"
        try:
            status, body, _ = _fetch_url(url, timeout=self.timeout)
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
                            "details": "arXiv ID not found in arXiv repository",
                        }
                    else:
                        authors = [a.find("{http://www.w3.org/2005/Atom}name").text for a in entry.findall("{http://www.w3.org/2005/Atom}author")]
                        published_elem = entry.find("{http://www.w3.org/2005/Atom}published")
                        year = published_elem.text[:4] if published_elem is not None and published_elem.text else None
                        res = {
                            "type": "arXiv",
                            "identifier": clean_id,
                            "status": "VERIFIED",
                            "title": remote_title,
                            "authors": authors[:5],
                            "year": year,
                            "details": "Resolved via arXiv API",
                        }
                        if expected_title:
                            matched, score = titles_match(expected_title, remote_title)
                            res["title_similarity"] = round(score, 2)
                            if not matched:
                                res["status"] = "METADATA_MISMATCH"
                                res["details"] = f"arXiv article exists, but title differs: '{remote_title}' (similarity: {score:.2f})"
                    self.cache[cache_key] = res
                    self._save_cache()
                    return res
            return {
                "type": "arXiv",
                "identifier": clean_id,
                "status": "LOOKUP_ERROR",
                "details": f"arXiv API returned status {status}",
            }
        except Exception as e:
            return {
                "type": "arXiv",
                "identifier": clean_id,
                "status": "LOOKUP_ERROR",
                "details": f"arXiv lookup error: {str(e)}",
            }

    def verify_pmid(self, pmid: str, expected_title: Optional[str] = None) -> Dict[str, Any]:
        """Verify a PubMed PMID via NCBI E-utilities."""
        clean_pmid = _clean_trailing_punct(pmid.strip())
        cache_key = f"pmid:{clean_pmid}"
        if not self.no_cache and cache_key in self.cache:
            return self.cache[cache_key]

        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={clean_pmid}&retmode=json"
        try:
            status, body, _ = _fetch_url(url, timeout=self.timeout)
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
                            "details": "PMID not found in PubMed",
                        }
                    else:
                        remote_title = pdata.get("title", "")
                        authors_list = [a.get("name") for a in pdata.get("authors", []) if isinstance(a, dict) and "name" in a]
                        year = pdata.get("pubdate", "")[:4]
                        res = {
                            "type": "PMID",
                            "identifier": clean_pmid,
                            "status": "VERIFIED",
                            "title": remote_title,
                            "authors": authors_list[:5],
                            "year": year,
                            "venue": pdata.get("source", ""),
                            "details": "Resolved via PubMed E-utilities",
                        }
                        if expected_title:
                            matched, score = titles_match(expected_title, remote_title)
                            res["title_similarity"] = round(score, 2)
                            if not matched:
                                res["status"] = "METADATA_MISMATCH"
                                res["details"] = f"PMID exists, but title differs: '{remote_title}' (similarity: {score:.2f})"
                    self.cache[cache_key] = res
                    self._save_cache()
                    return res
            return {
                "type": "PMID",
                "identifier": clean_pmid,
                "status": "LOOKUP_ERROR",
                "details": f"PubMed API returned HTTP {status}",
            }
        except Exception as e:
            return {
                "type": "PMID",
                "identifier": clean_pmid,
                "status": "LOOKUP_ERROR",
                "details": f"PubMed lookup error: {str(e)}",
            }

    def verify_isbn(self, isbn: str, expected_title: Optional[str] = None) -> Dict[str, Any]:
        """Verify an ISBN via Open Library API."""
        clean_isbn = re.sub(r"[^0-9Xx]", "", isbn)
        cache_key = f"isbn:{clean_isbn}"
        if not self.no_cache and cache_key in self.cache:
            return self.cache[cache_key]

        url = f"https://openlibrary.org/isbn/{clean_isbn}.json"
        try:
            status, body, _ = _fetch_url(url, timeout=self.timeout)
            if status == 200:
                data = json.loads(body.decode("utf-8"))
                remote_title = data.get("title", "")
                res = {
                    "type": "ISBN",
                    "identifier": isbn,
                    "status": "VERIFIED",
                    "title": remote_title,
                    "details": "Resolved via Open Library",
                }
                if expected_title:
                    matched, score = titles_match(expected_title, remote_title)
                    res["title_similarity"] = round(score, 2)
                    if not matched:
                        res["status"] = "METADATA_MISMATCH"
                        res["details"] = f"ISBN exists, but title differs: '{remote_title}' (similarity: {score:.2f})"
                self.cache[cache_key] = res
                self._save_cache()
                return res
            elif status == 404:
                res = {
                    "type": "ISBN",
                    "identifier": isbn,
                    "status": "NOT_FOUND",
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
                    "details": f"Open Library returned HTTP {status}",
                }
        except Exception as e:
            return {
                "type": "ISBN",
                "identifier": isbn,
                "status": "LOOKUP_ERROR",
                "details": f"Open Library lookup error: {str(e)}",
            }

    def verify_url(self, url: str) -> Dict[str, Any]:
        """Verify accessibility of a publisher or paper URL."""
        clean_url = _clean_trailing_punct(url.strip())
        cache_key = f"url:{clean_url}"
        if not self.no_cache and cache_key in self.cache:
            return self.cache[cache_key]

        try:
            status, _, _ = _fetch_url(clean_url, timeout=self.timeout)
            if status in (200, 301, 302, 307, 308):
                res = {
                    "type": "URL",
                    "identifier": clean_url,
                    "status": "VERIFIED",
                    "details": f"Accessible (HTTP {status})",
                }
            elif status in (404, 410):
                res = {
                    "type": "URL",
                    "identifier": clean_url,
                    "status": "NOT_FOUND",
                    "details": f"Broken link (HTTP {status})",
                }
            else:
                res = {
                    "type": "URL",
                    "identifier": clean_url,
                    "status": "LOOKUP_ERROR",
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
                "details": f"URL check error: {str(e)}",
            }


def extract_zotero_citations_from_docx(doc_path: Path) -> List[Dict[str, Any]]:
    """Extract citations from Word document Zotero CSL field codes."""
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

            # Balanced brace parsing for ADDIN ZOTERO_ITEM CSL_CITATION
            start_pos = 0
            while True:
                idx = xml_content.find("ADDIN ZOTERO_ITEM CSL_CITATION", start_pos)
                if idx == -1:
                    break
                brace_start = xml_content.find("{", idx)
                if brace_start == -1:
                    start_pos = idx + len("ADDIN ZOTERO_ITEM CSL_CITATION")
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
                                "source": f"Zotero ({part})",
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
                    start_pos = idx + len("ADDIN ZOTERO_ITEM CSL_CITATION")
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
                    # Quick regex to extract <w:t> content
                    extracted = re.findall(r"<w:t(?:[^>]*)>([^<]+)</w:t>", content)
                    if extracted:
                        texts.append(" ".join(extracted))
                except Exception:
                    pass
    return "\n".join(texts)


def extract_from_bibtex(bib_content: str) -> List[Dict[str, Any]]:
    """Parse BibTeX entries and extract identifiers with title/authors."""
    entries = []
    # Match @type{key, ...} allowing whitespace before closing brace
    pattern = re.compile(r"@(\w+)\s*\{\s*([^,]+),\s*([\s\S]*?)\s*\}\s*(?=@|\Z)", re.MULTILINE)
    for match in pattern.finditer(bib_content):
        entry_type = match.group(1).lower()
        cite_key = match.group(2).strip()
        body = match.group(3)

        fields = {}
        # Match field = {val} or field = "val"
        field_pattern = re.compile(r"(\w+)\s*=\s*[\"|\{]([\s\S]*?)[\"|\}]\s*(?:,|$)", re.MULTILINE)
        for fmatch in field_pattern.finditer(body):
            fkey = fmatch.group(1).lower()
            fval = fmatch.group(2).strip().replace("\n", " ")
            fields[fkey] = fval

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
    """Harvest all citation candidates from any supported file format."""
    ext = doc_path.suffix.lower()
    citations = []

    if ext in (".docx", ".dotx"):
        # 1. Zotero field codes
        zotero_items = extract_zotero_citations_from_docx(doc_path)
        for z in zotero_items:
            if z.get("doi"):
                citations.append({
                    "source": z["source"],
                    "type": "DOI",
                    "identifier": z["doi"],
                    "title": z.get("title", ""),
                    "authors": z.get("authors", []),
                    "year": z.get("year"),
                })

        # 2. Body text regex scan
        body_text = extract_text_from_docx(doc_path)
        text_items = scan_raw_text(body_text, source_label="DOCX Body Text")
        for item in text_items:
            # avoid re-adding DOIs already extracted from Zotero
            if not any(c["identifier"].lower() == item["identifier"].lower() for c in citations):
                citations.append(item)

    elif ext == ".bib":
        with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
            bib_text = f.read()
        bib_entries = extract_from_bibtex(bib_text)
        for b in bib_entries:
            if b.get("doi"):
                citations.append({
                    "source": b["source"],
                    "type": "DOI",
                    "identifier": b["doi"],
                    "title": b.get("title", ""),
                    "authors": [b.get("author", "")] if b.get("author") else [],
                    "year": b.get("year"),
                })
            elif b.get("eprint"):
                citations.append({
                    "source": b["source"],
                    "type": "arXiv",
                    "identifier": b["eprint"],
                    "title": b.get("title", ""),
                })
            elif b.get("pmid"):
                citations.append({
                    "source": b["source"],
                    "type": "PMID",
                    "identifier": b["pmid"],
                    "title": b.get("title", ""),
                })
            elif b.get("isbn"):
                citations.append({
                    "source": b["source"],
                    "type": "ISBN",
                    "identifier": b["isbn"],
                    "title": b.get("title", ""),
                })
            elif b.get("url"):
                citations.append({
                    "source": b["source"],
                    "type": "URL",
                    "identifier": b["url"],
                    "title": b.get("title", ""),
                })

    else:
        # Markdown (.md), LaTeX (.tex), Org (.org), Plain Text (.txt)
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

        if not ident:
            continue

        if c_type == "DOI":
            res = verifier.verify_doi(ident, expected_title=expected_title)
        elif c_type == "arXiv":
            res = verifier.verify_arxiv(ident, expected_title=expected_title)
        elif c_type == "PMID":
            res = verifier.verify_pmid(ident, expected_title=expected_title)
        elif c_type == "ISBN":
            res = verifier.verify_isbn(ident, expected_title=expected_title)
        elif c_type == "URL":
            res = verifier.verify_url(ident)
        else:
            res = {
                "type": c_type,
                "identifier": ident,
                "status": "LOOKUP_ERROR",
                "details": f"Unsupported citation type '{c_type}'",
            }

        res["source"] = item.get("source", "Unknown")
        if expected_title:
            res["expected_title"] = expected_title
        results.append(res)
    return results


def format_text_report(results: List[Dict[str, Any]], target_file: Path) -> str:
    """Format results into a clean ASCII terminal report safe for Windows cp1252."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"CITATION VERIFICATION REPORT: {target_file.name}")
    lines.append("=" * 80)

    pass_count = sum(1 for r in results if r["status"] == "VERIFIED")
    mismatch_count = sum(1 for r in results if r["status"] == "METADATA_MISMATCH")
    fail_count = sum(1 for r in results if r["status"] == "NOT_FOUND")
    err_count = sum(1 for r in results if r["status"] == "LOOKUP_ERROR")

    for idx, r in enumerate(results, 1):
        status = r["status"]
        if status == "VERIFIED":
            tag = "[PASS]"
        elif status == "METADATA_MISMATCH":
            tag = "[WARN]"
        elif status == "NOT_FOUND":
            tag = "[FAIL]"
        else:
            tag = "[ERR ]"

        lines.append(f"{idx:2d}. {tag} {r.get('type', 'ID')}: {r.get('identifier', '')}")
        lines.append(f"    Source: {r.get('source', 'Unknown')}")
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
    lines.append(f"  Total Checked      : {len(results)}")
    lines.append(f"  Verified [PASS]    : {pass_count}")
    lines.append(f"  Mismatched [WARN]  : {mismatch_count}")
    lines.append(f"  Hallucinated [FAIL]: {fail_count}")
    lines.append(f"  Lookup Errors      : {err_count}")
    lines.append("=" * 80)

    if fail_count > 0:
        lines.append("CRITICAL: Hallucinated or invalid citations detected! Review [FAIL] entries.")
    elif mismatch_count > 0:
        lines.append("WARNING: Real identifiers detected with mismatched paper titles! Review [WARN] entries.")
    else:
        lines.append("SUCCESS: All citations verified against authoritative registries.")
    lines.append("=" * 80)
    return "\n".join(lines)


def format_markdown_report(results: List[Dict[str, Any]], target_file: Path) -> str:
    """Format verification results as clean Markdown."""
    lines = []
    lines.append(f"# Citation Verification Report: `{target_file.name}`\n")

    pass_count = sum(1 for r in results if r["status"] == "VERIFIED")
    mismatch_count = sum(1 for r in results if r["status"] == "METADATA_MISMATCH")
    fail_count = sum(1 for r in results if r["status"] == "NOT_FOUND")
    err_count = sum(1 for r in results if r["status"] == "LOOKUP_ERROR")

    lines.append("| Metric | Count |")
    lines.append("| :--- | :--- |")
    lines.append(f"| Total Identifiers Checked | {len(results)} |")
    lines.append(f"| **Verified (PASS)** | **{pass_count}** |")
    lines.append(f"| **Mismatched Metadata (WARN)** | **{mismatch_count}** |")
    lines.append(f"| **Hallucinated / Missing (FAIL)** | **{fail_count}** |")
    lines.append(f"| Lookup Errors | {err_count} |\n")

    lines.append("## Detailed Reference Audit\n")
    lines.append("| # | Status | Type | Identifier | Title / Metadata | Notes |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

    for idx, r in enumerate(results, 1):
        status = r["status"]
        if status == "VERIFIED":
            badge = "**PASS**"
        elif status == "METADATA_MISMATCH":
            badge = "**WARN**"
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

        title_info = r.get("title") or r.get("expected_title") or "-"
        notes = r.get("details", "")
        if r.get("expected_title") and r.get("title") and r.get("title") != r.get("expected_title"):
            notes += f"<br>Doc: _{r['expected_title']}_"

        # sanitize pipe characters for markdown table
        title_info = title_info.replace("|", "/")
        notes = notes.replace("|", "/")

        lines.append(f"| {idx} | {badge} | {c_type} | {ident_link} | {title_info} | {notes} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Verify citations and detect hallucinated references in .docx, .bib, .md, .tex, and text files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_path", help="Path to manuscript or bibliography file (.docx, .bib, .md, .tex, .txt)")
    parser.add_argument("-o", "--output", help="Path to write verification report (.md, .json, or .txt)")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text", help="Output format (default: text)")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Contact email for CrossRef polite API pool")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP request timeout in seconds (default: 10)")
    parser.add_argument("--no-cache", action="store_true", help="Bypass local cache and query live APIs")
    parser.add_argument("--cache-file", help="Custom cache file location (default: .citation_cache.json)")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any citation is missing or mismatched")

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

    if args.format == "json":
        report = json.dumps({
            "target": str(input_path),
            "total": len(results),
            "results": results,
        }, indent=2)
    elif args.format == "markdown":
        report = format_markdown_report(results, input_path)
    else:
        report = format_text_report(results, input_path)

    if args.output:
        out_path = Path(args.output).resolve()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Verification report saved to: {out_path}")
    else:
        print(report)

    # Determine exit code
    has_hallucinations = any(r["status"] == "NOT_FOUND" for r in results)
    has_mismatches = any(r["status"] == "METADATA_MISMATCH" for r in results)

    if has_hallucinations or (args.strict and has_mismatches):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
