def test_health_checks_the_database(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}