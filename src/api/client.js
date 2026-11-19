const browserHost = globalThis.window?.location?.hostname;
const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(browserHost);
const API_BASE = import.meta.env.VITE_API_URL || (loopback ? `http://${browserHost}:8000/api` : '/api');
const pendingGets = new Map();
const sessionListeners = new Set();
let session = { status: 'loading', user: null };
let sessionRevision = 0;
let sessionChannel;

function readableValidationErrors(errors) {
  return errors.map(({ loc = [], msg = 'Check this field.', type }) => {
    const field = loc.at(-1);
    const passwordField = field === 'password' || field === 'new_password';
    if (passwordField) {
      if (type === 'missing') return field === 'password' ? 'Enter a temporary password.' : 'Enter a new password.';
      if (/at least 12 characters/i.test(msg)) return 'Use at least 12 characters.';
      if (/uppercase and lowercase/i.test(msg)) return 'Include at least one capital letter and one small letter.';
      if (/number and a symbol/i.test(msg)) return 'Include at least one number and one symbol, such as ! or #.';
    }
    return msg.replace(/^Value error,\s*/i, '');
  }).filter(Boolean).join(' ');
}

function setSession(next) {
  session = next;
  sessionRevision++;
  pendingGets.clear();
  sessionListeners.forEach(listener => listener());
}

async function restoreSession() {
  setSession({ status: 'loading', user: null });
  const revision = sessionRevision;
  try {
    const user = await request('/auth/me', { signal: AbortSignal.timeout(15000) });
    if (revision === sessionRevision) setSession({ status: 'ready', user });
  } catch (error) {
    if (revision === sessionRevision) {
      setSession(error.status === 401
        ? { status: 'ready', user: null }
        : { status: 'error', user: null, message: error.message });
    }
  }
  return session.user;
}

export const auth = {
  snapshot: () => session,
  subscribe(listener) {
    sessionListeners.add(listener);
    return () => sessionListeners.delete(listener);
  },
  signedIn: () => Boolean(session.user),
  role: () => session.user?.role,
  name: () => session.user?.full_name,
  displayName: () => session.user?.display_name || session.user?.full_name,
  updateProfile(profile) {
    if (session.user?.id !== profile.id) return;
    setSession({ ...session, user: { ...session.user, display_name: profile.display_name,
      profile_photo_revision: profile.profile_photo_revision } });
  },
  provider: () => session.user?.auth_provider || 'password',
  mustChangePassword: () => Boolean(session.user?.must_change_password),
  restore: restoreSession,
  start() {
    try {
      for (const key of ['eduscan.token', 'userRole', 'eduscan.fullName', 'eduscan.authProvider', 'eduscan.mustChangePassword']) {
        globalThis.localStorage?.removeItem(key);
      }
    } catch { /* Session restoration works without browser storage. */ }
    if (globalThis.window?.BroadcastChannel && !sessionChannel) {
      sessionChannel = new window.BroadcastChannel('eduscan.session');
      sessionChannel.addEventListener('message', restoreSession);
    }
    return restoreSession();
  },
  async confirmSignIn() {
    const user = await restoreSession();
    if (!user) throw new Error(session.message || 'EduScan could not restore the session. Use the authorized website and allow its session cookie.');
    sessionChannel?.postMessage('changed');
    return user;
  },
  clear() {
    setSession({ status: 'ready', user: null });
    globalThis.window?.google?.accounts?.id?.disableAutoSelect();
    sessionChannel?.postMessage('changed');
  },
  async logout() {
    await request('/auth/logout', { method: 'POST', signal: AbortSignal.timeout(15000) });
    auth.clear();
  },
};

async function request(path, options = {}) {
  const mutating = !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase());
  const revision = sessionRevision;
  if (mutating) pendingGets.clear();
  const headers = new Headers(options.headers || {});
  headers.set('X-EduScan-Request', '1');
  if (path !== '/auth/me' && session.user?.session_context) {
    headers.set('X-EduScan-Session-Context', session.user.session_context);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' });
  } catch (error) {
    if (error.name === 'TimeoutError') throw new Error('EduScan backend took too long to respond. Check the API connection and try again.');
    if (error.name === 'AbortError') throw new Error('EduScan request was cancelled.');
    throw new Error('EduScan backend is not reachable. Start the API server and try again.');
  } finally {
    if (mutating) pendingGets.clear();
  }
  if (response.status === 401 && revision === sessionRevision &&
      (!path.startsWith('/auth/') || path === '/auth/change-password')) {
    setSession({ status: 'ready', user: null });
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    let details;
    try {
      const payload = await response.json();
      details = payload.detail;
      detail = typeof payload.detail === 'string' ? payload.detail
        : Array.isArray(payload.detail) ? readableValidationErrors(payload.detail)
          : payload.detail?.message || 'Check the information you entered and try again.';
    } catch { /* preserve status message */ }
    const error = new Error(detail);
    error.status = response.status;
    if (response.status === 429) {
      const seconds = Number(response.headers.get('Retry-After'));
      error.retryAfter = Number.isFinite(seconds) && seconds > 0 ? seconds : 1;
    }
    error.code = details?.code;
    error.details = details;
    if (error.code === 'session_changed' && revision === sessionRevision) void restoreSession();
    throw error;
  }
  if (response.status === 204) return null;
  return response.headers.get('content-type')?.includes('application/json') ? response.json() : response;
}

function get(path, options = {}) {
  // Share only simultaneous default reads. Refreshes still fetch fresh data,
  // and callers with their own headers/signals retain independent requests.
  if (Object.keys(options).length) return request(path, options);
  const key = JSON.stringify([sessionRevision, path]);
  if (!pendingGets.has(key)) {
    const pending = request(path, options).finally(() => {
      if (pendingGets.get(key) === pending) pendingGets.delete(key);
    });
    pendingGets.set(key, pending);
  }
  return pendingGets.get(key);
}

export const api = {
  get,
  post: (path, body, options = {}) => request(path, { ...options, method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: body instanceof FormData ? body : JSON.stringify(body) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: body instanceof FormData ? body : JSON.stringify(body) }),
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
  openDocument: async (path) => {
    // Open synchronously from the click, before the authenticated request can delay it.
    const target = window.open('about:blank', '_blank');
    if (!target) throw new Error('Allow pop-ups for EduScan to preview this report.');
    target.opener = null;
    try {
      target.document.body.textContent = 'Preparing EduScan report preview…';
      const response = await request(path);
      const type = response.headers.get('content-type') || '';
      if (!type.includes('application/pdf') && !type.includes('text/html')) throw new Error('The report format is not supported.');
      const url = URL.createObjectURL(await response.blob());
      if (target.closed) { URL.revokeObjectURL(url); return; }
      target.location.href = url;
      const cleanup = () => { URL.revokeObjectURL(url); window.clearInterval(timer); window.removeEventListener('pagehide', cleanup); };
      const timer = window.setInterval(() => { if (target.closed) cleanup(); }, 10000);
      window.addEventListener('pagehide', cleanup, { once: true });
    } catch (error) { target.close(); throw error; }
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
