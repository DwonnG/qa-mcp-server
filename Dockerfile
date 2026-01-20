FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy configuration templates (user should mount their own config.py)
COPY config_example.py ./config_example.py

# Copy application package
COPY qa_mcp/ ./qa_mcp/

# Copy entry point
COPY run.py .

# Run the MCP server
CMD ["python", "run.py"]
