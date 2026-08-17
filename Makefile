.DEFAULT_GOAL := build
.PHONY: clean \
		install install_dependencies install_pre_commit \
		docs lint test build \
		generate_models

# general variables
PROJ_SLUG = quakesaver_client

clean:
	rm -rf .pytest_cache
	rm -rf build
	rm -rf docs/build
	rm -rf docs/source/modules
	rm -rf dist
	rm -rf quakesaver_client.egg-info
	rm -rf htmlcov
	rm -rf .coverage

install_dependencies:
	make build

install_pre_commit:
	uv run pre-commit install

install: install_dependencies install_pre_commit

build:
	uv build

lint:
	uv run pre-commit run --all-files

test:
	uv run py.test tests/* -vv --cov-report html --cov=$(PROJ_SLUG) -s

docs: clean
	uv run sphinx-apidoc -o ./docs/source/modules $(PROJ_SLUG)
	uv run cd docs && uv run make html

# datamodel-code-generator itself needs pydantic v2, while this package targets
# pydantic v1, so it runs in an isolated environment via uvx. The generated
# models stay on pydantic v1 through --output-model-type.
CODEGEN = uvx --from 'datamodel-code-generator>=0.73,<1' datamodel-codegen \
	--input-file-type jsonschema --output-model-type pydantic.BaseModel

generate_models:
	# can be deleted no usage
	rm pydantic_schemas/sensor_actions.schema.json || true
	# can be deleted due to state includes config
	rm pydantic_schemas/sensor_configs.schema.json || true
	$(CODEGEN) --input pydantic_schemas/data_products.schema.json --output quakesaver_client/models/data_products.py
	$(CODEGEN) --input pydantic_schemas/sensor_state.schema.json --output quakesaver_client/models/sensor_state.py
