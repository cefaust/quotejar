"""The root signpost.

Small surface, but it is the first thing anyone handed the deployment URL
sees, so it is worth pinning: that it exists at all, that it needs no
credentials, and that it does not leak anything.
"""


def test_root_returns_service_info(anon_client):
    r = anon_client.get("/")

    assert r.status_code == 200
    assert r.json()["name"] == "QuoteJar API"


def test_root_points_at_the_docs(anon_client):
    """The whole reason this route exists: telling a visitor where to go."""
    assert anon_client.get("/").json()["docs"] == "/docs"


def test_root_version_matches_the_openapi_document(anon_client):
    """Guards the drift this route was written to avoid.

    The handler reads app.version rather than repeating the literal, so a
    version bump cannot leave the root advertising a stale number while
    /openapi.json reports the real one.
    """
    root_version = anon_client.get("/").json()["version"]
    openapi_version = anon_client.get("/openapi.json").json()["info"]["version"]

    assert root_version == openapi_version


def test_root_needs_no_authentication(anon_client):
    """It is a signpost. Requiring a token to be told where the docs are would
    defeat the point."""
    assert anon_client.get("/").status_code == 200


def test_root_leaks_nothing_sensitive(anon_client):
    """Service metadata only.

    An unauthenticated root endpoint is the most-scanned path on any host, so
    it must never grow into a debug page. Anything naming the database, the
    environment, or internal hosts belongs behind auth or nowhere.
    """
    body = anon_client.get("/").text.lower()

    for leak in ("password", "secret", "postgres", "rds.amazonaws", "token"):
        assert leak not in body
