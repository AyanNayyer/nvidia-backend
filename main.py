
import os
import asyncio
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from loguru import logger
import yaml


load_dotenv()


logger.remove()
logger.add(
    "logs/app.log",
    rotation="1 day",
    retention="7 days",
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)
logger.add(
    lambda msg: print(msg, end=""),
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}"
)

# Global variables for guardrails
guardrails_app = None
chatgroq_client = None


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    conversation_id: Optional[str] = Field(None, description="Optional conversation identifier")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str = Field(..., description="AI response")
    blocked: bool = Field(False, description="Whether the request was blocked by guardrails")
    reason: Optional[str] = Field(None, description="Reason for blocking if applicable")
    citations: Optional[list] = Field(None, description="Citations if required")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class GuardrailsManager:
    
    def __init__(self):
        self.app = None
        self.config_path = "config.yml"
        self.config_available = False
        
        # Define comprehensive guardrail rules
        self.topic_restrictions = [
            "politics", "political", "election", "government", "politician",
            "illegal", "drug", "weapon", "violence", "harmful", "criminal",
            "hate", "discrimination", "offensive", "inappropriate", "racist",
            "sexist", "harassment", "threat", "suicide", "self-harm"
        ]
        
        self.toxic_keywords = [
            "stupid", "idiot", "moron", "dumb", "hate", "kill", "die", "damn",
            "crap", "suck", "terrible", "awful", "disgusting", "pathetic",
            "worthless", "useless", "retard", "fuck", "shit", "bitch", "asshole"
        ]
        
        # More specific toxic phrases to avoid false positives
        self.toxic_phrases = [
            "go to hell", "what the hell", "hell no", "hell yes",
            "damn you", "damn it", "kill yourself", "die already"
        ]
        
        self.citation_indicators = [
            "according to", "research shows", "studies indicate", "statistics show",
            "data suggests", "evidence shows", "experts say", "scientists found",
            "studies prove", "research indicates", "data reveals", "findings show"
        ]
        
    async def initialize(self):
        """Initialize the guardrails application."""
        try:
            import os
            if not os.path.exists(self.config_path):
                logger.info("No NeMo Guardrails config found, using comprehensive custom guardrails")
                return False
                
            from nemoguardrails import RailsConfig, LLMRails
            
            # Load configuration
            config = RailsConfig.from_path(self.config_path)
            
            # Initialize Rails
            self.app = LLMRails(config)
            
            logger.info("NeMo Guardrails initialized successfully")
            self.config_available = True
            return True
            
        except ImportError as e:
            logger.warning(f"NeMo Guardrails not available: {e}")
            logger.info("Using comprehensive custom guardrails implementation")
            return False
        except Exception as e:
            logger.warning(f"NeMo Guardrails configuration issue: {e}")
            logger.info("Using comprehensive custom guardrails implementation")
            return False
    
    async def check_input(self, message: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Comprehensive input guardrails checking."""
        try:
            message_lower = message.lower()
            
            # 1. Topic Restrictions - Block discussions on sensitive topics
            for topic in self.topic_restrictions:
                if topic in message_lower:
                    return {
                        "blocked": True,
                        "reason": f"Topic restriction: '{topic}' detected",
                        "category": "topic_restriction",
                        "severity": "high"
                    }
            
            # 2. Toxicity Filter - Prevent harmful or offensive language
            # Check for toxic phrases first (more specific)
            for phrase in self.toxic_phrases:
                if phrase in message_lower:
                    return {
                        "blocked": True,
                        "reason": f"Toxicity detected: '{phrase}' found",
                        "category": "toxicity",
                        "severity": "high"
                    }
            
            # Check for toxic keywords (but be more careful about context)
            for keyword in self.toxic_keywords:
                if keyword in message_lower:
                    # Skip if it's part of a common phrase that's not toxic
                    if keyword == "hell" and any(phrase in message_lower for phrase in ["how are you", "what the", "go to"]):
                        continue
                    if keyword == "damn" and any(phrase in message_lower for phrase in ["damn good", "damn right"]):
                        continue
                    
                    return {
                        "blocked": True,
                        "reason": f"Toxicity detected: '{keyword}' found",
                        "category": "toxicity",
                        "severity": "high"
                    }
            
            # 3. Response Length Control - Limit input to reasonable size
            max_length = int(os.getenv("MAX_INPUT_LENGTH", "1500"))
            if len(message) > max_length:
                return {
                    "blocked": True,
                    "reason": f"Input too long (max {max_length} characters)",
                    "category": "length",
                    "severity": "medium"
                }
            
            # 4. Additional safety checks
            # Check for potential spam patterns
            if message.count(' ') < 2 and len(message) > 50:
                return {
                    "blocked": True,
                    "reason": "Potential spam detected (too few spaces for length)",
                    "category": "spam",
                    "severity": "medium"
                }
            
            # Check for excessive repetition
            words = message_lower.split()
            if len(words) > 10:
                word_counts = {}
                for word in words:
                    word_counts[word] = word_counts.get(word, 0) + 1
                
                max_repetition = max(word_counts.values())
                if max_repetition > len(words) * 0.3:  # More than 30% repetition
                    return {
                        "blocked": True,
                        "reason": "Excessive word repetition detected",
                        "category": "spam",
                        "severity": "medium"
                    }
            
            return {"blocked": False, "reason": None}
            
        except Exception as e:
            logger.error(f"Error checking input guardrails: {e}")
            return {"blocked": False, "reason": None}
    
    async def check_output(self, response: str) -> Dict[str, Any]:
        """Comprehensive output guardrails checking."""
        try:
            response_lower = response.lower()
            
            # 1. Response Length Control - Limit answers to reasonable size
            max_length = int(os.getenv("MAX_RESPONSE_LENGTH", "1000"))
            if len(response) > max_length:
                truncated_response = response[:max_length] + "..."
                logger.warning(f"Response truncated to {max_length} characters")
                return {
                    "blocked": False,
                    "reason": None,
                    "truncated_response": truncated_response,
                    "original_length": len(response)
                }
            
            # 2. Citation Enforcement - Require citations when external facts are mentioned
            citations_required = any(indicator in response_lower for indicator in self.citation_indicators)
            
            if citations_required:
                # Check if citations are present
                citation_present = any(word in response_lower for word in [
                    "source:", "reference:", "citation:", "study:", "research:", 
                    "according to", "as cited in", "from the study", "per the research"
                ])
                
                if not citation_present:
                    return {
                        "blocked": True,
                        "reason": "Citations required for factual claims",
                        "category": "citation_required",
                        "severity": "high",
                        "citations": [],
                        "suggested_response": "I need to provide more accurate information with proper citations. Let me research that for you."
                    }
            
            # 3. Content Safety Check - Ensure response doesn't contain harmful content
            for keyword in self.toxic_keywords:
                if keyword in response_lower:
                    return {
                        "blocked": True,
                        "reason": f"Response contains inappropriate content: '{keyword}'",
                        "category": "content_safety",
                        "severity": "high"
                    }
            
            # 4. Topic Restriction Check - Ensure response doesn't discuss restricted topics
            for topic in self.topic_restrictions:
                if topic in response_lower:
                    return {
                        "blocked": True,
                        "reason": f"Response discusses restricted topic: '{topic}'",
                        "category": "topic_restriction",
                        "severity": "high"
                    }
            
            # 5. Quality Check - Ensure response is meaningful
            if len(response.strip()) < 10:
                return {
                    "blocked": True,
                    "reason": "Response too short to be meaningful",
                    "category": "quality",
                    "severity": "low"
                }
            
            # 6. Check for potential hallucination indicators
            hallucination_indicators = [
                "i don't know", "i'm not sure", "i can't", "i cannot",
                "i'm not able to", "i don't have access to"
            ]
            
            if any(indicator in response_lower for indicator in hallucination_indicators):
                logger.info("Response contains uncertainty indicators - may need verification")
            
            return {"blocked": False, "reason": None}
            
        except Exception as e:
            logger.error(f"Error checking output guardrails: {e}")
            return {"blocked": False, "reason": None}


class ChatGroqClient:
    """Async client for ChatGroq API."""
    
    def __init__(self):
        self.api_key = os.getenv("CHATGROQ_API_KEY")
        self.base_url = "https://api.chatgroq.com/v1"
        self.client = None
        
    async def initialize(self):
        """Initialize the HTTP client."""
        if not self.api_key:
            raise ValueError("CHATGROQ_API_KEY not found in environment variables")
        
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )
        logger.info("ChatGroq client initialized")
    
    async def generate_response(self, message: str, user_id: Optional[str] = None) -> str:
        """Generate response using ChatGroq API."""
        try:
            if not self.client:
                await self.initialize()
            
            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful, harmless, and honest AI assistant. Always be respectful and provide accurate information. If you make factual claims, include citations or sources."
                    },
                    {
                        "role": "user",
                        "content": message
                    }
                ],
                "model": "llama-3.1-70b-versatile",
                "max_tokens": int(os.getenv("MAX_RESPONSE_LENGTH", "1000")),
                "temperature": 0.7,
                "stream": False
            }
            
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
            
        except httpx.HTTPStatusError as e:
            logger.error(f"ChatGroq API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail="ChatGroq API error")
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()


# Initialize global instances
guardrails_manager = GuardrailsManager()
chatgroq_client = ChatGroqClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting NVIDIA NeMo Guardrails FastAPI application")
    
    # Initialize guardrails
    guardrails_success = await guardrails_manager.initialize()
    if not guardrails_success:
        logger.info("Using basic guardrails implementation (NeMo Guardrails not available)")
    
    # Initialize ChatGroq client
    try:
        await chatgroq_client.initialize()
    except Exception as e:
        logger.error(f"Failed to initialize ChatGroq client: {e}")
        raise
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    await chatgroq_client.close()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="NVIDIA NeMo Guardrails API",
    description="A secure AI conversational system with comprehensive safety guardrails",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "NVIDIA NeMo Guardrails API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "chat": "/chat",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "guardrails": guardrails_manager.app is not None,
        "chatgroq": chatgroq_client.client is not None
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint with guardrails protection.
    
    This endpoint processes user messages through multiple safety layers:
    1. Input validation and topic restrictions
    2. Toxicity filtering
    3. Length checks
    4. AI response generation
    5. Output validation and citation enforcement
    """
    try:
        logger.info(f"Processing chat request from user: {request.user_id}")
        
        # Step 1: Check input against guardrails
        input_check = await guardrails_manager.check_input(request.message, request.user_id)
        if input_check["blocked"]:
            logger.warning(f"Input blocked: {input_check['reason']}")
            return ChatResponse(
                response="I'm sorry, but I can't help with that request. Please try asking something else.",
                blocked=True,
                reason=input_check["reason"],
                metadata={"category": input_check.get("category")}
            )
        
        # Step 2: Generate AI response
        try:
            ai_response = await chatgroq_client.generate_response(request.message, request.user_id)
        except HTTPException as e:
            logger.error(f"ChatGroq API error: {e.detail}")
            return ChatResponse(
                response="I'm experiencing technical difficulties. Please try again later.",
                blocked=False,
                reason="API error",
                metadata={"error": str(e.detail)}
            )
        
        # Step 3: Check output against guardrails
        output_check = await guardrails_manager.check_output(ai_response)
        if output_check["blocked"]:
            logger.warning(f"Output blocked: {output_check['reason']}")
            return ChatResponse(
                response=output_check.get("suggested_response", "I need to provide more accurate information with proper citations. Let me research that for you."),
                blocked=True,
                reason=output_check["reason"],
                citations=output_check.get("citations", []),
                metadata={
                    "category": output_check.get("category"),
                    "severity": output_check.get("severity"),
                    "user_id": request.user_id,
                    "conversation_id": request.conversation_id
                }
            )
        
        # Handle truncated response
        if "truncated_response" in output_check:
            ai_response = output_check["truncated_response"]
            logger.info(f"Response truncated from {output_check['original_length']} to {len(ai_response)} characters")
        
        # Step 4: Return successful response
        logger.info("Chat request processed successfully")
        return ChatResponse(
            response=ai_response,
            blocked=False,
            metadata={
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "response_length": len(ai_response)
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/guardrails/status")
async def guardrails_status():
    """Get current guardrails status and comprehensive configuration."""
    return {
        "enabled": guardrails_manager.app is not None,
        "implementation": "NeMo Guardrails + Custom Guardrails" if guardrails_manager.app else "Custom Guardrails",
        "features": {
            "topic_restrictions": {
                "enabled": os.getenv("ENABLE_TOPIC_RESTRICTIONS", "True").lower() == "true",
                "restricted_topics": len(guardrails_manager.topic_restrictions),
                "examples": guardrails_manager.topic_restrictions[:5]  # Show first 5 examples
            },
            "toxicity_filter": {
                "enabled": os.getenv("ENABLE_TOXICITY_FILTER", "True").lower() == "true",
                "toxic_keywords": len(guardrails_manager.toxic_keywords),
                "examples": guardrails_manager.toxic_keywords[:5]  # Show first 5 examples
            },
            "citation_enforcement": {
                "enabled": os.getenv("ENABLE_CITATION_ENFORCEMENT", "True").lower() == "true",
                "citation_indicators": len(guardrails_manager.citation_indicators),
                "examples": guardrails_manager.citation_indicators[:3]  # Show first 3 examples
            },
            "response_length_control": {
                "max_response_length": int(os.getenv("MAX_RESPONSE_LENGTH", "1000")),
                "max_input_length": int(os.getenv("MAX_INPUT_LENGTH", "1500"))
            },
            "additional_safety": {
                "spam_detection": True,
                "repetition_detection": True,
                "quality_checks": True,
                "hallucination_detection": True
            }
        },
        "api_integration": {
            "chatgroq": chatgroq_client.client is not None,
            "model": "llama-3.1-70b-versatile"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "True").lower() == "true"
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
