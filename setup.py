from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="alaiy_os_connector_maestro",
    version="0.0.1",
    description="Maestro AI image studio connector for Alaiy OS",
    author="Alaiy OS",
    author_email="dev@alaiy.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
