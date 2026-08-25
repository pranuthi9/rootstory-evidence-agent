from __future__ import annotations

import json
import os
from typing import Protocol

from google import genai
from google.genai import types

from .models import Claim, Finding, Source


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
            raw["sources"] = grounded_sources
            claims.append(Claim.model_validate(raw))
        return claims


class NullEvidenceResearcher:
    """Safe local default: completes tasks without fabricating evidence."""

    def research(self, person: dict, finding: Finding) -> list[Claim]:
        return []
