import { useEffect, useState } from 'react'
import Modal from '../../../components/common/Modal.jsx'
import { Field, Input, Textarea } from '../../../components/common/FormField.jsx'
import { Alert } from '../../../components/common/Feedback.jsx'

/**
 * 审核动作弹窗: 通过 (意见选填) / 驳回 (必须填写原因, 数据退回录入人修改)。
 * target = { action: 'approve' | 'reject', ids: number[], label: string }
 */
export default function ReviewActionModal({ target, busy, error, onConfirm, onClose }) {
  const [reviewer, setReviewer] = useState('')
  const [reason, setReason] = useState('')
  const [localError, setLocalError] = useState(null)

  useEffect(() => {
    if (target) {
      setReviewer('')
      setReason('')
      setLocalError(null)
    }
  }, [target])

  if (!target) return null
  const isReject = target.action === 'reject'

  const submit = () => {
    if (isReject && !reason.trim()) {
      setLocalError('驳回时必须填写驳回原因, 便于录入人修改')
      return
    }
    setLocalError(null)
    onConfirm({
      action: target.action,
      ids: target.ids,
      reviewer: reviewer.trim() || null,
      reason: reason.trim() || null
    })
  }

  return (
    <Modal
      open={Boolean(target)}
      title={isReject ? '驳回监测数据' : '审核通过确认'}
      onClose={busy ? undefined : onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className={`btn ${isReject ? 'btn-danger' : 'btn-primary'}`}
            onClick={submit}
            disabled={busy}
          >
            {busy ? '提交中...' : isReject ? '确认驳回' : '确认通过'}
          </button>
        </>
      }
    >
      <div className="stack">
        <div>
          将对 <span className="strong">{target.label}</span> 执行
          <span className={`strong ${isReject ? 'danger-text' : 'success-text'}`}>
            {isReject ? ' 驳回 ' : ' 审核通过 '}
          </span>
          操作, 共 {target.ids.length} 条记录。
        </div>
        <Alert tone={isReject ? 'warning' : 'info'}>
          {isReject
            ? '驳回后数据将退回录入人修改, 重新提交后需再次审核。'
            : '通过后数据纳入统计与超标判定口径, 预判超标的数据将生成待标注超标记录。'}
        </Alert>
        {localError ? <Alert tone="error">{localError}</Alert> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Field label="审核人">
          <Input
            value={reviewer}
            onChange={(event) => setReviewer(event.target.value)}
            placeholder="如: 刘洋"
          />
        </Field>
        <Field
          label={isReject ? '驳回原因' : '审核意见'}
          required={isReject}
          hint={isReject ? '必填, 将随数据一并退回给录入人' : '选填'}
        >
          <Textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            invalid={Boolean(localError)}
            placeholder={isReject ? '如: 数值与原始记录不符, 请核对后重新录入' : '如: 周期性批量复核通过'}
          />
        </Field>
      </div>
    </Modal>
  )
}
