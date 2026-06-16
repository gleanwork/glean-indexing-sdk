import pytest
from glean.api_client.models.propertydefinition import PropertyDefinition, PropertyType, UIOptions

from glean.indexing.common.property_definition_builder import PropertyDefinitionBuilder
from glean.indexing.exceptions import InvalidPropertyError


class TestPropertyDefinitionBuilder:
    def test_basic_property_creation(self):
        """Test basic property creation with minimal parameters."""
        builder = PropertyDefinitionBuilder()
        properties = builder.add_property("test_name", "Test Label").build()

        assert len(properties) == 1
        prop = properties[0]
        assert prop.name == "test_name"
        assert prop.display_label == "Test Label"
        assert prop.property_type == PropertyType.TEXT.value
        assert prop.ui_options == UIOptions.SEARCH_RESULT.value
        assert prop.hide_ui_facet is False

    def test_property_creation_with_all_parameters(self):
        """Test property creation with all parameters specified."""
        builder = PropertyDefinitionBuilder()
        properties = builder.add_property(
            name="full_test",
            display_label="Full Test Label",
            display_label_plural="Full Test Labels",
            property_type=PropertyType.DATE,
            ui_options=UIOptions.DOC_HOVERCARD,
            hide_ui_facet=True,
            ui_facet_order=5,
            group="test_group",
        ).build()

        assert len(properties) == 1
        prop = properties[0]
        assert prop.name == "full_test"
        assert prop.display_label == "Full Test Label"
        assert prop.display_label_plural == "Full Test Labels"
        assert prop.property_type == PropertyType.DATE.value
        assert prop.ui_options == UIOptions.DOC_HOVERCARD.value
        assert prop.hide_ui_facet is True
        assert prop.ui_facet_order == 5
        assert prop.group == "test_group"

    def test_enum_value_conversion(self):
        """Test that enum objects are properly converted to string values."""
        builder = PropertyDefinitionBuilder()
        properties = builder.add_property(
            "enum_test",
            "Enum Test",
            property_type=PropertyType.INT,
            ui_options=UIOptions.SEARCH_RESULT,
        ).build()

        prop = properties[0]
        assert isinstance(prop.property_type, str)
        assert isinstance(prop.ui_options, str)
        assert prop.property_type == PropertyType.INT.value
        assert prop.ui_options == UIOptions.SEARCH_RESULT.value

    def test_method_chaining(self):
        """Test that the builder supports method chaining."""
        builder = PropertyDefinitionBuilder()
        properties = (
            builder.add_property("prop1", "Property 1")
            .add_property("prop2", "Property 2", property_type=PropertyType.USERID)
            .add_property("prop3", "Property 3", ui_options=UIOptions.DOC_HOVERCARD)
            .build()
        )

        assert len(properties) == 3
        assert properties[0].name == "prop1"
        assert properties[1].name == "prop2"
        assert properties[1].property_type == PropertyType.USERID.value
        assert properties[2].name == "prop3"
        assert properties[2].ui_options == UIOptions.DOC_HOVERCARD.value

    def test_optional_parameters_none_handling(self):
        """Test that None values for optional parameters are properly handled."""
        builder = PropertyDefinitionBuilder()
        properties = builder.add_property(
            "optional_test",
            "Optional Test",
            display_label_plural=None,
            ui_facet_order=None,
            group=None,
        ).build()

        prop = properties[0]
        assert not hasattr(prop, "display_label_plural") or prop.display_label_plural is None
        assert not hasattr(prop, "ui_facet_order") or prop.ui_facet_order is None
        assert not hasattr(prop, "group") or prop.group is None

    def test_string_trimming(self):
        """Test that string parameters are properly trimmed."""
        builder = PropertyDefinitionBuilder()
        properties = builder.add_property(
            "  trimmed_name  ",
            "  Trimmed Label  ",
            display_label_plural="  Trimmed Plural  ",
            group="  trimmed_group  ",
        ).build()

        prop = properties[0]
        assert prop.name == "trimmed_name"
        assert prop.display_label == "Trimmed Label"
        assert prop.display_label_plural == "Trimmed Plural"
        assert prop.group == "trimmed_group"

    def test_empty_name_validation(self):
        """Test that empty or whitespace-only names raise InvalidPropertyError."""
        builder = PropertyDefinitionBuilder()

        with pytest.raises(InvalidPropertyError, match="Invalid property 'name': cannot be empty"):
            builder.add_property("", "Valid Label")

        with pytest.raises(InvalidPropertyError, match="Invalid property 'name': cannot be empty"):
            builder.add_property("   ", "Valid Label")

    def test_empty_display_label_validation(self):
        """Test that empty or whitespace-only display labels raise InvalidPropertyError."""
        builder = PropertyDefinitionBuilder()

        with pytest.raises(
            InvalidPropertyError, match="Invalid property 'display_label': cannot be empty"
        ):
            builder.add_property("valid_name", "")

        with pytest.raises(
            InvalidPropertyError, match="Invalid property 'display_label': cannot be empty"
        ):
            builder.add_property("valid_name", "   ")

    def test_property_definition_creation_error_handling(self):
        """Test error handling when PropertyDefinition creation fails."""
        builder = PropertyDefinitionBuilder()

        with pytest.raises(InvalidPropertyError, match="Invalid property 'name': cannot be empty"):
            builder.add_property(None, "Test Label")  # type: ignore

    def test_clear_method(self):
        """Test that clear method removes all properties and supports chaining."""
        builder = PropertyDefinitionBuilder()
        builder.add_property("prop1", "Property 1")
        builder.add_property("prop2", "Property 2")

        assert builder.count() == 2

        result = builder.clear()
        assert result is builder
        assert builder.count() == 0
        assert len(builder.build()) == 0

    def test_count_method(self):
        """Test that count method returns the correct number of properties."""
        builder = PropertyDefinitionBuilder()

        assert builder.count() == 0

        builder.add_property("prop1", "Property 1")
        assert builder.count() == 1

        builder.add_property("prop2", "Property 2")
        assert builder.count() == 2

        builder.clear()
        assert builder.count() == 0

    def test_build_returns_copy(self):
        """Test that build returns a copy, not the original list."""
        builder = PropertyDefinitionBuilder()
        builder.add_property("prop1", "Property 1")

        properties1 = builder.build()
        properties2 = builder.build()

        assert properties1 is not properties2
        assert properties1 == properties2

        properties1.append("fake_property")  # type: ignore
        assert len(properties2) == 1

    def test_empty_builder_build(self):
        """Test that building an empty builder returns an empty list."""
        builder = PropertyDefinitionBuilder()
        properties = builder.build()

        assert isinstance(properties, list)
        assert len(properties) == 0

    def test_all_property_types(self):
        """Test that all PropertyType enum values work correctly."""
        builder = PropertyDefinitionBuilder()

        property_types = [
            PropertyType.TEXT,
            PropertyType.USERID,
            PropertyType.INT,
        ]

        for i, prop_type in enumerate(property_types):
            builder.add_property(f"prop_{i}", f"Property {i}", property_type=prop_type)

        properties = builder.build()
        assert len(properties) == len(property_types)

        for i, prop in enumerate(properties):
            assert prop.property_type == property_types[i].value

    def test_all_ui_options(self):
        """Test that all UIOptions enum values work correctly."""
        builder = PropertyDefinitionBuilder()

        ui_options = [
            UIOptions.SEARCH_RESULT,
            UIOptions.DOC_HOVERCARD,
        ]

        for i, ui_option in enumerate(ui_options):
            builder.add_property(f"prop_{i}", f"Property {i}", ui_options=ui_option)

        properties = builder.build()
        assert len(properties) == len(ui_options)

        for i, prop in enumerate(properties):
            assert prop.ui_options == ui_options[i].value

    def test_complex_workflow(self):
        """Test a complex workflow with multiple operations."""
        builder = PropertyDefinitionBuilder()

        builder.add_property("title", "Title", property_type=PropertyType.TEXT)
        builder.add_property("author", "Author", display_label_plural="Authors")
        assert builder.count() == 2

        builder.clear()
        assert builder.count() == 0

        properties = (
            builder.add_property("name", "Full Name", group="personal")
            .add_property("email", "Email Address", property_type=PropertyType.TEXT)
            .add_property("department", "Department", ui_options=UIOptions.DOC_HOVERCARD)
            .build()
        )

        assert len(properties) == 3
        assert all(isinstance(prop, PropertyDefinition) for prop in properties)
        assert properties[0].group == "personal"
        assert properties[2].ui_options == UIOptions.DOC_HOVERCARD.value
