"""监测数据审核记录 (提交/通过/驳回/重报全程留痕)."""
from datetime import datetime

from ..domain.constants import REVIEW_ACTION_LABELS, label_of
from ..extensions import db
from .base import iso


class MeasurementReview(db.Model):
    __tablename__ = "measurement_reviews"

    id = db.Column(db.Integer, primary_key=True)
    measurement_id = db.Column(
        db.Integer,
        db.ForeignKey("measurements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = db.Column(db.String(16), nullable=False, index=True)
    actor = db.Column(db.String(64))
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)

    measurement = db.relationship("Measurement", back_populates="reviews")

    def to_dict(self, include_measurement=False):
        payload = {
            "id": self.id,
            "measurement_id": self.measurement_id,
            "action": self.action,
            "action_label": label_of(REVIEW_ACTION_LABELS, self.action),
            "actor": self.actor,
            "reason": self.reason,
            "created_at": iso(self.created_at),
        }
        if include_measurement and self.measurement:
            measurement = self.measurement
            station = measurement.station
            payload["measurement"] = {
                "id": measurement.id,
                "station_id": measurement.station_id,
                "station_name": station.name if station else None,
                "station_code": station.code if station else None,
                "pollutant": measurement.pollutant,
                "pollutant_label": measurement.pollutant_label(),
                "value": measurement.value,
                "unit": measurement.unit,
                "measured_at": iso(measurement.measured_at),
                "recorder": measurement.recorder,
                "review_status": measurement.review_status,
            }
        return payload

    def __repr__(self):
        return "<MeasurementReview %s %s>" % (self.measurement_id, self.action)
