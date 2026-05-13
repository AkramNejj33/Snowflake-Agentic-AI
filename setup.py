from setuptools import setup, find_packages

setup(
    name="snowflake-agentic-ai",
    version="0.1.0",
    description="Multi-agent AI system with Snowflake backend",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "snowflake-connector-python>=3.12.0",
        "google-genai>=1.0.0",
        "chromadb>=0.5.0",
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "streamlit>=1.41.0",
        "pandas>=2.2.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.10.0",
        "tenacity>=9.0.0",
    ],
)
