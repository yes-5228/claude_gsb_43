import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { REVIEW_STATUS_TONE } from '../../../constants/index.js'
import { formatDateTime, formatNumber, formatRatio } from '../../../utils/format.js'

function waitingText(submittedAt) {
  if (!submittedAt) return '-'
  const hours = (Date.now() - new Date(String(submittedAt).replace(' ', 'T')).getTime()) / 3600000
  if (Number.isNaN(hours) || hours < 0) return '-'
  if (hours < 1) return '不足 1 小时'
  if (hours < 24) return `${Math.floor(hours)} 小时`
  return `${Math.floor(hours / 24)} 天 ${Math.floor(hours % 24)} 小时`
}

export default function ReviewTable({
  rows,
  loading,
  overdueHours = 24,
  selectable = false,
  selectedIds = [],
  onToggleRow,
  onToggleAll,
  onApprove,
  onReject,
  onEdit
}) {
  const isOverdue = (row) =>
    row.review_status === 'pending' &&
    row.submitted_at &&
    Date.now() - new Date(String(row.submitted_at).replace(' ', 'T')).getTime() >
      overdueHours * 3600000

  const columns = [
    {
      key: 'submitted_at',
      title: '提交时间',
      className: 'cell-nowrap',
      render: (row) => (
        <div>
          <div>{formatDateTime(row.submitted_at)}</div>
          {row.review_status === 'pending' ? (
            <div className="small muted">
              已等待 {waitingText(row.submitted_at)}{' '}
              {isOverdue(row) ? <Tag tone="danger">超时</Tag> : null}
            </div>
          ) : null}
        </div>
      )
    },
    { key: 'measured_at', title: '监测时间', className: 'cell-nowrap', render: (row) => formatDateTime(row.measured_at) },
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
    { key: 'pollutant_label', title: '监测因子', className: 'cell-nowrap' },
    {
      key: 'value',
      title: '监测值',
      align: 'right',
      className: 'cell-nowrap',
      render: (row) => (
        <span className={row.is_exceeded ? 'danger-text strong' : ''}>
          {formatNumber(row.value)} <span className="muted small">{row.unit}</span>
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
      key: 'review_status',
      title: '审核状态',
      render: (row) => (
        <div className="stack" style={{ gap: 4 }}>
          <Tag tone={REVIEW_STATUS_TONE[row.review_status]}>{row.review_status_label}</Tag>
          {row.review_status === 'rejected' && row.review_reason ? (
            <span className="small danger-text" title={row.review_reason}>
              原因: {row.review_reason}
            </span>
          ) : null}
          {row.review_status === 'approved' && row.reviewed_by ? (
            <span className="small muted">
              {row.reviewed_by} · {formatDateTime(row.reviewed_at)}
            </span>
          ) : null}
        </div>
      )
    },
    {
      key: 'actions',
      title: '操作',
      align: 'right',
      className: 'cell-nowrap',
      render: (row) => {
        if (row.review_status === 'pending') {
          return (
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
        if (row.review_status === 'rejected') {
          return (
            <button type="button" className="btn btn-sm" onClick={() => onEdit(row)}>
              修改重报
            </button>
          )
        }
        return <span className="muted small">已归档</span>
      }
    }
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      selectable={selectable}
      selectedIds={selectedIds}
      onToggleRow={onToggleRow}
      onToggleAll={onToggleAll}
      emptyText="当前筛选下没有待处理的审核数据"
      emptyIcon="✅"
      rowClassName={(row) => (isOverdue(row) ? 'row-overdue' : '')}
    />
  )
}
