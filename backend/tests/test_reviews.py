"""监测数据审核工作流测试: 待审核 / 通过 / 驳回 / 超时提醒 / 审核记录."""
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Exceedance, Measurement, ReviewRecord


def _enter(client, station, entry_payload, entries=None, **overrides):
    return client.post(
        "/api/measurements/entries",
        json=entry_payload(station.id, entries=entries, **overrides),
    )


def test_submitted_data_enters_pending_queue(client, station, entry_payload):
    _enter(client, station, entry_payload)

    queue = client.get("/api/reviews/pending").get_json()
    assert queue["total"] == 3
    first = queue["items"][0]
    assert first["review_status"] == "pending"
    assert first["review_status_label"] == "待审核"
    assert first["is_overdue"] is False
    assert first["waiting_hours"] >= 0

    summary = client.get("/api/reviews/summary").get_json()
    assert summary["pending"] == 3
    assert summary["overdue"] == 0
    assert summary["approved"] == 0
    assert summary["threshold_hours"] == 24


def test_approve_bring_data_into_statistics_and_exceedance_scope(
    client, station, entry_payload
):
    _enter(client, station, entry_payload)
    measurement = Measurement.query.filter_by(pollutant="SO2").one()

    response = client.post(
        "/api/reviews/%d" % measurement.id,
        json={"action": "approve", "reviewer": "刘洋"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["review_status"] == "approved"
    assert body["reviewer"] == "刘洋"
    assert body["reviewed_at"] is not None

    # 审核通过: 超标数据生成待标注超标记录, 统计口径纳入该条数据
    exceedance = Exceedance.query.one()
    assert exceedance.measurement_id == measurement.id
    assert exceedance.status == "pending"
    assert exceedance.level == "moderate"  # 900 / 500 = 1.8 倍
    summary = client.get("/api/measurements/summary").get_json()
    assert summary["total"] == 1
    assert summary["exceeded_count"] == 1

    record = ReviewRecord.query.filter_by(action="approve").one()
    assert record.from_status == "pending"
    assert record.to_status == "approved"
    assert record.reviewer == "刘洋"


def test_reject_requires_reason(client, station, entry_payload):
    _enter(client, station, entry_payload)
    measurement = Measurement.query.filter_by(pollutant="PM25").one()

    response = client.post(
        "/api/reviews/%d" % measurement.id, json={"action": "reject", "reviewer": "刘洋"}
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["fields"]["reason"] == "required"
    assert measurement.review_status == "pending"


def test_reject_sends_data_back_to_recorder_with_reason(client, station, entry_payload):
    _enter(client, station, entry_payload)
    measurement = Measurement.query.filter_by(pollutant="PM25").one()

    response = client.post(
        "/api/reviews/%d" % measurement.id,
        json={"action": "reject", "reviewer": "刘洋", "reason": "数值与原始记录不符, 请核对后重录"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["review_status"] == "rejected"
    assert body["review_status_label"] == "已驳回"
    assert body["review_reason"] == "数值与原始记录不符, 请核对后重录"

    # 驳回数据不进入统计口径, 也不生成超标记录
    assert Exceedance.query.count() == 0
    summary = client.get("/api/measurements/summary").get_json()
    assert summary["total"] == 0

    # 录入人修改后重新提交: 数据回到待审核, 驳回信息清空
    again = client.post(
        "/api/measurements/entries",
        json=entry_payload(
            station.id, overwrite=True, entries=[{"pollutant": "PM25", "value": 42.0}]
        ),
    )
    assert again.status_code == 201
    db.session.refresh(measurement)
    assert measurement.review_status == "pending"
    assert measurement.review_reason is None
    assert measurement.reviewer is None
    assert measurement.value == 42.0

    resubmit = ReviewRecord.query.filter_by(action="resubmit").one()
    assert resubmit.from_status == "rejected"
    assert resubmit.reviewer == "测试员"


def test_reviewed_record_cannot_be_reviewed_again(client, station, entry_payload):
    _enter(client, station, entry_payload)
    measurement = Measurement.query.filter_by(pollutant="CO").one()
    payload = {"action": "approve", "reviewer": "刘洋"}
    assert client.post("/api/reviews/%d" % measurement.id, json=payload).status_code == 200

    again = client.post("/api/reviews/%d" % measurement.id, json=payload)
    assert again.status_code == 409
    assert "已完成审核" in again.get_json()["error"]["message"]


def test_batch_review_approves_pending_and_skips_finished(client, station, entry_payload):
    _enter(client, station, entry_payload)
    ids = [row.id for row in Measurement.query.all()]
    client.post("/api/reviews/%d" % ids[0], json={"action": "approve", "reviewer": "刘洋"})

    response = client.post(
        "/api/reviews/batch",
        json={"ids": ids + [9999], "action": "approve", "reviewer": "周慧"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["updated"] == 2
    assert body["skipped"] == [ids[0]]
    assert body["missing"] == [9999]
    assert body["exceedance_count"] == 1  # SO2 预判超标, 审核通过后生成超标记录
    assert Measurement.query.filter_by(review_status="approved").count() == 3


def test_batch_reject_requires_reason(client, station, entry_payload):
    _enter(client, station, entry_payload)
    ids = [row.id for row in Measurement.query.all()]
    response = client.post("/api/reviews/batch", json={"ids": ids, "action": "reject"})
    assert response.status_code == 422
    assert response.get_json()["error"]["fields"]["reason"] == "required"

    ok = client.post(
        "/api/reviews/batch",
        json={"ids": ids, "action": "reject", "reviewer": "刘洋", "reason": "批量复核不通过"},
    )
    assert ok.status_code == 200
    assert ok.get_json()["updated"] == 3
    assert Measurement.query.filter_by(review_status="rejected").count() == 3


def test_overdue_pending_is_flagged_in_summary_and_queue(client, station, entry_payload, app):
    _enter(client, station, entry_payload)
    stale = Measurement.query.filter_by(pollutant="PM25").one()
    stale.created_at = datetime.now() - timedelta(hours=30)
    db.session.commit()

    summary = client.get("/api/reviews/summary").get_json()
    assert summary["pending"] == 3
    assert summary["overdue"] == 1
    assert summary["oldest_pending_at"] is not None

    overdue_only = client.get("/api/reviews/pending?overdue=true").get_json()
    assert overdue_only["total"] == 1
    assert overdue_only["items"][0]["pollutant"] == "PM25"
    assert overdue_only["items"][0]["is_overdue"] is True
    assert overdue_only["items"][0]["waiting_hours"] >= 30


def test_review_records_form_audit_trail(client, station, entry_payload):
    _enter(client, station, entry_payload)
    target = Measurement.query.filter_by(pollutant="SO2").one()
    client.post(
        "/api/reviews/%d" % target.id,
        json={"action": "reject", "reviewer": "刘洋", "reason": "怀疑仪器漂移"},
    )
    client.post(
        "/api/measurements/entries",
        json=entry_payload(station.id, overwrite=True, entries=[{"pollutant": "SO2", "value": 480.0}]),
    )
    client.post("/api/reviews/%d" % target.id, json={"action": "approve", "reviewer": "周慧"})

    records = client.get("/api/reviews/records?measurement_id=%d" % target.id).get_json()
    actions = [item["action"] for item in records["items"]]
    assert actions == ["approve", "resubmit", "reject", "submit"]
    reject = next(item for item in records["items"] if item["action"] == "reject")
    assert reject["reason"] == "怀疑仪器漂移"
    assert reject["reviewer"] == "刘洋"
    assert reject["action_label"] == "驳回"
    assert reject["measurement"]["station_code"] == "TEST-001"
    assert reject["measurement"]["pollutant"] == "SO2"

    by_action = client.get("/api/reviews/records?action=approve").get_json()
    assert by_action["total"] == 1
    by_reviewer = client.get("/api/reviews/records?reviewer=周慧").get_json()
    assert by_reviewer["total"] == 1


def test_review_options_endpoint(client):
    body = client.get("/api/reviews/options").get_json()
    assert {item["value"] for item in body["statuses"]} == {"pending", "approved", "rejected"}
    assert {item["value"] for item in body["actions"]} == {
        "submit",
        "resubmit",
        "approve",
        "reject",
    }
