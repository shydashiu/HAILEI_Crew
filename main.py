import sys
import traceback
import os
import signal
import atexit
import re
from datetime import datetime
from dotenv import load_dotenv

# Capture all output to crew_output.txt
class OutputCapture:
    def __init__(self, filename):
        self.filename = filename
        self.terminal = sys.stdout
        # Open file immediately
        self.log_file = open(self.filename, 'w', encoding='utf-8')
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.log_file and not self.log_file.closed:
            self.log_file.close()
            
    def close(self):
        if self.log_file and not self.log_file.closed:
            self.log_file.close()
            
    def write(self, message):
        # Write to both terminal and file
        self.terminal.write(message)
        if self.log_file and not self.log_file.closed:
            # Strip ANSI escape sequences for clean file output
            clean_message = self._strip_ansi(message)
            self.log_file.write(clean_message)
            self.log_file.flush()
            
    def _strip_ansi(self, text):
        """Remove ANSI escape sequences from text"""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
            
    def flush(self):
        self.terminal.flush()
        if self.log_file and not self.log_file.closed:
            self.log_file.flush()
            
    def isatty(self):
        # Required for CrewAI compatibility - delegate to terminal
        return self.terminal.isatty()
        
    def fileno(self):
        # Required for some terminal operations - delegate to terminal
        return self.terminal.fileno()
        
    def readable(self):
        # Required for some stream operations
        return False
        
    def writable(self):
        # Required for some stream operations
        return True

# Initialize output capture
output_capture = OutputCapture("crew_output.txt")
sys.stdout = output_capture

# Global cleanup function
def cleanup_output():
    """Ensure output capture is properly closed"""
    global output_capture
    if hasattr(output_capture, 'log_file') and output_capture.log_file:
        try:
            sys.stdout = output_capture.terminal
            output_capture.close()
            print("[DEBUG] Output capture cleanup completed")
        except Exception as e:
            print(f"[ERROR] Cleanup failed: {e}")

# Signal handlers for interruptions
def signal_handler(signum, frame):
    """Handle user interruptions (Ctrl+C, etc.)"""
    print(f"\n[WARNING] Received signal {signum}, cleaning up...")
    cleanup_output()
    sys.exit(1)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Termination

# Register cleanup function to run on exit
atexit.register(cleanup_output)

# Course request data - can be from form or API
SAMPLE_COURSE_REQUEST = {
    "course_title": "Introduction to Artificial Intelligence",
    "course_description": "This course provides a comprehensive introduction to Artificial Intelligence (AI), covering its foundations, history, and modern applications. Students will explore core AI concepts including problem-solving, search, knowledge representation, machine learning, and ethical implications of AI. Emphasis is placed on both theoretical underpinnings and practical applications across domains such as healthcare, business, and education. By the end of the course, students will be able to critically evaluate AI systems and demonstrate foundational skills in designing and applying AI techniques.",
    "course_credits": 3,
    "course_duration_weeks": 16,
    "course_level": "Undergraduate - Introductory",
    "course_expectations": "Students are expected to actively participate in discussions, complete weekly assignments, and engage with hands-on exercises. No prior AI experience is required, but familiarity with basic programming concepts (e.g., Python) and statistics is recommended. By the end of the course, students should be able to explain key AI concepts, evaluate AI applications, and demonstrate an understanding of the ethical and societal impacts of AI.",
    "course_modules": []
}

# HAILEI proprietary frameworks
KDKA_FRAMEWORK = {
    "summary": "KDKA aligns Knowledge, Delivery, Context, and Assessment so learning design centers the learner, not the teacher, and remains constructively aligned across modalities.",
    "pedagogical_basis": [
        "Learning is dynamic and contextual; design must connect content to learner needs.",
        "Delivery should span multiple modalities with accessibility in mind.",
        "Assessment must include formative and summative evidence aligned to outcomes."
    ],
    "how_to_use": "For each module, explicitly list target knowledge, choose delivery modes that fit learners and constraints, situate activities in authentic contexts, and align assessments to the stated outcomes.",
    "dimensions": {
        "knowledge": "Facts, concepts, skills, and metacognition tied to outcomes and Bloom levels.",
        "delivery": "Modalities and methods such as micro-lectures, labs, peer discussion, debates.",
        "context": "Authentic scenarios, stakeholders, constraints, and equity considerations.",
        "assessment": "Formative and summative checks aligned to outcomes; transparent criteria."
    },
    "ai_course_defaults": {
        "knowledge_examples": [
            "AI taxonomy and task types",
            "Data→Model→Prediction pipeline",
            "Evaluation metrics and tradeoffs",
            "Ethics, privacy, fairness, and responsible use"
        ],
        "delivery_examples": [
            "Short micro-lectures with transcripts",
            "Guided Colab notebooks with prewritten cells",
            "Case walkthroughs and think pair share",
            "Debate or fishbowl on policy topics"
        ],
        "context_examples": [
            "Campus services using AI (tutoring chatbots, search ranking)",
            "Sector cases (health, finance, arts, public sector)",
            "Stakeholder memos for non expert audiences"
        ],
        "assessment_examples": [
            "Auto graded quizzes for concepts",
            "Dataset cards and case memos",
            "Lab checkpoints with screenshots and rationale",
            "Final non expert brief and presentation"
        ]
    },
    "accessibility_equity_ethics": [
        "Provide transcripts, alt text, and low bandwidth materials.",
        "Avoid PII in datasets; document consent and provenance.",
        "Offer multiple demonstration modes for the same competency."
    ],
    "notes": "Use this object as shared context for agents to ensure consistent alignment across weekly modules and artifacts."
}

PRRR_FRAMEWORK = {
    "summary": "PRRR ensures each experience is Personal, Relatable, Relative, and Real to drive inclusion, engagement, and ethical relevance.",
    "how_to_use": "Every activity should touch at least two PRRR dimensions. Make relevance explicit in prompts, rubrics, and feedback.",
    "dimensions": {
        "personal": "Elicit prior experiences, goals, and choice of dataset/topic.",
        "relatable": "Use analogies and cross disciplinary links that honor diverse perspectives.",
        "relative": "Compare options, methods, metrics, risks, and benefits.",
        "real_world": "Anchor tasks in authentic stakeholders, decisions, and constraints."
    },
    "infusion_prompts": [
        "Personal Describe an AI tool you used recently. What did it help with and where did it fall short",
        "Relatable Explain training vs inference using a familiar analogy such as studying vs taking an exam",
        "Relative For your scenario which error is worse false positive or false negative and why",
        "Real world Draft an email advising a non expert on adopting an AI tool with benefits risks and mitigations",
        "Relatable Compare classification to sorting mail and regression to estimating delivery time",
        "Relative Choose two models and justify a recommendation using stakeholder aligned metrics"
    ],
    "ai_course_defaults": {
        "personalization_levers": [
            "Student selected open datasets aligned to major",
            "Choice of use case domain per module",
            "Reflection on value tradeoffs and comfort with risk"
        ],
        "relatability_patterns": [
            "Everyday analogies for core concepts",
            "Examples from multiple cultures and sectors",
            "Visuals and stories before formalism"
        ],
        "relative_frameworks": [
            "Confusion matrix plus cost framing",
            "Model comparison tables with metrics and tradeoffs",
            "Human rules vs data driven approaches"
        ],
        "real_world_outputs": [
            "Dataset cards and risk registers",
            "Stakeholder briefs and one pagers",
            "Policy snippets and responsible use guidelines"
        ]
    },
    "ethics_guardrails": [
        "Disclose limitations and uncertainty.",
        "Avoid sensitive data; document assumptions and mitigations.",
        "Encourage respectful debate and multiple viewpoints."
    ],
    "notes": "Use this object to embed PRRR signals in prompts, examples, rubrics, and peer review so relevance stays visible and accountable."
}

print("[DEBUG] Starting main.py execution")
print("[DEBUG] Output capture and signal handlers initialized")

# Load environment variables from .env file
print("[DEBUG] Loading environment variables...")
load_dotenv()

# Check if OpenAI API key is loaded
openai_key = os.getenv('OPENAI_API_KEY')
if openai_key:
    print("[DEBUG] OpenAI API key loaded successfully")
else:
    print("[ERROR] OpenAI API key not found in environment variables")
    print("[ERROR] Make sure your .env file exists and contains OPENAI_API_KEY=your_key_here")
    sys.exit(1)

try:
    print("[DEBUG] Attempting to import HAILEICourseDesign...")
    from hailei_crew_setup import HAILEICourseDesign
    print("[DEBUG] Import successful")
except Exception as e:
    print(f"[ERROR] Import failed: {e}")
    traceback.print_exc()
    sys.exit(1)

if __name__ == "__main__":
    try:
        print("[DEBUG] Entering main execution block")

        print("\n[INFO] Initializing HAILEI Course Design System...")
        print(f"[INFO] Course: {SAMPLE_COURSE_REQUEST['course_title']}")
        print(f"[INFO] Credits: {SAMPLE_COURSE_REQUEST['course_credits']}")
        print(f"[INFO] Duration: {SAMPLE_COURSE_REQUEST['course_duration_weeks']} weeks")
        print(f"[INFO] Level: {SAMPLE_COURSE_REQUEST['course_level']}")

        print("[DEBUG] About to initialize HAILEICourseDesign...")
        # Initialize HAILEI crew system
        hailei_system = HAILEICourseDesign()
        print("[DEBUG] HAILEICourseDesign initialized successfully")

        print(f"\n[INFO] Starting course design workflow...")
        print("[DEBUG] About to call run_course_design...")
        
        # Run the complete course design process
        result = hailei_system.run_course_design(
            course_request=SAMPLE_COURSE_REQUEST,
            kdka_framework=KDKA_FRAMEWORK,
            prrr_framework=PRRR_FRAMEWORK,
            lms_platform="Canvas"  # Default LMS platform
        )

        print("[DEBUG] run_course_design completed")

        # Save full output to file
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_filename = f"hailei_course_design_{timestamp}.txt"
        
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(f"=== HAILEI Course Design Output - {timestamp} ===\n")
            f.write(f"Course: {SAMPLE_COURSE_REQUEST['course_title']}\n")
            f.write(f"{'='*60}\n\n")
            f.write(str(result))
            f.write(f"\n\n{'='*60}\n")
            f.write(f"Design completed at: {datetime.now()}\n")

        print("\n--- HAILEI COURSE DESIGN COMPLETE ---\n")
        print(result)
        print(f"\n[INFO] Full design output saved to: {output_filename}")
        print("[DEBUG] Course design completed successfully")

    except Exception as e:
        error_msg = f"\nError occurred during HAILEI course design:\n\n{traceback.format_exc()}"
        print(error_msg)
        
        # Also save errors to file
        with open("hailei_error_log.txt", 'w', encoding='utf-8') as f:
            f.write(f"=== HAILEI Error - {datetime.now().strftime('%Y-%m-%d_%H-%M-%S')} ===\n")
            f.write(error_msg)
        
        print("[DEBUG] Error logged, cleanup will be handled by atexit")
        sys.exit(1)