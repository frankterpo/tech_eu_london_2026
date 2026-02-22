from setuptools import find_packages, setup


setup(
    name="agent",
    version="0.1.0",
    description="Envoice CLI Agent Trainer",
    long_description=(open("README.md", "r", encoding="utf-8").read()),
    long_description_content_type="text/markdown",
    python_requires=">=3.9",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "typer[all]>=0.12.0",
        "httpx>=0.27.0",
        "playwright>=1.42.0",
        "pydantic-settings>=2.2.0",
        "jsonschema>=4.21.0",
        "rich>=13.7.0",
        "supabase>=2.4.0",
        "python-dotenv>=1.0.1",
    ],
    entry_points={"console_scripts": ["agent=agent.main:app"]},
)
