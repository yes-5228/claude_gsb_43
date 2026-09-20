import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { formatDateTime, formatNumber, formatRatio } from '../../../utils/format.js'

export function formatWaiting(hours) {
  if (hours === null || hours === undefined) return '-'
  if (hours < 1) return '不足 1 小时'
  if (hours < 24) return `${Math.floor(hours)} 小时`
  const days = Math.floor(hours / 24)
  const rest = Math.floor(hours % 24)
  return rest ? `${days} 天 ${rest} 小时` : `${days} 天`
}

export default function PendingReviewTable({
  rows,
  loading,
  selectedIds,
  onToggleRow,
  onToggleAll,
  onApprove,
  onReject
}) {
  const columns = [
    {
      key: 'created_at',
      title: '提交时间',
      className: 'cell-nowrap',
      render: (row) => formatDateTime(row.created_at)
    },
    {
      key: 'station',
      title: '监测点',
      render: (row) => (
        <div>
          <div>{row.station?.name || '-'}</div>
          <div className="small muted mono">{row.station?.code || ''}</div>
        </div>
      )
    },
    { key: 'pollutant_label', title: '因子', className: 'cell-nowrap' },
    { key: 'period_label', title: '周期', className: 'cell-nowrap' },
    { key: 'measured_at', title: '监测时间', className: 'cell-nowrap', render: (row) => formatDateTime(row.measured_at) },
    {
      key: 'value',
      title: '监测值 / 限值',
      align: 'right',
      className: 'cell-nowrap',
      render: (row) => (
        <span className={row.is_exceeded ? 'danger-text strong' : ''}>
          {formatNumber(row.value)} / {row.limit_value === null ? '无限值' : formatNumber(row.limit_value)}
          <span className="muted small"> {row.unit}</span>
        </span>
      )
    },
    {
      key: 'is_exceeded',
      title: '超标预判',
      render: (row) =>
        row.is_exceeded ? <Tag tone="danger">{formatRatio(row.exceed_ratio)}</Tag> : <Tag tone="success">达标</Tag>
    },
    { key: 'recorder', title: '录入人', render: (row) => row.recorder || '-' },
    {
      key: 'waiting_hours',
      title: '等待时长',
      className: 'cell-nowrap',
      render: (row) =>
        row.is_overdue ? (
          <Tag tone="danger">超时 · {formatWaiting(row.waiting_hours)}</Tag>
        ) : (
          <span className="muted">{formatWaiting(row.waiting_hours)}</span>
        )
    },
    {
      key: 'actions',
      title: '操作',
      align: 'right',
      className: 'cell-nowrap',
      render: (row) => (
        <div className="inline" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-sm btn-primary" onClick={() => onApprove(row)}>
            通过
          </button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => onReject(row)}>
            驳回
          </button>
        </div>
      )
    }
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      selectable
      selectedIds={selectedIds}
      onToggleRow={onToggleRow}
      onToggleAll={onToggleAll}
      rowClassName={(row) => (row.is_overdue ? 'row-overdue' : '')}
      emptyText="当前没有待审核的数据, 审核队列已清空"
      emptyIcon="✅"
    />
  )
}
