"""监测数据审核工作流: 待审队列 / 通过与驳回 / 审核记录 / 超时提醒."""
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import func, or_

from ..domain import exceedance_rules
from ..domain.constants import REVIEW_ACTION_LABELS, REVIEW_STATUS_LABELS
from ..errors import NotFoundError, ValidationError
from ..extensions import db
from ..models import Measurement, MeasurementReview, Station
from ..models.base import iso
from ..utils.validation import parse_date
from . import measurement_service

STATUS_CHOICES = tuple(REVIEW_STATUS_LABELS.keys())
ACTION_CHOICES = tuple(REVIEW_ACTION_LABELS.keys())


def _split(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _int_list(args, name):
    values = []
    for item in _split(args.get(name)):
        try:
            values.append(int(item))
        except ValueError:
            raise ValidationError("%s 参数必须为整数" % name, fields={name: "invalid_integer"})
    return values


def _date_arg(args, name, end_of_day=False):
    from datetime import time

    raw = args.get(name)
    if raw in (None, ""):
        return None
    parsed = parse_date(raw, name)
    return datetime.combine(parsed, time.max if end_of_day else time.min)


def overdue_threshold():
    hours = current_app.config["REVIEW_OVERDUE_HOURS"]
    return datetime.now() - timedelta(hours=hours)


def review_query(args):
    """审核工作台列表: 默认展示待审核队列, 支持状态/站点/录入人等过滤."""
    query = db.session.query(Measurement).join(Station, Measurement.station_id == Station.id)

    statuses = _split(args.get("review_status")) or _split(args.get("status"))
    unknown = [item for item in statuses if item not in STATUS_CHOICES]
    if unknown:
        raise ValidationError(
            "未知审核状态: %s" % ", ".join(unknown), fields={"review_status": "unknown"}
        )
    if statuses:
        query = query.filter(Measurement.review_status.in_(statuses))
    else:
        query = query.filter(Measurement.review_status == "pending")

    station_ids = _int_list(args, "station_id")
    if station_ids:
        query = query.filter(Measurement.station_id.in_(station_ids))
    pollutants = [item.upper() for item in _split(args.get("pollutant"))]
    if pollutants:
        query = query.filter(Measurement.pollutant.in_(pollutants))
    recorder = (args.get("recorder") or "").strip()
    if recorder:
        query = query.filter(Measurement.recorder.like("%" + recorder + "%"))
    keyword = (args.get("keyword") or "").strip()
    if keyword:
        like = "%" + keyword + "%"
        query = query.filter(or_(Station.name.like(like), Station.code.like(like)))
    date_from = _date_arg(args, "date_from")
    if date_from:
        query = query.filter(Measurement.measured_at >= date_from)
    date_to = _date_arg(args, "date_to", end_of_day=True)
    if date_to:
        query = query.filter(Measurement.measured_at <= date_to)
    if str(args.get("overdue", "")).strip().lower() in {"1", "true", "yes"}:
        query = query.filter(
            Measurement.review_status == "pending",
            Measurement.submitted_at <= overdue_threshold(),
        )

    # 待审核按提交时间正序 (先提交先审), 其余按审核时间倒序
    if not statuses or statuses == ["pending"]:
        return query.order_by(Measurement.submitted_at.asc(), Measurement.id.asc())
    return query.order_by(Measurement.reviewed_at.desc(), Measurement.id.desc())


def summary(args=None):
    """审核概览: 待审核数量 / 超时未处理 / 今日已审 / 待修改."""
    threshold = overdue_threshold()
    rows = (
        db.session.query(Measurement.review_status, func.count())
        .group_by(Measurement.review_status)
        .all()
    )
    by_status = {
        status: {"key": status, "label": label, "count": 0}
        for status, label in REVIEW_STATUS_LABELS.items()
    }
    for status, count in rows:
        if status in by_status:
            by_status[status]["count"] = int(count)

    overdue = (
        db.session.query(func.count(Measurement.id))
        .filter(
            Measurement.review_status == "pending",
            Measurement.submitted_at <= threshold,
        )
        .scalar()
    )
    oldest_pending_at = (
        db.session.query(func.min(Measurement.submitted_at))
        .filter(Measurement.review_status == "pending")
        .scalar()
    )
    today_start = datetime.combine(datetime.now().date(), datetime.min.time())
    approved_today = (
        db.session.query(func.count(MeasurementReview.id))
        .filter(
            MeasurementReview.action == "approve",
            MeasurementReview.created_at >= today_start,
        )
        .scalar()
    )

    return {
        "pending": by_status["pending"]["count"],
        "overdue": int(overdue or 0),
        "overdue_hours": current_app.config["REVIEW_OVERDUE_HOURS"],
        "approved_today": int(approved_today or 0),
        "rejected": by_status["rejected"]["count"],
        "by_status": list(by_status.values()),
        "oldest_pending_submitted_at": iso(oldest_pending_at),
        "generated_at": iso(datetime.now()),
    }


def _load_pending(ids):
    ids = list(dict.fromkeys(int(item) for item in ids))
    if not ids:
        raise ValidationError("请至少选择一条监测数据", fields={"ids": "empty"})
    records = Measurement.query.filter(Measurement.id.in_(ids)).all()
    found = {record.id for record in records}
    missing = [item for item in ids if item not in found]
    return records, missing


def approve(ids, reviewer=None, comment=None):
    """批量审核通过: 纳入统计口径, 并按通过时的数值生成超标记录."""
    records, missing = _load_pending(ids)
    reviewer = (reviewer or "").strip() or "未署名"
    approved, skipped = [], []
    for record in records:
        if record.review_status != "pending":
            skipped.append(record.id)
            continue
        record.review_status = "approved"
        record.reviewed_by = reviewer
        record.reviewed_at = datetime.now()
        record.review_reason = None
        evaluation = exceedance_rules.evaluate(record.pollutant, record.period, record.value)
        measurement_service.sync_exceedance(record, evaluation)
        measurement_service.log_review(record, "approve", actor=reviewer, reason=comment)
        approved.append(record.id)
    db.session.commit()
    return {"approved": len(approved), "approved_ids": approved,
            "skipped": skipped, "missing": missing}


def reject(ids, reason=None, reviewer=None):
    """批量驳回: 必须填写原因, 记录退回录入人修改."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("驳回时必须填写原因", fields={"reason": "required"})
    records, missing = _load_pending(ids)
    reviewer = (reviewer or "").strip() or "未署名"
    rejected, skipped = [], []
    for record in records:
        if record.review_status != "pending":
            skipped.append(record.id)
            continue
        record.review_status = "rejected"
        record.reviewed_by = reviewer
        record.reviewed_at = datetime.now()
        record.review_reason = reason
        if record.exceedance is not None:
            db.session.delete(record.exceedance)
        measurement_service.log_review(record, "reject", actor=reviewer, reason=reason)
        rejected.append(record.id)
    db.session.commit()
    return {"rejected": len(rejected), "rejected_ids": rejected,
            "skipped": skipped, "missing": missing}


def logs_query(args):
    """审核记录流水: 按时间倒序, 可按动作类型过滤."""
    query = db.session.query(MeasurementReview).join(
        Measurement, MeasurementReview.measurement_id == Measurement.id
    )
    actions = _split(args.get("action"))
    unknown = [item for item in actions if item not in ACTION_CHOICES]
    if unknown:
        raise ValidationError(
            "未知审核动作: %s" % ", ".join(unknown), fields={"action": "unknown"}
        )
    if actions:
        query = query.filter(MeasurementReview.action.in_(actions))
    station_ids = _int_list(args, "station_id")
    if station_ids:
        query = query.filter(Measurement.station_id.in_(station_ids))
    return query.order_by(MeasurementReview.created_at.desc(), MeasurementReview.id.desc())


def get_review_log(log_id):
    entry = db.session.get(MeasurementReview, log_id)
    if entry is None:
        raise NotFoundError("审核记录不存在: id=%s" % log_id)
    return entry
