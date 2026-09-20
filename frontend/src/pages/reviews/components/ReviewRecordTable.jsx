import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { REVIEW_ACTION_TONE } from '../../../constants/index.js'
import { formatDateTime, formatNumber } from '../../../utils/format.js'

export default function ReviewRecordTable({ rows, loading }) {
  const columns = [
    {
      key: 'created_at',
      title: '时间',
      className: 'cell-nowrap',
      render: (row) => formatDateTime(row.created_at)
    },
    {
      key: 'station',
      title: '监测点',
      render: (row) => (
        <div>
          <div>{row.measurement?.station_name || '-'}</div>
          <div className="small muted mono">{row.measurement?.station_code || ''}</div>
        </div>
      )
    },
    { key: 'pollutant', title: '因子', render: (row) => row.measurement?.pollutant_label || '-' },
    {
      key: 'value',
      title: '监测值',
      align: 'right',
      render: (row) =>
        row.measurement ? (
          <span className={row.measurement.is_exceeded ? 'danger-text strong' : ''}>
            {formatNumber(row.measurement.value)} <span className="muted small">{row.measurement.unit || ''}</span>
          </span>
        ) : (
          '-'
        )
    },
    {
      key: 'measured_at',
      title: '监测时间',
      className: 'cell-nowrap',
      render: (row) => formatDateTime(row.measurement?.measured_at)
    },
    {
      key: 'action',
      title: '动作',
      render: (row) => <Tag tone={REVIEW_ACTION_TONE[row.action]}>{row.action_label}</Tag>
    },
    { key: 'reviewer', title: '操作人', render: (row) => row.reviewer || '-' },
    { key: 'recorder', title: '录入人', render: (row) => row.measurement?.recorder || '-' },
    {
      key: 'reason',
      title: '原因 / 备注',
      render: (row) => (row.reason ? <span>{row.reason}</span> : <span className="muted">-</span>)
    }
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      emptyText="暂无审核记录"
      emptyIcon="🗂️"
    />
  )
}
