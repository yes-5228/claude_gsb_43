import { Fragment, useEffect, useState } from 'react'
import Modal from '../../../components/common/Modal.jsx'
import { Field, Input, Textarea } from '../../../components/common/FormField.jsx'
import { Alert } from '../../../components/common/Feedback.jsx'

/**
 * 驳回弹窗: ids 为待驳回的记录 id 列表, 驳回原因必填。
 * rows 用于在弹窗中展示将退回给录入人的数据摘要。
 */
export default function RejectModal({ target, reviewer, busy, onCancel, onConfirm }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    if (target) {
      setReason('')
      setError(null)
    }
  }, [target])

  if (!target) return null
  const { ids, rows } = target

  const submit = () => {
    if (!reason.trim()) {
      setError('驳回时必须填写原因')
      return
    }
    onConfirm({ ids, reason: reason.trim() })
  }

  return (
    <Modal
      open
      title={`驳回监测数据 (${ids.length} 条)`}
      onClose={busy ? undefined : onCancel}
      closeOnOverlay={!busy}
      footer={
        <>
          <button type="button" className="btn" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button type="button" className="btn btn-danger" onClick={submit} disabled={busy}>
            {busy ? '提交中...' : '确认驳回'}
          </button>
        </>
      }
    >
      <div className="stack">
        <Alert tone="warning">
          驳回后数据将退回录入人修改, 修正后需重新送审; 驳回原因会展示给录入人。
        </Alert>
        {rows?.length ? (
          <dl className="kv">
            {rows.slice(0, 3).map((row) => (
              <Fragment key={row.id}>
                <dt>{row.station?.name || '-'}</dt>
                <dd>
                  {row.pollutant_label} · {row.value} {row.unit || ''} · 录入人 {row.recorder || '-'}
                </dd>
              </Fragment>
            ))}
            {rows.length > 3 ? (
              <>
                <dt>其余</dt>
                <dd>… 共 {rows.length} 条</dd>
              </>
            ) : null}
          </dl>
        ) : null}
        <Field label="审核人">
          <Input value={reviewer || ''} readOnly disabled placeholder="在列表上方填写" />
        </Field>
        <Field label="驳回原因" required error={error}>
          <Textarea
            value={reason}
            invalid={Boolean(error)}
            placeholder="如: 监测值与原始记录不符, 请核对仪器状态后重新录入"
            onChange={(event) => {
              setReason(event.target.value)
              setError(null)
            }}
          />
        </Field>
      </div>
    </Modal>
  )
}
