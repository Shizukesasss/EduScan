const loads = new WeakMap();

export function loadGoogleIdentity(browser = window, { timeoutMs = 15000 } = {}) {
  if (browser.google?.accounts?.id) return Promise.resolve(browser.google.accounts.id);
  if (loads.has(browser)) return loads.get(browser);
  const pending = new Promise((resolve, reject) => {
    const script = browser.document.createElement('script');
    const fail = () => {
      browser.clearTimeout(timer);
      script.remove();
      reject(new Error('Google sign-in could not load. Check your internet connection and try again.'));
    };
    const timer = browser.setTimeout(fail, timeoutMs);
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = () => {
      if (!browser.google?.accounts?.id) return fail();
      browser.clearTimeout(timer);
      resolve(browser.google.accounts.id);
    };
    script.onerror = fail;
    browser.document.head.appendChild(script);
  });
  loads.set(browser, pending);
  pending.catch(() => loads.delete(browser));
  return pending;
}

export function renderGoogleSignIn(api, element, clientId, onCredential, onError) {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(32));
  const nonce = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  api.initialize({
    client_id: clientId, hd: 'deped.gov.ph', nonce, auto_select: false,
    callback: (response) => {
      if (!response.credential) return onError(new Error('Google did not return an account. Please try again.'));
      onCredential({ credential: response.credential, nonce });
    },
  });
  api.renderButton(element, { type: 'standard', theme: 'outline', size: 'large', text: 'signin_with',
    width: Math.min(400, Math.max(200, element.clientWidth || 280)) });
}

export function workspaceFor(role) {
  if (role === 'teacher') return '/teacher';
  if (role === 'scanner') return '/scanner';
  if (role === 'school_head') return '/dashboard/grading';
  if (role === 'records_officer') return '/dashboard/reports';
  if (role === 'ict' || role === 'privacy_officer') return '/dashboard/administration';
  return '/dashboard';
}
