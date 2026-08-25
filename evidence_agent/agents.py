from __future__ import annotations

import ipaddress
import json
import os
import socket
from typing import Protocol
from urllib.parse import urlparse

import httpx
from google import genai
from google.genai import types

from .models import Claim, Finding, Source


def _public_https_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443)}
        return bool(addresses) and all(
            ipaddress.ip_address(address).is_global for address in addresses
        )
    except (OSError, ValueError):
        return False


def _verify_candidate_sources(raw_sources: list[dict], person_name: str) -> list[Source]:
    """Fetch model-proposed pages and retain only public pages that identify the subject."""
    verified: list[Source] = []
    name_tokens = [token.casefold() for token in person_name.split() if len(token) > 2]
    with httpx.Client(follow_redirects=True, timeout=10, max_redirects=3) as client:
        for item in raw_sources[:5]:
            url = str(item.get("url", ""))
            if not _public_https_url(url):
                continue
            try:
                response = client.get(url, headers={"User-Agent": "RootstoryEvidenceAgent/0.1"})
                response.raise_for_status()
                if not _public_https_url(str(response.url)):
                    continue
                content_type = response.headers.get("content-type", "")
                if not any(kind in content_type for kind in ("text/", "application/xhtml+xml")):
                    continue
                content = response.text[:1_000_000].casefold()
                if name_tokens and not all(token in content for token in name_tokens):
                    continue
                verified.append(
                    Source(
                        title=str(item.get("title") or response.url.host),
                        url=str(response.url),
                        publisher=item.get("publisher") or response.url.host,
                    )
                )
            except (httpx.HTTPError, ValueError):
                continue
    return verified


class EvidenceResearcher(Protocol):
    def research(self, person: dict, finding: Finding) -> list[Claim]: ...


class GeminiEvidenceResearcher:
    """Grounded specialist that returns claims, never direct tree mutations."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.client = genai.Client(vertexai=True)

    def research(self, person: dict, finding: Finding) -> list[Claim]:
        prompt = f"""
You are the evidence-research specialist in an autonomous genealogy audit.
Research only this objective and return source-backed facts. Do not infer family
relationships from names alone and do not invent missing values.

Person: {json.dumps(person, default=str)}
Finding: {finding.model_dump_json()}

Return JSON with a `claims` array. Each claim must contain:
- subject_id: exactly {finding.subject_id!r}
- field: the exact field being supported or discovered
- value: the proposed value
- confidence: 0 to 1
- rationale: a concise comparison of the evidence
- sources: canonical pages with title, https URL, and publisher

Use zero claims when reliable evidence cannot be found.
"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_mime_type="application/json",
            ),
        )
        payload = json.loads(response.text or '{"claims": []}')
        grounded_sources: list[Source] = []
        candidate = response.candidates[0] if response.candidates else None
        metadata = candidate.grounding_metadata if candidate else None
        for chunk in metadata.grounding_chunks or [] if metadata else []:
            if chunk.web and chunk.web.uri:
                grounded_sources.append(
                    Source(
                        title=chunk.web.title or "Google Search result",
                        url=chunk.web.uri,
                        publisher=chunk.web.domain,
                    )
                )
        claims: list[Claim] = []
        for raw in payload.get("claims", []):
            raw["subject_id"] = finding.subject_id
            # Only evidence returned by the grounding API is trusted. The model cannot
            # promote an arbitrary URL from its generated JSON into a verified source.
            raw["sources"] = grounded_sources or _verify_candidate_sources(
                raw.get("sources", []), str(person.get("name", ""))
            )
            claims.append(Claim.model_validate(raw))
        return claims


class NullEvidenceResearcher:
    """Safe local default: completes tasks without fabricating evidence."""

    def research(self, person: dict, finding: Finding) -> list[Claim]:
        return []
