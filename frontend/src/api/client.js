export async function api(endpoint, options = {}) {
  let url = endpoint;
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    if (url === '/me' || url === '/api/me') {
      url = '/api/auth/me';
    } else if (!url.startsWith('/api/') && url !== '/api') {
      url = '/api' + (url.startsWith('/') ? url : '/' + url);
    }
  }

  const token = localStorage.getItem('elh_token') || sessionStorage.getItem('token') || sessionStorage.token || '';
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {})
  };

  const config = {
    ...options,
    headers
  };

  const response = await fetch(url, config);
  const isAuthEndpoint = url.includes('/auth/login');

  if (response.status === 401 && !isAuthEndpoint) {
    localStorage.removeItem('elh_token');
    sessionStorage.removeItem('token');
    delete sessionStorage.token;
    if (window.logout) {
      window.logout();
    } else {
      window.location.hash = '#login';
    }
    throw new Error('Session expired. Please log in again.');
  }

  if (!response.ok) {
    let errMessage = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const data = await response.json();
      if (data.detail) errMessage = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      else if (data.message) errMessage = data.message;
    } catch {}
    throw new Error(errMessage);
  }

  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

