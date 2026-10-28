FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-agents.txt ./
RUN pip install --no-cache-dir -r requirements-agents.txt
COPY app.py ./
COPY pages/ pages/
COPY src/ src/
COPY data/docs/ data/docs/
COPY eval/reports/ eval/reports/
COPY .streamlit/config.toml .streamlit/config.toml
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
