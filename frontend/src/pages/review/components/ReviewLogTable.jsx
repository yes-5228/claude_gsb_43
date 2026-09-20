import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { REVIEW_ACTION_TONE, REVIEW_STATUS_LABELS, REVIEW_STATUS_TONE } from '../../../constants/index.js'
import { formatDateTime, formatNumber } from '../../../utils/format.js'

/** 审核记录流水: 提交 / 通过 / 驳回 / 重报全程留痕。 */
export default function ReviewLogTable({ rows, loading }) {
  const columns = [
    { key: 'created_at', title: '时间', className: 'cell-nowrap', render: (row) => formatDateTime(row.created_at) },
    {
      key: 'measurement',
      title: '监测数据',
      render: (row) => {
        const measurement = row.measurement
        if (!measurement) return '-'
        return (
          <div>
            <div>
              {measurement.station_name || '-'} · {measurement.pollutant_label}{' '}
              <span className="muted small">
                {formatNumber(measurement.value)} {measurement.unit || ''}
              </span>
            </div>
            <div className="small muted">
              监测时间 {formatDateTime(measurement.measured_at)} · 录入人 {measurement.recorder || '-'}
            </div>
          </div>
        )
      }
    },
    {
      key: 'action',
      title: '动作',
      render: (row) => <Tag tone={REVIEW_ACTION_TONE[row.action]}>{row.action_label}</Tag>
    },
    { key: 'actor', title: '操作人', render: (row) => row.actor || '-' },
    {
      key: 'reason',
      title: '原因 / 说明',
      render: (row) => (row.reason ? row.reason : <span className="muted">-</span>)
    },
    {
      key: 'review_status',
      title: '当前状态',
      render: (row) =>
        row.measurement ? (
          <Tag tone={REVIEW_STATUS_TONE[row.measurement.review_status]}>
            {REVIEW_STATUS_LABELS[row.measurement.review_status] || row.measurement.review_status}
          </Tag>
        ) : (
          '-'
        )
    }
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      emptyText="暂无审核记录"
      emptyIcon="🧾"
    />
  )
}
