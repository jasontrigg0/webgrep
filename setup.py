from distutils.core import setup
setup(
    name = 'webgrep',
    packages = ['webgrep'],
    version = "0.0.2",
    description = 'Command line website scraper',
    author = "Jason Trigg",
    author_email = "jasontrigg0@gmail.com",
    url = "https://github.com/jasontrigg0/webgrep",
    download_url = 'https://github.com/jasontrigg0/webgrep/tarball/0.0.2',
    scripts=[],
    install_requires=[
        "beautifulsoup4",
    ],
    keywords = [],
    classifiers = [],
)
