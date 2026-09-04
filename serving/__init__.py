"""
Model serving: the trained models behind a documented HTTP API.
===============================================================

Modules:
    api    FastAPI application exposing inference, online training, health,
           and metrics endpoints. Request and response schemas are declared
           as Pydantic models, so the OpenAPI documentation at /docs and the
           request validation are generated from one declaration and cannot
           drift apart.

Model loading order at startup:
    1. S3, when MODEL_BUCKET and MODEL_S3_PREFIX are set
    2. A local director.pt (full director state), if present
    3. A local player_model.pt (bare state_dict, which is what the training
       pipeline actually writes)
    4. Randomly initialised weights

Step 3 exists because the pipeline and the API disagreed about the artefact
shape, and serving silently fell back to random weights for months without
raising. tests/test_artifact_contract.py guards that seam now.

Note that inference here is a batch of one per request. The network uses
batch normalisation, which cannot compute a variance over a single sample,
so every call path must put the model in eval() first.
"""
