def test_create_recommendation_success_envelope(client, valid_request):
    r = client.post("/v1/recommendations", json=valid_request)
    body = r.json()
    assert r.status_code == 200
    assert body["ok"] is True
    assert body["data"]["headline"]["mode"] in {"walk", "bike", "drive", "train"}
    assert 0 <= body["data"]["headline"]["p_on_time"] <= 1
    assert body["meta"]["degraded"] is False
    assert r.headers["X-Request-ID"] == body["meta"]["request_id"]
