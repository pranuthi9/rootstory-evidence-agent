from unittest.mock import Mock, patch

import httpx

from evidence_agent.agents import _public_https_url, _verify_candidate_sources


def test_private_and_non_https_sources_are_rejected():
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 443))]):
        assert _public_https_url("https://example.test/person") is False
    assert _public_https_url("http://example.org/person") is False


def test_candidate_source_must_resolve_and_name_the_subject():
    response = Mock()
    response.text = "An archive biography of Ada Lovelace and her work."
    response.headers = {"content-type": "text/html"}
    response.url = httpx.URL("https://archive.example/ada")
    response.raise_for_status.return_value = None
    with (
        patch("evidence_agent.agents._public_https_url", return_value=True),
        patch("httpx.Client.get", return_value=response),
    ):
        verified = _verify_candidate_sources(
            [{"title": "Ada archive", "url": "https://archive.example/ada"}], "Ada Lovelace"
        )
    assert len(verified) == 1
    assert verified[0].title == "Ada archive"
