// ── THEME ─────────────────────────────────────────────────────────────────
const savedTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);
updateThemeIcon(savedTheme);

function toggleTheme() {
  const cur  = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
  fetch('/theme/set', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({theme: next}) });
}
function updateThemeIcon(theme) {
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
}

// ── SEARCH ────────────────────────────────────────────────────────────────
let timeout;
function searchMovies() {
  clearTimeout(timeout);
  timeout = setTimeout(async () => {
    const query     = document.getElementById('search').value.trim();
    const container = document.getElementById('results');
    if (query.length < 2) { container.innerHTML = ''; return; }
    container.innerHTML = `<div class="section-header" style="padding:0 0 14px">
      <span class="section-title"><span class="icon">🔍</span> Results for "${query}"</span></div>
      <div class="movies" id="results-grid"></div>`;
    const res  = await fetch(`/search?movie=${encodeURIComponent(query)}`);
    const data = await res.json();
    const grid = document.getElementById('results-grid');
    if (!data.length) {
      grid.innerHTML = `<p style="color:var(--muted);font-size:14px;padding:8px 0">No results found.</p>`;
      return;
    }
    grid.innerHTML = data.map(m => movieCard(m)).join('');
    attachStarListeners();
  }, 340);
}

function movieCard(m) {
  const poster = m.Poster && m.Poster !== 'N/A' ? m.Poster : '/static/noimage.png';
  const rating = m.imdbRating && m.imdbRating !== 'N/A' ? `<div class="card-rating">⭐ ${m.imdbRating}</div>` : '';
  return `
  <div class="card">
    <div class="card-poster" onclick="window.location='/movie/${m.imdbID}'" style="cursor:pointer">
      ${rating}
      <img src="${poster}" alt="${m.Title}" loading="lazy">
      <div class="card-overlay">
        <div class="overlay-actions">
          <a href="/movie/${m.imdbID}" class="overlay-btn primary">Details</a>
          <button class="overlay-btn secondary"
            onclick="event.stopPropagation();addToWatchlist('${m.imdbID}','${escHtml(m.Title)}','${poster}','${m.Year}',this)">
            + Watch</button>
        </div>
      </div>
    </div>
    <div class="card-info">
      <div class="card-title">${m.Title}</div>
      <div class="card-meta">${m.Year || ''}${m.Genre ? ' · ' + m.Genre.split(',')[0] : ''}</div>
    </div>
    <div class="review-form">
      <form onsubmit="submitReview(event,this)">
        <input type="hidden" name="movie_id"     value="${m.imdbID}">
        <input type="hidden" name="movie_title"  value="${escHtml(m.Title)}">
        <input type="hidden" name="movie_poster" value="${poster}">
        <input type="hidden" name="movie_genre"  value="${m.Genre||''}">
        <div class="stars" data-selected="0">
          <span>★</span><span>★</span><span>★</span><span>★</span><span>★</span>
        </div>
        <input type="hidden" name="rating" value="0">
        <input type="text" name="review" placeholder="Quick thought…">
        <button type="submit" class="submit-btn">Log Film</button>
        <button type="button" class="log-only-btn" onclick="logOnly(this)">Just log it (no rating)</button>
      </form>
    </div>
  </div>`;
}

function escHtml(s) {
  return (s||'').replace(/'/g,"&#39;").replace(/"/g,'&quot;');
}

// ── STARS ─────────────────────────────────────────────────────────────────
function attachStarListeners() {
  document.querySelectorAll('.stars').forEach(container => {
    if (container.dataset.attached) return;
    container.dataset.attached = '1';
    const stars = container.querySelectorAll('span');
    const input = container.closest('form')?.querySelector('input[name="rating"]');
    stars.forEach((star, i) => {
      star.addEventListener('mouseenter', () => {
        stars.forEach((s,j) => s.style.color = j<=i ? 'var(--gold)' : 'var(--muted)');
      });
      star.addEventListener('click', () => {
        const val = i + 1;
        container.dataset.selected = val;
        if (input) input.value = val;
        stars.forEach((s,j) => s.style.color = j<val ? 'var(--gold)' : 'var(--muted)');
      });
    });
    container.addEventListener('mouseleave', () => {
      const sel = parseInt(container.dataset.selected) || 0;
      stars.forEach((s,j) => s.style.color = j<sel ? 'var(--gold)' : 'var(--muted)');
    });
  });
}
document.addEventListener('DOMContentLoaded', attachStarListeners);

// ── SUBMIT REVIEW ─────────────────────────────────────────────────────────
async function submitReview(e, form) {
  e.preventDefault();
  const fd  = new FormData(form);
  const btn = form.querySelector('.submit-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  const res  = await fetch('/review', { method:'POST', body: fd });
  const data = await res.json();
  btn.disabled = false; btn.textContent = 'Log Film';
  if (data.status === 'login_required') {
    showToast('Please login first', 'error');
    setTimeout(() => window.location = '/login', 1200);
  } else {
    showToast('Film logged! 🎬', 'success');
    form.reset();
    const stars = form.querySelector('.stars');
    if (stars) {
      stars.dataset.selected = '0';
      stars.querySelectorAll('span').forEach(s => s.style.color = 'var(--muted)');
    }
  }
}

// ── LOG WITHOUT RATING ────────────────────────────────────────────────────
async function logOnly(btn) {
  const form     = btn.closest('form');
  const movie_id = form.querySelector('[name="movie_id"]').value;
  const title    = form.querySelector('[name="movie_title"]')?.value || '';
  const poster   = form.querySelector('[name="movie_poster"]')?.value || '';
  const genre    = form.querySelector('[name="movie_genre"]')?.value || '';
  const fd = new FormData();
  fd.append('movie_id',     movie_id);
  fd.append('movie_title',  title);
  fd.append('movie_poster', poster);
  fd.append('movie_genre',  genre);
  fd.append('rating', '0');
  fd.append('review', '');
  btn.disabled = true; btn.textContent = 'Logging…';
  const res  = await fetch('/review', { method:'POST', body: fd });
  const data = await res.json();
  btn.disabled = false; btn.textContent = 'Just log it (no rating)';
  if (data.status === 'login_required') {
    showToast('Please login first', 'error');
    setTimeout(() => window.location = '/login', 1200);
  } else { showToast('Added to diary 📖', 'success'); }
}

// ── WATCHLIST ─────────────────────────────────────────────────────────────
async function addToWatchlist(movieId, title, poster, year, btn) {
  const res  = await fetch('/watchlist/add', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ movie_id:movieId, title, poster, year })
  });
  const data = await res.json();
  if (data.status === 'login_required') {
    showToast('Please login first','error');
    setTimeout(() => window.location='/login', 1200);
  } else if (data.status === 'exists') {
    showToast('Already in watchlist','error');
  } else {
    showToast('Added to watchlist ✓','success');
    if (btn) { btn.textContent = '✓ Saved'; btn.disabled = true; }
  }
}

async function removeFromWatchlist(movieId, el) {
  const res  = await fetch('/watchlist/remove', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ movie_id: movieId })
  });
  const data = await res.json();
  if (data.status === 'removed') {
    const item = el.closest('.watchlist-item');
    item.style.transition = 'opacity .3s, transform .3s';
    item.style.opacity = '0'; item.style.transform = 'scale(.9)';
    setTimeout(() => item.remove(), 300);
    showToast('Removed from watchlist','success');
  }
}

async function toggleWatchlist(movieId, title, poster, year, btn) {
  const isActive = btn.classList.contains('active');
  const res = await fetch(isActive ? '/watchlist/remove' : '/watchlist/add', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ movie_id:movieId, title, poster, year })
  });
  const data = await res.json();
  if (data.status === 'login_required') {
    showToast('Please login first','error');
    setTimeout(() => window.location='/login', 1200); return;
  }
  btn.classList.toggle('active');
  btn.textContent = btn.classList.contains('active') ? '✓ In Watchlist' : '+ Watchlist';
  showToast(btn.classList.contains('active') ? 'Added to watchlist ✓' : 'Removed','success');
}

// ── IMDB EXTENDED MODAL ───────────────────────────────────────────────────
async function loadExtended() {
  const backdrop = document.getElementById('imdb-modal');
  backdrop.classList.add('open');
  const grid = document.getElementById('extended-grid');
  if (grid.dataset.loaded) return;
  grid.innerHTML = '<p style="color:var(--muted);padding:12px">Loading…</p>';
  const res    = await fetch('/imdb_extended');
  const movies = await res.json();
  grid.dataset.loaded = '1';
  grid.innerHTML = movies.map((m,i) => {
    const poster = m.Poster && m.Poster !== 'N/A' ? m.Poster : '/static/noimage.png';
    return `
    <div class="card">
      <div class="card-poster" onclick="window.location='/movie/${m.imdbID}'" style="cursor:pointer">
        <div class="card-rank">${i+11}</div>
        <div class="card-rating">⭐ ${m.imdbRating}</div>
        <img src="${poster}" loading="lazy">
        <div class="card-overlay">
          <div class="overlay-actions">
            <a href="/movie/${m.imdbID}" class="overlay-btn primary">Details</a>
            <button class="overlay-btn secondary"
              onclick="event.stopPropagation();addToWatchlist('${m.imdbID}','${escHtml(m.Title)}','${poster}','${m.Year}',this)">
              + Watch</button>
          </div>
        </div>
      </div>
      <div class="card-info">
        <div class="card-title">${m.Title}</div>
        <div class="card-meta">${m.Year} · ${(m.Genre||'').split(',')[0]}</div>
      </div>
    </div>`;
  }).join('');
}
function closeModal() { document.getElementById('imdb-modal').classList.remove('open'); }

// ── PROFILE ───────────────────────────────────────────────────────────────
function selectSwatch(el, color) {
  document.querySelectorAll('.swatch').forEach(s => s.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('avatar_color').value = color;
  const ring = document.getElementById('avatar-ring');
  if (ring) ring.style.background = color;
}

async function saveProfile(e) {
  e.preventDefault();
  const form = e.target;
  const fd   = new FormData(form);
  const btn  = form.querySelector('.save-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  const res  = await fetch('/profile/update', { method:'POST', body: fd });
  const data = await res.json();
  btn.disabled = false; btn.textContent = 'Save Changes';
  showToast(data.status === 'success' ? 'Profile updated ✓' : 'Something went wrong',
    data.status === 'success' ? 'success' : 'error');
}

// ── TOAST ─────────────────────────────────────────────────────────────────
function showToast(msg, type='success') {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast'; document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = `toast ${type}`;
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('show')));
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 2800);
}
