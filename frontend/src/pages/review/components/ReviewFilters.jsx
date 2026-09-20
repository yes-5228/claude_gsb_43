import { useEffect, useState } from 'react'
import { FilterPanel } from '../../../components/common/Card.jsx'
import { Checkbox, Field, Input, Select } from '../../../components/common/FormField.jsx'
import { usePollutantMeta, useStationOptions } from '../../../hooks/useOptions.js'

const STATUS_OPTIONS = [
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' }
]

export const INITIAL_REVIEW_FILTERS = {
  review_status: 'pending',
  station_id: '',
  pollutant: '',
  recorder: '',
  overdue: '',
  date_from: '',
  date_to: ''
}

export default function ReviewFilters({ value, loading, onSubmit, onReset }) {
  const [draft, setDraft] = useState(value)
  const { data: stationData } = useStationOptions()
  const { data: pollutantData } = usePollutantMeta()

  useEffect(() => {
    setDraft(value)
  }, [value])

  const update = (key) => (event) => setDraft({ ...draft, [key]: event.target.value })

  return (
    <FilterPanel
      loading={loading}
      onSearch={() => onSubmit(draft)}
      onReset={() => {
        setDraft(INITIAL_REVIEW_FILTERS)
        onReset()
      }}
    >
      <Field label="审核状态">
        <Select value={draft.review_status || ''} onChange={update('review_status')} options={STATUS_OPTIONS} />
      </Field>
      <Field label="监测点">
        <Select
          value={draft.station_id || ''}
          onChange={update('station_id')}
          placeholder="全部监测点"
          options={(stationData?.items ?? []).map((item) => ({
            value: String(item.id),
            label: `${item.code} ${item.name}`
          }))}
        />
      </Field>
      <Field label="监测因子">
        <Select
          value={draft.pollutant || ''}
          onChange={update('pollutant')}
          placeholder="全部因子"
          options={(pollutantData?.items ?? []).map((item) => ({ value: item.code, label: item.label }))}
        />
      </Field>
      <Field label="录入人">
        <Input
          placeholder="按录入人筛选"
          value={draft.recorder || ''}
          onChange={update('recorder')}
          onKeyDown={(event) => event.key === 'Enter' && onSubmit(draft)}
        />
      </Field>
      <Field label="开始日期">
        <Input type="date" value={draft.date_from || ''} onChange={update('date_from')} />
      </Field>
      <Field label="结束日期">
        <Input type="date" value={draft.date_to || ''} onChange={update('date_to')} />
      </Field>
      <Field label="超时筛选">
        <div style={{ paddingTop: 8 }}>
          <Checkbox
            label="仅看超时未处理"
            checked={draft.overdue === 'true'}
            onChange={(event) =>
              setDraft({ ...draft, overdue: event.target.checked ? 'true' : '' })
            }
          />
        </div>
      </Field>
    </FilterPanel>
  )
}
