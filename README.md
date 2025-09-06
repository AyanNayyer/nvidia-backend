# NVIDIA NeMo Guardrails with FastAPI

A secure AI conversational system using NVIDIA NeMo Guardrails and FastAPI for scalable, safe AI interactions.

## Features

- **Safety Guardrails**: Topic restrictions, toxicity filtering, response length control
- **Citation Enforcement**: Requires citations for external facts
- **Async Processing**: FastAPI with async support for high concurrency
- **ChatGroq Integration**: Powered by ChatGroq API
- **Comprehensive Logging**: Detailed logging for monitoring and debugging

## Setup

1. Install dependencies:
```bash
pip install -e .
```

2. Create `.env` file with your ChatGroq API key:
```
CHATGROQ_API_KEY=your_api_key_here
```

3. Run the application:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Usage

Send POST requests to `/chat` with:
```json
{
    "message": "Your message here",
    "user_id": "optional_user_id"
}
```

## Guardrails

- Blocks political discussions
- Prevents illegal content
- Filters toxic language
- Limits response length
- Enforces citations for external facts
