import streamlit as st
import requests

# ==========================================
# CONFIG
# ==========================================
# Use your live Render URL here
API_URL = "https://movie-recommendation-thcv.onrender.com" 

st.set_page_config(
    page_title="CineMatch AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================
# SESSION STATE
# ==========================================
if "page" not in st.session_state:
    st.session_state.page = "home"
if "selected_movie_query" not in st.session_state:
    st.session_state.selected_movie_query = None
if "search_term" not in st.session_state:
    st.session_state.search_term = ""

# ==========================================
# STYLES (DOUBLE TONE: DEEP CHARCOAL + VIBRANT RED)
# ==========================================
st.markdown("""
<style>
    /* Global Background & Font */
    .stApp {
        background-color: #0e0e0e; /* Deep Charcoal */
        color: #e0e0e0;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #000000;
        border-right: 1px solid #222;
    }
    
    /* Headings */
    h1, h2, h3 {
        color: #ffffff !important;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    h1 span {
        color: #E50914; /* Red Brand Accent */
    }

    /* Input Fields (Search) */
    .stTextInput > div > div > input {
        background-color: #1f1f1f;
        color: white;
        border: 1px solid #333;
        border-radius: 4px;
    }
    .stTextInput > div > div > input:focus {
        border-color: #E50914;
        box-shadow: 0 0 8px rgba(229, 9, 20, 0.4);
    }
    
    /* Primary Buttons (Red) */
    .stButton > button {
        background-color: #E50914;
        color: white;
        border: none;
        border-radius: 4px;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #ff1f2a;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(229, 9, 20, 0.4);
    }
    
    /* Movie Titles */
    .movie-title {
        color: #fff;
        font-size: 0.9rem;
        font-weight: 500;
        text-align: center;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-top: 8px;
        margin-bottom: 4px;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
        border-bottom: 1px solid #333;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border: none;
        color: #888;
    }
    .stTabs [aria-selected="true"] {
        color: #E50914 !important;
        border-bottom: 2px solid #E50914 !important;
    }
    
    /* Sidebar Selectbox */
    div[data-baseweb="select"] > div {
        background-color: #1f1f1f;
        border-color: #333;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# API HELPERS
# ==========================================
def get_home_feed(category="popular", limit=24):
    try:
        r = requests.get(f"{API_URL}/home", params={"category": category, "limit": limit}, timeout=5)
        if r.status_code == 200:
            movies = r.json()
            # Safety filter
            return [m for m in movies if isinstance(m, dict) and "title" in m]
        return []
    except Exception:
        return []

def search_tmdb(query):
    try:
        r = requests.get(f"{API_URL}/tmdb/search", params={"query": query}, timeout=5)
        if r.status_code == 200:
            return r.json().get("results", [])
        return []
    except:
        return []

def get_movie_bundle(query):
    try:
        r = requests.get(f"{API_URL}/movie/search", params={"query": query}, timeout=8)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None

# ==========================================
# UI COMPONENTS
# ==========================================
def render_movie_grid(movies):
    cols = st.columns(5) # 5-column grid
    for idx, movie in enumerate(movies):
        title = movie.get("title", "Unknown")
        poster_path = movie.get("poster_url") or movie.get("poster_path")
        
        # Handle Poster URL
        if poster_path and not poster_path.startswith("http"):
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        elif poster_path:
            poster_url = poster_path
        else:
            poster_url = "https://via.placeholder.com/500x750?text=No+Image"

        with cols[idx % 5]:
            # Clean "Card" Layout
            st.image(poster_url, use_container_width=True)
            st.markdown(f"<div class='movie-title' title='{title}'>{title}</div>", unsafe_allow_html=True)
            
            # Button Key must be unique
            if st.button("Details", key=f"btn_{idx}_{title[:5]}", use_container_width=True):
                st.session_state.selected_movie_query = title
                st.session_state.page = "details"
                st.rerun()
            st.write("") # Spacer

# ==========================================
# PAGES
# ==========================================
def home_page():
    # Header Section
    col_logo, col_search = st.columns([1, 2])
    with col_logo:
        st.markdown("# CineMatch <span>AI</span>", unsafe_allow_html=True)
    
    with col_search:
        st.write("") # Spacer for vertical alignment
        c1, c2 = st.columns([3, 1])
        with c1:
            q = st.text_input("Search", placeholder="Search for movies...", label_visibility="collapsed")
        with c2:
            if st.button("SEARCH", use_container_width=True):
                if q:
                    st.session_state.search_term = q
                    st.session_state.page = "search"
                    st.rerun()

    st.markdown("---")

    # Sidebar
    with st.sidebar:
        st.markdown("### 🧭 Discover")
        category = st.selectbox(
            "Browse by",
            ["popular", "trending", "top_rated", "upcoming", "now_playing"],
            label_visibility="collapsed"
        )
        st.markdown("---")
        st.info("Select a category to refresh the movie feed.")

    # Main Feed
    st.markdown(f"### {category.replace('_', ' ').title()}")
    movies = get_home_feed(category)
    
    if movies:
        render_movie_grid(movies)
    else:
        st.warning("Unable to load movies. Backend might be sleeping.")

def search_page():
    c1, c2 = st.columns([1, 6])
    with c1:
        if st.button("← Back"):
            st.session_state.page = "home"
            st.rerun()
    with c2:
        st.markdown(f"## Results for *'{st.session_state.search_term}'*")
    
    results = search_tmdb(st.session_state.search_term)
    if results:
        render_movie_grid(results)
    else:
        st.warning("No results found.")

def details_page():
    if st.button("← Back to Home"):
        st.session_state.page = "home"
        st.rerun()

    query_title = st.session_state.selected_movie_query
    data = get_movie_bundle(query_title)

    if not data:
        st.error("Could not load movie details.")
        return

    details = data.get("movie_details", {})
    recs_ai = [x['tmbd'] for x in data.get("recommendations", []) if x.get('tmbd')]
    recs_genre = data.get("genre_reccommendations", [])

    # Movie Details Hero
    st.markdown(f"## {details.get('title', 'Untitled')}")
    
    hero_c1, hero_c2 = st.columns([1, 3])
    
    with hero_c1:
        poster = details.get("poster_url")
        if poster:
            st.image(poster, use_container_width=True)
        else:
            st.write("No Image")
            
    with hero_c2:
        st.markdown("#### Overview")
        st.write(details.get("overview", "No overview available."))
        
        st.markdown("---")
        c_stats1, c_stats2 = st.columns(2)
        with c_stats1:
            st.markdown(f"**📅 Release Date:** {details.get('release_date', 'N/A')}")
        with c_stats2:
            st.markdown(f"**⭐ Rating:** {details.get('vote_average', 'N/A')}/10")

    # Recommendations Tabs
    st.markdown("### More Like This")
    tab1, tab2 = st.tabs(["🔥 AI Recommendations", "🍿 Similar Genre"])
    
    with tab1:
        if recs_ai:
            render_movie_grid(recs_ai)
        else:
            st.info("No AI recommendations available.")
            
    with tab2:
        if recs_genre:
            render_movie_grid(recs_genre)
        else:
            st.info("No genre recommendations available.")

# ==========================================
# MAIN ROUTER
# ==========================================
if st.session_state.page == "home":
    home_page()
elif st.session_state.page == "search":
    search_page()
elif st.session_state.page == "details":
    details_page()