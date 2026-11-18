/**
 * Guffy Job Automation Dashboard — Frontend SPA Engine (Ticket 11)
 */

let state = {
  currentTab: 'jobs',
  jobs: [],
  totalJobs: 0,
  limit: 20,
  offset: 0,
  activeJob: null,
  profile: null,
  analytics: null,
  companies: [],
  stagedJobs: []
};

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
  checkApiHealth();
  loadJobs();
  loadAnalytics();
  loadProfile();
});

// --- TOAST NOTIFICATIONS ---
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  const colors = {
    info: 'bg-indigo-600 text-white border-indigo-500',
    success: 'bg-emerald-600 text-white border-emerald-500',
    error: 'bg-rose-600 text-white border-rose-500',
    warning: 'bg-amber-600 text-white border-amber-500',
  };
  const icons = {
    info: 'fa-info-circle',
    success: 'fa-circle-check',
    error: 'fa-circle-exclamation',
    warning: 'fa-triangle-exclamation',
  };

  toast.className = `flex items-center gap-3 px-4 py-2.5 rounded-xl shadow-xl border text-xs pointer-events-auto transition-all duration-300 transform translate-y-2 opacity-0 ${colors[type] || colors.info}`;
  toast.innerHTML = `
    <i class="fa-solid ${icons[type] || icons.info}"></i>
    <span class="font-medium">${message}</span>
  `;

  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  });

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// --- API HEALTH CHECK ---
async function checkApiHealth() {
  const indicator = document.getElementById('api-status-indicator');
  try {
    const res = await fetch('/api/health');
    if (res.ok) {
      indicator.className = 'flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full';
      indicator.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> API Connected';
    } else {
      throw new Error('Unhealthy');
    }
  } catch (err) {
    indicator.className = 'flex items-center gap-2 text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2.5 py-1 rounded-full';
    indicator.innerHTML = '<span class="w-2 h-2 rounded-full bg-rose-500"></span> Disconnected';
  }
}

// --- TAB SWITCHING ---
function switchTab(tabName) {
  state.currentTab = tabName;
  const tabs = ['jobs', 'review', 'companies', 'profile', 'analytics'];
  const titles = {
    jobs: { title: 'Discovered Jobs', subtitle: 'Explore, filter, and score live opportunities' },
    review: { title: 'HITL Review Queue', subtitle: 'Verify autofilled forms and screenshots before submission' },
    companies: { title: 'Dream Companies', subtitle: 'Manage target companies and direct ATS crawlers' },
    profile: { title: 'Profile & Resume', subtitle: 'Configure preferences, screening answers, or upload resume' },
    analytics: { title: 'Analytics & Funnel', subtitle: 'Application pipeline performance and match trends' },
  };

  tabs.forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    const navEl = document.getElementById(`nav-${t}`);
    if (t === tabName) {
      el.classList.remove('hidden');
      navEl.classList.add('bg-slate-800', 'text-white');
      navEl.classList.remove('text-slate-300');
    } else {
      el.classList.add('hidden');
      navEl.classList.remove('bg-slate-800', 'text-white');
      navEl.classList.add('text-slate-300');
    }
  });

  document.getElementById('page-title').textContent = titles[tabName].title;
  document.getElementById('page-subtitle').textContent = titles[tabName].subtitle;

  if (tabName === 'jobs') loadJobs();
  else if (tabName === 'review') loadStagedJobs();
  else if (tabName === 'companies') loadCompanies();
  else if (tabName === 'profile') loadProfile();
  else if (tabName === 'analytics') loadAnalytics();
}

function refreshCurrentTab() {
  switchTab(state.currentTab);
  showToast('Refreshed data', 'info');
}

// --- TAB 1: JOBS MANAGEMENT ---
let filterDebounce = null;
function debounceFilterJobs() {
  clearTimeout(filterDebounce);
  filterDebounce = setTimeout(() => {
    state.offset = 0;
    loadJobs();
  }, 350);
}

function updateScoreLabel(val) {
  document.getElementById('filter-score-val').textContent = `${val}%`;
}

function resetFilters() {
  document.getElementById('filter-search').value = '';
  document.getElementById('filter-status').value = '';
  document.getElementById('filter-portal').value = '';
  document.getElementById('filter-min-score').value = 0;
  updateScoreLabel(0);
  state.offset = 0;
  loadJobs();
}

async function loadJobs() {
  const tbody = document.getElementById('jobs-table-body');
  tbody.innerHTML = `
    <tr>
      <td colspan="6" class="py-12 text-center text-slate-500">
        <i class="fa-solid fa-spinner fa-spin text-lg mb-2"></i>
        <div>Fetching jobs...</div>
      </td>
    </tr>
  `;

  const search = document.getElementById('filter-search').value.trim();
  const status = document.getElementById('filter-status').value;
  const portal = document.getElementById('filter-portal').value;
  const minScore = document.getElementById('filter-min-score').value;

  const params = new URLSearchParams({
    limit: state.limit,
    offset: state.offset
  });
  if (status) params.append('status', status);
  if (portal) params.append('portal', portal);
  if (search) params.append('company', search);
  if (minScore > 0) params.append('min_score', minScore);

  try {
    const res = await fetch(`/api/jobs?${params.toString()}`);
    const data = await res.json();
    state.jobs = data.items || [];
    state.totalJobs = data.total_count || 0;

    renderJobsTable();
    updatePagination();
    document.getElementById('badge-jobs-count').textContent = state.totalJobs;
  } catch (err) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="py-8 text-center text-rose-400">
          <i class="fa-solid fa-triangle-exclamation text-base mb-1"></i>
          <div>Failed to load jobs. Check server connection.</div>
        </td>
      </tr>
    `;
  }
}

function renderJobsTable() {
  const tbody = document.getElementById('jobs-table-body');
  if (state.jobs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="py-12 text-center text-slate-500">
          <i class="fa-solid fa-briefcase text-2xl mb-2 text-slate-600 block"></i>
          No jobs found matching current filters.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = state.jobs.map(job => {
    const scoreColor = job.match_score >= 80 ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                     : job.match_score >= 60 ? 'text-indigo-400 bg-indigo-500/10 border-indigo-500/20'
                     : job.match_score > 0 ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                     : 'text-slate-500 bg-slate-800 border-slate-700';

    const statusBadge = {
      discovered: 'bg-slate-800 text-slate-400 border-slate-700',
      scored: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
      staged: 'bg-amber-500/10 text-amber-400 border-amber-500/20 font-semibold',
      submitted: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      rejected: 'bg-rose-500/10 text-rose-400 border-rose-500/20'
    }[job.status] || 'bg-slate-800 text-slate-400 border-slate-700';

    const multiOutletBadge = (job.outlets_count > 1) ? `
      <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-medium cursor-pointer" onclick="openJobDetailModal('${job.id}')" title="${job.outlets_count} sources available">
        <i class="fa-solid fa-layer-group text-[9px]"></i> ${job.outlets_count} outlets
      </span>
    ` : '';

    return `
      <tr class="hover:bg-slate-800/40 transition">
        <td class="py-3 px-4">
          <div class="flex items-center gap-2">
            <span class="font-semibold text-slate-100 hover:text-indigo-400 cursor-pointer" onclick="openJobDetailModal('${job.id}')">${escapeHtml(job.title)}</span>
            ${multiOutletBadge}
          </div>
          <div class="text-[11px] text-slate-400">${escapeHtml(job.company)}</div>
        </td>
        <td class="py-3 px-4">
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-medium text-[11px] uppercase">${escapeHtml(job.portal)}</span>
            ${job.recommended_outlet && job.recommended_outlet.tier === 'direct_ats' ? `
              <span class="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[9px] font-semibold" title="Direct ATS route available">ATS ⭐</span>
            ` : ''}
          </div>
        </td>
        <td class="py-3 px-4 text-slate-400">
          <i class="fa-solid fa-location-dot text-[10px] mr-1 text-slate-500"></i>${escapeHtml(job.location || 'Remote')}
        </td>
        <td class="py-3 px-4">
          <span class="px-2 py-0.5 rounded-full border text-xs font-bold ${scoreColor}">
            ${job.match_score > 0 ? job.match_score + '%' : 'Unscored'}
          </span>
        </td>
        <td class="py-3 px-4">
          <span class="px-2.5 py-0.5 rounded-full border text-[11px] capitalize ${statusBadge}">
            ${escapeHtml(job.status)}
          </span>
        </td>
        <td class="py-3 px-4 text-right">
          <div class="flex items-center justify-end gap-1.5">
            <button onclick="openJobDetailModal('${job.id}')" title="Inspect" class="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700">
              <i class="fa-solid fa-eye text-xs"></i>
            </button>
            ${job.status !== 'staged' && job.status !== 'submitted' ? `
              <button onclick="stageSingleJob('${job.id}')" title="Stage Application" class="p-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500">
                <i class="fa-solid fa-paper-plane text-xs"></i>
              </button>
            ` : ''}
            ${job.status === 'staged' ? `
              <button onclick="approveSingleJob('${job.id}')" title="Approve & Submit" class="p-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 font-semibold">
                <i class="fa-solid fa-check text-xs"></i>
              </button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function updatePagination() {
  const start = state.totalJobs === 0 ? 0 : state.offset + 1;
  const end = Math.min(state.offset + state.limit, state.totalJobs);
  document.getElementById('jobs-pagination-info').textContent = `Showing ${start}–${end} of ${state.totalJobs} jobs`;

  document.getElementById('btn-prev-page').disabled = state.offset === 0;
  document.getElementById('btn-next-page').disabled = end >= state.totalJobs;
}

function prevJobsPage() {
  if (state.offset > 0) {
    state.offset = Math.max(0, state.offset - state.limit);
    loadJobs();
  }
}

function nextJobsPage() {
  if (state.offset + state.limit < state.totalJobs) {
    state.offset += state.limit;
    loadJobs();
  }
}

// --- JOB DETAIL MODAL ---
async function openJobDetailModal(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) throw new Error('Job not found');
    const job = await res.json();
    state.activeJob = job;

    document.getElementById('modal-job-title').textContent = job.title;
    document.getElementById('modal-job-meta').textContent = `${job.company} • ${job.location || 'Remote'} • ${job.portal.toUpperCase()}`;
    document.getElementById('modal-job-desc').textContent = job.description || 'No detailed description provided.';
    document.getElementById('modal-job-url-link').href = job.job_url;

    // Score & Skills
    const scoreEl = document.getElementById('modal-match-score');
    scoreEl.textContent = job.match_score > 0 ? `${job.match_score}%` : 'Unscored';

    const matchedContainer = document.getElementById('modal-matched-skills');
    matchedContainer.innerHTML = (job.matched_skills || []).length > 0
      ? job.matched_skills.map(s => `<span class="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[11px]">${escapeHtml(s)}</span>`).join('')
      : '<span class="text-slate-500 text-xs">None detected</span>';

    const missingContainer = document.getElementById('modal-missing-skills');
    missingContainer.innerHTML = (job.missing_skills || []).length > 0
      ? job.missing_skills.map(s => `<span class="px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[11px]">${escapeHtml(s)}</span>`).join('')
      : '<span class="text-slate-500 text-xs">None missing</span>';

    // Pros & Cons
    const prosConsBox = document.getElementById('modal-pros-cons-box');
    const pros = job.pros_cons?.pros || [];
    const cons = job.pros_cons?.cons || [];
    prosConsBox.innerHTML = `
      ${pros.map(p => `<div class="text-emerald-400 flex items-center gap-1.5"><i class="fa-solid fa-check text-[10px]"></i> ${escapeHtml(p)}</div>`).join('')}
      ${cons.map(c => `<div class="text-rose-400 flex items-center gap-1.5"><i class="fa-solid fa-xmark text-[10px]"></i> ${escapeHtml(c)}</div>`).join('')}
    `;

    // Multi-source Outlets & Direct Route Recommender (Ticket 13)
    const outlets = job.outlets || [];
    document.getElementById('modal-outlets-count').textContent = `${outlets.length} source${outlets.length === 1 ? '' : 's'}`;
    const outletsListEl = document.getElementById('modal-outlets-list');

    // Sort outlets descending by directness
    const sortedOutlets = [...outlets].sort((a, b) => (b.directness_score || 0) - (a.directness_score || 0));
    const highestScore = sortedOutlets.length ? sortedOutlets[0].directness_score : 0;

    outletsListEl.innerHTML = sortedOutlets.map((outlet, idx) => {
      const isTopPick = (outlet.directness_score === highestScore && highestScore >= 80);
      const tierBadgeColor = {
        direct_ats: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
        direct_apply: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
        job_board: 'bg-sky-500/20 text-sky-300 border-sky-500/30',
        aggregator: 'bg-slate-700/50 text-slate-300 border-slate-600',
      }[outlet.tier] || 'bg-slate-700 text-slate-300 border-slate-600';

      return `
        <div class="p-2.5 rounded-xl border ${isTopPick ? 'border-emerald-500/40 bg-emerald-950/20' : 'border-slate-800 bg-slate-950'} flex items-center justify-between gap-3">
          <div class="space-y-1">
            <div class="flex items-center gap-2">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${tierBadgeColor}">${escapeHtml(outlet.portal)}</span>
              ${isTopPick ? '<span class="text-[10px] text-emerald-400 font-semibold flex items-center gap-1"><i class="fa-solid fa-star text-[9px]"></i> Recommended Route</span>' : ''}
              ${outlet.easy_apply ? '<span class="text-[10px] text-indigo-400 font-medium">⚡ Easy Apply</span>' : ''}
            </div>
            <div class="text-[11px] text-slate-300 font-medium">${escapeHtml(outlet.label || '')}</div>
            <div class="text-[10px] text-slate-400">${escapeHtml(outlet.rationale || '')}</div>
          </div>
          <div class="flex items-center gap-2">
            <a href="${escapeHtml(outlet.job_url)}" target="_blank" class="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[11px] font-medium flex items-center gap-1" title="Open Link">
              <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i> View
            </a>
          </div>
        </div>
      `;
    }).join('');

    // Staged Assets
    const stagedSection = document.getElementById('modal-staged-assets-section');
    if (job.application && (job.application.cover_letter || job.application.pitch_note)) {
      stagedSection.classList.remove('hidden');
      document.getElementById('modal-cover-letter').value = job.application.cover_letter || '';
      document.getElementById('modal-pitch-note').value = job.application.pitch_note || '';
    } else {
      stagedSection.classList.add('hidden');
    }

    // Action buttons
    const btnContainer = document.getElementById('modal-action-buttons');
    if (job.status === 'staged') {
      btnContainer.innerHTML = `
        <button onclick="approveSingleJob('${job.id}')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-lg text-xs flex items-center gap-1.5">
          <i class="fa-solid fa-check"></i> Approve & Submit
        </button>
      `;
    } else if (job.status !== 'submitted') {
      btnContainer.innerHTML = `
        <button onclick="stageSingleJob('${job.id}')" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-lg text-xs flex items-center gap-1.5">
          <i class="fa-solid fa-paper-plane"></i> Stage Application
        </button>
      `;
    } else {
      btnContainer.innerHTML = `
        <span class="px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-semibold">
          <i class="fa-solid fa-check-circle"></i> Submitted
        </span>
      `;
    }

    document.getElementById('job-detail-modal').classList.remove('hidden');
  } catch (err) {
    showToast('Failed to load job details', 'error');
  }
}

function closeJobDetailModal() {
  document.getElementById('job-detail-modal').classList.add('hidden');
}

// --- STAGING & HITL APPROVAL ---
async function stageSingleJob(jobId) {
  showToast(`Staging application for job ${jobId}...`, 'info');
  try {
    const res = await fetch(`/api/stage/${jobId}`, { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast('Application successfully staged for review!', 'success');
      loadJobs();
      loadAnalytics();
      if (state.activeJob && state.activeJob.id === jobId) {
        closeJobDetailModal();
      }
    } else {
      showToast(`Staging failed: ${data.error_message || 'Unknown error'}`, 'warning');
    }
  } catch (err) {
    showToast('Staging request error', 'error');
  }
}

async function approveSingleJob(jobId) {
  showToast(`Submitting application for ${jobId}...`, 'info');
  try {
    const res = await fetch(`/api/approve/${jobId}`, { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast('Application submitted successfully!', 'success');
      loadJobs();
      loadStagedJobs();
      loadAnalytics();
      closeJobDetailModal();
    } else {
      showToast(`Submission failed: ${data.message || 'Error occurred'}`, 'error');
    }
  } catch (err) {
    showToast('Approval request failed', 'error');
  }
}

// --- TAB 2: REVIEW QUEUE ---
async function loadStagedJobs() {
  const container = document.getElementById('staged-queue-container');
  container.innerHTML = `
    <div class="py-12 text-center text-slate-500">
      <i class="fa-solid fa-spinner fa-spin text-lg mb-2"></i>
      <div>Loading staged applications...</div>
    </div>
  `;

  try {
    const res = await fetch('/api/jobs?status=staged&limit=100');
    const data = await res.json();
    state.stagedJobs = data.items || [];
    document.getElementById('badge-staged-count').textContent = state.stagedJobs.length;

    if (state.stagedJobs.length === 0) {
      container.innerHTML = `
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center text-slate-400">
          <i class="fa-solid fa-circle-check text-4xl text-emerald-400 mb-3 block"></i>
          <h4 class="text-base font-semibold text-white">Review Queue is Clear!</h4>
          <p class="text-xs text-slate-500 mt-1">No applications are currently awaiting human review. Discover and stage jobs to populate this queue.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = state.stagedJobs.map(job => {
      const matchScore = job.match_score || 0;
      return `
        <div class="bg-slate-900 border border-amber-500/30 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row gap-6">
          <div class="flex-1 space-y-4">
            <div class="flex items-start justify-between">
              <div>
                <span class="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] font-semibold uppercase tracking-wider">Awaiting Submission</span>
                <h4 class="text-base font-bold text-white mt-1.5 cursor-pointer hover:text-indigo-400" onclick="openJobDetailModal('${job.id}')">${escapeHtml(job.title)}</h4>
                <p class="text-xs text-slate-400">${escapeHtml(job.company)} • ${escapeHtml(job.location || 'Remote')} • ${escapeHtml(job.portal.toUpperCase())}</p>
              </div>
              <span class="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-bold">
                ${matchScore}% Match
              </span>
            </div>

            <div class="text-xs text-slate-300 bg-slate-950 p-4 rounded-xl border border-slate-800/80 space-y-2">
              <span class="font-semibold text-slate-400 uppercase text-[10px] block tracking-wider">Tailored Startup Pitch / Intro:</span>
              <p class="italic text-slate-300">"${escapeHtml(job.application?.pitch_note || 'Tailored pitch prepared for direct submission.')}"</p>
            </div>
          </div>

          <div class="w-full md:w-64 flex flex-col justify-between border-t md:border-t-0 md:border-l border-slate-800 pt-4 md:pt-0 md:pl-6 space-y-3">
            <div>
              <span class="text-[11px] text-slate-400 uppercase tracking-wider block font-semibold mb-2">Screenshot Verification</span>
              <div class="h-28 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-center text-slate-500 text-xs text-center p-2">
                <i class="fa-solid fa-camera mr-2"></i> Form Filled & Snapshotted
              </div>
            </div>

            <div class="space-y-2">
              <button onclick="approveSingleJob('${job.id}')" class="w-full py-2 px-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl text-xs shadow-md transition flex items-center justify-center gap-2">
                <i class="fa-solid fa-check"></i> 1-Click Submit
              </button>
              <button onclick="openJobDetailModal('${job.id}')" class="w-full py-2 px-3 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs transition border border-slate-700">
                Inspect Details
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = '<div class="text-rose-400 text-center py-8">Failed to load review queue.</div>';
  }
}

// --- TAB 3: DREAM COMPANIES ---
async function loadCompanies() {
  const tbody = document.getElementById('companies-table-body');
  tbody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-slate-500"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading companies...</td></tr>`;

  try {
    const res = await fetch('/api/companies');
    state.companies = await res.json();
    document.getElementById('badge-companies-count').textContent = state.companies.length;

    if (state.companies.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-slate-500">No target companies configured yet. Click "Add Company" above.</td></tr>`;
      return;
    }

    tbody.innerHTML = state.companies.map(c => `
      <tr class="hover:bg-slate-800/40 transition">
        <td class="py-3 px-4 font-semibold text-white">${escapeHtml(c.name)}</td>
        <td class="py-3 px-4 text-indigo-400">
          <a href="${escapeHtml(c.careers_url)}" target="_blank" class="hover:underline flex items-center gap-1.5">
            ${escapeHtml(c.domain || c.careers_url)} <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
          </a>
        </td>
        <td class="py-3 px-4">
          <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 uppercase text-[10px] font-semibold">${escapeHtml(c.ats)}</span>
        </td>
        <td class="py-3 px-4">
          <span class="px-2 py-0.5 rounded text-[11px] font-medium capitalize ${c.priority === 'high' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' : 'bg-slate-800 text-slate-300'}">
            ${escapeHtml(c.priority)}
          </span>
        </td>
        <td class="py-3 px-4 font-semibold text-slate-200">${c.active_jobs_count || 0}</td>
        <td class="py-3 px-4 text-slate-400 text-[11px]">${c.last_crawled_at ? new Date(c.last_crawled_at).toLocaleDateString() : 'Never'}</td>
        <td class="py-3 px-4 text-right">
          <button onclick="deleteCompany(${c.id})" class="p-1.5 text-slate-500 hover:text-rose-400 transition" title="Delete">
            <i class="fa-solid fa-trash-can text-xs"></i>
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-rose-400">Failed to load target companies.</td></tr>`;
  }
}

function openAddCompanyModal() {
  document.getElementById('add-company-modal').classList.remove('hidden');
}

function closeAddCompanyModal() {
  document.getElementById('add-company-modal').classList.add('hidden');
}

async function saveNewCompany() {
  const name = document.getElementById('new-comp-name').value.trim();
  const domain = document.getElementById('new-comp-domain').value.trim();
  const careers_url = document.getElementById('new-comp-url').value.trim();
  const ats = document.getElementById('new-comp-ats').value;
  const priority = document.getElementById('new-comp-priority').value;

  if (!name || !careers_url) {
    showToast('Name and Careers URL are required', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/companies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, domain, careers_url, ats, priority })
    });
    if (res.ok) {
      showToast(`Company ${name} tracked!`, 'success');
      closeAddCompanyModal();
      loadCompanies();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Failed to add company', 'error');
    }
  } catch (err) {
    showToast('Failed to add company', 'error');
  }
}

async function deleteCompany(id) {
  if (!confirm('Are you sure you want to stop tracking this company?')) return;
  try {
    const res = await fetch(`/api/companies/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Company removed', 'info');
      loadCompanies();
    }
  } catch (err) {
    showToast('Failed to delete company', 'error');
  }
}

// --- TAB 4: PROFILE & RESUME ---
async function loadProfile() {
  try {
    const res = await fetch('/api/profile');
    if (!res.ok) return;
    const p = await res.json();
    state.profile = p;

    // Contact
    document.getElementById('prof-full-name').value = p.personal_info?.full_name || '';
    document.getElementById('prof-email').value = p.personal_info?.email || '';
    document.getElementById('prof-phone').value = p.personal_info?.phone || '';
    document.getElementById('prof-location').value = p.personal_info?.location || '';
    document.getElementById('prof-linkedin').value = p.personal_info?.linkedin_url || '';
    document.getElementById('prof-github').value = p.personal_info?.github_url || '';
    document.getElementById('prof-portfolio').value = p.personal_info?.portfolio_url || '';

    // Preferences
    document.getElementById('prof-titles').value = (p.preferences?.target_titles || []).join(', ');
    document.getElementById('prof-target-locs').value = (p.preferences?.target_locations || []).join(', ');
    document.getElementById('prof-min-salary').value = p.preferences?.min_base_salary_usd || 0;
    document.getElementById('prof-remote-only').checked = !!p.preferences?.remote_only;
    document.getElementById('prof-blacklist').value = (p.preferences?.blacklisted_companies || []).join(', ');

    // Skills
    document.getElementById('prof-skills-lang').value = (p.skills?.languages || []).join(', ');
    document.getElementById('prof-skills-frameworks').value = (p.skills?.frameworks || []).join(', ');
    document.getElementById('prof-skills-tools').value = (p.skills?.cloud_and_tools || []).join(', ');

    // Screening Answers
    document.getElementById('prof-qa-auth').value = p.screening_answers?.work_authorization || 'Yes';
    document.getElementById('prof-qa-sponsorship').value = p.screening_answers?.require_sponsorship || 'No';
    document.getElementById('prof-qa-notice').value = p.screening_answers?.notice_period || '';
    document.getElementById('prof-qa-salary-str').value = p.screening_answers?.expected_salary || '';
  } catch (err) {
    showToast('Failed to load candidate profile', 'error');
  }
}

async function saveProfile() {
  const updated = {
    personal_info: {
      full_name: document.getElementById('prof-full-name').value.trim(),
      email: document.getElementById('prof-email').value.trim(),
      phone: document.getElementById('prof-phone').value.trim(),
      location: document.getElementById('prof-location').value.trim(),
      linkedin_url: document.getElementById('prof-linkedin').value.trim(),
      github_url: document.getElementById('prof-github').value.trim(),
      portfolio_url: document.getElementById('prof-portfolio').value.trim(),
      resume_path: state.profile?.personal_info?.resume_path || ''
    },
    preferences: {
      target_titles: document.getElementById('prof-titles').value.split(',').map(s => s.trim()).filter(Boolean),
      target_locations: document.getElementById('prof-target-locs').value.split(',').map(s => s.trim()).filter(Boolean),
      min_base_salary_usd: parseInt(document.getElementById('prof-min-salary').value) || 0,
      remote_only: document.getElementById('prof-remote-only').checked,
      blacklisted_companies: document.getElementById('prof-blacklist').value.split(',').map(s => s.trim()).filter(Boolean),
    },
    skills: {
      languages: document.getElementById('prof-skills-lang').value.split(',').map(s => s.trim()).filter(Boolean),
      frameworks: document.getElementById('prof-skills-frameworks').value.split(',').map(s => s.trim()).filter(Boolean),
      cloud_and_tools: document.getElementById('prof-skills-tools').value.split(',').map(s => s.trim()).filter(Boolean),
    },
    screening_answers: {
      work_authorization: document.getElementById('prof-qa-auth').value,
      require_sponsorship: document.getElementById('prof-qa-sponsorship').value,
      notice_period: document.getElementById('prof-qa-notice').value.trim(),
      expected_salary: document.getElementById('prof-qa-salary-str').value.trim(),
      years_of_experience: state.profile?.screening_answers?.years_of_experience || {}
    }
  };

  try {
    const res = await fetch('/api/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updated)
    });
    if (res.ok) {
      showToast('Candidate profile updated and persisted!', 'success');
      loadProfile();
    } else {
      showToast('Failed to save profile', 'error');
    }
  } catch (err) {
    showToast('Save profile error', 'error');
  }
}

async function uploadResumeFile(event) {
  const file = event.target.files[0];
  if (!file) return;

  const statusLabel = document.getElementById('resume-upload-status');
  statusLabel.classList.remove('hidden');
  statusLabel.textContent = 'Parsing resume...';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/profile/resume', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.ok) {
      statusLabel.textContent = 'Uploaded & parsed successfully!';
      showToast(`Resume parsed: ${data.skills_extracted_count || 0} skills extracted!`, 'success');
      loadProfile();
    } else {
      statusLabel.textContent = 'Failed to parse resume';
      showToast(data.detail || 'Resume ingestion error', 'error');
    }
  } catch (err) {
    statusLabel.textContent = 'Upload error';
    showToast('Failed to upload resume file', 'error');
  }
}

// --- TAB 5: ANALYTICS ---
async function loadAnalytics() {
  try {
    const res = await fetch('/api/analytics');
    const data = await res.json();
    state.analytics = data;

    const pipeline = data.pipeline || {};
    document.getElementById('stat-total-discovered').textContent = pipeline.total_discovered || 0;
    document.getElementById('stat-total-scored').textContent = pipeline.total_scored || 0;
    document.getElementById('stat-total-staged').textContent = pipeline.total_staged || 0;
    document.getElementById('stat-total-submitted').textContent = pipeline.total_submitted || 0;

    document.getElementById('stat-avg-score-sub').textContent = `Avg match score: ${data.average_match_score || 0}%`;

    // Funnel bars
    const funnelContainer = document.getElementById('analytics-funnel-bars');
    const total = Math.max(pipeline.total_discovered || 1, 1);
    const stages = [
      { name: 'Discovered Opportunities', count: pipeline.total_discovered || 0, color: 'bg-indigo-500' },
      { name: 'Semantic Scored & Filtered', count: pipeline.total_scored || 0, color: 'bg-cyan-500' },
      { name: 'Staged for Review', count: pipeline.total_staged || 0, color: 'bg-amber-500' },
      { name: 'Approved & Submitted', count: pipeline.total_submitted || 0, color: 'bg-emerald-500' },
    ];

    funnelContainer.innerHTML = stages.map(st => {
      const pct = Math.round((st.count / total) * 100);
      return `
        <div>
          <div class="flex justify-between text-xs mb-1">
            <span class="text-slate-300 font-medium">${st.name}</span>
            <span class="text-slate-400">${st.count} (${pct}%)</span>
          </div>
          <div class="w-full h-2 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
            <div class="${st.color} h-full transition-all duration-500 rounded-full" style="width: ${pct}%"></div>
          </div>
        </div>
      `;
    }).join('');

    // Portal Distribution
    const portalList = document.getElementById('portal-distribution-list');
    const dist = data.portal_distribution || {};
    const portalKeys = Object.keys(dist);

    if (portalKeys.length === 0) {
      portalList.innerHTML = '<div class="text-slate-500 col-span-4 text-center py-4">No portal data yet.</div>';
    } else {
      portalList.innerHTML = portalKeys.map(k => `
        <div class="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between">
          <span class="font-semibold uppercase text-slate-300">${escapeHtml(k)}</span>
          <span class="px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 font-bold">${dist[k]}</span>
        </div>
      `).join('');
    }
  } catch (err) {
    showToast('Failed to load analytics', 'error');
  }
}

// --- DISCOVERY ACTION MODALS ---
function triggerSearchModal() {
  document.getElementById('search-modal').classList.remove('hidden');
}
function closeSearchModal() {
  document.getElementById('search-modal').classList.add('hidden');
}

async function executeSearchPortals() {
  const kw = document.getElementById('search-keywords').value.split(',').map(s => s.trim()).filter(Boolean);
  const loc = document.getElementById('search-locations').value.split(',').map(s => s.trim()).filter(Boolean);
  const cbs = document.querySelectorAll('input[name="search-portal-cb"]:checked');
  const portals = Array.from(cbs).map(cb => cb.value);

  const btn = document.getElementById('btn-submit-search');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Searching...';

  try {
    const res = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        keywords: kw.length ? kw : ['Software Engineer'],
        locations: loc.length ? loc : ['Remote'],
        portals: portals.length ? portals : ['remoteok', 'wwr'],
        run_in_background: true
      })
    });
    if (res.ok) {
      showToast('Search initiated in background! Discovered postings will appear shortly.', 'success');
      closeSearchModal();
      setTimeout(loadJobs, 3000);
    }
  } catch (err) {
    showToast('Search execution failed', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-play text-[10px]"></i> Launch Search';
  }
}

function triggerCrawlModal() {
  document.getElementById('crawl-modal').classList.remove('hidden');
}
function closeCrawlModal() {
  document.getElementById('crawl-modal').classList.add('hidden');
}

async function executeCrawlCompanies() {
  const prio = document.getElementById('crawl-priority').value || null;
  const kwInput = document.getElementById('crawl-keywords').value.trim();
  const kw = kwInput ? kwInput.split(',').map(s => s.trim()) : null;

  const btn = document.getElementById('btn-submit-crawl');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Crawling...';

  try {
    const res = await fetch('/api/crawl-companies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ priority: prio, keywords: kw, run_in_background: true })
    });
    if (res.ok) {
      showToast('Company career crawl started in background!', 'success');
      closeCrawlModal();
      setTimeout(loadJobs, 4000);
    }
  } catch (err) {
    showToast('Crawl execution failed', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-play text-[10px]"></i> Start Crawler';
  }
}

async function triggerRunMatch() {
  showToast('Scoring discovered jobs against candidate profile...', 'info');
  try {
    const res = await fetch('/api/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force_rescore: false })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Scored ${data.total_scored} jobs (${data.passed_filter_count} passed criteria)!`, 'success');
      loadJobs();
      loadAnalytics();
    }
  } catch (err) {
    showToast('Semantic match execution failed', 'error');
  }
}

// --- UTILITY ---
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
