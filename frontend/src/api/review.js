import http, { toParams } from './client.js'

export const listReviewMeasurements = (params) => http.get('/review', { params: toParams(params) })
export const reviewSummary = () => http.get('/review/summary')
export const approveMeasurements = (payload) => http.post('/review/approve', payload)
export const rejectMeasurements = (payload) => http.post('/review/reject', payload)
export const listReviewLogs = (params) => http.get('/review/logs', { params: toParams(params) })
