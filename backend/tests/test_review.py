"""监测数据审核工作流测试."""
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Exceedance, Measurement, MeasurementReview


def _enter(client, station, entry_payload, **overrides):
    return client.post("/api/measurements/entries", json=entry_payload(station.id, **overrides))


def _pending_ids():
    return [row.id for row in Measurement.query.filter_by(review_status="pending").all()]


def test_submitted_data_enters_pending_review(client, station, entry_payload):
    response = _enter(client, station, entry_payload)
    assert response.status_code == 201
    record = Measurement.query.filter_by(pollutant="SO2").one()
    assert record.review_status == "pending"
    assert record.submitted_at is not None

    queue = client.get("/api/review").get_json()
    assert queue["total"] == 3
    assert queue["items"][0]["review_status_label"] == "待审核"
    assert queue["summary"]["pending"] == 3

    # 提交动作写入审核记录
    logs = MeasurementReview.query.filter_by(action="submit").all()
    assert len(logs) == 3
    assert {log.actor for log in logs} == {"测试员"}


def test_pending_data_is_excluded_from_statistics(client, station, entry_payload):
    _enter(client, station, entry_payload)

    queried = client.get("/api/query/measurements").get_json()
    assert queried["total"] == 0
    assert queried["applied_filters"]["review_statuses"] == ["approved"]

    stats = client.get("/api/query/statistics?group_by=pollutant&metric=count").get_json()
    assert stats["items"] == []

    overview = client.get("/api/meta/overview").get_json()
    assert overview["measurements"]["total"] == 0
    assert overview["review"]["pending"] == 3

    # 录入管理列表仍能看到全部状态, 便于录入人跟踪
    listed = client.get("/api/measurements").get_json()
    assert listed["total"] == 3
    pending_only = client.get("/api/measurements?review_status=pending").get_json()
    assert pending_only["total"] == 3
    approved_only = client.get("/api/measurements?review_status=approved").get_json()
    assert approved_only["total"] == 0


def test_approve_includes_data_and_creates_exceedance(client, station, entry_payload):
    _enter(client, station, entry_payload)
    ids = _pending_ids()
    response = client.post(
        "/api/review/approve", json={"ids": ids, "reviewer": "周审核", "comment": "复核无误"}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["approved"] == 3
    assert body["skipped"] == []

    assert Measurement.query.filter_by(review_status="approved").count() == 3
    exceedance = Exceedance.query.one()
    assert exceedance.pollutant == "SO2"
    assert exceedance.status == "pending"

    queried = client.get("/api/query/measurements").get_json()
    assert queried["total"] == 3
    assert queried["summary"]["exceeded_count"] == 1

    log = MeasurementReview.query.filter_by(action="approve").first()
    assert log.actor == "周审核"
    assert log.reason == "复核无误"

    # 重复审核同一条会被跳过, 不会重复生成超标记录
    again = client.post("/api/review/approve", json={"ids": ids}).get_json()
    assert again["approved"] == 0
    assert again["skipped"] == ids
    assert Exceedance.query.count() == 1


def test_reject_requires_reason(client, station, entry_payload):
    _enter(client, station, entry_payload)
    ids = _pending_ids()

    missing = client.post("/api/review/reject", json={"ids": ids})
    assert missing.status_code == 422

    blank = client.post("/api/review/reject", json={"ids": ids, "reason": "  "})
    assert blank.status_code == 422
    assert blank.get_json()["error"]["fields"]["reason"] == "required"


def test_reject_returns_record_to_recorder(client, station, entry_payload):
    _enter(client, station, entry_payload)
    target = Measurement.query.filter_by(pollutant="SO2").one()

    response = client.post(
        "/api/review/reject",
        json={"ids": [target.id], "reason": "数值与原始记录不符, 请核对", "reviewer": "吴质控"},
    )
    assert response.status_code == 200
    assert response.get_json()["rejected"] == 1

    db.session.refresh(target)
    assert target.review_status == "rejected"
    assert target.review_reason == "数值与原始记录不符, 请核对"
    assert target.reviewed_by == "吴质控"

    summary = client.get("/api/review/summary").get_json()
    assert summary["pending"] == 2
    assert summary["rejected"] == 1

    rejected = client.get("/api/review?review_status=rejected").get_json()
    assert rejected["total"] == 1
    assert rejected["items"][0]["review_reason"] == "数值与原始记录不符, 请核对"

    # 被驳回的数据不进入统计口径
    assert client.get("/api/query/measurements").get_json()["total"] == 0


def test_rejected_record_can_be_fixed_and_resubmitted(client, station, entry_payload):
    _enter(client, station, entry_payload)
    target = Measurement.query.filter_by(pollutant="SO2").one()
    client.post(
        "/api/review/reject", json={"ids": [target.id], "reason": "小数点错位, 请修正"}
    )

    response = client.patch(
        "/api/measurements/%d" % target.id, json={"value": 120.0, "remark": "已按原始记录修正"}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["value"] == 120.0
    assert body["review_status"] == "pending"
    assert body["review_reason"] is None
    assert body["is_exceeded"] is False

    # 修改重报留痕, 并可重新审核通过
    assert MeasurementReview.query.filter_by(action="resubmit").count() == 1
    approve = client.post("/api/review/approve", json={"ids": [target.id], "reviewer": "吴质控"})
    assert approve.get_json()["approved"] == 1
    assert Exceedance.query.count() == 0  # 修正后不再超标


def test_update_measurement_validates_value(client, station, entry_payload):
    _enter(client, station, entry_payload)
    target = Measurement.query.first()
    response = client.patch("/api/measurements/%d" % target.id, json={"value": "abc"})
    assert response.status_code == 422
    assert "value" in response.get_json()["error"]["fields"]


def test_summary_flags_overdue_pending_records(client, station, entry_payload, app):
    _enter(client, station, entry_payload)
    stale = Measurement.query.filter_by(pollutant="SO2").one()
    stale.submitted_at = datetime.now() - timedelta(hours=48)
    db.session.commit()

    summary = client.get("/api/review/summary").get_json()
    assert summary["pending"] == 3
    assert summary["overdue"] == 1
    assert summary["overdue_hours"] == app.config["REVIEW_OVERDUE_HOURS"]
    assert summary["oldest_pending_submitted_at"] is not None

    overdue = client.get("/api/review?overdue=true").get_json()
    assert overdue["total"] == 1
    assert overdue["items"][0]["pollutant"] == "SO2"


def test_review_logs_are_queryable(client, station, entry_payload):
    _enter(client, station, entry_payload)
    ids = _pending_ids()
    client.post("/api/review/approve", json={"ids": ids[:1], "reviewer": "周审核"})
    client.post("/api/review/reject", json={"ids": ids[1:], "reason": "时段存疑"})

    logs = client.get("/api/review/logs").get_json()
    assert logs["total"] == 6  # 3 提交 + 1 通过 + 2 驳回
    first = logs["items"][0]
    assert first["action"] == "reject"
    assert first["action_label"] == "审核驳回"
    assert first["reason"] == "时段存疑"
    assert first["measurement"]["station_code"] == "TEST-001"

    only_approve = client.get("/api/review/logs?action=approve").get_json()
    assert only_approve["total"] == 1
    assert only_approve["items"][0]["actor"] == "周审核"


def test_review_list_filters_and_missing_ids(client, station, entry_payload):
    _enter(client, station, entry_payload)
    by_station = client.get("/api/review?station_id=%d" % station.id).get_json()
    assert by_station["total"] == 3
    by_recorder = client.get("/api/review?recorder=不存在的人").get_json()
    assert by_recorder["total"] == 0
    bad_status = client.get("/api/review?review_status=unknown")
    assert bad_status.status_code == 422

    result = client.post("/api/review/approve", json={"ids": [9999]}).get_json()
    assert result["missing"] == [9999]
    assert result["approved"] == 0


def test_delete_measurement_cascades_review_logs(client, station, entry_payload, approve_all):
    _enter(client, station, entry_payload)
    approve_all()
    target = Measurement.query.filter_by(pollutant="SO2").one()
    assert MeasurementReview.query.filter_by(measurement_id=target.id).count() == 2

    response = client.delete("/api/measurements/%d" % target.id)
    assert response.status_code == 200
    assert MeasurementReview.query.filter_by(measurement_id=target.id).count() == 0
    assert Exceedance.query.count() == 0
