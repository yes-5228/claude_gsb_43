import { useCallback, useState } from 'react'
import {
  batchReview,
  listPendingReviews,
  listReviewRecords,
  reviewMeasurement,
  reviewSummary
} from '../../api/reviews.js'
import Pagination from '../../components/common/Pagination.jsx'
import { FilterPanel, SectionCard } from '../../components/common/Card.jsx'
import { Alert } from '../../components/common/Feedback.jsx'
import { Field, Input, Select } from '../../components/common/FormField.jsx'
import StatCard from '../../components/common/StatCard.jsx'
import Tag from '../../components/common/Tag.jsx'
import { useToast } from '../../components/common/ToastProvider.jsx'
import { REVIEW_ACTION_LABELS } from '../../constants/index.js'
import { useAsyncData } from '../../hooks/useAsyncData.js'
import { useListQuery } from '../../hooks/useListQuery.js'
import PendingReviewTable from './components/PendingReviewTable.jsx'
import ReviewActionModal from './components/ReviewActionModal.jsx'
import ReviewRecordTable from './components/ReviewRecordTable.jsx'

const QUEUE_FILTERS = { overdue: '' }
const RECORD_FILTERS = { action: '', reviewer: '', date_from: '', date_to: '' }

const ACTION_OPTIONS = Object.entries(REVIEW_ACTION_LABELS).map(([value, label]) => ({ value, label }))

export default function ReviewPage() {
  const toast = useToast()
  const queue = useListQuery(listPendingReviews, QUEUE_FILTERS)
  const records = useListQuery(listReviewRecords, RECORD_FILTERS)
  const summaryLoader = useCallback(() => reviewSummary(), [])
  const summary = useAsyncData(summaryLoader)

  const [selected, setSelected] = useState([])
  const [target, setTarget] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [recordDraft, setRecordDraft] = useState(RECORD_FILTERS)

  const reloadAll = useCallback(() => {
    queue.reload()
    records.reload()
    summary.reload().catch(() => {})
  }, [queue, records, summary])

  const toggleRow = useCallback((id) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]))
  }, [])

  const toggleAll = useCallback((ids) => {
    setSelected((prev) =>
      ids.every((id) => prev.includes(id))
        ? prev.filter((id) => !ids.includes(id))
        : Array.from(new Set([...prev, ...ids]))
    )
  }, [])

  const openAction = useCallback(
    (action, ids, label) => {
      if (ids.length === 0) {
        toast.warning('请先勾选需要审核的数据')
        return
      }
      setActionError(null)
      setTarget({ action, ids, label })
    },
    [toast]
  )

  const confirmAction = async ({ action, ids, reviewer, reason }) => {
    setBusy(true)
    setActionError(null)
    try {
      const payload = { action, reviewer, reason }
      const result =
        ids.length === 1
          ? await reviewMeasurement(ids[0], payload)
          : await batchReview({ ...payload, ids })
      const done = ids.length === 1 ? 1 : result.updated
      if (action === 'reject') {
        toast.success(`已驳回 ${done} 条数据, 退回录入人修改`)
      } else {
        const extra = result.exceedance_count ? `, 生成 ${result.exceedance_count} 条待标注超标记录` : ''
        toast.success(`已通过 ${done} 条数据${extra}`)
      }
      if (result.skipped?.length) toast.warning(`${result.skipped.length} 条记录已审核过, 已跳过`)
      setTarget(null)
      setSelected([])
      reloadAll()
    } catch (error) {
      setActionError(error.message)
    } finally {
      setBusy(false)
    }
  }

  const data = summary.data

  return (
    <>
      <div className="stat-grid">
        <StatCard
          label="待审核数据"
          value={data ? data.pending : '-'}
          tone={data?.pending ? 'warning' : undefined}
          foot={data?.oldest_pending_at ? `最早提交 ${data.oldest_pending_at.slice(0, 16).replace('T', ' ')}` : '审核队列已清空'}
        />
        <StatCard
          label="超时未处理"
          value={data ? data.overdue : '-'}
          tone={data?.overdue ? 'danger' : undefined}
          foot={data ? `超过 ${data.threshold_hours} 小时未审核` : ''}
        />
        <StatCard label="今日已审核" value={data ? data.reviewed_today : '-'} foot="通过 + 驳回" />
        <StatCard
          label="累计驳回"
          value={data ? data.rejected : '-'}
          tone={data?.rejected ? 'warning' : undefined}
          foot={data ? `已通过 ${data.approved} 条` : ''}
        />
      </div>

      {data?.overdue > 0 ? (
        <Alert tone="warning">
          有 {data.overdue} 条数据超过 {data.threshold_hours} 小时仍未审核, 请优先处理,
          超时数据在队列中以红色标记。
        </Alert>
      ) : null}

      {queue.error ? <Alert tone="error">{queue.error.message}</Alert> : null}

      <SectionCard
        title="待审核队列"
        hint="按提交时间正序, 审核通过后数据才纳入统计与超标判定口径"
        actions={
          <>
            <Tag tone="primary">已选 {selected.length} 条</Tag>
            <label className="inline" style={{ gap: 6 }}>
              <input
                type="checkbox"
                checked={queue.filters.overdue === 'true'}
                onChange={(event) =>
                  queue.setFilters({ ...queue.filters, overdue: event.target.checked ? 'true' : '' })
                }
              />
              <span className="small">仅看超时</span>
            </label>
            <button type="button" className="btn btn-sm" onClick={reloadAll} disabled={queue.loading}>
              刷新
            </button>
          </>
        }
      >
        <div className="stack">
          <div className="card" style={{ boxShadow: 'none' }}>
            <div className="card-body tight">
              <div className="inline">
                <span className="field-label">批量审核</span>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => openAction('approve', selected, '勾选的数据')}
                >
                  批量通过
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => openAction('reject', selected, '勾选的数据')}
                >
                  批量驳回
                </button>
                <button type="button" className="btn" onClick={() => setSelected([])} disabled={selected.length === 0}>
                  清空选择
                </button>
                <span className="small muted">驳回时必须填写原因, 数据将退回录入人修改</span>
              </div>
            </div>
          </div>

          <PendingReviewTable
            rows={queue.items}
            loading={queue.loading}
            selectedIds={selected}
            onToggleRow={toggleRow}
            onToggleAll={toggleAll}
            onApprove={(row) => openAction('approve', [row.id], `${row.station?.name || ''} ${row.pollutant_label}`)}
            onReject={(row) => openAction('reject', [row.id], `${row.station?.name || ''} ${row.pollutant_label}`)}
          />
          <Pagination
            page={queue.page}
            pages={queue.pages}
            total={queue.total}
            pageSize={queue.pageSize}
            onPageChange={queue.setPage}
            onPageSizeChange={queue.setPageSize}
          />
        </div>
      </SectionCard>

      <SectionCard title="审核记录" hint="提交、重新提交、通过、驳回的完整审计轨迹">
        <div className="stack">
          <FilterPanel
            loading={records.loading}
            onSearch={() => records.setFilters(recordDraft)}
            onReset={() => {
              setRecordDraft(RECORD_FILTERS)
              records.setFilters(RECORD_FILTERS)
            }}
          >
            <Field label="动作">
              <Select
                value={recordDraft.action}
                onChange={(event) => setRecordDraft({ ...recordDraft, action: event.target.value })}
                placeholder="全部动作"
                options={ACTION_OPTIONS}
              />
            </Field>
            <Field label="操作人">
              <Input
                value={recordDraft.reviewer}
                onChange={(event) => setRecordDraft({ ...recordDraft, reviewer: event.target.value })}
                placeholder="审核人 / 录入人"
              />
            </Field>
            <Field label="开始日期">
              <Input
                type="date"
                value={recordDraft.date_from}
                onChange={(event) => setRecordDraft({ ...recordDraft, date_from: event.target.value })}
              />
            </Field>
            <Field label="结束日期">
              <Input
                type="date"
                value={recordDraft.date_to}
                onChange={(event) => setRecordDraft({ ...recordDraft, date_to: event.target.value })}
              />
            </Field>
          </FilterPanel>

          {records.error ? <Alert tone="error">{records.error.message}</Alert> : null}

          <ReviewRecordTable rows={records.items} loading={records.loading} />
          <Pagination
            page={records.page}
            pages={records.pages}
            total={records.total}
            pageSize={records.pageSize}
            onPageChange={records.setPage}
            onPageSizeChange={records.setPageSize}
          />
        </div>
      </SectionCard>

      <ReviewActionModal
        target={target}
        busy={busy}
        error={actionError}
        onConfirm={confirmAction}
        onClose={() => setTarget(null)}
      />
    </>
  )
}
