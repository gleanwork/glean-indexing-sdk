"""Tests for the ContentFormatter utility."""

import os
import tempfile

from glean.indexing.utils import ContentFormatter


class TestContentFormatter:
    def test_render_simple_template(self):
        """Test rendering a simple template."""
        formatter = ContentFormatter("Hello, {{ name }}!")
        result = formatter.render({"name": "World"})
        assert result == "Hello, World!"

    def test_render_complex_template(self):
        """Test rendering a more complex template."""
        template = """
        <h1>{{ title }}</h1>
        <ul>
        {% for item in items %}
            <li>{{ item }}</li>
        {% endfor %}
        </ul>
        """
        formatter = ContentFormatter(template)
        result = formatter.render({"title": "My List", "items": ["Item 1", "Item 2", "Item 3"]})

        # Check for expected content
        assert "<h1>My List</h1>" in result
        assert "<li>Item 1</li>" in result
        assert "<li>Item 2</li>" in result
        assert "<li>Item 3</li>" in result

    def test_autoescape(self):
        """Test that HTML is properly escaped."""
        formatter = ContentFormatter("{{ html_content }}")
        result = formatter.render({"html_content": "<script>alert('XSS')</script>"})
        assert result == "&lt;script&gt;alert(&#39;XSS&#39;)&lt;/script&gt;"

    def test_from_file(self):
        """Test creating a formatter from a file."""
        # Create a temporary file with a template
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp:
            temp.write("Template from file: {{ message }}")
            temp_path = temp.name

        try:
            # Create formatter from the file and test it
            formatter = ContentFormatter.from_file(temp_path)
            result = formatter.render({"message": "It works!"})
            assert result == "Template from file: It works!"
        finally:
            # Clean up the temporary file
            os.unlink(temp_path)
