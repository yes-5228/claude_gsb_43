import { useCallback, useState } from 'react'
import { approveMeasurements, listReviewLogs, listReviewMeasurements, rejectMeasurements } from '../../api/review.js'
import Pagination from '../../components/common/Pagination.jsx'
import { SectionCard } from '../../components/common/Card.jsx'
import { Alert } from '../../components/common/Feedback.jsx'
import Tag from '../../components/common/Tag.jsx'
import { useToast } from '../../components/common/ToastProvider.jsx'
import { useListQuery } from '../../hooks/useListQuery.js'
import EditMeasurementModal from './components/EditMeasurementModal.jsx'
import RejectModal from './components/RejectModal.jsx'
import ReviewFilters, { INITIAL_REVIEW_FILTERS } from './components/ReviewFilters.jsx'
import ReviewLogTable from './components/ReviewLogTable.jsx'
import ReviewSummaryCards from './components/ReviewSummaryCards.jsx'
import ReviewTable from './components/ReviewTable.jsx'

export default function ReviewPage() {
  const toast = useToast()
  const query = useListQuery(listReviewMeasurements, INITIAL_REVIEW_FILTERS)
  const logs = useListQuery(listReviewLogs, {}, { pageSize: 10 })
  const [selected, setSelected] = useState([])
  const [reviewer, setReviewer] = useState('')
  const [rejectTarget, setRejectTarget] = useState(null)
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(false)

  const summary = query.summary
  const isPendingView = !query.filters.review_status || query.filters.review_status === 'pending'

  const reloadAll = useCallback(() => {
    query.reload()
    logs.reload()
  }, [query, logs])

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

  const doApprove = async (ids) => {
    if (!ids.length) {
      toast.warning('请先勾选需要审核通过的数据')
      return
    }
    setBusy(true)
    try {
      const result = await approveMeasurements({ ids, reviewer: reviewer || null })
      toast.success(`已通过 ${result.approved} 条数据, 纳入统计与超标判定口径`)
      if (result.skipped?.length) toast.warning(`有 ${result.skipped.length} 条已被处理, 自动跳过`)
      setSelected([])
      reloadAll()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setBusy(false)
    }
  }

  const doReject = async ({ ids, reason }) => {
    setBusy(true)
    try {
      const result = await rejectMeasurements({ ids, reason, reviewer: reviewer || null })
      toast.success(`已驳回 ${result.rejected} 条数据, 退回录入人修改`)
      if (result.skipped?.length) toast.warning(`有 ${result.skipped.length} 条已被处理, 自动跳过`)
      setRejectTarget(null)
      setSelected([])
      reloadAll()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <ReviewSummaryCards summary={summary} />

      {summary?.overdue > 0 ? (
        <Alert tone="warning">
          ⏰ 有 {summary.overdue} 条数据提交超过 {summary.overdue_hours} 小时仍未审核,
          最早提交于 {summary.oldest_pending_submitted_at?.replace('T', ' ').slice(0, 16) || '-'},
          请优先处理, 避免影响统计口径的及时性。
        </Alert>
      ) : null}

      <ReviewFilters
        value={query.filters}
        loading={query.loading}
        onSubmit={(next) => {
          setSelected([])
          query.setFilters(next)
        }}
        onReset={() => {
          setSelected([])
          query.setFilters(INITIAL_REVIEW_FILTERS)
        }}
      />

      {query.error ? <Alert tone="error">{query.error.message}</Alert> : null}

      <SectionCard
        title="数据审核工作台"
        hint="审核通过后数据才纳入统计与超标判定口径; 驳回必须填写原因, 记录将退回录入人修改"
        actions={
          <>
            <Tag tone="warning">待审核 {summary?.pending ?? 0} 条</Tag>
            <button type="button" className="btn btn-sm" onClick={reloadAll} disabled={query.loading}>
              刷新
            </button>
          </>
        }
      >
        <div className="stack">
          {isPendingView ? (
            <div className="card" style={{ boxShadow: 'none' }}>
              <div className="card-body tight">
                <div className="inline">
                  <span className="field-label">批量审核</span>
                  <input
                    className="input"
                    style={{ width: 140 }}
                    placeholder="审核人"
                    value={reviewer}
                    onChange={(event) => setReviewer(event.target.value)}
                  />
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => doApprove(selected)}
                    disabled={busy || selected.length === 0}
                  >
                    批量通过
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={() =>
                      setRejectTarget({
                        ids: selected,
                        rows: query.items.filter((row) => selected.includes(row.id))
                      })
                    }
                    disabled={busy || selected.length === 0}
                  >
                    批量驳回
                  </button>
                  <Tag tone="primary">已选 {selected.length} 条</Tag>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setSelected([])}
                    disabled={selected.length === 0}
                  >
                    清空选择
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          <ReviewTable
            rows={query.items}
            loading={query.loading}
            overdueHours={summary?.overdue_hours ?? 24}
            selectable={isPendingView}
            selectedIds={selected}
            onToggleRow={toggleRow}
            onToggleAll={toggleAll}
            onApprove={(row) => doApprove([row.id])}
            onReject={(row) => setRejectTarget({ ids: [row.id], rows: [row] })}
            onEdit={(row) => setEditing(row)}
          />
          <Pagination
            page={query.page}
            pages={query.pages}
            total={query.total}
            pageSize={query.pageSize}
            onPageChange={query.setPage}
            onPageSizeChange={query.setPageSize}
          />
        </div>
      </SectionCard>

      <SectionCard
        title="审核记录"
        hint="提交、通过、驳回、修改重报全程留痕, 按时间倒序"
        actions={
          <button type="button" className="btn btn-sm" onClick={logs.reload} disabled={logs.loading}>
            刷新
          </button>
        }
      >
        <ReviewLogTable rows={logs.items} loading={logs.loading} />
        <Pagination
          page={logs.page}
          pages={logs.pages}
          total={logs.total}
          pageSize={logs.pageSize}
          onPageChange={logs.setPage}
          onPageSizeChange={logs.setPageSize}
        />
      </SectionCard>

      <RejectModal
        target={rejectTarget}
        reviewer={reviewer}
        busy={busy}
        onCancel={() => setRejectTarget(null)}
        onConfirm={doReject}
      />
      <EditMeasurementModal
        measurement={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          reloadAll()
        }}
      />
    </>
  )
}
