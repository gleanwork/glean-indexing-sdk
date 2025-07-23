from typing import List, Optional

from glean.api_client.models.propertydefinition import PropertyDefinition, PropertyType, UIOptions


class PropertyDefinitionBuilder:
    """
    Builder class for creating PropertyDefinition objects with a fluent interface.

    This class provides a convenient way to build multiple PropertyDefinition objects
    with proper validation and type safety.

    Example:
        builder = PropertyDefinitionBuilder()
        properties = (builder
            .add_property("title", "Title", property_type=PropertyType.TEXT)
            .add_property("author", "Author", display_label_plural="Authors")
            .build())
    """

    def __init__(self) -> None:
        self.properties: List[PropertyDefinition] = []

    def add_property(
        self,
        name: str,
        display_label: str,
        display_label_plural: Optional[str] = None,
        property_type: PropertyType = PropertyType.TEXT,
        ui_options: UIOptions = UIOptions.SEARCH_RESULT,
        hide_ui_facet: bool = False,
        ui_facet_order: Optional[int] = None,
        group: Optional[str] = None,
    ) -> "PropertyDefinitionBuilder":
        """
        Add a property definition to the builder.

        Args:
            name: The property name (must not be empty)
            display_label: The display label for the property
            display_label_plural: Optional plural form of the display label
            property_type: The type of property (defaults to TEXT)
            ui_options: UI options for the property (defaults to SEARCH_RESULT)
            hide_ui_facet: Whether to hide the UI facet
            ui_facet_order: Optional order for UI facet display
            group: Optional group name for the property

        Returns:
            Self for method chaining

        Raises:
            ValueError: If name or display_label is empty
        """
        if not name or not name.strip():
            raise ValueError("Property name cannot be empty")
        if not display_label or not display_label.strip():
            raise ValueError("Display label cannot be empty")

        base_params = {
            "name": name.strip(),
            "display_label": display_label.strip(),
            "property_type": property_type.value,
            "ui_options": ui_options.value,
            "hide_ui_facet": hide_ui_facet,
        }

        optional_params = {
            k: v
            for k, v in {
                "display_label_plural": display_label_plural.strip()
                if display_label_plural
                else None,
                "ui_facet_order": ui_facet_order,
                "group": group.strip() if group else None,
            }.items()
            if v is not None
        }

        params = {**base_params, **optional_params}

        try:
            prop = PropertyDefinition(**params)
            self.properties.append(prop)
        except Exception as e:
            raise ValueError(f"Failed to create PropertyDefinition: {e}") from e

        return self

    def clear(self) -> "PropertyDefinitionBuilder":
        """
        Clear all properties from the builder.

        Returns:
            Self for method chaining
        """
        self.properties.clear()
        return self

    def count(self) -> int:
        """
        Get the number of properties currently in the builder.

        Returns:
            Number of properties
        """
        return len(self.properties)

    def build(self) -> List[PropertyDefinition]:
        """
        Build and return the list of PropertyDefinition objects.

        Returns:
            List of PropertyDefinition objects
        """
        return self.properties.copy()
