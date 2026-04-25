---
tags: [decision, llm, integration, assessment, architecture]
created: 2026-04-22
updated: 2026-04-22
sources: [llama.cpp/, models/, Coding-Projects/kteam-dj-be/, Coding-Projects/kteam-fe-chief/]
related: [[ADR-001-local-llm]], [[ADR-002-dual-model]], [[ADR-003-llama-cpp]], [[local-ai-stack]], [[qwen3.6-35b-a3b]]
status: stable
---

# ADR-004: Open-Source LLM Integration Assessment for K-Team

## Summary

This assessment evaluates open-source LLM integration approaches for the K-Team system (kteam-dj-be + kteam-fe-chief). It covers five major use cases: invoice scanning/OCR, AI chat bot, business automations, technical architecture, and recommended models. All recommendations assume **local-only deployment** on existing RTX 3090 (24GB VRAM) infrastructure with llama.cpp as the inference engine.

## 1. Invoice Scanning / OCR + Data Extraction

### Approach Overview

There are two viable architectures for invoice data extraction:

**Architecture A: Vision LLM Direct (Recommended for Phase 1)**
- Convert PDF pages to images (PyMuPDF / pdf2image)
- Pass images directly to a vision-capable LLM via llama.cpp multimodal API
- Prompt the LLM to extract structured JSON fields

**Architecture B: OCR + LLM Extraction (Recommended for Phase 2)**
- Use a dedicated OCR engine (PaddleOCR, Tesseract, or PaddleOCR-VL) to extract text
- Pass extracted text + original image to LLM for structured extraction
- Better accuracy for heavily scanned/low-quality documents

### Recommended Models for Invoice OCR

| Model | Type | VRAM (Q4) | Accuracy | Notes |
|-------|------|-----------|----------|-------|
| Qwen2.5-VL-3B-Instruct | Vision LLM | ~6GB | High | Best balance: small enough for RTX 3090, excellent OCR capability, supports JSON output |
| Qwen2.5-VL-7B-Instruct | Vision LLM | ~14GB | Very High | Best accuracy, fits on RTX 3090 with Q4_K_M quantization |
| Qwen2.5-VL-32B-Instruct | Vision LLM | ~20GB | Highest | Fits in 24GB with Q4_K_M but leaves little headroom for other tasks |
| Qwen3.6-35B-A3B (existing) | Vision MoE | ~12GB | Medium | Already deployed, vision-capable, but not optimized for OCR tasks |
| GLM-OCR | Vision OCR | ~7GB | High | Specialized OCR model, purpose-built for document text extraction |
| PaddleOCR-VL | Vision OCR | ~7GB | High | Specialized OCR, works well with llama.cpp |

**Recommendation:** Start with `Qwen2.5-VL-7B-Instruct:Q4_K_M` (14GB VRAM) for invoice scanning. It provides the best accuracy/speed tradeoff and leaves ~10GB VRAM for concurrent operations. The existing Qwen3.6-35B-A3B can handle simple invoice extraction as a fallback but will underperform on scanned/low-quality documents.

### Implementation Details

**Step 1: PDF Processing Pipeline**

```python
# Invoice OCR processor (Django app)
import fitz  # PyMuPDF
from PIL import Image
import io
import requests

def pdf_to_images(pdf_bytes, dpi=300):
    """Convert PDF pages to images for vision LLM processing."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images

def extract_invoice_data_vlm(pdf_path, llm_url="http://127.0.0.1:11434"):
    """Extract structured data from invoice PDF using vision LLM."""
    images = pdf_to_images(open(pdf_path, "rb").read(), dpi=300)

    # Build multimodal prompt
    messages = [{
        "role": "user",
        "content": "Extract all invoice data from this image. Return ONLY valid JSON with this schema: {\"vendor_name\": string, \"invoice_number\": string, \"invoice_date\": string, \"gst_number\": string, \"line_items\": [{\"sku\": string, \"description\": string, \"qty\": number, \"rate\": number, \"amount\": number}], \"subtotal\": number, \"gst_amount\": number, \"total\": number, \"payment_terms\": string}",
    }]

    # Convert images to base64 for llama.cpp API
    image_b64 = []
    for img in images[:1]:  # Process first page first
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_b64.append(buf.getvalue().hex())

    # Call llama.cpp multimodal API
    response = requests.post(f"{llm_url}/v1/chat/completions", json={
        "model": "Qwen2.5-VL-7B-Instruct",
        "messages": messages,
        "images": image_b64,
        "max_tokens": 2048,
        "temperature": 0.1,  # Low temp for structured output
        "response_format": {"type": "json_object"},
    })
    return response.json()
```

**Step 2: JSON Validation & DB Storage**

```python
# Django model for extracted invoice data
from django.db import models
from django.core.validators import MinValueValidator
import uuid

class ExtractedInvoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    original_pdf = models.FileField(upload_to="invoices/originals/")
    source_collection = models.CharField(max_length=50)  # kuroadmin or kurostaff
    business_group = models.CharField(max_length=100)
    vendor_name = models.CharField(max_length=200, null=True, blank=True)
    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    gst_number = models.CharField(max_length=50, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, null=True)
    gst_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True)
    payment_terms = models.TextField(null=True, blank=True)
    line_items_json = models.JSONField(null=True)
    extraction_confidence = models.FloatField(null=True)  # LLM confidence score
    status = models.CharField(max_length=20, default="pending_review")  # pending, confirmed, rejected
    extracted_by = models.CharField(max_length=50, default="Qwen2.5-VL-7B")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "extracted_invoices"
```

### Accuracy Expectations

| Document Type | Expected Accuracy | Notes |
|---------------|------------------|-------|
| Digital PDF invoices (text-based) | 95-98% | Clean text, consistent layout |
| Scanned invoices (300 DPI) | 85-92% | Depends on scan quality |
| Handwritten invoices | 60-75% | Not recommended for automation |
| Multi-page invoices | 80-90% | Per-page extraction, needs aggregation |

### Processing Time & Hardware

| Model | Image Size | Processing Time | VRAM |
|-------|-----------|-----------------|------|
| Qwen2.5-VL-3B (Q4) | 1024x1024 | 2-3 seconds | ~6GB |
| Qwen2.5-VL-7B (Q4) | 1024x1024 | 4-6 seconds | ~14GB |
| Qwen2.5-VL-32B (Q4) | 1024x1024 | 12-18 seconds | ~20GB |
| Qwen3.6-35B-A3B (existing) | 1024x1024 | 3-5 seconds | ~12GB |

### Integration with Existing Qwen3.6-35B-A3B

The existing Qwen3.6-35B-A3B can serve as a **fallback** for simple invoice extraction since it has vision capabilities (mmproj available at `/home/chief/models/qwen3.6-35b-a3b-gguf/mmproj-F16.gguf`). However:

- It is NOT optimized for OCR tasks
- It may struggle with complex layouts and tables
- Use it only for digital PDFs with clean text
- For scanned invoices, use Qwen2.5-VL-7B as primary

## 2. AI Chat Bot / Assistant

### 2a. Customer Support Chat Bot for Staff Portal

**Architecture:** Django backend as API layer, llama.cpp as LLM backend, React frontend component.

**Available Models:**
| Model | Use Case | VRAM | Speed |
|-------|----------|------|-------|
| Qwen3.6-35B-A3B (existing) | General support queries | ~12GB | Fast (3B active) |
| Qwen2.5-7B-Instruct | Fast responses | ~5GB | Very fast |
| Qwen2.5-14B-Instruct | Balanced | ~9GB | Fast |
| Qwen2.5-32B-Instruct | Complex queries | ~19GB | Medium |

**Django Integration Pattern:**

```python
# kteam_ai/apps.py - New Django app for LLM features
from django.db import models
from django.conf import settings
import requests
import json
from django.utils import timezone

class ChatMessage(models.Model):
    """Conversation history stored in PostgreSQL."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey('users.CustomUser', on_delete=models.CASCADE)
    business_group = models.CharField(max_length=100)
    session_id = models.UUIDField()
    role = models.CharField(max_length=10)  # 'user' or 'assistant'
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_messages"
        indexes = [
            models.Index(fields=['session_id', 'created_at']),
        ]

class LLMService:
    """Service class for LLM API calls."""

    MODELS = {
        "fast": {"url": "http://127.0.0.1:11434", "model": "qwen3.6-35b-a3b"},
        "reasoning": {"url": "http://127.0.0.1:11435", "model": "deepseek-r1-distill-qwen-32b"},
        "vl": {"url": "http://127.0.0.1:11434", "model": "qwen2.5-vl-7b-instruct"},
    }

    @classmethod
    def chat(cls, session_id, user_id, messages, use_reasoning=False):
        config = cls.MODELS["reasoning" if use_reasoning else "fast"]
        payload = {
            "model": config["model"],
            "messages": messages,
            "stream": False,
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        resp = requests.post(f"{config['url']}/v1/chat/completions", json=payload, timeout=60)
        return resp.json()["choices"][0]["message"]["content"]

    @classmethod
    def chat_stream(cls, session_id, user_id, messages, use_reasoning=False):
        """Streaming response for real-time chat UI."""
        config = cls.MODELS["reasoning" if use_reasoning else "fast"]
        resp = requests.post(
            f"{config['url']}/v1/chat/completions",
            json={"model": config["model"], "messages": messages, "stream": True, "temperature": 0.3},
            stream=True, timeout=120
        )
        for line in resp.iter_lines():
            if line:
                yield line
```

**Django API View:**

```python
# kteam_ai/views.py
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.response import Response
from rest_framework import status
from knox.auth import TokenAuthentication
from .services import LLMService
from .models import ChatMessage
import uuid

@api_view(["POST"])
@authentication_classes([TokenAuthentication])
def chat_completion(request):
    """Staff chat bot endpoint."""
    session_id = request.data.get("session_id", str(uuid.uuid4()))
    user = request.user

    # Build message history from DB
    history = ChatMessage.objects.filter(
        session_id=session_id,
        user=user
    ).order_by("created_at")[:20]  # Last 20 messages for context

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.data["message"]})

    # Save user message
    ChatMessage.objects.create(session_id=session_id, user=user, role="user", content=request.data["message"])

    # Get LLM response
    response_text = LLMService.chat(session_id, user.id, messages)

    # Save assistant response
    ChatMessage.objects.create(session_id=session_id, user=user, role="assistant", content=response_text)

    return Response({"session_id": session_id, "response": response_text})
```

**System Prompt for Staff Portal:**

```python
SYSTEM_PROMPT = """You are Kuro Assistant, a helpful AI assistant for Kuro Gaming staff.
You have access to the following business context:
- The company sells gaming PCs, peripherals, and prebuilt configurations
- You can help with invoice queries, inventory checks, product details, order status
- You should always reference real data from the database, never make up numbers
- If you don't know something, say so and suggest the staff member check with their manager
- Keep responses concise and professional
- Always use INR (Rs.) for currency values
- GST is applicable as per Indian tax regulations"""
```

### 2b. Internal Knowledge Base Q&A (RAG)

**Architecture:** Leverage existing RAGFlow deployment with Qwen3-Embedding-0.6B.

**Stack:**
- RAGFlow (already deployed, port 9380)
- Qwen3-Embedding-0.6B via TEI (Text Embedding Inference)
- Elasticsearch (RAGFlow's search backend)
- MinIO for document storage

**Integration with Django:**

```python
# kteam_ai/rag_client.py
import requests

class RAGClient:
    """Client for RAGFlow knowledge base."""

    BASE_URL = "http://127.0.0.1:9380/api/v1"

    def query(self, question, kb_id=None, top_k=5):
        """Query the knowledge base."""
        resp = requests.post(f"{self.BASE_URL}/retrieval", json={
            "question": question,
            "knowledge_base_id": kb_id,
            "top_k": top_k,
            "rerank_model": "",  # Use embedding model only
            "chunk_size": 100,
        })
        return resp.json()

    def index_document(self, file_path, kb_id, document_name):
        """Index a document in the knowledge base."""
        with open(file_path, "rb") as f:
            resp = requests.post(f"{self.BASE_URL}/dataset/upload_file", json={
                "knowledge_base_id": kb_id,
                "name": document_name,
            }, files={"file": f})
        return resp.json()
```

**Knowledge Base Categories:**
1. **Product Catalog** - Product specs, presets, pricing
2. **Invoice Policies** - GST rules, payment terms, credit notes
3. **Inventory Rules** - Stock management, transfer policies
4. **HR Policies** - Leave rules, attendance, salary structure
5. **Order Management** - Order processing, shipping, returns

### 2c. Inventory/Invoice Lookup Assistant

**Function Calling Approach:** Use llama.cpp's function calling to let the LLM query the Django API directly.

```python
# kteam_ai/tools.py - Function definitions for LLM tool use
from kuroadmin.models import StockRegister
from kurostaff.models import InwardInvoice
from django.db import connection
import json

INVENTORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_product",
            "description": "Search for a product by SKU, name, or category",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Product name, SKU, or category to search"},
                    "entity": {"type": "string", "description": "Product entity (kuro, peripherals, etc.)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_invoice",
            "description": "Find invoice by invoice number, vendor, or date range",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_number": {"type": "string", "description": "Invoice number"},
                    "vendor_name": {"type": "string", "description": "Vendor name"},
                    "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "Check current stock level for a product",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Product SKU"}
                },
                "required": ["sku"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_financial_summary",
            "description": "Get financial summary for a period",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Period (daily, weekly, monthly, yearly)"},
                    "from_date": {"type": "string", "description": "Start date"},
                    "to_date": {"type": "string", "description": "End date"}
                },
                "required": ["period"]
            }
        }
    }
]

def execute_tool_call(tool_name, arguments):
    """Execute a tool call and return results."""
    args = json.loads(arguments) if isinstance(arguments, str) else arguments

    if tool_name == "lookup_product":
        # Query MongoDB via djongo or direct pymongo
        from pymongo import MongoClient
        client = MongoClient("mongodb://127.0.0.1:27017/kuropurchase")
        collection = client.stock_register
        results = list(collection.find(
            {"$or": [
                {"sku": {"$regex": args.get("query", ""), "$options": "i"}},
                {"product_name": {"$regex": args.get("query", ""), "$options": "i"}},
            ]},
            {"sku": 1, "product_name": 1, "stock": 1, "price": 1}
        ).limit(10))
        return json.dumps(results)

    elif tool_name == "lookup_invoice":
        # Query MongoDB for invoices
        from pymongo import MongoClient
        client = MongoClient("mongodb://127.0.0.1:27017/kuropurchase")
        collection = client.inwardInvoices
        query = {}
        if args.get("invoice_number"):
            query["invoice_no"] = args["invoice_number"]
        if args.get("vendor_name"):
            query["vendor_name"] = {"$regex": args["vendor_name"], "$options": "i"}
        results = list(collection.find(query).limit(20))
        return json.dumps(results)

    elif tool_name == "check_stock":
        from pymongo import MongoClient
        client = MongoClient("mongodb://127.0.0.1:27017/kuropurchase")
        collection = client.stock_register
        result = collection.find_one({"sku": args["sku"]})
        return json.dumps(result)

    elif tool_name == "get_financial_summary":
        # Query PostgreSQL for financial data
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT SUM(amount) as total, COUNT(*) as count
                FROM kuroadmin_inwardinvoices
                WHERE created_at BETWEEN %s AND %s
            """, [args.get("from_date"), args.get("to_date")])
            row = cursor.fetchone()
            return json.dumps({"total_amount": row[0], "invoice_count": row[1]})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})
```

**LLM Request with Function Calling:**

```python
# In the chat view, after getting initial user message:
def chat_with_tools(session_id, user_id, messages):
    # First call: let LLM decide if it needs to use tools
    payload = {
        "model": "qwen3.6-35b-a3b",
        "messages": messages,
        "tools": INVENTORY_TOOLS,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": 1024,
    }
    resp = requests.post("http://127.0.0.1:11434/v1/chat/completions", json=payload)
    data = resp.json()["choices"][0]["message"]

    if data.get("tool_calls"):
        # Execute tool calls
        for tool_call in data["tool_calls"]:
            result = execute_tool_call(tool_call["function"]["name"], tool_call["function"]["arguments"])
            messages.append(data)  # Add assistant's tool call
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result
            })

        # Second call: get final answer with tool results
        resp2 = requests.post("http://127.0.0.1:11434/v1/chat/completions", json={
            "model": "qwen3.6-35b-a3b",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        })
        return resp2.json()["choices"][0]["message"]["content"]

    return data.get("content", "")
```

### Conversation History Management

- Store in PostgreSQL `chat_messages` table with session-based partitioning
- Keep last 20 messages per session for context (configurable)
- Implement session TTL (30 days default, auto-prune older sessions)
- Use Meilisearch for searching past conversations (optional)

### Safety and Guardrails

1. **System prompt guardrails** - Explicit instructions about data access and response boundaries
2. **Input filtering** - Filter for PII, SQL injection patterns, prompt injection
3. **Output validation** - Validate LLM responses before displaying in UI
4. **Rate limiting** - Per-user rate limits via Django middleware
5. **Audit logging** - Log all LLM interactions for compliance
6. **Data isolation** - Ensure LLM can only access data the user has permission to see

```python
# kteam_ai/middleware.py
import re

class LLMGuardMiddleware:
    """Input/output filtering for LLM interactions."""

    DANGEROUS_PATTERNS = [
        r"system prompt",
        r"ignore all instructions",
        r"show me your",
        r"<\|begin_of\|>",
        r"roleplay as",
        r"bypass",
    ]

    @classmethod
    def sanitize_input(cls, text):
        """Filter dangerous input patterns."""
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return None  # Block the request
        return text

    @classmethod
    def sanitize_output(cls, text):
        """Filter dangerous output patterns."""
        # Remove any raw system prompts or code that shouldn't be shown
        text = re.sub(r"<\|begin_of\|>.*?<\|end_of\|>", "", text, flags=re.DOTALL)
        return text
```

## 3. Automations

### 3a. Auto-Classification of Products/Categories

**Model:** Qwen2.5-7B-Instruct (fast, accurate for categorization)

```python
# kteam_ai/classification.py
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_category": {
            "type": "string",
            "enum": ["Desktops", "Laptops", "Peripherals", "Components", "Accessories", "Networking", "Storage"]
        },
        "sub_category": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"}
    },
    "required": ["primary_category", "tags"]
}

def classify_product(product_name, description, existing_categories):
    """Classify a product using LLM."""
    response = requests.post("http://127.0.0.1:11434/v1/chat/completions", json={
        "model": "qwen2.5-7b-instruct",
        "messages": [{
            "role": "system",
            "content": "You are a product classification assistant for a gaming PC company. Classify products into categories."
        }, {
            "role": "user",
            "content": f"Product: {product_name}\nDescription: {description}\n\nExisting categories: {existing_categories}\n\nClassify this product. Return ONLY JSON matching this schema: {json.dumps(CLASSIFICATION_SCHEMA, indent=2)}"
        }],
        "max_tokens": 512,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    })
    return json.loads(response.json()["choices"][0]["message"]["content"])
```

### 3b. Smart Search Suggestions

**Approach:** Use existing MeiliSearch + LLM query expansion.

```python
# kteam_ai/search.py
def smart_search(query, context="products"):
    """Enhance search with LLM-generated query expansions."""
    # Expand query using LLM
    resp = requests.post("http://127.0.0.1:11434/v1/chat/completions", json={
        "model": "qwen2.5-7b-instruct",
        "messages": [{
            "role": "user",
            "content": f"Generate search query variations for: '{query}' in the context of {context}. Return ONLY a JSON array of 5-7 related search terms. Examples: if query is 'RTX gaming PC', return ['gaming graphics card', 'NVIDIA RTX', 'gaming desktop', 'high performance PC']."
        }],
        "max_tokens": 256,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    })
    expanded_terms = json.loads(resp.json()["choices"][0]["message"]["content"])

    # Combine with MeiliSearch
    results = []
    for term in [query] + expanded_terms:
        meili_results = requests.post("http://127.0.0.1:8000/kuroadmin/search", json={
            "query": term,
            "index": context,
        })
        results.extend(meili_results.json().get("results", []))

    # Deduplicate and rank
    return deduplicate_and_rank(results)
```

### 3c. Automated Report Generation

**Model:** Qwen3.6-35B-A3B (existing, good for long-form text generation)

```python
# kteam_ai/reports.py
def generate_monthly_report(month, year):
    """Generate a monthly business report using LLM."""
    # Gather data from databases
    financial_data = get_financial_data(month, year)
    inventory_data = get_inventory_data(month, year)
    sales_data = get_sales_data(month, year)

    prompt = f"""Generate a monthly business report for {month} {year}.

Financial Summary:
{json.dumps(financial_data, indent=2)}

Inventory Summary:
{json.dumps(inventory_data, indent=2)}

Sales Summary:
{json.dumps(sales_data, indent=2)}

Requirements:
- Write in professional business English
- Include key highlights and trends
- Note any anomalies or concerns
- Suggest action items
- Keep under 1500 words
- Use INR (Rs.) for all currency values"""

    resp = requests.post("http://127.0.0.1:11434/v1/chat/completions", json={
        "model": "qwen3.6-35b-a3b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.5,
    })
    return resp.json()["choices"][0]["message"]["content"]
```

### 3d. Anomaly Detection in Financial Data

**Approach:** Use DeepSeek-R1-Distill-Qwen-32B (reasoning model) for financial analysis.

```python
# kteam_ai/anomaly_detection.py
def detect_financial_anomalies(period_days=30):
    """Detect anomalies in financial data using reasoning LLM."""
    # Get recent transaction data
    transactions = get_recent_transactions(period_days)

    resp = requests.post("http://127.0.0.1:11435/v1/chat/completions", json={
        "model": "deepseek-r1-distill-qwen-32b",
        "messages": [{
            "role": "system",
            "content": "You are a financial analyst. Analyze the data for anomalies, unusual patterns, and potential issues."
        }, {
            "role": "user",
            "content": f"Analyze these transactions for anomalies:\n{json.dumps(transactions, indent=2)}\n\nLook for: unusual amounts, duplicate entries, unexpected patterns, outliers, timing anomalies.\nReturn JSON: {{\"anomalies\": [{\"type\": string, \"description\": string, \"severity\": string, \"transaction_ids\": [string]}], \"summary\": string}}"
        }],
        "max_tokens": 4096,
        "temperature": 0.1,
    })
    return json.loads(resp.json()["choices"][0]["message"]["content"])
```

### 3e. Bulk Data Validation

```python
# kteam_ai/validation.py
def validate_bulk_products(products_data):
    """Validate bulk product import data."""
    resp = requests.post("http://127.0.0.1:11434/v1/chat/completions", json={
        "model": "qwen3.6-35b-a3b",
        "messages": [{
            "role": "user",
            "content": f"Validate these product entries and identify issues:\n{json.dumps(products_data[:50])}\n\nCheck for: duplicate SKUs, invalid formats, missing required fields, inconsistent data.\nReturn JSON: {{\"valid_count\": number, \"errors\": [{\"row\": number, \"field\": string, \"error\": string, \"suggestion\": string}]}}"
        }],
        "max_tokens": 4096,
        "temperature": 0.1,
    })
    return json.loads(resp.json()["choices"][0]["message"]["content"])
```

### 3f. SMS Message Generation

```python
# kteam_ai/sms.py
def generate_sms_template(template_type, context):
    """Generate SMS message templates using LLM."""
    templates = {
        "invoice_sent": "Your invoice {invoice_no} for Rs. {amount} has been sent. Due date: {due_date}. Payment terms: {terms}.",
        "order_shipped": "Your order {order_no} has been shipped. Track at: {tracking_url}",
        "payment_received": "Payment of Rs. {amount} for invoice {invoice_no} has been received. Thank you!",
        "stock_alert": "Low stock alert: {product_name} (SKU: {sku}) has only {qty} units remaining.",
    }

    resp = requests.post("http://127.0.0.1:11434/v1/chat/completions", json={
        "model": "qwen2.5-7b-instruct",
        "messages": [{
            "role": "user",
            "content": f"Generate a professional SMS message for: {template_type}. Context: {json.dumps(context)}\nKeep it under 160 characters."
        }],
        "max_tokens": 256,
        "temperature": 0.5,
    })
    return resp.json()["choices"][0]["message"]["content"]
```

### 3g. Duplicate Detection in Orders/Invoices

```python
# kteam_ai/duplicate_detection.py
def detect_duplicates(entity_type, records):
    """Detect potential duplicates using LLM similarity analysis."""
    resp = requests.post("http://127.0.0.1:11434/v1/chat/completions", json={
        "model": "qwen3.6-35b-a3b",
        "messages": [{
            "role": "user",
            "content": f"Find potential duplicates in these {entity_type} records. Consider: same vendor + same date + similar amount, same product + same date + similar qty.\n\nRecords:\n{json.dumps(records)}\n\nReturn JSON: {{\"duplicates\": [{\"group\": number, \"records\": [string], \"confidence\": number, \"reason\": string}]}}"
        }],
        "max_tokens": 4096,
        "temperature": 0.1,
    })
    return json.loads(resp.json()["choices"][0]["message"]["content"])
```

## 4. Technical Architecture for LLM Integration

### 4a. Integration with Existing Django Backend

**New Django App: `kteam_ai`**

```
kteam-dj-be/
├── kteam_ai/
│   ├── __init__.py
│   ├── apps.py
│   ├── views.py          # API endpoints
│   ├── services.py       # LLM service layer
│   ├── tools.py          # Function calling tools
│   ├── models.py         # Chat history, extracted invoices
│   ├── serializers.py    # DRF serializers
│   ├── urls.py           # API routes
│   ├── middleware.py     # Guardrails, rate limiting
│   ├── tasks.py          # Celery tasks for async processing
│   └── utils.py          # PDF processing, image conversion
├── backend/
│   └── settings.py       # Add kteam_ai to INSTALLED_APPS
```

**URLs:**

```python
# kteam_ai/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Chat bot
    path("ai/chat/", views.chat_completion, name="ai_chat"),
    path("ai/chat/stream/", views.chat_stream, name="ai_chat_stream"),
    path("ai/chat/sessions/", views.list_sessions, name="ai_sessions"),
    path("ai/chat/session/<uuid:session_id>/", views.get_session, name="ai_session"),

    # Invoice OCR
    path("ai/invoice/extract/", views.extract_invoice, name="ai_invoice_extract"),
    path("ai/invoice/extract/<uuid:id>/", views.get_extraction, name="ai_extraction_detail"),

    # RAG
    path("ai/rag/query/", views.rag_query, name="ai_rag_query"),

    # Automations
    path("ai/automate/classify/", views.classify_product, name="ai_classify"),
    path("ai/automate/search/", views.smart_search, name="ai_search"),
    path("ai/automate/report/", views.generate_report, name="ai_report"),
    path("ai/automate/validate/", views.validate_bulk_data, name="ai_validate"),
    path("ai/automate/sms/", views.generate_sms, name="ai_sms"),
    path("ai/automate/duplicates/", views.detect_duplicates, name="ai_duplicates"),
]
```

**Settings Update:**

```python
# backend/settings.py - Add to INSTALLED_APPS
INSTALLED_APPS = [
    ...
    'kteam_ai',  # LLM integration app
]

# LLM Configuration
LLM_CONFIG = {
    "fast_model": {
        "url": "http://127.0.0.1:11434",
        "model": "qwen3.6-35b-a3b",
        "max_tokens": 4096,
        "temperature": 0.3,
    },
    "reasoning_model": {
        "url": "http://127.0.0.1:11435",
        "model": "deepseek-r1-distill-qwen-32b",
        "max_tokens": 4096,
        "temperature": 0.1,
    },
    "vl_model": {
        "url": "http://127.0.0.1:11434",
        "model": "qwen2.5-vl-7b-instruct",
        "max_tokens": 2048,
        "temperature": 0.1,
    },
    "embedding_model": {
        "url": "http://127.0.0.1:6006",  # TEI endpoint
        "model": "Qwen3-Embedding-0.6B",
    },
    "ragflow": {
        "url": "http://127.0.0.1:9380/api/v1",
    },
}

# Rate limiting
LLM_RATE_LIMIT = {
    "chat": {"requests": 60, "period": 3600},  # 60 requests per hour
    "invoice_extract": {"requests": 30, "period": 3600},
    "automations": {"requests": 100, "period": 3600},
}
```

### 4b. API Design for LLM Endpoints

**Standard Response Format:**

```json
{
    "success": true,
    "data": { ... },
    "metadata": {
        "model": "qwen3.6-35b-a3b",
        "tokens_used": 1024,
        "processing_time_ms": 3200,
        "timestamp": "2026-04-22T12:00:00Z"
    }
}
```

**Error Handling:**

```json
{
    "success": false,
    "error": {
        "code": "LLM_TIMEOUT",
        "message": "LLM service timed out after 60 seconds",
        "retry_after": 5
    }
}
```

### 4c. Caching Strategies

```python
# kteam_ai/cache.py
import hashlib
import json
from django.core.cache import cache

def cache_key(prefix, **kwargs):
    """Generate a consistent cache key."""
    key_str = json.dumps(kwargs, sort_keys=True)
    key_hash = hashlib.md5(key_str.encode()).hexdigest()
    return f"ai:{prefix}:{key_hash}"

def cached_llm_call(prefix, ttl=3600, **kwargs):
    """Cache LLM responses with automatic key generation."""
    key = cache_key(prefix, **kwargs)
    cached = cache.get(key)
    if cached:
        return cached

    # Cache would be populated by the calling function
    return None

# Cache strategies by use case:
# - Chat completions: No cache (conversational, always different)
# - Product classification: 24-hour cache per product name
# - Search expansion: 1-hour cache per query
# - Report generation: Cache until next month
# - SMS templates: 7-day cache per template type
# - Anomaly detection: No cache (real-time data)
```

### 4d. Rate Limiting and Cost Management

```python
# kteam_ai/rate_limiter.py
from django.core.cache import cache
import time

class LLMRateLimiter:
    """Per-user rate limiting for LLM API calls."""

    @classmethod
    def check(cls, user_id, endpoint, limits):
        """Check if user has remaining requests."""
        key = f"rate_limit:{user_id}:{endpoint}"
        now = time.time()
        period = limits["period"]
        max_requests = limits["requests"]

        # Get current count
        current = cache.get(key) or 0
        if current >= max_requests:
            return False, max_requests - current

        # Increment
        cache.set(key, current + 1, period)
        return True, max_requests - current - 1

    @classmethod
    def reset(cls, user_id, endpoint):
        """Reset rate limit counter."""
        cache.delete(f"rate_limit:{user_id}:{endpoint}")
```

### 4e. Model Serving Architecture

**Current Setup (Optimal for RTX 3090):**

| Service | Port | Model | VRAM Usage | Purpose |
|---------|------|-------|------------|---------|
| llama.cpp (fast) | 11434 | Qwen3.6-35B-A3B | ~12GB | General chat, classification, report gen |
| llama.cpp (reasoning) | 11435 | DeepSeek-R1-Distill-Qwen-32B | ~18GB | Financial analysis, complex queries |

**Adding Vision LLM:**

The RTX 3090 has 24GB VRAM. Adding Qwen2.5-VL-7B-Instruct (14GB Q4) requires careful management:

```bash
# Option 1: Run VL model on same port, switch via model parameter
# (requires stopping current models and restarting)
# Best for: Single-use invoice processing

# Option 2: Add a second GPU (RTX 3090 is the only GPU currently)
# Not applicable with single GPU

# Option 3: Use CPU offloading for VL model
llama-server -hf ggml-org/Qwen2.5-VL-7B-Instruct-GGUF:Q4_K_M \
    --ctx-size 8192 --gpu-layers 35 --port 11436
# This uses ~14GB VRAM + ~10GB RAM, fits but slower
```

**Recommended Approach for Multi-Model:**

Use a **model router** that switches between models based on task:

```python
# kteam_ai/model_router.py
class ModelRouter:
    """Routes requests to appropriate model based on task type."""

    MODEL_POOL = {
        "chat": {"url": "http://127.0.0.1:11434", "model": "qwen3.6-35b-a3b"},
        "reasoning": {"url": "http://127.0.0.1:11435", "model": "deepseek-r1-distill-qwen-32b"},
    }

    # Vision model runs on-demand (loaded/unloaded as needed)
    # or use a dedicated service on port 11436

    @classmethod
    def get_model_for_task(cls, task_type):
        if task_type in ("classification", "search", "sms", "validation"):
            return cls.MODEL_POOL["chat"]
        elif task_type in ("anomaly_detection", "financial_analysis"):
            return cls.MODEL_POOL["reasoning"]
        elif task_type in ("invoice_ocr", "document_scan"):
            return {"url": "http://127.0.0.1:11436", "model": "qwen2.5-vl-7b-instruct"}
        elif task_type in ("report_generation"):
            return cls.MODEL_POOL["chat"]
        return cls.MODEL_POOL["chat"]
```

### 4f. GPU Utilization Optimization

**Key Settings for RTX 3090:**

```bash
# llama.cpp fast model (Qwen3.6-35B-A3B)
llama-server -m /home/chief/models/qwen3.6-35b-a3b-gguf/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf \
    --ctx-size 8192 \
    --gpu-layers 90 \
    --flash-attn on \
    --threads 16 \
    --batch-size 512 \
    --ubatch-size 512 \
    --parallel 4 \
    --port 11434

# Optimization notes:
# --gpu-layers 90: Offload most layers to GPU (MoE model has efficient GPU usage)
# --flash-attn on: Use Flash Attention for faster inference
# --parallel 4: Handle 4 concurrent requests
# --threads 16: Use CPU threads for remaining work
```

**VRAM Budget (24GB RTX 3090):**

| Component | VRAM |
|-----------|------|
| Qwen3.6-35B-A3B (Q4_K_XL) | ~12GB |
| Qwen3.6-35B-A3B mmproj (vision) | ~1GB |
| KV cache (8192 ctx, 4 parallel) | ~4GB |
| System overhead | ~2GB |
| **Remaining for VL model** | ~5GB (insufficient for 7B Q4) |

**Recommendation:** Run VL model on a **separate port** by restarting llama.cpp when invoice processing is needed, or use a **CPU-offloaded** VL model. For production, consider a **second GPU** or cloud inference for the VL model.

### 4g. Model Quantization Considerations

| Format | Quality | VRAM (7B) | VRAM (32B) | Use Case |
|--------|---------|-----------|------------|----------|
| FP16 | Perfect | ~14GB | ~64GB | Not feasible on RTX 3090 |
| Q8_0 | Near-perfect | ~7.5GB | ~34GB | Not feasible for 32B |
| Q6_K | High | ~6GB | ~28GB | Borderline for 32B |
| Q5_K_M | Good | ~5GB | ~24GB | Borderline for 32B |
| Q4_K_M | Balanced | ~4.5GB | ~19GB | **Recommended** |
| Q4_0 | Good | ~4GB | ~17GB | Alternative to Q4_K_M |
| Q3_K_M | Acceptable | ~3.5GB | ~15GB | When VRAM is tight |
| Q2_K | Poor | ~2.5GB | ~11GB | Only for small models |

**For RTX 3090 (24GB VRAM):**

| Model | Recommended Quant | VRAM |
|-------|------------------|------|
| Qwen3.6-35B-A3B | Q4_K_XL (existing) | ~12GB |
| Qwen2.5-VL-7B-Instruct | Q4_K_M | ~14GB |
| Qwen2.5-VL-3B-Instruct | Q4_K_M | ~6GB |
| Qwen2.5-7B-Instruct | Q4_K_M | ~5GB |
| Qwen2.5-14B-Instruct | Q4_K_M | ~9GB |
| Qwen2.5-32B-Instruct | Q4_K_M | ~19GB |
| DeepSeek-R1-Distill-Qwen-32B | Q4_K_M (existing) | ~18GB |

## 5. Recommended Models

### Comparison Table

| Model | Params | Active | Type | VRAM (Q4) | Speed | OCR | Reasoning | Best For |
|-------|--------|--------|------|-----------|-------|-----|-----------|----------|
| Qwen3.6-35B-A3B | 35B | 3B | MoE | ~12GB | Fast | Medium | Medium | General chat, classification |
| Qwen2.5-VL-7B-Instruct | 7B | 7B | Dense | ~14GB | Medium | High | Medium | Invoice OCR, document analysis |
| Qwen2.5-VL-3B-Instruct | 3B | 3B | Dense | ~6GB | Fast | Good | Low | Fast OCR fallback |
| Qwen2.5-7B-Instruct | 7B | 7B | Dense | ~5GB | Fast | N/A | Low | Classification, SMS, search |
| Qwen2.5-14B-Instruct | 14B | 14B | Dense | ~9GB | Medium | N/A | Medium | Balanced tasks |
| Qwen2.5-32B-Instruct | 32B | 32B | Dense | ~19GB | Slow | N/A | High | Complex queries |
| DeepSeek-R1-Distill-Qwen-32B | 32B | 32B | Dense | ~18GB | Medium | N/A | Very High | Financial analysis |
| Qwen3-Embedding-0.6B | 0.6B | 0.6B | Dense | <1GB | Instant | N/A | N/A | RAG embeddings |

### Model Recommendations by Use Case

| Use Case | Primary Model | Fallback | Quantization |
|----------|--------------|----------|--------------|
| Invoice OCR | Qwen2.5-VL-7B-Instruct | Qwen2.5-VL-3B-Instruct | Q4_K_M |
| Chat Bot (general) | Qwen3.6-35B-A3B (existing) | Qwen2.5-7B-Instruct | Q4_K_XL |
| Chat Bot (reasoning) | DeepSeek-R1-Distill-Qwen-32B (existing) | Qwen2.5-14B-Instruct | Q4_K_M |
| Product Classification | Qwen2.5-7B-Instruct | Qwen3.6-35B-A3B | Q4_K_M |
| Report Generation | Qwen3.6-35B-A3B (existing) | Qwen2.5-14B-Instruct | Q4_K_XL |
| Financial Analysis | DeepSeek-R1-Distill-Qwen-32B (existing) | Qwen2.5-32B-Instruct | Q4_K_M |
| Search Expansion | Qwen2.5-7B-Instruct | Qwen3.6-35B-A3B | Q4_K_M |
| SMS Generation | Qwen2.5-7B-Instruct | Qwen3.6-35B-A3B | Q4_K_M |
| Data Validation | Qwen3.6-35B-A3B (existing) | Qwen2.5-14B-Instruct | Q4_K_XL |
| Duplicate Detection | Qwen3.6-35B-A3B (existing) | Qwen2.5-7B-Instruct | Q4_K_XL |

### Quantization Options

**GPTQ (GPU-native):**
- Best for: Inference with transformers library
- Format: `.gptq` files
- Pros: Fastest inference on GPU, minimal overhead
- Cons: Requires model to be originally quantized, less flexible

**AWQ (Activation-aware Weight Quantization):**
- Best for: 4-bit quantization with minimal quality loss
- Format: `.awq` files
- Pros: Better quality than GPTQ at same bit rate
- Cons: Requires AWQ quantized model availability

**GGUF (llama.cpp format):**
- Best for: Current setup, maximum flexibility
- Format: `.gguf` files
- Pros: Works with existing llama.cpp, multiple quant levels, CPU/GPU hybrid
- Cons: Slightly slower than native GPU formats

**Recommendation for RTX 3090:** Continue using **GGUF format** since it's already integrated with the existing llama.cpp setup. For new models, prefer `Q4_K_M` quantization for the best quality/speed tradeoff.

## 6. Implementation Roadmap

### Phase 1: Quick Wins (Weeks 1-2)

**Scope:** Chat bot using existing Qwen3.6-35B-A3B

| Task | Effort | Dependencies |
|------|--------|-------------|
| Create `kteam_ai` Django app | 2 hours | None |
| Implement chat API endpoint | 4 hours | kteam_ai app created |
| Build conversation history model | 2 hours | kteam_ai app created |
| React chat component | 8 hours | Chat API ready |
| Add to staff portal navigation | 2 hours | Chat component ready |
| Rate limiting middleware | 2 hours | Chat API ready |
| System prompt & guardrails | 2 hours | Chat API ready |

**Total: ~22 hours (2-3 days for one developer)**

**Risks:**
- Low: Uses existing infrastructure
- Medium: Chat component UI needs to fit existing design system

**Deliverables:**
- Working chat bot in staff portal
- Conversation history in DB
- Rate limiting active

### Phase 2: Invoice Scanning (Weeks 3-6)

**Scope:** OCR + LLM extraction for invoices

| Task | Effort | Dependencies |
|------|--------|-------------|
| Install PyMuPDF for PDF processing | 1 hour | None |
| Download Qwen2.5-VL-7B-Instruct GGUF | 2 hours | None |
| Set up VL model serving on port 11436 | 2 hours | Model downloaded |
| Implement invoice extraction API | 6 hours | VL model running |
| Create ExtractedInvoice model | 2 hours | None |
| Build invoice upload UI component | 8 hours | API ready |
| PDF-to-image conversion pipeline | 4 hours | None |
| JSON validation & DB storage | 4 hours | Model + API ready |
| Frontend invoice review page | 8 hours | API + model ready |
| Test with real invoices | 8 hours | All above |

**Total: ~45 hours (1-2 weeks for one developer)**

**Risks:**
- High: VRAM constraints for VL model on single RTX 3090
- Medium: Accuracy on scanned invoices may require fine-tuning
- Medium: Need to handle multi-page invoices

**Mitigation:**
- Start with Qwen2.5-VL-3B-Instruct (6GB VRAM) as a test
- Use CPU offloading if needed
- Implement human-in-the-loop review workflow

**Deliverables:**
- Invoice upload and extraction pipeline
- Review interface for extracted data
- Database storage for extracted invoices

### Phase 3: Advanced Automations (Weeks 7-12)

**Scope:** RAG, analytics, bulk validations

| Task | Effort | Dependencies |
|------|--------|-------------|
| Integrate RAGFlow queries | 4 hours | RAGFlow running |
| Build knowledge base indexing | 4 hours | RAGFlow API |
| Implement product classification | 6 hours | Phase 1 complete |
| Smart search integration | 6 hours | Phase 1 complete |
| Automated report generation | 8 hours | Phase 1 complete |
| Anomaly detection pipeline | 8 hours | Phase 1 complete |
| Bulk data validation | 6 hours | Phase 1 complete |
| SMS template generation | 4 hours | Phase 1 complete |
| Duplicate detection | 6 hours | Phase 1 complete |
| Monitoring & evaluation | 8 hours | All above |

**Total: ~60 hours (2-3 weeks for one developer)**

**Risks:**
- Medium: RAGFlow integration complexity
- Medium: Report quality depends on data quality
- Low: Most automations are API calls to existing models

**Deliverables:**
- Full automation suite
- Monitoring dashboard
- Evaluation framework

## 7. Open Source Stack Recommendations

### Complete Stack by Use Case

**Chat Bot:**
| Component | Recommendation | Version |
|-----------|---------------|---------|
| Inference | llama.cpp (existing) | Latest |
| Model | Qwen3.6-35B-A3B (existing) | Q4_K_XL |
| Framework | Django DRF (existing) | Django 5 |
| Auth | Knox (existing) | Latest |
| Frontend | Radix UI + Tailwind CSS v4 | Existing |
| State | Redux Toolkit (existing) | Redux 5 |

**Invoice OCR:**
| Component | Recommendation | Version |
|-----------|---------------|---------|
| PDF Processing | PyMuPDF (fitz) | Latest |
| OCR Model | Qwen2.5-VL-7B-Instruct | Q4_K_M GGUF |
| Inference | llama.cpp (multimodal) | Latest |
| Image Processing | Pillow | Latest |
| Alternative OCR | PaddleOCR | 2.7+ |

**RAG/Knowledge Base:**
| Component | Recommendation | Version |
|-----------|---------------|---------|
| RAG Platform | RAGFlow (existing) | Latest |
| Embedding | Qwen3-Embedding-0.6B (existing) | via TEI |
| Search | Elasticsearch (via RAGFlow) | 8.x |
| Storage | MinIO (via RAGFlow) | Latest |
| Alternative | LangChain + Qdrant | Latest |

**Monitoring:**
| Component | Recommendation | Version |
|-----------|---------------|---------|
| LLM Status | llm-status.sh (existing) | Custom |
| Metrics | Prometheus + Grafana | Latest |
| Logging | Django logs + structured JSON | Existing |
| Tracing | OpenTelemetry | Latest |
| Evaluation | RAGAS or DeepEval | Latest |

### Docker Compose Setup

```yaml
# docker-compose-ai.yml
version: '3.8'

services:
  # Vision LLM for invoice OCR
  qwen-vl:
    image: ghcr.io/ggml-org/llama.cpp:latest
    container_name: kteam-qwen-vl
    command: >
      llama-server
      -hf ggml-org/Qwen2.5-VL-7B-Instruct-GGUF:Q4_K_M
      --ctx-size 8192
      --gpu-layers 35
      --flash-attn on
      --port 11436
    ports:
      - "11436:11436"
    volumes:
      - ./models:/models:ro
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped

  # Embedding model (TEI)
  embedding:
    image: ghcr.io/huggingface/text-embeddings-inference:latest
    container_name: kteam-embedding
    command: --model-id Qwen3-Embedding-0.6B
    ports:
      - "6006:80"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped

  # Monitoring
  prometheus:
    image: prom/prometheus:latest
    container_name: kteam-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: kteam-grafana
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=changeme
    volumes:
      - grafana_data:/var/lib/grafana
    restart: unless-stopped

volumes:
  grafana_data:
```

### Monitoring and Evaluation Framework

**Key Metrics to Track:**

| Metric | Tool | Purpose |
|--------|------|---------|
| Response time | Prometheus histogram | Monitor LLM latency |
| Token throughput | Prometheus counter | Track LLM throughput |
| Error rate | Prometheus counter | Track LLM failures |
| Model health | Custom script | Check model loading status |
| Chat accuracy | RAGAS evaluation | Measure response quality |
| OCR accuracy | Manual review + stats | Track extraction accuracy |
| Cost per query | Custom tracking | Track VRAM/GPU utilization |

**Evaluation Framework (RAGAS):**

```python
# kteam_ai/evaluation.py
from ragas import EvaluationDataset, evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision

def evaluate_chat_responses(question, answer, context):
    """Evaluate chat bot response quality."""
    dataset = EvaluationDataset.from_list({
        "question": [question],
        "answer": [answer],
        "contexts": [[context]],
    })
    results = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision])
    return results.to_pandas()
```

### Data Privacy and Security Considerations

1. **Local-only deployment** - All data stays on-premise, no cloud APIs
2. **Authentication** - Existing Knox auth protects all LLM endpoints
3. **Data isolation** - LLM tools only return data user has permission to access
4. **Input sanitization** - Guardrails middleware filters prompt injection
5. **Audit logging** - All LLM interactions logged with user ID and timestamp
6. **PII protection** - System prompts instruct LLM to not store/leak PII
7. **Model security** - GGUF files stored locally, no remote model downloads
8. **Network isolation** - LLM services bind to 127.0.0.1 (localhost only)

```python
# Security checklist:
# [x] All LLM endpoints behind Knox authentication
# [x] Input sanitization for prompt injection
# [x] Rate limiting per user
# [x] Conversation history encrypted at rest (DB level)
# [x] No external API calls (local-only)
# [x] LLM services bound to localhost only
# [x] Audit logging for all LLM interactions
# [x] Data access controlled by existing permission system
# [ ] PII redaction in logs (TODO)
# [ ] Model integrity verification (TODO)
```

## References

- [[ADR-001-local-llm]] - Decision to use local-only LLMs
- [[ADR-002-dual-model]] - Dual model (fast + reasoning) setup
- [[ADR-003-llama-cpp]] - llama.cpp inference engine decision
- [[local-ai-stack]] - Full local AI stack documentation
- [[qwen3.6-35b-a3b]] - Primary model specifications
- llama.cpp multimodal documentation (`~/llama.cpp/docs/multimodal.md`)
- llama.cpp function calling documentation (`~/llama.cpp/docs/function-calling.md`)
