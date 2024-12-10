FROM arm64/python:3.0-slim
WORKDIR /app
COPY . /app
RUN pip install -- no-cache-dir -r requirements.txt
CMD ["python", "main.py"]