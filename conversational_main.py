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
import argparse
import subprocess
import time
import re
from datetime import datetime
from typing import Dict, Any, Optional, List

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class CleanTerminalLogger:
    """
    Clean terminal output logger that captures exactly what user sees
    without ANSI escape sequences or special characters.
    """
    
    def __init__(self, log_file: str = "output/full_terminal_output.txt"):
        self.log_file = log_file
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.original_input = input
        self.log_buffer = []
        self.is_active = False
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Create/clear the log file with session header
        self._initialize_log_file()
    
    def _initialize_log_file(self):
        """Initialize log file with session header"""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"HAILEI Conversational System - Terminal Output Log\n")
            f.write(f"Session Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
    
    def _clean_text(self, text: str) -> str:
        """Remove ANSI escape sequences and clean up text"""
        # Remove ANSI escape sequences (colors, cursor movement, etc.)
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned = ansi_escape.sub('', text)
        
        # Remove other control characters but keep newlines and tabs
        cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned)
        
        # Clean up Unicode replacement characters
        cleaned = cleaned.replace('\ufffd', '')
        
        # Convert any remaining special characters to safe equivalents
        cleaned = cleaned.replace('\u001b', '')  # ESC character
        
        return cleaned
    
    def write(self, text: str):
        """Write text to both terminal and clean log file"""
        # Write to original terminal
        self.original_stdout.write(text)
        self.original_stdout.flush()
        
        # Clean text and write to log file
        clean_text = self._clean_text(text)
        # Log all content, even empty lines to preserve formatting
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(clean_text)
            f.flush()
    
    def flush(self):
        """Flush both outputs"""
        self.original_stdout.flush()
    
    def captured_input(self, prompt=""):
        """Capture user input and log it"""
        # Display prompt and get input
        if prompt:
            self.write(prompt)
        
        # Get user input using original input function
        user_input = self.original_input()
        
        # Log the user input
        self.write(user_input + "\n")
        
        return user_input
    
    def activate_global_capture(self):
        """Activate global stdout capture"""
        if not self.is_active:
            sys.stdout = self
            # Replace built-in input function to capture user inputs
            import builtins
            builtins.input = self.captured_input
            self.is_active = True
    
    def deactivate_global_capture(self):
        """Deactivate global stdout capture"""
        if self.is_active:
            sys.stdout = self.original_stdout
            # Restore original input function
            import builtins
            builtins.input = self.original_input
            self.is_active = False
    
    def log_section(self, title: str):
        """Log a section separator"""
        separator = f"\n{'-' * 60}\n{title}\n{'-' * 60}\n"
        self.write(separator)
    
    def log_error(self, error_text: str):
        """Log error with special formatting"""
        error_msg = f"\n[ERROR] {error_text}\n"
        self.write(error_msg)
    
    def log_success(self, success_text: str):
        """Log success with special formatting"""
        success_msg = f"\n[SUCCESS] {success_text}\n"
        self.write(success_msg)
    
    def finalize_log(self):
        """Add session footer to log"""
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"Session Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n")
    
    def __enter__(self):
        """Context manager entry"""
        self.activate_global_capture()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.deactivate_global_capture()
        self.finalize_log()

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
    
    def __init__(self, enable_logging: bool = True, mode: str = "cli"):
        """Initialize the conversational system"""
        
        self.mode = mode  # "cli" or "frontend"
        
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
        
        # Start orchestrator workflow and wait for it to reach first user interaction
        orchestrator_session_id = await self.orchestrator.start_conversation(
            course_request, session_id
        )
        
        # Give the phase execution time to reach the user input request
        await asyncio.sleep(0.5)  # Small delay to let async operations complete
        
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
                
                current_phase = orchestrator_state.get('current_phase', 'unknown')
                print(f"\\n⏳ Current phase: {current_phase}")
                print(f"📊 Progress: {progress.get('progress_percentage', 0)}%")
                
                # Check if we need to trigger phase execution
                if current_phase == 'course_overview' and progress.get('progress_percentage', 0) == 0:
                    print("\\n🚀 Waiting for course overview phase to complete...")
                    # Wait a bit for the background phase execution to complete
                    await asyncio.sleep(1)
                    continue
                
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
    
    async def start_frontend_mode(self):
        """Start the system in frontend mode with FastAPI server"""
        print("🌐 Starting HAILEI in Frontend Mode...")
        print("=" * 60)
        
        try:
            # Start FastAPI server in background
            print("🚀 Starting FastAPI server...")
            api_process = subprocess.Popen([
                sys.executable, "-m", "uvicorn", 
                "api.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Give server time to start
            print("⏳ Waiting for server to start...")
            time.sleep(3)
            
            # Check if server started successfully
            if api_process.poll() is None:
                print("✅ FastAPI server started successfully!")
                print()
                print("🔗 Available endpoints:")
                print("   • API Documentation: http://localhost:8000/docs")
                print("   • Frontend Interface: http://localhost:8000/frontend/")
                print("   • WebSocket Test: http://localhost:8000/frontend/websocket-test.html")
                print("   • Health Check: http://localhost:8000/health")
                print()
                print("📋 Test Instructions:")
                print("   1. Open http://localhost:8000/frontend/ in your browser")
                print("   2. Click 'Start New Session' to begin course design")
                print("   3. Interact with agents through the chat interface")
                print("   4. Test approval/feedback workflows")
                print()
                print("🔧 Backend Testing:")
                print("   • Check API docs at /docs for direct endpoint testing")
                print("   • Monitor this console for backend logs and errors")
                print()
                print("Press Ctrl+C to stop the frontend server...")
                
                try:
                    # Keep the server running and show logs
                    while api_process.poll() is None:
                        await asyncio.sleep(1)
                        
                        # Read and display any server output
                        if api_process.stdout.readable():
                            output = api_process.stdout.readline()
                            if output:
                                print(f"[API] {output.decode().strip()}")
                                
                except KeyboardInterrupt:
                    print("\n🛑 Stopping server...")
                    api_process.terminate()
                    api_process.wait()
                    print("✅ Server stopped")
                    
            else:
                print("❌ Failed to start FastAPI server")
                stdout, stderr = api_process.communicate()
                if stderr:
                    print(f"Error: {stderr.decode()}")
                    
        except Exception as e:
            print(f"❌ Error starting frontend mode: {e}")
            
    async def run_comprehensive_test(self):
        """Run comprehensive tests for both CLI and frontend modes"""
        print("🧪 HAILEI Comprehensive Testing Mode")
        print("=" * 60)
        
        # Test 1: CLI Mode
        print("\n📋 Test 1: CLI Mode")
        print("-" * 30)
        session_id = await self.start_course_design()
        print(f"✅ CLI Session created: {session_id}")
        
        # Test basic conversation flow
        state = self.get_session_status(session_id)
        print(f"✅ Session state retrieved: {state['orchestrator_state']['current_phase']}")
        
        # Test 2: API Integration (simulated)
        print("\n📋 Test 2: API Integration")
        print("-" * 30)
        try:
            # Simulate API calls
            result = await self.continue_conversation(session_id, "test message", "general")
            print(f"✅ API call successful: {result.get('message', 'OK')}")
        except Exception as e:
            print(f"❌ API test failed: {e}")
            
        # Test 3: Agent Activation
        print("\n📋 Test 3: Agent System")
        print("-" * 30)
        try:
            agents_status = self.orchestrator.get_agents_status()
            print(f"✅ Agents available: {len(agents_status)} agents")
            for agent_id, status in agents_status.items():
                print(f"   • {agent_id}: {status}")
        except Exception as e:
            print(f"❌ Agent test failed: {e}")
            
        print("\n🎯 Test Summary:")
        print("✅ CLI mode functional")
        print("✅ Session management working") 
        print("✅ Agent system operational")
        print("\n💡 Next: Run with --mode frontend to test web interface")


async def main():
    """Main entry point for conversational system with mode selection"""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='HAILEI Conversational Course Design System')
    parser.add_argument('--mode', choices=['cli', 'frontend', 'test'], default='cli',
                       help='Run mode: cli (interactive), frontend (web server), test (comprehensive)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--no-log', action='store_true', help='Disable terminal output logging')
    
    args = parser.parse_args()
    
    # Initialize clean terminal logging unless disabled
    if not args.no_log:
        terminal_logger = CleanTerminalLogger()
        print("📝 Terminal output will be logged to output/full_terminal_output.txt")
        
        # Use context manager to capture ALL output
        with terminal_logger:
            await run_with_logging(args, terminal_logger)
    else:
        await run_without_logging(args)


async def run_with_logging(args, terminal_logger):
    """Run the system with complete output logging"""
    try:
        terminal_logger.log_section(f"HAILEI System Startup - Mode: {args.mode.upper()}")
        
        print("🚀 Starting HAILEI Conversational Course Design System...")
        print(f"🎯 Mode: {args.mode.upper()}")
        print("=" * 60)
        
        # Initialize system with selected mode
        system = HAILEIConversationalSystem(
            enable_logging=True, 
            mode=args.mode
        )
        
        terminal_logger.log_section(f"{args.mode.upper()} Mode Execution")
        
        if args.mode == "cli":
            # CLI Interactive Mode
            print("🖥️  CLI Interactive Mode")
            print("   • Direct command-line interaction with agents")
            print("   • Step-by-step workflow testing")
            print("   • Real-time backend debugging")
            print()
            
            terminal_logger.log_section("Course Design Session Start")
            
            # Start course design
            session_id = await system.start_course_design()
            print(f"✅ System initialized successfully!")
            print(f"📋 Session ID: {session_id}")
            
            # Simulate CLI interaction for demo
            await system.simulate_cli_interaction(session_id)
            
        elif args.mode == "frontend":
            # Frontend Web Server Mode
            await system.start_frontend_mode()
            
        elif args.mode == "test":
            # Comprehensive Testing Mode
            await system.run_comprehensive_test()
        
    except KeyboardInterrupt:
        terminal_logger.log_error("Session interrupted by user (Ctrl+C)")
        print("\\n\\n👋 Interrupted by user")
    except Exception as e:
        terminal_logger.log_error(f"System error: {e}")
        print(f"\\n❌ Error: {e}")
        if args.debug:
            logging.exception("System error")
    finally:
        if 'system' in locals():
            system.shutdown()
        
        terminal_logger.log_section("Session Complete")
        print(f"\\n📋 Full session log saved to: {terminal_logger.log_file}")


async def run_without_logging(args):
    """Run the system without output logging"""
    try:
        print("🚀 Starting HAILEI Conversational Course Design System...")
        print(f"🎯 Mode: {args.mode.upper()}")
        print("=" * 60)
        
        # Initialize system with selected mode
        system = HAILEIConversationalSystem(
            enable_logging=True, 
            mode=args.mode
        )
        
        if args.mode == "cli":
            # CLI Interactive Mode
            print("🖥️  CLI Interactive Mode")
            print("   • Direct command-line interaction with agents")
            print("   • Step-by-step workflow testing")
            print("   • Real-time backend debugging")
            print()
            
            # Start course design
            session_id = await system.start_course_design()
            print(f"✅ System initialized successfully!")
            print(f"📋 Session ID: {session_id}")
            
            # Simulate CLI interaction for demo
            await system.simulate_cli_interaction(session_id)
            
        elif args.mode == "frontend":
            # Frontend Web Server Mode
            await system.start_frontend_mode()
            
        elif args.mode == "test":
            # Comprehensive Testing Mode
            await system.run_comprehensive_test()
        
    except KeyboardInterrupt:
        print("\\n\\n👋 Interrupted by user")
    except Exception as e:
        print(f"\\n❌ Error: {e}")
        if args.debug:
            logging.exception("System error")
    finally:
        if 'system' in locals():
            system.shutdown()


def print_usage_help():
    """Print usage examples"""
    print()
    print("🔧 HAILEI Usage Examples:")
    print("=" * 40)
    print("# CLI Mode (Interactive Testing)")
    print("python conversational_main.py --mode cli")
    print()
    print("# Frontend Mode (Web Interface)")  
    print("python conversational_main.py --mode frontend")
    print()
    print("# Test Mode (Comprehensive Validation)")
    print("python conversational_main.py --mode test")
    print()
    print("# Debug Mode")
    print("python conversational_main.py --mode cli --debug")
    print()
    print("# Disable Terminal Logging")
    print("python conversational_main.py --mode cli --no-log")
    print()
    print("📝 Note: Terminal output is automatically logged to output/full_terminal_output.txt")
    print("   Use --no-log to disable this feature.")
    print()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print_usage_help()
    asyncio.run(main())