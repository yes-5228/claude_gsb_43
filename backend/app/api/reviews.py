"""监测数据审核 API: 待审核队列 / 审核动作 / 审核记录 / 超时提醒."""
from flask import Blueprint, request

from ..domain.constants import REVIEW_ACTION_LABELS, REVIEW_STATUS_LABELS
from ..services import review_service
from ..utils.pagination import paginate_query
from ..utils.validation import Validator
from .helpers import json_payload, list_payload

bp = Blueprint("reviews", __name__)


@bp.get("/pending")
def pending_queue():
    """待审核队列: 按提交时间正序, 行内附带等待时长与超时标记."""
    query = review_service.pending_query(request.args)
    return paginate_query(query, review_service.pending_item)


@bp.get("/summary")
def review_summary():
    """待审核数量 / 超时未处理数量 / 今日已处理等提醒指标."""
    return review_service.pending_summary()


@bp.get("/records")
def review_records():
    """审核记录 (审计轨迹): 提交 / 重新提交 / 通过 / 驳回."""
    query = review_service.records_query(request.args)
    return paginate_query(query, lambda row: row.to_dict(include_measurement=True))


@bp.get("/options")
def review_options():
    return {
        "statuses": [{"value": key, "label": label} for key, label in REVIEW_STATUS_LABELS.items()],
        "actions": [{"value": key, "label": label} for key, label in REVIEW_ACTION_LABELS.items()],
    }


@bp.post("/<int:measurement_id>")
def review_one(measurement_id):
    """审核单条: action=approve 通过 / action=reject 驳回 (驳回必填原因)."""
    measurement = review_service.get_measurement(measurement_id)
    data = json_payload()
    validator = Validator(data)
    action = validator.choice("action", "审核动作", choices=("approve", "reject"), required=True)
    reviewer = validator.text("reviewer", "审核人", required=False, max_length=64)
    reason = validator.text("reason", "审核意见", required=False, max_length=500)
    validator.raise_if_invalid("审核信息不合法")

    updated = review_service.review(measurement, action, reviewer=reviewer, reason=reason)
    return updated.to_dict(include_station=True)


@bp.post("/batch")
def review_batch():
    """批量审核: 勾选多条后一次性通过或驳回."""
    data = json_payload()
    validator = Validator(data)
    action = validator.choice("action", "审核动作", choices=("approve", "reject"), required=True)
    reviewer = validator.text("reviewer", "审核人", required=False, max_length=64)
    reason = validator.text("reason", "审核意见", required=False, max_length=500)
    validator.raise_if_invalid("审核信息不合法")

    ids = list_payload("ids", data)
    return review_service.review_batch(ids, action, reviewer=reviewer, reason=reason)
