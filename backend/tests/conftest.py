import pytest

from app import create_app
from app.extensions import db
from app.models import Measurement, Station
from app.services import station_service


@pytest.fixture
def app():
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def station(app):
    return station_service.create_station(
        {
            "code": "TEST-001",
            "name": "测试监测点",
            "area": "测试区",
            "address": "测试路 1 号",
            "station_type": "ambient",
            "status": "active",
            "longitude": 114.05,
            "latitude": 22.54,
            "installed_at": None,
            "remark": None,
        }
    )


@pytest.fixture
def second_station(app):
    return station_service.create_station(
        {
            "code": "TEST-002",
            "name": "工业园监测点",
            "area": "工业园区",
            "address": None,
            "station_type": "industrial",
            "status": "active",
            "longitude": None,
            "latitude": None,
            "installed_at": None,
            "remark": None,
        }
    )


@pytest.fixture
def entry_payload():
    def _make(station_id, measured_at="2026-09-01 10:00", entries=None, **overrides):
        payload = {
            "station_id": station_id,
            "measured_at": measured_at,
            "period": "hourly",
            "data_source": "manual",
            "recorder": "测试员",
            "entries": entries
            if entries is not None
            else [
                {"pollutant": "PM25", "value": 60.0},
                {"pollutant": "SO2", "value": 900.0},
                {"pollutant": "CO", "value": 1.2},
            ],
        }
        payload.update(overrides)
        return payload

    return _make


@pytest.fixture
def station_model():
    return Station


@pytest.fixture
def approve_all(client):
    """Approve every pending measurement through the review API (统计口径前置步骤)."""

    def _approve(reviewer="审核员"):
        ids = [row.id for row in Measurement.query.filter_by(review_status="pending").all()]
        if not ids:
            return {"updated": 0, "updated_ids": []}
        response = client.post(
            "/api/reviews/batch",
            json={"ids": ids, "action": "approve", "reviewer": reviewer},
        )
        assert response.status_code == 200
        return response.get_json()

    return _approve
