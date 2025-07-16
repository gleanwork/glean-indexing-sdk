"""Content formatting utility using Jinja2."""

import logging
from typing import Any, Dict

from jinja2 import Environment

logger = logging.getLogger(__name__)


class ContentFormatter:
    """A utility for formatting content using Jinja2 templates."""

    def __init__(self, template_str: str):
        """Initialize the ContentFormatter.

        Args:
            template_str: A Jinja2 template string.
        """
        self.env = Environment(autoescape=True)
        self.template = self.env.from_string(template_str)

    def render(self, context: Dict[str, Any]) -> str:
        """Render the template with the given context.

        Args:
            context: A dictionary containing the context for rendering.

        Returns:
            The rendered template as a string.
        """
        return self.template.render(**context)

    @classmethod
    def from_file(cls, template_path: str) -> "ContentFormatter":
        """Create a ContentFormatter from a template file.

        Args:
            template_path: Path to a Jinja2 template file.

        Returns:
            A ContentFormatter instance.
        
        Raises:
            FileNotFoundError: If the template file doesn't exist.
            PermissionError: If the template file can't be read.
            UnicodeDecodeError: If the template file contains invalid UTF-8.
        """
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_str = f.read()
        except FileNotFoundError:
            logger.error(f"Template file not found: {template_path}")
            raise
        except PermissionError:
            logger.error(f"Permission denied reading template file: {template_path}")
            raise
        except UnicodeDecodeError as e:
            logger.error(f"Invalid UTF-8 encoding in template file {template_path}: {e}")
            raise
        
        return cls(template_str)
