"""监测数据审核记录 (审计轨迹, 只增不改)."""
from datetime import datetime

from ..domain.constants import REVIEW_ACTION_LABELS, REVIEW_STATUS_LABELS, label_of
from ..extensions import db
from .base import iso


class ReviewRecord(db.Model):
    __tablename__ = "review_records"

    id = db.Column(db.Integer, primary_key=True)
    measurement_id = db.Column(
        db.Integer,
        db.ForeignKey("measurements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = db.Column(db.String(16), nullable=False, index=True)  # submit/resubmit/approve/reject
    from_status = db.Column(db.String(16))
    to_status = db.Column(db.String(16), nullable=False, default="pending")
    reviewer = db.Column(db.String(64))
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)

    measurement = db.relationship("Measurement", back_populates="review_records")

    def to_dict(self, include_measurement=False):
        payload = {
            "id": self.id,
            "measurement_id": self.measurement_id,
            "action": self.action,
            "action_label": label_of(REVIEW_ACTION_LABELS, self.action),
            "from_status": self.from_status,
            "from_status_label": label_of(REVIEW_STATUS_LABELS, self.from_status)
            if self.from_status
            else None,
            "to_status": self.to_status,
            "to_status_label": label_of(REVIEW_STATUS_LABELS, self.to_status),
            "reviewer": self.reviewer,
            "reason": self.reason,
            "created_at": iso(self.created_at),
        }
        if include_measurement and self.measurement:
            measurement = self.measurement
            payload["measurement"] = {
                "id": measurement.id,
                "pollutant": measurement.pollutant,
                "pollutant_label": measurement.pollutant_label(),
                "value": measurement.value,
                "unit": measurement.unit,
                "is_exceeded": bool(measurement.is_exceeded),
                "measured_at": iso(measurement.measured_at),
                "recorder": measurement.recorder,
                "review_status": measurement.review_status,
                "review_status_label": label_of(REVIEW_STATUS_LABELS, measurement.review_status),
                "station_id": measurement.station_id,
                "station_name": measurement.station.name if measurement.station else None,
                "station_code": measurement.station.code if measurement.station else None,
            }
        return payload

    def __repr__(self):
        return "<ReviewRecord %s %s>" % (self.measurement_id, self.action)
