import os

from setuptools import Extension, setup


def get_mero_dir():
    m0path = os.environ.get('M0_SRC_DIR')
    if m0path:
        return m0path

    dirname = os.path.dirname(os.path.abspath(__file__))
    m0path = f'{dirname}/../../mero'
    return m0path


def get_mero_libs_dir():
    m0path = get_mero_dir()
    libs_dir = f'{m0path}/mero/.libs'
    return libs_dir


setup(
    name='hax',
    version='0.0.1',
    packages=['hax'],
    install_requires=['python-consul>=1.1.0'],
    entry_points={
        'console_scripts': ['hax=hax.hax:main'],
    },
    ext_modules=[
        Extension(name='libhax',
                  sources=['hax/hax.c'],
                  include_dirs=[get_mero_dir()],
                  define_macros=[('M0_INTERNAL', ''), ('M0_EXTERN', 'extern')],
                  library_dirs=[get_mero_libs_dir()],
                  runtime_library_dirs=[get_mero_libs_dir()],
                  libraries=['mero'],
                  extra_compile_args=[
                      '-g', '-Werror', '-Wall', '-Wextra', '-Wno-attributes',
                      '-Wno-unused-parameter', '-fPIC'
                  ])
    ],
)
