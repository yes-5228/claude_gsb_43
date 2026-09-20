import StatCard from '../../../components/common/StatCard.jsx'

export default function ReviewSummaryCards({ summary }) {
  const pending = summary?.pending ?? '-'
  const overdue = summary?.overdue ?? 0
  const approvedToday = summary?.approved_today ?? '-'
  const rejected = summary?.rejected ?? '-'

  return (
    <div className="stat-grid">
      <StatCard
        label="待审核数据"
        value={pending}
        tone={pending > 0 ? 'warning' : undefined}
        foot="提交后等待审核, 通过才纳入统计口径"
      />
      <StatCard
        label="超时未处理"
        value={overdue}
        tone={overdue > 0 ? 'danger' : undefined}
        foot={summary ? `超过 ${summary.overdue_hours} 小时未审核` : ''}
      />
      <StatCard label="今日已审核" value={approvedToday} foot="今日审核通过的记录数" />
      <StatCard
        label="待修改 (已驳回)"
        value={rejected}
        tone={rejected > 0 ? 'warning' : undefined}
        foot="已退回录入人, 等待修正后重新送审"
      />
    </div>
  )
}
