import streamlit as st
import requests

# ==========================================
# CONFIG
# ==========================================
API_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="CineMatch AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================
# SESSION STATE
# ==========================================
st.session_state.setdefault("page", "home")
st.session_state.setdefault("selected_movie_query", None)
st.session_state.setdefault("search_term", "")

# ==========================================
# STYLES (HIGH CONTRAST / NETFLIX INSPIRED)
# ==========================================
st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at top, #1b1b1b, #0b0b0b);
    color: #ffffff;
}

h1, h2, h3 {
    color: #ff3d3d !important;
    font-weight: 800;
}

.movie-title {
    text-align: center;
    font-size: 0.9rem;
    font-weight: 600;
    color: #f5f5f5;
    margin-top: 6px;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #141414, #0c0c0c);
}

.stButton > button {
    background: linear-gradient(135deg, #ff3d3d, #b31212);
    color: white;
    border-radius: 6px;
    border: none;
    font-weight: 700;
}

.stButton > button:hover {
    background: linear-gradient(135deg, #ff5c5c, #d41414);
    transform: scale(1.02);
}

input {
    background-color: #1f1f1f !important;
    color: white !important;
    border: 1px solid #444 !important;
}

.stTabs [aria-selected="true"] {
    color: #ff3d3d !important;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# API HELPERS
# ==========================================
def get_home_feed(category="popular", limit=24):
    try:
        r = requests.get(f"{API_URL}/home", params={"category": category, "limit": limit})
        if r.status_code == 200:
            movies = r.json()
            # 🔥 filter backend warning garbage
            return [
                m for m in movies
                if "use_column_width" not in m.get("title", "").lower()
            ]
        return []
    except Exception as e:
        st.error(f"Backend error: {e}")
        return []

def search_tmdb(query):
    try:
        r = requests.get(f"{API_URL}/tmdb/search", params={"query": query})
        if r.status_code == 200:
            return r.json().get("results", [])
        return []
    except:
        return []

def get_movie_bundle(query):
    try:
        r = requests.get(f"{API_URL}/movie/search", params={"query": query})
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        st.error(e)
        return None

# ==========================================
# UI COMPONENTS
# ==========================================
def render_movie_grid(movies):
    cols = st.columns(5)

    for idx, movie in enumerate(movies):
        title = movie.get("title", "Unknown")
        poster = movie.get("poster_url") or movie.get("poster_path")

        if poster and not poster.startswith("http"):
            poster = f"https://image.tmdb.org/t/p/w500{poster}"

        if not poster:
            poster = "https://via.placeholder.com/500x750?text=No+Image"

        with cols[idx % 5]:
            st.image(poster, use_container_width=True)
            st.markdown(f"<div class='movie-title'>{title}</div>", unsafe_allow_html=True)

            if st.button("Select", key=f"select_{idx}", use_container_width=True):
                st.session_state.selected_movie_query = title
                st.session_state.page = "details"
                st.rerun()

# ==========================================
# PAGES
# ==========================================
def home_page():
    st.title("🎬 CineMatch AI")

    with st.sidebar:
        st.header("Discover")
        category = st.selectbox(
            "Category",
            ["popular", "trending", "top_rated", "upcoming", "now_playing"],
        )

    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input("Search movies", placeholder="Inception, Batman...")
    with col2:
        st.write("")
        if st.button("Search", use_container_width=True):
            if query:
                st.session_state.search_term = query
                st.session_state.page = "search"
                st.rerun()

    st.markdown("---")
    st.subheader(category.replace("_", " ").title())

    movies = get_home_feed(category)
    if movies:
        render_movie_grid(movies)
    else:
        st.warning("No movies found.")

def search_page():
    st.title("🔍 Search Results")

    if st.button("← Back"):
        st.session_state.page = "home"
        st.rerun()

    results = search_tmdb(st.session_state.search_term)
    if results:
        render_movie_grid(results)
    else:
        st.error("No results found.")

def details_page():
    if st.button("← Back"):
        st.session_state.page = "home"
        st.rerun()

    title = st.session_state.selected_movie_query
    if not title:
        st.error("No movie selected.")
        return

    data = get_movie_bundle(title)
    if not data:
        return

    details = data.get("movie_details", {})
    tfidf_recs = data.get("recommendations", [])
    genre_recs = data.get("genre_reccommendations", [])

    col1, col2 = st.columns([1, 2])
    with col1:
        if details.get("poster_url"):
            st.image(details["poster_url"], use_container_width=True)

    with col2:
        st.title(details.get("title"))
        st.write(details.get("overview", "No overview available"))

    st.markdown("---")
    tab1, tab2 = st.tabs(["🔥 AI Based", "🍿 Genre Based"])

    with tab1:
        render_movie_grid([r.get("tmbd", {}) for r in tfidf_recs if r.get("tmbd")])

    with tab2:
        render_movie_grid(genre_recs)

# ==========================================
# ROUTER
# ==========================================
if st.session_state.page == "home":
    home_page()
elif st.session_state.page == "search":
    search_page()
elif st.session_state.page == "details":
    details_page()
