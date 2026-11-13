from fastapi.testclient import TestClient

from geofuel.api import app


def test_gps_update_and_readback():
    client = TestClient(app)
    response = client.post(
        "/api/gps/update",
        json={"vehicle_id": "MT-TEST", "lat": -6.9, "lon": 107.6},
    )
    assert response.status_code == 200
    assert response.json()["position"]["source_status"] == "DEVICE_REPORTED"
    positions = client.get("/api/gps/positions")
    assert positions.status_code == 200
    assert any(p["vehicle_id"] == "MT-TEST" for p in positions.json()["positions"])
    assert client.delete("/api/gps/positions/MT-TEST").json()["removed"] is True
