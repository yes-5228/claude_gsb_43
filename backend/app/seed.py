"""演示数据生成与启动引导."""
import random
from datetime import date, datetime, timedelta

from sqlalchemy import inspect, text

from .extensions import db
from .models import Exceedance, Measurement, Station

DEMO_STATIONS = [
    {
        "code": "SZ-AQ-001", "name": "市民中心站", "area": "福田区",
        "address": "福田区福中三路市民中心广场", "station_type": "ambient",
        "status": "active", "longitude": 114.0579, "latitude": 22.5410,
        "installed_at": date(2019, 5, 12), "remark": "城市环境评价点",
    },
    {
        "code": "SZ-AQ-002", "name": "华侨城站", "area": "南山区",
        "address": "南山区华侨城生态广场", "station_type": "ambient",
        "status": "active", "longitude": 113.9711, "latitude": 22.5356,
        "installed_at": date(2020, 3, 1), "remark": "城市环境评价点",
    },
    {
        "code": "SZ-AQ-003", "name": "罗湖口岸站", "area": "罗湖区",
        "address": "罗湖区火车站东广场", "station_type": "traffic",
        "status": "active", "longitude": 114.1276, "latitude": 22.5329,
        "installed_at": date(2018, 11, 20), "remark": "道路交通监测点, 早晚高峰浓度偏高",
    },
    {
        "code": "SZ-AQ-004", "name": "宝安中心站", "area": "宝安区",
        "address": "宝安区中心区宝安大道", "station_type": "ambient",
        "status": "active", "longitude": 113.8830, "latitude": 22.5551,
        "installed_at": date(2021, 6, 18), "remark": None,
    },
    {
        "code": "SZ-AQ-005", "name": "龙岗工业园站", "area": "龙岗区",
        "address": "龙岗区宝龙工业区龙岗大道", "station_type": "industrial",
        "status": "active", "longitude": 114.2465, "latitude": 22.7204,
        "installed_at": date(2019, 9, 8), "remark": "周边为工业排放源, 需重点关注 SO₂",
    },
    {
        "code": "SZ-AQ-006", "name": "梧桐山背景站", "area": "罗湖区",
        "address": "罗湖区梧桐山风景区", "station_type": "background",
        "status": "active", "longitude": 114.1837, "latitude": 22.5862,
        "installed_at": date(2017, 4, 2), "remark": "区域背景点, 用于对照评价",
    },
    {
        "code": "SZ-AQ-007", "name": "大鹏生态站", "area": "大鹏新区",
        "address": "大鹏新区葵涌街道", "station_type": "rural",
        "status": "maintenance", "longitude": 114.4798, "latitude": 22.5964,
        "installed_at": date(2022, 8, 15), "remark": "设备检修中, 计划本周恢复",
    },
    {
        "code": "SZ-AQ-008", "name": "前海自贸区站", "area": "南山区",
        "address": "南山区前海湾保税港区", "station_type": "ambient",
        "status": "offline", "longitude": 113.8980, "latitude": 22.5253,
        "installed_at": date(2023, 1, 10), "remark": "站点搬迁停用",
    },
]

POLLUTANT_BASE = {"PM25": 45.0, "PM10": 80.0, "SO2": 30.0, "NO2": 45.0, "CO": 1.5, "O3": 120.0}
HOURLY_FACTOR = {"PM25": 1.0, "PM10": 1.05, "SO2": 0.8, "NO2": 1.1, "CO": 0.9, "O3": 1.3}
STATION_FACTOR = {
    "ambient": 1.0, "traffic": 1.2, "industrial": 1.35, "background": 0.55, "rural": 0.75,
}
HOURLY_POINTS = (2, 8, 14, 20)
RECORDERS = ("李静", "王敏", "陈志强", "赵宇", "孙倩")
REVIEWERS = ("刘洋", "周慧")


def _value(pollutant, period, station_type, rng):
    base = POLLUTANT_BASE[pollutant] * STATION_FACTOR.get(station_type, 1.0)
    if period == "hourly":
        base *= HOURLY_FACTOR[pollutant]
    value = base * rng.uniform(0.72, 1.22)
    if rng.random() < 0.12:  # 少量明显超标样本, 便于演示超标标注
        value *= rng.uniform(1.8, 2.6)
    return round(value, 2 if pollutant == "CO" else 1)


def seed_demo_data(days=5, rng=None, recorder_pool=RECORDERS):
    """Generate demo stations and monitoring records through the normal service path."""
    from .services import measurement_service

    rng = rng or random.Random(20260914)
    created_stations = []
    for item in DEMO_STATIONS:
        station = Station(**item)
        db.session.add(station)
        created_stations.append(station)
    db.session.commit()

    today = date.today()
    totals = {"stations": len(created_stations), "measurements": 0, "exceedances": 0}
    for station in created_stations:
        for offset in range(days):
            day = today - timedelta(days=offset)
            daily_entries = [
                {"pollutant": code, "value": _value(code, "daily", station.station_type, rng)}
                for code in POLLUTANT_BASE
            ]
            result = measurement_service.record_entries(
                station_id=station.id,
                measured_at=datetime(day.year, day.month, day.day, 0, 0),
                period="daily",
                entries=daily_entries,
                data_source="device",
                recorder=rng.choice(recorder_pool),
                remark="日均值自动汇总",
            )
            totals["measurements"] += result["summary"]["created_count"]

            for hour in HOURLY_POINTS:
                hourly_entries = [
                    {"pollutant": code, "value": _value(code, "hourly", station.station_type, rng)}
                    for code in HOURLY_FACTOR
                ]
                result = measurement_service.record_entries(
                    station_id=station.id,
                    measured_at=datetime(day.year, day.month, day.day, hour, 0),
                    period="hourly",
                    entries=hourly_entries,
                    data_source="manual",
                    recorder=rng.choice(recorder_pool),
                )
                totals["measurements"] += result["summary"]["created_count"]

    # 审核工作流演示: 大部分数据审核通过进入统计口径, 少量留作待审核 (含超时未处理)
    from .services import review_service

    measurements = Measurement.query.order_by(Measurement.id.asc()).all()
    approve_ids = [row.id for index, row in enumerate(measurements) if index % 10 != 9]
    if approve_ids:
        review_service.review_batch(
            approve_ids, "approve", reviewer=rng.choice(REVIEWERS), reason="周期性批量复核通过"
        )
    totals["approved"] = len(approve_ids)
    totals["pending_review"] = len(measurements) - len(approve_ids)

    # 让一部分待审核数据的提交时间早于超时阈值, 用于演示超时未处理提醒
    timeout_hours = 24
    try:
        from flask import current_app

        timeout_hours = int(current_app.config.get("REVIEW_TIMEOUT_HOURS", 24))
    except RuntimeError:  # pragma: no cover - 无应用上下文时退化为默认值
        pass
    pending_rows = (
        Measurement.query.filter_by(review_status="pending").order_by(Measurement.id.asc()).all()
    )
    now = datetime.now()
    for index, row in enumerate(pending_rows):
        if index % 2 == 0:
            row.created_at = now - timedelta(hours=timeout_hours + 4 + index)
            db.session.add(row)
    db.session.commit()

    totals["exceedances"] = Exceedance.query.count()

    # 标注一部分超标记录, 让工作台同时存在待办与已处理记录
    from .services import exceedance_service

    exceedances = Exceedance.query.order_by(Exceedance.id.asc()).all()
    annotated = 0
    for index, record in enumerate(exceedances):
        if index % 3 == 0:
            continue
        if index % 3 == 1:
            exceedance_service.annotate(
                record, status="confirmed", note="数据经复核属实, 已通知运维排查周边排放源",
                annotator=rng.choice(recorder_pool),
            )
        else:
            exceedance_service.annotate(
                record, status="ignored", note="仪器校准期间异常值, 已在原始数据中标记无效",
                annotator=rng.choice(recorder_pool),
            )
        annotated += 1
    totals["annotated"] = annotated
    return totals


def reset_database():
    db.drop_all()
    db.create_all()


def ensure_schema_upgrades():
    """为审核工作流之前创建的存量数据库补充审核列, 历史数据视为已审核通过."""
    inspector = inspect(db.engine)
    if "measurements" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("measurements")}
    additions = []
    if "review_status" not in existing:
        additions.append(("review_status", "VARCHAR(16) NOT NULL DEFAULT 'pending'"))
    if "reviewed_at" not in existing:
        additions.append(("reviewed_at", "TIMESTAMP"))
    if "reviewer" not in existing:
        additions.append(("reviewer", "VARCHAR(64)"))
    if "review_reason" not in existing:
        additions.append(("review_reason", "TEXT"))
    if not additions:
        return
    with db.engine.begin() as connection:
        for name, ddl in additions:
            connection.execute(text("ALTER TABLE measurements ADD COLUMN %s %s" % (name, ddl)))
        # 存量数据此前已在统计口径内, 迁移后直接视为审核通过
        connection.execute(text("UPDATE measurements SET review_status = 'approved'"))


def ensure_bootstrap(app):
    """Create tables / seed demo data at startup when enabled by config."""
    auto_init = app.config.get("AUTO_INIT_DB")
    auto_seed = app.config.get("AUTO_SEED")
    if not auto_init and not auto_seed:
        return
    with app.app_context():
        try:
            if auto_init:
                db.create_all()
                ensure_schema_upgrades()
            if auto_seed and db.session.query(Station.id).first() is None:
                app.logger.info("seeding demo data ...")
                seed_demo_data()
        except Exception as exc:  # pragma: no cover - depends on external database
            app.logger.warning("bootstrap skipped: %s", exc)
