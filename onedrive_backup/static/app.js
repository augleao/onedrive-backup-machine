async function status() {
  const r = await fetch('/api/status');
  const j = await r.json();
  document.getElementById('status').innerText = j.authenticated ? 'Authenticated' : 'Not authenticated';
}

async function authStatusPoll() {
  const r = await fetch('/api/auth/device/status');
  const j = await r.json();

  const box = document.getElementById('authbox');
  const msg = document.getElementById('auth_message');
  if (j.verification_uri && j.user_code) {
    box.style.display = 'block';
    const link = document.getElementById('auth_url');
    link.href = j.verification_uri;
    link.innerText = j.verification_uri;
    document.getElementById('auth_code').innerText = j.user_code;
  }

  if (j.status === 'authenticated') {
    msg.innerText = 'Conta vinculada com sucesso.';
    await status();
    return;
  }
  if (j.status === 'error') {
    msg.innerText = 'Falha na autenticacao: ' + (j.message || 'erro desconhecido');
    return;
  }
  if (j.status === 'pending') {
    msg.innerText = j.message || 'Aguardando conclusao do login...';
    setTimeout(authStatusPoll, 3000);
  }
}

document.getElementById('login').addEventListener('click', async () => {
  const r = await fetch('/api/auth/device/start', { method: 'POST' });
  const j = await r.json();

  const box = document.getElementById('authbox');
  box.style.display = 'block';
  if (j.verification_uri && j.user_code) {
    const link = document.getElementById('auth_url');
    link.href = j.verification_uri;
    link.innerText = j.verification_uri;
    document.getElementById('auth_code').innerText = j.user_code;
  }
  document.getElementById('auth_message').innerText = j.message || 'Aguardando conclusao do login...';
  setTimeout(authStatusPoll, 3000);
});

document.getElementById('backup').addEventListener('click', async () => {
  const r = await fetch('/api/backup', { method: 'POST' });
  const j = await r.json();
  alert('Backup started: ' + JSON.stringify(j));
});

status();
