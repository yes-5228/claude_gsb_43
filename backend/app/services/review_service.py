"""监测数据审核工作流: 待审核队列 / 审核动作 / 审核记录 / 超时提醒.

口径约定: 只有 review_status == "approved" 的监测数据才纳入统计与超标判定;
驳回必须填写原因, 数据回到录入人处修改后重新提交会再次进入待审核。
"""
from datetime import datetime, time, timedelta

from flask import current_app
from sqlalchemy import func, or_

from ..domain.constants import REVIEW_ACTION_LABELS, REVIEW_STATUS_LABELS
from ..domain.exceedance_rules import grade_ratio
from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Exceedance, Measurement, ReviewRecord, Station
from ..models.base import iso
from ..utils.validation import parse_date

REVIEW_ACTIONS = ("approve", "reject")


def _timeout_hours():
    return int(current_app.config.get("REVIEW_TIMEOUT_HOURS", 24))


def _overdue_cutoff(now=None):
    return (now or datetime.now()) - timedelta(hours=_timeout_hours())


def _split(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _int_list(value, field="ids"):
    values = []
    for item in _split(value) if isinstance(value, str) else (value or []):
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            raise ValidationError(
                "%s 必须为整数" % field, fields={field: "invalid_integer"}
            )
    return values


def _date_arg(args, name, end_of_day=False):
    raw = args.get(name)
    if raw in (None, ""):
        return None
    parsed = parse_date(raw, name)
    return datetime.combine(parsed, time.max if end_of_day else time.min)


def log_action(measurement, action, reviewer=None, reason=None, from_status=None):
    """Append one audit row for a review-workflow transition (caller commits)."""
    if action not in REVIEW_ACTION_LABELS:
        raise ValueError("未知审核动作: %s" % action)
    record = ReviewRecord(
        measurement_id=measurement.id,
        action=action,
        from_status=from_status,
        to_status=measurement.review_status,
        reviewer=(reviewer or "").strip() or None,
        reason=(reason or "").strip() or None,
    )
    db.session.add(record)
    return record


def get_measurement(measurement_id):
    measurement = db.session.get(Measurement, measurement_id)
    if measurement is None:
        raise NotFoundError("监测数据不存在: id=%s" % measurement_id)
    return measurement


def _create_exceedance(measurement):
    """审核通过后将超标数据纳入超标判定口径 (生成待标注超标记录)."""
    if not measurement.is_exceeded or measurement.exceedance is not None:
        return None
    exceedance = Exceedance(
        station_id=measurement.station_id,
        pollutant=measurement.pollutant,
        period=measurement.period,
        measured_at=measurement.measured_at,
        value=measurement.value,
        limit_value=measurement.limit_value,
        exceed_ratio=measurement.exceed_ratio,
        level=grade_ratio(measurement.exceed_ratio),
        status="pending",
    )
    measurement.exceedance = exceedance
    db.session.add(exceedance)
    return exceedance


def _apply_review(measurement, action, reviewer=None, reason=None):
    """Transition one pending measurement; returns the created Exceedance if any."""
    if measurement.review_status != "pending":
        raise ConflictError(
            "该记录已完成审核 (当前状态: %s), 请刷新后重试"
            % REVIEW_STATUS_LABELS.get(measurement.review_status, measurement.review_status)
        )
    reason = (reason or "").strip()
    if action == "reject" and not reason:
        raise ValidationError("驳回时必须填写驳回原因", fields={"reason": "required"})

    from_status = measurement.review_status
    measurement.review_status = "approved" if action == "approve" else "rejected"
    measurement.reviewed_at = datetime.now()
    measurement.reviewer = (reviewer or "").strip() or "未署名"
    measurement.review_reason = reason or None

    exceedance = _create_exceedance(measurement) if action == "approve" else None
    log_action(measurement, action, reviewer=measurement.reviewer,
               reason=reason or None, from_status=from_status)
    return exceedance


def review(measurement, action, reviewer=None, reason=None):
    """审核单条记录: approve 通过 / reject 驳回 (驳回必填原因)."""
    if action not in REVIEW_ACTIONS:
        raise ValidationError(
            "审核动作取值不合法, 可选: %s" % ", ".join(REVIEW_ACTIONS),
            fields={"action": "unknown"},
        )
    _apply_review(measurement, action, reviewer=reviewer, reason=reason)
    db.session.commit()
    return measurement


def review_batch(ids, action, reviewer=None, reason=None):
    """批量审核: 跳过已完成审核的记录并回报, 其余一次性提交."""
    if action not in REVIEW_ACTIONS:
        raise ValidationError(
            "审核动作取值不合法, 可选: %s" % ", ".join(REVIEW_ACTIONS),
            fields={"action": "unknown"},
        )
    if action == "reject" and not (reason or "").strip():
        raise ValidationError("批量驳回时必须填写驳回原因", fields={"reason": "required"})

    ids = list(dict.fromkeys(_int_list(ids)))
    if not ids:
        raise ValidationError("请至少选择一条待审核数据", fields={"ids": "empty"})

    records = Measurement.query.filter(Measurement.id.in_(ids)).all()
    found = {record.id for record in records}
    missing = [item for item in ids if item not in found]

    updated, skipped, exceedances = [], [], 0
    for record in records:
        if record.review_status != "pending":
            skipped.append(record.id)
            continue
        exceedance = _apply_review(record, action, reviewer=reviewer, reason=reason)
        if exceedance is not None:
            exceedances += 1
        updated.append(record.id)

    db.session.commit()
    return {
        "action": action,
        "action_label": REVIEW_ACTION_LABELS[action],
        "updated": len(updated),
        "updated_ids": updated,
        "skipped": skipped,
        "missing": missing,
        "exceedance_count": exceedances,
    }


def pending_query(args):
    """待审核队列: 按提交时间正序, 先提交的先审."""
    query = (
        db.session.query(Measurement)
        .join(Station, Measurement.station_id == Station.id)
        .filter(Measurement.review_status == "pending")
    )
    station_ids = _int_list(args.get("station_id"), field="station_id")
    if station_ids:
        query = query.filter(Measurement.station_id.in_(station_ids))
    pollutants = _split(args.get("pollutant"))
    if pollutants:
        query = query.filter(Measurement.pollutant.in_([item.upper() for item in pollutants]))
    recorder = (args.get("recorder") or "").strip()
    if recorder:
        query = query.filter(Measurement.recorder.like("%" + recorder + "%"))
    keyword = (args.get("keyword") or "").strip()
    if keyword:
        like = "%" + keyword + "%"
        query = query.filter(or_(Station.name.like(like), Station.code.like(like)))
    if str(args.get("overdue", "")).strip().lower() in {"1", "true", "yes", "on"}:
        query = query.filter(Measurement.created_at < _overdue_cutoff())
    return query.order_by(Measurement.created_at.asc(), Measurement.id.asc())


def pending_item(measurement, now=None):
    """待审核队列行: 附带等待时长与超时标记."""
    now = now or datetime.now()
    payload = measurement.to_dict(include_station=True)
    waiting_hours = max((now - measurement.created_at).total_seconds() / 3600.0, 0.0)
    payload["waiting_hours"] = round(waiting_hours, 1)
    payload["is_overdue"] = measurement.created_at < _overdue_cutoff(now)
    return payload


def pending_summary():
    """审核工作台顶部统计: 待审核数量 / 超时未处理 / 处理情况."""
    now = datetime.now()
    cutoff = _overdue_cutoff(now)
    today_start = datetime.combine(now.date(), time.min)

    status_rows = dict(
        db.session.query(Measurement.review_status, func.count())
        .group_by(Measurement.review_status)
        .all()
    )
    pending = int(status_rows.get("pending", 0))
    overdue = 0
    oldest_pending_at = None
    if pending:
        overdue = int(
            db.session.query(func.count(Measurement.id))
            .filter(Measurement.review_status == "pending", Measurement.created_at < cutoff)
            .scalar()
            or 0
        )
        oldest_pending_at = (
            db.session.query(func.min(Measurement.created_at))
            .filter(Measurement.review_status == "pending")
            .scalar()
        )

    reviewed_today = int(
        db.session.query(func.count(ReviewRecord.id))
        .filter(ReviewRecord.action.in_(REVIEW_ACTIONS), ReviewRecord.created_at >= today_start)
        .scalar()
        or 0
    )

    return {
        "pending": pending,
        "overdue": overdue,
        "threshold_hours": _timeout_hours(),
        "approved": int(status_rows.get("approved", 0)),
        "rejected": int(status_rows.get("rejected", 0)),
        "reviewed_today": reviewed_today,
        "oldest_pending_at": iso(oldest_pending_at),
        "generated_at": iso(now),
    }


def records_query(args):
    """审核记录列表: 支持动作 / 审核人 / 站点 / 时间过滤."""
    query = (
        db.session.query(ReviewRecord)
        .join(Measurement, ReviewRecord.measurement_id == Measurement.id)
        .join(Station, Measurement.station_id == Station.id)
    )
    actions = _split(args.get("action"))
    if actions:
        query = query.filter(ReviewRecord.action.in_(actions))
    reviewer = (args.get("reviewer") or "").strip()
    if reviewer:
        query = query.filter(ReviewRecord.reviewer.like("%" + reviewer + "%"))
    station_ids = _int_list(args.get("station_id"), field="station_id")
    if station_ids:
        query = query.filter(Measurement.station_id.in_(station_ids))
    keyword = (args.get("keyword") or "").strip()
    if keyword:
        like = "%" + keyword + "%"
        query = query.filter(
            or_(
                Station.name.like(like),
                Station.code.like(like),
                Measurement.pollutant.like(like),
            )
        )
    date_from = _date_arg(args, "date_from")
    if date_from:
        query = query.filter(ReviewRecord.created_at >= date_from)
    date_to = _date_arg(args, "date_to", end_of_day=True)
    if date_to:
        query = query.filter(ReviewRecord.created_at <= date_to)
    measurement_id = args.get("measurement_id")
    if measurement_id not in (None, ""):
        try:
            query = query.filter(ReviewRecord.measurement_id == int(measurement_id))
        except (TypeError, ValueError):
            raise ValidationError(
                "measurement_id 必须为整数", fields={"measurement_id": "invalid_integer"}
            )
    return query.order_by(ReviewRecord.created_at.desc(), ReviewRecord.id.desc())
