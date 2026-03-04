import json
import os
import sys
import logging
from typing import Dict, Optional, Type

# Use relative imports for sibling packages/modules
from .models import BaseModel, DeepSeekR1Model, Llama3_2VisionModel, GPTUnified, GeminiModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Map model names (from config.json) to their corresponding classes
MODEL_CLASS_MAP: Dict[str, Type[BaseModel]] = {
    "deepseek-r1-distill-qwen-7b": DeepSeekR1Model,
    "llama-3.2-vision": Llama3_2VisionModel,
    "gpt-4o": GPTUnified,
    "gpt-4o-mini": GPTUnified,
    "gpt-4.1-mini": GPTUnified,
    "o4-mini": GPTUnified,
    "gemini-2.0": GeminiModel,
    "gemini-pro-vision": GeminiModel,
    "gemini-2.5-flash": GeminiModel,
    "gemini-2.5-pro": GeminiModel,
}

class LLMClient:
    def __init__(self, config_path: str = 'config/config.json'):
        # Ensure project root is available for path resolution
        self.script_dir = os.path.dirname(os.path.abspath(__file__)) # src/llms
        self.project_root = os.path.abspath(os.path.join(self.script_dir, "..", ".."))
        self.config_path = os.path.join(self.project_root, config_path)
        self.config = None
        self.llm_config = None
        self.model = None
        self.prompt_template = None
        try:
            self._load_config()
            self._initialize_model()
            self._load_prompt()
            logging.info("LLMClient initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize LLMClient: {e}")

    def _load_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.llm_config = self.config.get('llms')
        if not self.llm_config: raise ValueError("LLM config missing.")

    def _initialize_model(self):
        name = self.llm_config.get('current_model', 'gpt-4o-mini')
        models = self.llm_config.get('models', [])
        conf = next((m for m in models if m.get('name') == name), None)
        if not conf: raise ValueError(f"Model {name} not found.")
        cls = MODEL_CLASS_MAP.get(name)
        if not cls: raise ValueError(f"No class for {name}.")
        self.model = cls(conf)
        logging.info(f"Instantiated model: {name}")

    def _load_prompt(self):
        fname = self.llm_config.get('prompt_file')
        paths = [
            os.path.join(self.script_dir, fname),
            os.path.join(self.project_root, "src", "llms", fname),
            os.path.join(self.project_root, fname),
        ]
        fpath = next((p for p in paths if os.path.exists(p)), None)
        if not fpath: raise FileNotFoundError(f"Prompt {fname} not found.")
        self.prompt_template = self.model.load_prompt_template(fpath)

    def analyze_stock(self, stock_data: dict) -> Optional[str]:
        if not self.model or not self.prompt_template: return None
        try:
            prompt = self.model.construct_prompt(self.prompt_template, stock_data)
            return self.model.generate_analysis(prompt, stock_data.get('chart_image_path'))
        except Exception as e:
            logging.error(f"Error during analysis: {e}")
            return None
