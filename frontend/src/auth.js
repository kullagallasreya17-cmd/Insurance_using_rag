const TOKEN_KEY = "insurance_access_token";
const USER_KEY = "insurance_user";

function readStorage(key) {
  return sessionStorage.getItem(key) || localStorage.getItem(key);
}

export function setSession(token, user, remember = true) {
  if (remember) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } else {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  }
}

export function getToken() {
  return readStorage(TOKEN_KEY);
}

export function getUser() {
  const rawUser = readStorage(USER_KEY);
  return rawUser ? JSON.parse(rawUser) : null;
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}

export function isAuthenticated() {
  return Boolean(getToken());
}
