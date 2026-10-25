import requests

from desktop import updates


def test_rate_limited_api_uses_public_feeds(monkeypatch):
    class Response:
        def __init__(self, url):
            self.url = url
            self.content = ('''<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="https://github.com/Chihiro521/videodl/releases/tag/desktop-v0.2.0"/></entry></feed>''' if "releases.atom" in url else '''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>tag:github.com,2008:Grit::Commit/123456789abc</id></entry></feed>''').encode()
        def raise_for_status(self):
            if "api.github.com" in self.url:
                raise requests.HTTPError("rate limited")
    class Session:
        headers = {}
        def get(self, url, **kwargs):
            return Response(url)
    monkeypatch.setattr(updates.requests, "Session", Session)
    result = updates.check_updates()
    assert result["available"]
    assert result["latest"] == "desktop-v0.2.0"
    assert result["upstream_revision"] == "123456789abc"
