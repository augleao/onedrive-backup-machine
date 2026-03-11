async function status() {
  const r = await fetch('/api/status');
  const j = await r.json();
  document.getElementById('status').innerText = j.authenticated ? 'Authenticated' : 'Not authenticated';
}
document.getElementById('login').addEventListener('click', () => { window.location = '/auth/login'; });
document.getElementById('backup').addEventListener('click', async () => {
  const r = await fetch('/api/backup', { method: 'POST' });
  const j = await r.json();
  alert('Backup started: ' + JSON.stringify(j));
});
status();
