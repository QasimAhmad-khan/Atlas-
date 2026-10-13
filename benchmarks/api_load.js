import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || '10s',
  summaryTrendStats: ['avg', 'med', 'p(50)', 'p(95)', 'p(99)', 'max'],
  thresholds: { http_req_failed: ['rate<0.01'], checks: ['rate>0.99'] },
};

export default function () {
  for (const path of ['/pages?limit=20', '/stats']) {
    const result = http.get(`${__ENV.BASE_URL}${path}`, {
      headers: { Authorization: `Bearer ${__ENV.API_KEY}` },
    });
    check(result, { 'response is 200': (r) => r.status === 200 });
  }
}

export function handleSummary(data) {
  return { [__ENV.OUTPUT || 'api-load.json']: JSON.stringify(data, null, 2) };
}
