"""监测数据录入业务逻辑 (含超标预判与审核工作流联动)."""
from datetime import datetime

from ..domain import exceedance_rules
from ..domain.standards import get_pollutant
from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Exceedance, Measurement, MeasurementReview, Station


def get_measurement(measurement_id):
    measurement = db.session.get(Measurement, measurement_id)
    if measurement is None:
        raise NotFoundError("监测数据不存在: id=%s" % measurement_id)
    return measurement


def log_review(measurement, action, actor=None, reason=None):
    """Append an audit trail entry for the review workflow."""
    entry = MeasurementReview(
        measurement_id=measurement.id,
        action=action,
        actor=(actor or "").strip() or None,
        reason=(reason or "").strip() or None,
    )
    db.session.add(entry)
    return entry


def preview_entries(period, entries):
    """Dry-run evaluation for the entry form (no database writes)."""
    results = []
    for entry in entries:
        pollutant = str(entry.get("pollutant", "")).upper()
        meta = get_pollutant(pollutant)
        if meta is None:
            raise ValidationError("未知监测因子: %s" % entry.get("pollutant"), fields={"pollutant": "unknown"})
        try:
            value = float(entry.get("value"))
        except (TypeError, ValueError):
            raise ValidationError(
                "%s 监测值必须为数字" % meta["label"], fields={pollutant: "invalid_number"}
            )
        evaluation = exceedance_rules.evaluate(pollutant, period, value)
        results.append(
            {
                "pollutant": pollutant,
                "pollutant_label": meta["label"],
                "value": value,
                "unit": meta["unit"],
                **evaluation,
            }
        )
    return {"period": period, "results": results, "summary": exceedance_rules.summarize(results)}


def _load_station(station_id):
    station = db.session.get(Station, station_id)
    if station is None:
        raise NotFoundError("监测点不存在: id=%s" % station_id)
    return station


def _apply_reading(record, meta, value, data_source, recorder, remark):
    """Refresh the reading fields and the preliminary exceedance flags."""
    evaluation = exceedance_rules.evaluate(record.pollutant, record.period, value)
    record.value = value
    record.unit = meta["unit"]
    record.limit_value = evaluation["limit"]
    record.exceed_ratio = evaluation["ratio"]
    record.is_exceeded = evaluation["exceeded"]
    record.data_source = data_source
    record.recorder = recorder
    record.remark = remark
    return evaluation


def _reset_review(record, actor, action):
    """Data changed: route the record back into the pending review queue."""
    record.review_status = "pending"
    record.submitted_at = datetime.now()
    record.reviewed_by = None
    record.reviewed_at = None
    record.review_reason = None
    if record.exceedance is not None:
        # 未重新审核前不计入超标判定口径
        db.session.delete(record.exceedance)
    log_review(record, action, actor=actor)


def record_entries(station_id, measured_at, period, entries, data_source="manual",
                   recorder=None, remark=None, overwrite=False):
    """Persist one measured_at snapshot for a station.

    Duplicate (station, pollutant, period, measured_at) rows are reported back;
    when ``overwrite`` is true the existing row is refreshed instead.
    Every write (re)enters the review workflow as ``pending``; exceedance
    records are only generated once the entry passes review.
    """
    station = _load_station(station_id)
    if not entries:
        raise ValidationError("至少需要录入一条监测数据", fields={"entries": "empty"})

    existing = {
        row.pollutant: row
        for row in Measurement.query.filter_by(
            station_id=station.id, period=period, measured_at=measured_at
        ).all()
    }

    created, updated, duplicates, evaluated = [], [], [], []
    seen = set()
    for entry in entries:
        pollutant = str(entry.get("pollutant", "")).upper()
        meta = get_pollutant(pollutant)
        if meta is None:
            raise ValidationError(
                "未知监测因子: %s" % entry.get("pollutant"), fields={"pollutant": "unknown"}
            )
        if pollutant in seen:
            raise ValidationError(
                "%s 在同一时刻重复提交" % meta["label"], fields={pollutant: "duplicated_in_batch"}
            )
        seen.add(pollutant)

        try:
            value = float(entry.get("value"))
        except (TypeError, ValueError):
            raise ValidationError(
                "%s 监测值必须为数字" % meta["label"], fields={pollutant: "invalid_number"}
            )

        evaluation = exceedance_rules.evaluate(pollutant, period, value)
        evaluated.append(
            {
                "pollutant": pollutant,
                "pollutant_label": meta["label"],
                "value": value,
                "unit": meta["unit"],
                **evaluation,
            }
        )

        record = existing.get(pollutant)
        if record is not None and not overwrite:
            duplicates.append(
                {
                    "pollutant": pollutant,
                    "pollutant_label": meta["label"],
                    "value": value,
                    "existing_id": record.id,
                    "message": "该时刻 %s 数据已存在" % meta["label"],
                }
            )
            continue

        is_new = record is None
        if is_new:
            record = Measurement(station_id=station.id, pollutant=pollutant, period=period,
                                 measured_at=measured_at)
            db.session.add(record)

        _apply_reading(record, meta, value, data_source,
                       entry.get("recorder") or recorder, entry.get("remark") or remark)
        db.session.flush()
        _reset_review(record, actor=record.recorder, action="submit" if is_new else "resubmit")
        db.session.flush()
        (created if is_new else updated).append(record.to_dict(include_station=True))

    if not created and not updated and duplicates:
        raise ConflictError(
            "所选时刻已存在相同数据, 如需覆盖请勾选\"覆盖已有数据\": %s"
            % ", ".join(item["pollutant_label"] for item in duplicates)
        )

    db.session.commit()
    return {
        "station": station.to_option(),
        "measured_at": measured_at.isoformat(timespec="seconds"),
        "period": period,
        "created": created,
        "updated": updated,
        "exceedances": [],
        "duplicates": duplicates,
        "evaluations": evaluated,
        "summary": {
            "created_count": len(created),
            "updated_count": len(updated),
            "exceeded_count": len([item for item in evaluated if item["exceeded"]]),
            "duplicate_count": len(duplicates),
        },
    }


def update_measurement(measurement, value, remark=None, recorder=None):
    """录入人修改数据后重新送审 (驳回或待审记录均可修正).

    修改后记录回到待审核状态, 已生成的超标记录先行移除,
    待审核通过后按新数值重新判定。
    """
    meta = get_pollutant(measurement.pollutant)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(
            "%s 监测值必须为数字" % meta["label"], fields={"value": "invalid_number"}
        )

    _apply_reading(
        measurement,
        meta,
        number,
        measurement.data_source,
        (recorder or "").strip() or measurement.recorder,
        remark if remark is not None else measurement.remark,
    )
    _reset_review(measurement, actor=measurement.recorder, action="resubmit")
    db.session.commit()
    return measurement


def sync_exceedance(record, evaluation):
    """Create / refresh / drop the exceedance row attached to a measurement.

    Only invoked once the measurement has passed review, keeping the
    exceedance work bench inside the approved-data perimeter.
    """
    if evaluation["exceeded"]:
        if record.exceedance is None:
            record.exceedance = Exceedance(
                station_id=record.station_id,
                pollutant=record.pollutant,
                period=record.period,
                measured_at=record.measured_at,
                value=record.value,
                limit_value=evaluation["limit"],
                exceed_ratio=evaluation["ratio"],
                level=evaluation["level"],
                status="pending",
            )
        else:
            record.exceedance.value = record.value
            record.exceedance.limit_value = evaluation["limit"]
            record.exceedance.exceed_ratio = evaluation["ratio"]
            record.exceedance.level = evaluation["level"]
            record.exceedance.measured_at = record.measured_at
    elif record.exceedance is not None:
        db.session.delete(record.exceedance)


def delete_measurement(measurement):
    payload = measurement.to_dict()
    db.session.delete(measurement)
    db.session.commit()
    return payload
