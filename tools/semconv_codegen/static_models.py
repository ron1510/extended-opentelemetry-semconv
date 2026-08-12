"""Generate committed Pydantic field models from semantic JSON Schema."""

from __future__ import annotations

import json

from datamodel_code_generator import (
    Formatter,
    GenerateConfig,
    InputFileType,
    PythonVersion,
    generate,
)
from datamodel_code_generator.enums import DataModelType, StrictTypes
from datamodel_code_generator.parser import LiteralType

from tools.semconv_codegen.semantic_schema import SemanticModel


def render_static_models(schema: str, models: tuple[SemanticModel, ...]) -> str:
    config = GenerateConfig(
        input_file_type=InputFileType.JsonSchema,
        output_model_type=DataModelType.PydanticV2BaseModel,
        target_python_version=PythonVersion.PY_312,
        base_class="extended_otel_semconv.entities.SemanticEntity",
        disable_timestamp=True,
        snake_case_field=True,
        extra_fields="forbid",
        enum_field_as_literal=LiteralType.All,
        strict_types=list(StrictTypes),
        field_constraints=True,
        use_annotated=True,
        use_generic_container_types=True,
        use_standard_collections=True,
        use_union_operator=True,
        skip_root_model=True,
        formatters=[Formatter.BUILTIN],
    )
    schema_document = json.loads(schema)
    schema_document.pop("$id", None)
    generated = generate(schema_document, config=config)
    if not isinstance(generated, str):
        raise RuntimeError("datamodel-code-generator did not return a single Python module")
    return generated.replace("#   filename:  <dict>\n", "#   source: semantic-entities.schema.json\n")
