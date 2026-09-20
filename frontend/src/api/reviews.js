import http, { toParams } from './client.js'

export const listPendingReviews = (params) =>
  http.get('/reviews/pending', { params: toParams(params) })
export const reviewSummary = () => http.get('/reviews/summary')
export const listReviewRecords = (params) =>
  http.get('/reviews/records', { params: toParams(params) })
export const reviewMeasurement = (id, payload) => http.post(`/reviews/${id}`, payload)
export const batchReview = (payload) => http.post('/reviews/batch', payload)
