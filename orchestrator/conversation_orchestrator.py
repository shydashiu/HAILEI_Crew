"""
HAILEI Conversational AI Orchestrator

Main orchestration engine that replaces CrewAI's crew system with conversational
workflows designed for frontend deployment and iterative refinement.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Union, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import Mock

from crewai import Agent
from humanlayer import HumanLayer

from .conversation_state import ConversationState, AgentOutput, PhaseStatus, AgentStatus
from .phase_manager import PhaseManager
from .refinement_engine import RefinementEngine
from .parallel_orchestrator import ParallelOrchestrator, ParallelTask, ExecutionMode
from .decision_engine import DynamicDecisionEngine, DecisionContext
from .context_manager import EnhancedContextManager, ContextType, MemoryPriority, ContextQuery
from .error_recovery import ErrorRecoverySystem, ErrorSeverity, ErrorCategory
from agents.agent_wrappers import AgentExecutor
from agents.conversational_agents import ConversationalAgentFactory


class HAILEIOrchestrator:
    """
    Main conversational orchestrator for HAILEI educational AI system.
    
    Features:
    - Persistent conversation state across phases
    - Iterative agent refinement with human feedback
    - Frontend-ready WebSocket/API integration
    - Parallel agent execution when beneficial
    - Context preservation across entire workflow
    - HumanLayer integration for production deployment
    """
    
    def __init__(
        self,
        agents: Dict[str, Agent],
        frameworks: Dict[str, Dict],
        humanlayer_instance: Optional[HumanLayer] = None,
        max_parallel_agents: int = 3,
        enable_logging: bool = True
    ):
        """
        Initialize the conversational orchestrator.
        
        Args:
            agents: Dictionary of agent_id -> CrewAI Agent instances
            frameworks: KDKA and PRRR framework definitions
            humanlayer_instance: HumanLayer instance for human interaction
            max_parallel_agents: Maximum number of agents that can run simultaneously
            enable_logging: Enable detailed logging for debugging
        """
        self.agents = agents
        self.frameworks = frameworks
        self.humanlayer = humanlayer_instance or HumanLayer()
        self.max_parallel_agents = max_parallel_agents
        
        # Core components
        self.phase_manager = PhaseManager(self)
        self.refinement_engine = RefinementEngine(self)
        self.parallel_orchestrator = ParallelOrchestrator(self, max_parallel_agents, enable_logging)
        self.decision_engine = DynamicDecisionEngine(enable_logging)
        self.context_manager = EnhancedContextManager(
            max_memory_entries=5000,
            memory_cleanup_threshold=0.8,
            enable_logging=enable_logging
        )
        self.error_recovery = ErrorRecoverySystem(
            orchestrator=self,
            enable_logging=enable_logging,
            max_error_history=1000
        )
        
        # Agent execution system
        self.agent_factory = ConversationalAgentFactory(enable_logging=enable_logging)
        self.agent_executor = AgentExecutor(max_concurrent_executions=max_parallel_agents)
        self.conversational_agents = {}  # Will store agent wrappers
        
        # State management
        self.conversation_state: Optional[ConversationState] = None
        self.active_sessions: Dict[str, ConversationState] = {}
        
        # Execution control
        self.executor = ThreadPoolExecutor(max_workers=max_parallel_agents)
        self.execution_lock = threading.Lock()
        self.stop_execution = threading.Event()
        
        # Event callbacks for frontend integration
        self.event_callbacks: Dict[str, List[Callable]] = {
            'phase_started': [],
            'phase_completed': [],
            'agent_started': [],
            'agent_completed': [],
            'agent_output': [],
            'user_input_required': [],
            'refinement_cycle': [],
            'error_occurred': []
        }
        
        # Logging setup
        if enable_logging:
            self.logger = logging.getLogger('hailei_orchestrator')
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
        else:
            self.logger = logging.getLogger('null')
            self.logger.addHandler(logging.NullHandler())
        
        # Initialize conversational agents
        self._initialize_conversational_agents()
    
    def _initialize_conversational_agents(self):
        """Initialize conversational agent wrappers for real execution"""
        try:
            # Create all conversational agents from the factory
            agent_wrappers = self.agent_factory.create_all_agents()
            
            # Register each wrapper with the executor
            for agent_id, wrapper in agent_wrappers.items():
                self.conversational_agents[agent_id] = wrapper
                self.agent_executor.register_agent(wrapper)
                self.logger.info(f"Registered conversational agent: {agent_id}")
            
            self.logger.info(f"Initialized {len(agent_wrappers)} conversational agents")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize conversational agents: {e}")
            # Fall back to empty dict - orchestrator will still work with basic agents
            self.conversational_agents = {}
    
    def register_event_callback(self, event_type: str, callback: Callable):
        """Register callback for frontend event handling"""
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type].append(callback)
    
    def emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit event to registered callbacks (for WebSocket/API integration)"""
        for callback in self.event_callbacks.get(event_type, []):
            try:
                callback(data)
            except Exception as e:
                self.logger.error(f"Event callback error for {event_type}: {e}")
    
    def create_session(
        self,
        course_request: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> ConversationState:
        """
        Create new conversation session for a course design workflow.
        
        Args:
            course_request: Course requirements and specifications
            session_id: Optional custom session ID
        
        Returns:
            ConversationState: New conversation state instance
        """
        conversation_state = ConversationState(
            session_id=session_id,
            course_request=course_request
        )
        conversation_state.frameworks = self.frameworks
        
        self.active_sessions[conversation_state.session_id] = conversation_state
        self.conversation_state = conversation_state
        
        self.logger.info(f"Created new session: {conversation_state.session_id}")
        
        # Emit session created event
        self.emit_event('session_created', {
            'session_id': conversation_state.session_id,
            'course_title': course_request.get('course_title', 'Untitled Course'),
            'timestamp': datetime.now().isoformat()
        })
        
        return conversation_state
    
    def load_session(self, session_id: str) -> Optional[ConversationState]:
        """Load existing conversation session"""
        if session_id in self.active_sessions:
            self.conversation_state = self.active_sessions[session_id]
            self.logger.info(f"Loaded session: {session_id}")
            return self.conversation_state
        return None
    
    def get_session_state(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get session state for frontend display"""
        session_id = session_id or (self.conversation_state.session_id if self.conversation_state else None)
        if session_id and session_id in self.active_sessions:
            return self.active_sessions[session_id].to_dict()
        return None
    
    async def start_conversation(
        self,
        course_request: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> str:
        """
        Start new conversational course design workflow.
        
        Args:
            course_request: Course requirements and specifications
            session_id: Optional custom session ID
        
        Returns:
            str: Session ID for frontend tracking
        """
        # Create or load session
        if session_id and session_id in self.active_sessions:
            conversation_state = self.load_session(session_id)
        else:
            conversation_state = self.create_session(course_request, session_id)
        
        # Start with course overview phase
        await self.begin_phase('course_overview')
        
        return conversation_state.session_id
    
    async def begin_phase(self, phase_id: str) -> bool:
        """
        Begin a specific phase of the conversation workflow.
        
        Args:
            phase_id: Phase identifier
            
        Returns:
            bool: Success status
        """
        self.logger.info(f"🚀 [DEBUG] begin_phase() called with phase_id: {phase_id}")
        
        if not self.conversation_state:
            self.logger.error(f"❌ [DEBUG] No active conversation session for phase {phase_id}")
            raise ValueError("No active conversation session")
        
        if phase_id not in self.conversation_state.phases:
            self.logger.error(f"❌ [DEBUG] Unknown phase: {phase_id}")
            raise ValueError(f"Unknown phase: {phase_id}")
        
        # Check dependencies
        phase = self.conversation_state.phases[phase_id]
        self.logger.info(f"📋 [DEBUG] Phase '{phase_id}' dependencies: {phase.dependencies}")
        
        for dep_phase_id in phase.dependencies:
            dep_phase = self.conversation_state.phases[dep_phase_id]
            self.logger.info(f"🔍 [DEBUG] Checking dependency '{dep_phase_id}' status: {dep_phase.status}")
            if dep_phase.status != PhaseStatus.COMPLETED:
                self.logger.warning(f"⚠️ [DEBUG] Phase {phase_id} dependency {dep_phase_id} not completed")
                return False
        
        # Set current phase
        self.logger.info(f"🎯 [DEBUG] Setting current phase to: {phase_id}")
        self.conversation_state.set_current_phase(phase_id)
        
        self.logger.info(f"✅ [DEBUG] Starting phase: {phase.phase_name}")
        
        # Emit phase started event
        self.emit_event('phase_started', {
            'session_id': self.conversation_state.session_id,
            'phase_id': phase_id,
            'phase_name': phase.phase_name,
            'assigned_agents': phase.assigned_agents,
            'timestamp': datetime.now().isoformat()
        })
        
        # Use phase manager to handle phase logic
        self.logger.info(f"🔧 [DEBUG] Calling phase_manager.execute_phase({phase_id})")
        try:
            result = await self.phase_manager.execute_phase(phase_id)
            self.logger.info(f"📊 [DEBUG] phase_manager.execute_phase({phase_id}) returned: {result}")
            return result
        except Exception as e:
            self.logger.error(f"💥 [DEBUG] Exception in phase_manager.execute_phase({phase_id}): {e}")
            self.logger.error(f"🔍 [DEBUG] Full traceback:", exc_info=True)
            raise
    
    async def activate_agent(
        self,
        agent_id: str,
        task_description: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentOutput:
        """
        Activate an agent for task execution with conversation context.
        
        Args:
            agent_id: Agent identifier
            task_description: Task for the agent to perform
            context: Additional context for the agent
            
        Returns:
            AgentOutput: Agent's output for user review
        """
        self.logger.info(f"🤖 [DEBUG] activate_agent() called with agent_id: {agent_id}")
        self.logger.info(f"📝 [DEBUG] Task description: {task_description[:100]}...")
        
        # Check if agent exists in either traditional agents or conversational agents
        self.logger.info(f"🔍 [DEBUG] Available agents: {list(self.agents.keys())}")
        self.logger.info(f"🔍 [DEBUG] Available conversational agents: {list(self.conversational_agents.keys())}")
        
        if agent_id not in self.agents and agent_id not in self.conversational_agents:
            self.logger.error(f"❌ [DEBUG] Unknown agent: {agent_id}")
            raise ValueError(f"Unknown agent: {agent_id}")
        
        if not self.conversation_state:
            self.logger.error(f"❌ [DEBUG] No active conversation session for agent {agent_id}")
            raise ValueError("No active conversation session")
        
        # Get agent from traditional agents or create a mock for conversational agents
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            self.logger.info(f"✅ [DEBUG] Found agent in traditional agents: {agent_id}")
        else:
            # Create a mock agent for conversational agent system
            agent = Mock()
            agent.role = self.conversational_agents[agent_id].agent_id.replace('_', ' ').title()
            agent.agent_id = agent_id
            self.logger.info(f"🎭 [DEBUG] Created mock agent for conversational agent: {agent_id}")
        
        self.logger.info(f"🎯 [DEBUG] Setting agent {agent_id} status to WORKING")
        self.conversation_state.set_active_agent(agent_id, AgentStatus.WORKING)
        
        self.logger.info(f"🚀 [DEBUG] Activating agent: {agent_id}")
        
        # Emit agent started event
        self.emit_event('agent_started', {
            'session_id': self.conversation_state.session_id,
            'agent_id': agent_id,
            'agent_name': agent.role,
            'task_description': task_description,
            'timestamp': datetime.now().isoformat()
        })
        
        # Prepare agent context
        self.logger.info(f"📋 [DEBUG] Preparing agent context for {agent_id}")
        agent_context = self._prepare_agent_context(agent_id, context)
        
        try:
            # Execute agent task (this will be refined in next steps)
            self.logger.info(f"⚙️ [DEBUG] Executing agent task for {agent_id}")
            result = await self._execute_agent_task(agent, task_description, agent_context)
            self.logger.info(f"✅ [DEBUG] Agent task completed for {agent_id}, result length: {len(result) if result else 0}")
        except Exception as e:
            self.logger.error(f"💥 [DEBUG] Exception in _execute_agent_task for {agent_id}: {e}")
            self.logger.error(f"🔍 [DEBUG] Full traceback:", exc_info=True)
            raise
            
            # Create agent output
            output = AgentOutput(
                agent_id=agent_id,
                agent_name=agent.role,
                phase=self.conversation_state.current_phase,
                content=result,
                timestamp=datetime.now(),
                metadata={'context': agent_context}
            )
            
            # Add to conversation state
            self.conversation_state.add_agent_output(output)
            
            # Store agent output in enhanced context manager
            self.context_manager.store_context(
                content={
                    'agent_output': result,
                    'agent_name': agent.role,
                    'task_description': task_description,
                    'execution_metadata': agent_context
                },
                context_type=ContextType.AGENT,
                priority=MemoryPriority.HIGH,
                tags={agent_id, 'agent_output', self.conversation_state.current_phase or 'unknown'},
                source_agent=agent_id,
                phase_id=self.conversation_state.current_phase
            )
            
            # Update agent status
            self.conversation_state.set_active_agent(agent_id, AgentStatus.WAITING_FOR_HUMAN)
            
            self.logger.info(f"Agent {agent_id} completed task")
            
            # Log agent output to session file (for debugging)
            try:
                from api.main import get_session_logger
                session_logger = get_session_logger(self.conversation_state.session_id)
                session_logger.log_agent_output(agent_id, result)
            except Exception as e:
                self.logger.warning(f"Failed to log agent output: {e}")
            
            # Emit agent completed event
            self.emit_event('agent_completed', {
                'session_id': self.conversation_state.session_id,
                'agent_id': agent_id,
                'output_preview': result[:200] + '...' if len(result) > 200 else result,
                'timestamp': datetime.now().isoformat()
            })
            
            # Emit agent output event for frontend display
            self.emit_event('agent_output', {
                'session_id': self.conversation_state.session_id,
                'output': output.to_dict()
            })
            
            return output
            
        except Exception as e:
            self.logger.error(f"Agent {agent_id} execution failed: {e}")
            
            # Use error recovery system to handle the failure
            recovery_context = {
                'session_id': self.conversation_state.session_id,
                'phase_id': self.conversation_state.current_phase,
                'agent_id': agent_id,
                'task_description': task_description,
                'agent_context': agent_context
            }
            
            recovery_result = await self.error_recovery.handle_error(
                error=e,
                context=recovery_context,
                operation='agent_execution',
                component=f'agent_{agent_id}'
            )
            
            if recovery_result.success and isinstance(recovery_result.output, AgentOutput):
                # Recovery succeeded, return recovered output
                self.logger.info(f"Agent {agent_id} recovered successfully")
                self.conversation_state.add_agent_output(recovery_result.output)
                self.conversation_state.set_active_agent(agent_id, AgentStatus.WAITING_FOR_HUMAN)
                return recovery_result.output
            else:
                # Recovery failed, set error status and emit error event
                self.conversation_state.set_active_agent(agent_id, AgentStatus.ERROR)
                
                # Emit error event
                self.emit_event('error_occurred', {
                    'session_id': self.conversation_state.session_id,
                    'agent_id': agent_id,
                    'error': str(e),
                    'recovery_attempted': True,
                    'recovery_success': recovery_result.success,
                    'timestamp': datetime.now().isoformat()
                })
                
                raise
    
    def _prepare_agent_context(self, agent_id: str, additional_context: Optional[Dict] = None) -> Dict[str, Any]:
        """Prepare comprehensive context for agent execution using enhanced context manager"""
        
        # Get intelligent context summary from context manager
        context_summary = self.context_manager.get_context_summary(self.conversation_state)
        
        # Base context from conversation state
        context = {
            'course_request': self.conversation_state.course_request,
            'frameworks': self.conversation_state.frameworks,
            'current_phase': self.conversation_state.current_phase,
            'conversation_history': self.conversation_state.conversation_history[-10:],  # Last 10 turns
            'previous_outputs': {},
            'global_context': self.conversation_state.context_memory['global_context'],
            'agent_context': self.conversation_state.context_memory['agent_contexts'].get(agent_id, {}),
            'phase_context': self.conversation_state.context_memory['phase_contexts'].get(
                self.conversation_state.current_phase, {}
            )
        }
        
        # Add enhanced context from context manager
        context.update({
            'enhanced_context': context_summary,
            'relevant_phase_context': context_summary['current_phase_context'],
            'relevant_global_context': context_summary['global_context'],
            'procedural_knowledge': context_summary['procedural_context']
        })
        
        # Add previous phase outputs for continuity
        for prev_agent_id, outputs in self.conversation_state.agent_outputs.items():
            if outputs:
                latest_output = outputs[-1]
                if latest_output.is_approved:
                    context['previous_outputs'][prev_agent_id] = {
                        'content': latest_output.content,
                        'phase': latest_output.phase,
                        'agent_name': latest_output.agent_name
                    }
        
        # Store this context preparation as procedural knowledge
        self.context_manager.store_context(
            content={
                'agent_id': agent_id,
                'context_keys': list(context.keys()),
                'preparation_time': datetime.now().isoformat(),
                'phase': self.conversation_state.current_phase
            },
            context_type=ContextType.PROCEDURAL,
            priority=MemoryPriority.LOW,
            tags={'context_preparation', agent_id},
            source_agent='orchestrator',
            phase_id=self.conversation_state.current_phase
        )
        
        # Merge additional context
        if additional_context:
            context.update(additional_context)
        
        return context
    
    async def _execute_agent_task(
        self,
        agent: Agent,
        task_description: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Execute agent task with conversation context using conversational agent wrappers.
        """
        # Get agent ID from the agent role or use a mapping
        agent_id = self._get_agent_id_from_agent(agent)
        
        if agent_id and agent_id in self.conversational_agents:
            # Use conversational agent wrapper for execution
            try:
                self.logger.info(f"Executing task via conversational agent: {agent_id}")
                
                # Prepare conversation history for context
                conversation_history = []
                if self.conversation_state and self.conversation_state.conversation_history:
                    conversation_history = self.conversation_state.conversation_history[-10:]  # Last 10 turns
                
                # Execute through the agent wrapper
                result = await self.agent_executor.execute_agent_task(
                    agent_id=agent_id,
                    task_description=task_description,
                    context=context,
                    conversation_history=conversation_history
                )
                
                if result.success:
                    self.logger.info(f"Agent {agent_id} completed task successfully")
                    return result.output
                else:
                    self.logger.error(f"Agent {agent_id} failed: {result.error_message}")
                    return f"Agent execution failed: {result.error_message}"
                    
            except Exception as e:
                self.logger.error(f"Error executing agent {agent_id}: {e}")
                # Fall back to placeholder if agent execution fails
                return await self._fallback_agent_execution(agent, task_description, context)
        else:
            # Fall back to placeholder execution for agents not in conversational system
            self.logger.warning(f"Agent {agent_id} not found in conversational agents, using fallback")
            return await self._fallback_agent_execution(agent, task_description, context)
    
    def _get_agent_id_from_agent(self, agent: Agent) -> Optional[str]:
        """Map CrewAI agent to agent ID for conversational system"""
        # Try to find agent by role matching
        for agent_id, crewai_agent in self.agents.items():
            if crewai_agent == agent or crewai_agent.role == agent.role:
                return agent_id
        
        # Try to infer from role name
        role_lower = agent.role.lower()
        if "coordinator" in role_lower:
            return "hailei4t_coordinator_agent"
        elif "instructional planning" in role_lower or "ipdai" in role_lower:
            return "ipdai_agent"
        elif "content authoring" in role_lower or "cauthai" in role_lower:
            return "cauthai_agent"
        elif "technical" in role_lower or "tfdai" in role_lower:
            return "tfdai_agent"
        elif "editor" in role_lower or "editorai" in role_lower:
            return "editorai_agent"
        elif "ethical" in role_lower or "ethosai" in role_lower:
            return "ethosai_agent"
        elif "search" in role_lower or "searchai" in role_lower:
            return "searchai_agent"
        
        return None
    
    async def _fallback_agent_execution(
        self,
        agent: Agent,
        task_description: str,
        context: Dict[str, Any]
    ) -> str:
        """Fallback placeholder execution for agents not in conversational system"""
        try:
            course_title = context.get('course_request', {}).get('course_title', 'the course')
            current_phase = context.get('current_phase', 'unknown')
            
            # Create contextually appropriate response based on agent role
            if "coordinator" in agent.role.lower():
                result = f"""Hello! I'm the HAILEI Educational Intelligence Coordinator, and I'm excited to work with you on designing "{course_title}".

I orchestrate a team of specialist AI agents who each bring unique expertise to course design:
- **IPDAi**: Instructional Planning & Design using our KDKA framework
- **CAuthAi**: Content Authoring with PRRR engagement methodology  
- **TFDAi**: Technical & Functional Design for LMS implementation
- **EditorAi**: Content Review & Enhancement with accessibility compliance
- **EthosAi**: Ethical Oversight & UDL validation

We're currently in the {current_phase.replace('_', ' ').title()} phase. How would you like to proceed?"""

            elif "instructional planning" in agent.role.lower() or "ipdai" in agent.role.lower():
                result = f"""I'm IPDAi, your Instructional Planning & Design specialist. For "{course_title}", I'll create a comprehensive foundation using our proprietary KDKA framework:

**Knowledge**: Learning objectives aligned with Bloom's taxonomy
**Delivery**: Multi-modal approaches suited to your learners  
**Context**: Authentic scenarios and equity considerations
**Assessment**: Formative and summative measures aligned to outcomes

I'm ready to begin developing your course structure. What specific aspects would you like me to focus on first?"""

            elif "authoring" in agent.role.lower() or "cauthai" in agent.role.lower():
                result = f"""I'm CAuthAi, your Content Authoring specialist. I'll develop engaging instructional content for "{course_title}" using our PRRR framework:

**Personal**: Connecting to learner experiences and goals
**Relatable**: Using analogies and cross-disciplinary examples
**Relative**: Comparing options, methods, and approaches
**Real-world**: Anchoring activities in authentic contexts

I'm ready to create compelling learning experiences. What type of content should we develop first?"""

            else:
                # Generic response for other agents
                result = f"""I'm {agent.role}, ready to contribute my expertise to "{course_title}". 

Current task: {task_description}

I'm working within the {current_phase.replace('_', ' ').title()} phase and will ensure my work builds upon previous outputs while maintaining alignment with the KDKA and PRRR frameworks.

How can I best assist with this phase of your course design?"""
            
            return result
            
        except Exception as e:
            self.logger.error(f"Fallback execution failed for {agent.role}: {e}")
            return f"I'm {agent.role}, ready to help with your course design. Due to a technical issue, I'm operating in simplified mode. Please let me know how I can assist you."
    
    async def request_user_input(
        self,
        message: str,
        input_type: str = "approval",
        options: Optional[List[str]] = None,
        timeout: Optional[int] = None
    ) -> str:
        """
        Request user input through HumanLayer with frontend integration.
        
        Args:
            message: Message to display to user
            input_type: Type of input (approval, feedback, choice)
            options: Available options for choice input
            timeout: Timeout in seconds
            
        Returns:
            str: User's response
        """
        if not self.conversation_state:
            raise ValueError("No active conversation session")
        
        # Set pending user input state
        input_data = {
            'message': message,
            'input_type': input_type,
            'options': options,
            'timestamp': datetime.now().isoformat(),
            'agent_id': self.conversation_state.active_agent,
            'phase_id': self.conversation_state.current_phase
        }
        
        self.conversation_state.set_pending_user_input(input_data)
        
        # Emit user input required event
        self.emit_event('user_input_required', {
            'session_id': self.conversation_state.session_id,
            'input_data': input_data
        })
        
        # Use HumanLayer for actual input collection
        try:
            if input_type == "approval":
                response = await self._get_approval_input(message)
            elif input_type == "feedback":
                response = await self._get_feedback_input(message)
            elif input_type == "choice":
                response = await self._get_choice_input(message, options or [])
            else:
                response = await self._get_text_input(message)
            
            # Clear pending input
            self.conversation_state.clear_pending_user_input()
            
            # Add to conversation history
            self.conversation_state.add_conversation_turn("user", response)
            
            return response
            
        except Exception as e:
            self.logger.error(f"User input collection failed: {e}")
            self.conversation_state.clear_pending_user_input()
            raise
    
    async def _get_approval_input(self, message: str) -> str:
        """Get user approval through WebSocket/Frontend"""
        # Set the agent status to waiting for human input
        if self.conversation_state and self.conversation_state.active_agent:
            self.conversation_state.set_active_agent(
                self.conversation_state.active_agent, 
                AgentStatus.WAITING_FOR_HUMAN
            )
        
        # Return a special signal that means "wait for user input via WebSocket"
        # The actual approval will come through process_user_message with message_type="approval"
        return "WAITING_FOR_USER_INPUT"
    
    async def _get_feedback_input(self, message: str) -> str:
        """Get user feedback through HumanLayer"""
        # Placeholder for HumanLayer feedback integration
        return "No feedback provided"  # Will be replaced with actual HumanLayer call
    
    async def _get_choice_input(self, message: str, options: List[str]) -> str:
        """Get user choice through HumanLayer"""
        # Placeholder for HumanLayer choice integration
        return options[0] if options else "default"  # Will be replaced with actual HumanLayer call
    
    async def _get_text_input(self, message: str) -> str:
        """Get user text input through HumanLayer"""
        # Placeholder for HumanLayer text integration
        return "User response"  # Will be replaced with actual HumanLayer call
    
    async def process_user_feedback(
        self,
        agent_id: str,
        feedback: str,
        phase_id: Optional[str] = None
    ) -> AgentOutput:
        """
        Process user feedback and trigger agent refinement.
        
        Args:
            agent_id: Agent to refine output
            feedback: User feedback for improvement
            phase_id: Phase context for feedback
            
        Returns:
            AgentOutput: Refined agent output
        """
        if not self.conversation_state:
            raise ValueError("No active conversation session")
        
        phase_id = phase_id or self.conversation_state.current_phase
        
        # Add feedback to conversation state
        self.conversation_state.add_user_feedback(agent_id, feedback, phase_id)
        
        # Store feedback in context manager for learning
        self.context_manager.store_context(
            content={
                'feedback': feedback,
                'agent_id': agent_id,
                'phase_id': phase_id,
                'feedback_type': 'refinement_request',
                'timestamp': datetime.now().isoformat()
            },
            context_type=ContextType.USER,
            priority=MemoryPriority.HIGH,
            tags={'user_feedback', agent_id, phase_id or 'unknown'},
            source_agent=agent_id,
            phase_id=phase_id
        )
        
        # Add to conversation history
        self.conversation_state.add_conversation_turn("user", f"Feedback for {agent_id}: {feedback}")
        
        # Emit refinement cycle event
        self.emit_event('refinement_cycle', {
            'session_id': self.conversation_state.session_id,
            'agent_id': agent_id,
            'feedback': feedback,
            'cycle_number': self.conversation_state.refinement_cycles.get(f"{agent_id}_{phase_id}", 1),
            'timestamp': datetime.now().isoformat()
        })
        
        # Use refinement engine to process feedback
        return await self.refinement_engine.refine_output(agent_id, feedback, phase_id)
    
    async def approve_output(self, agent_id: str, phase_id: Optional[str] = None) -> bool:
        """
        Approve agent output and proceed to next step.
        
        Args:
            agent_id: Agent whose output to approve
            phase_id: Phase context for approval
            
        Returns:
            bool: Success status
        """
        if not self.conversation_state:
            raise ValueError("No active conversation session")
        
        phase_id = phase_id or self.conversation_state.current_phase
        
        # Mark output as approved
        self.conversation_state.approve_output(agent_id, phase_id)
        
        # Add to conversation history
        self.conversation_state.add_conversation_turn(
            "user", 
            f"Approved output from {agent_id} for {phase_id}"
        )
        
        # Update agent status
        self.conversation_state.set_active_agent(agent_id, AgentStatus.COMPLETED)
        
        self.logger.info(f"Approved output from {agent_id} for {phase_id}")
        
        return True
    
    async def complete_phase(self, phase_id: str) -> bool:
        """
        Complete current phase and transition to next.
        
        Args:
            phase_id: Phase to complete
            
        Returns:
            bool: Success status
        """
        if not self.conversation_state:
            raise ValueError("No active conversation session")
        
        if phase_id not in self.conversation_state.phases:
            raise ValueError(f"Unknown phase: {phase_id}")
        
        phase = self.conversation_state.phases[phase_id]
        
        # Check if all required agents have completed and been approved
        all_approved = True
        for agent_id in phase.assigned_agents:
            output = self.conversation_state.get_latest_output(agent_id, phase_id)
            if not output or not output.is_approved:
                all_approved = False
                break
        
        if not all_approved:
            self.logger.warning(f"Cannot complete phase {phase_id}: not all outputs approved")
            return False
        
        # Complete the phase
        phase.status = PhaseStatus.COMPLETED
        phase.completed_at = datetime.now()
        
        # Move completed agents to phase completion list
        phase.completed_agents = phase.assigned_agents.copy()
        phase.active_agents = []
        
        self.logger.info(f"Completed phase: {phase.phase_name}")
        
        # Emit phase completed event
        self.emit_event('phase_completed', {
            'session_id': self.conversation_state.session_id,
            'phase_id': phase_id,
            'phase_name': phase.phase_name,
            'completed_agents': phase.completed_agents,
            'timestamp': datetime.now().isoformat()
        })
        
        return True
    
    def get_next_phase(self) -> Optional[str]:
        """Get next phase in the workflow sequence"""
        if not self.conversation_state:
            return None
        
        current_index = -1
        if self.conversation_state.current_phase:
            try:
                current_index = self.conversation_state.phase_order.index(
                    self.conversation_state.current_phase
                )
            except ValueError:
                pass
        
        next_index = current_index + 1
        if next_index < len(self.conversation_state.phase_order):
            return self.conversation_state.phase_order[next_index]
        
        return None
    
    async def continue_workflow(self) -> bool:
        """Continue to next phase in the workflow"""
        next_phase = self.get_next_phase()
        if next_phase:
            return await self.begin_phase(next_phase)
        return False
    
    async def execute_phase_with_parallel_coordination(
        self,
        phase_id: str,
        agent_tasks: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, AgentOutput]:
        """
        Execute a phase using intelligent parallel coordination with decision engine.
        
        Args:
            phase_id: Phase to execute
            agent_tasks: Optional list of specific agent tasks
            
        Returns:
            Dict of agent_id -> AgentOutput results
        """
        if not self.conversation_state:
            raise ValueError("No active conversation session")
        
        # Set current phase
        self.conversation_state.set_current_phase(phase_id)
        
        # Create default tasks if none provided
        if not agent_tasks:
            agent_tasks = self._create_default_phase_tasks(phase_id)
        
        # Use decision engine to optimize execution strategy
        available_agents = [task['agent_id'] for task in agent_tasks]
        decision_context = DecisionContext(
            phase_id=phase_id,
            current_state=self.conversation_state,
            available_agents=available_agents,
            execution_history=self.parallel_orchestrator.execution_history,
            performance_metrics=self.decision_engine.agent_success_rates,
            user_preferences=self.conversation_state.context_memory.get('user_preferences', {})
        )
        
        # Get execution strategy recommendation
        execution_decision = await self.decision_engine.make_execution_decision(decision_context)
        self.logger.info(f"Decision engine recommends: {execution_decision.decision_value.value} execution")
        
        # Convert to ParallelTask objects
        parallel_tasks = []
        for task_data in agent_tasks:
            parallel_task = ParallelTask(
                agent_id=task_data['agent_id'],
                task_description=task_data['task_description'],
                context=task_data.get('context', {}),
                dependencies=task_data.get('dependencies', []),
                priority=task_data.get('priority', 1),
                estimated_duration=task_data.get('estimated_duration', 60.0)
            )
            parallel_tasks.append(parallel_task)
        
        # Optimize priorities if needed
        if execution_decision.confidence.value in ['high', 'very_high']:
            priority_decision = await self.decision_engine.optimize_workflow_priorities(
                decision_context, parallel_tasks
            )
            
            # Apply optimized priorities
            for task in parallel_tasks:
                if task.agent_id in priority_decision.decision_value:
                    task.priority = priority_decision.decision_value[task.agent_id]
        
        # Execute with parallel coordination
        results = await self.parallel_orchestrator.execute_phase_with_parallel_coordination(
            phase_id, parallel_tasks, self.conversation_state
        )
        
        # Provide feedback to decision engine for learning
        execution_success_rate = len([r for r in results.values() if not r.metadata.get('error', False)]) / len(results)
        self.decision_engine.update_performance_feedback(
            f"execution_{phase_id}_{datetime.now().timestamp()}",
            execution_success_rate,
            {'phase_id': phase_id, 'execution_mode': execution_decision.decision_value.value}
        )
        
        # Emit phase completion event
        self.emit_event('phase_completed', {
            'session_id': self.conversation_state.session_id,
            'phase_id': phase_id,
            'phase_name': phase_id.replace('_', ' ').title(),
            'agent_count': len(results),
            'execution_mode': execution_decision.decision_value.value,
            'decision_confidence': execution_decision.confidence.value,
            'timestamp': datetime.now().isoformat()
        })
        
        return results
    
    def _create_default_phase_tasks(self, phase_id: str) -> List[Dict[str, Any]]:
        """Create default agent tasks for a phase"""
        
        phase_agent_mapping = {
            'course_overview': [
                {
                    'agent_id': 'hailei4t_coordinator_agent',
                    'task_description': 'Provide course overview and coordinate initial planning',
                    'dependencies': [],
                    'priority': 3
                }
            ],
            'foundation_design': [
                {
                    'agent_id': 'ipdai_agent',
                    'task_description': 'Create comprehensive course foundation using KDKA framework',
                    'dependencies': [],
                    'priority': 3
                },
                {
                    'agent_id': 'ethosai_agent',
                    'task_description': 'Conduct initial ethical review of course foundation',
                    'dependencies': [],
                    'priority': 1
                }
            ],
            'content_creation': [
                {
                    'agent_id': 'cauthai_agent',
                    'task_description': 'Create engaging content modules using PRRR framework',
                    'dependencies': ['ipdai_agent'],
                    'priority': 3
                },
                {
                    'agent_id': 'tfdai_agent',
                    'task_description': 'Design technical implementation and learning management',
                    'dependencies': [],
                    'priority': 2
                },
                {
                    'agent_id': 'searchai_agent',
                    'task_description': 'Research and gather relevant educational resources',
                    'dependencies': [],
                    'priority': 1
                }
            ],
            'technical_design': [
                {
                    'agent_id': 'tfdai_agent',
                    'task_description': 'Finalize technical course implementation',
                    'dependencies': ['cauthai_agent'],
                    'priority': 3
                }
            ],
            'quality_review': [
                {
                    'agent_id': 'editorai_agent',
                    'task_description': 'Comprehensive quality review and editing',
                    'dependencies': ['cauthai_agent'],
                    'priority': 3
                },
                {
                    'agent_id': 'ethosai_agent',
                    'task_description': 'Final ethical review and compliance check',
                    'dependencies': [],
                    'priority': 2
                }
            ],
            'ethical_audit': [
                {
                    'agent_id': 'ethosai_agent',
                    'task_description': 'Complete ethical audit and recommendations',
                    'dependencies': [],
                    'priority': 3
                }
            ],
            'final_integration': [
                {
                    'agent_id': 'hailei4t_coordinator_agent',
                    'task_description': 'Integrate all components and finalize course package',
                    'dependencies': ['editorai_agent', 'ethosai_agent'],
                    'priority': 3
                }
            ]
        }
        
        return phase_agent_mapping.get(phase_id, [])
    
    def get_parallel_execution_statistics(self) -> Dict[str, Any]:
        """Get parallel execution performance statistics"""
        return self.parallel_orchestrator.get_execution_statistics()
    
    def get_decision_engine_statistics(self) -> Dict[str, Any]:
        """Get decision engine performance statistics"""
        return self.decision_engine.get_decision_statistics()
    
    def get_context_manager_statistics(self) -> Dict[str, Any]:
        """Get context manager performance statistics"""
        return self.context_manager.get_context_statistics()
    
    def get_error_recovery_statistics(self) -> Dict[str, Any]:
        """Get error recovery system statistics"""
        return self.error_recovery.get_error_statistics()
    
    def store_global_context(
        self,
        content: Dict[str, Any],
        priority: MemoryPriority = MemoryPriority.MEDIUM,
        tags: Optional[Set[str]] = None
    ) -> str:
        """
        Store global context information that persists across phases.
        
        Args:
            content: Context content to store
            priority: Memory priority level
            tags: Tags for categorization
            
        Returns:
            str: Context ID
        """
        return self.context_manager.store_context(
            content=content,
            context_type=ContextType.GLOBAL,
            priority=priority,
            tags=tags or set(),
            source_agent='orchestrator'
        )
    
    def retrieve_relevant_context(
        self,
        context_types: List[ContextType],
        tags: Optional[Set[str]] = None,
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for current conversation state.
        
        Args:
            context_types: Types of context to retrieve
            tags: Optional tags for filtering
            max_results: Maximum number of results
            
        Returns:
            List of context content dictionaries
        """
        if not self.conversation_state:
            return []
        
        query = ContextQuery(
            context_types=context_types,
            tags=tags,
            phase_id=self.conversation_state.current_phase,
            max_results=max_results
        )
        
        entries = self.context_manager.retrieve_context(query, self.conversation_state)
        return [entry.content for entry in entries]
    
    async def request_intelligent_agent_selection(
        self,
        required_skills: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Request intelligent agent selection from decision engine.
        
        Args:
            required_skills: Skills needed for the task
            context: Additional context for selection
            
        Returns:
            str: Selected agent ID
        """
        if not self.conversation_state:
            raise ValueError("No active conversation session")
        
        # Get all available agents
        available_agents = list(self.agents.keys()) + list(self.conversational_agents.keys())
        
        # Create decision context
        decision_context = DecisionContext(
            phase_id=self.conversation_state.current_phase or "unknown",
            current_state=self.conversation_state,
            available_agents=available_agents,
            execution_history=self.parallel_orchestrator.execution_history,
            performance_metrics=self.decision_engine.agent_success_rates,
            user_preferences=self.conversation_state.context_memory.get('user_preferences', {})
        )
        
        # Get agent selection decision
        selection_decision = await self.decision_engine.make_agent_selection_decision(
            decision_context, required_skills
        )
        
        self.logger.info(f"Decision engine selected: {selection_decision.decision_value} (confidence: {selection_decision.confidence.value})")
        
        return selection_decision.decision_value
    
    def cleanup_session(self, session_id: str):
        """Clean up session resources"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            if self.conversation_state and self.conversation_state.session_id == session_id:
                self.conversation_state = None
            self.logger.info(f"Cleaned up session: {session_id}")
    
    async def process_session(self, session_id: str) -> Dict[str, Any]:
        """
        Process session to start the conversation workflow.
        
        Args:
            session_id: Session to process
            
        Returns:
            Dict containing session processing results
        """
        if not self.conversation_state or self.conversation_state.session_id != session_id:
            conversation_state = self.load_session(session_id)
            if not conversation_state:
                raise ValueError(f"Session {session_id} not found")
        
        try:
            # Start with coordinator agent introduction
            coordinator_response = await self.activate_agent(
                agent_id="hailei4t_coordinator_agent",
                task_description=f"Greet the user and introduce the HAILEI course design process for '{self.conversation_state.course_request.get('course_title', 'the course')}'. Explain that you will coordinate with specialist agents to create a comprehensive course design.",
                context={
                    "session_start": True,
                    "user_greeting": True
                }
            )
            
            # Set conversation as started
            self.conversation_state.add_conversation_turn(
                "agent", 
                coordinator_response.content, 
                "hailei4t_coordinator_agent"
            )
            
            self.logger.info(f"Session {session_id} conversation started successfully")
            
            return {
                "success": True,
                "coordinator_response": coordinator_response.content,
                "current_phase": self.conversation_state.current_phase,
                "session_id": session_id
            }
            
        except Exception as e:
            self.logger.error(f"Failed to process session {session_id}: {e}")
            raise
    
    async def process_user_message(
        self,
        session_id: str,
        user_message: str,
        message_type: str = "chat"
    ) -> Dict[str, Any]:
        """
        Process user message and generate appropriate response.
        
        Args:
            session_id: Session ID for the conversation
            user_message: User's message content
            message_type: Type of message (chat, approval, feedback)
            
        Returns:
            Dict containing agent response and metadata
        """
        if not self.conversation_state or self.conversation_state.session_id != session_id:
            conversation_state = self.load_session(session_id)
            if not conversation_state:
                raise ValueError(f"Session {session_id} not found")
        
        try:
            # Add user message to conversation history
            self.conversation_state.add_conversation_turn("user", user_message)
            
            # Determine which agent should respond based on current state
            active_agent_id = self.conversation_state.active_agent or "hailei4t_coordinator_agent"
            
            # Handle different message types
            if message_type == "approval":
                # User approving current output
                success = await self.approve_output(active_agent_id, self.conversation_state.current_phase)
                self.logger.info(f"Approval processed for {active_agent_id}: {success}")
                
                # Log approval to session file
                try:
                    from api.main import get_session_logger
                    session_logger = get_session_logger(self.conversation_state.session_id)
                    session_logger.log(f"User approved output from {active_agent_id} in phase {self.conversation_state.current_phase}")
                except Exception as e:
                    self.logger.warning(f"Failed to log approval: {e}")
                
                if success:
                    # Try to complete current phase
                    phase_completed = await self.complete_phase(self.conversation_state.current_phase)
                    self.logger.info(f"Phase completion result: {phase_completed}")
                    
                    if phase_completed:
                        # Continue to next phase
                        next_phase = self.get_next_phase()
                        self.logger.info(f"Next phase determined: {next_phase}")
                        
                        if next_phase:
                            await self.begin_phase(next_phase)
                            response_content = f"Thank you for your approval. Moving to the next phase: {next_phase.replace('_', ' ').title()}"
                        else:
                            response_content = "Congratulations! All phases have been completed. Your course design is ready!"
                    else:
                        response_content = "Thank you for your approval. Please wait while we complete the current phase."
                else:
                    response_content = "There was an issue processing your approval. Please try again."
                
                agent_id = "hailei4t_coordinator_agent"
                
            elif message_type == "feedback":
                # User providing feedback for refinement
                refined_output = await self.process_user_feedback(
                    active_agent_id, 
                    user_message, 
                    self.conversation_state.current_phase
                )
                response_content = refined_output.content if refined_output else "Thank you for your feedback. I'll refine the output accordingly."
                agent_id = active_agent_id
                
            else:
                # Regular chat message - route to appropriate agent
                if active_agent_id == "hailei4t_coordinator_agent":
                    # Coordinator handles general questions and orchestration
                    task_description = f"Respond to the user's message: '{user_message}'. Provide helpful guidance about the course design process and determine if any specialist agents need to be activated."
                else:
                    # Specialist agent handles domain-specific questions
                    task_description = f"Continue your work and respond to the user's message: '{user_message}'. Provide clarification or refinements as needed."
                
                agent_response = await self.activate_agent(
                    agent_id=active_agent_id,
                    task_description=task_description,
                    context={"user_message": user_message, "conversation_context": True}
                )
                
                response_content = agent_response.content
                agent_id = active_agent_id
            
            # Add agent response to conversation history
            self.conversation_state.add_conversation_turn("agent", response_content, agent_id)
            
            return {
                "content": response_content,
                "agent": agent_id,
                "session_id": session_id,
                "current_phase": self.conversation_state.current_phase,
                "message_type": message_type,
                "suggestions": self._generate_suggestions()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to process user message in session {session_id}: {e}")
            
            # Return error response
            return {
                "content": f"I apologize, but I encountered an error processing your message: {str(e)}. Please try again.",
                "agent": "hailei4t_coordinator_agent",
                "session_id": session_id,
                "error": True
            }
    
    def _generate_suggestions(self) -> List[str]:
        """Generate context-appropriate suggestions for the user"""
        if not self.conversation_state:
            return []
        
        suggestions = []
        current_phase = self.conversation_state.current_phase
        
        if current_phase == "course_overview":
            suggestions = [
                "Tell me more about the KDKA framework",
                "What specialists will work on my course?",
                "How long will the course design process take?",
                "Can I modify the course requirements?"
            ]
        elif current_phase == "foundation_design":
            suggestions = [
                "Review the learning objectives",
                "Modify the course structure", 
                "Approve the foundation design",
                "Ask for clarification on the frameworks"
            ]
        elif current_phase == "content_creation":
            suggestions = [
                "Review the learning activities",
                "Suggest changes to content",
                "Approve the content design",
                "Ask about assessment methods"
            ]
        else:
            suggestions = [
                "Review current progress",
                "Approve current work",
                "Request modifications",
                "Continue to next phase"
            ]
        
        return suggestions

    def shutdown(self):
        """Shutdown orchestrator and cleanup resources"""
        self.stop_execution.set()
        self.executor.shutdown(wait=True)
        self.active_sessions.clear()
        self.conversation_state = None
        self.logger.info("Orchestrator shutdown complete")