"""Frontend-aligned API endpoints for the HAILEI experience."""

from datetime import datetime
import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from pydantic import BaseModel, Field, field_validator

from .auth import get_current_user
from .models import CourseRequest
from .websocket_manager import ConnectionManager

# Orchestrator dependency injection
orchestrator = None

def set_orchestrator(orch):
    """Set orchestrator instance for dependency injection"""
    global orchestrator
    orchestrator = orch

frontend_router = APIRouter(prefix="/frontend", tags=["Frontend"])
connection_manager = ConnectionManager()


# Frontend-specific models
class SimpleCourseRequest(BaseModel):
    """Simplified course request for frontend"""
    title: str = Field(..., description="Course title")
    level: str = Field(..., description="Course level")
    duration: int = Field(..., description="Duration in weeks")
    description: Optional[str] = None


class QuickSessionResponse(BaseModel):
    """Quick session response for frontend"""
    session_id: str
    status: str
    websocket_url: str
    timestamp: datetime


class NewSessionRequest(BaseModel):
    """Minimal payload for creating a conversational session."""

    display_name: Optional[str] = Field(
        default=None,
        description="Optional display name shared with the assistant greeting.",
        max_length=100,
    )

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ChatMessage(BaseModel):
    """Chat message for conversational interface"""
    message: str = Field(..., description="User message")
    context: Optional[Dict[str, Any]] = None


class RefinementRequest(BaseModel):
    """Refinement request for improving agent output"""
    feedback: str = Field(..., description="User feedback for refinement")


class ChatResponse(BaseModel):
    """Chat response from the system"""
    response: str
    agent_id: Optional[str] = None
    suggestions: List[str] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime


class AgentStatus(BaseModel):
    """Agent status for frontend display"""
    agent_id: str
    name: str
    status: str  # idle, working, completed, error
    progress: float
    current_task: Optional[str] = None
    last_update: datetime


class WorkflowProgress(BaseModel):
    """Workflow progress for frontend"""
    session_id: str
    current_phase: str
    total_phases: int
    completed_phases: int
    overall_progress: float
    agent_statuses: List[AgentStatus]
    estimated_completion: Optional[datetime] = None


class DecisionSubmission(BaseModel):
    """Approval or feedback decision submitted from the frontend."""

    thread_id: str = Field(..., description="Session/thread identifier for the decision.")
    assistant_message_id: str = Field(
        ..., description="Identifier of the assistant message receiving the decision."
    )
    decision: str = Field(
        ..., description="Decision value", pattern="^(approved|feedback)$"
    )
    feedback_text: Optional[str] = Field(
        default=None,
        description="Feedback text supplied when the decision is 'feedback'.",
    )

    @field_validator("feedback_text")
    @classmethod
    def validate_feedback(cls, value: Optional[str], values: Dict[str, Any]):
        decision = values.get("decision")
        if decision == "feedback":
            if not value or not value.strip():
                raise ValueError("Feedback text is required when decision is 'feedback'.")
            return value.strip()
        return value.strip() if value else None


def _build_default_course_request(display_name: Optional[str] = None) -> CourseRequest:
    """Create a baseline course request when the UI starts a new session without details."""

    base_title = "New Learning Journey"
    if display_name:
        base_title = f"{display_name}'s Learning Journey"

    return CourseRequest(
        course_title=base_title,
        course_level="general",
        course_duration_weeks=8,
        course_description="Auto-generated session from the frontend chat interface.",
        target_audience="General learners",
        prerequisites=None,
        learning_outcomes=[],
        special_requirements={},
    )


async def _start_orchestrator_session(course_request: CourseRequest) -> QuickSessionResponse:
    """Helper to start a conversation and return a standardized response payload."""

    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")

    try:
        session_id = await orchestrator.start_conversation(
            course_request=course_request.model_dump()
        )

        try:
            from .main import get_session_logger

            session_logger = get_session_logger(session_id)
            session_logger.log(f"Session created: {session_id}")
            session_logger.log(
                f"Course request: {course_request.model_dump(exclude_none=True)}"
            )
        except Exception as exc:  # pragma: no cover - logging best-effort
            logging.error("Failed to initialize session logger: %s", exc)

        return QuickSessionResponse(
            session_id=session_id,
            status="ready",
            websocket_url=f"/ws/{session_id}",
            timestamp=datetime.now()
        )

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=500, detail=f"Failed to start session: {exc}")


@frontend_router.post("/new-session", response_model=QuickSessionResponse)
async def create_new_session(
    request: Optional[NewSessionRequest] = Body(default=None),
    current_user: dict = Depends(get_current_user)
):
    """Create a new conversational session with minimal required data."""

    course_request = _build_default_course_request(
        request.display_name if request else None
    )
    return await _start_orchestrator_session(course_request)


@frontend_router.post("/quick-start", response_model=QuickSessionResponse)
async def quick_start_session(
    course_request: SimpleCourseRequest,
    current_user: dict = Depends(get_current_user)
):
    """Quick start endpoint that accepts a fully described course payload."""

    full_request = CourseRequest(
        course_title=course_request.title,
        course_level=course_request.level,
        course_duration_weeks=course_request.duration,
        course_description=course_request.description,
        target_audience="General learners",
        prerequisites=None,
        learning_outcomes=[],
        special_requirements={},
    )

    return await _start_orchestrator_session(full_request)


@frontend_router.post("/decisions")
async def submit_decision(
    submission: DecisionSubmission,
    current_user: dict = Depends(get_current_user)
):
    """Record an approval or feedback decision from the chat UI."""

    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")

    logging.info(
        "Frontend decision received for %s: %s",
        submission.assistant_message_id,
        submission.decision,
    )

    # Future enhancement: forward to orchestrator approval/feedback pipeline.
    return {
        "status": "received",
        "timestamp": datetime.now().isoformat(),
    }


@frontend_router.post("/chat/{session_id}", response_model=ChatResponse)
async def chat_with_system(
    session_id: str,
    message: ChatMessage,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Conversational interface endpoint for natural language interaction
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
    
    # Load session
    conversation_state = orchestrator.load_session(session_id)
    if not conversation_state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Process the message through orchestrator's conversation system
        # This would integrate with the conversational agents
        response_text = f"Processing your request: {message.message}"
        
        # Determine suggested actions based on current state
        suggestions = [
            "Review current progress",
            "Modify course requirements", 
            "Continue to next phase",
            "Request expert consultation"
        ]
        
        # Determine available actions
        actions = [
            {"type": "approve", "label": "Approve Current Output", "enabled": True},
            {"type": "refine", "label": "Request Refinement", "enabled": True},
            {"type": "next_phase", "label": "Continue to Next Phase", "enabled": False}
        ]
        
        # Notify WebSocket clients
        background_tasks.add_task(
            notify_websocket_clients,
            session_id,
            {
                "type": "chat_response",
                "message": response_text,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return ChatResponse(
            response=response_text,
            agent_id="main_orchestrator",
            suggestions=suggestions,
            actions=actions,
            timestamp=datetime.now()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


@frontend_router.get("/progress/{session_id}", response_model=WorkflowProgress)
async def get_workflow_progress(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive workflow progress for frontend display
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
    
    session_state = orchestrator.get_session_state(session_id)
    if not session_state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Mock agent statuses (in real implementation, would query actual agents)
        agent_statuses = [
            AgentStatus(
                agent_id="ipdai_agent",
                name="Instructional Design Agent",
                status="completed",
                progress=1.0,
                current_task="Course foundation design completed",
                last_update=datetime.now()
            ),
            AgentStatus(
                agent_id="cauthai_agent", 
                name="Content Development Agent",
                status="working",
                progress=0.6,
                current_task="Creating learning modules",
                last_update=datetime.now()
            ),
            AgentStatus(
                agent_id="askai_agent",
                name="Assessment Design Agent", 
                status="idle",
                progress=0.0,
                current_task=None,
                last_update=datetime.now()
            )
        ]
        
        # Calculate overall progress
        completed_phases = 1
        total_phases = 4
        overall_progress = completed_phases / total_phases
        
        return WorkflowProgress(
            session_id=session_id,
            current_phase=session_state.get("current_phase", "foundation_design"),
            total_phases=total_phases,
            completed_phases=completed_phases,
            overall_progress=overall_progress,
            agent_statuses=agent_statuses,
            estimated_completion=None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Progress retrieval failed: {str(e)}")


@frontend_router.post("/actions/{session_id}/approve")
async def approve_current_phase(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Frontend-friendly approval endpoint
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
    
    conversation_state = orchestrator.load_session(session_id)
    if not conversation_state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Approve current phase outputs
        current_phase = getattr(conversation_state, 'current_phase', 'foundation_design')
        success = await orchestrator.approve_output(
            agent_id="current_active_agent",  # Would be determined dynamically
            phase_id=current_phase
        )
        
        if success:
            # Try to advance to next phase
            await orchestrator.continue_workflow()
        
        # Notify clients
        background_tasks.add_task(
            notify_websocket_clients,
            session_id,
            {
                "type": "phase_approved",
                "phase_id": current_phase,
                "success": success,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return {"success": success, "message": "Phase approved successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


@frontend_router.post("/actions/{session_id}/refine")
async def request_refinement(
    session_id: str,
    request: RefinementRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Frontend-friendly refinement request endpoint
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="System not ready")
    
    conversation_state = orchestrator.load_session(session_id)
    if not conversation_state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Process refinement request
        current_phase = getattr(conversation_state, 'current_phase', 'foundation_design')
        refined_output = await orchestrator.process_user_feedback(
            agent_id="current_active_agent",  # Would be determined dynamically
            feedback=request.feedback,
            phase_id=current_phase
        )
        
        # Notify clients
        background_tasks.add_task(
            notify_websocket_clients,
            session_id,
            {
                "type": "refinement_requested",
                "feedback": request.feedback,
                "phase_id": current_phase,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return {
            "success": True,
            "message": "Refinement request processed",
            "refined_output": refined_output.to_dict() if refined_output else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Refinement failed: {str(e)}")


@frontend_router.get("/templates/course-types")
async def get_course_templates():
    """
    Get predefined course templates for quick selection
    """
    templates = [
        {
            "id": "technical_bootcamp",
            "name": "Technical Bootcamp",
            "description": "Intensive technical skills training",
            "duration_weeks": 12,
            "level": "Intermediate",
            "sample_topics": ["Programming", "Web Development", "Data Science"]
        },
        {
            "id": "professional_development",
            "name": "Professional Development",
            "description": "Soft skills and leadership training", 
            "duration_weeks": 8,
            "level": "All Levels",
            "sample_topics": ["Communication", "Leadership", "Project Management"]
        },
        {
            "id": "academic_course",
            "name": "Academic Course",
            "description": "Traditional academic curriculum",
            "duration_weeks": 16,
            "level": "Undergraduate",
            "sample_topics": ["Theory", "Research", "Critical Thinking"]
        },
        {
            "id": "certification_prep",
            "name": "Certification Preparation",
            "description": "Exam preparation and certification training",
            "duration_weeks": 6,
            "level": "Advanced",
            "sample_topics": ["Practice Tests", "Key Concepts", "Exam Strategies"]
        }
    ]
    
    return {"templates": templates}


@frontend_router.get("/health/frontend")
async def frontend_health_check():
    """
    Frontend-specific health check with UI-relevant information
    """
    # Get orchestrator from main module at runtime
    from . import main
    orchestrator = main.orchestrator
    
    status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "orchestrator": "healthy" if orchestrator else "unavailable",
            "websocket": "healthy",
            "authentication": "healthy"
        },
        "features": {
            "chat_interface": True,
            "real_time_updates": True,
            "progress_tracking": True,
            "multi_agent_coordination": True
        }
    }
    
    if orchestrator:
        status["active_sessions"] = len(orchestrator.active_sessions)
        status["websocket_connections"] = connection_manager.get_connection_count()
    
    return status


# Helper function for WebSocket notifications
async def notify_websocket_clients(session_id: str, message: Dict[str, Any]):
    """Notify WebSocket clients of events"""
    try:
        await connection_manager.send_to_session(session_id, message)
    except Exception as e:
        import logging
        logging.error(f"WebSocket notification failed for session {session_id}: {e}")