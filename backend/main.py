from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from utils.file_utils import init_dirs

app = FastAPI(title="RepoPulse API")

# Add CORS middleware to allow frontend to connect easily
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize data and temp directories
init_dirs()

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
