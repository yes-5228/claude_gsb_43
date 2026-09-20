import { useEffect, useState } from 'react'
import { updateMeasurement } from '../../../api/measurements.js'
import Modal from '../../../components/common/Modal.jsx'
import { Field, Input } from '../../../components/common/FormField.jsx'
import { Alert } from '../../../components/common/Feedback.jsx'
import { useToast } from '../../../components/common/ToastProvider.jsx'
import { formatDateTime, formatNumber } from '../../../utils/format.js'

/** 录入人修改被驳回的数据并重新送审。 */
export default function EditMeasurementModal({ measurement, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState({ value: '', remark: '', recorder: '' })
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (measurement) {
      setForm({
        value: measurement.value ?? '',
        remark: measurement.remark || '',
        recorder: measurement.recorder || ''
      })
      setErrors({})
      setMessage(null)
    }
  }, [measurement])

  if (!measurement) return null

  const submit = async () => {
    const number = Number(form.value)
    if (form.value === '' || Number.isNaN(number)) {
      setErrors({ value: '监测值必须是数字' })
      return
    }
    if (number < 0) {
      setErrors({ value: '监测值不能为负数' })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      await updateMeasurement(measurement.id, {
        value: number,
        remark: form.remark || null,
        recorder: form.recorder || null
      })
      toast.success('已重新提交, 等待审核')
      onSaved?.()
    } catch (err) {
      setErrors(err.fields || {})
      setMessage(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      title={`修改重报 · ${measurement.station?.name || ''}`}
      onClose={busy ? undefined : onClose}
      closeOnOverlay={!busy}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? '提交中...' : '修正并重新送审'}
          </button>
        </>
      }
    >
      <div className="stack">
        {measurement.review_reason ? (
          <Alert tone="error">驳回原因: {measurement.review_reason}</Alert>
        ) : null}
        <dl className="kv">
          <dt>监测因子</dt>
          <dd>
            {measurement.pollutant_label} ({measurement.unit || '-'})
          </dd>
          <dt>监测时间</dt>
          <dd>
            {formatDateTime(measurement.measured_at)} · {measurement.period_label}
          </dd>
          <dt>当前监测值</dt>
          <dd>{formatNumber(measurement.value)}</dd>
        </dl>

        {message ? <Alert tone="error">{message}</Alert> : null}

        <div className="form-grid">
          <Field label="修正后监测值" required error={errors.value}>
            <Input
              type="number"
              step="0.01"
              min="0"
              value={form.value}
              invalid={Boolean(errors.value)}
              onChange={(event) => {
                setForm({ ...form, value: event.target.value })
                setErrors({})
              }}
            />
          </Field>
          <Field label="录入人" error={errors.recorder}>
            <Input
              value={form.recorder}
              onChange={(event) => setForm({ ...form, recorder: event.target.value })}
            />
          </Field>
        </div>
        <Field label="备注" error={errors.remark} hint="说明修正依据, 便于审核人复核">
          <Input
            value={form.remark}
            placeholder="如: 已按原始记录修正小数点错位"
            onChange={(event) => setForm({ ...form, remark: event.target.value })}
          />
        </Field>
      </div>
    </Modal>
  )
}
