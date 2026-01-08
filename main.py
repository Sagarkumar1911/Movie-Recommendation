from contextlib import asynccontextmanager
import os
import pickle
from typing import Optional ,List , Dict ,Any ,Tuple
import numpy as np
import pandas as pd
import httpx
from fastapi import FastAPI, HTTPException,Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from contextlib import asynccontextmanager 

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.themoviedb.org/3"
TMBD_img_500 = "https://image.tmdb.org/t/p/w500"
if not TMDB_API_KEY:
    raise ValueError("TMDB_API_KEY not found in environment variables.")

app = FastAPI(title="Movie Recommendation API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DF_PATH = os.path.join(BASE_DIR, "df.pkl")
INDICES_PATH = os.path.join(BASE_DIR, "indices.pkl")
TFIDF_MATRIX_PATH = os.path.join(BASE_DIR, "tfidf_matrix.pkl")
TFIDF_PATH = os.path.join(BASE_DIR, "tfidf.pkl")

df: Optional[pd.DataFrame] = None
indices_obj:Any =None
tfidf_matrix:Any =None
tfidf_obj:Any =None

TITLE_TO_INDEX: Optional[Dict[str, int]] = None

class TMBDMovieCard(BaseModel):
    id: int
    title: str
    poster_url: Optional[str]= None
    relase_date: Optional[str]= None
    vote_average: Optional[float]= None
    overview: Optional[str]= None
    
class TMBDMovieDetail(BaseModel):
    id: int
    title: str
    overview: Optional[str]= None
    release_date: Optional[str]= None
    genres: List[Dict[str, Any]]= None
    poster_url: Optional[str]= None
    backdrop_url: Optional[str]= None
       
   
class   TFIDFRecItem(BaseModel):
    title: str
    similarity_score: float
    tmbd:Optional[TMBDMovieCard]= None
    
class SearchBundleResponse(BaseModel):
    query: str
    movie_details: TMBDMovieDetail
    recommendations: List[TFIDFRecItem]
    genre_reccommendations: List[TMBDMovieCard]
    
    
def _norm_title(title: str) -> str:
    return title.strip().lower()    

def make_img_url(path: Optional[str]) -> Optional[str]:
    if path:
        return f"{TMBD_img_500}{path}"
    return None

async def tmbd_get(path :str, params: Dict[str, Any]={}) -> Dict[str, Any]:
    """
    Safe TMBD GET
    - Network errors -> 502
    -TmDB errors -> 500

    
    """
    q = dict(params)
    q["api_key"] = TMDB_API_KEY
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r= await client.get(f"{TMDB_BASE}{path}", params=q)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Network error: {str(e)}")  
    
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"TMDB API error: {r.text}")
    return r.json()
 
async def tmbd_cards_from_results(results: List[Dict],limit: int = 20 ) -> List[TMBDMovieCard]:
    out : list[TMBDMovieCard] = []
    for m in (results or [])[:limit]:
        out.append(
            TMBDMovieCard(
                id=m["id"],
                title=m["title"],
                poster_url=make_img_url(m.get("poster_path")),
                relase_date=m.get("release_date"),
                vote_average=m.get("vote_average"),
                overview=m.get("overview"),
            )
        )
    return out

async def get_movie_details_tmdb(movie_id: int) -> TMBDMovieDetail:
    data = await tmbd_get(f"/movie/{movie_id}", params={"language": "en-US"})
    return TMBDMovieDetail(
        id=data["id"],
        title=data["title"],
        overview=data.get("overview"),
        release_date=data.get("release_date"),
        genres=data.get("genres", [])or [],
        poster_url=make_img_url(data.get("poster_path")),
        backdrop_url=make_img_url(data.get("backdrop_path")),
    )
    
async def tmbd_search_movies(query: str, page: int =1) -> Dict[str, Any]:
    data = await tmbd_get(
        "/search/movie",
        params={
            "query": query,
            "page": page,
            "include_adult": False,
            "language": "en-US",
        },
    )
    return data


async def tmbd_search_first(query :str) -> Optional[dict]:
    data = await tmbd_search_movies(query, page=1)
    results = data.get("results", []) or []
    if results:
        return results[0]
    return None


def build_title_to_idx_map(indices: Any) -> Dict[str, int]:
    """
    indices.pkl can be:
    - dict(title -> index)
    - pandas Series (index=title, value=index)
    We normalize into TITLE_TO_IDX.
    """
    title_to_idx: Dict[str, int] = {}

    if isinstance(indices, dict):
        for k, v in indices.items():
            title_to_idx[_norm_title(k)] = int(v)
        return title_to_idx

    # pandas Series or similar mapping
    try:
        for k, v in indices.items():
            title_to_idx[_norm_title(k)] = int(v)
        return title_to_idx
    except Exception:
        # last resort: if it's a list-like etc.
        raise RuntimeError(
            "indices.pkl must be dict or pandas Series-like (with .items())"
        )
        
        
def get_local_idx_by_title(title: str) -> int:
    global TITLE_TO_IDX
    if TITLE_TO_IDX is None:
        raise HTTPException(status_code=500, detail="TF-IDF index map not initialized")
    key = _norm_title(title)
    if key in TITLE_TO_IDX:
        return int(TITLE_TO_IDX[key])
    raise HTTPException(
        status_code=404, detail=f"Title not found in local dataset: '{title}'"
    )
    
    
def tfidf_recommend_titles(
    query_title: str, top_n: int = 10
) -> List[Tuple[str, float]]:
    """
    Returns list of (title, score) from local df using cosine similarity on TF-IDF matrix.
    Safe against missing columns/rows.
    """
    global df, tfidf_matrix
    if df is None or tfidf_matrix is None:
        raise HTTPException(status_code=500, detail="TF-IDF resources not loaded")

    idx = get_local_idx_by_title(query_title)

    # query vector
    qv = tfidf_matrix[idx]
    scores = (tfidf_matrix @ qv.T).toarray().ravel()

    # sort descending
    order = np.argsort(-scores)

    out: List[Tuple[str, float]] = []
    for i in order:
        if int(i) == int(idx):
            continue
        try:
            title_i = str(df.iloc[int(i)]["title"])
        except Exception:
            continue
        out.append((title_i, float(scores[int(i)])))
        if len(out) >= top_n:
            break
    return out


async def attach_tmdb_card_by_title(title: str) -> Optional[TMBDMovieCard]:
    """
    Uses TMDB search by title to fetch poster for a local title.
    If not found, returns None (never crashes the endpoint).
    """
    try:
        m = await tmbd_search_first(title)
        if not m:
            return None
        return TMBDMovieCard(
            tmdb_id=int(m["id"]),
            title=m.get("title") or title,
            poster_url=make_img_url(m.get("poster_path")),
            release_date=m.get("release_date"),
            vote_average=m.get("vote_average"),
        )
    except Exception:
        return None
    
    
# STARTUP: LOAD PICKLES
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load your pickles (moved from load_pickles)
    global df, indices_obj, tfidf_matrix, tfidf_obj, TITLE_TO_IDX
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DF_PATH = os.path.join(BASE_DIR, "df.pkl")
    INDICES_PATH = os.path.join(BASE_DIR, "indices.pkl")
    TFIDF_MATRIX_PATH = os.path.join(BASE_DIR, "tfidf_matrix.pkl")
    TFIDF_PATH = os.path.join(BASE_DIR, "tfidf.pkl")
    
    # Load df
    with open(DF_PATH, "rb") as f:
        df = pickle.load(f)
    
    # Load indices
    with open(INDICES_PATH, "rb") as f:
        indices_obj = pickle.load(f)
    
    # Load TF-IDF matrix
    with open(TFIDF_MATRIX_PATH, "rb") as f:
        tfidf_matrix = pickle.load(f)
    
    # Load tfidf vectorizer
    with open(TFIDF_PATH, "rb") as f:
        tfidf_obj = pickle.load(f)
    
    # Build normalized map
    TITLE_TO_IDX = build_title_to_idx_map(indices_obj)
    
    # Sanity check
    if df is None or "title" not in df.columns:
        raise RuntimeError("df.pkl must contain a DataFrame with a 'title' column")
    
    
  
  
# =========================
# ROUTES
# =========================
@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- HOME FEED (TMDB) ----------
@app.get("/home", response_model=List[TMBDMovieCard])
async def home(
    category: str = Query("popular"),
    limit: int = Query(24, ge=1, le=50),
):
    """
    Home feed for Streamlit (posters).
    category:
      - trending (trending/movie/day)
      - popular, top_rated, upcoming, now_playing  (movie/{category})
    """
    try:
        if category == "trending":
            data = await tmbd_get("/trending/movie/day", {"language": "en-US"})
            return await tmbd_cards_from_results(data.get("results", []), limit=limit)

        if category not in {"popular", "top_rated", "upcoming", "now_playing"}:
            raise HTTPException(status_code=400, detail="Invalid category")

        data = await tmbd_get(f"/movie/{category}", {"language": "en-US", "page": 1})
        return await tmbd_cards_from_results(data.get("results", []), limit=limit)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Home route failed: {e}")


# ---------- TMDB KEYWORD SEARCH (MULTIPLE RESULTS) ----------
@app.get("/tmdb/search")
async def tmdb_search(
    query: str = Query(..., min_length=1),
    page: int = Query(1, ge=1, le=10),
):
    """
    Returns RAW TMDB shape with 'results' list.
    Streamlit will use it for:
      - dropdown suggestions
      - grid results
    """
    return await tmbd_search_movies(query=query, page=page)


# ---------- MOVIE DETAILS (SAFE ROUTE) ----------
@app.get("/movie/id/{tmdb_id}", response_model=TMBDMovieDetail)
async def movie_details_route(tmdb_id: int):
    return await get_movie_details_tmdb(tmdb_id)


# ---------- GENRE RECOMMENDATIONS ----------
@app.get("/recommend/genre", response_model=List[TMBDMovieCard])
async def recommend_genre(
    tmdb_id: int = Query(...),
    limit: int = Query(18, ge=1, le=50),
):
    """
    Given a TMDB movie ID:
    - fetch details
    - pick first genre
    - discover movies in that genre (popular)
    """
    details = await get_movie_details_tmdb(tmdb_id)
    if not details.genres:
        return []

    genre_id = details.genres[0]["id"]
    discover = await tmbd_get(
        "/discover/movie",
        {
            "with_genres": genre_id,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "page": 1,
        },
    )
    cards = await tmbd_cards_from_results(discover.get("results", []), limit=limit)
    return [c for c in cards if c.tmdb_id != tmdb_id]


# ---------- TF-IDF ONLY (debug/useful) ----------
@app.get("/recommend/tfidf")
async def recommend_tfidf(
    title: str = Query(..., min_length=1),
    top_n: int = Query(10, ge=1, le=50),
):
    recs = tfidf_recommend_titles(title, top_n=top_n)
    return [{"title": t, "score": s} for t, s in recs]


# ---------- BUNDLE: Details + TF-IDF recs + Genre recs ----------
@app.get("/movie/search", response_model=SearchBundleResponse)
async def search_bundle(
    query: str = Query(..., min_length=1),
    tfidf_top_n: int = Query(12, ge=1, le=30),
    genre_limit: int = Query(12, ge=1, le=30),
):
    """
    This endpoint is for when you have a selected movie and want:
      - movie details
      - TF-IDF recommendations (local) + posters
      - Genre recommendations (TMDB) + posters

    NOTE:
    - It selects the BEST match from TMDB for the given query.
    - If you want MULTIPLE matches, use /tmdb/search
    """
    best = await tmbd_search_first(query)
    if not best:
        raise HTTPException(
            status_code=404, detail=f"No TMDB movie found for query: {query}"
        )

    tmdb_id = int(best["id"])
    details = await get_movie_details_tmdb(tmdb_id)

    # 1) TF-IDF recommendations (never crash endpoint)
    tfidf_items: List[TFIDFRecItem] = []

    recs: List[Tuple[str, float]] = []
    try:
        # try local dataset by TMDB title
        recs = tfidf_recommend_titles(details.title, top_n=tfidf_top_n)
    except Exception:
        # fallback to user query
        try:
            recs = tfidf_recommend_titles(query, top_n=tfidf_top_n)
        except Exception:
            recs = []

    for title, score in recs:
        card = await attach_tmdb_card_by_title(title)
        tfidf_items.append(TFIDFRecItem(title=title, score=score, tmdb=card))

    # 2) Genre recommendations (TMDB discover by first genre)
    genre_recs: List[TMBDMovieCard] = []
    if details.genres:
        genre_id = details.genres[0]["id"]
        discover = await tmbd_get(
            "/discover/movie",
            {
                "with_genres": genre_id,
                "language": "en-US",
                "sort_by": "popularity.desc",
                "page": 1,
            },
        )
        cards = await tmbd_cards_from_results(
            discover.get("results", []), limit=genre_limit
        )
        genre_recs = [c for c in cards if c.tmdb_id != details.tmdb_id]

    return SearchBundleResponse(
        query=query,
        movie_details=details,
        tfidf_recommendations=tfidf_items,
        genre_recommendations=genre_recs,
    )