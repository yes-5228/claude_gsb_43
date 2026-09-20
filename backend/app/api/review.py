"""监测数据审核工作流 API."""
from flask import Blueprint, request

from ..domain.constants import REVIEW_ACTION_LABELS, REVIEW_STATUS_LABELS
from ..services import review_service
from ..utils.pagination import paginate_query
from ..utils.validation import Validator
from .helpers import json_payload, list_payload

bp = Blueprint("review", __name__)


@bp.get("/", strict_slashes=False)
def list_review_measurements():
    """审核工作台列表: 默认待审核队列, 支持状态/站点/录入人/超时过滤."""
    query = review_service.review_query(request.args)
    result = paginate_query(query, lambda row: row.to_dict(include_station=True))
    result["summary"] = review_service.summary()
    return result


@bp.get("/summary")
def review_summary():
    """待审核数量 / 超时未处理 / 今日已审 / 待修改."""
    return review_service.summary()


@bp.get("/options")
def review_options():
    return {
        "statuses": [
            {"value": key, "label": label} for key, label in REVIEW_STATUS_LABELS.items()
        ],
        "actions": [
            {"value": key, "label": label} for key, label in REVIEW_ACTION_LABELS.items()
        ],
    }


@bp.post("/approve")
def approve_measurements():
    """批量审核通过: 纳入统计与超标判定口径."""
    data = json_payload()
    validator = Validator(data)
    reviewer = validator.text("reviewer", "审核人", required=False, max_length=64)
    comment = validator.text("comment", "审核意见", required=False, max_length=500)
    validator.raise_if_invalid("审核信息不合法")
    ids = list_payload("ids", data)
    return review_service.approve(ids, reviewer=reviewer, comment=comment)


@bp.post("/reject")
def reject_measurements():
    """批量驳回: 必须填写原因 (服务层强制), 记录退回录入人修改."""
    data = json_payload()
    validator = Validator(data)
    reason = validator.text("reason", "驳回原因", required=False, max_length=500)
    reviewer = validator.text("reviewer", "审核人", required=False, max_length=64)
    validator.raise_if_invalid("驳回信息不合法")
    ids = list_payload("ids", data)
    return review_service.reject(ids, reason=reason, reviewer=reviewer)


@bp.get("/logs")
def list_review_logs():
    """审核记录流水: 提交/通过/驳回/重报全程留痕."""
    query = review_service.logs_query(request.args)
    return paginate_query(query, lambda row: row.to_dict(include_measurement=True))
