from setuptools import find_packages, setup

setup(
    name="shared-memory",
    version="0.1.0",
    description="Redis(可选) + SQLite 持久化的共享记忆池 SDK",
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    extras_require={"redis": ["redis>=5.0.0"]},
    entry_points={"console_scripts": ["shared-memory=shared_memory.cli:main"]},
)
