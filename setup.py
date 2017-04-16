#!/usr/bin/env python
from setuptools import setup, find_packages


def main():
    with open('README.md', 'r') as f:
        long_description = f.read()

    with open('requirements.txt', 'r') as f:
        requirements = [line for line in f]

    setup(
        name='tick-feedstocks',
        version='0.0.0',
        description='Automatically update conda-forge feedstocks by '
                    'ticking versions, updating hashes, and creating pull requests.',
        long_descripton=long_description,
        author='Peter M. Landwehr',
        author_email='pmlandwehr@gmail.com',
        url='https://github.com/pmlandwehr/cf_maintainer_bot',
        license='BSD',
        classifiers=[
            'Development Status :: 3 - Alpha',
            'Intended Audience :: Developers',
            'Topic :: Software Development :: Build Tools',
            'License :: OSI Approved :: BSD License',
            'Programming Language :: Python :: 3.5',
        ],
        keywords='conda conda-forge',
        packages=find_packages(),
        install_requires=requirements,
        entry_points={
            'console_scripts': [
                'tick-feedstocks=tick-feedstocks.core:main'
            ],
        },
    )


if __name__ == '__main__':
    main()
