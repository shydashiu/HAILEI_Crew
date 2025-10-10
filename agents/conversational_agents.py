"""
HAILEI Conversational Agent Factory

Factory for creating conversational agent wrappers from existing CrewAI agents.
Integrates with existing HAILEI agent configurations and tools.
"""

import os
import yaml
import logging
from typing import Dict, List, Optional, Any

from crewai import Agent
from .agent_wrappers import ConversationalAgentWrapper, AgentExecutor

# Import existing tools
from tools.blooms_taxonomy_tool import blooms_taxonomy_tool
from tools.accessibility_checker_tool import accessibility_checker_tool
from tools.resource_search_tool import resource_search_tool


class ConversationalAgentFactory:
    """
    Factory for creating conversational agents from existing HAILEI configurations.
    
    Features:
    - Load existing agent configurations
    - Create conversational wrappers
    - Initialize agent executor
    - Manage agent lifecycle
    """
    
    def __init__(
        self,
        agents_config_path: str = "config/agents.yaml",
        enable_logging: bool = True
    ):
        """
        Initialize agent factory.
        
        Args:
            agents_config_path: Path to agents configuration file
            enable_logging: Enable detailed logging
        """
        self.agents_config_path = os.path.abspath(agents_config_path)
        
        # Agent storage
        self.agent_configs: Dict[str, Dict] = {}
        self.crewai_agents: Dict[str, Agent] = {}
        self.conversational_wrappers: Dict[str, ConversationalAgentWrapper] = {}
        
        # Agent executor
        self.agent_executor = AgentExecutor(enable_logging=enable_logging)
        
        # Tool mappings
        self.available_tools = {
            'blooms_taxonomy_tool': blooms_taxonomy_tool,
            'accessibility_checker_tool': accessibility_checker_tool,
            'resource_search_tool': resource_search_tool
        }
        
        # Logging setup
        if enable_logging:
            self.logger = logging.getLogger('hailei_agent_factory')
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
        
        # Load agent configurations
        self._load_agent_configurations()
    
    def _load_agent_configurations(self):
        """Load agent configurations from YAML file"""
        try:
            with open(self.agents_config_path, 'r') as file:
                self.agent_configs = yaml.safe_load(file)
            
            self.logger.info(f"Loaded {len(self.agent_configs)} agent configurations")
            
        except FileNotFoundError:
            self.logger.error(f"Agent configuration file not found: {self.agents_config_path}")
            raise
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing agent configuration: {e}")
            raise
    
    def create_all_agents(self) -> Dict[str, ConversationalAgentWrapper]:
        """
        Create all conversational agent wrappers from configurations.
        
        Returns:
            Dict mapping agent_id to conversational wrapper
        """
        self.logger.info("Creating all conversational agents...")
        
        for agent_id in self.agent_configs.keys():
            try:
                wrapper = self.create_agent(agent_id)
                self.conversational_wrappers[agent_id] = wrapper
                self.agent_executor.register_agent(wrapper)
                
            except Exception as e:
                self.logger.error(f"Failed to create agent {agent_id}: {e}")
        
        self.logger.info(f"Created {len(self.conversational_wrappers)} conversational agents")
        return self.conversational_wrappers
    
    def create_agent(self, agent_id: str) -> ConversationalAgentWrapper:
        """
        Create individual conversational agent wrapper.
        
        Args:
            agent_id: Agent identifier from configuration
            
        Returns:
            ConversationalAgentWrapper: Wrapped agent
        """
        if agent_id not in self.agent_configs:
            raise ValueError(f"Agent configuration not found: {agent_id}")
        
        config = self.agent_configs[agent_id]
        
        # Prepare agent tools
        agent_tools = self._prepare_agent_tools(agent_id, config)
        
        # Create CrewAI agent
        crewai_agent = Agent(
            role=config.get('role', f'Agent {agent_id}'),
            goal=config.get('goal', 'Complete assigned tasks'),
            backstory=config.get('backstory', 'Specialized agent for educational tasks'),
            tools=agent_tools,
            verbose=True,
            memory=False,  # We handle memory through conversation state
            allow_delegation=config.get('allow_delegation', False)
        )
        
        # Store CrewAI agent
        self.crewai_agents[agent_id] = crewai_agent
        
        # Create conversational wrapper
        wrapper = ConversationalAgentWrapper(
            agent_id=agent_id,
            crewai_agent=crewai_agent,
            max_retries=2,
            timeout_seconds=300
        )
        
        self.logger.info(f"Created conversational agent: {agent_id}")
        return wrapper
    
    def _prepare_agent_tools(self, agent_id: str, config: Dict) -> List:
        """Prepare tools for specific agent based on configuration"""
        tools = []
        
        # Define tool assignments based on agent roles
        tool_assignments = {
            'ipdai_agent': ['blooms_taxonomy_tool'],
            'cauthai_agent': ['resource_search_tool'],
            'tfdai_agent': [],  # No specific tools for technical design
            'editorai_agent': ['accessibility_checker_tool', 'blooms_taxonomy_tool'],
            'ethosai_agent': ['accessibility_checker_tool'],
            'searchai_agent': ['resource_search_tool'],
            'hailei4t_coordinator_agent': []  # Coordinator uses delegation, not tools
        }
        
        # Get assigned tools for this agent
        assigned_tools = tool_assignments.get(agent_id, [])
        
        # Add tools to agent
        for tool_name in assigned_tools:
            if tool_name in self.available_tools:
                tools.append(self.available_tools[tool_name])
                self.logger.info(f"Added tool {tool_name} to agent {agent_id}")
        
        return tools
    
    def get_agent(self, agent_id: str) -> Optional[ConversationalAgentWrapper]:
        """Get conversational agent wrapper by ID"""
        return self.conversational_wrappers.get(agent_id)
    
    def get_crewai_agent(self, agent_id: str) -> Optional[Agent]:
        """Get underlying CrewAI agent by ID"""
        return self.crewai_agents.get(agent_id)
    
    def get_agent_executor(self) -> AgentExecutor:
        """Get agent executor for parallel execution"""
        return self.agent_executor
    
    def list_agents(self) -> List[str]:
        """List all available agent IDs"""
        return list(self.agent_configs.keys())
    
    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive agent information"""
        if agent_id not in self.agent_configs:
            return None
        
        config = self.agent_configs[agent_id]
        wrapper = self.conversational_wrappers.get(agent_id)
        
        info = {
            'agent_id': agent_id,
            'role': config.get('role'),
            'goal': config.get('goal'),
            'backstory': config.get('backstory'),
            'allow_delegation': config.get('allow_delegation', False),
            'has_wrapper': wrapper is not None
        }
        
        if wrapper:
            info.update({
                'performance_metrics': wrapper.get_performance_metrics(),
                'conversation_memory': wrapper.get_conversation_memory(),
                'wrapper_config': {
                    'max_retries': wrapper.max_retries,
                    'timeout_seconds': wrapper.timeout_seconds,
                    'execution_count': wrapper.execution_count
                }
            })
        
        return info
    
    def reload_configurations(self):
        """Reload agent configurations from file"""
        self.logger.info("Reloading agent configurations...")
        
        # Clear existing configurations
        self.agent_configs.clear()
        
        # Reload from file
        self._load_agent_configurations()
        
        self.logger.info("Agent configurations reloaded")
    
    def create_specialized_agents_dict(self) -> Dict[str, ConversationalAgentWrapper]:
        """
        Create dictionary of specialized agents for orchestrator integration.
        
        Returns:
            Dict mapping simplified names to agent wrappers
        """
        # Create all agents
        self.create_all_agents()
        
        # Map to simplified names for orchestrator
        specialized_agents = {}
        
        agent_mapping = {
            'coordinator': 'hailei4t_coordinator_agent',
            'ipdai': 'ipdai_agent',
            'cauthai': 'cauthai_agent', 
            'tfdai': 'tfdai_agent',
            'editorai': 'editorai_agent',
            'ethosai': 'ethosai_agent',
            'searchai': 'searchai_agent'
        }
        
        for simple_name, agent_id in agent_mapping.items():
            if agent_id in self.conversational_wrappers:
                specialized_agents[simple_name] = self.conversational_wrappers[agent_id]
            else:
                self.logger.warning(f"Agent {agent_id} not found for mapping to {simple_name}")
        
        self.logger.info(f"Created specialized agents dict with {len(specialized_agents)} agents")
        return specialized_agents
    
    def get_orchestrator_agents_dict(self) -> Dict[str, Agent]:
        """
        Get dictionary of CrewAI agents for orchestrator integration.
        
        Returns:
            Dict mapping simplified names to CrewAI agents
        """
        # Ensure agents are created
        if not self.crewai_agents:
            self.create_all_agents()
        
        # Map to simplified names for orchestrator
        orchestrator_agents = {}
        
        agent_mapping = {
            'coordinator': 'hailei4t_coordinator_agent',
            'ipdai': 'ipdai_agent',
            'cauthai': 'cauthai_agent',
            'tfdai': 'tfdai_agent', 
            'editorai': 'editorai_agent',
            'ethosai': 'ethosai_agent',
            'searchai': 'searchai_agent'
        }
        
        for simple_name, agent_id in agent_mapping.items():
            if agent_id in self.crewai_agents:
                # Use the full agent_id as the key for orchestrator compatibility
                orchestrator_agents[agent_id] = self.crewai_agents[agent_id]
            else:
                self.logger.warning(f"CrewAI agent {agent_id} not found for mapping to {simple_name}")
        
        return orchestrator_agents
    
    def shutdown(self):
        """Shutdown agent factory and cleanup resources"""
        self.logger.info("Shutting down agent factory...")
        
        # Clear all agent references
        self.conversational_wrappers.clear()
        self.crewai_agents.clear()
        self.agent_configs.clear()
        
        self.logger.info("Agent factory shutdown complete")
    
    def validate_configurations(self) -> Dict[str, List[str]]:
        """
        Validate agent configurations for completeness.
        
        Returns:
            Dict with validation results
        """
        validation_results = {
            'valid_agents': [],
            'invalid_agents': [],
            'warnings': []
        }
        
        required_fields = ['role', 'goal', 'backstory']
        
        for agent_id, config in self.agent_configs.items():
            is_valid = True
            
            # Check required fields
            for field in required_fields:
                if field not in config or not config[field]:
                    validation_results['warnings'].append(f"{agent_id}: Missing or empty {field}")
                    is_valid = False
            
            # Check role length
            if 'role' in config and len(config['role']) < 10:
                validation_results['warnings'].append(f"{agent_id}: Role description too short")
            
            # Check backstory length
            if 'backstory' in config and len(config['backstory']) < 50:
                validation_results['warnings'].append(f"{agent_id}: Backstory too short")
            
            if is_valid:
                validation_results['valid_agents'].append(agent_id)
            else:
                validation_results['invalid_agents'].append(agent_id)
        
        return validation_results