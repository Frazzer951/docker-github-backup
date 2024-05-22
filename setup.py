from setuptools import find_packages, setup

setup(
    name="github_backup",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["requests==2.32.2"],
    extras_require={
        "dev": [
            "ruff==0.4.4",
        ]
    },
)
