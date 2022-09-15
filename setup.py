import setuptools

setuptools.setup(
    name="pycaen",
    version="0.2",
    author="Friedemann Neuhaus",
    author_email="friedemann@neuhaus-tech.de",
    description="Module to control CAEN USB devices",
    url="https://github.com/fneuhaus/pycaen",
    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),
    install_requires=["pyserial"],
)
