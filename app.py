from flask import Flask, render_template, request, redirect, session, jsonify
import requests, sqlite3, json, time
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

# ── KEYS ─────────────────────────────────────────────────────────────────────
OMDB_KEY   = "2e6e1bc6"
TMDB_KEY   = "e51d1ffc9641ef8c55ba4547747d0a4c"
TMDB_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJlNTFkMWZmYzk2NDFlZjhjNTViYTQ1NDc3NDdkMGE0YyIsIm5iZiI6MTc3NzI5ODEyOS4zNzksInN1YiI6IjY5ZWY2YWQxNDk4Y2YxNDA2NjAyOWJlYiIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.DpCWNd5IJha5eF7EryJ30Tjn8oTIfOEbogyzRZIIiKU"
TMDB_BASE  = "https://api.themoviedb.org/3"
TMDB_IMG   = "https://image.tmdb.org/t/p/w500"
TMDB_HDRS  = {"Authorization": f"Bearer {TMDB_TOKEN}", "accept": "application/json"}

# ── REAL IMDB TOP 20 (hardcoded IMDb IDs — ratings fetched from OMDB) ─────────
IMDB_TOP20 = [
    "tt0111161",  # 1  The Shawshank Redemption      9.3
    "tt0068646",  # 2  The Godfather                  9.2
    "tt0468569",  # 3  The Dark Knight                9.0
    "tt0071562",  # 4  The Godfather Part II           9.0
    "tt0050083",  # 5  12 Angry Men                   9.0
    "tt0108052",  # 6  Schindler's List               9.0
    "tt0167260",  # 7  The Return of the King         9.0
    "tt0110912",  # 8  Pulp Fiction                   8.9
    "tt0060196",  # 9  The Good the Bad and the Ugly  8.8
    "tt0120737",  # 10 The Fellowship of the Ring     8.8
    "tt0137523",  # 11 Fight Club                     8.8
    "tt1375666",  # 12 Inception                      8.8
    "tt0167261",  # 13 The Two Towers                 8.8
    "tt0080684",  # 14 The Empire Strikes Back        8.7
    "tt0133093",  # 15 The Matrix                     8.7
    "tt0099685",  # 16 Goodfellas                     8.7
    "tt0073486",  # 17 One Flew Over the Cuckoo's Nest 8.7
    "tt0047478",  # 18 Seven Samurai                  8.6
    "tt0109830",  # 19 Forrest Gump                   8.8
    "tt0114369",  # 20 Se7en                          8.6
]

GENRE_MAP = {
    28:'Action', 12:'Adventure', 16:'Animation', 35:'Comedy', 80:'Crime',
    99:'Documentary', 18:'Drama', 10751:'Family', 14:'Fantasy', 36:'History',
    27:'Horror', 10402:'Music', 9648:'Mystery', 10749:'Romance',
    878:'Science Fiction', 10770:'TV Movie', 53:'Thriller', 10752:'War', 37:'Western'
}

# ── CACHE ─────────────────────────────────────────────────────────────────────
_cache = {}
def cache_get(key):
    v = _cache.get(key)
    if v and time.time() < v['exp']: return v['data']
    return None
def cache_set(key, data, ttl=300):
    _cache[key] = {'data': data, 'exp': time.time() + ttl}

# ── DB ────────────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
        password TEXT, bio TEXT DEFAULT '', avatar_color TEXT DEFAULT '#e8a020',
        theme TEXT DEFAULT 'dark')""")
    c.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT, movie_id TEXT, username TEXT,
        rating INTEGER, review TEXT, genre TEXT, movie_title TEXT,
        movie_poster TEXT, created_at TEXT DEFAULT (datetime('now')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, movie_id TEXT,
        movie_title TEXT, movie_poster TEXT, movie_year TEXT,
        added_at TEXT DEFAULT (datetime('now')), UNIQUE(username, movie_id))""")
    for col in ['genre','movie_title','movie_poster','created_at']:
        try: c.execute(f"ALTER TABLE reviews ADD COLUMN {col} TEXT")
        except: pass
    for col in [("bio","TEXT DEFAULT ''"),("avatar_color","TEXT DEFAULT '#e8a020'"),("theme","TEXT DEFAULT 'dark'")]:
        try: c.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")
        except: pass
    conn.commit(); conn.close()

init_db()

def db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# ── API HELPERS ───────────────────────────────────────────────────────────────
def tmdb(path, params={}, ttl=300):
    key = 'tmdb:' + path + str(sorted(params.items()))
    cached = cache_get(key)
    if cached: return cached
    try:
        p = {"language": "en-US"}
        p.update(params)
        r = requests.get(f"{TMDB_BASE}{path}", headers=TMDB_HDRS, params=p, timeout=8)
        data = r.json()
        if data.get("results") is not None:
            cache_set(key, data, ttl)
        return data
    except Exception as e:
        print(f"[TMDB ERROR] {path}: {e}")
        return {"results": []}

def omdb(imdb_id):
    """Fetch a single movie from OMDB by IMDB ID — real IMDB ratings."""
    key = 'omdb:' + imdb_id
    cached = cache_get(key)
    if cached: return cached
    try:
        r = requests.get(f"http://www.omdbapi.com/?apikey={OMDB_KEY}&i={imdb_id}", timeout=6)
        data = r.json()
        if data.get('Response') == 'True':
            cache_set(key, data, 86400)  # cache 24h
        return data
    except Exception as e:
        print(f"[OMDB ERROR] {imdb_id}: {e}")
        return {}

def img(path):
    return f"{TMDB_IMG}{path}" if path else "/static/noimage.png"

def normalise_tmdb(m, detail=False):
    """TMDB movie → flat dict."""
    mid      = str(m.get('id', ''))
    title    = m.get('title') or m.get('name', '')
    poster   = img(m.get('poster_path'))
    backdrop = f"https://image.tmdb.org/t/p/w1280{m['backdrop_path']}" if m.get('backdrop_path') else poster
    year     = (m.get('release_date') or m.get('first_air_date', ''))[:4]
    vote     = m.get('vote_average', 0)
    overview = m.get('overview', '')

    genres = ''
    if detail and m.get('genres'):
        genres = ', '.join(g['name'] for g in m['genres'])
    elif m.get('genre_ids'):
        genres = ', '.join(GENRE_MAP.get(gid, '') for gid in m['genre_ids'][:3] if gid in GENRE_MAP)
        genres = ', '.join(filter(None, genres.split(', ')))

    runtime = ''
    if detail and m.get('runtime'):
        h, mn = divmod(m['runtime'], 60)
        runtime = f"{h}h {mn}m" if h else f"{mn}m"

    cast = director = ''
    if detail and m.get('credits'):
        cast     = ', '.join(p['name'] for p in m['credits'].get('cast', [])[:5])
        dirs     = [p['name'] for p in m['credits'].get('crew', []) if p['job'] == 'Director']
        director = ', '.join(dirs[:2])

    return {
        'imdbID'    : f"tmdb-{mid}",
        'Title'     : title,
        'Year'      : year,
        'Poster'    : poster,
        'Backdrop'  : backdrop,
        'imdbRating': f"{vote:.1f}" if vote else 'N/A',
        'Genre'     : genres,
        'Overview'  : overview,
        'Runtime'   : runtime,
        'Cast'      : cast,
        'Director'  : director,
    }

def normalise_omdb(m):
    """OMDB movie → flat dict (real IMDB rating, IMDB-style ID)."""
    return {
        'imdbID'    : m.get('imdbID', ''),
        'Title'     : m.get('Title', ''),
        'Year'      : m.get('Year', ''),
        'Poster'    : m.get('Poster', '/static/noimage.png'),
        'Backdrop'  : m.get('Poster', '/static/noimage.png'),
        'imdbRating': m.get('imdbRating', 'N/A'),
        'Genre'     : m.get('Genre', ''),
        'Overview'  : m.get('Plot', ''),
        'Runtime'   : m.get('Runtime', ''),
        'Cast'      : m.get('Actors', ''),
        'Director'  : m.get('Director', ''),
    }

def get_user(username):
    conn = db()
    u = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(u) if u else {}

def get_recs(username):
    conn = db()
    rows = conn.execute("SELECT genre FROM reviews WHERE username=? AND genre IS NOT NULL", (username,)).fetchall()
    conn.close()
    gc = {}
    for r in rows:
        for g in (r['genre'] or '').split(','):
            g = g.strip()
            if g: gc[g] = gc.get(g, 0) + 1
    if not gc: return []
    top = max(gc, key=gc.get)
    gid = next((k for k, v in GENRE_MAP.items() if v.lower() == top.lower()), None)
    if not gid: return []
    data = tmdb('/discover/movie', {'with_genres': gid, 'sort_by': 'popularity.desc'}, ttl=3600)
    return [normalise_tmdb(m) for m in data.get('results', [])[:8]]

# ── HOME ──────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    user_data = get_user(session['user']) if 'user' in session else {}
    return render_template('index.html', user_data=user_data)

# ── ASYNC SECTION ENDPOINTS ───────────────────────────────────────────────────

@app.route('/api/section/top_rated')
def api_top_rated():
    """Real IMDB Top 20 — fetched from OMDB with real IMDB ratings."""
    results = []
    for imdb_id in IMDB_TOP20:
        m = omdb(imdb_id)
        if m.get('Response') == 'True':
            results.append(normalise_omdb(m))
    return jsonify(results)

@app.route('/api/section/trending')
def api_trending():
    data = tmdb('/trending/movie/week', ttl=3600)
    return jsonify([normalise_tmdb(m) for m in data.get('results', [])[:8]])

@app.route('/api/section/now_playing')
def api_now_playing():
    data = tmdb('/movie/now_playing', {'region': 'US'}, ttl=3600)
    return jsonify([normalise_tmdb(m) for m in data.get('results', [])[:8]])

@app.route('/api/section/upcoming')
def api_upcoming():
    data = tmdb('/movie/upcoming', {'region': 'US'}, ttl=3600)
    results = [m for m in data.get('results', [])
               if (m.get('release_date') or '0000') >= '2025-01-01']
    return jsonify([normalise_tmdb(m) for m in results[:8]])

@app.route('/api/section/recommendations')
def api_recommendations():
    if 'user' not in session: return jsonify([])
    return jsonify(get_recs(session['user']))

# ── SEARCH ────────────────────────────────────────────────────────────────────
@app.route('/search')
def search():
    q = request.args.get('movie', '').strip()
    if not q: return jsonify([])
    data = tmdb('/search/movie', {'query': q})
    return jsonify([normalise_tmdb(m) for m in data.get('results', [])[:12]])

# ── MOVIE DETAIL ──────────────────────────────────────────────────────────────
@app.route('/movie/<path:movie_id>')
def movie_detail(movie_id):
    movie = {}
    # Could be OMDB imdb id (tt...) or TMDB id (tmdb-...)
    if movie_id.startswith('tt'):
        raw   = omdb(movie_id)
        movie = normalise_omdb(raw) if raw.get('Response') == 'True' else {}
        movie['imdbID'] = movie_id
    else:
        tid   = movie_id.replace('tmdb-', '')
        raw   = tmdb(f'/movie/{tid}', {'append_to_response': 'credits'})
        movie = normalise_tmdb(raw, detail=True)
        movie['imdbID'] = movie_id

    if not movie.get('Title'):
        return "Movie not found", 404

    conn = db()
    reviews = conn.execute(
        "SELECT username,rating,review,created_at FROM reviews WHERE movie_id=? ORDER BY created_at DESC",
        (movie_id,)).fetchall()
    in_watchlist = False
    if 'user' in session:
        in_watchlist = conn.execute(
            "SELECT id FROM watchlist WHERE username=? AND movie_id=?",
            (session['user'], movie_id)).fetchone() is not None
    conn.close()
    user_data = get_user(session['user']) if 'user' in session else {}
    return render_template('movie.html', movie=movie, reviews=reviews,
                           in_watchlist=in_watchlist, user_data=user_data)

# ── REVIEW ────────────────────────────────────────────────────────────────────
@app.route('/review', methods=['POST'])
def review():
    if 'user' not in session: return jsonify({"status": "login_required"})
    movie_id    = request.form['movie_id']
    rating      = request.form.get('rating') or 0
    review_text = request.form.get('review', '')
    title       = request.form.get('movie_title', '')
    poster      = request.form.get('movie_poster', '')
    genre       = request.form.get('movie_genre', '')
    now         = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if not title:
        if movie_id.startswith('tt'):
            raw   = omdb(movie_id)
            title = raw.get('Title', '')
            poster= raw.get('Poster', '')
            genre = raw.get('Genre', '')
        else:
            tid   = movie_id.replace('tmdb-', '')
            raw   = tmdb(f'/movie/{tid}')
            title = raw.get('title', '')
            poster= img(raw.get('poster_path'))
            genre = ', '.join(g['name'] for g in raw.get('genres', [])[:3])
    conn = db()
    conn.execute(
        "INSERT INTO reviews (movie_id,username,rating,review,genre,movie_title,movie_poster,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (movie_id, session['user'], int(rating), review_text, genre, title, poster, now))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

# ── WATCHLIST ─────────────────────────────────────────────────────────────────
@app.route('/watchlist/add', methods=['POST'])
def watchlist_add():
    if 'user' not in session: return jsonify({"status": "login_required"})
    data     = request.get_json()
    movie_id = data.get('movie_id')
    title    = data.get('title', '')
    poster   = data.get('poster', '')
    year     = data.get('year', '')
    if not title:
        if movie_id.startswith('tt'):
            raw    = omdb(movie_id)
            title  = raw.get('Title', '')
            poster = raw.get('Poster', '')
            year   = raw.get('Year', '')[:4]
        else:
            tid    = movie_id.replace('tmdb-', '')
            raw    = tmdb(f'/movie/{tid}')
            title  = raw.get('title', '')
            poster = img(raw.get('poster_path'))
            year   = (raw.get('release_date', ''))[:4]
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = db()
    try:
        conn.execute(
            "INSERT INTO watchlist (username,movie_id,movie_title,movie_poster,movie_year,added_at) VALUES (?,?,?,?,?,?)",
            (session['user'], movie_id, title, poster, year, now))
        conn.commit(); status = "added"
    except: status = "exists"
    conn.close()
    return jsonify({"status": status})

@app.route('/watchlist/remove', methods=['POST'])
def watchlist_remove():
    if 'user' not in session: return jsonify({"status": "login_required"})
    movie_id = request.get_json().get('movie_id')
    conn = db()
    conn.execute("DELETE FROM watchlist WHERE username=? AND movie_id=?", (session['user'], movie_id))
    conn.commit(); conn.close()
    return jsonify({"status": "removed"})

@app.route('/watchlist')
def watchlist():
    if 'user' not in session: return redirect('/login')
    conn = db()
    items = conn.execute(
        "SELECT movie_id,movie_title,movie_poster,movie_year,added_at FROM watchlist WHERE username=? ORDER BY added_at DESC",
        (session['user'],)).fetchall()
    conn.close()
    return render_template('watchlist.html', items=items, user_data=get_user(session['user']))

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user, pwd = request.form['username'], request.form['password']
        conn = db()
        try:
            conn.execute("INSERT INTO users (username,password) VALUES (?,?)", (user, pwd))
            conn.commit(); conn.close(); return redirect('/login')
        except:
            conn.close(); return render_template('register.html', error="Username taken")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user, pwd = request.form['username'], request.form['password']
        conn = db()
        result = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (user, pwd)).fetchone()
        conn.close()
        if result:
            session['user'] = user; return redirect('/')
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None); return redirect('/')

# ── PROFILE ───────────────────────────────────────────────────────────────────
@app.route('/profile')
def profile():
    if 'user' not in session: return redirect('/login')
    return render_template('profile.html', user_data=get_user(session['user']))

@app.route('/profile/update', methods=['POST'])
def profile_update():
    if 'user' not in session: return jsonify({"status": "error"})
    bio          = request.form.get('bio', '')
    avatar_color = request.form.get('avatar_color', '#e8a020')
    new_password = request.form.get('new_password', '')
    conn = db()
    if new_password:
        conn.execute("UPDATE users SET bio=?,avatar_color=?,password=? WHERE username=?",
                     (bio, avatar_color, new_password, session['user']))
    else:
        conn.execute("UPDATE users SET bio=?,avatar_color=? WHERE username=?",
                     (bio, avatar_color, session['user']))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/theme/set', methods=['POST'])
def theme_set():
    theme = request.get_json().get('theme', 'dark')
    session['theme'] = theme
    if 'user' in session:
        conn = db()
        conn.execute("UPDATE users SET theme=? WHERE username=?", (theme, session['user']))
        conn.commit(); conn.close()
    return jsonify({"status": "ok"})

# ── DIARY ─────────────────────────────────────────────────────────────────────
@app.route('/myreviews')
def myreviews():
    if 'user' not in session: return redirect('/login')
    conn = db()
    data = conn.execute(
        "SELECT movie_id,rating,review,movie_title,movie_poster,created_at FROM reviews WHERE username=? ORDER BY created_at DESC",
        (session['user'],)).fetchall()
    conn.close()
    movies = []
    for d in data:
        title, poster = d['movie_title'], d['movie_poster']
        if not title:
            mid = str(d['movie_id'])
            if mid.startswith('tt'):
                raw = omdb(mid); title = raw.get('Title','Unknown'); poster = raw.get('Poster','')
            else:
                raw = tmdb(f"/movie/{mid.replace('tmdb-','')}"); title = raw.get('title','Unknown'); poster = img(raw.get('poster_path'))
        movies.append({'movie_id':d['movie_id'],'rating':d['rating'],'review':d['review'],
                       'title':title,'poster':poster,'date':d['created_at'] or ''})
    return render_template('myreviews.html', movies=movies, username=session['user'], user_data=get_user(session['user']))

# ── ANALYTICS ─────────────────────────────────────────────────────────────────
@app.route('/analytics')
def analytics():
    if 'user' not in session: return redirect('/login')
    conn = db()
    rows            = conn.execute("SELECT rating,genre FROM reviews WHERE username=?", (session['user'],)).fetchall()
    total_watched   = conn.execute("SELECT COUNT(*) FROM reviews WHERE username=?", (session['user'],)).fetchone()[0]
    watchlist_count = conn.execute("SELECT COUNT(*) FROM watchlist WHERE username=?", (session['user'],)).fetchone()[0]
    conn.close()
    rating_dist = {0:0,1:0,2:0,3:0,4:0,5:0}
    genre_count = {}
    for r in rows:
        rating_dist[int(r['rating'] or 0)] += 1
        for g in (r['genre'] or '').split(','):
            g = g.strip()
            if g: genre_count[g] = genre_count.get(g, 0) + 1
    top_genres = sorted(genre_count.items(), key=lambda x: -x[1])[:6]
    rated = [r['rating'] for r in rows if r['rating'] and int(r['rating']) > 0]
    avg_rating = round(sum(rated)/len(rated), 1) if rated else 0
    return render_template('analytics.html',
        total_watched=total_watched, watchlist_count=watchlist_count,
        rating_dist=json.dumps(rating_dist), top_genres=json.dumps(top_genres),
        avg_rating=avg_rating, user_data=get_user(session['user']))

# ── ADVANCED SEARCH ───────────────────────────────────────────────────────────
@app.route('/advanced-search')
def advanced_search():
    return render_template('advanced_search.html', user_data=get_user(session['user']) if 'user' in session else {})

@app.route('/api/advanced-search')
def api_advanced_search():
    query      = request.args.get('q', '').strip()
    actor      = request.args.get('actor', '').strip()
    director   = request.args.get('director', '').strip()
    genre_name = request.args.get('genre', '').strip()
    year_from  = request.args.get('year_from', '').strip()
    year_to    = request.args.get('year_to', '').strip()
    mtype      = request.args.get('type', 'movie').strip()
    min_rating = request.args.get('min_rating', '').strip()
    sort_by    = request.args.get('sort', 'popularity.desc')

    results = []

    # ── Resolve actor/director → TMDB person ID ───────────────────────────────
    person_id = None
    person_key = actor or director
    if person_key:
        pdata   = tmdb('/search/person', {'query': person_key})
        persons = pdata.get('results', [])
        if not persons:
            return jsonify([])   # person not found → empty
        person_id = persons[0]['id']

    # ── Resolve genre name → TMDB genre ID ────────────────────────────────────
    genre_id = None
    if genre_name:
        genre_id = next((k for k, v in GENRE_MAP.items() if v.lower() == genre_name.lower()), None)

    # ── If title query given: use /search/movie ────────────────────────────────
    if query:
        for page in range(1, 4):
            data  = tmdb('/search/movie', {'query': query, 'page': page})
            batch = data.get('results', [])
            if not batch: break
            results.extend(batch)
            if len(results) >= 40: break

        # Post-filter by genre
        if genre_id:
            results = [m for m in results if genre_id in (m.get('genre_ids') or [])]
        # Post-filter by year range
        if year_from:
            results = [m for m in results if (m.get('release_date') or '0')[:4] >= year_from]
        if year_to:
            results = [m for m in results if (m.get('release_date') or '9999')[:4] <= year_to]
        # Post-filter by rating
        if min_rating:
            try: results = [m for m in results if float(m.get('vote_average') or 0) >= float(min_rating)]
            except: pass

    else:
        # ── No title: use /discover with all params ────────────────────────────
        endpoint = '/discover/tv' if mtype == 'series' else '/discover/movie'
        params = {'sort_by': sort_by, 'vote_count.gte': 20}
        if person_id : params['with_people'] = person_id
        if genre_id  : params['with_genres'] = genre_id
        if year_from : params['primary_release_date.gte'] = f"{year_from}-01-01"
        if year_to   : params['primary_release_date.lte'] = f"{year_to}-12-31"
        if min_rating: params['vote_average.gte'] = min_rating

        for page in range(1, 4):
            params['page'] = page
            data  = tmdb(endpoint, params)
            batch = data.get('results', [])
            if not batch: break
            results.extend(batch)
            if len(results) >= 40: break

    return jsonify([normalise_tmdb(m) for m in results[:24]])

if __name__ == '__main__':
    app.run(debug=True)
