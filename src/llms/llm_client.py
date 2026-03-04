import json
import os
import sys
import logging
from typing import Dict, Optional, Type

# Standard absolute imports for top-level packages (google, openai)
# Relative imports for package members

try:
    from .models.basemodel import BaseModel
    from .models.deepseek_r1 import DeepSeekR1Model
    from .models.llama3_2_vision import Llama3_2VisionModel
    from .models.gpt_unified import GPTUnified
    from .models.gemini import GeminiModel
except (ImportError, ValueError):
    # Fallback for standalone execution
    from src.llms.models.basemodel import BaseModel
    from src.llms.models.deepseek_r1 import DeepSeekR1Model
    from src.llms.models.llama3_2_vision import Llama3_2VisionModel
    from src.llms.models.gpt_unified import GPTUnified
    from src.llms.models.gemini import GeminiModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Map model names (from config.json) to their corresponding classes
MODEL_CLASS_MAP: Dict[str, Type[BaseModel]] = {
    "deepseek-r1-distill-qwen-7b": DeepSeekR1Model,
    "llama-3.2-vision": Llama3_2VisionModel,
    "gpt-4o": GPTUnified, # Mapping for gpt-4o
    "gpt-4o-mini": GPTUnified, # Add mapping for gpt-4o-mini
    "gpt-4.1-mini": GPTUnified,  
    "o4-mini": GPTUnified,  
    "gemini-2.0": GeminiModel,
    "gemini-pro-vision": GeminiModel,
    "gemini-2.5-flash": GeminiModel,
    "gemini-2.5-pro": GeminiModel,
}

class LLMClient:
    """
    Client layer for interacting with different LLM models for stock analysis.
    """

    def __init__(self, config_path: str = 'config/config.json'):
        self.config_path = config_path
        self.config: Optional[Dict] = None
        self.llm_config: Optional[Dict] = None
        self.model: Optional[BaseModel] = None
        self.prompt_template: Optional[str] = None

        try:
            self._load_config()
            self._initialize_model()
            self._load_prompt()
            logging.info("LLMClient initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize LLMClient: {e}", exc_info=True)
            self.model = None
            self.prompt_template = None

    def _load_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.llm_config = self.config.get('llms')
            if not self.llm_config:
                raise ValueError("LLM configuration ('llms') missing in config file.")
        except Exception as e:
            logging.error(f"Error loading configuration: {e}")
            raise

    def _initialize_model(self):
        current_model_name = self.llm_config.get('current_model', 'gpt-4o-mini')
        models_list = self.llm_config.get('models', [])
        model_config = next((m for m in models_list if m.get('name') == current_model_name), None)

        if not model_config:
            raise ValueError(f"Configuration for model '{current_model_name}' not found.")

        model_class = MODEL_CLASS_MAP.get(current_model_name)
        if not model_class:
            raise ValueError(f"No implementation class found for '{current_model_name}'.")

        self.model = model_class(model_config)
        logging.info(f"Instantiated model: {current_model_name}")

    def _load_prompt(self):
        prompt_file_name = self.llm_config.get('prompt_file')

        # Robust path finding for prompt file
        script_dir = os.path.dirname(os.path.abspath(__file__)) # src/llms
        project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))

        potential_paths = [
            os.path.join(script_dir, prompt_file_name),
            os.path.join(project_root, "src", "llms", prompt_file_name),
            os.path.join(project_root, prompt_file_name),
        ]

        prompt_file_path = next((p for p in potential_paths if os.path.exists(p)), None)
        if not prompt_file_path:
             raise FileNotFoundError(f"Prompt file '{prompt_file_name}' not found.")

        self.prompt_template = self.model.load_prompt_template(prompt_file_path)

    def analyze_stock(self, stock_data: dict) -> Optional[str]:
        if not self.model or not self.prompt_template:
            return None

        try:
            final_prompt = self.model.construct_prompt(self.prompt_template, stock_data)
            chart_image_path = stock_data.get('chart_image_path')
            return self.model.generate_analysis(final_prompt, chart_image_path)
        except Exception as e:
            logging.error(f"Error during stock analysis: {e}")
            return None
