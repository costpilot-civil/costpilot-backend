from costpilot_core.material.attribute_extractor import AttributeExtractor
from costpilot_core.material.classifier import MaterialClassifier
from costpilot_core.material.config_loader import MaterialConfigLoader
from costpilot_core.material.material_extractor import MaterialExtractor
from costpilot_core.material.registry import MaterialRegistry


def build_material_extractor() -> MaterialExtractor:
    templates = MaterialConfigLoader().load_all()

    registry = MaterialRegistry(templates)

    return MaterialExtractor(
        registry=registry,
        classifier=MaterialClassifier(registry),
        attribute_extractor=AttributeExtractor(),
    )
