const state = {
  tasks: [],
  jobs: [],
  selectedTaskId: null,
  wizardMode: 'create',
  editingTaskId: null,
  wizardStep: 1,
  selectedSources: new Map(),
  treeStack: [],
  treeCurrent: { id: null, path: '/' },
};

function qs(id) {
  return document.getElementById(id);
}

async function readJsonOrThrow(response) {
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_e) {
    throw new Error(`Invalid server response (HTTP ${response.status}): ${text.slice(0, 180)}`);
  }
  if (!response.ok) {
    throw new Error(data.message || data.error || `HTTP ${response.status}`);
  }
  return data;
}

function setStatus(text) {
  qs('status').innerText = text;
}

function setLoginEnabled(enabled) {
  qs('login').disabled = !enabled;
}

function formatDate(value) {
  if (!value) {
    return '-';
  }
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) {
    return value;
  }
  return dt.toLocaleString();
}

function formatSchedule(task) {
  const schedule = task.schedule || {};
  const time = schedule.time || '02:00';
  if (schedule.type === 'daily') {
    return `Daily @ ${time}`;
  }
  if (schedule.type === 'weekly') {
    const labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    return `Weekly ${labels[schedule.weekday || 0]} @ ${time}`;
  }
  return `Monthly day ${schedule.day || 1} @ ${time}`;
}

function selectedTask() {
  return state.tasks.find((t) => t.id === state.selectedTaskId) || null;
}

function renderTasks() {
  const tbody = qs('tasks_tbody');
  tbody.innerHTML = '';
  if (!state.tasks.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">No tasks created yet.</td></tr>';
    return;
  }

  state.tasks.forEach((task) => {
    const tr = document.createElement('tr');
    if (task.id === state.selectedTaskId) {
      tr.classList.add('selected');
    }
    tr.innerHTML = `
      <td>${task.name}</td>
      <td>${task.strategy?.mode || 'full'}</td>
      <td>${formatSchedule(task)}</td>
      <td>${formatDate(task.state?.next_run_at)}</td>
      <td>${task.state?.last_status || 'idle'}</td>
    `;
    tr.addEventListener('click', () => {
      state.selectedTaskId = task.id;
      renderTasks();
    });
    tbody.appendChild(tr);
  });
}

function renderJobs() {
  const tbody = qs('jobs_tbody');
  tbody.innerHTML = '';
  if (!state.jobs.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">No jobs yet.</td></tr>';
    return;
  }

  state.jobs.forEach((job) => {
    const tr = document.createElement('tr');
    const summary = job.summary || {};
    const summaryText = `Downloaded: ${summary.downloaded || 0}, Skipped: ${summary.skipped || 0}, Errors: ${summary.errors || 0}`;
    tr.innerHTML = `
      <td>${job.task_name || job.task_id || '-'}</td>
      <td><span class="job-status job-${job.status || 'queued'}">${job.status || 'queued'}</span></td>
      <td>${job.mode || '-'}</td>
      <td>${formatDate(job.started_at)}</td>
      <td>${summaryText}</td>
    `;
    tbody.appendChild(tr);
  });
}

function updateModeFields() {
  const mode = qs('backup_mode').value;
  qs('incremental_limit_wrap').style.display = mode === 'incremental' ? 'block' : 'none';
}

function updateScheduleFields() {
  const type = qs('schedule_type').value;
  qs('weekly_wrap').style.display = type === 'weekly' ? 'block' : 'none';
  qs('monthly_wrap').style.display = type === 'monthly' ? 'block' : 'none';
}

function updateSelectedCount() {
  qs('selected_count').innerText = String(state.selectedSources.size);
}

function setStep(step) {
  state.wizardStep = step;
  [1, 2, 3].forEach((s) => {
    qs(`step_${s}`).classList.toggle('active', s === step);
    qs(`badge_step_${s}`).classList.toggle('active', s === step);
  });
  qs('wizard_prev').style.visibility = step === 1 ? 'hidden' : 'visible';
  qs('wizard_next').style.display = step === 3 ? 'none' : 'inline-block';
  qs('wizard_save').style.display = step === 3 ? 'inline-block' : 'none';
}

function resetWizardForm() {
  qs('task_name').value = '';
  qs('backup_mode').value = 'full';
  qs('incremental_limit').value = '3';
  qs('schedule_type').value = 'daily';
  qs('schedule_time').value = '02:00';
  qs('schedule_weekday').value = '0';
  qs('schedule_day').value = '1';
  qs('destination_path').value = '/backup/onedrive';
  qs('task_enabled').checked = true;
  state.selectedSources = new Map();
  state.treeStack = [];
  state.treeCurrent = { id: null, path: '/' };
  updateModeFields();
  updateScheduleFields();
  updateSelectedCount();
}

function openWizard(mode, task = null) {
  state.wizardMode = mode;
  state.editingTaskId = task ? task.id : null;
  qs('wizard_title').innerText = mode === 'edit' ? 'Edit Backup Task' : 'Create Backup Task';
  resetWizardForm();

  if (task) {
    qs('task_name').value = task.name || '';
    qs('backup_mode').value = task.strategy?.mode || 'full';
    qs('incremental_limit').value = String(task.strategy?.incrementals_until_full || 3);
    qs('schedule_type').value = task.schedule?.type || 'daily';
    qs('schedule_time').value = task.schedule?.time || '02:00';
    qs('schedule_weekday').value = String(task.schedule?.weekday || 0);
    qs('schedule_day').value = String(task.schedule?.day || 1);
    qs('destination_path').value = task.destination_path || '/backup/onedrive';
    qs('task_enabled').checked = task.enabled !== false;
    (task.sources || []).forEach((src) => {
      state.selectedSources.set(src.id, {
        id: src.id,
        name: src.name,
        path: src.path,
        is_folder: !!src.is_folder,
        lastModifiedDateTime: src.lastModifiedDateTime || null,
        size: src.size || 0,
      });
    });
    updateModeFields();
    updateScheduleFields();
    updateSelectedCount();
  }

  setStep(1);
  qs('wizard_backdrop').style.display = 'flex';
  loadTree(null, '/');
}

function closeWizard() {
  qs('wizard_backdrop').style.display = 'none';
}

function requireStep(step) {
  if (step === 1) {
    if (!qs('task_name').value.trim()) {
      alert('Task name is required.');
      return false;
    }
    if (!state.selectedSources.size) {
      alert('Select at least one file or folder from OneDrive.');
      return false;
    }
  }
  if (step === 2) {
    if (qs('backup_mode').value === 'incremental' && Number(qs('incremental_limit').value) < 1) {
      alert('Incremental limit must be at least 1.');
      return false;
    }
    if (!qs('schedule_time').value) {
      alert('Schedule time is required.');
      return false;
    }
  }
  if (step === 3) {
    if (!qs('destination_path').value.trim()) {
      alert('Destination path is required.');
      return false;
    }
  }
  return true;
}

async function loadStatus() {
  try {
    const r = await fetch('api/status');
    const j = await readJsonOrThrow(r);
    if (!j.client_id_configured) {
      setStatus('Set client_id in add-on configuration');
      setLoginEnabled(false);
      qs('client_id_help').style.display = 'block';
      qs('authbox').style.display = 'block';
      qs('auth_message').innerText = 'Configure client_id first. Use the Azure button above.';
      return;
    }
    setLoginEnabled(true);
    qs('client_id_help').style.display = 'none';
    setStatus(j.authenticated ? 'Account linked' : 'Account not linked');
  } catch (e) {
    setLoginEnabled(false);
    setStatus(`Error: ${e.message}`);
  }
}

async function authStatusPoll() {
  let j;
  try {
    const r = await fetch('api/auth/device/status');
    j = await readJsonOrThrow(r);
  } catch (e) {
    qs('auth_message').innerText = `Login status error: ${e.message}`;
    return;
  }

  const box = qs('authbox');
  const msg = qs('auth_message');
  if (j.verification_uri && j.user_code) {
    box.style.display = 'block';
    qs('auth_url').href = j.verification_uri;
    qs('auth_url').innerText = j.verification_uri;
    qs('auth_code').innerText = j.user_code;
  }

  if (j.status === 'authenticated') {
    msg.innerText = 'Account linked successfully.';
    await loadStatus();
    return;
  }
  if (j.status === 'error') {
    msg.innerText = 'Login failed: ' + (j.message || 'unknown error');
    return;
  }
  if (j.status === 'pending') {
    msg.innerText = j.message || 'Waiting for login completion...';
    setTimeout(authStatusPoll, 3000);
  }
}

async function startLogin() {
  if (qs('login').disabled) {
    qs('authbox').style.display = 'block';
    qs('auth_message').innerText = 'Configure client_id in add-on settings before linking account.';
    return;
  }

  let j;
  try {
    const r = await fetch('api/auth/device/start', { method: 'POST' });
    j = await readJsonOrThrow(r);
  } catch (e) {
    qs('authbox').style.display = 'block';
    qs('auth_message').innerText = `Failed to start login: ${e.message}`;
    return;
  }

  qs('authbox').style.display = 'block';
  if (j.verification_uri && j.user_code) {
    qs('auth_url').href = j.verification_uri;
    qs('auth_url').innerText = j.verification_uri;
    qs('auth_code').innerText = j.user_code;
  }
  qs('auth_message').innerText = j.message || 'Waiting for login completion...';
  setTimeout(authStatusPoll, 3000);
}

async function logoutAccount() {
  try {
    const r = await fetch('api/logout', { method: 'POST' });
    await readJsonOrThrow(r);
    qs('authbox').style.display = 'none';
    await loadStatus();
  } catch (e) {
    alert('Failed to disconnect: ' + e.message);
  }
}

async function loadSettings() {
  try {
    const r = await fetch('api/settings');
    const j = await readJsonOrThrow(r);
    qs('retention_days').value = String(j.retention_days || 30);
  } catch (e) {
    alert('Failed to load settings: ' + e.message);
  }
}

async function saveSettings() {
  const retentionDays = Number(qs('retention_days').value || '30');
  try {
    const r = await fetch('api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ retention_days: retentionDays }),
    });
    await readJsonOrThrow(r);
    alert('Global retention saved.');
  } catch (e) {
    alert('Failed to save settings: ' + e.message);
  }
}

async function loadTasks() {
  try {
    const r = await fetch('api/tasks');
    const j = await readJsonOrThrow(r);
    state.tasks = j.tasks || [];
    if (!state.tasks.some((t) => t.id === state.selectedTaskId)) {
      state.selectedTaskId = null;
    }
    renderTasks();
  } catch (e) {
    alert('Failed to load tasks: ' + e.message);
  }
}

async function loadJobs() {
  try {
    const r = await fetch('api/jobs');
    const j = await readJsonOrThrow(r);
    state.jobs = j.jobs || [];
    renderJobs();
  } catch (e) {
    console.error('Failed to load jobs', e);
  }
}

function renderTree(items) {
  const container = qs('tree_container');
  container.innerHTML = '';

  if (!items.length) {
    container.innerHTML = '<div class="muted">This folder is empty.</div>';
    return;
  }

  items.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'tree-row';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = state.selectedSources.has(item.id);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) {
        state.selectedSources.set(item.id, {
          id: item.id,
          name: item.name,
          path: item.path || item.name,
          is_folder: !!item.is_folder,
          lastModifiedDateTime: item.lastModifiedDateTime || null,
          size: item.size || 0,
        });
      } else {
        state.selectedSources.delete(item.id);
      }
      updateSelectedCount();
    });

    const label = document.createElement('div');
    label.innerHTML = item.is_folder ? `📁 ${item.name}` : `📄 ${item.name}`;

    const actions = document.createElement('div');
    if (item.is_folder) {
      const open = document.createElement('button');
      open.textContent = 'Open';
      open.className = 'small';
      open.addEventListener('click', () => {
        state.treeStack.push({ ...state.treeCurrent });
        loadTree(item.id, item.path || item.name);
      });
      actions.appendChild(open);
    }

    row.appendChild(checkbox);
    row.appendChild(label);
    row.appendChild(actions);
    container.appendChild(row);
  });
}

async function loadTree(parentId, pathText) {
  const query = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : '';
  qs('tree_path').innerText = pathText || '/';
  try {
    const r = await fetch(`api/onedrive/tree${query}`);
    const j = await readJsonOrThrow(r);
    state.treeCurrent = {
      id: parentId || null,
      path: pathText || '/',
    };
    renderTree(j.items || []);
  } catch (e) {
    qs('tree_container').innerHTML = `<div class="warn">Failed to load folder: ${e.message}</div>`;
  }
}

function taskPayloadFromForm() {
  return {
    name: qs('task_name').value.trim(),
    enabled: qs('task_enabled').checked,
    destination_path: qs('destination_path').value.trim(),
    sources: Array.from(state.selectedSources.values()),
    strategy: {
      mode: qs('backup_mode').value,
      incrementals_until_full: Number(qs('incremental_limit').value || '3'),
    },
    schedule: {
      type: qs('schedule_type').value,
      time: qs('schedule_time').value || '02:00',
      weekday: Number(qs('schedule_weekday').value || '0'),
      day: Number(qs('schedule_day').value || '1'),
    },
  };
}

async function saveTaskFromWizard() {
  if (!requireStep(3)) {
    return;
  }

  const payload = taskPayloadFromForm();
  const isEdit = state.wizardMode === 'edit' && state.editingTaskId;
  const url = isEdit ? `api/tasks/${state.editingTaskId}` : 'api/tasks';
  const method = isEdit ? 'PUT' : 'POST';

  try {
    const r = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    await readJsonOrThrow(r);
    closeWizard();
    await loadTasks();
  } catch (e) {
    alert('Failed to save task: ' + e.message);
  }
}

async function runSelectedTask() {
  const task = selectedTask();
  if (!task) {
    alert('Select one task first.');
    return;
  }
  try {
    const r = await fetch(`api/tasks/${task.id}/run`, { method: 'POST' });
    const j = await readJsonOrThrow(r);
    alert(`Task "${task.name}" started. Job: ${j.job_id}`);
    await loadTasks();
    await loadJobs();
  } catch (e) {
    alert('Failed to run task: ' + e.message);
  }
}

async function deleteSelectedTask() {
  const task = selectedTask();
  if (!task) {
    alert('Select one task first.');
    return;
  }
  if (!window.confirm(`Delete task "${task.name}"?`)) {
    return;
  }
  try {
    const r = await fetch(`api/tasks/${task.id}`, { method: 'DELETE' });
    await readJsonOrThrow(r);
    state.selectedTaskId = null;
    await loadTasks();
  } catch (e) {
    alert('Failed to delete task: ' + e.message);
  }
}

function bindEvents() {
  qs('login').addEventListener('click', startLogin);
  qs('logout').addEventListener('click', logoutAccount);
  qs('save_settings').addEventListener('click', saveSettings);

  qs('new_task').addEventListener('click', () => openWizard('create'));
  qs('edit_task').addEventListener('click', () => {
    const task = selectedTask();
    if (!task) {
      alert('Select one task first.');
      return;
    }
    openWizard('edit', task);
  });
  qs('delete_task').addEventListener('click', deleteSelectedTask);
  qs('run_task').addEventListener('click', runSelectedTask);
  qs('refresh_jobs').addEventListener('click', loadJobs);

  qs('backup_mode').addEventListener('change', updateModeFields);
  qs('schedule_type').addEventListener('change', updateScheduleFields);

  qs('wizard_cancel').addEventListener('click', closeWizard);
  qs('wizard_prev').addEventListener('click', () => {
    if (state.wizardStep > 1) {
      setStep(state.wizardStep - 1);
    }
  });
  qs('wizard_next').addEventListener('click', () => {
    if (!requireStep(state.wizardStep)) {
      return;
    }
    if (state.wizardStep < 3) {
      setStep(state.wizardStep + 1);
    }
  });
  qs('wizard_save').addEventListener('click', saveTaskFromWizard);

  qs('tree_root').addEventListener('click', () => {
    state.treeStack = [];
    loadTree(null, '/');
  });
  qs('tree_up').addEventListener('click', () => {
    if (!state.treeStack.length) {
      loadTree(null, '/');
      return;
    }
    const parent = state.treeStack.pop();
    loadTree(parent.id, parent.path);
  });
  qs('tree_refresh').addEventListener('click', () => {
    loadTree(state.treeCurrent.id, state.treeCurrent.path);
  });
}

async function init() {
  bindEvents();
  await Promise.all([loadStatus(), loadSettings(), loadTasks(), loadJobs()]);
  setInterval(loadJobs, 5000);
}

init();
