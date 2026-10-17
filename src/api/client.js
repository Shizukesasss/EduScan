const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api';

export const auth = {
  token: () => localStorage.getItem('eduscan.token'),
  role: () => localStorage.getItem('userRole'),
  name: () => localStorage.getItem('eduscan.fullName'),
  mustChangePassword: () => localStorage.getItem('eduscan.mustChangePassword') === 'true',
  save(result) {
    localStorage.setItem('eduscan.token', result.access_token);
    localStorage.setItem('userRole', result.role);
    localStorage.setItem('eduscan.fullName', result.full_name);
    localStorage.setItem('eduscan.mustChangePassword', String(Boolean(result.must_change_password)));
  },
  passwordChanged() { localStorage.setItem('eduscan.mustChangePassword', 'false'); },
  clear() {
    localStorage.removeItem('eduscan.token');
    localStorage.removeItem('userRole');
    localStorage.removeItem('eduscan.fullName');
    localStorage.removeItem('eduscan.mustChangePassword');
  },
};

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = auth.token();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (error) {
    if (error.name === 'TimeoutError') throw new Error('EduScan backend took too long to respond. Check the API connection and try again.');
    if (error.name === 'AbortError') throw new Error('EduScan request was cancelled.');
    throw new Error('EduScan backend is not reachable. Start the API server and try again.');
  }
  if (response.status === 401) auth.clear();
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    let details;
    try {
      const payload = await response.json();
      details = payload.detail;
      detail = typeof payload.detail === 'string' ? payload.detail : payload.detail?.message || JSON.stringify(payload.detail);
    } catch { /* preserve status message */ }
    const error = new Error(detail);
    error.code = details?.code;
    error.details = details;
    throw error;
  }
  if (response.status === 204) return null;
  return response.headers.get('content-type')?.includes('application/json') ? response.json() : response;
}

export const api = {
  get: (path, options = {}) => request(path, options),
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: body instanceof FormData ? body : JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path, body) => request(path, { method: 'DELETE', body: body === undefined ? undefined : JSON.stringify(body) }),
  download: async (path, fallbackName) => {
    const response = await request(path);
    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') || '';
    const filename = disposition.match(/filename="?([^";]+)"?/)?.[1] || fallbackName;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  },
  printHtml: async (path) => {
    const target = window.open('about:blank', '_blank');
    if (!target) throw new Error('Allow pop-ups for EduScan to open the printable report.');
    target.opener = null;
    try {
      target.document.body.textContent = 'Preparing printable EduScan report…';
      const response = await request(path);
      const html = await response.text();
      const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
      target.location.href = url;
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) { target.close(); throw error; }
  },
};

export const enrollmentCapture = { frames: 20, interval: 220, quality: 0.92, maxDimension: 960 };

export function captureVideoFrame(video, quality = 0.9, maxDimension = 0) {
  if (!video?.videoWidth) throw new Error('Camera is not ready');
  const canvas = document.createElement('canvas');
  const scale = maxDimension > 0 ? Math.min(1, maxDimension / Math.max(video.videoWidth, video.videoHeight)) : 1;
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => canvas.toBlob(
    (blob) => blob ? resolve(blob) : reject(new Error('Camera frame could not be captured')),
    'image/jpeg', quality,
  ));
}

export function localDate(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

export function displayTime(value) {
  if (!value) return '—';
  const [hours, minutes] = value.split(':').map(Number);
  const date = new Date();
  date.setHours(hours, minutes, 0, 0);
  return date.toLocaleTimeString('en-PH', { hour: 'numeric', minute: '2-digit' });
}
