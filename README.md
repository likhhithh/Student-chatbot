cd student-study-chatbot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

source .venv/bin/activate
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 1

source .venv/bin/activate
export API_BASE_URL="http://localhost:8000"
streamlit run ui/streamlit_app.py
