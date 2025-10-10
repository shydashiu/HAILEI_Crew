"""
HAILEI Conversational Course Design System

Main entry point for the conversational AI orchestration system.
Replaces the CrewAI-based main.py with frontend-ready conversational workflows.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Core orchestration imports
from orchestrator import HAILEIOrchestrator, ConversationState
from agents import ConversationalAgentFactory
from human_interface import FrontendHumanLayer, ConversationManager

# Framework data (from original main.py)
from main import (
    KDKA_FRAMEWORK, 
    PRRR_FRAMEWORK, 
    SAMPLE_COURSE_REQUEST
)


class HAILEIConversationalSystem:
    """
    Main system class for HAILEI conversational course design.
    
    Features:
    - Complete replacement for CrewAI crew system
    - Frontend-ready conversational workflows
    - Iterative refinement capabilities
    - Production deployment readiness
    """
    
    def __init__(self, enable_logging: bool = True):
        """Initialize the conversational system"""
        
        # Logging setup
        if enable_logging:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.StreamHandler(),
                    logging.FileHandler('hailei_conversational.log')
                ]
            )
            self.logger = logging.getLogger('hailei_conversational_system')
        else:
            self.logger = logging.getLogger('null')
            self.logger.addHandler(logging.NullHandler())
        
        # Initialize components
        self.logger.info("Initializing HAILEI Conversational System...")
        
        # Agent factory for creating conversational agents
        self.agent_factory = ConversationalAgentFactory()
        
        # Frontend human interaction
        self.frontend_humanlayer = FrontendHumanLayer()
        
        # Conversation manager
        self.conversation_manager = ConversationManager(self.frontend_humanlayer)
        
        # Create agents and orchestrator
        self.agents = self.agent_factory.get_orchestrator_agents_dict()
        self.frameworks = {
            'kdka': KDKA_FRAMEWORK,
            'prrr': PRRR_FRAMEWORK
        }
        
        # Main orchestrator
        self.orchestrator = HAILEIOrchestrator(
            agents=self.agents,
            frameworks=self.frameworks,
            humanlayer_instance=self.frontend_humanlayer.humanlayer
        )
        
        # Register event callbacks for frontend integration
        self._register_event_callbacks()
        
        self.logger.info("HAILEI Conversational System initialized successfully")
    
    def _register_event_callbacks(self):
        """Register event callbacks for system integration"""
        
        # Orchestrator events
        self.orchestrator.register_event_callback('phase_started', self._on_phase_started)
        self.orchestrator.register_event_callback('phase_completed', self._on_phase_completed)
        self.orchestrator.register_event_callback('agent_output', self._on_agent_output)
        self.orchestrator.register_event_callback('user_input_required', self._on_user_input_required)
        
        # HumanLayer events
        self.frontend_humanlayer.register_event_callback('interaction_requested', self._on_interaction_requested)
        self.frontend_humanlayer.register_event_callback('interaction_completed', self._on_interaction_completed)
    
    def _on_phase_started(self, data: Dict[str, Any]):
        """Handle phase started event"""
        self.logger.info(f"Phase started: {data['phase_name']}")
        
        # Add to conversation history
        if 'session_id' in data:
            self.conversation_manager.add_turn(
                data['session_id'],
                'coordinator',
                f"Starting {data['phase_name']}",
                {'event_type': 'phase_started', 'phase_id': data['phase_id']}
            )
    
    def _on_phase_completed(self, data: Dict[str, Any]):
        """Handle phase completed event"""
        self.logger.info(f"Phase completed: {data['phase_name']}")
        
        # Add to conversation history
        if 'session_id' in data:
            self.conversation_manager.add_turn(
                data['session_id'],
                'coordinator',
                f"Completed {data['phase_name']}",
                {'event_type': 'phase_completed', 'phase_id': data['phase_id']}
            )
    
    def _on_agent_output(self, data: Dict[str, Any]):
        """Handle agent output event"""
        output = data['output']
        self.logger.info(f"Agent output received: {output['agent_name']}")
        
        # Add to conversation history
        if 'session_id' in data:
            self.conversation_manager.add_turn(
                data['session_id'],
                output['agent_name'],
                f"Generated output for {output['phase']}",
                {'event_type': 'agent_output', 'output_preview': output['content'][:200]}
            )
    
    def _on_user_input_required(self, data: Dict[str, Any]):
        """Handle user input required event"""
        self.logger.info("User input required")
        
        # This would trigger frontend notification in production
        pass
    
    def _on_interaction_requested(self, data: Dict[str, Any]):
        """Handle interaction requested event"""
        request = data['request']
        self.logger.info(f"Interaction requested: {request['interaction_type']}")
    
    def _on_interaction_completed(self, data: Dict[str, Any]):
        """Handle interaction completed event"""
        self.logger.info(f"Interaction completed: {data['request_id']}")
    
    async def start_course_design(
        self,
        course_request: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        Start conversational course design workflow.
        
        Args:
            course_request: Course requirements (uses sample if not provided)
            session_id: Optional session ID
            
        Returns:
            str: Session ID for tracking
        """
        # Use sample course if not provided
        if course_request is None:
            course_request = SAMPLE_COURSE_REQUEST
        
        self.logger.info(f"Starting course design for: {course_request.get('course_title', 'Unknown Course')}")
        
        # Start conversation
        session_id = self.conversation_manager.start_conversation(
            session_id or f"session_{datetime.now().timestamp()}",
            initial_context={'course_request': course_request}
        )
        
        # Start orchestrator workflow
        orchestrator_session_id = await self.orchestrator.start_conversation(
            course_request, session_id
        )
        
        self.logger.info(f"Course design workflow started with session: {session_id}")
        return session_id
    
    async def continue_conversation(
        self,
        session_id: str,
        user_input: str,
        input_type: str = "text"
    ) -> Dict[str, Any]:
        """
        Continue conversation with user input.
        
        Args:
            session_id: Session identifier
            user_input: User's input
            input_type: Type of input (text, approval, feedback)
            
        Returns:
            Dict with conversation state and next steps
        """
        self.logger.info(f"Continuing conversation for session {session_id}")
        
        # Add user turn to conversation
        self.conversation_manager.add_turn(session_id, "user", user_input, {
            'input_type': input_type
        })
        
        # Process input based on current state
        conversation_state = self.orchestrator.get_session_state(session_id)
        
        if not conversation_state:
            return {'error': 'Session not found'}
        
        # Handle different input types
        if input_type == "approval":
            # Handle approval
            approved = user_input.lower() in ['yes', 'approve', 'approved', 'proceed']
            if approved:
                success = await self.orchestrator.continue_workflow()
                return {
                    'status': 'approved',
                    'workflow_continued': success,
                    'session_state': self.orchestrator.get_session_state(session_id)
                }
            else:
                return {
                    'status': 'denied',
                    'message': 'Please provide feedback for improvements'
                }
        
        elif input_type == "feedback":
            # Handle feedback for refinement
            current_agent = conversation_state.get('active_agent')
            if current_agent:
                refined_output = await self.orchestrator.process_user_feedback(
                    current_agent, user_input
                )
                return {
                    'status': 'feedback_processed',
                    'refined_output': refined_output.to_dict(),
                    'session_state': self.orchestrator.get_session_state(session_id)
                }
        
        else:
            # General text input
            return {
                'status': 'input_received',
                'message': 'Input received and processed',
                'session_state': self.orchestrator.get_session_state(session_id)
            }
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current session status and state"""
        # Get orchestrator state
        orchestrator_state = self.orchestrator.get_session_state(session_id)
        
        # Get conversation state
        conversation_context = self.conversation_manager.get_conversation_context(session_id)
        
        # Get conversation history
        conversation_history = self.conversation_manager.get_conversation_history(session_id, limit=20)
        
        if not orchestrator_state:
            return None
        
        return {
            'session_id': session_id,
            'orchestrator_state': orchestrator_state,
            'conversation_context': conversation_context.to_dict() if conversation_context else None,
            'conversation_history': conversation_history,
            'frontend_state': self.frontend_humanlayer.get_session_state(session_id),
            'timestamp': datetime.now().isoformat()
        }
    
    def list_active_sessions(self) -> List[str]:
        """List all active session IDs"""
        return list(self.orchestrator.active_sessions.keys())
    
    async def simulate_cli_interaction(self, session_id: str):
        """
        Simulate CLI interaction for testing (will be replaced by frontend).
        This demonstrates the conversational flow.
        """
        print("\\n🎓 HAILEI Conversational Course Design - CLI Demo")
        print("=" * 60)
        
        while True:
            # Get current state
            state = self.get_session_status(session_id)
            if not state:
                print("Session not found")
                break
            
            orchestrator_state = state['orchestrator_state']
            pending_input = orchestrator_state.get('pending_user_input')
            
            if pending_input:
                # Handle pending input
                print(f"\\n🤖 {pending_input['message']}")
                
                if pending_input['input_type'] == 'approval':
                    response = input("\\n👤 Your response (yes/no): ").strip()
                    result = await self.continue_conversation(session_id, response, "approval")
                    
                elif pending_input['input_type'] == 'feedback':
                    response = input("\\n👤 Your feedback: ").strip()
                    result = await self.continue_conversation(session_id, response, "feedback")
                    
                else:
                    response = input("\\n👤 Your response: ").strip()
                    result = await self.continue_conversation(session_id, response, "text")
                
                print(f"\\n✅ {result.get('status', 'processed')}")
                
                if result.get('refined_output'):
                    print("\\n📝 Refined Output:")
                    print(result['refined_output']['content'][:300] + "...")
            
            else:
                # Check if workflow is complete
                progress = orchestrator_state.get('progress', {})
                if progress.get('progress_percentage', 0) >= 100:
                    print("\\n🎉 Course design workflow completed!")
                    break
                
                # Wait for next step
                print(f"\\n⏳ Current phase: {orchestrator_state.get('current_phase', 'unknown')}")
                print(f"📊 Progress: {progress.get('progress_percentage', 0)}%")
                
                wait = input("\\nPress Enter to continue or 'q' to quit: ").strip()
                if wait.lower() == 'q':
                    break
    
    def shutdown(self):
        """Shutdown the conversational system"""
        self.logger.info("Shutting down HAILEI Conversational System...")
        
        # Shutdown components
        self.orchestrator.shutdown()
        self.agent_factory.shutdown()
        
        self.logger.info("HAILEI Conversational System shutdown complete")


async def main():
    """Main entry point for conversational system"""
    print("🚀 Starting HAILEI Conversational Course Design System...")
    
    try:
        # Initialize system
        system = HAILEIConversationalSystem()
        
        # Start course design
        session_id = await system.start_course_design()
        
        print(f"\\n✅ System initialized successfully!")
        print(f"📋 Session ID: {session_id}")
        
        # Simulate CLI interaction for demo
        await system.simulate_cli_interaction(session_id)
        
    except KeyboardInterrupt:
        print("\\n\\n👋 Interrupted by user")
    except Exception as e:
        print(f"\\n❌ Error: {e}")
        logging.exception("System error")
    finally:
        if 'system' in locals():
            system.shutdown()


if __name__ == "__main__":
    asyncio.run(main())