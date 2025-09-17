from setuptools import setup

setup(
    name="deepr",
    version="1.0.0",
    py_modules=["deepr"],
    install_requires=[
        "openai",
        "flask",
        "python-dotenv",
        "colorama",
        "python-docx",
        "docx2pdf",
        "pytz",
        "requests"
    ],
    entry_points={
        "console_scripts": [
            "deepr = deepr:cli_entry",
            "manager = manager:main"
        ]
    },
    author="blisspixel",
    description="Automated research pipeline using OpenAI's Deep Research API.",
    license="MIT"
)
